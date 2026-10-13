"""RSS 2.0 and Atom feeds: press releases and news from WIPO, peer IP offices and others.

Items dated within the lookback before the window and up to its end are kept; a backfill keeps every item up to the
window's end. Re-collected items get the same
evidence id when unchanged, so normalisation removes the overlap.

A source whose terms don't clearly allow storing its text sets `keep_summary: false`: its items keep the title, link
and dates only, like news (CLAUDE.md: a source whose licence is unclear is not stored as text).

An item's id is its guid, else its link. A feed whose items have no guid and share links (APH's committee feeds list
several hearings or reports under one inquiry's page) sets `item_id: link_and_content`: the id is the link plus a
short hash of the title, date and summary. An item without a date is kept, with the run's time as its
`observable_at` (when Moria first could see it); a feed that never dates its items sets `undated_items: expected`
so that this is not a warning every day.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Literal

from defusedxml import ElementTree

from ..config import Strict
from ..records import RawRecord, make_envelope, sha256_hex, utc_now
from .base import CollectContext, CollectError

PARSER_VERSION = "feed-v2"
ATOM = "{http://www.w3.org/2005/Atom}"


class FeedParams(Strict):
    url: str
    lookback_days: int = 3
    keep_summary: bool = True
    item_id: Literal["guid_or_link", "link_and_content"] = "guid_or_link"
    undated_items: Literal["warn", "expected"] = "warn"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        moment = parsedate_to_datetime(value)  # RSS: RFC 822
    except (TypeError, ValueError):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))  # Atom: RFC 3339
        except ValueError:
            return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _text(el, tag: str) -> str | None:
    found = el.find(tag)
    return found.text.strip() if found is not None and found.text else None


def parse_feed(xml: bytes) -> list[dict]:
    root = ElementTree.fromstring(xml)
    items: list[dict] = []
    if root.tag == f"{ATOM}feed":
        for e in root.findall(f"{ATOM}entry"):
            link = next(
                (lk.get("href") for lk in e.findall(f"{ATOM}link") if lk.get("rel") in (None, "alternate")), None
            )
            items.append(
                {
                    "id": _text(e, f"{ATOM}id"),
                    "title": _text(e, f"{ATOM}title"),
                    "link": link,
                    "published": _text(e, f"{ATOM}published"),
                    "updated": _text(e, f"{ATOM}updated"),
                    "summary": _text(e, f"{ATOM}summary") or _text(e, f"{ATOM}content"),
                }
            )
    else:
        channel = root.find("channel")
        if channel is None:
            raise CollectError("feed: neither an RSS channel nor an Atom feed")
        for it in channel.findall("item"):
            items.append(
                {
                    "id": _text(it, "guid") or _text(it, "link"),
                    "title": _text(it, "title"),
                    "link": _text(it, "link"),
                    "published": _text(it, "pubDate"),
                    "updated": None,
                    "summary": _text(it, "description"),
                }
            )
    return items


class FeedCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = FeedParams.model_validate(card.params)

    def _record_id(self, item: dict) -> str | None:
        if self.params.item_id == "link_and_content" and item.get("link"):
            content = "|".join(item.get(k) or "" for k in ("title", "published", "updated", "summary"))
            return f"{item['link']}#{sha256_hex(content)[:16]}"
        return item.get("id") or item.get("link")

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        resp = ctx.client.get(self.params.url)
        retrieved_at = utc_now().isoformat(timespec="seconds")
        items = parse_feed(resp.content)
        earliest = ctx.window.start - timedelta(days=self.params.lookback_days)
        records: list[RawRecord] = []
        undated = 0
        for item in items:
            dated = _parse_date(item["published"]) or _parse_date(item["updated"])
            if dated is None:
                undated += 1
            elif not (earliest <= dated < ctx.window.end) and not (ctx.backfill and dated < ctx.window.end):
                continue
            record_id = self._record_id(item)
            if not record_id:
                ctx.warnings.append("feed item without an id or link, skipped")
                continue
            if not self.params.keep_summary:
                item = {k: v for k, v in item.items() if k != "summary"}
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
                        payload=item,
                        request={"url": self.params.url},
                        retrieval_method="feed",
                        tool_identity=f"moria:{PARSER_VERSION}",
                        licence=self.card.licence,
                        parser_version=PARSER_VERSION,
                        event_at=None,
                        # an undated item is observable from the run that first sees it
                        observable_at=dated.astimezone(UTC).isoformat() if dated else retrieved_at,
                        provider_updated_at=item.get("updated"),
                        retrieved_at=retrieved_at,
                    ),
                    payload=item,
                )
            )
            if ctx.limit and len(records) >= ctx.limit:
                break
        if undated and self.params.undated_items == "warn":
            ctx.warnings.append(f"feed: {undated} items without a usable date; observable_at is the retrieval time")
        self.counts = {"items_in_feed": len(items), "items_undated": undated}
        return records
