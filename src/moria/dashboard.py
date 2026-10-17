"""`moria dashboard --as-of D`: the data behind the dashboard (`dashboard/index.html`, D-030), so that people can
explore a scan and its review queue, see the evidence behind each candidate, and learn how Moria reached it.

Two bundles from one read of the scan's and the review's outputs, by the rules the reports already follow:
- **public** (`dashboard/data/public.json` in the repo, served by GitHub Pages): aggregates only, like `reports/`:
  counts by type, detector, source, ring and check, histograms of scores and p-values, the queue's quotas and
  sensitivity, the documents' volumes, the ingestion days, the evaluations' results, the scans' history, and the
  public parts of the config (source cards, territories, known trends, settings). No labels, titles, keyphrases,
  URLs or candidate ids.
- **private** (`interpretation/dashboard/as_of=<D>/dashboard.json.gz` in the private bucket; `--out` also writes it
  to the analyst's own disk, never the repo): every candidate with its label, numbers, components and checks; the
  series behind each series candidate as Moria tested them, with its trend fits and their intervals, its anomaly
  band, its acceleration and change points; the window items behind each document candidate (titles and links);
  the dossiers, the decision model's suggestions and the register's state. The dashboard reads it in the browser:
  nothing is uploaded, and nothing reads it back.

Neither bundle changes anything Moria computed. Values are copied from the stages' outputs; the fits' intercepts and
the anomaly bands, which the measures don't store, are recomputed with the detectors' own functions on the same
matrices (`measures.build_group`, `stats.theil_sen`) and checked against the stored slopes and z-scores; a fit that
doesn't match is left out and counted (`fit_mismatch`).
"""

from __future__ import annotations

import gzip
import json
import logging
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import duckdb
import numpy as np

from . import stats
from .artefacts import CHECKS
from .artefacts import COMMAND as ARTEFACTS
from .concepts import COMMAND as DOCS
from .config import REPO_ROOT, BaselineFile, DetectConfig, ReviewConfig, SourceCard, TerritoriesFile
from .detect import COMMAND as DETECT
from .detect import TYPES, _matching
from .dossier import COMMAND as DOSSIER
from .dossier import load_dossiers
from .manifest import Manifest
from .measures import COMMAND as SERIES
from .measures import Series, aligned, build_group, index_label, load_series, synthetic_totals
from .monitor import COMMAND as MONITOR
from .pathways import COMMAND as PATHWAYS
from .pathways import EVAL as EVAL_PATHWAYS
from .queue import COMMAND as QUEUE
from .queue import dossier_flags
from .rank import COMMAND as RANK
from .rank import VIEWS, failed, files_of, largest_remainder, manifest_of
from .records import canonical_json, sha256_hex
from .register import events, state
from .store import Store
from .tables import cache_root, fetch_outputs, latest_manifest, read_rows

log = logging.getLogger("moria.dashboard")

COMMAND = "dashboard"
SCHEMA = 1
PUBLIC_PATH = "dashboard/data/public.json"
PATHWAY_IDS = ("P1", "P2", "P3", "P4", "P5", "P6")
Z99 = 2.5758  # the two-sided 99% normal quantile: the anomaly band before any adjustment for many tests


def private_key(as_of: date) -> str:
    return f"interpretation/dashboard/as_of={as_of.isoformat()}/dashboard.json.gz"


def _r(v, digits: int = 6):
    """A float to `digits` significant figures (None for missing or non-finite values); other values unchanged."""
    if v is None:
        return None
    if isinstance(v, bool | int | str):
        return v
    v = float(v)
    if not math.isfinite(v):
        return None
    return float(f"{v:.{digits}g}")


def _hist(values: list[float | None], lo: float, hi: float, bins: int) -> list[int]:
    out = [0] * bins
    width = (hi - lo) / bins
    for v in values:
        if v is None or not math.isfinite(v):
            continue
        out[min(bins - 1, max(0, int((v - lo) / width)))] += 1
    return out


def _counter(items) -> dict[str, int]:
    return dict(sorted(Counter(items).items()))


def _run_ref(m: dict | None) -> dict | None:
    if not m:
        return None
    git = m.get("git") or {}
    return {"run_id": m["run_id"], "commit": (git.get("commit") or "")[:7], "dirty": git.get("dirty")}


# ------------------------------------------------------------------------------------------------------- inputs


class Inputs:
    """One scan and its review, read once: the manifests, the tables, the dossiers and the register."""

    def __init__(self, store: Store, as_of: date):
        self.store, self.as_of = store, as_of
        self.rank_m = _matching(store, RANK, as_of)
        self.queue_m = _matching(store, QUEUE, as_of)
        if self.queue_m["params"].get("rank_run") != self.rank_m["run_id"]:
            raise ValueError(f"the queue of {as_of} is for an older ranking; run `moria review --as-of {as_of}`")
        p = self.rank_m["params"]
        self.pathways_m = manifest_of(store, PATHWAYS, self.queue_m["params"]["pathways_run"])
        self.dossier_m = manifest_of(store, DOSSIER, self.queue_m["params"]["dossier_run"])
        self.detect_m = manifest_of(store, DETECT, p["detect_run"])
        self.artefacts_m = manifest_of(store, ARTEFACTS, p["artefacts_run"])
        self.series_m = manifest_of(store, SERIES, p["series_run"])
        self.docs_m = manifest_of(store, DOCS, p["documents_run"])
        self.monitor_m = latest_manifest(store, MONITOR)
        if not self.monitor_m or self.monitor_m["status"] != "passed" or \
                self.monitor_m["params"].get("as_of") != as_of.isoformat():  # fmt: skip
            self.monitor_m = None
        rf, qf = files_of(store, self.rank_m, "review/"), files_of(store, self.queue_m, "review/")
        self.ranked = read_rows(rf["ranked.parquet"])
        self.queue = read_rows(qf["queue.parquet"])
        self.sensitivity = read_rows(qf["sensitivity.parquet"])
        self.suggestions = read_rows(files_of(store, self.pathways_m, "interpretation/pathways/")["pathways.parquet"])
        cf = {**files_of(store, self.detect_m, "candidates/"), **files_of(store, self.artefacts_m, "candidates/")}
        self.candidates = {c["candidate_id"]: c for c in read_rows(cf["candidates.parquet"])}
        self.evidence: dict[str, list[dict]] = defaultdict(list)
        for e in read_rows(cf["evidence.parquet"]):
            self.evidence[e["candidate_id"]].append(e)
        self.artefacts = {a["candidate_id"]: a for a in read_rows(cf["artefacts.parquet"])}
        self.measure_files = files_of(store, self.series_m, "measures/series/")
        self.doc_files = files_of(store, self.docs_m, "measures/documents/")
        self.measures = read_rows(self.measure_files["measures.parquet"])
        self.volumes = read_rows(self.doc_files["volumes.parquet"]) if "volumes.parquet" in self.doc_files else []
        self.days, self.incidents = [], []
        if self.monitor_m:
            mf = files_of(store, self.monitor_m, "monitors/summary/")
            self.days = read_rows(mf["days.parquet"]) if "days.parquet" in mf else []
            self.incidents = read_rows(mf["incidents.parquet"]) if "incidents.parquet" in mf else []
        self.events = events(store)
        self.register = state(self.events)
        # the shortlist's dossier checks that the queue may weigh (queue.dossier_penalty, D-032)
        self.dossier_flags = dossier_flags(store, self.queue_m["params"]["dossier_run"])

    def runs(self) -> dict[str, dict | None]:
        return {c: _run_ref(m) for c, m in (
            (RANK, self.rank_m), (QUEUE, self.queue_m), (PATHWAYS, self.pathways_m), (DOSSIER, self.dossier_m),
            (DETECT, self.detect_m), (ARTEFACTS, self.artefacts_m), (SERIES, self.series_m), (DOCS, self.docs_m),
            (MONITOR, self.monitor_m))}  # fmt: skip


# ------------------------------------------------------------------------------------------------- the public


def _origin(c: dict) -> str:
    """Where a candidate came from, coarsely: a series source, IP RAPID's class pairs, or the documents."""
    if c["subject_kind"] in ("series", "pair"):
        return (c["sources"] or ["unknown"])[0]
    return "ip_rapid (class pairs)" if c["sources"] == ["ip_rapid"] else "documents"


def scan_part(inp: Inputs, cfg: DetectConfig) -> dict:
    cands, arts = list(inp.candidates.values()), inp.artefacts
    types = {}
    for t in TYPES:
        cs = [c for c in cands if c["type"] == t]
        flags = Counter(f for c in cs for f in arts[c["candidate_id"]]["flags"])
        types[t] = {"candidates": len(cs), "clean": sum(1 for c in cs if arts[c["candidate_id"]]["clean"]),
                    "flags": {k: flags.get(k, 0) for k in CHECKS}}  # fmt: skip
    det = Counter(d for c in cands for d in c["detectors"])
    det_clean = Counter(d for c in cands if arts[c["candidate_id"]]["clean"] for d in c["detectors"])
    det_type: dict[str, Counter] = defaultdict(Counter)
    for c in cands:
        for d in c["detectors"]:
            det_type[d][c["type"]] += 1
    detectors = [{"detector": d, "candidates": n, "clean": det_clean.get(d, 0), "types": dict(det_type[d])}
                 for d, n in sorted(det.items(), key=lambda kv: (-kv[1], kv[0]))]  # fmt: skip
    origins: dict[str, Counter] = defaultdict(Counter)
    for c in cands:
        o = origins[_origin(c)]
        o[c["type"]] += 1
        o["clean"] += arts[c["candidate_id"]]["clean"]
    rings: dict[str, Counter] = defaultdict(Counter)
    for c in cands:
        rings[" + ".join(c["rings"]) or "(none)"][c["type"]] += 1
    # the series tested, by source and frequency (as the scan report counts them)
    agg: dict[tuple, Counter] = defaultdict(Counter)
    for r in inp.measures:
        a = agg[(r["source"], r["frequency"])]
        a["series"] += 1
        a["testable"] += (r["trend_windows"] or 0) >= 2
        a["trends"] += bool(r["trend_dir"])
        a["accelerations"] += bool(r["accel"])
        a["anomalies"] += bool(r["anomaly"])
        a["level_changes"] += bool(r["cp_level_recent"])
        a["surges"] += bool(r["surge"])
    tested = [{"source": s, "frequency": f, **dict(a)} for (s, f), a in sorted(agg.items())]
    # multiple testing: trend windows' raw p, Benjamini-Hochberg's q and Holm's p, and their histograms
    windows = []
    for j in (1, 2, 3):
        raw = [r[f"trend_w{j}_p"] for r in inp.measures]
        holm = [r[f"trend_w{j}_p_holm"] for r in inp.measures]
        bh = [r[f"trend_w{j}_q_bh"] for r in inp.measures]
        windows.append({
            "window": f"w{j}", "tested": sum(1 for p in raw if p is not None),
            "raw_05": sum(1 for p in raw if p is not None and p < 0.05),
            "bh_05": sum(1 for q in bh if q is not None and q < 0.05),
            "holm_05": sum(1 for p in holm if p is not None and p < 0.05),
            "hist_raw": _hist(raw, 0, 1, 20), "hist_holm": _hist(holm, 0, 1, 20),
            "hist_raw_fine": _hist([p for p in raw if p is not None and p < 0.05], 0, 0.05, 10),
        })  # fmt: skip
    sm, dmc, detc = inp.series_m["counts"], inp.docs_m["counts"], inp.detect_m["counts"]
    return {
        "candidates": len(cands), "clean": sum(1 for c in cands if arts[c["candidate_id"]]["clean"]),
        "types": types, "detectors": detectors,
        "origins": [{"origin": k, **dict(v)} for k, v in sorted(origins.items())],
        "rings": [{"rings": k, **dict(v)} for k, v in sorted(rings.items())],
        "subject_kinds": _counter(c["subject_kind"] for c in cands),
        "series_tested": tested,
        "multiple_testing": {"series": sm.get("series", len(inp.measures)), "trends_holm": sm.get("trends", 0),
                             "trends_bh": sm.get("trends_bh", 0), "pairs": sm.get("divergence_pairs", 0),
                             "diverging": sm.get("divergences", 0), "windows": windows},
        "signalboost": {k: sm.get(k, 0) for k in (
            "horizon_short_tested", "horizon_short_sig", "horizon_medium_tested", "horizon_medium_sig",
            "horizon_long_tested", "horizon_long_sig", "horizon_structural", "context_modelled", "contextual",
            "anomaly", "context_explained", "coupling_tested", "decoupled", "coupled", "redundancy_flagged",
            "redundancy_groups")} | {k: dmc.get(k, 0) for k in (
            "combinations_fading", "jurisdiction_new", "jurisdiction_rising", "jurisdiction_fading")} | {
            "candidate_redundancy_groups": detc.get("redundancy_groups", 0),
            "redundant_candidates": detc.get("redundant_candidates", 0)},
        "new_detectors": dict(sorted(cfg.new_detectors.items())),
    }  # fmt: skip


def ranking_part(inp: Inputs) -> dict:
    queued = {q["candidate_id"] for q in inp.queue}
    rows = inp.ranked
    out: dict = {"histograms": {}, "bins": 40}
    for v in VIEWS:
        key = f"score_{v}"
        out["histograms"][v] = {
            "all": _hist([r[key] for r in rows], 0, 1, 40),
            "shortlist": _hist([r[key] for r in rows if r["shortlisted"]], 0, 1, 40),
            "queue": _hist([r[key] for r in rows if r["candidate_id"] in queued], 0, 1, 40),
            "in_view": sum(1 for r in rows if r[key] is not None),
        }
    out["components"] = {
        "strength_pct": _hist([r["strength_pct"] for r in rows], 0, 1, 20),
        "breadth": _hist([r["breadth"] for r in rows], 0, 1, 20),
        "lead": _counter(f"{r['lead']:.2f}" for r in rows),
        "novelty": _counter(f"{r['novelty']:.2f}" for r in rows),
    }
    out["factors"] = {
        k: _counter(f"{r[k]:.3g}" for r in rows)
        for k in ("scope_factor", "type_factor", "flag_factor", "context_factor")
    }
    out["ring_basis"] = _counter(r["ring_basis"] for r in rows)
    out["rings"] = _counter(r["ring"] for r in rows)
    out["known_trend_match"] = sum(1 for r in rows if r["known_trend_match"])
    flow: Counter = Counter()
    for r in rows:
        c = inp.candidates[r["candidate_id"]]
        stage = "queue" if r["candidate_id"] in queued else "shortlist" if r["shortlisted"] else "not shortlisted"
        flow[(_origin(c), r["type"], stage)] += 1
    out["flow"] = [{"origin": o, "type": t, "stage": s, "n": n} for (o, t, s), n in sorted(flow.items())]
    return out


def queue_part(inp: Inputs, cfg: ReviewConfig) -> dict:
    short = [r for r in inp.ranked if r["shortlisted"]]
    q = inp.queue
    caps = largest_remainder(cfg.queue.size, cfg.queue.rings)
    rings = Counter(r["ring"] for r in q)
    checks = {k.removeprefix("check_"): v for k, v in sorted((inp.dossier_m.get("counts") or {}).items())
              if k.startswith("check_")}  # fmt: skip
    dc = inp.dossier_m.get("counts") or {}
    sug = inp.suggestions
    ps = [json.loads(s["pathways"]) for s in sug if s["pathways"]]
    pathways = {}
    for pid in PATHWAY_IDS:
        vals = sorted(p[pid] for p in ps if p.get(pid) is not None)
        if vals:
            n = len(vals)
            pathways[pid] = {"hist": _hist(vals, 0, 1, 50), "min": _r(vals[0], 4), "q1": _r(vals[n // 4], 4),
                             "median": _r(vals[n // 2], 4), "q3": _r(vals[(3 * n) // 4], 4),
                             "max": _r(vals[-1], 4)}  # fmt: skip
    answers = {name: _counter(s[f"{name}_top"] for s in sug if s.get(f"{name}_top"))
               for name in ("pathway", "order", "origin", "horizon", "stance", "impact")}  # fmt: skip
    ev = latest_manifest(inp.store, EVAL_PATHWAYS)
    evaluation = None
    if ev and ev["status"] == "passed" and ev["params"].get("as_of") == inp.as_of.isoformat():
        r = ev["params"]["result"]
        evaluation = {"run_id": ev["run_id"], "separation": r["separation"], "spread": r["spread"],
                      "rule": r["rule"], "passes": r["passes"], "relevant": r.get("relevant"),
                      "irrelevant": r.get("irrelevant"), "pathway_iqr": r.get("pathway_iqr"),
                      "sample": ev["params"].get("sample")}  # fmt: skip
    regs = [s for s in inp.register.values() if not s["signal_id"].startswith("miss-")]
    return {
        "size": len(q), "shortlist_size": len(short),
        "types": _counter(r["type"] for r in q), "rings": _counter(r["ring"] for r in q),
        "sources": _counter(r["source"] for r in q), "views": _counter(r["view"] for r in q),
        "passes": _counter(str(r["pass"]) for r in q), "flagged": sum(1 for r in q if r["flags"]),
        "flags": _counter(f for r in q for f in r["flags"]),
        "quotas": {ring: {"cap": caps[ring], "filled": rings.get(ring, 0)} for ring in caps},
        "shortlist": {"types": _counter(r["type"] for r in short), "rings": _counter(r["ring"] for r in short),
                      "sources": _counter(r["source"] for r in short), "views": _counter(r["shortlist_view"]
                                                                                          for r in short)},
        "sensitivity": [{k: s[k] for k in ("view", "component", "factor", "overlap", "size")}
                        for s in inp.sensitivity],
        "checks": checks,
        "openalex_samples": {"fetched": dc.get("openalex_samples_ok", 0), "concentrated": dc.get(
            "openalex_concentrated", 0), "calls": dc.get("openalex_calls", 0)},
        "dossiers": {k: dc.get(k, 0) for k in ("dossiers", "with_chart", "with_counter_evidence", "with_related")},
        "pathways": {"author": inp.pathways_m["params"].get("author"),
                     "questions": inp.pathways_m["params"].get("questions"),
                     "use_in_ranking": cfg.pathways.use_in_ranking, "answers": answers, "probabilities": pathways,
                     "evaluation": evaluation},
        "register": {"events": _counter(e["kind"] for e in inp.events), "status": _counter(s["status"] for s in regs),
                     "reviewed": sum(1 for s in regs if s["review"])},
    }  # fmt: skip


def documents_part(inp: Inputs, cfg: DetectConfig) -> dict:
    dm = inp.docs_m["counts"]
    return {
        "window_days": cfg.documents.window_days, "baseline_days": cfg.documents.baseline_days,
        "items_window": dm.get("items_window", 0), "items_baseline": dm.get("items_baseline", 0),
        "undated": dm.get("backlog_items", 0), "min_items": cfg.documents.min_items,
        "min_sources": cfg.documents.min_sources,
        "indicators": {k: dm.get(k, 0) for k in ("new_term", "cross_family", "cross_ring", "low_base_surge",
                                                  "combinations_new", "combinations_rising", "novel_micro_clusters",
                                                  "concepts", "clusters")},
        "sources": [{"source": v["source"], "family": v["family"],
                     "onboarded": v["onboarded_at"].date().isoformat() if v["onboarded_at"] else None,
                     "history_from": v["coverage_start"].year if v["coverage_start"] else None,
                     "window_groups": v["window_groups"], "baseline_groups": v["baseline_groups"],
                     "window_per_day": _r(v["window_per_day"], 4), "baseline_per_day": _r(v["baseline_per_day"], 4),
                     "change": _r(v["change"], 4)} for v in inp.volumes],
    }  # fmt: skip


def ingestion_part(inp: Inputs) -> dict:
    return {
        "days": [{"source": d["source"], "day": d["day"].isoformat(), "cadence": d["cadence"], "runs": d["runs"],
                  "failed": d["failed"], "records": d["records"], "flag": d["flag"]}
                 for d in sorted(inp.days, key=lambda d: (d["source"], d["day"]))],
        "incidents": [{"source": i["source"], "day": i["day"].isoformat(), "kind": i["kind"]}
                      for i in sorted(inp.incidents, key=lambda i: (i["source"], i["day"], i["kind"]))],
    }  # fmt: skip


def evals_part(store: Store, as_of: date) -> dict:
    out: dict = {}
    m = latest_manifest(store, "eval.artefacts")
    if m and m["status"] == "passed":
        seeds = m["params"].get("seeds") or []
        out["artefacts"] = {
            "run_id": m["run_id"],
            "as_of": m["params"].get("as_of"),
            "seeds": [
                {"seed": s["seed"], "check": s["flag"], "caught": s["caught"], "control_ok": s["control_ok"]}
                for s in seeds
            ],
            "caught": m["counts"].get("caught"),
            "controls_ok": m["counts"].get("controls_ok"),
        }
    m = latest_manifest(store, "eval.detectors")
    if m and m["status"] == "passed":
        v = (m["params"].get("result") or {}).get("verdicts") or {}
        out["detectors"] = {"run_id": m["run_id"], "as_of": m["params"].get("as_of"), "verdicts": [
            {"detector": d, "recall": _r(x.get("recall"), 4), "incremental": _r(x.get("incremental"), 4),
             "null_rate": _r(x.get("null_rate"), 4), "null_reference": _r(x.get("null_reference"), 4),
             "artefact_excess": _r(x.get("artefact_excess"), 4), "retain": bool(x.get("retain")),
             "failed": sorted(k for k, ok in (x.get("checks") or {}).items() if not ok)}
            for d, x in sorted(v.items())]}  # fmt: skip
    m = latest_manifest(store, "eval.hindsight")
    if m and m["status"] == "passed":
        r = m["params"].get("result") or {}
        out["hindsight"] = {"run_id": m["run_id"], "median_lead_months": r.get("median_lead_months"),
                            "recovery": r.get("recovery"), "queued_share": r.get("queued_share"),
                            "developments": [{k: d.get(k) for k in ("id", "name", "mainstream", "first_raised",
                                                                     "lead_months", "recovered", "queued", "miss")}
                                             for d in r.get("developments") or []]}  # fmt: skip
    return out


def history_part(store: Store) -> list[dict]:
    """Per scan (the latest passed run of each as_of): candidates by type, clean, shortlist and queue, from the
    manifests' counts."""

    def latest(command: str) -> dict[str, dict]:
        by: dict[str, dict] = {}
        for k in store.list(f"manifests/{command}/"):
            m = json.loads(store.get(k))
            day = (m.get("params") or {}).get("as_of")
            if m["status"] == "passed" and day and (day not in by or (m.get("started_ns") or 0) >
                                                     (by[day].get("started_ns") or 0)):  # fmt: skip
                by[day] = m
        return by

    det, art, rnk, que = latest(DETECT), latest(ARTEFACTS), latest(RANK), latest(QUEUE)
    out = []
    for day in sorted(det):
        c = det[day]["counts"]
        row = {"as_of": day, "candidates": c.get("candidates", 0),
               "types": {t: c.get(f"type_{t}", 0) for t in TYPES}}  # fmt: skip
        if day in art:
            row["clean"] = art[day]["counts"].get("clean")
        if day in rnk:
            row["shortlist"] = rnk[day]["counts"].get("shortlisted")
        if day in que:
            row["queue"] = que[day]["counts"].get("queue")
        out.append(row)
    return out


def config_part(review: ReviewConfig, detect_cfg: DetectConfig, cards: dict[str, SourceCard],
                territories: TerritoriesFile, baseline: BaselineFile) -> dict:  # fmt: skip
    rc, qc, sc, dc = review.rank, review.queue, detect_cfg.series, detect_cfg.documents
    return {
        "sources": [{"id": c.id, "name": c.name, "adapter": c.adapter, "family": c.family, "rings": list(c.rings),
                     "cadence": c.cadence, "coverage": c.coverage, "history_start": c.history_start,
                     "publication_lag": c.publication_lag, "licence": c.licence, "snapshot_rights": c.snapshot_rights,
                     "known_biases": list(c.known_biases), "breaks": list(c.breaks)}
                    for c in sorted(cards.values(), key=lambda c: c.id)],
        "territories": [{"id": t.id, "name": t.name, "aim": t.aim, "description": t.description,
                         "pathways": list(t.pathways)} for t in territories.territories],
        "known_trends": [{"id": t.id, "name": t.name, "statement": t.statement, "pestle": list(t.pestle),
                          "rings": list(t.rings), "status": t.status} for t in baseline.trends],
        "pathways": dict(review.pathways.statements),
        "rank": {"shortlist": rc.shortlist, "floor": rc.floor, "weights": rc.weights, "type_weight": rc.type_weight,
                 # the weights' configured order: the geometric mean sums in it, so the what-if matches exactly
                 "weights_order": {v: list(ws) for v, ws in rc.weights.items()},
                 "context_explained": rc.context_explained, "flag_penalty": rc.flag_penalty,
                 "scope": rc.scope.model_dump(), "lead": rc.lead, "novelty": rc.novelty,
                 "known_trend_sim": rc.known_trend_sim, "known_trend_factor": rc.known_trend_factor},
        "queue": {"size": qc.size, "views": qc.views, "rings": qc.rings, "third_order_max": qc.third_order_max,
                  "source_max": qc.source_max, "sensitivity": qc.sensitivity,
                  "dossier_penalty": qc.dossier_penalty},
        "detect": {"alpha": sc.alpha, "trend_min_windows": sc.trend_min_windows, "windows": sc.windows,
                   "min_coverage": sc.min_coverage, "min_mean_count": sc.min_mean_count,
                   "anomaly_alpha": sc.anomaly_alpha, "anomaly_min_change": sc.anomaly_min_change,
                   "accel_min_change": sc.accel_min_change, "anomaly_baseline": sc.anomaly_baseline,
                   "surge": sc.surge.model_dump(), "documents": {"window_days": dc.window_days,
                   "baseline_days": dc.baseline_days, "min_items": dc.min_items, "min_sources": dc.min_sources}},
        "use_in_ranking": review.pathways.use_in_ranking,
    }  # fmt: skip


def public_bundle(inp: Inputs, review: ReviewConfig, detect_cfg: DetectConfig, cards: dict[str, SourceCard],
                  territories: TerritoriesFile, baseline: BaselineFile) -> dict:  # fmt: skip
    nm = manifest_of(inp.store, "normalise", inp.series_m["params"]["normalise_run"])
    norm = {s: v.get("counts") or {} for s, v in (nm["params"].get("sources") or {}).items()}
    regs = [s for s in inp.register.values() if not s["signal_id"].startswith("miss-")]
    funnel = {
        "sources": len(cards), "documents": sum(c.get("documents", 0) for c in norm.values()),
        "series": inp.series_m["counts"].get("series", len(inp.measures)),
        "candidates": len(inp.ranked), "clean": sum(1 for a in inp.artefacts.values() if a["clean"]),
        "shortlist": sum(1 for r in inp.ranked if r["shortlisted"]), "queue": len(inp.queue),
        "reviewed": sum(1 for s in regs if s["review"]),
    }  # fmt: skip
    return {
        "schema": SCHEMA, "kind": "public", "as_of": inp.as_of.isoformat(), "runs": inp.runs(), "funnel": funnel,
        "scan": scan_part(inp, detect_cfg), "ranking": ranking_part(inp), "queue": queue_part(inp, review),
        "documents": documents_part(inp, detect_cfg), "ingestion": ingestion_part(inp),
        "evals": evals_part(inp.store, inp.as_of), "history": history_part(inp.store),
        "config": config_part(review, detect_cfg, cards, territories, baseline),
    }  # fmt: skip


# ------------------------------------------------------------------------------------------------ the private


def load_scan_series(store: Store, cfg: DetectConfig, series_m: dict, measure_ids: set[str], as_of: date,
                     wanted: set[str]) -> dict[str, Series]:  # fmt: skip
    """The series a scan tested, at its date, as the dossier's Layer.series reads them (with their denominators;
    a synthetic total needs every series of its source)."""
    pairs = []
    nm = manifest_of(store, "normalise", series_m["params"]["normalise_run"])
    files = fetch_outputs(store, nm, "lake/", cache_root())
    for src in sorted(set(cfg.series.sources) - {"ip_rapid_metrics"}):
        s, o = f"lake/series/source={src}/series.parquet", f"lake/observations/source={src}/observations.parquet"
        if s in files and o in files:
            pairs.append((files[s], files[o]))
    if series_m["params"].get("ipr_metrics_run"):
        im = manifest_of(store, "ipr.metrics", series_m["params"]["ipr_metrics_run"])
        f = fetch_outputs(store, im, "lake/ipr_metrics/", cache_root())
        pairs.append((f["lake/ipr_metrics/series.parquet"], f["lake/ipr_metrics/observations.parquet"]))
    only = {w for w in wanted if "|*|" not in w}
    for w in wanted:
        if "|*|" in w:
            only |= {m for m in measure_ids if m.startswith(w.split("|*|")[0] + "|")}
    got = load_series(pairs, cfg, as_of, only=only)
    synthetic_totals(got)
    return got


def _arr(values) -> list:
    return [_r(v) for v in values]


def _ts(x: np.ndarray, y: np.ndarray, alpha: float = 0.05) -> tuple[float, float]:
    t = stats.theil_sen(x, y[None, :], alpha)
    return float(t["slope"][0]), float(t["intercept"][0])


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return bool(np.isclose(a, b, rtol=1e-6, atol=1e-9))


def series_view(g, k: int, m: dict, cfg: DetectConfig, checks: Counter) -> dict | None:
    """One tested series as Moria tested it: its periods, counts (or levels), the denominator and the tested
    quantity; the trend fit of each window with its interval; the anomaly band; the acceleration's two halves; the
    change points and the surge. Recomputed parts are checked against the stored numbers."""
    s, kind, base, last = g.series[k], g.kind, g.base, int(g.last[k])
    if last < base:
        return None
    counts = g.counts[k, : last - base + 1]
    present = np.nonzero(~np.isnan(counts))[0]
    if not len(present):
        return None
    first = base + int(present[0])
    sl = slice(first - base, last - base + 1)
    transform = g.transform[k]
    out: dict = {
        "series_id": s.series_id, "source": s.source, "label": s.meta.get("label"), "unit": s.meta.get("unit"),
        "scope": s.meta.get("scope"), "frequency": kind, "transform": transform, "denominator": g.denominators[k],
        "test_family": m.get("test_family"), "first": index_label(kind, first), "last": index_label(kind, last),
        "periods": [index_label(kind, i) for i in range(first, last + 1)],
        "values": _arr(g.counts[k, sl]), "y": _arr(g.y[k, sl]),
        "denom": _arr(g.denom[k, sl]) if transform == "log_share" else None,
        "trend": {"sig": m.get("trend_sig"), "dir": m.get("trend_dir"), "growth": _r(m.get("trend_growth")),
                  "windows": m.get("trend_windows")},
    }  # fmt: skip
    one_y, one_last = g.y[k : k + 1], g.last[k : k + 1]
    fits = []
    for j, w in enumerate(cfg.series.windows[kind], 1):
        slope = m.get(f"trend_w{j}_slope")
        if slope is None:
            continue
        win = aligned(one_y, one_last, base, w)[0]
        x = np.arange(w, dtype=float)
        got, intercept = _ts(x, win, cfg.series.alpha)
        if not _same(got, slope):
            checks["fit_mismatch"] += 1
            continue
        fits.append({
            "window": f"w{j}", "periods": w, "start": index_label(kind, last - w + 1), "end": index_label(kind, last),
            "slope": _r(slope), "lo": _r(m.get(f"trend_w{j}_lo")), "hi": _r(m.get(f"trend_w{j}_hi")),
            "intercept": _r(intercept), "x_mid": _r(float(np.median(x[~np.isnan(win)]))),
            "y_mid": _r(float(np.nanmedian(win))), "n": m.get(f"trend_w{j}_n"), "p": _r(m.get(f"trend_w{j}_p")),
            "p_holm": _r(m.get(f"trend_w{j}_p_holm")), "q_bh": _r(m.get(f"trend_w{j}_q_bh")),
            "sig": m.get(f"trend_w{j}_sig"),
        })  # fmt: skip
        checks["fits"] += 1
    out["fits"] = fits
    if m.get("anom_period") and m.get("anom_z") is not None:
        b = cfg.series.anomaly_baseline[kind]
        mat = aligned(one_y, one_last, base, b + 1)[0]
        den = aligned(g.denom[k : k + 1], one_last, base, b + 1)[0]
        x = np.arange(b, dtype=float)
        slope, intercept = _ts(x, mat[:b])
        pred = intercept + slope * b
        sigma = float(stats.robust_sigma((mat[:b] - (intercept + slope * x))[None, :])[0])
        with np.errstate(all="ignore"):
            if transform == "level":
                floor = 1e-9 * (abs(pred) + 1)
            else:
                exp_count = math.exp(pred) * den[b] if transform == "log_share" else math.exp(pred)
                floor = 1 / math.sqrt(max(exp_count, 1))
        scale = max(0.0 if math.isnan(sigma) else sigma, floor)
        z = (mat[b] - pred) / scale
        if _same(z, m["anom_z"]):
            out["anomaly"] = {"period": m["anom_period"], "start": index_label(kind, last - b), "baseline": b,
                              "slope": _r(slope), "intercept": _r(intercept), "scale": _r(scale), "pred": _r(pred),
                              "z": _r(z), "z_band": Z99, "p_holm": _r(m.get("anom_p_holm")),
                              "value": _r(m.get("anom_value")), "expected": _r(m.get("anom_expected")),
                              "change": _r(m.get("anom_change")), "flagged": bool(m.get("anomaly"))}  # fmt: skip
        else:
            checks["anomaly_mismatch"] += 1
    if m.get("accel_periods") and m.get("accel_early") is not None:
        w = int(m["accel_periods"])
        win = aligned(one_y, one_last, base, w)[0]
        x = np.arange(w, dtype=float)
        half = w // 2
        es, ei = _ts(x[:half], win[:half])
        rs, ri = _ts(x[half:], win[half:])
        if _same(es, m["accel_early"]) and _same(rs, m.get("accel_recent")):
            out["acceleration"] = {"periods": w, "start": index_label(kind, last - w + 1), "half": half,
                                   "early": {"slope": _r(es), "intercept": _r(ei)},
                                   "recent": {"slope": _r(rs), "intercept": _r(ri)}, "lo": _r(m.get("accel_lo")),
                                   "hi": _r(m.get("accel_hi")), "p_holm": _r(m.get("accel_p_holm")),
                                   "change": _r(m.get("accel_change")), "flagged": bool(m.get("accel"))}  # fmt: skip
        else:
            checks["acceleration_mismatch"] += 1
    if m.get("cp_slope_period"):
        out["change_slope"] = {"period": m["cp_slope_period"], "before": _r(m.get("cp_slope_before")),
                               "after": _r(m.get("cp_slope_after")), "change": _r(m.get("cp_slope_change")),
                               "steeper": bool(m.get("cp_steeper"))}  # fmt: skip
    if m.get("cp_level_period"):
        out["change_level"] = {"period": m["cp_level_period"], "change": _r(m.get("cp_level_change")),
                               "recent": bool(m.get("cp_level_recent"))}  # fmt: skip
    if m.get("surge_window"):
        out["surge"] = {"window": m["surge_window"], "count": _r(m.get("surge_count")),
                        "baseline": _r(m.get("surge_baseline")), "expected": _r(m.get("surge_expected")),
                        "ratio": _r(m.get("surge_ratio")), "p_holm": _r(m.get("surge_p_holm")),
                        "flagged": bool(m.get("surge"))}  # fmt: skip
    return out


def series_views(series: dict[str, Series], wanted: set[str], mrows: dict[str, dict], cfg: DetectConfig,
                 as_of: date) -> tuple[dict[str, dict], Counter]:  # fmt: skip
    checks: Counter = Counter()
    by: dict[tuple[str, str], list[Series]] = defaultdict(list)
    for sid in sorted(wanted):
        s = series.get(sid)
        if s is not None and s.points and sid in mrows:
            by[(s.source, s.kind)].append(s)
    out = {}
    for (source, kind), members in sorted(by.items()):
        g = build_group(source, kind, members, series, cfg, as_of)
        if g is None:
            continue
        for k, s in enumerate(members):
            v = series_view(g, k, mrows[s.series_id], cfg, checks)
            if v is not None:
                out[s.series_id] = v
    checks["series"] = len(out)
    return out, checks


def document_items(store: Store, docs_m: dict, wanted: set[str]) -> dict[str, dict]:
    """Titles, links and dates of the wanted items (normalise's documents behind the document measures)."""
    nm = manifest_of(store, "normalise", docs_m["params"]["normalise_run"])
    out: dict[str, dict] = {}
    if not wanted:
        return out
    con = duckdb.connect()
    ids = sorted(wanted)
    for p in fetch_outputs(store, nm, "lake/documents/", cache_root()).values():
        rows = con.execute(
            "SELECT item_id, source, family, doc_type, title, url, outlet, strftime(event_at, '%Y-%m-%d') "
            "FROM read_parquet(?) WHERE item_id IN (SELECT unnest(?))",
            [p.as_posix(), ids],
        ).fetchall()
        for r in rows:
            out[r[0]] = {"source": r[1], "family": r[2], "doc_type": r[3], "title": r[4], "url": r[5],
                         "outlet": r[6], "event_at": r[7]}  # fmt: skip
    return out


def candidate_rows(inp: Inputs) -> list[dict]:
    queued = {q["candidate_id"]: q for q in inp.queue}
    out = []
    for r in sorted(inp.ranked, key=lambda r: r["candidate_id"]):
        cid = r["candidate_id"]
        c, a, q = inp.candidates[cid], inp.artefacts.get(cid) or {}, queued.get(cid)
        ev = inp.evidence.get(cid, [])
        out.append({
            "id": cid, "label": c["label"] or c["subject"], "type": c["type"], "subject_kind": c["subject_kind"],
            "subject": c["subject"], "source": r["source"], "sources": list(c["sources"]),
            "families": list(c["families"]), "rings": list(c["rings"]), "detectors": list(c["detectors"]),
            "flags": list(r["flags"]), "checks": {k: a.get(k) for k in CHECKS},
            "dossier_flags": list(getattr(inp, "dossier_flags", {}).get(cid, [])), "held": bool(r.get("held")),
            "ring": r["ring"], "ring_basis": r["ring_basis"], "views": list(r["views"]),
            "redundancy_group": c["redundancy_group"], "redundancy_size": c["redundancy_size"],
            "corroboration": c["corroboration"], "direction": c["direction"], "scope": c["scope"],
            "n_items": c["n_items"], "n_sources": c["n_sources"], "window": [c["window_start"], c["window_end"]],
            "numbers": json.loads(c["numbers"] or "{}"),
            # the ranking's inputs at full precision, so that the dashboard's what-if reproduces the queue exactly
            "strength": _r(r["strength"]), "strength_pct": r["strength_pct"], "breadth": r["breadth"],
            "lead": r["lead"], "novelty": r["novelty"],
            "known_trend": r["known_trend"], "known_trend_sim": _r(r["known_trend_sim"], 4),
            "known_trend_match": bool(r["known_trend_match"]), "territory": r["territory_top"],
            "territory_sim": _r(r["territory_sim"], 4), "territory_terms": list(r["term_territories"] or []),
            "factors": {"scope": r["scope_factor"], "type": r["type_factor"], "flags": r["flag_factor"],
                        "context": r["context_factor"]},
            "scores": {v: r[f"score_{v}"] for v in VIEWS},
            "shortlist": {"rank": r["shortlist_rank"], "view": r["shortlist_view"], "pass": r["shortlist_pass"]}
            if r["shortlisted"] else None,
            "queue": {"rank": q["queue_rank"], "view": q["view"], "pass": q["pass"]} if q else None,
            "series": [{"id": e["ref"], "role": e["role"]} for e in ev if e["kind"] == "series"],
        })  # fmt: skip
    return out


def private_bundle(inp: Inputs, public: dict, detect_cfg: DetectConfig, loaded: dict[str, Series] | None = None,
                   docs: dict[str, dict] | None = None, dossiers: dict[str, dict] | None = None,
                   kind: str = "private") -> tuple[dict, Counter]:  # fmt: skip
    """The private bundle. The practice data passes its own series, documents and dossiers (`dashboard_practice`);
    a real run reads them from the store."""
    counts: Counter = Counter()
    cands = candidate_rows(inp)
    # the series behind the series candidates (subjects and references), as Moria tested them
    mrows = {r["series_id"]: r for r in inp.measures}
    wanted = {s["id"] for c in cands for s in c["series"] if s["role"] in ("subject", "reference")}
    denoms = {mrows[w]["denominator"] for w in wanted if w in mrows and mrows[w]["denominator"]}
    if loaded is None:
        loaded = load_scan_series(inp.store, detect_cfg, inp.series_m, set(mrows), inp.as_of, wanted | denoms)
    series, checks = series_views(loaded, wanted, mrows, detect_cfg, inp.as_of)
    counts.update(checks)
    # the window items behind the document candidates, one per de-duplication group (the earliest)
    picks: dict[str, list[dict]] = {}
    for c in cands:
        items = [e for e in inp.evidence.get(c["id"], []) if e["kind"] == "item"]
        if not items:
            continue
        copies = Counter(e["dedup_group"] or e["ref"] for e in items)
        first: dict[str, dict] = {}
        for e in sorted(items, key=lambda e: (e["observable_at"] is None, e["observable_at"] or 0, e["ref"])):
            first.setdefault(e["dedup_group"] or e["ref"], e)
        picks[c["id"]] = [{"item_id": e["ref"], "source": e["source"], "family": e["family"], "ring": e["ring"],
                           "role": e["role"], "copies": copies[e["dedup_group"] or e["ref"]],
                           "observable_at": e["observable_at"].isoformat(timespec="seconds")
                           if e["observable_at"] else None} for e in first.values()]  # fmt: skip
    if docs is None:
        docs = document_items(inp.store, inp.docs_m, {i["item_id"] for v in picks.values() for i in v})
    for v in picks.values():
        for i in v:
            d = docs.get(i["item_id"]) or {}
            i.update(title=d.get("title"), url=d.get("url"), outlet=d.get("outlet"), doc_type=d.get("doc_type"),
                     event_at=d.get("event_at"))  # fmt: skip
    counts["items"] = sum(len(v) for v in picks.values())
    if dossiers is None:
        dossiers = load_dossiers(inp.store, inp.dossier_m)
    counts["dossiers"] = len(dossiers)
    sugg = {}
    for s in inp.suggestions:
        sugg[s["candidate_id"]] = {
            "author": s["author"], "pathways": json.loads(s["pathways"]) if s["pathways"] else None,
            **{k: s.get(k) for k in ("pathway_top", "order_top", "origin_top", "horizon_top", "stance_top",
                                     "impact_top", "error")},
            **{k: _r(s.get(k), 4) for k in ("pathway_p", "impact_value", "pathway_strength")},
            **{k: json.loads(s[k]) if s.get(k) else None for k in ("order", "origin", "horizon", "stance",
                                                                   "impact")},
        }  # fmt: skip
    register = [{"signal_id": s["signal_id"], "status": s["status"], "reviews": s["reviews"], "review": s["review"],
                 "queued": len(s["queued"])}
                for s in sorted(inp.register.values(), key=lambda s: s["signal_id"])]  # fmt: skip
    counts["candidates"] = len(cands)
    bundle = {**public, "kind": kind, "candidates": cands, "series": series, "items": picks,
              "dossiers": dossiers, "suggestions": sugg, "register": register}  # fmt: skip
    return bundle, counts


# ----------------------------------------------------------------------------------------------------- the stage


def encode_public(bundle: dict) -> bytes:
    """Sorted, indented JSON: the public bundle is reviewed in diffs like the reports."""
    return (json.dumps(bundle, sort_keys=True, indent=1, ensure_ascii=False, default=str) + "\n").encode("utf-8")


def encode_private(bundle: dict) -> bytes:
    return gzip.compress(canonical_json(bundle).encode("utf-8"), compresslevel=9, mtime=0)


def check_out_path(out: Path) -> None:
    """The private bundle never goes into the repo: a path inside it is refused unless it is under data/
    (git-ignored)."""
    p, root = out.resolve(), REPO_ROOT.resolve()
    if p.is_relative_to(root) and not p.is_relative_to(root / "data"):
        raise ValueError(f"{out}: the private bundle holds labels and links and never goes in the repo; write it "
                         "outside the repo (or under data/, which is git-ignored)")  # fmt: skip


def dashboard(store: Store, review: ReviewConfig, detect_cfg: DetectConfig, cards: dict[str, SourceCard],
              territories: TerritoriesFile, baseline: BaselineFile, as_of: date, out: Path | None = None,
              public_out: Path | None = None, config_hash: str | None = None) -> tuple[str, str, dict]:  # fmt: skip
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        if out is not None:
            check_out_path(out)
        inp = Inputs(store, as_of)
        manifest.params = {"as_of": as_of.isoformat(), "runs": inp.runs()}
        public = public_bundle(inp, review, detect_cfg, cards, territories, baseline)
        private, counts = private_bundle(inp, public, detect_cfg)
        pdata = encode_private(private)
        key = private_key(as_of)
        store.put(key, pdata, "application/gzip")
        manifest.add_output(key, pdata)
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(pdata if out.suffix == ".gz" else gzip.decompress(pdata))
        pub = encode_public(public)
        if public_out is not None:
            public_out.parent.mkdir(parents=True, exist_ok=True)
            public_out.write_bytes(pub)
        manifest.params["public"] = {"path": PUBLIC_PATH, "sha256": sha256_hex(pub), "bytes": len(pub)}
        counts["private_bytes"], counts["public_bytes"] = len(pdata), len(pub)
        manifest.counts = dict(sorted(counts.items()))
        if counts.get("fit_mismatch") or counts.get("anomaly_mismatch") or counts.get("acceleration_mismatch"):
            manifest.warnings.append("some recomputed fits did not match the stored numbers and were left out")
        log.info("dashboard: %d candidates, %d series, %d items", counts["candidates"], counts["series"],
                 counts["items"])  # fmt: skip
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        return failed(COMMAND, store, manifest, e)
