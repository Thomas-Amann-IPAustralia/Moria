"""`moria queue --as-of D`: the review queue of about 40 dossiers (design §2.5, §8.2, §8.5, §13 day 5).

The shortlist of `moria rank` is ranked again, with the decision model's suggestions (`moria pathways`) when
`pathways.use_in_ranking` is on: a pathway component (each pathway's probability as a percentile among the
shortlist, then the highest, since every question has its own level) joins both views, and an impact component (the
expected impact's percentile) joins the strategic view; the model's probabilities are uncalibrated (design §9.1: for
ranking, never thresholds). The early-warning view is then pathway x novelty x lead time (with strength); the
strategic view pathway x breadth x impact (with strength). The switch is off until `moria eval pathways` passes and
the owner turns it on (D-029): the suggestions are then recorded and shown, not ranked, and the manifest says so.

The queue is chosen by `rank.select`: the views alternate by their shares, each ring is held to its quota (core 35%,
adjacent 35%, wider world 30%), each source to `queue.source_max`, third-order pathways to 20% of the queue (the
order a person confirmed; the model's when its suggestions are used), and one candidate per redundancy group. A flag
is shown, never hidden: it lowers a rank (`rank.flag_penalty`).

**Sensitivity** (design §8.2: the report shows how sensitive the ranking is to the weights): each weight of each view
is multiplied by each factor in `queue.sensitivity`, the queue chosen again, and the places that change counted; so
are the queues with no flag penalty and no type weight.

Writes `review/as_of=<D>/queue.parquet` (one row per place, with its dossier's keys) and `sensitivity.parquet`.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

import pyarrow as pa

from .config import ReviewConfig
from .detect import _matching
from .dossier import key_of
from .manifest import Manifest
from .pathways import COMMAND as PATHWAYS
from .rank import COMMAND as RANK
from .rank import VIEWS, failed, files_of, percentiles, select, view_scores
from .store import Store
from .tables import STRS, read_rows, upload, write_rows

log = logging.getLogger("moria.queue")

COMMAND = "queue"

QUEUE = pa.schema(
    [
        ("queue_rank", pa.int32()),
        ("candidate_id", pa.string()),
        ("as_of", pa.date32()),
        ("view", pa.string()),  # the view whose ranking picked it
        ("pass", pa.int8()),  # 1 within every quota; 2 a ring's unused places; 3 the source cap relaxed
        ("views", STRS),
        ("type", pa.string()),
        ("subject_kind", pa.string()),
        ("ring", pa.string()),
        ("source", pa.string()),
        ("label", pa.string()),
        ("detectors", STRS),
        ("flags", STRS),
        ("redundancy_group", pa.string()),
        ("score_early_warning", pa.float64()),
        ("score_strategic", pa.float64()),
        ("strength_pct", pa.float64()),
        ("breadth", pa.float64()),
        ("lead", pa.float64()),
        ("novelty", pa.float64()),
        ("pathway", pa.float64()),  # percentile within the shortlist; null without suggestions
        ("impact", pa.float64()),
        ("author", pa.string()),  # the model that suggested the pathways, or none
        ("pathways", pa.string()),  # canonical JSON {P1: probability, ...}
        ("pathway_top", pa.string()),
        ("pathway_p", pa.float64()),
        ("order_top", pa.string()),
        ("origin_top", pa.string()),
        ("horizon_top", pa.string()),
        ("stance_top", pa.string()),
        ("impact_top", pa.string()),
        ("known_trend", pa.string()),
        ("known_trend_sim", pa.float64()),
        ("known_trend_match", pa.bool_()),
        ("territory_top", pa.string()),
        ("term_territories", STRS),
        ("dossier_md", pa.string()),
        ("dossier_json", pa.string()),
    ]
)
SENSITIVITY = pa.schema(
    [
        ("view", pa.string()),
        ("component", pa.string()),  # a weight, or flags / type (the factor switched off)
        ("factor", pa.float64()),
        ("overlap", pa.int32()),  # places of the base queue still in the queue
        ("size", pa.int32()),
    ]
)


def rescore(rows: list[dict], sug: dict[str, dict], cfg: ReviewConfig, weights=None, flags=True, types=True,
            confirmed: dict[str, str] | None = None) -> None:  # fmt: skip
    """Final scores of the shortlisted rows, in place. With `pathways.use_in_ranking` on, a pathway component (each
    pathway's probability as a percentile among the shortlist, then the highest: every question has its own level)
    and an impact component (the expected impact's percentile) join the views; else the views keep their
    pre-pathway components. The third-order cap reads the order a person confirmed, else, when the suggestions are
    used, the model's."""
    use = cfg.pathways.use_in_ranking
    have = [r for r in rows if sug.get(r["candidate_id"], {}).get("pathways")]
    if use and have:
        best = [0.0] * len(have)
        for pid in ("P1", "P2", "P3", "P4", "P5", "P6"):
            vals = [json.loads(sug[r["candidate_id"]]["pathways"]).get(pid) for r in have]
            best = [max(b, p) for b, p in zip(best, percentiles(vals), strict=True)]
        for r, b in zip(have, best, strict=True):
            r["pathway"] = b
        for r, p in zip(have, percentiles([sug[r["candidate_id"]]["impact_value"] for r in have]), strict=True):
            r["impact"] = p
    for r in rows:
        extra = {k: r[k] for k in ("pathway", "impact") if use and r.get(k) is not None}
        saved = (r["flag_factor"], r["type_factor"])
        if not flags:
            r["flag_factor"] = 1.0
        if not types:
            r["type_factor"] = 1.0
        view_scores(r, cfg, weights, extra)
        r["flag_factor"], r["type_factor"] = saved
        machine = sug.get(r["candidate_id"], {}).get("order_top") if use else None
        r["order"] = (confirmed or {}).get(r["candidate_id"]) or machine


def choose(rows: list[dict], cfg: ReviewConfig) -> list[dict]:
    return select(rows, cfg.queue.size, cfg.queue, {v: f"score_{v}" for v in VIEWS}, third_order=True)


def sensitivity(rows: list[dict], sug: dict[str, dict], cfg: ReviewConfig, base: set[str],
                confirmed: dict[str, str]) -> list[dict]:  # fmt: skip
    out = []
    for view in VIEWS:
        for comp, w in sorted(cfg.rank.weights[view].items()):
            for f in cfg.queue.sensitivity:
                weights = {v: dict(ws) for v, ws in cfg.rank.weights.items()}
                weights[view][comp] = w * f
                trial = [dict(r) for r in rows]
                rescore(trial, sug, cfg, weights, confirmed=confirmed)
                got = {p["candidate_id"] for p in choose(trial, cfg)}
                out.append({"view": view, "component": comp, "factor": f, "overlap": len(got & base),
                            "size": len(base)})  # fmt: skip
    for comp, kw in (("flags", {"flags": False}), ("type", {"types": False})):
        trial = [dict(r) for r in rows]
        rescore(trial, sug, cfg, confirmed=confirmed, **kw)
        got = {p["candidate_id"] for p in choose(trial, cfg)}
        out.append({"view": "both", "component": comp, "factor": 0.0, "overlap": len(got & base), "size": len(base)})
    for r in rows:  # leave the rows' scores as the base run's
        r.pop("order", None)
    return out


def queue(store: Store, cfg: ReviewConfig, as_of: date, config_hash: str | None = None) -> tuple[str, str, dict]:
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        rm, pm = _matching(store, RANK, as_of), _matching(store, PATHWAYS, as_of)
        if pm["params"].get("rank_run") != rm["run_id"]:
            raise ValueError(f"the pathway suggestions of {as_of} are for an older ranking; run `moria dossier` and "
                             "`moria pathways` again")  # fmt: skip
        manifest.params = {"as_of": as_of.isoformat(), "rank_run": rm["run_id"], "pathways_run": pm["run_id"],
                           "dossier_run": pm["params"].get("dossier_run"), "author": pm["params"].get("author"),
                           "backend": pm["params"].get("backend")}  # fmt: skip
        ranked = read_rows(files_of(store, rm, "review/")["ranked.parquet"])
        sug = {r["candidate_id"]: r for r in read_rows(files_of(store, pm, "interpretation/pathways/")
                                                       ["pathways.parquet"])}  # fmt: skip
        rows = [r for r in ranked if r["shortlisted"] and r["candidate_id"] in sug]
        missing = sum(1 for r in ranked if r["shortlisted"]) - len(rows)
        if missing:
            manifest.warnings.append(f"{missing} shortlisted candidates have no dossier or suggestion row")
        if not any(s.get("pathway_strength") is not None for s in sug.values()):
            manifest.warnings.append("no pathway suggestions: the queue is ranked without pathway and impact")
        if not cfg.pathways.use_in_ranking:
            manifest.warnings.append("pathway suggestions are recorded, not ranked (pathways.use_in_ranking is off)")
        confirmed = confirmed_orders(store)
        rescore(rows, sug, cfg, confirmed=confirmed)
        picks = choose(rows, cfg)
        base = {p["candidate_id"] for p in picks}
        sens = sensitivity(rows, sug, cfg, base, confirmed)
        rescore(rows, sug, cfg, confirmed=confirmed)
        by = {r["candidate_id"]: r for r in rows}
        out = []
        for p in picks:
            r, s = by[p["candidate_id"]], sug[p["candidate_id"]]
            out.append({**{k: r.get(k) for k in ("candidate_id", "views", "type", "subject_kind", "ring", "source",
                                                 "label", "detectors", "flags", "redundancy_group",
                                                 "score_early_warning", "score_strategic", "strength_pct", "breadth",
                                                 "lead", "novelty", "pathway", "impact", "known_trend",
                                                 "known_trend_sim", "known_trend_match", "territory_top",
                                                 "term_territories")},
                        **{k: s.get(k) for k in ("author", "pathways", "pathway_top", "pathway_p", "order_top",
                                                 "origin_top", "horizon_top", "stance_top", "impact_top")},
                        "queue_rank": p["rank"], "view": p["view"], "pass": p["pass"], "as_of": as_of,
                        "dossier_md": key_of(p["candidate_id"], as_of, "md"),
                        "dossier_json": key_of(p["candidate_id"], as_of, "json")})  # fmt: skip
        prefix = f"review/as_of={as_of.isoformat()}/"
        with tempfile.TemporaryDirectory(prefix="moria-queue-") as tmp:
            write_rows(out, QUEUE, Path(tmp) / "queue.parquet", ("queue_rank",))
            write_rows(sens, SENSITIVITY, Path(tmp) / "sensitivity.parquet", ("view", "component", "factor"))
            for name in ("queue", "sensitivity"):
                upload(store, manifest, f"{prefix}{name}.parquet", Path(tmp) / f"{name}.parquet")
        counts: dict[str, int] = defaultdict(int)
        counts["queue"] = len(out)
        counts["shortlist"] = len(rows)
        for r in out:
            counts[f"ring_{r['ring']}"] += 1
            counts[f"type_{r['type']}"] += 1
            counts[f"view_{r['view']}"] += 1
            counts[f"pass_{r['pass']}"] += 1
            counts["flagged"] += bool(r["flags"])
            counts["third_order"] += r["order_top"] == "3"
        counts["sensitivity_min_overlap"] = min((s["overlap"] for s in sens), default=len(out))
        manifest.counts = dict(sorted(counts.items()))
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        return failed(COMMAND, store, manifest, e)


def confirmed_orders(store: Store) -> dict[str, str]:
    """The lowest order of each signal's pathways that a person confirmed in the register."""
    from .register import events, state

    out = {}
    for sid, s in state(events(store)).items():
        orders = [p["order"] for p in (s.get("review") or {}).get("pathways") or [] if p.get("confirmed")]
        if orders:
            out[sid] = str(min(orders))
    return out
