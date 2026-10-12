"""OpenAlex whole-taxonomy counts (design §5.2, §8.5): works counted by primary topic at every level of the
taxonomy (domain, field, subfield, topic), for each publication year and each recent month, worldwide and for works
with an author at an Australian institution.

Counts only: no titles, no abstracts. Each `group_by` page is one OpenAlex "list" call, which costs 1 credit of the
key's free 10,000 a day. The key has no prepaid balance, so a call over the budget is refused (HTTP 429), never
billed. The run still checks the day's remaining credits before it starts and stops at a cap set in the card, so it
never starves other work of the day's budget.

One record per (level, scope, period): every group's id, name and count, with the total works the filter matched.
Each weekly run is a vintage: OpenAlex fills in recent periods late, so the same period's counts change from run to
run, and the store keeps every version.
"""

from __future__ import annotations

import logging
import os
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import Field

from ..config import Strict
from ..records import RawRecord, make_envelope, utc_now
from .base import CollectContext, CollectError

PARSER_VERSION = "openalex-counts-v1"
LEVELS = {
    "domain": "primary_topic.domain.id",
    "field": "primary_topic.field.id",
    "subfield": "primary_topic.subfield.id",
    "topic": "primary_topic.id",
}
SCOPES = {"world": None, "au": "authorships.countries:AU"}
# Pages a level needs, for the up-front estimate: 4 domains, 26 fields, 252 subfields and about 4,500 topics, at 200
# groups a page (OpenAlex, 2026-10-12). The run counts the real pages as it goes.
EST_PAGES = {"domain": 1, "field": 1, "subfield": 2, "topic": 23}
ID_PREFIX = "https://openalex.org/"

log = logging.getLogger("moria.collect.openalex")


class OpenAlexCountsParams(Strict):
    base_url: str = "https://api.openalex.org"
    api_key_env: str = "OPENALEX_API_KEY"  # the environment variable's name; its value is never logged or stored
    levels: list[Literal["domain", "field", "subfield", "topic"]] = Field(default_factory=lambda: list(LEVELS))
    scopes: list[Literal["world", "au"]] = Field(default_factory=lambda: list(SCOPES))
    from_year: int = 2010
    months_back: int = 36
    extra_filter: str = ""  # appended to every filter, e.g. "type:article|preprint|review"
    per_page: int = 200
    max_credits: int = 4000  # the run refuses to plan more than this
    reserve_credits: int = 1000  # the run stops rather than leave fewer than this for the rest of the day


@dataclass(frozen=True)
class Period:
    label: str  # "2024" or "2024-05"
    kind: Literal["year", "month"]
    first: date
    last: date

    @property
    def filter(self) -> str:
        if self.kind == "year":
            return f"publication_year:{self.first.year}"
        return f"from_publication_date:{self.first.isoformat()},to_publication_date:{self.last.isoformat()}"


def periods(day: date, from_year: int, months_back: int) -> list[Period]:
    """Every year from `from_year` to `day`'s year, then the `months_back` months ending with `day`'s month. The
    current year and month are partial; later vintages complete them."""
    out = [Period(str(y), "year", date(y, 1, 1), date(y, 12, 31)) for y in range(from_year, day.year + 1)]
    y, m = day.year, day.month
    months = []
    for _ in range(months_back):
        months.append(Period(f"{y:04d}-{m:02d}", "month", date(y, m, 1), date(y, m, monthrange(y, m)[1])))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out + sorted(months, key=lambda p: p.first)


def _short(key: str) -> str:
    return key.removeprefix(ID_PREFIX)


class OpenAlexCountsCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = OpenAlexCountsParams.model_validate(card.params)
        self.credits_used = 0
        self.remaining: int | None = None

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self.params.api_key_env, "")
        if not key:
            raise CollectError(f"openalex: {self.params.api_key_env} is not set (docs/setup.md)")
        return {"Authorization": f"Bearer {key}"}

    def _budget(self, ctx: CollectContext, headers: dict[str, str]) -> int:
        """Credits left today, from the free /rate-limit endpoint."""
        data = ctx.client.get(f"{self.params.base_url}/rate-limit", headers=headers).json()
        limits = data.get("rate_limit", {})
        if limits.get("prepaid_remaining_usd"):
            # A prepaid balance would turn calls over the free budget into spending: refuse, the owner decides.
            raise CollectError("openalex: the key has a prepaid balance, so calls over the free budget would be billed")
        return int(limits.get("credits_remaining", 0))

    def _plan(self, ctx: CollectContext) -> list[tuple[Period, str, str]]:
        plan = [
            (p, scope, level)
            for p in periods(ctx.window.day, self.params.from_year, self.params.months_back)
            for scope in self.params.scopes
            for level in self.params.levels
        ]
        return plan[: ctx.limit] if ctx.limit else plan

    def _filter(self, period: Period, scope: str) -> str:
        parts = [period.filter, SCOPES[scope], self.params.extra_filter]
        return ",".join(p for p in parts if p)

    def _groups(self, ctx: CollectContext, headers: dict[str, str], filt: str, level: str) -> tuple[dict, int, int]:
        """Every group for one filter and level, by cursor paging. Returns ({id: (name, count)}, total works, pages)."""
        groups: dict[str, tuple[str, int]] = {}
        cursor, pages, total = "*", 0, 0
        while cursor:
            resp = ctx.client.get(
                f"{self.params.base_url}/works",
                params={
                    "filter": filt,
                    "group_by": LEVELS[level],
                    "per_page": str(self.params.per_page),
                    "cursor": cursor,
                },
                headers=headers,
            )
            pages += 1
            self.credits_used += int(resp.headers.get("x-ratelimit-credits-used", "1") or 1)
            remaining = resp.headers.get("x-ratelimit-remaining")
            if remaining is not None and remaining.lstrip("-").isdigit():
                self.remaining = int(remaining)
            data = resp.json()
            page = data.get("group_by") or []
            total = int(data.get("meta", {}).get("count") or 0)
            for g in page:
                groups[_short(str(g["key"]))] = (g.get("key_display_name") or "", int(g["count"]))
            if self.remaining is not None and self.remaining < self.params.reserve_credits:
                reserve = self.params.reserve_credits
                raise CollectError(f"openalex: stopped with {self.remaining} credits left today (reserve {reserve})")
            # OpenAlex returns a next_cursor even after the last page, so a short page ends the paging
            cursor = data.get("meta", {}).get("next_cursor") if len(page) >= self.params.per_page else None
        return groups, total, pages

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        headers = self._headers()
        plan = self._plan(ctx)
        estimate = sum(EST_PAGES[level] for _, _, level in plan)
        if estimate > self.params.max_credits:
            raise CollectError(
                f"openalex: the plan needs about {estimate} credits; the card caps a run at {self.params.max_credits}"
            )
        left = self._budget(ctx, headers)
        if left - estimate < self.params.reserve_credits:
            raise CollectError(
                f"openalex: {left} credits left today; the run needs about {estimate} and keeps "
                f"{self.params.reserve_credits} in reserve"
            )
        log.info("openalex: %d queries, about %d credits of %d left today", len(plan), estimate, left)
        retrieved_at = utc_now().isoformat(timespec="seconds")
        records = []
        for i, (period, scope, level) in enumerate(plan, start=1):
            filt = self._filter(period, scope)
            groups, total, pages = self._groups(ctx, headers, filt, level)
            payload = {
                "level": level,
                "scope": scope,
                "period": period.label,
                "period_kind": period.kind,
                "filter": filt,
                "group_by": LEVELS[level],
                "total_works": total,
                "grouped_works": sum(c for _, c in groups.values()),
                "groups": [{"id": k, "name": n, "count": c} for k, (n, c) in sorted(groups.items())],
                "pages": pages,
            }
            records.append(
                RawRecord(
                    envelope=make_envelope(
                        provider="OpenAlex",
                        source_collection="openalex_works_counts",
                        provider_record_id=f"{level}|{scope}|{period.label}",
                        kind="observation",
                        family=self.card.family,
                        rings=self.card.rings,
                        domains=self.card.domains,
                        payload=payload,
                        request={"filter": filt, "group_by": LEVELS[level], "base_url": self.params.base_url},
                        retrieval_method="rest:openalex:group_by",
                        tool_identity=f"moria:{PARSER_VERSION}",
                        licence=self.card.licence,
                        parser_version=PARSER_VERSION,
                        event_at=period.first.isoformat(),
                        observable_at=retrieved_at,
                        retrieved_at=retrieved_at,
                    ),
                    payload=payload,
                )
            )
            if i % 25 == 0 or i == len(plan):
                log.info(
                    "openalex [%d/%d] %s %s %s: %d groups; %d credits used",
                    i,
                    len(plan),
                    period.label,
                    scope,
                    level,
                    len(groups),
                    self.credits_used,
                )
        log.info(
            "openalex: %d credits used; %s left today",
            self.credits_used,
            "unknown" if self.remaining is None else self.remaining,
        )
        return records

    @property
    def counts(self) -> dict[str, int]:
        """Extra manifest counts: the credits this run used of the day's free budget."""
        return {"openalex_credits_used": self.credits_used}
