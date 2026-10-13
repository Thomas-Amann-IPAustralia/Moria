"""Dated lists on web pages that offer no feed: a news board (MOIP, formerly KIPO) or a register of notifications
(WIPO Lex's treaty notifications).

Each page in the card is fetched (robots.txt honoured) and read with the card's item pattern: a regular expression
whose named groups give each item's `title`, `date`, and `link` or `id` (with `link_template` to build the link from
the id), and optionally `number` and `summary`. Titles and summaries are stripped of tags and entities. Items dated
within the lookback before the window and up to its end are kept, as for feeds; a backfill keeps every item on the
pages. A page that answers but yields no item is a warning (its layout may have changed), and a run in which no page
yields any item fails.

A source whose terms don't clearly allow storing its text keeps titles, links and dates only (`keep_summary: false`,
the default).
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime, timedelta

from pydantic import field_validator

from ..config import Strict
from ..http import FetchError
from ..records import RawRecord, make_envelope, utc_now
from .base import CollectContext, CollectError

PARSER_VERSION = "listpage-v1"


class ListPage(Strict):
    id: str  # Moria's name for the page, e.g. "pct" or "news"
    url: str
    label: str = ""  # e.g. the treaty's name


class ListPageParams(Strict):
    pages: list[ListPage]
    item_pattern: str  # named groups: title, date, and link or id; optionally number and summary
    date_format: str  # strptime format of the date group, e.g. "%B %d, %Y"
    link_template: str | None = None  # e.g. "https://site/detail?seq={id}"
    lookback_days: int = 30
    keep_summary: bool = False

    @field_validator("item_pattern")
    @classmethod
    def _groups(cls, value: str) -> str:
        groups = set(re.compile(value).groupindex)
        if not {"title", "date"} <= groups or not groups & {"link", "id"}:
            raise ValueError("item_pattern needs the named groups title, date, and link or id")
        return value


def _clean(fragment: str | None) -> str | None:
    if fragment is None:
        return None
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())
    return text or None


def parse_items(page: str, params: ListPageParams, base_url: str) -> list[dict]:
    from urllib.parse import urljoin

    pattern = re.compile(params.item_pattern, re.S)
    items = []
    for m in pattern.finditer(page):
        g = m.groupdict()
        if g.get("link"):
            link = urljoin(base_url, html.unescape(g["link"]))
        elif params.link_template and g.get("id"):
            link = params.link_template.format(id=g["id"])
        else:
            link = None
        items.append(
            {
                "id": g.get("id"),
                "number": _clean(g.get("number")),
                "title": _clean(g.get("title")),
                "date_text": _clean(g.get("date")),
                "link": link,
                "summary": _clean(g.get("summary")),
            }
        )
    return items


class ListPageCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = ListPageParams.model_validate(card.params)
        ids = [p.id for p in self.params.pages]
        if len(set(ids)) != len(ids):
            raise CollectError("listpage: page ids must be unique")
        self.counts: dict[str, int] = {}

    def _date(self, text: str | None) -> datetime | None:
        if not text:
            return None
        try:
            return datetime.strptime(text, self.params.date_format).replace(tzinfo=UTC)
        except ValueError:
            return None

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        pages = self.params.pages[: ctx.limit] if ctx.limit else self.params.pages
        earliest = ctx.window.start - timedelta(days=self.params.lookback_days)
        records: list[RawRecord] = []
        found = failed = undated = 0
        for page in pages:
            try:
                resp = ctx.client.get(page.url, check_robots=True)
            except FetchError as e:
                failed += 1
                ctx.warnings.append(f"listpage: {page.id} not fetched: {e}")
                continue
            retrieved_at = utc_now().isoformat(timespec="seconds")
            items = parse_items(resp.text, self.params, str(resp.url))
            found += len(items)
            if not items:
                ctx.warnings.append(f"listpage: {page.id} answered but no item matched; its layout may have changed")
            for item in items:
                dated = self._date(item["date_text"])
                if dated is None:
                    undated += 1
                    continue
                if not (ctx.backfill or earliest <= dated) or dated >= ctx.window.end:
                    continue
                record_id = item["link"] or f"{page.url}#{item['id']}"
                payload = {"page": page.id, "page_label": page.label or None, **item, "date": dated.date().isoformat()}
                if not self.params.keep_summary:
                    payload.pop("summary")
                records.append(
                    RawRecord(
                        envelope=make_envelope(
                            provider=self.card.name,
                            source_collection=self.card.id,
                            provider_record_id=record_id,
                            kind="document",
                            family=self.card.family,
                            rings=self.card.rings,
                            domains=self.card.domains,
                            payload=payload,
                            request={"url": page.url},
                            retrieval_method="html:listpage",
                            tool_identity=f"moria:{PARSER_VERSION}",
                            licence=self.card.licence,
                            parser_version=PARSER_VERSION,
                            event_at=payload["date"],
                            observable_at=payload["date"],
                            retrieved_at=retrieved_at,
                        ),
                        payload=payload,
                    )
                )
        if undated:
            ctx.warnings.append(f"listpage: {undated} items with a date that does not parse; skipped")
        self.counts = {"pages": len(pages), "pages_failed": failed, "items_on_pages": found}
        if pages and (failed == len(pages) or found == 0):
            first = ctx.warnings[0] if ctx.warnings else "no items"
            raise CollectError(f"listpage: no page yielded any item ({failed} failed); first: {first}")
        return records
