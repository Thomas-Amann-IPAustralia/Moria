"""Day 4's smaller parts: the ingestion monitor's incidents and gaps, an item's ring, the cards' dated breaks, and a
candidate's id."""

from __future__ import annotations

from datetime import date

from moria.artefacts import card_breaks
from moria.concepts import item_ring
from moria.detect import candidate_id
from moria.monitor import summarise

from .conftest import card


def test_monitor_finds_failures_bands_and_gaps():
    daily = card("feed", {}, id="feed_a", cadence="daily", expected_volume={"min_per_run": 1, "max_per_run": 50})
    entries = [
        {"source": "feed_a", "day": "2026-10-06", "run_id": "r0", "status": "passed", "records": 500},  # backfill
        {"source": "feed_a", "day": "2026-10-07", "run_id": "r1", "status": "passed", "records": 90},
        {"source": "feed_a", "day": "2026-10-10", "run_id": "r3", "status": "passed", "records": 0},
        {"source": "feed_a", "day": "2026-10-11", "run_id": "r4", "status": "passed", "records": 0},  # a dry run
        {"source": "feed_a", "day": "2026-10-11", "run_id": "r5", "status": "passed", "records": 7},  # then a good one
    ]
    manifests = [
        {"command": "collect.feed_a", "run_id": "20261008T020000Z-x", "status": "failed", "error": "boom",
         "params": {"window_start": "2026-10-08T00:00:00+00:00"}},
        {"command": "collect.feed_a", "run_id": "20261011T020000Z-y", "status": "failed", "error": "retried",
         "params": {"window_start": "2026-10-11T00:00:00+00:00"}},
    ]  # fmt: skip
    days, incidents = summarise(entries, manifests, {"feed_a": daily}, date(2026, 10, 14))
    kinds = {(i["day"].isoformat(), i["kind"]) for i in incidents}
    assert kinds == {
        ("2026-10-07", "above_expected"),
        ("2026-10-08", "failed_run"),
        ("2026-10-09", "gap"),
        ("2026-10-10", "below_expected"),
        ("2026-10-12", "gap"),
    }  # 10-13 is collected on 10-14
    flags = {d["day"].isoformat(): d["flag"] for d in days}
    assert flags["2026-10-06"] == "ok" and flags["2026-10-11"] == "ok"  # the first snapshot; the day's best run


def test_monitor_spares_snapshots_releases_and_sources_without_a_daily_volume():
    daily = card("feed", {}, id="feed_a", cadence="daily", expected_volume={"min_per_run": 1, "max_per_run": 50})
    monthly = card(
        "bigquery_cpc", {}, id="cpc", cadence="monthly", expected_volume={"min_per_run": 9, "max_per_run": 99}
    )
    bulk = card("zip_csv", {}, id="bulk", cadence="once", expected_volume={"min_per_run": 100, "max_per_run": 200})
    entries = [
        {"source": "feed_a", "day": "2026-10-10", "run_id": "a1", "status": "passed", "records": 5},
        {"source": "feed_a", "day": "2026-10-11", "run_id": "a2", "status": "passed", "records": 900},
        {"source": "feed_a", "day": "2026-10-12", "run_id": "a3", "status": "passed", "records": 4},
        {"source": "cpc", "day": "2026-10-11", "run_id": "c1", "status": "passed", "records": 0},  # a dry run
        {"source": "bulk", "day": "2025-03-10", "run_id": "20261012T010000Z-b1", "status": "passed", "records": 5},
    ]
    manifests = [
        {"command": "collect.feed_a", "run_id": "a2", "status": "passed", "params": {"backfill": True}},
        {"command": "collect.bulk", "run_id": "20261012T010000Z-b1", "status": "passed",
         "params": {"release": "2025-03-10"}, "counts": {"rows": 150}},
    ]  # fmt: skip
    cards = {"feed_a": daily, "cpc": monthly, "bulk": bulk}
    days, incidents = summarise(entries, manifests, cards, date(2026, 10, 14))
    assert not incidents  # a backfill run; a monthly source's dry run; a one-off release
    assert {(d["source"], d["day"].isoformat()) for d in days if d["source"] == "bulk"} == {("bulk", "2025-03-10")}


def test_item_ring_uses_the_card_then_core_terms_then_the_tagger():
    one = card("feed", {}, rings=["wider_world"])
    many = card("feed", {}, rings=["core", "adjacent", "wider_world"])
    probs = {"core": 0.9, "adjacent": 0.06, "wider_world": 0.04}
    assert item_ring(one, ["theme:ip_system:0"], probs) == "wider_world"
    assert item_ring(many, ["theme:ip_system:0"], probs) == "core"
    assert item_ring(many, ["T1:core:0"], probs) == "core"
    assert item_ring(many, ["T1:adjacent:0"], probs) == "adjacent"  # core only through core terms (D-021)
    assert item_ring(card("feed", {}, rings=["core", "adjacent"]), [], probs) == "adjacent"


def test_only_dated_breaks_apply_to_a_whole_source():
    c = card("feed", {}, id="s", breaks=["2026-10-12: parser v3", "CPI: the monthly CPI begins 2024-04", "2025-06"])
    assert card_breaks({"s": c}) == {"s": [date(2025, 6, 1), date(2026, 10, 12)]}


def test_candidate_ids_follow_the_subject_across_scans():
    assert candidate_id("kp:example") == candidate_id("kp:example") != candidate_id("kp:other")
    assert candidate_id("kp:example").startswith("sig-") and len(candidate_id("kp:example")) == 16


def test_class_pairs_mark_a_class_new_to_the_scheme(tmp_path):
    from moria.concepts import class_pairs, decide_combinations
    from moria.config import load_detect
    from moria.iprmetrics import CLASS_COUNTS, CLASS_PAIRS
    from moria.tables import write_rows

    from .detect_fixtures import AS_OF, months

    pairs, counts = [], []
    for p in months("2026-01", 9):  # the window: two new pairs, one with a subclass the scheme added in 2025
        for a, b, who in (("A01B", "G06N", ("p1", "p2")), ("G06N", "H10D", ("p3", "p4"))):
            pairs.append({"right": "patent", "scheme": "ipc", "class_a": a, "class_b": b, "period": p,
                          "applications": 1, "applicant_min": who[0], "applicant_max": who[1]})  # fmt: skip
    for c, start, n in (("A01B", "2015-01", 129), ("G06N", "2015-01", 129), ("H10D", "2025-01", 9),
                        ("*", "2015-01", 129)):  # fmt: skip
        counts += [{"right": "patent", "scheme": "ipc", "class": c, "period": p, "applications": 5}
                   for p in months(start, n)]  # fmt: skip
    write_rows(pairs, CLASS_PAIRS, tmp_path / "class_pairs.parquet", ("period",))
    write_rows(counts, CLASS_COUNTS, tmp_path / "class_counts.parquet", ("period",))
    files = {"ipr": {f"lake/ipr_metrics/{n}": tmp_path / n for n in ("class_pairs.parquet", "class_counts.parquet")}}
    cfg = load_detect()
    rows = class_pairs(files, AS_OF, cfg)
    for r in rows:
        r["_exposure"] = (*r["_exposure"], 12, 60)
    decide_combinations(rows, cfg)
    got = {(r["a"], r["b"]): r for r in rows}
    assert got[("A01B", "G06N")]["new"] and not got[("A01B", "G06N")]["new_class"]
    assert got[("G06N", "H10D")]["new_class"] and got[("G06N", "H10D")]["classes_since"] == "2025-01"
