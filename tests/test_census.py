"""Census reports: aggregates only, never a title or a URL."""

from __future__ import annotations

from datetime import date

import httpx

from moria.census import census_markdown
from moria.collectors import Window, run_collection

from .conftest import card, make_client
from .test_abs import CSV, Q1, abs_card
from .test_http_collectors import RSS


def test_census_profiles_a_feed_without_printing_its_titles(http_cfg, store):
    c = card("feed", {"url": "https://feed.test/rss", "lookback_days": 3})
    run_collection(
        c, store, make_client(http_cfg, lambda r: httpx.Response(200, content=RSS)), Window.for_day(date(2026, 10, 9))
    )
    report = census_markdown(store, c)
    assert "**Records:** 1" in report and "| title | 100% |" in report
    assert "Inside window" not in report and "feed.test/1" not in report


def test_census_summarises_abs_queries(http_cfg, store):
    c = abs_card([Q1])
    run_collection(
        c, store, make_client(http_cfg, lambda r: httpx.Response(200, text=CSV)), Window.for_day(date(2026, 10, 11))
    )
    report = census_markdown(store, c)
    assert "| first | 2 | 3 | 2025-Q4 | 2026-Q1 |" in report and "Observations with no value: 1" in report


def test_census_of_a_source_never_collected(store):
    assert "No collection in the store yet." in census_markdown(store, card("feed", {"url": "https://x.test/rss"}))
