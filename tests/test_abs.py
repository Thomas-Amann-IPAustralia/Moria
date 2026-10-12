"""The ABS SDMX collector, against hand-built replicas of the ABS Data API's CSV (placeholder labels)."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from moria.collectors import Window, run_collection
from moria.collectors.abs import parse_sdmx_csv
from moria.records import decode_bundle

from .conftest import card, make_client

DAY = date(2026, 10, 11)
HEADER = (
    "DATAFLOW,MEASURE: Measure,REGION: Region,FREQ: Frequency,TIME_PERIOD: Time Period,OBS_VALUE,"
    "UNIT_MEASURE: Unit of Measure,UNIT_MULT: Unit of Multiplier,OBS_STATUS: Observation Status,"
    "OBS_COMMENT: Observation Comment,DECIMALS: Decimals"
)
CSV = "\n".join(
    [
        HEADER,
        "ABS:TEST(1.0.0),M1: Placeholder measure,AUS: Placeholder region,Q: Quarterly,2026-Q1,4.5,PCT: Percent,"
        "0: Units,,,1: One",
        "ABS:TEST(1.0.0),M1: Placeholder measure,AUS: Placeholder region,Q: Quarterly,2025-Q4,4.25,PCT: Percent,"
        "0: Units,p: Preliminary,,1: One",
        "ABS:TEST(1.0.0),M2: Another measure,AUS: Placeholder region,Q: Quarterly,2025-Q4,,PCT: Percent,"
        "0: Units,,,1: One",
    ]
)


def abs_card(queries, **params):
    return card(
        "abs_sdmx",
        {"base_url": "https://abs.test/rest", "queries": queries, **params},
        family="statistics",
        cadence="weekly",
    )


Q1 = {"id": "first", "dataflow": "TEST", "key": "M1+M2.AUS.Q", "start_period": "2025"}
Q2 = {"id": "second", "dataflow": "ABS,EMPTY,1.0.0", "key": "X.AUS.Q", "start_period": "2025"}


def test_parse_groups_rows_into_series_with_codes_labels_and_status():
    series = parse_sdmx_csv(CSV)
    assert [s["series_key"] for s in series] == ["M1.AUS.Q", "M2.AUS.Q"]
    m1 = series[0]
    assert m1["dimensions"]["MEASURE"] == {"code": "M1", "label": "Placeholder measure"}
    assert m1["observations"] == [["2025-Q4", 4.25, "p"], ["2026-Q1", 4.5, None]]
    assert m1["attributes"]["UNIT_MEASURE"] == {"code": "PCT", "label": "Percent"}
    assert (m1["first_period"], m1["last_period"], m1["n_obs"]) == ("2025-Q4", "2026-Q1", 2)
    assert series[1]["observations"] == [["2025-Q4", None, None]]  # a missing value is kept as null


def test_collect_keeps_each_series_and_warns_on_an_empty_query(http_cfg, store):
    seen = []

    def handler(request):
        seen.append(request)
        if "/EMPTY," in request.url.path or "EMPTY" in request.url.path:
            return httpx.Response(404, text="NoResultsFound")
        return httpx.Response(200, text=CSV)

    r = run_collection(abs_card([Q1, Q2]), store, make_client(http_cfg, handler), Window.for_day(DAY))
    assert r.status == "passed", r.error
    recs = decode_bundle(store.get(r.bundle_key))
    assert sorted(x.envelope.provider_record_id for x in recs) == ["TEST|M1.AUS.Q", "TEST|M2.AUS.Q"]
    assert {x.envelope.source_collection for x in recs} == {"abs_test"}
    assert all(x.payload["query_id"] == "first" for x in recs)
    assert any("abs query second: no data" in w for w in r.warnings)
    assert seen[0].headers["Accept"].startswith("application/vnd.sdmx.data+csv")
    assert seen[0].url.params["startPeriod"] == "2025" and seen[0].url.path == "/rest/data/TEST/M1+M2.AUS.Q"


def test_an_unchanged_series_keeps_its_evidence_id_across_runs(http_cfg, store):
    client = make_client(http_cfg, lambda r: httpx.Response(200, text=CSV))
    ids = []
    for _ in range(2):
        r = run_collection(abs_card([Q1]), store, client, Window.for_day(DAY))
        ids.append(sorted(x.envelope.evidence_id for x in decode_bundle(store.get(r.bundle_key))))
    assert ids[0] == ids[1]  # a vintage that changed nothing is recognisably the same evidence


def test_collect_fails_loudly(http_cfg, store):
    empty = make_client(http_cfg, lambda r: httpx.Response(404))
    r = run_collection(abs_card([Q1, Q2]), store, empty, Window.for_day(DAY))
    assert r.status == "failed" and "every query returned no data" in r.error

    capped = run_collection(
        abs_card([Q1], max_series_per_query=1),
        store,
        make_client(http_cfg, lambda r: httpx.Response(200, text=CSV)),
        Window.for_day(DAY),
    )
    assert capped.status == "failed" and "returned 2 series, above the card's cap of 1" in capped.error

    bad = make_client(http_cfg, lambda r: httpx.Response(200, text="<html>not csv</html>"))
    r = run_collection(abs_card([Q1]), store, bad, Window.for_day(DAY))
    assert r.status == "failed" and "unexpected CSV header" in r.error


def test_query_ids_must_be_unique():
    from moria.collectors.abs import AbsSdmxCollector

    with pytest.raises(Exception, match="unique"):
        AbsSdmxCollector(abs_card([Q1, Q1]))
