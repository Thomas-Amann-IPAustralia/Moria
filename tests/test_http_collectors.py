"""HTTP politeness and every collector, against hand-built replicas of each source's format (placeholder text)."""

from __future__ import annotations

import json
from datetime import date
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from moria.collectors import Window, run_collection
from moria.collectors.base import CollectContext
from moria.collectors.feed import FeedCollector
from moria.collectors.gdelt import GdeltParams, QueryGroup, build_groups
from moria.collectors.legislation import LegislationCollector
from moria.collectors.sitemap import SitemapCollector, extract_page
from moria.http import FetchError
from moria.records import decode_bundle

from .conftest import card, make_client

DAY = date(2026, 10, 9)


def test_retry_after_then_success_and_safe_error_messages(http_cfg):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, text="ok")

    c = make_client(http_cfg, handler)
    assert c.get("https://example.org/x", params={"api_key": "SECRET"}).text == "ok"
    assert calls["n"] == 2

    c2 = make_client(http_cfg, lambda r: httpx.Response(503))
    with pytest.raises(FetchError) as e:
        c2.get("https://example.org/path", params={"api_key": "SECRET"})
    assert "SECRET" not in str(e.value) and "example.org/path" in str(e.value)


def test_robots_txt_is_honoured(http_cfg):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        return httpx.Response(200, text="page")

    c = make_client(http_cfg, handler)
    assert c.get("https://site.test/public", check_robots=True).text == "page"
    with pytest.raises(FetchError):
        c.get("https://site.test/private/x", check_robots=True)


def test_query_groups_are_balanced_and_quoted():
    g = QueryGroup("x:0", ("two words", "single", "knock-off"))
    assert g.expression == '("two words" OR single OR "knock-off")'
    groups = build_groups(GdeltParams(phrases_per_query=6))
    assert all(1 <= len(gr.phrases) <= 6 for gr in groups)
    assert not any(p.lower() == "ip" for gr in groups for p in gr.phrases)


def test_gdelt_collects_articles_and_volumes(http_cfg, store):
    def handler(request):
        q = parse_qs(urlsplit(str(request.url)).query)
        if q["mode"] == ["artlist"]:
            return httpx.Response(
                200,
                json={
                    "articles": [
                        {
                            "url": "https://news.test/a",
                            "title": "Placeholder title",
                            "seendate": "20261009T010203Z",
                            "domain": "news.test",
                            "language": "English",
                            "sourcecountry": "Australia",
                        }
                    ]
                },
            )
        return httpx.Response(
            200, json={"timeline": [{"series": "Article Count", "data": [{"date": "20261009T000000Z", "value": 7}]}]}
        )

    c = card("gdelt", {"phrases_per_query": 6, "territory_rings": ["core"], "include_themes": False})
    r = run_collection(c, store, make_client(http_cfg, handler), Window.for_day(DAY), limit=2)
    assert r.status == "passed"
    recs = decode_bundle(store.get(r.bundle_key))
    kinds = sorted(x.envelope.kind for x in recs)
    assert kinds.count("document") == 2 and kinds.count("observation") == 4  # 2 groups x (1 article, world + au)
    doc = next(x for x in recs if x.envelope.kind == "document")
    assert doc.envelope.provider == "news.test" and doc.envelope.observable_at.startswith("2026-10-09T01:02:03")
    manifest = json.loads(store.get(r.manifest_key))
    assert manifest["status"] == "passed" and manifest["outputs"][0]["key"] == r.bundle_key


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>Inside window</title><link>https://feed.test/1</link><guid>g1</guid>
<pubDate>Fri, 09 Oct 2026 10:00:00 GMT</pubDate><description>placeholder</description></item>
<item><title>Too old</title><link>https://feed.test/2</link><guid>g2</guid>
<pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate></item></channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>T</title>
<entry><id>tag:a</id><title>Atom item</title><link rel="alternate" href="https://feed.test/a"/>
<updated>2026-10-08T12:00:00+01:00</updated><summary>placeholder</summary></entry></feed>"""


@pytest.mark.parametrize(("body", "expected_ids"), [(RSS, ["g1"]), (ATOM, ["tag:a"])])
def test_feeds_keep_items_in_the_lookback_window(http_cfg, body, expected_ids):
    c = card("feed", {"url": "https://feed.test/rss", "lookback_days": 3})
    ctx = CollectContext(
        card=c, client=make_client(http_cfg, lambda r: httpx.Response(200, content=body)), window=Window.for_day(DAY)
    )
    recs = FeedCollector(c).collect(ctx)
    assert [x.envelope.provider_record_id for x in recs] == expected_ids


SITEMAP = b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://site.test/news/new</loc><lastmod>2026-10-09</lastmod></url>
<url><loc>https://site.test/old</loc><lastmod>2025-01-01</lastmod></url></urlset>"""

PAGE = """<html><head><title>Placeholder page</title><meta name="description" content="A summary"></head>
<body><nav>menu</nav><main><h1>Heading</h1><p>Body text here.</p><script>var x=1;</script></main>
<footer>footer</footer></body></html>"""


def test_sitemap_fetches_changed_pages_as_text(http_cfg):
    def handler(request):
        if request.url.path == "/sitemap.xml":
            return httpx.Response(200, content=SITEMAP)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=PAGE)

    c = card("sitemap", {"sitemap_url": "https://site.test/sitemap.xml", "lookback_days": 2})
    ctx = CollectContext(card=c, client=make_client(http_cfg, handler), window=Window.for_day(DAY))
    recs = SitemapCollector(c).collect(ctx)
    assert [x.payload["url"] for x in recs] == ["https://site.test/news/new"]
    p = recs[0].payload
    assert p["title"] == "Placeholder page" and p["description"] == "A summary"
    assert "Body text here." in p["text"] and "menu" not in p["text"] and "var x" not in p["text"]
    assert len(p["html_sha256"]) == 64 and "html" not in p


def test_extract_page_handles_entities():
    assert extract_page("<p>A &amp; B</p>")["text"] == "A & B"


def test_legislation_pages_through_versions_and_titles(http_cfg):
    seen = []

    def handler(request):
        q = parse_qs(urlsplit(str(request.url)).query)
        seen.append((request.url.path, q["$skip"][0]))
        if request.url.path.endswith("/Versions"):
            skip = int(q["$skip"][0])
            rows = [
                {
                    "titleId": f"F{skip + i}",
                    "compilationNumber": "1",
                    "registeredAt": "2026-10-09T01:00:00",
                    "start": "2026-10-01T00:00:00",
                    "name": "Placeholder instrument",
                }
                for i in range(2 if skip == 0 else 1)
            ]
            return httpx.Response(200, json={"value": rows})
        return httpx.Response(
            200, json={"value": [{"id": "C1", "name": "Placeholder Act", "asMadeRegisteredAt": "2026-10-09T02:00:00"}]}
        )

    c = card("legislation", {"base_url": "https://leg.test/v1", "page_size": 2}, family="legal")
    ctx = CollectContext(card=c, client=make_client(http_cfg, handler), window=Window.for_day(DAY))
    recs = LegislationCollector(c).collect(ctx)
    assert len(recs) == 4 and ("/v1/Versions", "2") in seen
    assert {x.envelope.source_collection for x in recs} == {"frl_versions", "frl_titles"}


def test_failed_collection_still_writes_a_manifest(http_cfg, store):
    c = card("feed", {"url": "https://feed.test/rss"})
    r = run_collection(c, store, make_client(http_cfg, lambda r: httpx.Response(500)), Window.for_day(DAY))
    assert r.status == "failed" and "HTTP 500" in r.error
    assert json.loads(store.get(r.manifest_key))["status"] == "failed"
