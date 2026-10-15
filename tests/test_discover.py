"""`moria discover`: addresses, counts and dates only, from hand-built pages (placeholder text)."""

from __future__ import annotations

import httpx

from moria.discover import describe_xml, discover

from .conftest import make_client

PAGE = b"""<html><head><link rel="alternate" type="application/rss+xml" href="/news/rss.xml"></head>
<body><p>Placeholder text that must never be printed.</p>
<a href="/news/item-1">First</a><a href="/sitemap.xml">Sitemap</a><a href="#top">Top</a>
<a href="https://other.test/feed">Elsewhere</a></body></html>"""
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>Placeholder</title><pubDate>Fri, 09 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>Placeholder</title><pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>"""


def handler(request):
    path = request.url.path
    if path == "/robots.txt":
        return httpx.Response(
            200, text="# a comment\nUser-agent: *\nDisallow: /private/ # why\nSitemap: https://site.test/sitemap.xml\n"
        )
    if path == "/news/":
        return httpx.Response(200, content=PAGE, headers={"content-type": "text/html; charset=utf-8"})
    if path == "/news/rss.xml":
        return httpx.Response(200, content=RSS, headers={"content-type": "application/rss+xml"})
    return httpx.Response(403, text="blocked")


def test_discover_reports_addresses_and_counts_never_text(http_cfg):
    client = make_client(http_cfg, handler)
    urls = [
        "https://site.test/news/",
        "https://site.test/news/rss.xml",
        "https://site.test/robots.txt",
        "https://site.test/private/x",
        "https://site.test/blocked",
    ]
    lines = list(discover(client, urls, match=r"/news/item"))
    out = "\n".join(lines)
    assert "Placeholder" not in out
    assert "declared feeds: application/rss+xml https://site.test/news/rss.xml" in out
    assert "  link: https://site.test/news/item-1" in out and "  link: https://site.test/sitemap.xml" in out
    assert "#top" not in out and "other.test/feed" in out
    assert "RSS, 2 items, dates 2026-10-05 to 2026-10-09 (2 of 2)" in out
    assert "sitemaps: https://site.test/sitemap.xml" in out
    assert "  rule: user-agent: *\n  rule: disallow: /private/\n" in out and "comment" not in out
    assert "https://site.test/private/x: disallowed for Moria by robots.txt; not fetched" in out
    assert "https://site.test/blocked: HTTP 403, text/plain" in out


def test_describe_xml_knows_sitemaps_and_atom():
    urlset = b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>https://s.test/a</loc><lastmod>2026-10-01</lastmod></url><url><loc>https://s.test/b</loc></url></urlset>"""
    assert describe_xml(urlset) == "sitemap urlset, 2 URLs, dates 2026-10-01 to 2026-10-01 (1 of 2)"
    atom = (
        b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><updated>2026-10-08T12:00:00Z</updated></entry></feed>"""
    )
    assert describe_xml(atom) == "Atom, 1 entries, dates 2026-10-08 to 2026-10-08 (1 of 1)"
    assert describe_xml(b"not xml") is None
