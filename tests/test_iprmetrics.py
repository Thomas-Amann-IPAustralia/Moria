"""`moria ipr metrics` on a tiny hand-built IP RAPID lake: a base and a delta, origin, self-filing (an applicant as
its own agent), first-time applicants, G06N, timeliness, vintages, and discontinued series."""

from __future__ import annotations

import json
from datetime import date

import duckdb
import pyarrow.parquet as pq

from moria.iprmetrics import drop_discontinued, metrics
from moria.records import canonical_json

from .conftest import card

APPS = [  # number, right, sub type, filed, registered
    ("1", "trade_mark", "trade_mark", "2026-01-10", "2026-08-20"),
    ("2", "trade_mark", "trade_mark", "2026-01-20", None),
    ("3", "patent", "standard_complete", "2026-02-05", None),
    ("4", "trade_mark", "certification", "2026-03-01", None),
]
PARTIES = [  # number, right, party id, role category, country
    ("1", "trade_mark", "p1", "applicant", "AU"),
    ("1", "trade_mark", "p1", "applicant_agent", "AU"),  # the applicant is its own agent: self-filed
    ("2", "trade_mark", "p2", "applicant", "US"),
    ("2", "trade_mark", "g9", "applicant_agent", "AU"),  # a firm files for it
    ("3", "patent", "p1", "applicant", "AU"),
    ("4", "trade_mark", "p1", "applicant", "AU"),  # p1's second trade mark: not first-time
]


def lake(tmp_path, store, apps, release, mode="base", delta_rows=None):
    con = duckdb.connect()
    work = tmp_path / release
    work.mkdir()
    tables = {}

    def write(name, sql):
        path = work / f"{name}.parquet"
        con.execute(f"COPY ({sql}) TO '{path.as_posix()}' (FORMAT parquet)")
        key = f"lake/ip_rapid/{mode}={release}/{name}.parquet"
        store.put_file(key, path)
        tables[name] = {"key": key}

    vals = ", ".join(f"('{n}', '{r}', '{s}', DATE '{f}', {f'DATE {g!r}' if g else 'NULL'})" for n, r, s, f, g in apps)
    write("application", f"SELECT * FROM (VALUES {vals}) t(application_number, ip_right_type, ip_right_sub_type, "
                         "application_date, gained_registration_status_date)")  # fmt: skip
    pv = ", ".join(f"('{n}', '{r}', '{p}', '{c}', '{cc}', true)" for n, r, p, c, cc in PARTIES)
    write("party_activity", f"SELECT * FROM (VALUES {pv}) t(application_number, ip_right_type, party_id, "
                            "party_role_category, country_code, is_founding)")  # fmt: skip
    write("application_links", "SELECT '1' AS application_number, 'trade_mark' AS ip_right_type, "
                               "'madrid_import' AS link_type")  # fmt: skip
    write("application_classification", "SELECT '3' AS application_number, 'patent' AS ip_right_type, true AS "
          "is_current, 'ipc_mark' AS classification_system, 'G06N 3/08' AS classification")  # fmt: skip
    write("application_events", "SELECT * FROM (VALUES ('1', 'trade_mark', 'opposition', DATE '2026-05-02'), "
          "('2', 'trade_mark', 'publish_renew', DATE '2018-11-01')) t(application_number, ip_right_type, "
          "event_category, event_effective_date)")  # fmt: skip
    if delta_rows:
        path = work / "delta-application.parquet"
        con.execute(f"COPY ({delta_rows}) TO '{path.as_posix()}' (FORMAT parquet)")
        key = f"lake/ip_rapid/delta={release}/application.parquet"
        store.put_file(key, path)
        tables = {"application": {"key": key}}
    manifest = {"release_date": release, "mode": mode, "tables": tables}
    if mode == "delta":
        manifest["base_release"] = "2026-09-07"
    store.put(f"raw/ip_rapid/{release}/manifest.json", canonical_json(manifest).encode())


def obs(store):
    return pq.read_table(store.root / "lake/ipr_metrics/observations.parquet").to_pylist()


def test_metrics_from_a_base_then_a_delta(tmp_path, store):
    c = card("ip_rapid", {}, family="ipa_internal")
    lake(tmp_path, store, APPS, "2026-09-07")
    status, mkey, counts = metrics(store, c, threads=1, memory_limit="500MB")
    assert status == "passed", counts
    v = {(o["series_id"].split("|", 1)[1], o["period"]): o["value"] for o in obs(store)}
    assert v[("applications|trade_mark|all", "2026-01")] == 2
    assert v[("applications|trade_mark|certification", "2026-03")] == 1
    assert v[("applications_au|trade_mark", "2026-01")] == 1 and v[("applications_overseas|trade_mark", "2026-01")] == 1
    assert v[("applications_self_filed|trade_mark", "2026-01")] == 1  # number 1 (its own agent), not number 2
    assert v[("first_time_applicants|trade_mark", "2026-01")] == 2 and ("first_time_applicants|trade_mark",
                                                                      "2026-03") not in v  # fmt: skip
    assert v[("applications_ai_g06n|patent", "2026-02")] == 1 and v[("madrid_designating_au|trade_mark", "2026-01")]
    assert v[("days_to_registration_median|trade_mark", "2026-08")] == 222
    assert v[("oppositions|trade_mark", "2026-05")] == 1
    m = json.loads(store.get(mkey))
    assert "renewals|trade_mark" in m["params"]["discontinued"]  # its events stop in 2018
    # a delta: one more application in January; only the changed values become a new vintage
    added = ("SELECT 'added' AS _change, '5' AS application_number, 'trade_mark' AS ip_right_type, "
             "'trade_mark' AS ip_right_sub_type, DATE '2026-01-25' AS application_date, "
             "NULL::DATE AS gained_registration_status_date")  # fmt: skip
    lake(tmp_path, store, APPS, "2026-10-12", mode="delta", delta_rows=added)
    assert metrics(store, c, threads=1, memory_limit="500MB")[0] == "passed"
    jan = sorted((o["vintage_at"].date(), o["value"]) for o in obs(store)
                 if o["series_id"].endswith("applications|trade_mark|all") and o["period"] == "2026-01")  # fmt: skip
    assert jan == [(date(2026, 9, 7), 2.0), (date(2026, 10, 12), 3.0)]
    march = [o for o in obs(store) if o["series_id"].endswith("trade_mark|certification")]
    assert len(march) == 1  # unchanged: no second vintage
    status = {o["period"]: o["status"] for o in obs(store) if o["series_id"].endswith("applications|trade_mark|all")}
    assert status.get("2026-10") is None and status["2026-01"] is None


def test_drop_discontinued():
    rows = [("a", "2026-09", "x", 1.0), ("b", "2025-06", "x", 1.0), ("c", "2025-10", "x", 1.0)]
    kept, stopped = drop_discontinued(rows, date(2026, 10, 12))
    assert stopped == ["b"] and [r[0] for r in kept] == ["a", "c"]
