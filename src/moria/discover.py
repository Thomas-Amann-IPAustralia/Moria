"""`moria discover`: what a source's addresses answer, from wherever the command runs (the sources backlog, step 2).

Some sites refuse the build session but may answer a GitHub runner, so a new source's addresses are checked from a
runner (`collect-source` with the source `discover`). For each URL: the HTTP status, content type, size and final
address, and whether robots.txt lets Moria's user agent fetch it; for a feed or a sitemap, its kind, item count and
date range; for an HTML page, the feed and sitemap links it offers and the links matching a pattern. Addresses, counts
and dates only, never a page's text, so the output may go in public logs.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

from defusedxml import ElementTree

from .http import FetchError, PoliteClient

FEEDISH = re.compile(r"rss|atom|feed|\.xml\b|sitemap", re.IGNORECASE)
MAX_LINKS = 40
ATOM = "{http://www.w3.org/2005/Atom}"
SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.alternate: list[tuple[str, str]] = []
        self.anchors: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        if tag == "link" and "alternate" in a.get("rel", "").lower() and a.get("href"):
            self.alternate.append((a.get("type", ""), a["href"]))
        elif tag == "a" and a.get("href"):
            self.anchors.append(a["href"])


def page_links(html: str) -> list[str]:
    """Every anchor's href on a page, as written (relative or absolute)."""
    p = _Links()
    p.feed(html)
    return p.anchors


def _dates(values: list[str]) -> str:
    parsed = []
    for v in values:
        try:
            parsed.append(parsedate_to_datetime(v).date().isoformat())
        except (TypeError, ValueError):
            if re.match(r"\d{4}-\d{2}-\d{2}", v):
                parsed.append(v[:10])
    if not parsed:
        return "no dates"
    return f"dates {min(parsed)} to {max(parsed)} ({len(parsed)} of {len(values)})"


def describe_xml(data: bytes) -> str | None:
    """The kind of an XML feed or sitemap, its item count and date range; None if it is neither."""
    try:
        root = ElementTree.fromstring(data)
    except Exception:
        return None
    if root.tag == "rss" and root.find("channel") is not None:
        items = root.find("channel").findall("item")
        return f"RSS, {len(items)} items, {_dates([i.findtext('pubDate') or '' for i in items])}"
    if root.tag == f"{ATOM}feed":
        entries = root.findall(f"{ATOM}entry")
        stamps = [e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated") or "" for e in entries]
        return f"Atom, {len(entries)} entries, {_dates(stamps)}"
    if root.tag == f"{SM}urlset":
        urls = root.findall(f"{SM}url")
        return f"sitemap urlset, {len(urls)} URLs, {_dates([u.findtext(f'{SM}lastmod') or '' for u in urls])}"
    if root.tag == f"{SM}sitemapindex":
        return f"sitemap index, {len(root.findall(f'{SM}sitemap'))} sitemaps"
    if root.tag.endswith("RDF"):
        return "RSS 1.0 (RDF)"
    return f"XML, root <{root.tag[:60]}>"


ROBOTS_FIELD = re.compile(r"^\s*(user-agent|allow|disallow|crawl-delay)\s*:\s*(\S{0,200})", re.IGNORECASE)


def robots_rules(text: str, limit: int = 60) -> list[str]:
    """A robots.txt's user-agent, allow, disallow and crawl-delay lines, normalised (directives for crawlers, which
    is why they may be printed); comments and anything else are left out."""
    rules = []
    for line in text.splitlines():
        m = ROBOTS_FIELD.match(line.split("#", 1)[0])
        if m:
            rules.append(f"{m.group(1).lower()}: {m.group(2)}")
    return rules[:limit]


def html_links(html: str, base: str, match: re.Pattern | None) -> tuple[list[str], list[str]]:
    """(feed links the page declares, other links that look like feeds or sitemaps or match the pattern)"""
    p = _Links()
    p.feed(html)
    declared = [f"{t or '?'} {urljoin(base, h)}" for t, h in p.alternate if "rss" in t or "atom" in t or "xml" in t]
    seen, other = set(), []
    for href in p.anchors:
        full = urldefrag(urljoin(base, href))[0]
        if full in seen or full == base or not full.startswith(("http://", "https://")):
            continue
        if FEEDISH.search(href) or (match and match.search(full)):
            seen.add(full)
            other.append(full)
    return declared, other[:MAX_LINKS]


def discover(client: PoliteClient, urls: list[str], match: str | None = None) -> Iterator[str]:
    """Lines to print, one URL at a time."""
    pattern = re.compile(match, re.IGNORECASE) if match else None
    for url in urls:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            yield f"{url}: not an http(s) address"
            continue
        is_robots = parts.path == "/robots.txt"
        if not is_robots and not client.allowed_by_robots(url):
            yield f"{url}: disallowed for Moria by robots.txt; not fetched"
            continue
        try:
            resp = client.get(url, retries=0, ok_statuses=tuple(range(100, 600)))
        except FetchError as e:
            yield f"{url}: {e}"
            continue
        ctype = resp.headers.get("content-type", "?").split(";")[0]
        moved = f" -> {resp.url}" if str(resp.url) != url else ""
        yield f"{url}: HTTP {resp.status_code}, {ctype}, {len(resp.content):,} bytes{moved}"
        if resp.status_code != 200:
            continue
        if is_robots:
            sitemaps = [
                ln.split(":", 1)[1].strip() for ln in resp.text.splitlines() if ln.lower().startswith("sitemap:")
            ]
            yield f"  robots.txt: {len(resp.text.splitlines())} lines; sitemaps: {', '.join(sitemaps) or 'none'}"
            for rule in robots_rules(resp.text):
                yield f"  rule: {rule}"
            continue
        xml = describe_xml(resp.content) if ("xml" in ctype or resp.content.lstrip()[:5] == b"<?xml") else None
        if xml:
            yield f"  {xml}"
        elif "html" in ctype:
            declared, other = html_links(resp.text, str(resp.url), pattern)
            yield f"  declared feeds: {', '.join(declared) or 'none'}"
            for link in other:
                yield f"  link: {link}"
