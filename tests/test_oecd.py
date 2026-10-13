"""The OECD sources (D-020): the Data API collector, feed categories, a JSON list endpoint and a delimited bulk file,
against hand-built replicas of each format (placeholder text)."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from moria.collectors import Window, run_collection
from moria.collectors.base import CollectError
from moria.collectors.oecd import OecdSdmxCollector
from moria.records import decode_bundle

from .conftest import card, make_client

DAY = date(2026, 10, 12)

SDMX = "\n".join(
    [
        "DATAFLOW,REF_AREA: Reference area,FREQ: Frequency,MEASURE: Measure,TIME_PERIOD: Time period,OBS_VALUE,"
        "OBS_STATUS: Observation status,UNIT_MULT: Unit multiplier,BASE_PER: Base period,DECIMALS: Decimals",
        "OECD.TEST:DSD_X@DF_X(1.3),AUS: Placeholder area,A: Annual,M1: Placeholder measure,2023,1.5,,"
        "0: Units,2015,1: One",
        "OECD.TEST:DSD_X@DF_X(1.3),AUS: Placeholder area,A: Annual,M1: Placeholder measure,2024,1.75,E: Estimated,"
        "0: Units,2015,1: One",
    ]
)
WORDS = "\n".join(
    [
        "DATAFLOW,REF_AREA: Reference area,FREQ: Frequency,MEASURE: Measure,TIME_PERIOD: Time period,OBS_VALUE",
        "OECD.TEST:DSD_Q@DF_Q(2.1),XXX: Placeholder area,A: Annual,NAME: Regime name,2024,Placeholder regime",
    ]
)


def oecd_card(queries, **params):
    return card("oecd_sdmx", {"base_url": "https://sdmx.test/rest", "queries": queries, **params},
                family="statistics", cadence="weekly")  # fmt: skip


QX = {"id": "numbers", "dataflow": "OECD.TEST,DSD_X@DF_X,", "key": ".A.M1", "start_period": "2020"}
QW = {"id": "words", "dataflow": "OECD.TEST,DSD_Q@DF_Q,2.1", "key": ".A.", "start_period": "2020",
      "text_values": True}  # fmt: skip
QE = {"id": "empty", "dataflow": "OECD.TEST,DSD_E@DF_E,", "key": ".A.", "start_period": "2020"}


def sdmx_handler(seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        if "DF_E" in request.url.path:
            return httpx.Response(404, text="NoResultsFound")
        return httpx.Response(200, text=WORDS if "DF_Q" in request.url.path else SDMX)

    return handler


def test_oecd_series_keep_codes_words_and_a_version_free_id(http_cfg, store):
    seen = []
    r = run_collection(oecd_card([QX, QW, QE]), store, make_client(http_cfg, sdmx_handler(seen)), Window.for_day(DAY))
    assert r.status == "passed", r.error
    recs = {x.envelope.provider_record_id: x for x in decode_bundle(store.get(r.bundle_key))}
    assert sorted(recs) == ["OECD.TEST:DSD_Q@DF_Q|XXX.A.NAME", "OECD.TEST:DSD_X@DF_X|AUS.A.M1"]
    x = recs["OECD.TEST:DSD_X@DF_X|AUS.A.M1"]
    assert x.envelope.provider == "OECD" and x.envelope.source_collection == "oecd_numbers"
    assert x.payload["dataflow"] == "OECD.TEST:DSD_X@DF_X(1.3)"  # the version this vintage came from
    assert x.payload["observations"] == [["2023", 1.5, None], ["2024", 1.75, "E"]]
    assert x.payload["attributes"]["BASE_PER"] == {"code": "2015", "label": ""}
    assert recs["OECD.TEST:DSD_Q@DF_Q|XXX.A.NAME"].payload["observations"] == [["2024", "Placeholder regime", None]]
    assert any("oecd query empty: no data" in w for w in r.warnings)
    assert seen[0].url.path == "/rest/data/OECD.TEST,DSD_X@DF_X,/.A.M1" and seen[0].url.params["startPeriod"] == "2020"
    assert "labels=both" in seen[0].headers["Accept"]


def test_oecd_words_without_text_values_fail_and_the_query_budget_is_enforced(http_cfg, store):
    no_words = dict(QW, text_values=False)
    r = run_collection(oecd_card([no_words]), store, make_client(http_cfg, sdmx_handler()), Window.for_day(DAY))
    assert r.status == "failed" and "non-numeric" in r.error
    with pytest.raises(CollectError, match="rate limit"):
        OecdSdmxCollector(oecd_card([dict(QX, id=f"q{i}") for i in range(3)], max_queries=2))
    with pytest.raises(Exception, match="agency,flow,version"):
        OecdSdmxCollector(oecd_card([dict(QX, dataflow="DF_X")]))


def test_oecd_refusal_is_retried_once_then_fails(http_cfg, store):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, text="slow down")

    r = run_collection(oecd_card([QX]), store, make_client(http_cfg, handler), Window.for_day(DAY))
    assert r.status == "failed" and "HTTP 429" in r.error and len(calls) == 2


FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Placeholder report</title><link>https://pub.test/a</link><guid>https://pub.test/a</guid>
<pubDate>Mon, 12 Oct 2026 22:00:00 GMT</pubDate><description>Placeholder abstract</description>
<category domain="content-type">Report</category><category domain="policy-area">Digital</category></item>
</channel></rss>"""


def test_feed_keeps_categories_only_when_the_card_asks(http_cfg, store):
    client = make_client(http_cfg, lambda r: httpx.Response(200, content=FEED))
    kept = run_collection(card("feed", {"url": "https://pub.test/rss", "keep_categories": True}), store, client,
                          Window.for_day(DAY))  # fmt: skip
    rec = decode_bundle(store.get(kept.bundle_key))[0]
    assert rec.payload["categories"] == [
        {"domain": "content-type", "term": "Report"},
        {"domain": "policy-area", "term": "Digital"},
    ]
    plain = run_collection(
        card("feed", {"url": "https://pub.test/rss"}, id="plain"), store, client, Window.for_day(DAY)
    )
    assert "categories" not in decode_bundle(store.get(plain.bundle_key))[0].payload


def json_pages():
    pages = {
        "1": {"data": [{"id": 9, "organizationName": "Org A", "country": "AUS", "publishedAt": "2026-10-02T05:35:28Z",
                        "reportingPeriodLabel": "Q3 2026", "secret": "not kept"}], "lastPage": 2},
        "2": {"data": [{"id": 3, "organizationName": "Org B", "country": "FRA", "publishedAt": "2025-02-15T20:09:43Z",
                        "reportingPeriodLabel": "Q1 2025"},
                       {"id": 4, "organizationName": "Org C", "publishedAt": "not a date"}], "lastPage": 2},
    }  # fmt: skip

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, json=pages[request.url.params["page"]])

    return handler


def json_card(**params):
    p = {
        "url": "https://api.test/reports",
        "date_field": "publishedAt",
        "title_field": "organizationName",
        "link_template": "https://site.test/reports/{id}",
        "fields": ["country", "reportingPeriodLabel"],
        **params,
    }
    return card("json_list", p, cadence="weekly")  # fmt: skip


def test_json_list_reads_every_page_and_keeps_metadata_within_the_lookback(http_cfg, store):
    client = make_client(http_cfg, json_pages())
    r = run_collection(json_card(lookback_days=14), store, client, Window.for_day(DAY))
    assert r.status == "passed", r.error
    recs = decode_bundle(store.get(r.bundle_key))
    assert [x.payload for x in recs] == [
        {"id": "9", "title": "Org A", "date": "2026-10-02T05:35:28+00:00", "link": "https://site.test/reports/9",
         "country": "AUS", "reportingPeriodLabel": "Q3 2026"}
    ]  # fmt: skip
    assert recs[0].envelope.observable_at.startswith("2026-10-02")
    assert any("without an id or a usable date" in w for w in r.warnings)
    every = run_collection(json_card(), store, client, Window.for_day(DAY), backfill=True)
    assert every.records == 2


def test_json_list_with_nothing_listed_fails(http_cfg, store):
    def handler(request):
        return httpx.Response(404) if request.url.path == "/robots.txt" else httpx.Response(200, json={"data": []})

    r = run_collection(json_card(), store, make_client(http_cfg, handler), Window.for_day(DAY))
    assert r.status == "failed" and "listed no items" in r.error


def stip_file(extra_row: str = "") -> bytes:
    lines = [
        "InitiativeID|CountryCode|NameEnglish|ShortDescription|StartDateYear|TH1|TH2",
        "Initiative id|Country code|English name|Description|Start year|Placeholder theme one|Placeholder theme two",
        "http://x.test/1|AUS|Placeholder one|Placeholder text|2021|1|0",
        "http://x.test/1|AUS|Placeholder one|Placeholder text|2021|1|0",
        'http://x.test/2|NZL|Placeholder "two"|Placeholder text|2023|0|1',
        "http://x.test/3|FRA|Placeholder|three|has a stray bar|2024|0|1",
    ]
    if extra_row:
        lines.append(extra_row)
    return ("\ufeff" + "\r\r\n".join(lines) + "\r\r\n").encode("utf-8")


def stip_card(**params):
    p = {
        "url": "https://stip.test/STIP.csv",
        "table": "instruments",
        "delimiter": "|",
        "quoting": "none",
        "label_row": True,
        "max_malformed_share": 0.5,
        "text_columns": ["ShortDescription"],
        "census": {"id_column": "InitiativeID", "group_columns": ["CountryCode"], "flag_prefix": "TH"},
        **params,
    }
    return card("delimited_csv", p, id="stip", cadence="weekly",
                expected_volume={"min_per_run": 1, "max_per_run": 10})  # fmt: skip


def test_delimited_file_goes_to_the_lake_with_labels_and_rows_left_out(http_cfg, store, tmp_path):
    import duckdb

    from moria.census import census_markdown
    from moria.delimited import refresh

    data = {"v": stip_file()}
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.headers.get("If-Modified-Since") == "Tue, 08 Sep 2026 11:35:40 GMT" and data["v"] == stip_file():
            return httpx.Response(304)
        return httpx.Response(200, content=data["v"], headers={"Last-Modified": "Tue, 08 Sep 2026 11:35:40 GMT"})

    r = refresh(stip_card(), store, make_client(http_cfg, handler))
    assert r.status == "passed", r.error
    assert r.records == 3 and any("1 rows with a stray delimiter" in w for w in r.warnings)
    release = json.loads(store.get("raw/stip/2026-09-08/manifest.json"))
    assert release["labels"]["TH1"] == "Placeholder theme one"
    assert release["malformed"] == {"rows": 1, "first_fields": ["http://x.test/3"]}
    assert release["text_stored"] is True
    path = tmp_path / "t.parquet"
    store.get_file(release["tables"]["instruments"]["key"], path)
    rows = (
        duckdb.connect().execute(f"SELECT NameEnglish, StartDateYear FROM read_parquet('{path}') ORDER BY 1").fetchall()
    )
    assert rows == [('Placeholder "two"', "2023"), ("Placeholder one", "2021"), ("Placeholder one", "2021")]
    text = census_markdown(store, stip_card())
    assert "distinct InitiativeID: 2" in text and "| AUS | 1 |" in text
    assert "| TH1 | Placeholder theme one | 1 |" in text and "Placeholder text" not in text

    again = refresh(stip_card(), store, make_client(http_cfg, handler))
    assert again.status == "passed" and again.records == 0 and "not modified" in again.warnings[0]

    data["v"] = stip_file("http://x.test/4|USA|Placeholder four|Placeholder text|2025|0|0")
    changed = refresh(stip_card(), store, make_client(http_cfg, handler))
    assert changed.status == "failed" and "a person should look" in changed.error


def test_delimited_text_columns_keep_only_lengths_when_text_is_not_allowed(http_cfg, store, tmp_path):
    import duckdb

    from moria.delimited import refresh

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=stip_file())

    r = refresh(stip_card(store_text=False), store, make_client(http_cfg, handler))
    assert r.status == "passed", r.error
    key = next(k for k in store.list("lake/stip/") if k.endswith(".parquet"))
    store.get_file(key, tmp_path / "t.parquet")
    values = duckdb.connect().execute(f"SELECT DISTINCT ShortDescription FROM read_parquet('{tmp_path}/t.parquet')")
    assert values.fetchall() == [("16",)]


def test_delimited_too_many_bad_rows_fail(http_cfg, store):
    from moria.delimited import refresh

    def handler(request):
        return httpx.Response(404) if request.url.path == "/robots.txt" else httpx.Response(200, content=stip_file())

    r = refresh(stip_card(max_malformed_share=0.1), store, make_client(http_cfg, handler))
    assert r.status == "failed" and "can't be split" in r.error
