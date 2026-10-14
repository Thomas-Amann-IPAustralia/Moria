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
    daily = card("feed", {}, id="feed_a", cadence="daily")
    entries = [
        {"source": "feed_a", "day": "2026-10-10", "run_id": "r1", "status": "passed", "records": 5, "flag": "ok"},
        {"source": "feed_a", "day": "2026-10-13", "run_id": "r3", "status": "passed", "records": 0,
         "flag": "below_expected", "expected": {"min_per_run": 1}},
    ]  # fmt: skip
    manifests = [{"command": "collect.feed_a", "run_id": "20261011T020000Z-x", "status": "failed", "error": "boom",
                  "params": {"window_start": "2026-10-11T00:00:00+00:00"}}]  # fmt: skip
    days, incidents = summarise(entries, manifests, {"feed_a": daily}, date(2026, 10, 14))
    kinds = {(i["day"].isoformat(), i["kind"]) for i in incidents}
    assert kinds == {("2026-10-11", "failed_run"), ("2026-10-12", "gap"), ("2026-10-13", "below_expected")}
    flags = {d["day"].isoformat(): d["flag"] for d in days}
    assert flags == {"2026-10-10": "ok", "2026-10-11": "failed", "2026-10-12": "gap", "2026-10-13": "below_expected"}


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
