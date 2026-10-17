"""The fixes from the review of the first queue (D-031, D-032): the trailing edge of research and patent counts,
reclassifications, IP RAPID pairs against their latest months, redundancy within a source, cluster names, document
signals held until their sources have a baseline, and the dossiers' checks in the queue."""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np

from moria import measures
from moria.artefacts import Checker
from moria.concepts import cluster_label, decide_combinations
from moria.config import load_detect, load_openalex_taxonomy, load_review
from moria.measures import Series, openalex_parent
from moria.rank import baseline_days, established, view_scores

CFG = load_detect()
AS_OF = date(2026, 10, 15)


def test_lags_cover_the_trailing_edge_and_staleness_counts_from_them():
    sc = CFG.series
    assert sc.lag("openalex_counts|topic|T10001|au|month") == 2
    assert sc.lag("openalex_counts|topic|T10001|au|year") == 0
    assert sc.lag("patent_cpc_counts|G06N|au") == 4 and sc.lag("patent_cpc_counts|G06N|world") == 3
    # a patent series lagged 4 years is still tested (staleness counts from its lag)
    pts = {measures.period_index("A", date(y, 1, 1)): 100.0 + 5 * (y - 2005) for y in range(2005, 2026)}
    tot = {i: 10_000.0 for i in pts}
    series = {
        "patent_cpc_counts|G06N|au": Series("patent_cpc_counts|G06N|au", "patent_cpc_counts", "A",
                                            {"label": "CPC G06N", "unit": "families", "scope": "au",
                                             "dimensions": "{}", "family": "patent", "rings": ["adjacent"]}, pts),
        "patent_cpc_counts|A01B|au": Series("patent_cpc_counts|A01B|au", "patent_cpc_counts", "A",
                                            {"label": "CPC A01B", "unit": "families", "scope": "au",
                                             "dimensions": "{}", "family": "patent", "rings": ["adjacent"]}, tot),
    }  # fmt: skip
    rows = measures._run(series, CFG, AS_OF)[0]
    got = {r["series_id"]: r for r in rows}["patent_cpc_counts|G06N|au"]
    assert got["last_period"] == "2021" and got["trend_windows"]


def test_index_only_patent_schemes_are_left_out():
    assert not CFG.series.tested("patent_cpc_counts", "au", {}, "patent_cpc_counts|A23V|au")
    assert not CFG.series.tested("patent_cpc_counts", "world", {}, "patent_cpc_counts|Y10T|world")
    assert CFG.series.tested("patent_cpc_counts", "au", {}, "patent_cpc_counts|Y02E|au")  # climate tagging stays


def test_an_openalex_count_is_a_share_of_its_parent():
    tax = load_openalex_taxonomy()
    topic, sub = next(iter(tax.topics.items()))
    assert openalex_parent(f"openalex_counts|topic|{topic}|au|month") == f"openalex_counts|subfield|{sub}|au|month"
    assert openalex_parent(f"openalex_counts|subfield|{sub}|world|year") == \
        f"openalex_counts|field|{sub[:2]}|world|year"  # fmt: skip
    dom = tax.fields[sub[:2]]
    assert openalex_parent(f"openalex_counts|field|{sub[:2]}|au|month") == f"openalex_counts|domain|{dom}|au|month"
    assert openalex_parent(f"openalex_counts|domain|{dom}|au|month") == "openalex_counts|total|au|month"
    assert openalex_parent("openalex_counts|topic|T0|au|month") == "openalex_counts|total|au|month"  # unknown


def test_a_whole_field_moving_shows_at_the_field_not_in_its_topics():
    """Two topics of one subfield both double their share of all works; against their subfield, neither moves."""
    tax = load_openalex_taxonomy()
    sub = next(iter(tax.topics.values()))
    topics = [t for t, s in tax.topics.items() if s == sub][:2]
    cfg = CFG.model_copy(update={"series": CFG.series.model_copy(update={"lags": []})})
    months = [measures.period_index("M", date(2023 + (m // 12), m % 12 + 1, 1)) for m in range(9, 45)]
    rng = np.random.default_rng(1)
    grow = {i: 1.0 + (k / len(months)) for k, i in enumerate(months)}

    def s(sid, pts):
        level = sid.split("|")[1]
        return Series(sid, "openalex_counts", "M", {"label": sid, "unit": "works", "scope": "world",
                      "dimensions": "{}", "family": "research", "rings": ["adjacent"],
                      "parent": openalex_parent(sid) if level != "total" else None}, pts)  # fmt: skip

    series = {}
    for t in topics:
        sid = f"openalex_counts|topic|{t}|world|month"
        series[sid] = s(sid, {i: float(round(200 * grow[i] + rng.normal(0, 3))) for i in months})
    sub_id = f"openalex_counts|subfield|{sub}|world|month"
    series[sub_id] = s(sub_id, {i: 2_000 * grow[i] for i in months})
    tot = "openalex_counts|total|world|month"
    series[tot] = s(tot, {i: 1_000_000.0 for i in months})
    rows = {r["series_id"]: r for r in measures._run(series, cfg, AS_OF)[0]}
    assert rows[sub_id]["denominator"] == tot and rows[sub_id]["trend_dir"] == 1
    for t in topics:
        r = rows[f"openalex_counts|topic|{t}|world|month"]
        assert r["denominator"] == sub_id and not r["trend_dir"]
        assert abs(r["volume_change"]) < 1e-6  # the coverage check reads all works, not the growing subfield


def test_a_reclassification_flags_the_classes_it_moved():
    row = {"denominator": "x", "volume_change": 0.0, "surge_volume_change": 0.0, "frequency": "A"}
    series = {"patent_cpc_counts|G06K|au": row, "patent_cpc_counts|G06N|au": row}
    checker = Checker(CFG, {}, AS_OF, [], [], [], series, {}, [], [])
    c = {
        "subject_kind": "series",
        "subject": "patent_cpc_counts|G06K|au",
        "sources": ["patent_cpc_counts"],
        "type": "acceleration",
        "detectors": ["acceleration"],
        "window_start": "2006",
        "window_end": "2021",
    }
    out, details = checker.series_check(c)
    assert out["source_break"] == "flag" and "G06V" in details["source_break"][0]
    out, _ = checker.series_check({**c, "subject": "patent_cpc_counts|G06N|au"})
    assert out["source_break"] == "pass"


def _pair(window, baseline, recent, aw=100, bw=100, nw=1_000, rising=False, fading=False):
    return {"scheme": "ipc_country", "combination": "nc:ipc_country:CN+A01C", "window": window, "baseline": baseline,
            "a_window": aw, "b_window": bw, "a_baseline": 500, "b_baseline": 500, "window_sources": 2,
            "baseline_sources": 2, "lift_window": None, "lift_baseline": None, "rising": rising, "fading": fading,
            "_exposure": (nw, 5_000, 12, 60), "_recent": (recent, 200, 200, 2_000)}  # fmt: skip


def test_ip_rapid_pairs_are_compared_with_their_latest_months():
    # a step down years ago: the baseline held many, the latest 24 months few, the window few: not fading now
    old = _pair(window=1, baseline=120, recent=4)
    old["lift_baseline"], old["lift_window"] = 120 * 5_000 / (500 * 500), 1 * 1_000 / (100 * 100)
    # a fall in the window itself: the latest months were still busy
    new = _pair(window=1, baseline=120, recent=48)
    new["lift_baseline"], new["lift_window"] = old["lift_baseline"], old["lift_window"]
    decide_combinations([old, new], CFG)
    assert new["fading"] and not old["fading"]
    assert new["recent"] == 48 and new["expected_recent"] > old["expected_recent"]
    assert "_recent" not in old


def test_a_cluster_is_named_by_a_title_and_its_first_keyphrases():
    assert cluster_label("Former PM meets   trade minister", ["trade deal", "india", "uk", "soy"], 3) == \
        "Former PM meets trade minister (and similar: trade deal; india; uk)"  # fmt: skip
    assert cluster_label(None, ["a", "b"], 3) == "a; b"
    assert cluster_label("x" * 200, [], 3).endswith("...")


def test_a_document_signal_waits_for_its_sources_baseline():
    end = datetime(2026, 10, 16, tzinfo=UTC)
    vols = [{"source": "old", "coverage_start": datetime(2020, 1, 1, tzinfo=UTC)},
            {"source": "older", "coverage_start": datetime(2019, 1, 1, tzinfo=UTC)},
            {"source": "new", "coverage_start": datetime(2026, 10, 11, tzinfo=UTC)}]  # fmt: skip
    hist = baseline_days(vols, AS_OF, 91, 730)
    assert hist["old"] == 730 and hist["new"] == 0 and end > vols[2]["coverage_start"]
    items = [{"role": "window", "source": s, "dedup_group": g} for s, g in
             (("new", "g1"), ("new", "g2"), ("old", "g3"), ("new", "g4"))]  # fmt: skip
    assert not established(items, hist, 90, 3, 2)  # without the new source: 1 group from 1 source
    items += [{"role": "window", "source": "older", "dedup_group": "g5"},
              {"role": "window", "source": "older", "dedup_group": "g6"}]  # fmt: skip
    assert established(items, hist, 90, 3, 2)
    row = {
        "views": ["early_warning"],
        "held": True,
        "strength_pct": 0.9,
        "novelty": 1.0,
        "lead": 1.0,
        "breadth": 0.5,
        "scope_factor": 1.0,
        "type_factor": 1.0,
        "flag_factor": 1.0,
        "context_factor": 1.0,
    }
    view_scores(row, load_review())
    assert row["score_early_warning"] is None and row["score_strategic"] is None


def test_the_queue_weighs_the_dossiers_checks():
    review = load_review()
    assert set(review.queue.dossier_penalty) == {"concentrated_works", "reclassified", "few_applicants"}
    assert all(0 < v < 1 for v in review.queue.dossier_penalty.values())


def test_a_change_point_many_series_share_is_a_source_break():
    from moria.artefacts import crowded_breaks

    rows = [{"source": "openalex_counts", "frequency": "M", "cp_slope_period": "2025-11", "cp_level_period": None}
            for _ in range(30)]  # fmt: skip
    rows += [{"source": "openalex_counts", "frequency": "M", "cp_slope_period": f"2024-{m:02d}",
              "cp_level_period": None} for m in range(1, 13) for _ in range(3)]  # fmt: skip
    stats = [{**r, "source": "abs_headline"} for r in rows]  # a shared shock in statistics is not a source break
    hot = crowded_breaks(rows + stats, CFG)
    assert hot == {("openalex_counts", "M"): {"2025-11": 30}}
    series = {"openalex_counts|topic|T1|world|month": {"denominator": "d", "volume_change": 0.0,
              "surge_volume_change": 0.0, "frequency": "M", "source": "openalex_counts"}}  # fmt: skip
    checker = Checker(CFG, {}, AS_OF, [], [], [], {**series}, {}, [], [])
    checker.crowded = hot
    c = {
        "subject_kind": "series",
        "subject": "openalex_counts|topic|T1|world|month",
        "sources": ["openalex_counts"],
        "type": "acceleration",
        "detectors": ["acceleration"],
        "window_start": "2023-09",
        "window_end": "2026-08",
        "numbers": '{"acceleration": {"change_point": "2025-11"}}',
    }
    out, details = checker.series_check(c)
    assert out["source_break"] == "flag" and "shared break" in details["source_break"][0]


def test_backfill_collects_missing_past_days_newest_first(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    from typer.testing import CliRunner

    from moria import cli
    from moria.store import LocalStore

    store = LocalStore(tmp_path)
    done = {"day": "2026-10-09", "status": "passed", "source": "gdelt_news"}
    store.put("monitors/ingestion/source=gdelt_news/2026-10-09/r1.json", json.dumps(done).encode())
    store.put("monitors/ingestion/source=gdelt_news/2026-10-11/r2.json", json.dumps(done).encode())
    asked = []

    def fake(sources, day, limit, backend, backfill=False):
        asked.append(day)
        return [SimpleNamespace(status="passed", source=sources[0])]

    monkeypatch.setattr(cli, "open_store", lambda cfg, backend=None: store)
    monkeypatch.setattr(cli, "_collect", fake)
    run = CliRunner().invoke(cli.app, ["backfill", "gdelt_news", "--from", "2026-10-05", "--max-days", "3"])
    assert run.exit_code == 0, run.output
    # up to the day before the first collection (10-08), newest first, skipping collected days, three this run
    assert asked == [date(2026, 10, 8), date(2026, 10, 7), date(2026, 10, 6)]
    assert cli.collected_days(store, "gdelt_news") == {date(2026, 10, 9), date(2026, 10, 11)}
    refused = CliRunner().invoke(cli.app, ["backfill", "un_news", "--from", "2026-01-01"])
    assert refused.exit_code == 2
