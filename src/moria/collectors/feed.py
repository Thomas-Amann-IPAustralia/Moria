"""RSS 2.0 and Atom feeds: press releases and news from WIPO, peer IP offices and others.

Items dated within the lookback before the window and up to its end are kept. Re-collected items get the same
evidence id when unchanged, so normalisation removes the overlap.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree

from ..config import Strict
from ..records import RawRecord, make_envelope
from .base import CollectContext, CollectError

PARSER_VERSION = "feed-v1"
ATOM = "{http://www.w3.org/2005/Atom}"


class FeedParams(Strict):
    url: str
    lookback_days: int = 3


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

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        resp = ctx.client.get(self.params.url)
        items = parse_feed(resp.content)
        earliest = ctx.window.start - timedelta(days=self.params.lookback_days)
        records: list[RawRecord] = []
        for item in items:
            dated = _parse_date(item["published"]) or _parse_date(item["updated"])
            if dated is None:
                ctx.warnings.append(f"feed item without a usable date: {item.get('id')}")
            elif not (earliest <= dated < ctx.window.end):
                continue
            record_id = item.get("id") or item.get("link")
            if not record_id:
                ctx.warnings.append("feed item without an id or link, skipped")
                continue
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
                        observable_at=dated.astimezone(UTC).isoformat() if dated else None,
                        provider_updated_at=item.get("updated"),
                    ),
                    payload=item,
                )
            )
            if ctx.limit and len(records) >= ctx.limit:
                break
        return records
