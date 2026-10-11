"""GDELT DOC 2.0: article titles and metadata, plus daily volumes, for the territory terms and the broad themes.

Only titles, URLs and metadata are stored: article text belongs to its publishers (design §12). Every query runs for
one UTC day. Volumes are taken worldwide (English-language sources) and for Australian sources, so the gap between
them is visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from ..config import Strict, load_territories, load_themes
from ..http import FetchError
from ..records import RawRecord, make_envelope
from .base import CollectContext, CollectError

API = "https://api.gdeltproject.org/api/v2/doc/doc"
PARSER_VERSION = "gdelt-v1"


class GdeltParams(Strict):
    phrases_per_query: int = 6
    max_records: int = 250
    territory_rings: list[Literal["core", "adjacent", "wider_world"]] = Field(
        default_factory=lambda: ["core", "adjacent", "wider_world"]
    )
    include_themes: bool = True
    volume_scopes: list[Literal["world", "au"]] = Field(default_factory=lambda: ["world", "au"])
    articles: bool = True


@dataclass(frozen=True)
class QueryGroup:
    group_id: str  # e.g. "T1:core:0" or "theme:climate_energy:1"
    phrases: tuple[str, ...]

    @property
    def expression(self) -> str:
        terms = [f'"{p}"' if (" " in p or "-" in p) else p for p in self.phrases]
        return terms[0] if len(terms) == 1 else "(" + " OR ".join(terms) + ")"


def build_groups(params: GdeltParams) -> list[QueryGroup]:
    groups: list[QueryGroup] = []

    def chunk(prefix: str, phrases: list[str]) -> None:
        # Balanced groups of at most phrases_per_query: 14 phrases with a maximum of 6 become 5, 5 and 4.
        if not phrases:
            return
        n_groups = -(-len(phrases) // params.phrases_per_query)
        size, extra = divmod(len(phrases), n_groups)
        start = 0
        for i in range(n_groups):
            end = start + size + (1 if i < extra else 0)
            groups.append(QueryGroup(f"{prefix}:{i}", tuple(phrases[start:end])))
            start = end

    for t in load_territories().territories:
        for ring in params.territory_rings:
            chunk(f"{t.id}:{ring}", getattr(t.terms, ring))
    if params.include_themes:
        for name, phrases in sorted(load_themes().themes.items()):
            chunk(f"theme:{name}", phrases)
    return groups


def _gdelt_time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%d%H%M%S")


def _seendate(value: str | None) -> str | None:
    # GDELT seendate looks like 20261009T123000Z
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).isoformat()
    except ValueError:
        return None


class GdeltCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = GdeltParams.model_validate(card.params)

    def _call(self, ctx: CollectContext, query: str, mode: str, extra: dict) -> dict:
        request = {
            "query": query,
            "mode": mode,
            "format": "json",
            "startdatetime": _gdelt_time(ctx.window.start),
            "enddatetime": _gdelt_time(ctx.window.end),
            **extra,
        }
        resp = ctx.client.get(API, params=request)
        try:
            return {"request": request, "data": resp.json()}
        except ValueError as e:
            # GDELT answers some invalid queries with a plain-text message
            raise CollectError(f"gdelt: non-JSON answer for {mode}: {resp.text.strip()[:120]!r}") from e

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        records: list[RawRecord] = []
        groups = build_groups(self.params)
        if ctx.limit:
            groups = groups[: ctx.limit]
        failures = 0
        for g in groups:
            try:
                if self.params.articles:
                    out = self._call(
                        ctx,
                        f"{g.expression} sourcelang:english",
                        "artlist",
                        {"maxrecords": str(self.params.max_records), "sort": "datedesc"},
                    )
                    for art in out["data"].get("articles", []):
                        url = art.get("url")
                        if not url:
                            continue
                        payload = {"query_group": g.group_id, "article": art}
                        records.append(
                            RawRecord(
                                envelope=make_envelope(
                                    provider=art.get("domain") or "unknown",
                                    source_collection="gdelt_doc_v2",
                                    provider_record_id=url,
                                    kind="document",
                                    family=self.card.family,
                                    rings=self.card.rings,
                                    domains=self.card.domains,
                                    payload=payload,
                                    request=out["request"],
                                    retrieval_method="rest:gdelt_doc_v2:artlist",
                                    tool_identity=f"moria:{PARSER_VERSION}",
                                    licence=self.card.licence,
                                    parser_version=PARSER_VERSION,
                                    event_at=None,
                                    observable_at=_seendate(art.get("seendate")),
                                ),
                                payload=payload,
                            )
                        )
                for scope in self.params.volume_scopes:
                    suffix = "sourcelang:english" if scope == "world" else "sourcecountry:australia"
                    out = self._call(ctx, f"{g.expression} {suffix}", "timelinevolraw", {})
                    payload = {"query_group": g.group_id, "scope": scope, "timeline": out["data"].get("timeline", [])}
                    records.append(
                        RawRecord(
                            envelope=make_envelope(
                                provider="The GDELT Project",
                                source_collection="gdelt_doc_v2_volume",
                                provider_record_id=f"{g.group_id}|{scope}|{ctx.window.day.isoformat()}",
                                kind="observation",
                                family=self.card.family,
                                rings=self.card.rings,
                                domains=self.card.domains,
                                payload=payload,
                                request=out["request"],
                                retrieval_method="rest:gdelt_doc_v2:timelinevolraw",
                                tool_identity=f"moria:{PARSER_VERSION}",
                                licence=self.card.licence,
                                parser_version=PARSER_VERSION,
                                event_at=ctx.window.start.isoformat(),
                                observable_at=ctx.window.end.isoformat(),
                            ),
                            payload=payload,
                        )
                    )
            except (FetchError, CollectError) as e:
                failures += 1
                ctx.warnings.append(f"gdelt group {g.group_id} failed: {e}")
        if groups and failures == len(groups):
            raise CollectError(f"gdelt: every query group failed ({failures}); first: {ctx.warnings[0]}")
        return records
