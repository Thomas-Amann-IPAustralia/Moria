"""Dated lists from a site's own JSON endpoint, when the site offers no feed: the reports companies publish under the
OECD's Hiroshima AI Process reporting framework (OECD.AI's transparency reports, read from `api.oecd.ai`).

The endpoint is read page by page (`page_param` = 1, 2, … until the page count the response gives, or an empty page,
up to `max_pages`; robots.txt honoured). Each item keeps its id, title, date and the card's chosen `fields`, plus a
link built from `link_template`: metadata only, like a list page without summaries. Items dated within the lookback
before the window and up to its end are kept; a backfill keeps every item. An item without a usable date is skipped
with a warning; a run that finds no item at all fails.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..config import Strict
from ..records import RawRecord, make_envelope, utc_now
from .base import CollectContext, CollectError

PARSER_VERSION = "json-list-v1"


class JsonListParams(Strict):
    url: str  # the list endpoint
    page_param: str | None = "page"  # None: one request, no pages
    items_key: str | None = "data"  # where the items are in the response; None: the response is the list
    last_page_key: str | None = "lastPage"
    max_pages: int = 20
    id_field: str = "id"
    date_field: str  # an ISO 8601 date or time
    title_field: str
    link_template: str  # e.g. "https://oecd.ai/en/transparency/reports/{id}"
    fields: tuple[str, ...] = ()  # further fields kept as they are (names, codes, labels; never long text)
    lookback_days: int = 30


def _date(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


class JsonListCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = JsonListParams.model_validate(card.params)
        self.counts: dict[str, int] = {}

    def _pages(self, ctx: CollectContext) -> list[dict]:
        p = self.params
        items: list[dict] = []
        pages = 0
        while True:
            pages += 1
            query = {p.page_param: str(pages)} if p.page_param else None
            body = ctx.client.get(p.url, params=query, check_robots=True).json()
            batch = body.get(p.items_key) if p.items_key else body
            if not isinstance(batch, list):
                raise CollectError(f"json_list: no list under {p.items_key!r} on page {pages}")
            items += [i for i in batch if isinstance(i, dict)]
            last = body.get(p.last_page_key) if p.last_page_key and isinstance(body, dict) else None
            if not p.page_param or not batch or (isinstance(last, int) and pages >= last):
                break
            if pages >= p.max_pages:
                ctx.warnings.append(f"json_list: stopped at the card's cap of {p.max_pages} pages")
                break
        self.counts = {"pages": pages, "items_listed": len(items)}
        return items

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        p = self.params
        items = self._pages(ctx)
        retrieved_at = utc_now().isoformat(timespec="seconds")
        if not items:
            raise CollectError("json_list: the endpoint listed no items")
        earliest = ctx.window.start - timedelta(days=p.lookback_days)
        records: list[RawRecord] = []
        undated = 0
        for item in items:
            dated = _date(item.get(p.date_field))
            item_id = item.get(p.id_field)
            if dated is None or item_id is None:
                undated += 1
                continue
            if not (ctx.backfill or earliest <= dated) or dated >= ctx.window.end:
                continue
            link = p.link_template.format(id=item_id)
            payload = {
                "id": str(item_id),
                "title": item.get(p.title_field),
                "date": dated.astimezone(UTC).isoformat(),
                "link": link,
                **{f: item.get(f) for f in p.fields},
            }
            records.append(
                RawRecord(
                    envelope=make_envelope(
                        provider=self.card.name,
                        source_collection=self.card.id,
                        provider_record_id=link,
                        kind="document",
                        family=self.card.family,
                        rings=self.card.rings,
                        domains=self.card.domains,
                        payload=payload,
                        request={"url": p.url},
                        retrieval_method="rest:json-list",
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
            if ctx.limit and len(records) >= ctx.limit:
                break
        if undated:
            ctx.warnings.append(f"json_list: {undated} items without an id or a usable date; skipped")
        return records
