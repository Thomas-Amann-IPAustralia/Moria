"""`moria measure series --as-of D`: the whole-taxonomy detectors over every count and statistical series (design
§8.1, §8.2, §8.5; day 4), at a point in time.

Reads the latest passed `normalise` run (`lake/series`, `lake/observations`) and `ipr.metrics` run
(`lake/ipr_metrics`). For each series it takes, at `as_of`, each period's value from the latest vintage observable by
then (the earliest vintage when none is: backfilled history has no true first sighting), and drops the period that
contains `as_of` (never complete), the source's lagged periods (`config/detect.yaml`) and IP RAPID's release month.

**Rates per source volume.** A count is tested as its share of the source's volume in the same period (design §8.3):
an OpenAlex topic over all works in the same scope and period, a CPC subclass over all subclasses, a GDELT query
group over every document, an IP RAPID split over all applications of that right. Counts are tested on a log scale
(the slope is a growth rate); statistics (ABS, OECD) on their own scale.

Per series:
- **trend** (design §8.2): Theil-Sen slope with Sen's interval and Mann-Kendall's test in three windows (12, 24 and
  36 months; longer for annual and quarterly series, `windows`), Holm-adjusted within each family of series (source,
  frequency, taxonomy level or dataflow, scope) and window; Benjamini-Hochberg's q is kept beside it, for the owner;
- **acceleration**: the recent half's slope minus the earlier half's, bootstrap standard error, Holm; and the last
  change in slope (optimal partitioning, PELT's objective) when it is to a steeper slope;
- **anomaly**: the latest value against the band of a Theil-Sen line fitted to the periods before it, family-wise
  (Holm) at 99%; and a recent change in level;
- **low-base surge**: the latest periods' count against a low trailing baseline, exact Poisson test, rate per
  source volume;
- **divergence** (design §8.5): Australia's share against the world's (or the OECD's) for the same topic, subclass,
  query group or indicator, tested for a trend like any series.

Writes `measures/series/as_of=<D>/measures.parquet` (one row per series tested) and `divergence.parquet` (one row per
pair). Labels stay in the private bucket; nothing here is text from a source.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa

from . import stats
from .config import DetectConfig
from .iprmetrics import COMMAND as IPRM
from .manifest import Manifest
from .normalise import COMMAND as NORMALISE
from .store import Store
from .tables import STRS, cache_root, fetch_outputs, upload, upstream, write_rows

log = logging.getLogger("moria.measures")

COMMAND = "measure.series"
KINDS = {"year": "A", "quarter": "Q", "month": "M", "day": "D"}
PER_YEAR = {"A": 1, "Q": 4, "M": 12, "D": 365}
AU_SCOPES = {"au", "AUS"}

F32 = pa.float64()
_TREND = [(f"trend_w{k}_{c}", t) for k in (1, 2, 3) for c, t in
          (("periods", pa.int16()), ("n", pa.int16()), ("slope", F32), ("lo", F32), ("hi", F32), ("p", F32),
           ("p_holm", F32), ("q_bh", F32), ("sig", pa.bool_()))]  # fmt: skip
MEASURES = pa.schema(
    [
        ("series_id", pa.string()),
        ("source", pa.string()),
        ("family", pa.string()),  # the source family (statistics, research, patent, news...)
        ("test_family", pa.string()),  # the family of tests Holm adjusts within
        ("frequency", pa.string()),
        ("transform", pa.string()),  # log_share, log_count or level
        ("denominator", pa.string()),
        ("label", pa.string()),
        ("scope", pa.string()),
        ("rings", STRS),
        ("first_period", pa.string()),
        ("last_period", pa.string()),
        ("n_points", pa.int32()),
        ("mean_count", F32),  # count series: mean count per period over the shortest window
        *_TREND,
        ("trend_windows", pa.int8()),  # windows evaluable
        ("trend_sig", pa.int8()),  # windows significant after Holm
        ("trend_dir", pa.int8()),  # +1 rising, -1 falling, 0 none
        ("trend_growth", F32),  # per year: a log slope for counts, the slope over the median level for statistics
        ("accel_periods", pa.int16()),
        ("accel_early", F32),
        ("accel_recent", F32),
        ("accel_diff", F32),
        ("accel_lo", F32),
        ("accel_hi", F32),
        ("accel_p", F32),
        ("accel_p_holm", F32),
        ("accel_change", F32),  # the change in yearly growth (counts), or in yearly slope over the level (statistics)
        ("accel", pa.bool_()),
        ("cp_slope_period", pa.string()),
        ("cp_slope_before", F32),
        ("cp_slope_after", F32),
        ("cp_slope_change", F32),  # as accel_change
        ("cp_steeper", pa.bool_()),
        ("cp_level_period", pa.string()),
        ("cp_level_before", F32),
        ("cp_level_after", F32),
        ("cp_level_change", F32),  # the shift about the trend line, as anom_change
        ("cp_level_recent", pa.bool_()),
        ("anom_period", pa.string()),
        ("anom_value", F32),
        ("anom_expected", F32),
        ("anom_z", F32),
        ("anom_p", F32),
        ("anom_p_holm", F32),
        ("anom_change", F32),  # how far off the expected value: a ratio minus 1 (counts), or over the level or spread
        ("anomaly", pa.bool_()),
        ("surge_window", pa.string()),  # first and last period of the surge window
        ("surge_count", F32),
        ("surge_baseline", F32),
        ("surge_expected", F32),
        ("surge_ratio", F32),
        ("surge_p", F32),
        ("surge_p_holm", F32),
        ("surge", pa.bool_()),
        ("volume_change", F32),  # the source volume over the shortest window against the window before it, minus 1
        ("surge_volume_change", F32),  # the volume per period in the surge window against its baseline, minus 1
    ]
)
_DTREND = [(f"w{k}_{c}", t) for k in (1, 2, 3) for c, t in
           (("n", pa.int16()), ("slope", F32), ("lo", F32), ("hi", F32), ("p", F32), ("p_holm", F32),
            ("sig", pa.bool_()))]  # fmt: skip
DIVERGENCE = pa.schema(
    [
        ("pair_id", pa.string()),
        ("source", pa.string()),
        ("au_series", pa.string()),
        ("ref_series", pa.string()),
        ("ref_scope", pa.string()),
        ("label", pa.string()),
        ("frequency", pa.string()),
        ("transform", pa.string()),  # log_share: the log of AU's share over the reference's; level: the difference
        ("last_period", pa.string()),
        *_DTREND,
        ("windows", pa.int8()),
        ("sig", pa.int8()),
        ("direction", pa.int8()),  # +1 Australia gaining on the reference, -1 falling behind
        ("growth", F32),
        ("au_trend_dir", pa.int8()),
        ("ref_trend_dir", pa.int8()),
    ]
)


# ------------------------------------------------------------------------------------------------- periods, values


def period_index(kind: str, start: date) -> int:
    if kind == "A":
        return start.year
    if kind == "Q":
        return start.year * 4 + (start.month - 1) // 3
    if kind == "M":
        return start.year * 12 + start.month - 1
    return start.toordinal()


def index_label(kind: str, i: int) -> str:
    if kind == "A":
        return str(i)
    if kind == "Q":
        return f"{i // 4}-Q{i % 4 + 1}"
    if kind == "M":
        return f"{i // 12}-{i % 12 + 1:02d}"
    return date.fromordinal(i).isoformat()


def period_index_of_label(kind: str, label: str | None) -> int | None:
    """The inverse of index_label."""
    if not label:
        return None
    try:
        if kind == "A":
            return int(label)
        if kind == "Q":
            y, q = label.split("-Q")
            return int(y) * 4 + int(q) - 1
        if kind == "M":
            return int(label[:4]) * 12 + int(label[5:7]) - 1
        return date.fromisoformat(label).toordinal()
    except ValueError:
        return None


def current_index(kind: str, as_of: date) -> int:
    """The index of the period that contains as_of: never complete, so the last usable period is the one before."""
    return period_index(kind, as_of)


@dataclass
class Series:
    series_id: str
    source: str
    kind: str
    meta: dict
    points: dict[int, float] = field(default_factory=dict)


def as_of_end(as_of: date) -> datetime:
    """A scan at as_of sees what was observable by the end of that UTC day."""
    return datetime(as_of.year, as_of.month, as_of.day, tzinfo=UTC) + timedelta(days=1)


def load_series(paths: list[tuple[Path, Path]], sources: set[str], as_of: date) -> dict[str, Series]:
    """Every series of the listed sources at as_of: each period's latest vintage observable by then (else the
    earliest), periods ending after as_of left out, values marked incomplete left out."""
    end = as_of_end(as_of).strftime("%Y-%m-%d %H:%M:%S+00")
    out: dict[str, Series] = {}
    con = duckdb.connect()
    for series_path, obs_path in paths:
        meta_rows = con.execute(
            "SELECT series_id, source, label, unit, scope, dimensions, family, rings FROM read_parquet(?)",
            [series_path.as_posix()],
        ).fetchall()
        metas = {r[0]: r for r in meta_rows if r[1] in sources}
        if not metas:
            continue
        rows = con.execute(
            f"""SELECT series_id, period_kind, period_start, value FROM (
                  SELECT *, row_number() OVER (PARTITION BY series_id, period ORDER BY
                    (vintage_at <= TIMESTAMPTZ '{end}') DESC,
                    CASE WHEN vintage_at <= TIMESTAMPTZ '{end}' THEN vintage_at END DESC NULLS LAST,
                    vintage_at ASC) AS rn
                  FROM read_parquet(?) WHERE period_kind IN ('year', 'quarter', 'month', 'day'))
                WHERE rn = 1 AND value IS NOT NULL AND isfinite(value) AND coalesce(status, '') <> 'incomplete'
                ORDER BY series_id, period_start""",
            [obs_path.as_posix()],
        ).fetchall()
        for sid, pk, start, value in rows:
            m = metas.get(sid)
            if m is None:
                continue
            kind = KINDS[pk]
            s = out.get(sid)
            if s is None:
                meta = {
                    "label": m[2],
                    "unit": m[3],
                    "scope": m[4],
                    "dimensions": m[5],
                    "family": m[6],
                    "rings": list(m[7]),
                }
                s = out[sid] = Series(sid, m[1], kind, meta)
            elif s.kind != kind:
                continue  # one period kind per series: the first seen
            s.points[period_index(kind, start)] = float(value)
    for s in out.values():
        cur = current_index(s.kind, as_of)
        s.points = {i: v for i, v in s.points.items() if i < cur}
    return {k: v for k, v in out.items() if v.points}


# --------------------------------------------------------------------------------------------- roles of a series


def role(s: Series) -> tuple[str, str | None, str]:
    """(transform, denominator series id or None, test family group) for a series."""
    parts = s.series_id.split("|")
    src = s.source
    if src == "openalex_counts":
        level, scope, kind = parts[1], parts[-2], parts[-1]
        if level == "total":
            return "log_count", None, "total"
        return "log_share", f"openalex_counts|total|{scope}|{kind}", level
    if src == "patent_cpc_counts":
        return "log_share", f"patent_cpc_counts|*|{parts[-1]}", "cpc"
    if src == "gdelt_news":
        if parts[1] == "total":
            return "log_count", None, "total"
        return "log_share", f"gdelt_news|total|{parts[2]}", parts[3]
    if src == "ip_rapid_metrics":
        metric, right = parts[1], parts[2]
        if s.meta.get("unit") == "days":
            return "level", None, metric
        if metric == "applications" and parts[3] == "all":
            return "log_count", None, "applications_all"
        if metric.startswith("applications") or metric in ("first_time_applicants", "madrid_designating_au"):
            return "log_share", f"ip_rapid_metrics|applications|{right}|all", metric
        return "log_count", None, metric
    # statistics (ABS, OECD): levels, families by dataflow
    return "level", None, parts[1] if len(parts) > 1 else "all"


def synthetic_totals(series: dict[str, Series]) -> None:
    """Totals that the sources don't publish: all CPC subclasses together, per scope and year."""
    sums: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for s in series.values():
        if s.source == "patent_cpc_counts":
            for i, v in s.points.items():
                sums[s.series_id.split("|")[-1]][i] += v
    for scope, pts in sums.items():
        sid = f"patent_cpc_counts|*|{scope}"
        series[sid] = Series(sid, "patent_cpc_counts", "A", {"label": "All CPC subclasses", "unit": "families",
                             "scope": scope, "dimensions": "{}", "family": "patent", "rings": ["adjacent"],
                             "synthetic": True}, dict(pts))  # fmt: skip


# ---------------------------------------------------------------------------------------------------- the matrices


def aligned(dense: np.ndarray, last: np.ndarray, base: int, width: int) -> np.ndarray:
    """Per row, the `width` columns ending at that row's last index (NaN before the matrix starts)."""
    cols = last[:, None] - base - (width - 1) + np.arange(width)[None, :]
    out = np.take_along_axis(dense, np.clip(cols, 0, dense.shape[1] - 1), axis=1)
    out[cols < 0] = np.nan
    return out


@dataclass
class Group:
    """One source's series of one frequency, as dense matrices over the period index."""

    source: str
    kind: str
    ids: list[str]
    series: list[Series]
    base: int
    counts: np.ndarray  # raw values (counts or levels)
    y: np.ndarray  # the tested quantity
    denom: np.ndarray  # the denominator per period (1 where there is none)
    last: np.ndarray  # each row's last usable index
    transform: list[str]
    denominators: list[str | None]
    groups: list[str]
    excluded: np.ndarray  # columns of excluded calendar months


def build_group(source: str, kind: str, members: list[Series], all_series: dict[str, Series], cfg: DetectConfig,
                as_of: date) -> Group | None:  # fmt: skip
    sc = cfg.series
    roles = [role(s) for s in members]
    cur = current_index(kind, as_of)
    lo = min(min(s.points) for s in members)
    hi = cur - 1
    t = hi - lo + 1
    if t <= 0:
        return None
    r = len(members)
    counts = np.full((r, t), np.nan)
    denom = np.ones((r, t))
    last = np.zeros(r, dtype=int)
    for k, (s, (transform, dname, _)) in enumerate(zip(members, roles, strict=True)):
        limit = hi - sc.lag(s.series_id)
        pts = {i: v for i, v in s.points.items() if i <= limit}
        if not pts:
            last[k] = lo - 1
            continue
        if transform != "level":
            # a count absent in a period the source covered is a zero (taxonomy counts list non-zero groups only)
            d = all_series.get(dname) if dname else None
            span = sorted(d.points) if d else sorted(pts)
            first = min(pts)
            for i in span:
                if first <= i <= limit:
                    pts.setdefault(i, 0.0)
            if d:
                for i, v in d.points.items():
                    if lo <= i <= hi:
                        denom[k, i - lo] = v
                for i in list(pts):
                    if i not in d.points:
                        del pts[i]  # no volume to rate it against
        for i, v in pts.items():
            counts[k, i - lo] = v
        last[k] = max(pts) if pts else lo - 1
    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.where(
            np.array([tr == "log_share" for tr, _, _ in roles])[:, None],
            np.log((counts + 0.5) / denom),
            np.where(np.array([tr == "log_count" for tr, _, _ in roles])[:, None], np.log(counts + 0.5), counts),
        )
    excluded = np.zeros(t, dtype=bool)
    months = sc.exclude_months.get(source, [])
    if kind == "M" and months:
        excluded = np.array([(lo + c) % 12 + 1 in months for c in range(t)])
        y[:, excluded] = np.nan
    return Group(source, kind, [s.series_id for s in members], members, lo, counts, y, denom, last,
                 [x[0] for x in roles], [x[1] for x in roles], [x[2] for x in roles], excluded)  # fmt: skip


# ------------------------------------------------------------------------------------------------------- measures


def _family(g: Group, k: int) -> str:
    scope = g.series[k].meta.get("scope") or ""
    scope = "au" if scope in AU_SCOPES else scope if scope in ("world", "OECD") else "other"
    return f"{g.source}|{g.kind}|{g.groups[k]}|{scope}"


def trend_windows(mats: list[tuple[np.ndarray, np.ndarray]], widths: list[int], min_cov: float, alpha: float,
                  valid: np.ndarray) -> list[dict]:  # fmt: skip
    """Theil-Sen and Mann-Kendall in each window (its values and its excluded months), for rows whose window is
    covered: at least `min_cov` of its expected periods present."""
    out = []
    for w, (mat, ex) in zip(widths, mats, strict=True):
        expected = np.maximum((~ex).sum(axis=1), 1)
        present = np.sum(~np.isnan(mat), axis=1)
        ok = valid & (present >= min_cov * expected) & (present >= 4)
        res = {"periods": w, "ok": ok, "n": present}
        x = np.arange(w, dtype=float)
        ts = stats.theil_sen(x, np.where(ok[:, None], mat, np.nan), alpha)
        mk = stats.mann_kendall(np.where(ok[:, None], mat, np.nan))
        res.update(slope=ts["slope"], lo=ts["lo"], hi=ts["hi"], p=np.where(ok, mk["p"], np.nan), z=mk["z"])
        out.append(res)
    return out


def _measure(g: Group, cfg: DetectConfig, as_of: date, counts: dict) -> list[dict]:
    sc = cfg.series
    kind, widths = g.kind, sc.windows[g.kind]
    r = len(g.ids)
    cur = current_index(kind, as_of)
    stale = g.last < (cur - 1 - sc.stale_after[kind])
    is_count = np.array([t != "level" for t in g.transform])
    has_data = g.last >= g.base
    mats = []
    for w in widths:
        m = aligned(g.y, g.last, g.base, w)
        ex = aligned(np.broadcast_to(g.excluded.astype(float), g.y.shape).copy(), g.last, g.base, w) == 1
        mats.append((m, ex))
    c1 = aligned(g.counts, g.last, g.base, widths[0])
    mean_count = _nanmean(c1)
    volume_ok = ~is_count | (np.nan_to_num(mean_count) >= sc.min_mean_count)
    valid = has_data & ~stale & volume_ok
    counts[f"stale_{g.source}"] += int((stale & has_data).sum())
    wins = trend_windows(mats, widths, sc.min_coverage, sc.alpha, valid)
    rows = []
    for k in range(r):
        s = g.series[k]
        if not has_data[k]:
            continue
        pts = sorted(i for i in s.points if i <= g.last[k])
        row = {
            "series_id": g.ids[k], "source": g.source, "family": s.meta.get("family"),
            "test_family": _family(g, k), "frequency": kind, "transform": g.transform[k],
            "denominator": g.denominators[k], "label": s.meta.get("label"), "scope": s.meta.get("scope"),
            "rings": _rings(s), "first_period": index_label(kind, pts[0]) if pts else None,
            "last_period": index_label(kind, int(g.last[k])), "n_points": len(pts),
            "mean_count": float(mean_count[k]) if is_count[k] and np.isfinite(mean_count[k]) else None,
            "_stale": bool(stale[k]),
        }  # fmt: skip
        for j, wr in enumerate(wins, 1):
            ok = bool(wr["ok"][k])
            row.update({f"trend_w{j}_periods": wr["periods"], f"trend_w{j}_n": int(wr["n"][k]) if ok else None,
                        f"trend_w{j}_slope": _f(wr["slope"][k]) if ok else None,
                        f"trend_w{j}_lo": _f(wr["lo"][k]) if ok else None,
                        f"trend_w{j}_hi": _f(wr["hi"][k]) if ok else None,
                        f"trend_w{j}_p": _f(wr["p"][k]) if ok else None})  # fmt: skip
        row["trend_windows"] = sum(1 for wr in wins if wr["ok"][k])
        rows.append(row)
    index = {row["series_id"]: n for n, row in enumerate(rows)}
    keep = np.array([g.ids[k] in index for k in range(r)])
    _acceleration(g, mats, wins, valid & keep, rows, index, cfg)
    _change_points(g, mats, wins, valid & keep, rows, index, cfg)
    _anomaly(g, has_data & ~stale & keep, rows, index, cfg)
    _surge(g, has_data & ~stale & keep & is_count, rows, index, cfg)
    _volume(g, has_data & keep & is_count, rows, index, cfg)
    return rows


def _nanmean(a: np.ndarray) -> np.ndarray:
    """Row means ignoring NaN; NaN for an empty row, without numpy's warning."""
    n = np.sum(~np.isnan(a), axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, np.nansum(a, axis=1) / np.maximum(n, 1), np.nan)


def _f(v) -> float | None:
    return float(v) if v is not None and np.isfinite(v) else None


def _rings(s: Series) -> list[str]:
    try:
        ring = (json.loads(s.meta.get("dimensions") or "{}") or {}).get("ring")
    except (ValueError, AttributeError):
        ring = None
    return [ring] if ring else list(s.meta.get("rings") or [])


def _acceleration(g: Group, mats, wins, valid, rows, index, cfg: DetectConfig) -> None:
    """On each row's longest evaluable window: the recent half's slope against the earlier half's."""
    sc = cfg.series
    done = np.zeros(len(g.ids), dtype=bool)
    for j in range(len(mats) - 1, -1, -1):
        ok = valid & wins[j]["ok"] & ~done
        if not ok.any():
            continue
        done |= ok
        mat = mats[j][0][ok]
        w = mat.shape[1]
        x = np.arange(w, dtype=float)
        half = w // 2
        early = stats.theil_sen(x[:half], mat[:, :half])["slope"]
        recent = stats.theil_sen(x[half:], mat[:, half:])["slope"]
        shape = (np.sign(recent) != 0) & (np.abs(recent) > np.abs(early)) & (np.sign(recent - early) == np.sign(recent))
        p = np.ones(ok.sum())
        lo = np.full(ok.sum(), np.nan)
        hi = np.full(ok.sum(), np.nan)
        diff = recent - early
        if shape.any():
            b = stats.bootstrap_slope_change(x, mat[shape], sc.bootstrap.reps, sc.bootstrap.seed, sc.alpha)
            p[shape] = np.nan_to_num(b["p"], nan=1.0)
            lo[shape], hi[shape] = b["lo"], b["hi"]
        for n, k in enumerate(np.nonzero(ok)[0]):
            row = rows[index[g.ids[k]]]
            row.update(accel_periods=w, accel_early=_f(early[n]), accel_recent=_f(recent[n]), accel_diff=_f(diff[n]),
                       accel_lo=_f(lo[n]), accel_hi=_f(hi[n]), accel_p=_f(p[n]))  # fmt: skip


def _change_points(g: Group, mats, wins, valid, rows, index, cfg: DetectConfig) -> None:
    """The last change in slope and in level, on each row's longest evaluable window (the periods it has)."""
    cp = cfg.series.change_points
    done = np.zeros(len(g.ids), dtype=bool)
    for j in range(len(mats) - 1, -1, -1):
        ok = valid & wins[j]["ok"] & ~done
        if not ok.any():
            continue
        done |= ok
        mat = mats[j][0]
        w = mat.shape[1]
        last = g.last
        patterns: dict[tuple, list[int]] = defaultdict(list)
        for k in np.nonzero(ok)[0]:
            patterns[tuple(np.nonzero(~np.isnan(mat[k]))[0])].append(int(k))
        for cols, ks in patterns.items():
            cols = np.array(cols)
            if len(cols) < 2 * cp.min_size_level[g.kind]:
                continue
            y = mat[np.ix_(ks, cols)]
            x = cols.astype(float)
            lin = stats.change_points(y, x, "linear", cp.min_size[g.kind], cp.penalty_factor)
            # a change in level is sought about the window's trend line, so that a trend is not read as steps
            ts = stats.theil_sen(x, y)
            resid = y - (ts["intercept"][:, None] + ts["slope"][:, None] * x[None, :])
            lev = stats.change_points(resid, x, "mean", cp.min_size_level[g.kind], cp.penalty_factor)
            for n, k in enumerate(ks):
                row = rows[index[g.ids[k]]]
                start = int(last[k]) - (w - 1)
                if lin[n]:
                    c = lin[n][-1]
                    prev = lin[n][-2] if len(lin[n]) > 1 else 0
                    before = stats.ols_slope(x[prev:c], y[n, prev:c])
                    after = stats.ols_slope(x[c:], y[n, c:])
                    row.update(cp_slope_period=index_label(g.kind, start + int(cols[c])), cp_slope_before=_f(before),
                               cp_slope_after=_f(after),
                               _cp_shape=bool(c >= len(cols) // 2 and np.isfinite(after) and np.isfinite(before)
                                              and abs(after) > abs(before) and after != 0
                                              and np.sign(after - before) == np.sign(after)))  # fmt: skip
                if lev[n]:
                    c = lev[n][-1]
                    prev = lev[n][-2] if len(lev[n]) > 1 else 0
                    recent = (len(cols) - c) <= cp.min_size_level[g.kind] + cp.recent[g.kind]
                    shift = float(np.mean(resid[n, c:]) - np.mean(resid[n, prev:c]))
                    if g.transform[k] == "level":
                        scale = max(abs(float(np.mean(y[n]))), float(stats.robust_sigma(y[n][None])[0]), 1e-12)
                        change = abs(shift) / scale
                    else:
                        change = abs(float(np.exp(shift)) - 1)
                    row.update(cp_level_period=index_label(g.kind, start + int(cols[c])),
                               cp_level_before=_f(np.mean(y[n, prev:c])), cp_level_after=_f(np.mean(y[n, c:])),
                               cp_level_change=_f(change), _cp_level_recent=bool(recent))  # fmt: skip


def _anomaly(g: Group, valid, rows, index, cfg: DetectConfig) -> None:
    """The latest value against a Theil-Sen line fitted on the periods before it, with a robust band."""
    b = cfg.series.anomaly_baseline[g.kind]
    mat = aligned(g.y, g.last, g.base, b + 1)
    cnt = aligned(g.counts, g.last, g.base, b + 1)
    den = aligned(g.denom, g.last, g.base, b + 1)
    base = mat[:, :b]
    ok = valid & (np.sum(~np.isnan(base), axis=1) >= max(4, int(0.75 * b))) & ~np.isnan(mat[:, b])
    if not ok.any():
        return
    x = np.arange(b, dtype=float)
    ts = stats.theil_sen(x, base)
    pred = ts["intercept"] + ts["slope"] * b
    resid = base - (ts["intercept"][:, None] + ts["slope"][:, None] * x[None, :])
    sigma = stats.robust_sigma(resid)
    transform = np.array(g.transform)
    with np.errstate(all="ignore"):
        exp_count = np.where(transform == "log_share", np.exp(pred) * den[:, b], np.exp(pred))
        floor = np.where(transform == "level", 1e-9 * (np.abs(pred) + 1), 1 / np.sqrt(np.maximum(exp_count, 1)))
        z = (mat[:, b] - pred) / np.maximum(np.nan_to_num(sigma), floor)
        spread = np.maximum(np.abs(pred), stats.robust_sigma(base))
        change = np.where(transform == "level", np.abs(mat[:, b] - pred) / spread, np.abs(np.exp(mat[:, b] - pred) - 1))
    p = 2 * stats.norm.sf(np.abs(z))
    for k in np.nonzero(ok)[0]:
        if not np.isfinite(z[k]):
            continue
        row = rows[index[g.ids[k]]]
        value = cnt[k, b]
        expected = exp_count[k] if transform[k] != "level" else pred[k]
        row.update(anom_period=index_label(g.kind, int(g.last[k])), anom_value=_f(value), anom_expected=_f(expected),
                   anom_z=_f(z[k]), anom_p=_f(p[k]), anom_change=_f(change[k]))  # fmt: skip


def _surge(g: Group, valid, rows, index, cfg: DetectConfig) -> None:
    """Low-base surges: the latest periods' count against the trailing baseline, as rates per source volume."""
    sv = cfg.series.surge
    w, bl = sv.window[g.kind], sv.baseline[g.kind]
    cnt = aligned(g.counts, g.last, g.base, w + bl)
    den = aligned(g.denom, g.last, g.base, w + bl)
    ok = valid & ~np.isnan(cnt).any(axis=1)
    if not ok.any():
        return
    x1, x0 = cnt[:, bl:].sum(axis=1), cnt[:, :bl].sum(axis=1)
    e1, e0 = den[:, bl:].sum(axis=1), den[:, :bl].sum(axis=1)
    p, ratio = stats.poisson_rate_test(x1, e1, x0, e0)
    with np.errstate(all="ignore"):
        expected = x0 * e1 / e0
    for k in np.nonzero(ok)[0]:
        row = rows[index[g.ids[k]]]
        first = index_label(g.kind, int(g.last[k]) - w + 1)
        row.update(surge_window=f"{first}/{index_label(g.kind, int(g.last[k]))}", surge_count=_f(x1[k]),
                   surge_baseline=_f(x0[k]), surge_expected=_f(expected[k]), surge_ratio=_f(ratio[k]),
                   surge_p=_f(p[k]) if x1[k] >= sv.min_count and expected[k] <= sv.max_expected else None,
                   surge_volume_change=_f((e1[k] / w) / (e0[k] / bl) - 1) if e0[k] > 0 else None)  # fmt: skip


def _volume(g: Group, valid, rows, index, cfg: DetectConfig) -> None:
    """The source's volume (the denominator, or the count itself for a total) over the shortest window against the
    window before it, for the coverage check (design §8.3)."""
    w = cfg.series.windows[g.kind][0]
    vol = np.where(np.array([d is None for d in g.denominators])[:, None], g.counts, g.denom)
    mat = aligned(vol, g.last, g.base, 2 * w)
    for k in np.nonzero(valid)[0]:
        prev, now = mat[k, :w], mat[k, w:]
        if np.isnan(prev).all() or np.isnan(now).all() or np.nansum(prev) <= 0:
            continue
        rows[index[g.ids[k]]]["volume_change"] = float(np.nanmean(now) / np.nanmean(prev) - 1)


def _adjust(rows: list[dict], cfg: DetectConfig) -> None:
    """Holm (and BH, reported) within each test family."""
    fam = [r["test_family"] for r in rows]
    for j in (1, 2, 3):
        p = np.array([np.nan if r.get(f"trend_w{j}_p") is None else r[f"trend_w{j}_p"] for r in rows])
        groups = [f"{f}|w{j}" for f in fam]
        h, q = stats.holm(p, groups), stats.bh(p, groups)
        for r, hv, qv in zip(rows, h, q, strict=True):
            r[f"trend_w{j}_p_holm"], r[f"trend_w{j}_q_bh"] = _f(hv), _f(qv)
    for name in ("accel", "anom", "surge"):
        p = np.array([np.nan if r.get(f"{name}_p") is None else r[f"{name}_p"] for r in rows])
        h = stats.holm(p, [f"{f}|{name}" for f in fam])
        for r, hv in zip(rows, h, strict=True):
            r[f"{name}_p_holm"] = _f(hv)


def _decide(row: dict, cfg: DetectConfig) -> None:
    sc = cfg.series
    sig, dirs = 0, []
    for j in (1, 2, 3):
        ph, lo, hi = row.get(f"trend_w{j}_p_holm"), row.get(f"trend_w{j}_lo"), row.get(f"trend_w{j}_hi")
        s = ph is not None and ph < sc.alpha and lo is not None and (lo > 0 or hi < 0)
        row[f"trend_w{j}_sig"] = bool(s) if ph is not None else None
        if s:
            sig += 1
            dirs.append(1 if lo > 0 else -1)
    row["trend_sig"] = sig
    agree = len(set(dirs)) == 1
    row["trend_dir"] = dirs[-1] if sig >= sc.trend_min_windows and agree else 0
    row["trend_growth"] = None
    if row["trend_dir"]:
        j = max(j for j in (1, 2, 3) if row.get(f"trend_w{j}_sig"))
        lvl = 1.0 if row["transform"] != "level" else row.get("_level")
        row["trend_growth"] = row[f"trend_w{j}_slope"] * PER_YEAR[row["frequency"]] / lvl if lvl else None
    per = PER_YEAR[row["frequency"]]
    scale = 1.0 if row["transform"] != "level" else row.get("_level")

    def yearly(v):
        return v * per / scale if v is not None and scale else None

    row["accel_change"] = yearly(row.get("accel_diff"))
    ap, lo, hi = row.get("accel_p_holm"), row.get("accel_lo"), row.get("accel_hi")
    row["accel"] = bool(ap is not None and ap < sc.alpha and lo is not None and (lo > 0 or hi < 0)
                        and abs(row["accel_change"] or 0) >= sc.accel_min_change)  # fmt: skip
    before, after = row.get("cp_slope_before"), row.get("cp_slope_after")
    row["cp_slope_change"] = yearly(after - before) if before is not None and after is not None else None
    row["cp_steeper"] = bool(row.pop("_cp_shape", False) and abs(row["cp_slope_change"] or 0) >= sc.accel_min_change)
    row["cp_level_recent"] = bool(row.pop("_cp_level_recent", False)
                                  and row["frequency"] in sc.change_points.level_frequencies
                                  and (row.get("cp_level_change") or 0) >= sc.anomaly_min_change)  # fmt: skip
    ah = row.get("anom_p_holm")
    big = (row.get("anom_change") or 0) >= sc.anomaly_min_change
    row["anomaly"] = bool(ah is not None and ah < sc.anomaly_alpha and big)
    sh, ratio = row.get("surge_p_holm"), row.get("surge_ratio")
    row["surge"] = bool(sh is not None and sh < sc.alpha and ratio is not None and ratio >= sc.surge.min_ratio)
    row.pop("_level", None)
    row.pop("_stale", None)


# ----------------------------------------------------------------------------------------------------- divergence


def pair_key(s: Series) -> tuple[str, str] | None:
    """(the pair's key, 'au' or 'ref') when a series has a counterpart in another scope."""
    parts = s.series_id.split("|")
    src = s.source
    if src == "openalex_counts" and parts[1] != "total":
        return "|".join(parts[1:3] + parts[4:]), "au" if parts[3] == "au" else ("ref" if parts[3] == "world" else "")
    if src == "patent_cpc_counts":
        return parts[1], "au" if parts[2] == "au" else ("ref" if parts[2] == "world" else "")
    if src == "gdelt_news" and parts[1] != "total":
        return f"{parts[1]}|{parts[3]}", "au" if parts[2] == "au" else ("ref" if parts[2] == "world" else "")
    if src == "oecd_headline":
        try:
            dims = json.loads(s.meta.get("dimensions") or "{}")
        except ValueError:
            return None
        scope = s.meta.get("scope")
        side = "au" if scope == "AUS" else ("ref" if scope == "OECD" else "")
        rest = {k: v for k, v in dims.items() if k not in ("REF_AREA", "query_id")}
        return json.dumps(rest, sort_keys=True), side
    return None


def divergence(groups: dict[tuple[str, str], Group], rows: list[dict], cfg: DetectConfig, as_of: date) -> list[dict]:
    sc = cfg.series
    by_id = {r["series_id"]: r for r in rows}
    out = []
    for (source, kind), g in sorted(groups.items()):
        if source not in sc.divergence_reference:
            continue
        sides: dict[str, dict[str, int]] = defaultdict(dict)
        for k, s in enumerate(g.series):
            pk = pair_key(s)
            if pk and pk[1]:
                sides[pk[0]][pk[1]] = k
        pairs = sorted((key, v["au"], v["ref"]) for key, v in sides.items() if "au" in v and "ref" in v)
        if not pairs:
            continue
        cur = current_index(kind, as_of)
        widths = sc.windows[kind]
        a_idx = np.array([a for _, a, _ in pairs])
        r_idx = np.array([b for _, _, b in pairs])
        last = np.minimum(g.last[a_idx], g.last[r_idx])
        d = g.y[a_idx] - g.y[r_idx]
        stale = last < (cur - 1 - sc.stale_after[kind])
        # volume: Australia's counts must be big enough to rate (counts) in the shortest window
        cnt = aligned(g.counts[a_idx], last, g.base, widths[0])
        mc = _nanmean(cnt)
        is_count = np.array([g.transform[a] != "level" for a in a_idx])
        valid = ~stale & (~is_count | (np.nan_to_num(mc) >= sc.min_mean_count))
        mats = []
        for w in widths:
            m = aligned(d, last, g.base, w)
            ex = aligned(np.broadcast_to(g.excluded.astype(float), d.shape).copy(), last, g.base, w) == 1
            mats.append((m, ex))
        wins = trend_windows(mats, widths, sc.min_coverage, sc.alpha, valid)
        for n, (key, a, b) in enumerate(pairs):
            if not valid[n]:
                continue
            row = {"pair_id": f"{source}|{key}", "source": source, "au_series": g.ids[a], "ref_series": g.ids[b],
                   "ref_scope": g.series[b].meta.get("scope"), "label": g.series[a].meta.get("label"),
                   "frequency": kind, "transform": g.transform[a],
                   "last_period": index_label(kind, int(last[n]))}  # fmt: skip
            for j, wr in enumerate(wins, 1):
                ok = bool(wr["ok"][n])
                row.update({f"w{j}_n": int(wr["n"][n]) if ok else None,
                            f"w{j}_slope": _f(wr["slope"][n]) if ok else None,
                            f"w{j}_lo": _f(wr["lo"][n]) if ok else None, f"w{j}_hi": _f(wr["hi"][n]) if ok else None,
                            f"w{j}_p": _f(wr["p"][n]) if ok else None})  # fmt: skip
            row["windows"] = sum(1 for wr in wins if wr["ok"][n])
            row["_family"] = f"{source}|{kind}|{g.groups[a]}|divergence"
            row["au_trend_dir"] = (by_id.get(g.ids[a]) or {}).get("trend_dir")
            row["ref_trend_dir"] = (by_id.get(g.ids[b]) or {}).get("trend_dir")
            out.append(row)
    fam = [r["_family"] for r in out]
    for j in (1, 2, 3):
        p = np.array([np.nan if r.get(f"w{j}_p") is None else r[f"w{j}_p"] for r in out])
        h = stats.holm(p, [f"{f}|w{j}" for f in fam])
        for r, hv in zip(out, h, strict=True):
            r[f"w{j}_p_holm"] = _f(hv)
    for r in out:
        sig, dirs = 0, []
        for j in (1, 2, 3):
            ph, lo, hi = r.get(f"w{j}_p_holm"), r.get(f"w{j}_lo"), r.get(f"w{j}_hi")
            s = ph is not None and ph < sc.alpha and lo is not None and (lo > 0 or hi < 0)
            r[f"w{j}_sig"] = bool(s) if ph is not None else None
            if s:
                sig += 1
                dirs.append(1 if lo > 0 else -1)
        r["sig"] = sig
        r["direction"] = dirs[-1] if sig >= sc.trend_min_windows and len(set(dirs)) == 1 else 0
        r["growth"] = None
        if r["direction"]:
            j = max(j for j in (1, 2, 3) if r.get(f"w{j}_sig"))
            r["growth"] = r[f"w{j}_slope"] * PER_YEAR[r["frequency"]]
        r.pop("_family")
    return out


# ------------------------------------------------------------------------------------------------------------ run


def inputs(store: Store, cfg: DetectConfig) -> tuple[dict, list[tuple[Path, Path]]]:
    """The checked upstream files: (upstream run ids, [(series file, observations file)])."""
    sources = set(cfg.series.sources)
    runs = {}
    pairs = []
    nm = upstream(store, NORMALISE)
    runs["normalise_run"] = nm["run_id"]
    files = fetch_outputs(store, nm, "lake/", cache_root())
    for src in sorted(sources - {"ip_rapid_metrics"}):
        s, o = f"lake/series/source={src}/series.parquet", f"lake/observations/source={src}/observations.parquet"
        if s in files and o in files:
            pairs.append((files[s], files[o]))
    if "ip_rapid_metrics" in sources:
        im = upstream(store, IPRM)
        runs["ipr_metrics_run"] = im["run_id"]
        f = fetch_outputs(store, im, "lake/ipr_metrics/", cache_root())
        pairs.append((f["lake/ipr_metrics/series.parquet"], f["lake/ipr_metrics/observations.parquet"]))
    return runs, pairs


def level_of(rows: list[dict], series: dict[str, Series]) -> None:
    """The median absolute level of a statistic over its longest significant window, to express its slope as a
    share of its level."""
    for r in rows:
        if r["transform"] != "level":
            continue
        s = series[r["series_id"]]
        vals = [abs(v) for i, v in sorted(s.points.items())[-48:]]
        r["_level"] = float(np.median(vals)) if vals and np.median(vals) > 0 else None


def measure(store: Store, cfg: DetectConfig, as_of: date, config_hash: str | None = None) -> tuple[str, str, dict]:
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        runs, files = inputs(store, cfg)
        manifest.params = {"as_of": as_of.isoformat(), **runs}
        series = load_series(files, set(cfg.series.sources), as_of)
        rows, div, counts = _run(series, cfg, as_of)
        prefix = f"measures/series/as_of={as_of.isoformat()}/"
        with tempfile.TemporaryDirectory(prefix="moria-measure-") as tmp:
            write_rows(rows, MEASURES, Path(tmp) / "measures.parquet", ("series_id",))
            write_rows(div, DIVERGENCE, Path(tmp) / "divergence.parquet", ("pair_id",))
            for name in ("divergence", "measures"):
                upload(store, manifest, f"{prefix}{name}.parquet", Path(tmp) / f"{name}.parquet")
        manifest.counts = counts
        return "passed", manifest.finish(store, "passed"), counts
    except Exception as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        cause = f"{COMMAND}: {type(e).__name__}: {first[:300]}"
        log.error("%s", cause)
        return "failed", manifest.finish(store, "failed", cause), {"error": cause}


def _run(series: dict[str, Series], cfg: DetectConfig, as_of: date) -> tuple[list[dict], list[dict], dict]:
    synthetic_totals(series)
    by: dict[tuple[str, str], list[Series]] = defaultdict(list)
    for s in sorted(series.values(), key=lambda s: s.series_id):
        if not s.meta.get("synthetic"):
            by[(s.source, s.kind)].append(s)
    rows: list[dict] = []
    groups: dict[tuple[str, str], Group] = {}
    counts: dict[str, int] = defaultdict(int)
    for (source, kind), members in sorted(by.items()):
        g = build_group(source, kind, members, series, cfg, as_of)
        if g is None:
            continue
        groups[(source, kind)] = g
        got = _measure(g, cfg, as_of, counts)
        log.info("measure: %s %s: %d series tested", source, kind, len(got))
        rows.extend(got)
    level_of(rows, series)
    _adjust(rows, cfg)
    for row in rows:
        _decide(row, cfg)
    div = divergence(groups, rows, cfg, as_of)
    counts["series"] = len(rows)
    counts["series_trend_windows_2plus"] = sum(1 for r in rows if (r["trend_windows"] or 0) >= 2)
    counts["trends"] = sum(1 for r in rows if r["trend_dir"])
    counts["trends_bh"] = sum(1 for r in rows if _bh_trend(r, cfg))
    for key in ("accel", "cp_steeper", "anomaly", "cp_level_recent", "surge"):
        counts[key] = sum(1 for r in rows if r.get(key))
    counts["divergence_pairs"] = len(div)
    counts["divergences"] = sum(1 for d in div if d["direction"])
    return rows, div, dict(sorted(counts.items()))


def _bh_trend(r: dict, cfg: DetectConfig) -> bool:
    """Would the trend rule pass with Benjamini-Hochberg's q in place of Holm's p? Reported for the owner only."""
    dirs = []
    for j in (1, 2, 3):
        q, lo, hi = r.get(f"trend_w{j}_q_bh"), r.get(f"trend_w{j}_lo"), r.get(f"trend_w{j}_hi")
        if q is not None and q < cfg.series.alpha and lo is not None and (lo > 0 or hi < 0):
            dirs.append(1 if lo > 0 else -1)
    return len(dirs) >= cfg.series.trend_min_windows and len(set(dirs)) == 1
