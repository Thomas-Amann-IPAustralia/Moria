"""The OpenAlex counts collector, against a hand-built replica of the API's group_by and rate-limit answers."""

from __future__ import annotations

import json
from datetime import date
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from moria.collectors import Window, run_collection
from moria.collectors.openalex import periods
from moria.records import decode_bundle

from .conftest import card, make_client

DAY = date(2026, 10, 11)
TOPICS = [f"T{10000 + i}" for i in range(5)]  # five placeholder topics: three pages at per_page=2


def oa_card(**params):
    base = {
        "base_url": "https://oa.test",
        "from_year": 2025,
        "months_back": 2,
        "per_page": 2,
        "scopes": ["world", "au"],
    }
    return card("openalex_counts", {**base, **params}, family="research", cadence="weekly")


def make_handler(seen: list, remaining: int = 9000, prepaid: float = 0, refuse_after: int | None = None):
    state = {"calls": 0}

    def handler(request):
        seen.append(request)
        if request.url.path == "/rate-limit":
            limits = {"credits_remaining": remaining, "prepaid_remaining_usd": prepaid}
            return httpx.Response(200, json={"rate_limit": limits})
        state["calls"] += 1
        q = {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}
        keys = TOPICS if q["group_by"] == "primary_topic.id" else ["domains/1", "domains/2"]
        start = 0 if q["cursor"] == "*" else keys.index(q["cursor"]) + 1
        page = keys[start : start + int(q["per_page"])]
        au = "authorships.countries:AU" in q["filter"]
        groups = [
            {"key": f"https://openalex.org/{k}", "key_display_name": f"Placeholder {k}", "count": 3 if au else 30}
            for k in page
        ]
        left = remaining - state["calls"] if refuse_after is None or state["calls"] <= refuse_after else 10
        meta = {"count": len(keys) * (3 if au else 30) + 7, "next_cursor": page[-1] if page else None}
        return httpx.Response(
            200,
            json={"meta": meta, "group_by": groups},
            headers={"x-ratelimit-credits-used": "1", "x-ratelimit-remaining": str(left)},
        )

    return handler


def test_periods_cover_years_then_recent_months():
    ps = periods(date(2026, 2, 11), 2025, 3)
    assert [p.label for p in ps] == ["2025", "2026", "2025-12", "2026-01", "2026-02"]
    assert ps[-1].filter == "from_publication_date:2026-02-01,to_publication_date:2026-02-28"
    assert ps[0].filter == "publication_year:2025"


def test_counts_page_through_every_group_with_the_key_in_a_header(http_cfg, store, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "PLACEHOLDER-KEY")
    seen: list = []
    c = oa_card(levels=["domain", "topic"])
    r = run_collection(c, store, make_client(http_cfg, make_handler(seen)), Window.for_day(DAY))
    assert r.status == "passed", r.error
    recs = decode_bundle(store.get(r.bundle_key))
    # periods: 2025, 2026, 2026-09, 2026-10; two scopes; two levels
    assert len(recs) == 4 * 2 * 2
    by_id = {x.envelope.provider_record_id: x.payload for x in recs}
    topic = by_id["topic|au|2026-09"]
    assert [g["id"] for g in topic["groups"]] == TOPICS and topic["pages"] == 3
    assert topic["filter"] == "from_publication_date:2026-09-01,to_publication_date:2026-09-30,authorships.countries:AU"
    assert topic["total_works"] == 22 and topic["grouped_works"] == 15
    assert by_id["domain|world|2025"]["groups"][0] == {"id": "domains/1", "name": "Placeholder domains/1", "count": 30}
    assert all(x.envelope.kind == "observation" for x in recs)
    # The key travels in a header, never in a URL
    assert all("PLACEHOLDER-KEY" not in str(req.url) for req in seen)
    assert all(req.headers["Authorization"] == "Bearer PLACEHOLDER-KEY" for req in seen)
    manifest = json.loads(store.get(r.manifest_key))
    # Two domains fill a page of two, so the domain level takes an extra, empty page; the five topics take three
    assert manifest["counts"]["openalex_credits_used"] == 4 * 2 * (2 + 3)


def test_counts_refuse_to_start_without_enough_free_budget(http_cfg, store, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "PLACEHOLDER-KEY")
    seen: list = []
    r = run_collection(
        oa_card(reserve_credits=50), store, make_client(http_cfg, make_handler(seen, remaining=60)), Window.for_day(DAY)
    )
    assert r.status == "failed" and "60 credits left today" in r.error
    assert [req.url.path for req in seen] == ["/rate-limit"]  # nothing spent

    r = run_collection(oa_card(), store, make_client(http_cfg, make_handler([], prepaid=5.0)), Window.for_day(DAY))
    assert r.status == "failed" and "prepaid balance" in r.error

    r = run_collection(oa_card(max_credits=10), store, make_client(http_cfg, make_handler([])), Window.for_day(DAY))
    assert r.status == "failed" and "caps a run at 10" in r.error


def test_counts_stop_at_the_reserve_and_need_the_key(http_cfg, store, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "PLACEHOLDER-KEY")
    r = run_collection(
        oa_card(reserve_credits=100),
        store,
        make_client(http_cfg, make_handler([], refuse_after=3)),
        Window.for_day(DAY),
    )
    assert r.status == "failed" and "stopped with 10 credits left today" in r.error

    monkeypatch.delenv("OPENALEX_API_KEY")
    r = run_collection(oa_card(), store, make_client(http_cfg, make_handler([])), Window.for_day(DAY))
    assert r.status == "failed" and "OPENALEX_API_KEY is not set" in r.error


@pytest.mark.parametrize("limit", [1, 3])
def test_limit_caps_the_queries(http_cfg, store, monkeypatch, limit):
    monkeypatch.setenv("OPENALEX_API_KEY", "PLACEHOLDER-KEY")
    r = run_collection(
        oa_card(levels=["domain"]), store, make_client(http_cfg, make_handler([])), Window.for_day(DAY), limit=limit
    )
    assert r.status == "passed" and r.records == limit
