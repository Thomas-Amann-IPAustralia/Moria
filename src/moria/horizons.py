"""Multi-horizon measures for `moria measure series` (the SignalBoost proposal's item 1; D-025).

Each horizon (in months, `config/detect.yaml` `horizons`) is converted to the series' own periods (6 months = 2
quarters = 182 days; a horizon shorter than one period is not tested) and read by the method that suits it:
- **short** (3 and 6 months): the mean of the latest periods against the Theil-Sen line of the trailing baseline
  before them, with a band from the baseline's own rolling means (so that persistence in the noise widens it): a
  short-term shift, an anomaly that has lasted the horizon;
- **medium** (12 and 36 months): Theil-Sen and Mann-Kendall over the horizon: a sustained trend;
- **long** (60, 120 and 180 months): the same over the long window, and its last structural break, by the change-point
  search day 4 calibrated (optimal partitioning at 3 times BIC), in slope and in level about the long-run line.

Minimum history: a horizon is tested only where the series has it (`min_points`, the share of periods present, and
the baseline of a short horizon). Holm adjusts within each test family, horizon and method. The horizons of one
series overlap: they are views of one set of numbers, never corroboration of each other, so a series is one line
of evidence however many horizons fire (`horizons_fired`, `horizon_profile`).

Writes nothing itself: `measures.py` adds `horizons.parquet` and the profile columns of `measures.parquet`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

import numpy as np
import pyarrow as pa
from numpy.lib.stride_tricks import sliding_window_view

from . import stats
from .config import DetectConfig

F64 = pa.float64()
HORIZONS = pa.schema(
    [
        ("series_id", pa.string()),
        ("source", pa.string()),
        ("frequency", pa.string()),
        ("horizon_months", pa.int16()),
        ("method", pa.string()),  # short, medium or long
        ("periods", pa.int32()),
        ("window_start", pa.string()),
        ("window_end", pa.string()),
        ("n", pa.int32()),  # periods present in the horizon
        ("effect", F64),  # short: the shift (a ratio minus 1 for counts, over the level for statistics);
        # medium and long: the yearly growth (a log slope for counts, the slope over the level for statistics)
        ("lo", F64),  # Sen's interval of the slope (medium, long)
        ("hi", F64),
        ("observed", F64),  # short: the horizon's mean, on the tested scale
        ("expected", F64),  # short: the baseline line's mean over the horizon
        ("z", F64),
        ("p", F64),
        ("p_holm", F64),
        ("sig", pa.bool_()),
        ("direction", pa.int8()),
        ("break_slope_period", pa.string()),  # long: the last change in slope
        ("break_slope_change", F64),  # in yearly growth (counts) or yearly slope over the level (statistics)
        ("break_level_period", pa.string()),  # long: the last change in level about the long-run line
        ("break_level_change", F64),
        ("structural", pa.bool_()),  # a break of at least the acceleration (slope) or anomaly (level) size
        ("structural_direction", pa.int8()),
    ]
)


def periods_of(kind: str, months: int, per_year: dict[str, int]) -> int:
    """A horizon in the series' own periods, rounded down (91 days for 3 months); 0 when shorter than a period."""
    return int(months * per_year[kind] / 12 + 1e-9)


def _scale(g, k: int) -> float:
    """1 for counts (log scale); the median absolute level of the last 48 points for statistics."""
    if g.transform[k] != "level":
        return 1.0
    vals = [abs(v) for _, v in sorted(g.series[k].points.items())[-48:]]
    med = float(np.median(vals)) if vals else 0.0
    return med if med > 0 else float("nan")


def _f(v) -> float | None:
    return float(v) if v is not None and np.isfinite(v) else None


def measure_group(g, cfg: DetectConfig, as_of: date, valid: np.ndarray, index_label, aligned, per_year) -> list[dict]:
    """Every horizon of one source and frequency, for the rows day 4 would test (`valid`)."""
    hc, sc = cfg.horizons, cfg.series
    out: list[dict] = []
    scales = np.array([_scale(g, k) for k in range(len(g.ids))])
    for months in hc.months(g.source):
        p = periods_of(g.kind, months, per_year)
        if p < 1:
            continue
        method = hc.method(months)
        if method == "short":
            out += _short(g, cfg, months, p, valid, scales, index_label, aligned)
        else:
            min_points = hc.medium.min_points if method == "medium" else hc.long.min_points
            if p < min_points:
                continue
            out += _trend(g, cfg, months, p, method, min_points, valid, scales, index_label, aligned, per_year)
    for r in out:
        r.setdefault("structural", False)
    del sc
    return out


def _excluded(g, aligned, width: int) -> np.ndarray:
    return aligned(np.broadcast_to(g.excluded.astype(float), g.y.shape).copy(), g.last, g.base, width) == 1


def _short(g, cfg, months, p, valid, scales, index_label, aligned) -> list[dict]:
    hc, sc = cfg.horizons.short, cfg.series
    b = max(sc.anomaly_baseline[g.kind], hc.baseline_factor * p)
    mat = aligned(g.y, g.last, g.base, b + p)
    ex = _excluded(g, aligned, b + p)
    cnt_den = aligned(g.denom, g.last, g.base, b + p)
    base, rec = mat[:, :b], mat[:, b:]
    exp_base = np.maximum((~ex[:, :b]).sum(axis=1), 1)
    rec_present = (~np.isnan(rec)).sum(axis=1)
    ok = (valid & (np.sum(~np.isnan(base), axis=1) >= np.maximum(4, hc.min_baseline * exp_base))
          & (rec_present == (~ex[:, b:]).sum(axis=1)) & (rec_present >= 1))  # fmt: skip
    if not ok.any():
        return []
    rows_k = np.nonzero(ok)[0]
    base, rec, den = base[rows_k], rec[rows_k], cnt_den[rows_k, b:]
    x = np.arange(b, dtype=float)
    ts = stats.theil_sen(x, base)
    xr = np.arange(b, b + p, dtype=float)
    pred = ts["intercept"][:, None] + ts["slope"][:, None] * xr[None, :]
    pred = np.where(np.isnan(rec), np.nan, pred)
    resid = base - (ts["intercept"][:, None] + ts["slope"][:, None] * x[None, :])
    with np.errstate(all="ignore"):
        obs_mean, pred_mean = np.nanmean(rec, axis=1), np.nanmean(pred, axis=1)
        roll = np.nanmean(sliding_window_view(resid, p, axis=1), axis=2) if p > 1 else resid
        sigma = stats.robust_sigma(roll)
        transform = np.array([g.transform[k] for k in rows_k])
        exp_count = np.nansum(np.where(transform[:, None] == "log_share", np.exp(pred) * den, np.exp(pred)), axis=1)
        floor = np.where(transform == "level", 1e-9 * (np.abs(pred_mean) + 1), 1 / np.sqrt(np.maximum(exp_count, 1)))
        z = (obs_mean - pred_mean) / np.maximum(np.nan_to_num(sigma), floor)
        spread = np.maximum(np.abs(pred_mean), stats.robust_sigma(base))
        diff = obs_mean - pred_mean
        effect = np.where(transform == "level", diff / spread, np.exp(diff) - 1)
    pv = 2 * stats.norm.sf(np.abs(z))
    out = []
    for n, k in enumerate(rows_k):
        if not np.isfinite(z[n]):
            continue
        last = int(g.last[k])
        out.append({"series_id": g.ids[k], "source": g.source, "frequency": g.kind, "horizon_months": months,
                    "method": "short", "periods": p, "window_start": index_label(g.kind, last - p + 1),
                    "window_end": index_label(g.kind, last), "n": int(rec_present[k]), "effect": _f(effect[n]),
                    "observed": _f(obs_mean[n]), "expected": _f(pred_mean[n]), "z": _f(z[n]), "p": _f(pv[n]),
                    "direction": int(np.sign(z[n])), "_family": f"{_test_family(g, k)}|h{months}"})  # fmt: skip
    return out


def _test_family(g, k: int) -> str:
    from .measures import _family

    return _family(g, k)


def _trend(g, cfg, months, p, method, min_points, valid, scales, index_label, aligned, per_year) -> list[dict]:
    sc = cfg.series
    mat = aligned(g.y, g.last, g.base, p)
    ex = _excluded(g, aligned, p)
    expected = np.maximum((~ex).sum(axis=1), 1)
    present = np.sum(~np.isnan(mat), axis=1)
    ok = valid & (present >= sc.min_coverage * expected) & (present >= min_points)
    rows_k = np.nonzero(ok)[0]
    if not len(rows_k):
        return []
    x = np.arange(p, dtype=float)
    out = []
    for chunk in np.array_split(rows_k, max(1, int(np.ceil(len(rows_k) * p * p / 2e7)))):
        m = mat[chunk]
        ts = stats.theil_sen(x, m, sc.alpha)
        mk = stats.mann_kendall(m)
        if method == "long" and cfg.horizons.long.autocorrelation:
            # long windows of yearly or monthly points are autocorrelated: Mann-Kendall's variance is inflated
            infl = stats.lag1_inflation(m, x)
            mk["z"] = mk["z"] / np.sqrt(infl)
            mk["p"] = np.where(np.isnan(mk["p"]), np.nan, 2 * stats.norm.sf(np.abs(mk["z"])))
        brk = _breaks(g, cfg, m, chunk, scales, per_year) if method == "long" else {}
        for n, k in enumerate(chunk):
            if not np.isfinite(ts["slope"][n]):
                continue
            last = int(g.last[k])
            yearly = per_year[g.kind] / scales[k]
            row = {"series_id": g.ids[k], "source": g.source, "frequency": g.kind, "horizon_months": months,
                   "method": method, "periods": p, "window_start": index_label(g.kind, last - p + 1),
                   "window_end": index_label(g.kind, last), "n": int(present[k]),
                   "effect": _f(ts["slope"][n] * yearly), "lo": _f(ts["lo"][n] * yearly),
                   "hi": _f(ts["hi"][n] * yearly), "z": _f(mk["z"][n]), "p": _f(mk["p"][n]),
                   "_family": f"{_test_family(g, k)}|h{months}"}  # fmt: skip
            b = brk.get(int(k))
            if b:
                start = last - p + 1
                row.update(
                    break_slope_period=index_label(g.kind, start + b["slope_col"]) if b.get("slope_col") is not None
                    else None, break_slope_change=_f(b.get("slope_change")),
                    break_level_period=index_label(g.kind, start + b["level_col"]) if b.get("level_col") is not None
                    else None, break_level_change=_f(b.get("level_change")),
                    structural=b["structural"], structural_direction=b["direction"])  # fmt: skip
            out.append(row)
    return out


def _breaks(g, cfg, mat: np.ndarray, rows_k: np.ndarray, scales: np.ndarray, per_year) -> dict[int, dict]:
    """The last break in slope and in level over each row's long window (rows grouped by their missing periods)."""
    cp, sc = cfg.series.change_points, cfg.series
    seg = max(periods_of(g.kind, cfg.horizons.long.min_segment_months, per_year), cp.min_size[g.kind])
    patterns: dict[tuple, list[int]] = defaultdict(list)
    for n in range(len(rows_k)):
        patterns[tuple(np.nonzero(~np.isnan(mat[n]))[0])].append(n)
    out: dict[int, dict] = {}
    for cols, ns in patterns.items():
        cols = np.array(cols)
        if len(cols) < 2 * seg:
            continue
        y = mat[np.ix_(ns, cols)]
        x = cols.astype(float)
        pen = cfg.horizons.long.penalty_factor
        lin = stats.change_points(y, x, "linear", seg, pen)
        ts = stats.theil_sen(x, y)
        resid = y - (ts["intercept"][:, None] + ts["slope"][:, None] * x[None, :])
        lev = stats.change_points(resid, x, "mean", seg, pen)
        for j, n in enumerate(ns):
            k = int(rows_k[n])
            res = {"structural": False, "direction": 0}
            if lin[j]:
                c = lin[j][-1]
                prev = lin[j][-2] if len(lin[j]) > 1 else 0
                before, after = stats.ols_slope(x[prev:c], y[j, prev:c]), stats.ols_slope(x[c:], y[j, c:])
                change = (after - before) * per_year[g.kind] / scales[k]
                res.update(slope_col=int(cols[c]), slope_change=change)
                if np.isfinite(change) and abs(change) >= sc.accel_min_change:
                    res.update(structural=True, direction=int(np.sign(change)))
            if lev[j]:
                c = lev[j][-1]
                prev = lev[j][-2] if len(lev[j]) > 1 else 0
                shift = float(np.mean(resid[j, c:]) - np.mean(resid[j, prev:c]))
                if g.transform[k] == "level":
                    size = abs(shift) / max(abs(float(np.mean(y[j]))), float(stats.robust_sigma(y[j][None])[0]), 1e-12)
                    change = shift / max(abs(float(np.mean(y[j]))), 1e-12)
                else:
                    size = change = float(np.exp(shift)) - 1
                    size = abs(size)
                res.update(level_col=int(cols[c]), level_change=change)
                if size >= sc.anomaly_min_change and not res["structural"]:
                    res.update(structural=True, direction=int(np.sign(shift)))
            out[k] = res
    return out


def adjust(rows: list[dict], cfg: DetectConfig) -> None:
    """Holm within each test family and horizon; then each row's decision."""
    h = stats.holm(np.array([np.nan if r.get("p") is None else r["p"] for r in rows]), [r["_family"] for r in rows])
    hc, sc = cfg.horizons, cfg.series
    for r, hv in zip(rows, h, strict=True):
        r["p_holm"] = _f(hv)
        r.pop("_family")
        if r["method"] == "short":
            r["sig"] = bool(r["p_holm"] is not None and r["p_holm"] < hc.short.alpha
                            and abs(r["effect"] or 0) >= hc.short.min_change)  # fmt: skip
        else:
            lo, hi = r.get("lo"), r.get("hi")
            r["sig"] = bool(r["p_holm"] is not None and r["p_holm"] < sc.alpha and lo is not None
                            and (lo > 0 or hi < 0))  # fmt: skip
            r["direction"] = (1 if lo > 0 else -1) if r["sig"] else 0
        r.setdefault("structural_direction", 0)


def profile(hrows: list[dict]) -> dict[str, tuple[str | None, list[str]]]:
    """Per series: (its horizon profile, the horizons that fired), from short-term to structural:
    - structural_shift: a break in the long-run path (slope or level);
    - reversal: a long-run trend and a medium-term trend in opposite directions;
    - sustained: a medium-term trend;
    - long_run: a long-run trend only;
    - transient: a short-term shift only."""
    by: dict[str, list[dict]] = defaultdict(list)
    for r in hrows:
        by[r["series_id"]].append(r)
    out = {}
    for sid, rs in by.items():
        fired = []
        for r in sorted(rs, key=lambda r: r["horizon_months"]):
            if r["sig"]:
                fired.append(f"{r['horizon_months']}m{'+' if r['direction'] > 0 else '-'}")
            if r.get("structural"):
                fired.append(f"{r['horizon_months']}m break{'+' if r['structural_direction'] > 0 else '-'}")
        dirs = {m: {r["direction"] for r in rs if r["method"] == m and r["sig"]} for m in ("short", "medium", "long")}
        structural = any(r.get("structural") for r in rs)
        medium = dirs["medium"].pop() if len(dirs["medium"]) == 1 else 0
        long = dirs["long"].pop() if len(dirs["long"]) == 1 else 0
        if structural:
            prof = "structural_shift"
        elif medium and long and medium != long:
            prof = "reversal"
        elif medium:
            prof = "sustained"
        elif long:
            prof = "long_run"
        elif dirs["short"]:
            prof = "transient"
        else:
            prof = None
        out[sid] = (prof, fired)
    return out
