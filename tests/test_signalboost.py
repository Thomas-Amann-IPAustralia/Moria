"""The SignalBoost detectors (D-025) on hand-built series and pairs: horizons, context, coupling, redundancy, fading
pairs, jurisdictions by class, the candidates' switches and corroboration, and the evaluation's parts. Numbers are
synthetic."""

from __future__ import annotations

import json
from datetime import date

import numpy as np

from moria import detect, evaldetect, measures
from moria.concepts import _combination, country_pairs, decide_combinations
from moria.config import load_detect
from moria.measures import Series, period_index_of_label

from .detect_fixtures import AS_OF, months

CFG = load_detect()


def cfg_with(**on) -> object:
    return CFG.model_copy(update={"new_detectors": {**CFG.new_detectors, **on}})


def S(sid: str, source: str, kind: str, values: dict[str, float], scope: str = "AUS", unit: str = "applications",
      dims: dict | None = None, family: str = "patent") -> Series:  # fmt: skip
    meta = {"label": sid.split("|")[-1], "unit": unit, "scope": scope, "dimensions": json.dumps(dims or {}),
            "family": family, "rings": ["core"]}  # fmt: skip
    return Series(sid, source, kind, meta, {period_index_of_label(kind, p): float(v) for p, v in values.items()})


def ipr_layer(seed: int = 3) -> dict[str, Series]:
    """IP RAPID-like monthly counts, 2006-01 to 2026-09: a subclass whose share starts growing 25% a year in 2021
    (a structural break), a copy of it (a redundant indicator), a flat one, and one doubled in its last 3 months."""
    rng = np.random.default_rng(seed)
    ms = months("2006-01", 249)
    total = {m: float(rng.poisson(4000)) for m in ms}
    out = {"t": S("ip_rapid_metrics|applications|patent|all", "ip_rapid_metrics", "M", total)}
    start = ms.index("2021-01")
    shapes = {
        "G06N": lambda i: 0.01 * np.exp(0.25 * max(i - start, 0) / 12),
        "A01B": lambda i: 0.01,
        "B01B": lambda i: 0.01 * (2.0 if i >= len(ms) - 3 else 1.0),
    }
    for code, f in shapes.items():
        vals = {m: float(rng.poisson(total[m] * f(i))) for i, m in enumerate(ms)}
        out[code] = S(f"ip_rapid_metrics|applications_ipc|patent|{code}", "ip_rapid_metrics", "M", vals)
        if code == "G06N":
            out["H04L"] = S("ip_rapid_metrics|applications_ipc|patent|H04L", "ip_rapid_metrics", "M", dict(vals))
    return {s.series_id: s for s in out.values()}


def run(series: dict[str, Series], cfg=CFG):
    return measures._run(series, cfg, AS_OF)


def test_horizons_tell_a_break_from_a_shift_and_from_noise():
    rows, _, counts, hrows, _, red = run(ipr_layer())
    by = {(h["series_id"].rsplit("|", 1)[1], h["horizon_months"]): h for h in hrows}
    r = {x["series_id"].rsplit("|", 1)[1]: x for x in rows}
    assert {m for (c, m) in by if c == "G06N"} == {3, 6, 12, 36, 60, 120, 180}
    assert any(by[("G06N", m)]["structural"] and by[("G06N", m)]["structural_direction"] == 1 for m in (120, 180))
    assert r["G06N"]["horizon_profile"] == "structural_shift"
    assert by[("B01B", 3)]["sig"] and by[("B01B", 3)]["direction"] == 1 and by[("B01B", 3)]["method"] == "short"
    # noise: no short shift, long-run trend or break (a lone 12-month window at 5% in a family of 4 may pass)
    assert not any((h["sig"] and h["method"] != "medium") or h["structural"] for (c, _), h in by.items() if c == "A01B")
    assert r["A01B"]["horizon_profile"] in (None, "sustained")
    # the copy moves exactly like the original: one redundancy group, not two lines of evidence
    groups = {x["series_id"].rsplit("|", 1)[1]: x["group"] for x in red}
    assert groups["G06N"] == groups["H04L"] and r["G06N"]["redundancy_group"] == groups["G06N"]
    assert counts["horizon_structural"] >= 2


def test_a_horizon_beyond_the_history_is_not_tested():
    series = {k: v for k, v in ipr_layer().items()}
    for s in series.values():  # keep 40 months
        s.points = dict(sorted(s.points.items())[-40:])
    _, _, _, hrows, _, _ = run(series)
    assert {h["horizon_months"] for h in hrows} <= {3, 6, 12, 36}


def openalex_family(seed: int = 5) -> dict[str, Series]:
    """Monthly topic and subfield shares in Australia and the world sharing a common factor; topic T0 doubles in
    Australia in the last month alone; every Australian subfield jumps 80% in the last month together."""
    rng = np.random.default_rng(seed)
    ms = months("2023-10", 36)  # to 2026-09
    factor = np.cumsum(rng.normal(0, 0.12, len(ms)))
    out = []
    for scope, total in (("au", 400_000.0), ("world", 4_000_000.0)):
        out.append(S(f"openalex_counts|total|{scope}|month", "openalex_counts", "M", {m: total for m in ms},
                     scope=scope, unit="works", family="research"))  # fmt: skip
        for level, jump in (("topic", "T0"), ("subfield", "all")):
            for k in range(8):
                name = f"{'T' if level == 'topic' else 'S'}{k}"
                f = factor + rng.normal(0, 0.02, len(ms))
                vals = {}
                for i, m in enumerate(ms):
                    lam = total * 0.002 * np.exp(f[i])
                    if scope == "au" and i == len(ms) - 1 and (jump == "all" or name == jump):
                        lam *= 2.0 if level == "topic" else 1.8
                    vals[m] = float(rng.poisson(lam))
                out.append(S(f"openalex_counts|{level}|{name}|{scope}|month", "openalex_counts", "M", vals,
                             scope=scope, unit="works", family="research"))  # fmt: skip
    return {s.series_id: s for s in out}


def test_context_separates_a_lone_jump_from_a_shared_one():
    rows, _, _, _, crows, _ = run(openalex_family())
    c = {x["series_id"]: x for x in crows}
    t0 = c["openalex_counts|topic|T0|au|month"]
    assert t0["contextual"] and t0["observed"] > t0["expected"] and len(t0["peers"]) >= 3
    assert t0["reference"] == "openalex_counts|topic|T0|world|month"
    assert {"trend", "volume"} <= set(t0["covariates"]) <= {"trend", "peers", "reference", "volume"}
    assert set(json.loads(t0["contributions"])) == set(t0["covariates"])
    assert not c["openalex_counts|topic|T3|au|month"]["contextual"]
    s0 = c["openalex_counts|subfield|S0|au|month"]
    assert not s0["contextual"] and s0["explained_share"] > 0.5  # its peers moved alike
    r = {x["series_id"]: x for x in rows}
    if r["openalex_counts|subfield|S0|au|month"]["anomaly"]:
        assert s0["explained"]


def test_coupling_finds_a_broken_relationship():
    rng = np.random.default_rng(9)
    ms = months("2018-06", 100)  # to 2026-09
    d_world = rng.normal(0, 1, len(ms))
    d_au = np.where(np.arange(len(ms)) < len(ms) - 36, d_world + rng.normal(0, 0.2, len(ms)), rng.normal(0, 1, len(ms)))
    series = {}
    for area, d in (("AUS", d_au), ("OECD", d_world)):
        sid = f"oecd_headline|OECD.SDD:DF_CLI|{area}.M.CLI"
        series[sid] = S(
            sid,
            "oecd_headline",
            "M",
            {m: 100 + v for m, v in zip(ms, np.cumsum(d), strict=True)},
            scope=area,
            unit="index",
            dims={"REF_AREA": area, "MEASURE": "CLI"},
            family="statistics",
        )
    _, _, counts, _, crows, _ = run(series)
    au = next(c for c in crows if c["series_id"].endswith("AUS.M.CLI"))
    assert au["coupling"] == "decoupled" and au["coupling_r_early"] > 0.8 and abs(au["coupling_r_recent"]) < 0.4
    assert counts["decoupled"] == 1


def test_switches_decide_whether_new_detectors_make_candidates():
    rows, div, _, hrows, crows, _ = run(ipr_layer())
    off = detect.series_candidates(rows, div, CFG, hrows, crows)
    assert not any(set(c["detectors"]) & set(evaldetect.NEW_SERIES) for c in off)
    on = detect.series_candidates(rows, div, cfg_with(structural_shift=True, short_shift=True), hrows, crows)
    g = next(c for c in on if c["subject"].endswith("G06N"))
    assert "structural_shift" in g["detectors"] and g["numbers"]["horizons"]["profile"] == "structural_shift"
    assert g["redundancy_group"] and g["redundancy_group"] == next(
        c for c in on if c["subject"].endswith("H04L"))["redundancy_group"]  # fmt: skip
    b = next(c for c in on if c["subject"].endswith("B01B"))
    assert "short_shift" in b["detectors"]
    assert detect.corroboration(g) == 1


def test_corroboration_counts_sources_once_per_group():
    from datetime import UTC, datetime

    at = datetime(2026, 9, 1, tzinfo=UTC)
    items = [{"source": "a", "dedup_group": "g1", "observable_at": at},
             {"source": "b", "dedup_group": "g1", "observable_at": at.replace(day=2)},  # a syndicated copy
             {"source": "c", "dedup_group": "g2", "observable_at": None}]  # fmt: skip
    assert detect.corroboration({"_items": items}) == 2


def _row(window, baseline, aw, bw, ab=200, bb=200, nw=300, nb=2000):
    r = _combination("kp", "alpha", f"beta{window}", window, baseline, aw, bw, ab, bb, nw, nb, 2)
    r["baseline_sources"] = 3
    r["_exposure"] = (*r["_exposure"], 91, 730)
    return r


def test_an_established_pair_that_breaks_down_is_fading():
    rows = [_row(0, 40, 30, 30), _row(6, 40, 30, 30), _row(0, 40, 2, 30)]  # broken; as expected; one side gone
    decide_combinations(rows, CFG)
    broken, steady, gone = rows
    assert broken["fading"] and abs(broken["expected_window"] - 6.0) < 1e-9 and broken["p_fade"] < 0.01
    assert not steady["fading"] and not gone["fading"]
    assert not broken["rising"] and broken["p"] is None  # day 4's rising test keeps its own family


def test_jurisdictions_by_class(tmp_path):
    from moria.iprmetrics import COUNTRY_CLASSES
    from moria.tables import write_rows

    rows = []
    span = months("2020-10", 72)  # the baseline (60 months) and the window (12) before as_of
    window = set(span[-12:])

    def add(c, k, p, n, who=("p1", "p2")):
        rows.append({"right": "trade_mark", "scheme": "nice", "country": c, "class": k, "period": p,
                     "applications": n, "applicant_min": who[0], "applicant_max": who[1]})  # fmt: skip

    for p in span:
        w = p in window
        add("kr", "9", p, 2 if w else 0)  # Korean applicants new to class 9
        add("cn", "35", p, 0 if w else 3)  # Chinese applicants leave class 35, while filing elsewhere
        add("kr", "*", p, 5)
        add("cn", "*", p, 6)
        add("*", "9", p, 20)
        add("*", "35", p, 20)
        add("*", "*", p, 200)
    write_rows(rows, COUNTRY_CLASSES, tmp_path / "country_classes.parquet", ("period",))
    files = {"ipr": {"lake/ipr_metrics/country_classes.parquet": tmp_path / "country_classes.parquet"}}
    got = country_pairs(files, AS_OF, CFG)
    for r in got:
        r["_exposure"] = (*r["_exposure"], 12, 60)
    decide_combinations(got, CFG)
    by = {(r["a"], r["b"]): r for r in got}
    assert by[("KR", "9")]["new"] and by[("KR", "9")]["scheme"] == "nice_country"
    assert by[("CN", "35")]["fading"]


def test_planter_shapes_and_nulls():
    series = ipr_layer()
    p = evaldetect.Planter(series, CFG, AS_OF, 1)
    sid = "ip_rapid_metrics|applications_ipc|patent|A01B"
    last = p.last(series[sid])
    p.plant("spike", sid)
    assert p.out[sid].points[last] == round(series[sid].points[last] * 2)
    assert series[sid].points[last] != p.out[sid].points[last] or series[sid].points[last] == 0  # the original kept
    p.null("ip_rapid_metrics|applications_ipc|patent|B01B", flat=True)
    null = p.out["ip_rapid_metrics|applications_ipc|patent|B01B"]
    assert set(null.points) == set(series["ip_rapid_metrics|applications_ipc|patent|B01B"].points)
    assert all(v >= 0 for v in null.points.values())


def test_series_experiment_and_verdicts_run_end_to_end():
    series = {**ipr_layer(), **openalex_family()}
    cfg = CFG.model_copy(update={"evaluation": CFG.evaluation.model_copy(update={"per_class": 2})})
    res = evaldetect.series_experiment(series, cfg, AS_OF)
    assert set(res["detectors"]) == {*evaldetect.DAY4, *evaldetect.NEW_SERIES}
    assert set(res["artefacts"]) == {"volume_jump", "duplicated_period"} and res["quiet_series"] > 0
    v = evaldetect.verdicts(res, None, None, cfg)
    assert set(v) == set(evaldetect.NEW_SERIES) and all("retain" in x for x in v.values())
    text = evaldetect.report({"series": res, "backtest": None, "relationships": None, "verdicts": v}, "m.json",
                             AS_OF, cfg)  # fmt: skip
    assert "G06N" not in text and "Verdicts" in text  # aggregates only


def test_month_arithmetic_for_the_backtest():
    assert evaldetect._months_back(date(2026, 10, 14), 13) == date(2025, 9, 14)
    assert evaldetect._months_back(date(2026, 3, 31), 1) == date(2026, 2, 28)


def test_relationship_experiment_runs_on_a_minimal_layer(store):
    from .detect_fixtures import minimal_layer

    minimal_layer(store)
    cfg = CFG.model_copy(update={"evaluation": CFG.evaluation.model_copy(update={"placebo_repeats": 2})})
    rel = evaldetect.relationship_experiment(store, cfg, {}, AS_OF)
    assert len(rel["placebo"]) == 2 and {"kp", "class", "country"} <= set(rel["placebo"][0])
    assert set(rel["synthetic"]) == {"kp_fading", "class_fading", "country_fading", "country_rising"}


def test_explained_by_context_is_shown_while_the_detector_stays_off():
    cx = {
        "period": "2026-09",
        "observed": -6.7,
        "expected": -6.75,
        "expected_trend": -7.3,
        "z": 0.8,
        "change": 0.05,
        "p_holm": 1.0,
        "contributions": '{"peers":0.5,"trend":0.05}',
        "peers": ["p1", "p2"],
        "reference": "ref",
        "r2": 0.9,
        "transform": "log_share",
        "contextual": False,
        "explained": True,
        "explained_share": 0.9,
    }
    r = {"series_id": "s", "source": "openalex_counts", "family": "research", "denominator": None}
    assert not CFG.on("contextual_anomaly") and CFG.context.annotate_explained
    fired, numbers, _ = detect.boost_numbers(r, [], cx, CFG)
    assert "contextual_anomaly" not in fired and numbers["context_explains"]["share"] == 0.9
    ev = detect._series_evidence(r, cx, ["context_explains"])
    assert {(e[1], e[4]) for e in ev} >= {("ref", "reference"), ("p1", "peer"), ("p2", "peer")}
    off = CFG.model_copy(update={"context": CFG.context.model_copy(update={"annotate_explained": False})})
    assert "context_explains" not in detect.boost_numbers(r, [], cx, off)[1]
