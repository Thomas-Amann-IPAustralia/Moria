"""The BigQuery CPC counts collector, against a hand-built replica of BigQuery's REST answers (no Google calls)."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from moria.collectors import Window, run_collection
from moria.collectors.bigquery import BigQueryCpcCollector
from moria.records import decode_bundle

from .conftest import card, make_client

DAY = date(2026, 10, 11)


class FakeCredentials:
    valid = True
    token = "PLACEHOLDER-TOKEN"


@pytest.fixture(autouse=True)
def fake_google(monkeypatch):
    monkeypatch.setattr(BigQueryCpcCollector, "credentials_factory", staticmethod(lambda: FakeCredentials()))
    monkeypatch.setenv("GCP_PROJECT_ID", "placeholder-project")


def bq_card(**params):
    return card("bigquery_cpc", {"dry_run": False, "max_bytes_billed": 10_000, **params}, family="patent")


def cell_row(subclass, year, families, au):
    return {"f": [{"v": subclass}, {"v": str(year)}, {"v": str(families)}, {"v": str(au)}]}


SCHEMA = {"fields": [{"name": n} for n in ("subclass", "priority_year", "families", "au_families")]}


def make_handler(seen: list, estimate: int = 5_000):
    def handler(request):
        seen.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            if body["dryRun"]:
                return httpx.Response(200, json={"totalBytesProcessed": str(estimate), "jobComplete": True})
            return httpx.Response(200, json={"jobComplete": False, "jobReference": {"jobId": "j1", "location": "US"}})
        if "pageToken" in request.url.params:
            return httpx.Response(200, json={"rows": [cell_row("G06N", 2025, 300, 9)]})
        return httpx.Response(
            200,
            json={
                "jobComplete": True,
                "jobReference": {"jobId": "j1"},
                "schema": SCHEMA,
                "totalRows": "3",
                "rows": [cell_row("A01B", 2024, 120, 3), cell_row("G06N", 2024, 250, 7)],
                "pageToken": "next",
                "totalBytesProcessed": "4800",
                "totalBytesBilled": "10485760",
            },
        )

    return handler


def test_counts_come_back_per_subclass_with_the_cap_on_every_query(http_cfg, store):
    seen: list = []
    r = run_collection(bq_card(), store, make_client(http_cfg, make_handler(seen)), Window.for_day(DAY))
    assert r.status == "passed", r.error
    recs = {x.payload["cpc_subclass"]: x.payload for x in decode_bundle(store.get(r.bundle_key))}
    assert recs["G06N"]["years"] == [[2024, 250, 7], [2025, 300, 9]] and recs["A01B"]["years"] == [[2024, 120, 3]]
    posts = [json.loads(q.content) for q in seen if q.method == "POST"]
    assert [p["dryRun"] for p in posts] == [True, False]
    assert all(p["maximumBytesBilled"] == "10000" for p in posts)
    assert posts[1]["queryParameters"][0]["parameterValue"]["value"] == "2000"
    assert all(q.headers["Authorization"] == "Bearer PLACEHOLDER-TOKEN" for q in seen)
    assert "/projects/placeholder-project/queries" in str(seen[0].url)
    counts = json.loads(store.get(r.manifest_key))["counts"]
    assert counts["bytes_estimated"] == 5000 and counts["bytes_billed"] == 10485760


def test_dry_run_only_estimates_and_the_cap_refuses_a_large_query(http_cfg, store):
    seen: list = []
    r = run_collection(bq_card(dry_run=True), store, make_client(http_cfg, make_handler(seen)), Window.for_day(DAY))
    assert r.status == "passed" and r.records == 0 and "dry run only" in r.warnings[0]
    assert [json.loads(q.content)["dryRun"] for q in seen] == [True]  # nothing ran for real

    seen.clear()
    big = make_handler(seen, estimate=50_000)
    r = run_collection(bq_card(), store, make_client(http_cfg, big), Window.for_day(DAY))
    assert r.status == "failed" and "above the card's cap" in r.error
    assert len(seen) == 1


def test_missing_project_or_bad_table_fail_loudly(http_cfg, store, monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID")
    r = run_collection(bq_card(), store, make_client(http_cfg, make_handler([])), Window.for_day(DAY))
    assert r.status == "failed" and "GCP_PROJECT_ID is not set" in r.error
    with pytest.raises(Exception, match="unexpected table name"):
        BigQueryCpcCollector(bq_card(table="x`; DROP TABLE y; --"))
