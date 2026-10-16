"""`moria eval detectors --as-of D`: the SignalBoost detectors against day 4's (the proposal's item 4; D-025).

Retain a new detector only where it measurably improves detection. Four experiments, all on the real evidence layer
at `as_of`, all in memory (nothing is written to the layer):

1. **Injections into real series.** Series that no detector flags are sampled per source and frequency
   (`evaluation.per_class`), and known changes are planted in them, each kind in its own series: a one-period spike
   (day 4's band is for this), a 3-month shift, a steeper slope over 36 months, a structural ramp from 60 months
   back, a contextual jump (the series moves and its context does not), the same jump with its peers and counterpart
   moving alike (a control: context should explain it), and a broken relationship (an Australian series' recent
   changes shuffled against its counterpart's). Every detector runs over the whole layer with the plants in place,
   so Holm's families are as real. Recall is the share of plants a detector catches where it can test; incremental
   value is the share of plants it catches that no day-4 detector catches.
2. **Null series.** Other quiet series are replaced by their own noise (residuals about their Theil-Sen line,
   resampled in blocks of 3) around a flat level (for trend detectors) or their own line (for change detectors):
   false positives per series.
3. **Artefacts.** Every count source's volume and counts raised 60% in the last 3 months (a coverage jump), or one
   recent period counted twice (a duplicated collection): flags per quiet series, against day 4's on the same.
4. **Backtest.** The full series chain at past dates (every `every_months` over `back_months`), point in time. A flag
   is *confirmed* when day 4's trend or acceleration detectors agree in direction `confirm_months` later; reversed
   when the trend goes the other way. A label-free benchmark beside day 4's band anomalies, until the owner's
   hindsight set exists (design §11.3).

Relationship detectors: **placebo** runs (window and baseline items, or months, reassigned at random; nothing should
fire) and **synthetic breakdowns** (established keyphrase or class pairs removed from, or country-class pairs cut
or raised in, the window).

The retention rules (`evaluation.retain`) were committed before the first run. The verdict is a recommendation:
switching a detector on (`new_detectors`) is the owner's call (CLAUDE.md). Writes `manifests/eval.detectors/` and
returns the results for `reports/eval/detectors.md` (aggregates only: no labels, phrases or classes).
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb
import numpy as np

from . import concepts, measures, stats
from .config import DetectConfig, SourceCard
from .horizons import periods_of
from .iprmetrics import COMMAND as IPRM
from .manifest import Manifest
from .measures import PER_YEAR, Series, current_index, role
from .records import canonical_json
from .store import Store
from .tables import StageInputError, cache_root, fetch_outputs, upstream

log = logging.getLogger("moria.evaldetect")

COMMAND = "eval.detectors"
NEW_SERIES = ("short_shift", "long_trend", "structural_shift", "contextual_anomaly", "decoupling")
DAY4 = ("trend", "acceleration", "anomaly", "surge")
INJECTIONS = ("spike", "shift", "slope", "structural", "contextual", "common", "decouple")
NULLS = ("null_flat", "null_line")
TARGET = {"short_shift": "shift", "long_trend": "structural", "structural_shift": "structural",
          "contextual_anomaly": "contextual", "decoupling": "decouple"}  # fmt: skip
NULL_OF = {"short_shift": "null_line", "long_trend": "null_flat", "structural_shift": "null_line",
           "contextual_anomaly": "null_line", "decoupling": "null_line", "trend": "null_flat",
           "acceleration": "null_line", "anomaly": "null_line", "surge": "null_line"}  # fmt: skip
COMPARABLE = {"short_shift": "anomaly", "long_trend": "trend", "structural_shift": "anomaly",
              "contextual_anomaly": "anomaly", "decoupling": "anomaly"}  # fmt: skip


# ------------------------------------------------------------------------------------------------- what fired


def fired(rows: list[dict], hrows: list[dict], crows: list[dict]) -> tuple[dict, dict]:
    """(series -> {detector: direction}, series -> {detector: testable}) for day 4's and the new detectors."""
    out: dict[str, dict[str, int]] = defaultdict(dict)
    can: dict[str, dict[str, bool]] = defaultdict(dict)
    for r in rows:
        sid = r["series_id"]
        can[sid].update({d: True for d in DAY4})
        if r["trend_dir"]:
            out[sid]["trend"] = r["trend_dir"]
        if r["accel"] or (r["cp_steeper"] and r["trend_dir"]):
            out[sid]["acceleration"] = r["trend_dir"] or int(np.sign(r.get("accel_recent") or 1))
        if r["anomaly"] or r["cp_level_recent"]:
            shift = r.get("anom_z") if r["anomaly"] else (r.get("cp_level_after") or 0) - (r.get("cp_level_before")
                                                                                            or 0)  # fmt: skip
            out[sid]["anomaly"] = 1 if (shift or 0) > 0 else -1
        if r["surge"]:
            out[sid]["surge"] = 1
    for h in hrows:
        sid = h["series_id"]
        if h["method"] == "short":
            can[sid]["short_shift"] = True
            if h["sig"]:
                out[sid]["short_shift"] = h["direction"]
        if h["method"] == "long":
            can[sid]["long_trend"] = can[sid]["structural_shift"] = True
            if h["sig"]:
                out[sid]["long_trend"] = h["direction"]
            if h.get("structural"):
                out[sid]["structural_shift"] = h["structural_direction"]
    for c in crows:
        sid = c["series_id"]
        can[sid]["contextual_anomaly"] = True
        if c["contextual"]:
            out[sid]["contextual_anomaly"] = 1 if c["observed"] > c["expected"] else -1
        if c.get("coupling_p") is not None:
            can[sid]["decoupling"] = True
            if c.get("coupling"):
                out[sid]["decoupling"] = -1 if c["coupling"] == "decoupled" else 1
    return out, can


# --------------------------------------------------------------------------------------------------- planting


class Planter:
    """Changes planted in copies of real series, on the scale each series is tested on: counts multiplied (a
    relative change r is a factor 1 + r), statistics shifted by r times their level."""

    def __init__(self, series: dict[str, Series], cfg: DetectConfig, as_of: date, seed: int):
        self.series, self.cfg, self.as_of = series, cfg, as_of
        self.rng = np.random.default_rng(seed)
        self.out: dict[str, Series] = {}

    def last(self, s: Series) -> int | None:
        lim = current_index(s.kind, self.as_of) - 1 - self.cfg.series.lag(s.series_id)
        pts = [i for i in s.points if i <= lim]
        return max(pts) if pts else None

    def copy(self, sid: str) -> Series:
        if sid not in self.out:
            s = self.series[sid]
            self.out[sid] = Series(s.series_id, s.source, s.kind, s.meta, dict(s.points))
        return self.out[sid]

    @staticmethod
    def level(s: Series) -> float:
        vals = [abs(v) for _, v in sorted(s.points.items())[-48:]]
        return float(np.median(vals)) if vals else 1.0

    def relative(self, sid: str, changes: dict[int, float]) -> None:
        s = self.copy(sid)
        is_level = role(s)[0] == "level"
        lv = self.level(s)
        for i, r in changes.items():
            if i in s.points:
                v = s.points[i]
                s.points[i] = v + r * lv if is_level else float(max(round(v * (1 + r)), 0))

    def periods(self, s: Series, months: int) -> int:
        return max(1, periods_of(s.kind, months, PER_YEAR))

    def plant(self, kind: str, sid: str, peers: list[str] | None = None, ref: str | None = None) -> None:
        inj = self.cfg.evaluation.injections
        s = self.series[sid]
        last = self.last(s)
        per = PER_YEAR[s.kind]
        counts = role(s)[0] != "level"
        if kind == "spike":
            self.relative(sid, {last: inj.spike})
        elif kind == "shift":
            p = self.periods(s, 3)
            self.relative(sid, {last - k: inj.shift for k in range(p)})
        elif kind in ("slope", "structural"):
            p = self.periods(s, 36 if kind == "slope" else 60)
            g = inj.slope if kind == "slope" else inj.structural
            ramp = {last - p + 1 + k: (k + 1) / per for k in range(p)}
            self.relative(sid, {i: (np.exp(g * t) - 1) if counts else g * t for i, t in ramp.items()})
        elif kind in ("contextual", "common"):
            self.relative(sid, {last: inj.contextual})
            if kind == "common":
                for o in [*(peers or []), *([ref] if ref else [])]:
                    lo = self.last(self.series[o])
                    if lo is not None:
                        self.relative(o, {lo: inj.contextual})
        elif kind == "decouple":
            self._decouple(sid, last)

    def _ys(self, s: Series) -> tuple[list[int], np.ndarray, callable]:
        """The series' points to its last usable one, on its tested scale, with the way back to raw values."""
        transform, dname, _ = role(s)
        den = self.series.get(dname) if dname else None
        last = self.last(s)
        idx = [i for i in sorted(s.points) if i <= last and (den is None or i in den.points)]
        raw = np.array([s.points[i] for i in idx])
        if transform == "log_share" and den is not None:
            d = np.array([den.points[i] for i in idx])
            return idx, np.log((raw + 0.5) / d), lambda y: np.maximum(np.round(np.exp(y) * d - 0.5), 0)
        if transform != "level":
            return idx, np.log(raw + 0.5), lambda y: np.maximum(np.round(np.exp(y) - 0.5), 0)
        return idx, raw.astype(float), lambda y: y

    def _decouple(self, sid: str, last: int) -> None:
        s = self.copy(sid)
        idx, y, back = self._ys(s)
        n = min(len(y), self.cfg.context.coupling.max_points)
        d = np.diff(y[-n:])
        half = len(d) // 2
        d[half:] = self.rng.permutation(d[half:])
        y2 = y.copy()
        y2[-n + 1 :] = y[-n] + np.cumsum(d)
        for i, v in zip(idx, back(y2), strict=True):
            s.points[i] = float(v)

    def null(self, sid: str, flat: bool) -> None:
        """The series' own noise about its Theil-Sen line, resampled in blocks of 3, around a flat level or the
        line itself."""
        s = self.copy(sid)
        idx, y, back = self._ys(s)
        if len(y) < 6:
            return
        x = np.array(idx, dtype=float)
        ts = stats.theil_sen(x, y[None])
        line = ts["intercept"][0] + ts["slope"][0] * x
        resid = y - line
        blocks = [resid[k : k + 3] for k in range(len(resid) - 2)]
        boot = np.concatenate([blocks[j] for j in self.rng.integers(0, len(blocks), len(resid) // 3 + 1)])[: len(y)]
        centre = np.full(len(y), np.median(y)) if flat else line
        for i, v in zip(idx, back(centre + boot), strict=True):
            s.points[i] = float(v)


def artefact_series(series: dict[str, Series], cfg: DetectConfig, as_of: date, kind: str) -> dict[str, Series]:
    """Every count series of every source with a volume: the last 3 months' values raised (a coverage jump), or the
    last period counted twice (a duplicated collection)."""
    inj = cfg.evaluation.injections
    p = Planter(series, cfg, as_of, 0)
    for sid, s in series.items():
        if s.meta.get("synthetic") or role(s)[0] == "level":
            continue
        last = p.last(s)
        if last is None:
            continue
        if kind == "volume_jump":
            p.relative(sid, {last - k: inj.volume_jump for k in range(p.periods(s, 3))})
        else:
            p.relative(sid, {last: inj.duplicated_period})
    return {**series, **p.out}


# ---------------------------------------------------------------------------------------------- the experiments


def series_experiment(series: dict[str, Series], cfg: DetectConfig, as_of: date) -> dict:
    ec = cfg.evaluation
    rows0, _, _, h0, c0, _ = measures._run(dict(series), cfg, as_of)
    f0, can0 = fired(rows0, h0, c0)
    quiet = sorted(r["series_id"] for r in rows0 if not measures.flagged(r) and (r["trend_windows"] or 0) >= 2
                   and r["series_id"] in series)  # fmt: skip
    ctx0 = {c["series_id"]: c for c in c0}
    rng = np.random.default_rng(ec.seed)
    by_class: dict[tuple, list[str]] = defaultdict(list)
    for sid in quiet:
        s = series[sid]
        by_class[(s.source, s.kind)].append(sid)
    used: set[str] = set()
    plan: dict[str, list[str]] = defaultdict(list)  # experiment -> series
    long_need = cfg.horizons.long.min_points
    for (_, kind), sids in sorted(by_class.items()):
        sids = list(rng.permutation(sids))
        for exp in (*INJECTIONS, *NULLS):
            n, taken = (ec.per_class // 2 if exp == "common" else ec.per_class), 0
            for sid in sids:
                if taken >= n:
                    break
                c = ctx0.get(sid)
                if sid in used:
                    continue
                if exp == "structural" and len(series[sid].points) < max(periods_of(kind, 60, PER_YEAR) + 5,
                                                                         long_need):  # fmt: skip
                    continue
                if exp in ("contextual", "common") and not (c and (c["peers"] or c["reference"])):
                    continue
                if exp == "common" and (set(c["peers"] or []) | {c["reference"]}) & used:
                    continue
                established = cfg.context.coupling.established
                if exp == "decouple" and not (c and (c.get("coupling_r_early") or 0) >= established):
                    continue
                plan[exp].append(sid)
                used.add(sid)
                taken += 1
                if exp == "common":
                    used |= set(c["peers"] or []) | ({c["reference"]} if c["reference"] else set())
    planter = Planter(series, cfg, as_of, ec.seed)
    for exp, sids in plan.items():
        for sid in sids:
            if exp in NULLS:
                planter.null(sid, flat=exp == "null_flat")
            else:
                c = ctx0.get(sid) or {}
                planter.plant(exp, sid, c.get("peers"), c.get("reference"))
    rows1, _, _, h1, c1, _ = measures._run({**series, **planter.out}, cfg, as_of)
    f1, can1 = fired(rows1, h1, c1)
    result: dict = {"plants": {k: len(v) for k, v in plan.items()}, "detectors": {}}
    for d in (*DAY4, *NEW_SERIES):
        res = {}
        for exp in (*INJECTIONS, *NULLS):
            sids = plan.get(exp, [])
            testable = [s for s in sids if can1.get(s, {}).get(d)]
            hit = [s for s in testable if d in f1.get(s, {})]
            alone = [s for s in hit if not any(x in f1.get(s, {}) for x in DAY4)]
            res[exp] = {"planted": len(sids), "testable": len(testable), "fired": len(hit),
                        "recall": len(hit) / len(testable) if testable else None,
                        "incremental": len(alone) / len(sids) if sids else None}  # fmt: skip
        result["detectors"][d] = res
    day4_any = {exp: (sum(1 for s in plan.get(exp, []) if any(x in f1.get(s, {}) for x in DAY4)) /
                      max(len(plan.get(exp, [])), 1)) for exp in (*INJECTIONS, *NULLS)}  # fmt: skip
    result["day4_any"] = day4_any
    # artefacts: flags per quiet count series, the new detectors against day 4's
    arts = {}
    count_quiet = [s for s in quiet if role(series[s])[0] != "level"]
    for kind in ("volume_jump", "duplicated_period"):
        ra, _, _, ha, ca, _ = measures._run(artefact_series(series, cfg, as_of, kind), cfg, as_of)
        fa, cana = fired(ra, ha, ca)
        out = {}
        for d in (*DAY4, *NEW_SERIES):
            testable = [s for s in count_quiet if cana.get(s, {}).get(d)]
            out[d] = sum(1 for s in testable if d in fa.get(s, {})) / len(testable) if testable else None
        out["day4_any"] = (sum(1 for s in count_quiet if any(x in fa.get(s, {}) for x in DAY4))
                           / max(len(count_quiet), 1))  # fmt: skip
        arts[kind] = out
    result["artefacts"] = arts
    result["quiet_series"] = len(quiet)
    result["baseline_flagged"] = {d: sum(1 for v in f0.values() if d in v) for d in (*DAY4, *NEW_SERIES)}
    del can0
    return result


def _months_back(d: date, k: int) -> date:
    t = d.year * 12 + d.month - 1 - k
    return date(t // 12, t % 12 + 1, min(d.day, 28))


def backtest(files: list, cfg: DetectConfig, as_of: date) -> dict:
    bc = cfg.evaluation.backtest
    dates = [_months_back(as_of, k) for k in range(bc.back_months, -1, -bc.every_months)]
    flags: dict[date, dict[str, dict[str, int]]] = {}
    for d in dates:
        series = measures.load_series(files, cfg, d)
        rows, _, _, h, c, _ = measures._run(series, cfg, d)
        flags[d] = fired(rows, h, c)[0]
        log.info("backtest %s: %d series", d, len(rows))
    step = bc.confirm_months // bc.every_months
    out = {"dates": [d.isoformat() for d in dates], "detectors": {}}
    for det in ("anomaly", *NEW_SERIES):
        onsets = confirmed = reversed_ = 0
        leads = []
        per_date = []
        for n, d in enumerate(dates):
            now = {s for s, v in flags[d].items() if det in v}
            per_date.append(len(now))
            if n + step >= len(dates):
                continue
            before = {s for s, v in flags[dates[n - 1]].items() if det in v} if n else set()
            later = flags[dates[n + step]]
            for s in sorted(now - before):
                direction = flags[d][s][det]
                onsets += 1
                lt = later.get(s, {})
                if lt.get("trend") == direction or lt.get("acceleration") == direction:
                    confirmed += 1
                    first = next(k for k in range(n, len(dates)) if flags[dates[k]].get(s, {}).get("trend") ==
                                 direction or flags[dates[k]].get(s, {}).get("acceleration") == direction)  # fmt: skip
                    leads.append((first - n) * bc.every_months)
                elif lt.get("trend") == -direction:
                    reversed_ += 1
        out["detectors"][det] = {"onsets": onsets, "confirmed": confirmed, "reversed": reversed_,
                                 "confirmation_rate": confirmed / onsets if onsets else None,
                                 "reversal_rate": reversed_ / onsets if onsets else None,
                                 "median_lead_months": float(np.median(leads)) if leads else None,
                                 "flags_per_date": per_date}  # fmt: skip
    return out


# ----------------------------------------------------------------------------------------------- relationships


def _ipr_files(files: dict) -> dict[str, Path]:
    return {k.rsplit("/", 1)[1]: p for k, p in files["ipr"].items()}


def _window_months(as_of: date, cfg: DetectConfig) -> tuple[list[str], list[str]]:
    dc = cfg.documents
    last = date(as_of.year, as_of.month, 1)
    months = [_months_back(last, k + 1).strftime("%Y-%m") for k in range(dc.ipr_window_months + dc.ipr_baseline_months)]
    return months[: dc.ipr_window_months], months[dc.ipr_window_months :]


def _rewrite(src: Path, dst: Path, sql_select: str) -> Path:
    con = duckdb.connect()
    con.execute(f"COPY ({sql_select.format(src=src.as_posix())}) TO '{dst.as_posix()}' (FORMAT parquet)")
    return dst


def _pairs_of(paths: dict[str, Path], as_of: date, cfg: DetectConfig) -> list[dict]:
    files = {"ipr": {f"lake/ipr_metrics/{k}": p for k, p in paths.items()}}
    dc = cfg.documents
    rows = concepts._lengths(concepts.class_pairs(files, as_of, cfg), dc.ipr_window_months, dc.ipr_baseline_months)
    rows += concepts._lengths(concepts.country_pairs(files, as_of, cfg), dc.ipr_window_months, dc.ipr_baseline_months)
    concepts.decide_combinations(rows, cfg)
    return rows


def _rates(rows: list[dict]) -> dict:
    out = {}
    for group, test in (("kp", lambda s: s == "kp"), ("class", lambda s: s in ("ipc", "nice")),
                        ("country", lambda s: s.endswith("_country"))):  # fmt: skip
        rs = [r for r in rows if test(r["scheme"])]
        out[group] = {"tested_fade": sum(1 for r in rs if r["p_fade"] is not None),
                      "fading": sum(1 for r in rs if r["fading"]),
                      "tested_rise": sum(1 for r in rs if r["p"] is not None),
                      "new": sum(1 for r in rs if r["new"]), "rising": sum(1 for r in rs if r["rising"])}  # fmt: skip
    return out


def relationship_experiment(store: Store, cfg: DetectConfig, cards: dict[str, SourceCard], as_of: date) -> dict:
    ec = cfg.evaluation
    rng = np.random.default_rng(ec.seed + 1)
    try:
        _, files = concepts.inputs(store)
    except (StageInputError, ValueError) as e:
        # the features are behind normalise (prepare has not run since): the IP RAPID pairs are tested, the
        # keyphrase pairs are skipped and the report says why
        im = upstream(store, IPRM)
        files = {"ipr": {**fetch_outputs(store, im, "lake/ipr_metrics/class_", cache_root()),
                         **fetch_outputs(store, im, "lake/ipr_metrics/country_", cache_root())}}  # fmt: skip
        out: dict = {"real": {}, "placebo": [{} for _ in range(ec.placebo_repeats)], "synthetic": {},
                     "kp_skipped": str(e).splitlines()[0][:300]}  # fmt: skip
        return _class_experiment(files, cfg, as_of, rng, out)
    return _class_experiment(files, cfg, as_of, rng, _kp_experiment(files, cards, cfg, as_of, rng))


def _kp_experiment(files: dict, cards: dict[str, SourceCard], cfg: DetectConfig, as_of: date, rng) -> dict:
    """Keyphrase pairs: placebos (window and baseline items reassigned) and synthetic breakdowns."""
    ec, rc = cfg.evaluation, cfg.relationships
    items, _ = concepts.load_items(files, cards, as_of, cfg)
    wanted = {i["item_id"] for i in items}
    kp_rows: dict[str, list[str]] = defaultdict(list)
    for p in concepts._by_source(files["kp"]).values():
        for r in concepts.read_rows(p, ["item_id", "phrase"]):
            if r["item_id"] in wanted:
                kp_rows[r["item_id"]].append(r["phrase"])
    dc = cfg.documents

    def kp_combos(its, kps):
        rows = concepts._lengths(concepts.keyphrase_pairs(its, kps, cfg), dc.window_days, dc.baseline_days)
        concepts.decide_combinations(rows, cfg)
        return rows

    real = kp_combos(items, kp_rows)
    out: dict = {"real": _rates(real), "placebo": [], "synthetic": {}}
    # placebo: window and baseline reassigned at random, the window's share kept
    for _ in range(ec.placebo_repeats):
        perm = rng.permutation([i["period"] for i in items])
        shuffled = [{**i, "period": p} for i, p in zip(items, perm, strict=True)]
        out["placebo"].append(_rates(kp_combos(shuffled, kp_rows)))
    # synthetic: established keyphrase pairs broken in the window (one side removed where they met)
    eligible = [r for r in real if r["scheme"] == "kp" and not r["fading"] and not r["rising"]
                and r["baseline"] >= 2 * rc.fade_min_baseline
                and (r["expected_window"] or 0) >= 2 * rc.fade_min_expected
                and min(r["a_window"], r["b_window"]) >= rc.fade_min_each_window + r["window"]]  # fmt: skip
    chosen = [eligible[j] for j in rng.permutation(len(eligible))[: ec.per_class]]
    by_item = {i["item_id"]: i for i in items}
    kp2 = {k: list(v) for k, v in kp_rows.items()}
    for r in chosen:
        for iid, ps in kp2.items():
            if by_item[iid]["period"] == "w" and r["a"] in ps and r["b"] in ps:
                ps.remove(r["b"])
    after = {r["combination"]: r for r in kp_combos(items, kp2)}
    out["synthetic"]["kp_fading"] = {
        "planted": len(chosen),
        "caught": sum(1 for r in chosen if after.get(r["combination"], {}).get("fading")),
    }
    return out


def _class_experiment(files: dict, cfg: DetectConfig, as_of: date, rng, out: dict) -> dict:
    """IP RAPID's class pairs and country-class pairs: placebos (months reassigned) and synthetic changes."""
    ec, rc = cfg.evaluation, cfg.relationships
    paths = _ipr_files(files)
    window, baseline = _window_months(as_of, cfg)
    span = window + baseline
    real_c = _pairs_of(paths, as_of, cfg)
    out["real"].update({k: v for k, v in _rates(real_c).items() if k != "kp"})
    with tempfile.TemporaryDirectory(prefix="moria-evalrel-") as tmp:
        for rep in range(ec.placebo_repeats):
            perm = dict(zip(span, rng.permutation(span), strict=True))
            case = "CASE period " + " ".join(f"WHEN '{a}' THEN '{b}'" for a, b in perm.items()) + " ELSE period END"
            moved = {}
            for name, p in paths.items():
                cols = duckdb.connect().execute(f"SELECT * FROM read_parquet('{p.as_posix()}') LIMIT 0").description
                sel = ", ".join(f"{case} AS period" if c[0] == "period" else f'"{c[0]}"' for c in cols)
                moved[name] = _rewrite(p, Path(tmp) / f"{rep}-{name}", f"SELECT {sel} FROM read_parquet('{{src}}')")
            rates = _rates(_pairs_of(moved, as_of, cfg))
            out["placebo"][rep].update({k: v for k, v in rates.items() if k != "kp"})
        # synthetic: established class pairs cut to a fifth in the window; country-class pairs cut or tripled
        wl = ", ".join(f"'{m}'" for m in window)
        for group, scheme_ok, mult, key in (
            ("class_fading", ("ipc", "nice"), 0.2, "fading"),
            ("country_fading", ("ipc_country", "nice_country"), 0.2, "fading"),
            ("country_rising", ("ipc_country", "nice_country"), 3.0, "rising"),
        ):
            pool = [r for r in real_c if r["scheme"] in scheme_ok and not r["fading"] and not r["rising"]
                    and not r["new"] and r["baseline"] >= 2 * rc.fade_min_baseline and r["window"] >= 5
                    and (r["expected_window"] or 0) >= 2 * rc.fade_min_expected]  # fmt: skip
            pick = [pool[j] for j in rng.permutation(len(pool))[: ec.per_class]]
            if not pick:
                out["synthetic"][group] = {"planted": 0, "caught": 0}
                continue
            edited = dict(paths)
            if group == "class_fading":
                cond = " OR ".join(f"(scheme = '{r['scheme']}' AND class_a = '{r['a']}' AND class_b = '{r['b']}')"
                                   for r in pick)  # fmt: skip
                edited["class_pairs.parquet"] = _rewrite(
                    paths["class_pairs.parquet"], Path(tmp) / f"{group}.parquet",
                    f"SELECT * REPLACE (CAST(CASE WHEN period IN ({wl}) AND ({cond}) THEN floor(applications * {mult}) "
                    "ELSE applications END AS INTEGER) AS applications) FROM read_parquet('{src}')")  # fmt: skip
            else:
                cond = " OR ".join(f"(scheme || '_country' = '{r['scheme']}' AND upper(country) = '{r['a']}' AND "
                                   f"\"class\" = '{r['b']}')" for r in pick)  # fmt: skip
                edited["country_classes.parquet"] = _rewrite(
                    paths["country_classes.parquet"], Path(tmp) / f"{group}.parquet",
                    f"SELECT * REPLACE (CAST(CASE WHEN period IN ({wl}) AND ({cond}) THEN floor(applications * {mult}) "
                    "ELSE applications END AS INTEGER) AS applications) FROM read_parquet('{src}')")  # fmt: skip
            got = {r["combination"]: r for r in _pairs_of(edited, as_of, cfg)}
            out["synthetic"][group] = {"planted": len(pick), "caught": sum(
                1 for r in pick if got.get(r["combination"], {}).get(key) or (key == "rising" and got.get(
                    r["combination"], {}).get("new")))}  # fmt: skip
    return out


# ------------------------------------------------------------------------------------------------------ verdicts


def verdicts(series: dict, rel: dict | None, back: dict | None, cfg: DetectConfig) -> dict:
    rt = cfg.evaluation.retain
    out = {}
    for d in NEW_SERIES:
        res = series["detectors"][d]
        target, null = res[TARGET[d]], res[NULL_OF[d]]
        recall, inc, nr = target["recall"], target["incremental"], null["recall"]
        ref = series["detectors"][COMPARABLE[d]][NULL_OF[d]]["recall"] or 0.0
        art = [series["artefacts"][k][d] - series["artefacts"][k]["day4_any"] for k in series["artefacts"]
               if series["artefacts"][k][d] is not None]  # fmt: skip
        excess = max(art) if art else None
        checks = {"incremental": inc is not None and inc >= rt.min_incremental,
                  "null_rate": nr is None or (nr <= ref + rt.null_margin and nr <= rt.max_null_rate),
                  "artefacts": excess is None or excess <= rt.max_artefact_excess}  # fmt: skip
        if d == "contextual_anomaly":
            common = res["common"]["recall"]
            band = series["detectors"]["anomaly"]["common"]["recall"]
            checks["context_control"] = common is not None and band is not None and common < band
        out[d] = {"recall": recall, "incremental": inc, "null_rate": nr, "null_reference": ref,
                  "artefact_excess": excess, "checks": checks, "retain": all(checks.values())}  # fmt: skip
        if back:
            out[d]["backtest"] = back["detectors"].get(d)
    if rel:
        synth = rel["synthetic"]
        placebo = rel["placebo"]

        def null_rate(groups, keys):
            fired_ = sum(p[g][k] for p in placebo for g in groups if g in p for k in keys)
            tested = sum(p[g]["tested_fade" if k == "fading" else "tested_rise"] for p in placebo for g in groups
                         if g in p for k in keys)  # fmt: skip
            return fired_ / tested if tested else None

        def rec(names):
            planted = sum(synth.get(n, {}).get("planted", 0) for n in names)
            return sum(synth.get(n, {}).get("caught", 0) for n in names) / planted if planted else None

        for d, names, groups, keys in (("fading_combination", ["kp_fading", "class_fading"], ["kp", "class"],
                                        ["fading"]),
                                       ("jurisdiction_shift", ["country_fading", "country_rising"], ["country"],
                                        ["fading", "new", "rising"])):  # fmt: skip
            recall, nr = rec(names), null_rate(groups, keys)
            ref = null_rate(["kp", "class"], ["new", "rising"]) or 0.0  # day 4's new combinations, same placebos
            checks = {
                "incremental": recall is not None and recall >= rt.min_incremental,  # day 4 has no such test
                "null_rate": nr is not None and nr <= ref + rt.null_margin and nr <= rt.max_null_rate,
            }
            out[d] = {"recall": recall, "incremental": recall, "null_rate": nr, "null_reference": ref,
                      "artefact_excess": None, "checks": checks, "retain": all(checks.values())}  # fmt: skip
    return out


def evaluate(store: Store, cfg: DetectConfig, cards: dict[str, SourceCard], as_of: date, with_backtest: bool = True,
             config_hash: str | None = None) -> tuple[str, str, dict, dict]:  # fmt: skip
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        runs, files = measures.inputs(store, cfg)
        series = measures.load_series(files, cfg, as_of)
        log.info("eval detectors: %d series", len(series))
        sres = series_experiment(series, cfg, as_of)
        back = backtest(files, cfg, as_of) if with_backtest else None
        rel = relationship_experiment(store, cfg, cards, as_of)
        result = {"series": sres, "backtest": back, "relationships": rel,
                  "verdicts": verdicts(sres, rel, back, cfg)}  # fmt: skip
        result = json.loads(canonical_json(result))
        manifest.params = {"as_of": as_of.isoformat(), **runs, "backtest": with_backtest, "result": result}
        manifest.counts = {"detectors": len(result["verdicts"]),
                           "retain": sum(1 for v in result["verdicts"].values() if v["retain"])}  # fmt: skip
        return "passed", manifest.finish(store, "passed"), manifest.counts, result
    except Exception as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        cause = f"{COMMAND}: {type(e).__name__}: {first[:300]}"
        log.error("%s", cause)
        return "failed", manifest.finish(store, "failed", cause), {"error": cause}, {}


# -------------------------------------------------------------------------------------------------------- report


def _p(v) -> str:
    return "-" if v is None else f"{v:.0%}" if v >= 0.1 or v == 0 else f"{v:.1%}"


def report(result: dict, mkey: str, as_of: date, cfg: DetectConfig) -> str:
    rt = cfg.evaluation.retain
    s = result["series"]
    lines = [
        "# The SignalBoost detectors against day 4's",
        "",
        f"Generated by `moria eval detectors --as-of {as_of}` (`{mkey}`): the proposal's item 4 (D-025). Changes "
        "planted in real series, null series from their own noise, artefacts and a backtest; placebo and synthetic "
        "tests for the relationship detectors. Aggregates only.",
        "",
        f"Retention rules (config/detect.yaml, D-025): incremental value (plants it is for, caught by it and by no "
        f"day-4 detector) at least {rt.min_incremental:.0%}; false positives on null series (or placebo tests) at "
        f"most day 4's comparable detector's rate plus {rt.null_margin:.0%}, and at most {rt.max_null_rate:.0%}; "
        f"artefact flags at most {rt.max_artefact_excess:.0%} beyond day 4's. A detector that passes is recommended; "
        "switching it on is the owner's call. Recall is where it could test.",
        "",
        "## Verdicts",
        "",
        "| Detector | Recall | Incremental | False positives (day 4's) | Artefact excess | Retain |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for d, v in result["verdicts"].items():
        failed = [k.replace("_", " ") for k, ok in v["checks"].items() if not ok]
        verdict = "yes" if v["retain"] else f"no ({', '.join(failed)})"
        ex = v["artefact_excess"]
        lines.append(
            f"| {d.replace('_', ' ')} | {_p(v['recall'])} | {_p(v['incremental'])} | {_p(v['null_rate'])} "
            f"({_p(v.get('null_reference'))}) | {'-' if ex is None else f'{ex:+.1%}'} | {verdict} |"
        )
    lines += ["", "## Plants in real series", "",
              f"{s['quiet_series']:,} series that no detector flagged were eligible; plants per kind: "
              + ", ".join(f"{k.replace('_', ' ')} {n:,}" for k, n in sorted(s["plants"].items())) + ". "
              "Each cell: the share caught where the detector could test (testable plants in brackets).", "",
              "| Detector | " + " | ".join(k.replace("_", " ") for k in (*INJECTIONS, *NULLS)) + " |",
              "|---|" + "---:|" * (len(INJECTIONS) + len(NULLS))]  # fmt: skip
    for d, res in s["detectors"].items():
        lines.append(f"| {d.replace('_', ' ')} | " + " | ".join(
            f"{_p(res[k]['recall'])} ({res[k]['testable']})" for k in (*INJECTIONS, *NULLS)) + " |")  # fmt: skip
    lines.append("| any day-4 detector (of all plants) | " + " | ".join(
        _p(s["day4_any"][k]) for k in (*INJECTIONS, *NULLS)) + " |")  # fmt: skip
    lines += ["", "Common: the jump planted in a series and its peers and counterpart alike; a contextual detector "
              "should leave it to its context, where day 4's band flags it.", "",
              "## Artefacts", "", "Flags per quiet count series when every count source carries the artefact.", "",
              "| Detector | Volume jump (last 3 months) | Duplicated period |", "|---|---:|---:|"]  # fmt: skip
    for d in (*DAY4, *NEW_SERIES, "day4_any"):
        lines.append(f"| {d.replace('_', ' ')} | {_p(s['artefacts']['volume_jump'][d])} | "
                     f"{_p(s['artefacts']['duplicated_period'][d])} |")  # fmt: skip
    b = result.get("backtest")
    if b:
        lines += [
            "",
            "## Backtest",
            "",
            f"The series chain at {len(b['dates'])} dates from {b['dates'][0]} to "
            f"{b['dates'][-1]}, point in time. An onset is a flag absent at the date before; it is confirmed "
            f"when day 4's trend or acceleration agrees in direction {cfg.evaluation.backtest.confirm_months} "
            "months later. Label-free: the owner's hindsight set (design §11.3) is the real test.",
            "",
            "| Detector | Onsets | Confirmed | Reversed | Median lead (months) |",
            "|---|---:|---:|---:|---:|",
        ]
        for d, v in b["detectors"].items():
            lead = "-" if v["median_lead_months"] is None else f"{v['median_lead_months']:.0f}"
            name = "day-4 band anomaly (benchmark)" if d == "anomaly" else d.replace("_", " ")
            lines.append(f"| {name} | {v['onsets']:,} | {_p(v['confirmation_rate'])} | {_p(v['reversal_rate'])} | "
                         f"{lead} |")  # fmt: skip
    r = result.get("relationships")
    if r:
        lines += ["", "## Relationships", "", "Placebo: window and baseline items (or months, for IP RAPID) "
                  f"reassigned at random, {len(r['placebo'])} times; detections per test. Synthetic: established "
                  "pairs broken in the window (keyphrase pairs: one side removed where they met; class pairs cut "
                  "to a fifth), country-class pairs cut to a fifth or tripled.", "",
                  "| Pairs | Real: fading | Real: new / rising | Placebo: fading per test | Placebo: new or rising "
                  "per test |", "|---|---:|---:|---:|---:|"]  # fmt: skip
        for g in ("kp", "class", "country"):
            real = r["real"].get(g, {})
            pf = sum(p[g]["fading"] for p in r["placebo"] if g in p)
            pt = sum(p[g]["tested_fade"] for p in r["placebo"] if g in p)
            pr = sum(p[g]["new"] + p[g]["rising"] for p in r["placebo"] if g in p)
            prt = sum(p[g]["tested_rise"] for p in r["placebo"] if g in p)
            name = {"kp": "keyphrases", "class": "IPC and Nice classes", "country": "countries by class"}[g]
            lines.append(f"| {name} | {real.get('fading', 0):,} | {real.get('new', 0):,} / {real.get('rising', 0):,} "
                         f"| {_p(pf / pt if pt else None)} | {_p(pr / prt if prt else None)} |")  # fmt: skip
        if r.get("kp_skipped"):
            lines += ["", f"Keyphrase pairs were not tested in this run: {r['kp_skipped']}"]
        lines += ["", "| Synthetic | Planted | Caught |", "|---|---:|---:|"]
        for k, v in r["synthetic"].items():
            lines.append(f"| {k.replace('_', ' ')} | {v['planted']:,} | {v['caught']:,} |")
    lines.append("")
    return "\n".join(lines)
