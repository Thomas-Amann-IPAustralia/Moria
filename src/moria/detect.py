"""`moria detect --as-of D`: candidate signals (design §6.3, §8.2; day 4) from the measures of the same as_of.

A candidate is one subject (a series, an AU/world pair, a concept, a combination or a micro-cluster) with every
detector that fired on it, and its type:
- **acceleration**: the bootstrap test of the change in slope, or a change point to a steeper slope on a series that
  is itself a significant trend (design §8.2: a trend whose rate of growth is increasing);
- **trend**: significant in at least 2 of 3 windows after Holm; or a divergence between Australia and the world;
- **weak_signal**: a low-base surge, a new term, a new combination, a cross-family or cross-ring concept, or a
  micro-cluster of novel items, each with at least 3 items (one per de-duplication group) from at least 2 sources;
- **anomaly**: outside the 99% band, or a recent change in level. It triggers investigation; it is not yet a signal.

The SignalBoost detectors (D-025) join only when switched on in `config/detect.yaml` (`new_detectors`): a long-run
trend or a structural break (trend), a short-term shift, a contextual anomaly or a change in coupling (anomaly), a
fading pair (weak signal), and a jurisdiction entering, rising in or leaving a class (weak signal). Their numbers
carry the explanation (the expected value and each covariate's contribution, the horizon and its window) and their
evidence the series behind it (peers and counterpart as `peer` and `reference`). A band anomaly whose move its
context predicts carries `context_explains` in its numbers, with that context as evidence, when
`context.annotate_explained` is on (the owner, D-028): an alternative explanation for the dossier, never a filter.

**Corroboration.** Correlated evidence is not independent (D-025): one series is one line of evidence however many
windows, horizons or detectors fire on it (`corroboration` 1); flagged series that move together share a
`redundancy_group` (an AU/world pair takes its Australian series' group), and `redundancy_size` counts the
candidates in it; a document candidate's corroboration is its sources, each counted once per de-duplication group
(the source of the group's earliest item), so syndication adds nothing.

A candidate's id comes from its subject alone (`sig-` and 12 hex digits), so the same subject keeps its id across
scans and the register can follow it. Each candidate keeps its detectors' numbers (canonical JSON) and its evidence:
the series behind it, or the window items with their sources, families, rings and groups.

Writes `candidates/as_of=<D>/candidates.parquet` and `evidence.parquet`. Ranking, quotas and dossiers are day 5's.
"""

from __future__ import annotations

import json
import logging
import math
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

import pyarrow as pa

from .concepts import COMMAND as DOCS
from .config import DetectConfig
from .manifest import Manifest
from .measures import COMMAND as SERIES
from .measures import index_label, period_index_of_label
from .records import canonical_json, sha256_hex
from .store import Store
from .tables import STRS, TS, cache_root, fetch_outputs, read_rows, upload, upstream, write_rows

log = logging.getLogger("moria.detect")

COMMAND = "detect"
TYPES = ("acceleration", "trend", "weak_signal", "anomaly")  # a subject's type: the first that applies
VIEWS = {"acceleration": ["early_warning", "strategic"], "trend": ["strategic"], "weak_signal": ["early_warning"],
         "anomaly": ["early_warning"]}  # fmt: skip

CANDIDATES = pa.schema(
    [
        ("candidate_id", pa.string()),
        ("as_of", pa.date32()),
        ("type", pa.string()),
        ("subject_kind", pa.string()),  # series, pair, concept, combination, micro
        ("subject", pa.string()),
        ("label", pa.string()),
        ("detectors", STRS),
        ("numbers", pa.string()),  # canonical JSON: each detector's numbers and windows
        ("strength", pa.float64()),  # the primary detector's effect size, for ranking (day 5)
        ("direction", pa.int8()),  # +1 rising, -1 falling, 0 not directional
        ("sources", STRS),
        ("families", STRS),
        ("rings", STRS),
        ("scope", pa.string()),
        ("n_items", pa.int32()),  # de-duplication groups (documents), or 0 for series
        ("n_sources", pa.int16()),
        ("window_start", pa.string()),
        ("window_end", pa.string()),
        ("views", STRS),
        ("corroboration", pa.int16()),  # independent lines of evidence (D-025)
        ("redundancy_group", pa.string()),  # candidates whose series move together (measures' redundancy.parquet)
        ("redundancy_size", pa.int32()),  # candidates in the group (1 when alone)
    ]
)
EVIDENCE = pa.schema(
    [
        ("candidate_id", pa.string()),
        ("kind", pa.string()),  # series or item
        ("ref", pa.string()),  # a series id or an item id
        ("source", pa.string()),
        ("family", pa.string()),
        ("ring", pa.string()),
        ("dedup_group", pa.string()),
        ("observable_at", TS),
        ("role", pa.string()),  # subject, denominator, reference, peer, window, baseline
    ]
)


def corroboration(c: dict) -> int:
    """Independent lines of evidence: 1 for a series or a pair (its windows, horizons and detectors read the same
    numbers); for document evidence, the sources of its de-duplication groups, each group counted once by its
    earliest item; 1 for IP RAPID's applications (one source)."""
    items = c.get("_items") or []
    if not items:
        return 1
    first: dict[str, tuple] = {}
    for e in items:
        at = e["observable_at"]
        key = (at is None, at.timestamp() if at else 0.0, e["source"])
        if e["dedup_group"] not in first or key < first[e["dedup_group"]]:
            first[e["dedup_group"]] = key
    return len({k[2] for k in first.values()})


def candidate_id(subject: str) -> str:
    return f"sig-{sha256_hex(subject)[:12]}"


def _matching(store: Store, command: str, as_of: date) -> dict:
    m = upstream(store, command)
    if m["params"].get("as_of") != as_of.isoformat():
        raise ValueError(f"the latest {command} run is for as_of {m['params'].get('as_of')}, not {as_of}; run "
                         f"`moria {command.replace('.', ' ')} --as-of {as_of}` first")  # fmt: skip
    return m


def _r(v, n=4):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), n)


# ------------------------------------------------------------------------------------------------------- series


def boost_numbers(r: dict, hz: list[dict], cx: dict | None, cfg: DetectConfig) -> tuple[list[str], dict, dict]:
    """The SignalBoost detectors switched on that fired on a series: (detectors, numbers, extra) where extra holds
    the window, strength and direction each would give the candidate."""
    fired, numbers, extra = [], {}, {}
    short = [h for h in hz if h["method"] == "short" and h["sig"]]
    long = [h for h in hz if h["method"] == "long" and h["sig"]]
    broken = [h for h in hz if h.get("structural")]

    def hnum(h):
        return {"horizon_months": h["horizon_months"], "window": f"{h['window_start']}/{h['window_end']}",
                "effect": _r(h["effect"]), "lo": _r(h.get("lo")), "hi": _r(h.get("hi")), "z": _r(h.get("z")),
                "p_holm": _r(h.get("p_holm"), 8)}  # fmt: skip

    if cfg.on("short_shift") and short:
        fired.append("short_shift")
        numbers["short_shift"] = [hnum(h) for h in short]
        h = max(short, key=lambda h: h["horizon_months"])
        extra["short_shift"] = (h["window_start"], abs(h["effect"] or 0), h["direction"])
    if cfg.on("long_trend") and long:
        fired.append("long_trend")
        numbers["long_trend"] = [hnum(h) for h in long]
        h = max(long, key=lambda h: h["horizon_months"])
        extra["long_trend"] = (h["window_start"], abs(h["effect"] or 0), h["direction"])
    if cfg.on("structural_shift") and broken:
        fired.append("structural_shift")
        numbers["structural_shift"] = [{**hnum(h), "slope_break": h.get("break_slope_period"),
                                        "slope_change": _r(h.get("break_slope_change")),
                                        "level_break": h.get("break_level_period"),
                                        "level_change": _r(h.get("break_level_change"))} for h in broken]  # fmt: skip
        h = max(broken, key=lambda h: h["horizon_months"])
        size = abs(h.get("break_slope_change") or h.get("break_level_change") or 0)
        extra["structural_shift"] = (h.get("break_slope_period") or h.get("break_level_period"), size,
                                     h["structural_direction"])  # fmt: skip
    if any(cfg.on(d) for d in ("short_shift", "long_trend", "structural_shift")) and r.get("horizon_profile"):
        numbers["horizons"] = {"profile": r["horizon_profile"], "fired": r.get("horizons_fired") or []}
    if cx:
        cnum = {"period": cx["period"], "observed": _r(cx["observed"]), "expected": _r(cx["expected"]),
                "expected_trend": _r(cx["expected_trend"]), "z": _r(cx["z"]), "change": _r(cx["change"]),
                "p_holm": _r(cx["p_holm"], 8), "contributions": json.loads(cx["contributions"] or "{}"),
                "peers": len(cx["peers"] or []), "reference": cx["reference"], "r2": _r(cx["r2"]),
                "scale": cx["transform"]}  # fmt: skip
        if cfg.on("contextual_anomaly") and cx["contextual"]:
            fired.append("contextual_anomaly")
            numbers["contextual_anomaly"] = cnum
            extra["contextual_anomaly"] = (cx["period"], abs(cx["change"] or 0),
                                           1 if (cx["observed"] or 0) > (cx["expected"] or 0) else -1)  # fmt: skip
        elif (cfg.on("contextual_anomaly") or cfg.context.annotate_explained) and cx["explained"]:
            numbers["context_explains"] = {**cnum, "share": _r(cx["explained_share"])}
        if cfg.on("decoupling") and cx.get("coupling"):
            fired.append("decoupling")
            numbers["decoupling"] = {"change": cx["coupling"], "r_early": _r(cx["coupling_r_early"]),
                                     "r_recent": _r(cx["coupling_r_recent"]), "n_early": cx["coupling_n_early"],
                                     "n_recent": cx["coupling_n_recent"], "p_holm": _r(cx["coupling_p_holm"], 8),
                                     "since": cx["coupling_start"], "reference": cx["reference"]}  # fmt: skip
            extra["decoupling"] = (cx["coupling_start"], abs((cx["coupling_r_early"] or 0)
                                                             - (cx["coupling_r_recent"] or 0)),
                                   -1 if cx["coupling"] == "decoupled" else 1)  # fmt: skip
    return fired, numbers, extra


def series_candidates(rows: list[dict], div: list[dict], cfg: DetectConfig, horizons: list[dict] | None = None,
                      context: list[dict] | None = None) -> list[dict]:  # fmt: skip
    hz_by: dict[str, list[dict]] = defaultdict(list)
    for h in horizons or []:
        hz_by[h["series_id"]].append(h)
    cx_by = {c["series_id"]: c for c in context or []}
    groups = {r["series_id"]: r.get("redundancy_group") for r in rows}
    out = []
    for r in rows:
        fired, numbers = [], {}
        after = r.get("cp_slope_after") or 0
        steep_trend = bool(r.get("cp_steeper") and r["trend_dir"] and after * r["trend_dir"] > 0)
        if r["trend_dir"]:
            fired.append("trend")
            numbers["trend"] = {f"w{j}": {"periods": r[f"trend_w{j}_periods"], "slope": _r(r[f"trend_w{j}_slope"]),
                                          "lo": _r(r[f"trend_w{j}_lo"]), "hi": _r(r[f"trend_w{j}_hi"]),
                                          "p_holm": _r(r[f"trend_w{j}_p_holm"], 8),
                                          "q_bh": _r(r[f"trend_w{j}_q_bh"], 8), "sig": r[f"trend_w{j}_sig"]}
                                for j in (1, 2, 3)}  # fmt: skip
            numbers["trend"]["growth_per_year"] = _r(r["trend_growth"])
        if r["accel"] or steep_trend:
            fired.append("acceleration")
            numbers["acceleration"] = {"periods": r.get("accel_periods"), "early": _r(r.get("accel_early")),
                                       "recent": _r(r.get("accel_recent")), "change": _r(r.get("accel_change")),
                                       "lo": _r(r.get("accel_lo")), "hi": _r(r.get("accel_hi")),
                                       "p_holm": _r(r.get("accel_p_holm"), 8), "bootstrap": bool(r["accel"]),
                                       "change_point": r.get("cp_slope_period") if steep_trend else None,
                                       "change_point_change": _r(r.get("cp_slope_change"))}  # fmt: skip
        if r["surge"]:
            fired.append("low_base_surge")
            numbers["low_base_surge"] = {"window": r["surge_window"], "count": r["surge_count"],
                                         "baseline": r["surge_baseline"], "expected": _r(r["surge_expected"]),
                                         "ratio": _r(r["surge_ratio"]), "p_holm": _r(r["surge_p_holm"], 8)}  # fmt: skip
        if r["anomaly"] or r.get("cp_level_recent"):
            fired.append("anomaly")
            numbers["anomaly"] = {"period": r.get("anom_period"), "value": _r(r.get("anom_value")),
                                  "expected": _r(r.get("anom_expected")), "z": _r(r.get("anom_z")),
                                  "change": _r(r.get("anom_change")), "p_holm": _r(r.get("anom_p_holm"), 8),
                                  "band": bool(r["anomaly"]),
                                  "level_change_point": r.get("cp_level_period") if r.get("cp_level_recent") else None,
                                  "level_change": _r(r.get("cp_level_change"))}  # fmt: skip
        new, new_numbers, extra = boost_numbers(r, hz_by.get(r["series_id"], []), cx_by.get(r["series_id"]), cfg)
        numbers.update(new_numbers)
        shown = new + (["context_explains"] if "context_explains" in new_numbers else [])  # its context's evidence
        old = list(fired)
        fired += new
        if not fired:
            continue
        kind = ("acceleration" if "acceleration" in fired else "trend" if {"trend", "long_trend", "structural_shift"}
                & set(fired) else "weak_signal" if "low_base_surge" in fired else "anomaly")  # fmt: skip
        if not old:  # only SignalBoost detectors fired: the first of them gives the window, strength and direction
            first = next(d for d in ("structural_shift", "long_trend", "short_shift", "contextual_anomaly",
                                     "decoupling") if d in extra)  # fmt: skip
            start, strength, direction = extra[first]
            out.append({"subject_kind": "series", "subject": r["series_id"], "label": r["label"], "type": kind,
                        "detectors": fired, "numbers": numbers, "strength": strength, "direction": direction or 1,
                        "sources": [r["source"]], "families": [r["family"]] if r["family"] else [],
                        "rings": r["rings"], "scope": r["scope"], "n_items": 0, "window_start": start,
                        "window_end": r["last_period"], "redundancy_group": r.get("redundancy_group"),
                        "_evidence": _series_evidence(r, cx_by.get(r["series_id"]), shown)})  # fmt: skip
            continue
        if kind == "acceleration":
            strength, direction = (
                abs(r.get("accel_change") or r.get("cp_slope_change") or 0),
                r["trend_dir"] or (1 if (r.get("accel_recent") or 0) > 0 else -1),
            )
        elif kind == "trend":
            strength, direction = abs(r["trend_growth"] or 0), r["trend_dir"]
        elif kind == "weak_signal":
            strength, direction = math.log(max(r["surge_ratio"] or 1, 1)), 1
        else:
            strength = abs(r.get("anom_change") or r.get("cp_level_change") or 0)
            shift = r.get("anom_z") or (r.get("cp_level_after") or 0) - (r.get("cp_level_before") or 0)
            direction = 1 if shift > 0 else -1
        start = _window_start(r, kind)
        out.append({"subject_kind": "series", "subject": r["series_id"], "label": r["label"], "type": kind,
                    "detectors": fired, "numbers": numbers, "strength": strength, "direction": direction,
                    "sources": [r["source"]], "families": [r["family"]] if r["family"] else [], "rings": r["rings"],
                    "scope": r["scope"], "n_items": 0, "window_start": start, "window_end": r["last_period"],
                    "redundancy_group": r.get("redundancy_group"),
                    "_evidence": _series_evidence(r, cx_by.get(r["series_id"]), shown)})  # fmt: skip
    for d in div:
        if not d["direction"]:
            continue
        numbers = {"divergence": {f"w{j}": {"slope": _r(d[f"w{j}_slope"]), "lo": _r(d[f"w{j}_lo"]),
                                            "hi": _r(d[f"w{j}_hi"]), "p_holm": _r(d[f"w{j}_p_holm"], 8),
                                            "sig": d[f"w{j}_sig"]} for j in (1, 2, 3)}}  # fmt: skip
        numbers["divergence"].update(growth_per_year=_r(d["growth"]), au_trend=d["au_trend_dir"],
                                     reference_trend=d["ref_trend_dir"], reference=d["ref_scope"],
                                     transform=d["transform"])  # fmt: skip
        j = max(j for j in (1, 2, 3) if d[f"w{j}_sig"])
        last = period_index_of_label(d["frequency"], d["last_period"])
        start = index_label(d["frequency"], last - cfg.series.windows[d["frequency"]][j - 1] + 1) if last else None
        out.append({"subject_kind": "pair", "subject": d["pair_id"], "label": d["label"], "type": "trend",
                    "detectors": ["divergence"], "numbers": numbers, "strength": abs(d["growth"] or 0),
                    "direction": d["direction"], "sources": [d["source"]], "families": [], "rings": [],
                    "scope": f"AU vs {d['ref_scope']}", "n_items": 0, "window_start": start,
                    "window_end": d["last_period"], "redundancy_group": groups.get(d["au_series"]),
                    "_evidence": [("series", d["au_series"], d["source"], None, "subject"),
                                  ("series", d["ref_series"], d["source"], None, "reference")]})  # fmt: skip
    return out


def _series_evidence(r: dict, cx: dict | None, new: list[str]) -> list[tuple]:
    """The series behind a series candidate: itself, its denominator, and the context a contextual detector read."""
    ev = [("series", r["series_id"], r["source"], r["family"], "subject")]
    if r["denominator"]:
        ev.append(("series", r["denominator"], r["source"], r["family"], "denominator"))
    if cx and {"contextual_anomaly", "decoupling", "context_explains"} & set(new):
        if cx.get("reference"):
            ev.append(("series", cx["reference"], r["source"], r["family"], "reference"))
        if {"contextual_anomaly", "context_explains"} & set(new):
            ev += [("series", p, r["source"], r["family"], "peer") for p in cx.get("peers") or []]
    return ev


def _window_start(r: dict, kind: str) -> str | None:
    """The first period of the detector's window, from the last period and the window's length."""
    last = period_index_of_label(r["frequency"], r["last_period"])
    if last is None:
        return None
    if kind == "trend":
        j = max((j for j in (1, 2, 3) if r.get(f"trend_w{j}_sig")), default=1)
        n = r[f"trend_w{j}_periods"]
    elif kind == "acceleration":
        n = r.get("accel_periods") or r["trend_w3_periods"]
    elif kind == "weak_signal":
        return (r.get("surge_window") or "/").split("/")[0] or None
    else:
        n = 1
    return index_label(r["frequency"], last - n + 1)


# ---------------------------------------------------------------------------------------------------- documents


def document_candidates(
    concepts: list[dict],
    surges: list[dict],
    combos: list[dict],
    novelty: list[dict],
    evidence: dict[str, list[dict]],
    cfg: DetectConfig,
    as_of: date,
) -> tuple[list[dict], dict]:
    dc = cfg.documents
    out = []
    dropped: dict[str, int] = defaultdict(int)
    by_concept: dict[str, dict] = {}
    for c in concepts:
        fired, numbers = [], {}
        if c["new_term"]:
            fired.append("new_term")
            first = c["first_observable_at"]
            numbers["new_term"] = {"first_observable_at": first.isoformat() if first else None,
                                   "window_groups": c["window_groups"]}  # fmt: skip
        if c["cross_family"]:
            fired.append("cross_family")
            numbers["cross_family"] = {"window_families": c["window_families"],
                                       "baseline_families": c["baseline_families"]}  # fmt: skip
        if c["cross_ring"]:
            fired.append("cross_ring")
            numbers["cross_ring"] = {"wider_window": c["wider_window"], "wider_baseline": c["wider_baseline"],
                                     "core_window": c["core_window"], "ratio": _r(c["cross_ring_ratio"]),
                                     "p_holm": _r(c["cross_ring_p_holm"], 8)}  # fmt: skip
        by_concept[c["concept"]] = {"c": c, "fired": fired, "numbers": numbers}
    for s in surges:
        if not s.get("surge"):
            continue
        slot = by_concept.get(s["concept"])
        if slot is None:
            continue
        if "low_base_surge" not in slot["fired"]:
            slot["fired"].append("low_base_surge")
        slot["numbers"].setdefault("low_base_surge", {})[s["family"]] = {
            "window": s["window_groups"], "baseline": s["baseline_groups"], "expected": _r(s["expected"]),
            "ratio": _r(s["ratio"]), "p_holm": _r(s["p_holm"], 8)}  # fmt: skip
    for key, slot in sorted(by_concept.items()):
        if not slot["fired"]:
            continue
        c = slot["c"]
        out.append(_doc_candidate("concept", key, c["label"], slot["fired"], slot["numbers"], evidence.get(key, []),
                                  cfg, as_of))  # fmt: skip
    for r in combos:
        country = r["scheme"].endswith("_country")
        fading = bool(r.get("fading"))
        if country:
            if not cfg.on("jurisdiction_shift") or not (r["new"] or r["rising"] or fading):
                continue
            fired = ["jurisdiction_shift"]
        elif r["new"] or r["rising"]:
            fired = ["new_combination"]
        elif fading and cfg.on("fading_combination"):
            fired = ["fading_combination"]
        else:
            continue
        rising = r["new"] or r["rising"]
        numbers = {fired[0]: {"scheme": r["scheme"], "new": r["new"], "rising": r["rising"],
                              "window": r["window"], "baseline": r["baseline"], "a_baseline": r["a_baseline"],
                              "b_baseline": r["b_baseline"], "lift_ratio": _r(r["ratio"]),
                              "p_holm": _r(r["p_holm"], 8)}}  # fmt: skip
        if fading and not rising:
            numbers[fired[0]].update(fading=True, expected_window=_r(r.get("expected_window")),
                                     a_window=r.get("a_window"), b_window=r.get("b_window"),
                                     p_fade_holm=_r(r.get("p_fade_holm"), 8))  # fmt: skip
        label = f"{r['a']} + {r['b']}"
        direction = 1 if rising else -1
        if r["scheme"] == "kp":
            c = _doc_candidate("combination", r["combination"], label, fired, numbers,
                               evidence.get(r["combination"], []), cfg, as_of)  # fmt: skip
            c["direction"] = direction
            if not rising:
                c["strength"] = -math.log(max(r["ratio"] or 0.01, 0.01))
            out.append(c)
        else:  # IP RAPID applications: no items in the lake; at least 3 applications from at least 2 applicants
            size, applicants = (
                (r["window"], r["window_sources"]) if rising else (r["baseline"], r.get("baseline_sources") or 0)
            )
            if size < dc.min_items or applicants < dc.min_sources:
                dropped["weak_signal_minimum"] += 1
                continue
            strength = (math.log(max(r["ratio"] or 2.0, 1.0) + 1) if rising
                        else -math.log(max(r["ratio"] or 0.01, 0.01)))  # fmt: skip
            name = (f"Applicants from {r['a']} in {r['scheme'].split('_')[0].upper()} {r['b']}" if country
                    else f"{r['scheme'].upper()} {label}")  # fmt: skip
            out.append({"subject_kind": "combination", "subject": r["combination"], "label": name,
                        "type": "weak_signal", "detectors": fired, "numbers": numbers, "strength": strength,
                        "direction": direction, "sources": ["ip_rapid"], "families": ["patent"], "rings": ["core"],
                        "scope": "AUS", "n_items": int(size), "window_start": None,
                        "window_end": as_of.isoformat(), "_evidence": [], "_items": [],
                        "_checked": True})  # fmt: skip
    for n in novelty:
        out.append(_doc_candidate("micro", n["micro"], n["label"], ["novel_items"],
                                  {"novel_items": {"family": n["family"], "items": n["items"], "groups": n["groups"],
                                                   "mean_score": _r(n["mean_score"]),
                                                   "baseline_size": n["baseline_size"]}},
                                  evidence.get(n["micro"], []), cfg, as_of))  # fmt: skip
    kept = []
    for c in out:
        if not c.pop("_checked", False) and (c["n_items"] < dc.min_items or c["n_sources"] < dc.min_sources):
            dropped["weak_signal_minimum"] += 1
            continue
        kept.append(c)
    return kept, dict(dropped)


def _doc_candidate(kind: str, key: str, label: str, fired: list[str], numbers: dict, ev: list[dict],
                   cfg: DetectConfig, as_of: date) -> dict:  # fmt: skip
    groups = {e["dedup_group"] for e in ev}
    dates = [e["observable_at"] for e in ev]
    strength = float(len(groups))
    if "low_base_surge" in numbers:
        ratios = [v["ratio"] or 1 for v in numbers["low_base_surge"].values()]
        strength = math.log(max(max(ratios), 1)) + len(groups) / 100
    return {"subject_kind": kind, "subject": key, "label": label, "type": "weak_signal", "detectors": fired,
            "numbers": numbers, "strength": strength, "direction": 1,
            "sources": sorted({e["source"] for e in ev}), "families": sorted({e["family"] for e in ev}),
            "rings": sorted({e["ring"] for e in ev}), "scope": None, "n_items": len(groups),
            "n_sources": len({e["source"] for e in ev}),
            "window_start": min(dates).date().isoformat() if dates else None,
            "window_end": as_of.isoformat(),
            "_evidence": [], "_items": ev}  # fmt: skip


# ------------------------------------------------------------------------------------------------------------ run


def detect(store: Store, cfg: DetectConfig, as_of: date, config_hash: str | None = None) -> tuple[str, str, dict]:
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        sm, dm = _matching(store, SERIES, as_of), _matching(store, DOCS, as_of)
        manifest.params = {"as_of": as_of.isoformat(), "series_run": sm["run_id"], "documents_run": dm["run_id"]}
        sp = {k.rsplit("/", 1)[1]: p for k, p in fetch_outputs(store, sm, "measures/series/", cache_root()).items()}
        dp = {k.rsplit("/", 1)[1]: p for k, p in fetch_outputs(store, dm, "measures/documents/", cache_root()).items()}
        cands, evidence, counts = build(sp, dp, cfg, as_of)
        prefix = f"candidates/as_of={as_of.isoformat()}/"
        with tempfile.TemporaryDirectory(prefix="moria-detect-") as tmp:
            write_rows(cands, CANDIDATES, Path(tmp) / "candidates.parquet", ("candidate_id",))
            write_rows(evidence, EVIDENCE, Path(tmp) / "evidence.parquet", ("candidate_id", "kind", "ref"))
            for name in ("candidates", "evidence"):
                upload(store, manifest, f"{prefix}{name}.parquet", Path(tmp) / f"{name}.parquet")
        manifest.counts = counts
        return "passed", manifest.finish(store, "passed"), counts
    except Exception as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        cause = f"{COMMAND}: {type(e).__name__}: {first[:300]}"
        log.error("%s", cause)
        return "failed", manifest.finish(store, "failed", cause), {"error": cause}


def build(sp: dict[str, Path], dp: dict[str, Path], cfg: DetectConfig, as_of: date) -> tuple[list, list, dict]:
    rows = read_rows(sp["measures.parquet"])
    div = read_rows(sp["divergence.parquet"])
    horizons = read_rows(sp["horizons.parquet"]) if "horizons.parquet" in sp else []
    context = read_rows(sp["context.parquet"]) if "context.parquet" in sp else []
    ev_rows: dict[str, list[dict]] = defaultdict(list)
    for e in read_rows(dp["evidence.parquet"]):
        ev_rows[e["key"]].append(e)
    docs, dropped = document_candidates(read_rows(dp["concepts.parquet"]), read_rows(dp["surges.parquet"]),
                                        read_rows(dp["combinations.parquet"]), read_rows(dp["novelty.parquet"]),
                                        ev_rows, cfg, as_of)  # fmt: skip
    cands, evidence = [], []
    for c in series_candidates(rows, div, cfg, horizons, context) + docs:
        cid = candidate_id(c["subject"])
        c["corroboration"] = corroboration(c)
        for kind, ref, source, family, role in c.pop("_evidence"):
            evidence.append({"candidate_id": cid, "kind": kind, "ref": ref, "source": source, "family": family,
                             "ring": None, "dedup_group": None, "observable_at": None, "role": role})  # fmt: skip
        for e in c.pop("_items", []) or []:
            evidence.append({"candidate_id": cid, "kind": "item", "ref": e["item_id"], "source": e["source"],
                             "family": e["family"], "ring": e["ring"], "dedup_group": e["dedup_group"],
                             "observable_at": e["observable_at"], "role": e.get("role") or "window"})  # fmt: skip
        c.setdefault("n_sources", len(c["sources"]))
        c.update(candidate_id=cid, as_of=as_of, numbers=canonical_json(c["numbers"]), views=VIEWS[c["type"]])
        cands.append(c)
    sizes: dict[str, int] = defaultdict(int)
    for c in cands:
        c.setdefault("redundancy_group", None)
        if c["redundancy_group"]:
            sizes[c["redundancy_group"]] += 1
    for c in cands:
        c["redundancy_size"] = sizes[c["redundancy_group"]] if c["redundancy_group"] else 1
    counts: dict[str, int] = defaultdict(int)
    for c in cands:
        counts[f"type_{c['type']}"] += 1
        for d in c["detectors"]:
            counts[f"detector_{d}"] += 1
    counts["candidates"] = len(cands)
    counts["redundancy_groups"] = len(sizes)
    counts["redundant_candidates"] = sum(n - 1 for n in sizes.values())
    counts["evidence_rows"] = len(evidence)
    for k, v in dropped.items():
        counts[f"dropped_{k}"] = v
    return cands, evidence, dict(sorted(counts.items()))
