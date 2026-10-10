"""Web pages found through a site's sitemap: pages whose lastmod falls in the lookback and window are fetched.

robots.txt is honoured. Pages are stored as extracted text plus metadata and the SHA-256 and size of the original
HTML, not the full HTML: a single government page can be over 500 KB, and the free storage is 10 GB (D-007).
"""

from __future__ import annotations

from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import urlsplit

from defusedxml import ElementTree
from pydantic import Field

from ..config import Strict
from ..http import FetchError
from ..records import RawRecord, make_envelope, sha256_hex
from .base import CollectContext, CollectError

PARSER_VERSION = "sitemap-v1"
SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
MAX_TEXT_CHARS = 50_000


class SitemapParams(Strict):
    sitemap_url: str
    lookback_days: int = 2
    include_prefixes: list[str] = Field(default_factory=list)
    exclude_substrings: list[str] = Field(default_factory=list)
    max_pages: int = 50


class _TextExtractor(HTMLParser):
    SKIP = frozenset({"script", "style", "noscript", "nav", "header", "footer", "svg", "form", "template"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.description: str | None = None
        self._skip_depth = 0
        self._in_title = False
        self._chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            a = dict(attrs)
            if (a.get("name") or "").lower() == "description" and a.get("content"):
                self.description = a["content"].strip()

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title = ((self.title or "") + data).strip()
        elif not self._skip_depth and data.strip():
            self._chunks.append(" ".join(data.split()))

    @property
    def text(self) -> str:
        return "\n".join(self._chunks)[:MAX_TEXT_CHARS]


def extract_page(html: str) -> dict:
    p = _TextExtractor()
    p.feed(html)
    p.close()
    return {"title": p.title, "description": p.description, "text": p.text}


def parse_sitemap(xml: bytes) -> tuple[list[dict], list[str]]:
    """Returns (urls with lastmod, nested sitemap URLs)."""
    root = ElementTree.fromstring(xml)
    if root.tag == f"{SM}sitemapindex":
        return [], [s.findtext(f"{SM}loc", "").strip() for s in root.findall(f"{SM}sitemap")]
    if root.tag != f"{SM}urlset":
        raise CollectError("sitemap: neither a urlset nor a sitemapindex")
    urls = []
    for u in root.findall(f"{SM}url"):
        loc = (u.findtext(f"{SM}loc") or "").strip()
        if loc:
            urls.append({"loc": loc, "lastmod": (u.findtext(f"{SM}lastmod") or "").strip() or None})
    return urls, []


def _lastmod_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class SitemapCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = SitemapParams.model_validate(card.params)

    def _selected(self, urls: list[dict], first: date, last_exclusive: date) -> list[dict]:
        chosen = []
        for u in urls:
            day = _lastmod_day(u["lastmod"])
            path = urlsplit(u["loc"]).path
            if day is None or not (first <= day < last_exclusive):
                continue
            if self.params.include_prefixes and not any(path.startswith(p) for p in self.params.include_prefixes):
                continue
            if any(s in u["loc"] for s in self.params.exclude_substrings):
                continue
            chosen.append(u)
        return sorted(chosen, key=lambda u: (u["lastmod"] or "", u["loc"]), reverse=True)

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        urls, nested = parse_sitemap(ctx.client.get(self.params.sitemap_url).content)
        for sub in nested[:20]:
            more, _ = parse_sitemap(ctx.client.get(sub).content)
            urls.extend(more)
        first = ctx.window.day - timedelta(days=self.params.lookback_days)
        chosen = self._selected(urls, first, ctx.window.day + timedelta(days=1))
        cap = min(self.params.max_pages, ctx.limit or self.params.max_pages)
        if len(chosen) > cap:
            ctx.warnings.append(f"sitemap: {len(chosen)} pages changed, capped at {cap}")
            chosen = chosen[:cap]
        records: list[RawRecord] = []
        for u in chosen:
            try:
                resp = ctx.client.get(u["loc"], check_robots=True)
            except FetchError as e:
                ctx.warnings.append(f"sitemap page skipped: {e}")
                continue
            html = resp.text
            payload = {
                "url": u["loc"],
                "lastmod": u["lastmod"],
                "html_sha256": sha256_hex(resp.content),
                "html_bytes": len(resp.content),
                **extract_page(html),
            }
            records.append(
                RawRecord(
                    envelope=make_envelope(
                        provider=self.card.name,
                        source_collection=self.card.id,
                        provider_record_id=u["loc"],
                        kind="document",
                        family=self.card.family,
                        rings=self.card.rings,
                        domains=self.card.domains,
                        payload=payload,
                        request={"url": u["loc"]},
                        retrieval_method="html:sitemap",
                        tool_identity=f"moria:{PARSER_VERSION}",
                        licence=self.card.licence,
                        parser_version=PARSER_VERSION,
                        event_at=None,
                        observable_at=u["lastmod"],
                        provider_updated_at=u["lastmod"],
                    ),
                    payload=payload,
                )
            )
        return records
