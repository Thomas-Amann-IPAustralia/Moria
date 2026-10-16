"""Contextual anomalies and coupling for `moria measure series` (the SignalBoost proposal's items 2 and 3; D-025).

**Contextual anomaly.** Day 4's band asks whether a series' latest value is far from its own line. Here it is asked
whether the value is far from what its context predicts. A ridge regression is fitted on the baseline before the
latest period (`context.baseline`), row by row in one batched solve, on:
- a time trend (the series' own history);
- its **peers**: the mean of the series of its own test family (same source, frequency, taxonomy level or dataflow,
  and scope class) whose changes over the baseline correlated best with its own (at most `peers`, each at least
  `peer_min_corr`). They are chosen on the baseline alone, so the latest period is predicted out of sample;
- its **international counterpart**, for an Australian series: the world's share (OpenAlex, CPC, GDELT) or the OECD's
  level for the same topic, subclass, query group or indicator;
- the **source's volume**, for a share (its denominator, on a log scale).
The latest value is then tested against the prediction of the full context, of the peers alone and of the
counterpart alone (they often carry the same movement, and a joint fit credits whichever was less noisy); the
context that explains it best is kept, so a move any context explains is not contextual. The test uses a robust
residual sigma with the prediction's leverage (for counts, at least the Poisson noise of the expected count), Holm
within the test family, and day 4's minimum change. Each row keeps its covariates' contributions to the prediction
(`contributions`: the coefficient times the covariate's move from its baseline mean, on the tested scale) and the
peers' and counterpart's series ids, so the explanation reads from the evidence ("peers up 12%, the world up 3%,
observed up 60%"). A band anomaly whose move the context predicts (`explained_share` of it) is marked `explained`:
an alternative explanation for the dossier, never a reason to hide it.

**Coupling.** For an Australian series with a counterpart: the correlation of their period-to-period changes in the
earlier and the recent half of the last `max_points` periods, by Fisher's test (Holm). `decoupled`: an established
relationship (at least `established`) that has broken (at most `broken`); `coupled`: the reverse. Peers are not
tested for coupling: they were chosen for their correlation, which would bias the test.

The counterpart and peers explain a move; they never corroborate it (D-025).
"""

from __future__ import annotations

import json
import warnings
from collections import defaultdict
from datetime import date

import numpy as np
import pyarrow as pa

from . import stats
from .config import DetectConfig

F64 = pa.float64()
STRS = pa.list_(pa.string())
CONTEXT = pa.schema(
    [
        ("series_id", pa.string()),
        ("source", pa.string()),
        ("frequency", pa.string()),
        ("transform", pa.string()),
        ("period", pa.string()),  # the latest period, the one tested
        ("baseline_start", pa.string()),
        ("n_baseline", pa.int16()),
        ("observed", F64),  # on the tested scale (a log share, a log count, or the level)
        ("expected_trend", F64),  # the baseline's own Theil-Sen line at the latest period
        ("expected", F64),  # the contextual model's prediction
        ("se", F64),
        ("z", F64),
        ("p", F64),
        ("p_holm", F64),
        ("change", F64),  # how far off the prediction: a ratio minus 1 (counts), or over the level (statistics)
        ("contextual", pa.bool_()),  # significant and at least min_change off its context
        ("explained", pa.bool_()),  # a band anomaly (day 4) whose move the context predicts
        ("explained_share", F64),  # the share of the move off the trend line that the context predicts
        ("covariates", STRS),  # trend, peers, reference, volume: those the fit used
        ("contributions", pa.string()),  # canonical JSON: covariate -> its contribution to the prediction
        ("r2", F64),
        ("peers", STRS),  # the peers' series ids
        ("peer_corr", F64),  # their mean correlation with the series over the baseline
        ("reference", pa.string()),  # the counterpart's series id
        ("coupling_r_early", F64),
        ("coupling_r_recent", F64),
        ("coupling_n_early", pa.int16()),
        ("coupling_n_recent", pa.int16()),
        ("coupling_p", F64),
        ("coupling_p_holm", F64),
        ("coupling", pa.string()),  # decoupled, coupled, or none
        ("coupling_start", pa.string()),  # the first period of the coupling window
    ]
)
NAMES = ("trend", "peers", "reference", "volume")


def _f(v) -> float | None:
    return float(v) if v is not None and np.isfinite(v) else None


def references(g, pair_key) -> dict[int, int]:
    """Row of each Australian series -> row of its counterpart in the same group."""
    sides: dict[str, dict[str, int]] = defaultdict(dict)
    for k, s in enumerate(g.series):
        pk = pair_key(s)
        if pk and pk[1]:
            sides[pk[0]][pk[1]] = k
    return {v["au"]: v["ref"] for v in sides.values() if "au" in v and "ref" in v}


def choose_peers(g, cfg: DetectConfig, valid: np.ndarray, family, aligned) -> dict[int, tuple[list[int], float]]:
    """Row -> (its peers' rows, their mean correlation), chosen on the baseline's first differences among the rows of
    its test family that end in the same period and have a complete baseline."""
    cc = cfg.context
    b = cc.baseline[g.kind]
    mat = aligned(g.y, g.last, g.base, b + 1)[:, :b]
    ex = aligned(np.broadcast_to(g.excluded.astype(float), g.y.shape).copy(), g.last, g.base, b + 1)[:, :b] == 1
    complete = valid & (np.isnan(mat) == ex).all(axis=1)
    sets: dict[tuple, list[int]] = defaultdict(list)
    for k in np.nonzero(complete)[0]:
        sets[(family(g, int(k)), int(g.last[k]))].append(int(k))
    out: dict[int, tuple[list[int], float]] = {}
    for ks in sets.values():
        if len(ks) < 2:
            continue
        d = np.diff(mat[ks], axis=1)
        d = d[:, ~np.isnan(d).any(axis=0)]
        if d.shape[1] < 4:
            continue
        sd = d.std(axis=1)
        z = np.where(sd[:, None] > 0, (d - d.mean(axis=1, keepdims=True)) / np.where(sd > 0, sd, 1)[:, None], 0.0)
        corr = z @ z.T / d.shape[1]
        np.fill_diagonal(corr, -np.inf)
        top = np.argsort(-corr, axis=1)[:, : cc.peers]
        for i, k in enumerate(ks):
            chosen = [j for j in top[i] if corr[i, j] >= cc.peer_min_corr]
            if chosen:
                out[k] = ([ks[j] for j in chosen], float(np.mean(corr[i, chosen])))
    return out


def measure_group(g, cfg: DetectConfig, as_of: date, valid: np.ndarray, rows_by_id: dict, family, aligned,
                  index_label, pair_key) -> list[dict]:  # fmt: skip
    cc = cfg.context
    b = cc.baseline[g.kind]
    width = b + 1
    r = len(g.ids)
    ex = aligned(np.broadcast_to(g.excluded.astype(float), g.y.shape).copy(), g.last, g.base, width) == 1
    y = aligned(g.y, g.last, g.base, width)
    expected_base = np.maximum((~ex[:, :b]).sum(axis=1), 1)
    ok = valid & ~np.isnan(y[:, b]) & (np.sum(~np.isnan(y[:, :b]), axis=1) >= np.maximum(cc.min_baseline
                                                                                       * expected_base, 6))  # fmt: skip
    if not ok.any():
        return []
    refs = references(g, pair_key)
    peers = choose_peers(g, cfg, ok, family, aligned)
    x = np.zeros((r, width, len(NAMES)))
    x[:, :, 0] = np.arange(width, dtype=float)[None, :]
    present = np.zeros((r, len(NAMES)), dtype=bool)
    present[:, 0] = True
    for k, (ps, _) in peers.items():
        pm = aligned(g.y[ps], np.full(len(ps), g.last[k]), g.base, width)
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # a period none of the peers has stays missing
            x[k, :, 1] = np.nanmean(pm, axis=0) if len(ps) > 1 else pm[0]
        present[k, 1] = True
    for k, j in refs.items():
        x[k, :, 2] = aligned(g.y[[j]], np.array([g.last[k]]), g.base, width)[0]
        present[k, 2] = True
    den = aligned(g.denom, g.last, g.base, width)
    for k in range(r):
        if g.transform[k] == "log_share" and g.denominators[k]:
            with np.errstate(all="ignore"):
                x[k, :, 3] = np.log(den[k])
            present[k, 3] = True
    x = np.where(present[:, None, :], x, 0.0)
    target_ok = ok & ~np.isnan(x[:, b, :]).any(axis=1)
    w = (~np.isnan(y[:, :b]) & ~np.isnan(x[:, :b, :]).any(axis=2)).astype(float)
    target_ok &= w.sum(axis=1) >= present.sum(axis=1) + 4
    rows_k = np.nonzero(target_ok)[0]
    if not len(rows_k):
        return []
    xb = np.nan_to_num(x[rows_k, :b, :])
    yb = np.nan_to_num(y[rows_k, :b])
    obs = y[rows_k, b]
    transform = np.array([g.transform[k] for k in rows_k])
    # peers and counterpart often carry the same movement, and a joint fit credits whichever was less noisy: the
    # value is tested against the full context, the peers alone and the counterpart alone, and the context that
    # explains it best is the one kept (a move any context explains is not contextual)
    fits = []
    for drop in ((), (2,), (1,)):
        keep = np.ones(len(NAMES), dtype=bool)
        keep[list(drop)] = False
        xs = np.where(keep[None, None, :], xb, 0.0)
        f = stats.ridge_rows(xs, yb, w[rows_k], np.where(keep[None, :], x[rows_k, b, :], 0.0), cc.ridge)
        with np.errstate(all="ignore"):
            ec = np.where(transform == "log_share", np.exp(f["pred"]) * den[rows_k, b], np.exp(f["pred"]))
            fl = np.where(transform == "level", 1e-9 * (np.abs(f["pred"]) + 1), 1 / np.sqrt(np.maximum(ec, 1)))
            f["z"] = (obs - f["pred"]) / np.maximum(np.nan_to_num(f["se"]), fl)
        f["keep"] = keep
        fits.append(f)
    best = np.argmin(np.vstack([np.where(np.isfinite(f["z"]), np.abs(f["z"]), np.inf) for f in fits]), axis=0)
    pick = np.arange(len(rows_k))
    fit = {k: np.stack([f[k] for f in fits])[best, pick] for k in ("pred", "se", "y_mean", "sigma", "r2", "z")}
    fit["beta"] = np.stack([f["beta"] for f in fits])[best, pick]
    fit["x_mean"] = np.stack([f["x_mean"] for f in fits])[best, pick]
    kept = np.stack([np.broadcast_to(f["keep"], (len(rows_k), len(NAMES))) for f in fits])[best, pick]
    trend = stats.ridge_rows(xb[:, :, :1], yb, w[rows_k], x[rows_k, b, :1], 0.0)
    z = fit["z"]
    with np.errstate(all="ignore"):
        level = np.maximum(np.abs(fit["y_mean"]), np.nan_to_num(fit["sigma"]))
        off = obs - fit["pred"]
        change = np.where(transform == "level", np.abs(off) / level, np.abs(np.exp(off) - 1))
        moved = obs - trend["pred"]
        share = np.where(np.abs(moved) > 0, (fit["pred"] - trend["pred"]) / moved, np.nan)
    pv = 2 * stats.norm.sf(np.abs(z))
    coupling = _coupling(g, cfg, refs, rows_k, aligned)
    out = []
    for n, k in enumerate(rows_k):
        if not np.isfinite(z[n]):
            continue
        used = [NAMES[c] for c in range(len(NAMES)) if present[k, c] and kept[n, c]]
        contrib = {
            NAMES[c]: round(float(fit["beta"][n, c] * (x[k, b, c] - fit["x_mean"][n, c])), 6)
            for c in range(len(NAMES))
            if present[k, c] and kept[n, c] and np.isfinite(fit["beta"][n, c])
        }
        last = int(g.last[k])
        row = {
            "series_id": g.ids[k],
            "source": g.source,
            "frequency": g.kind,
            "transform": g.transform[k],
            "period": index_label(g.kind, last),
            "baseline_start": index_label(g.kind, last - b),
            "n_baseline": int(w[k].sum()),
            "observed": _f(obs[n]),
            "expected_trend": _f(trend["pred"][n]),
            "expected": _f(fit["pred"][n]),
            "se": _f(fit["se"][n]),
            "z": _f(z[n]),
            "p": _f(pv[n]),
            "change": _f(change[n]),
            "explained_share": _f(share[n]),
            "covariates": used,
            "contributions": json.dumps(contrib, sort_keys=True, separators=(",", ":")),
            "r2": _f(fit["r2"][n]),
            "peers": [g.ids[j] for j in peers.get(int(k), ([], 0))[0]],
            "peer_corr": _f(peers[int(k)][1]) if int(k) in peers else None,
            "reference": g.ids[refs[int(k)]] if int(k) in refs else None,
            "_family": family(g, int(k)),
            "_anomaly": bool((rows_by_id.get(g.ids[k]) or {}).get("anomaly")),
        }
        row.update(coupling.get(int(k), {}))
        out.append(row)
    return out


def _coupling(g, cfg: DetectConfig, refs: dict[int, int], rows_k, aligned) -> dict[int, dict]:
    cp = cfg.context.coupling
    ks = [int(k) for k in rows_k if int(k) in refs]
    if not ks:
        return {}
    width = cp.max_points
    a = aligned(g.y[ks], g.last[ks], g.base, width)
    b = aligned(g.y[[refs[k] for k in ks]], g.last[ks], g.base, width)
    both = ~np.isnan(a) & ~np.isnan(b)
    out = {}
    for n, k in enumerate(ks):
        cols = np.nonzero(both[n])[0]
        if len(cols) < cp.min_points:
            continue
        cols = cols[cols >= cols[-1] - (cp.max_points - 1)]
        da, db = np.diff(a[n, cols]), np.diff(b[n, cols])
        half = len(da) // 2
        e = stats.row_corr(da[None, :half], db[None, :half])[0]
        rcent = stats.row_corr(da[None, half:], db[None, half:])[0]
        n1, n2 = half, len(da) - half
        p = stats.correlation_change([e], [n1], [rcent], [n2])[0]
        start = int(g.last[k]) - (width - 1) + int(cols[0])
        out[k] = {"coupling_r_early": _f(e), "coupling_r_recent": _f(rcent), "coupling_n_early": n1,
                  "coupling_n_recent": n2, "coupling_p": _f(p), "_cstart": start}  # fmt: skip
    return out


def adjust(rows: list[dict], cfg: DetectConfig, index_label) -> None:
    cc = cfg.context
    fam = [r["_family"] for r in rows]
    h = stats.holm(np.array([np.nan if r["p"] is None else r["p"] for r in rows]), fam)
    hc = stats.holm(np.array([np.nan if r.get("coupling_p") is None else r["coupling_p"] for r in rows]),
                    [f"{f}|coupling" for f in fam])  # fmt: skip
    for r, hv, cv in zip(rows, h, hc, strict=True):
        r["p_holm"] = _f(hv)
        r["contextual"] = bool(r["p_holm"] is not None and r["p_holm"] < cc.alpha
                               and (r["change"] or 0) >= cc.min_change)  # fmt: skip
        anomaly = r.pop("_anomaly")
        r["explained"] = bool(anomaly and not r["contextual"] and (r["explained_share"] or 0) >= cc.explained_share)
        r["coupling_p_holm"] = _f(cv)
        r["coupling"] = None
        if r.get("coupling_p") is not None:
            e, rc = r["coupling_r_early"], r["coupling_r_recent"]
            sig = r["coupling_p_holm"] is not None and r["coupling_p_holm"] < cc.coupling.alpha
            if sig and e is not None and rc is not None:
                if e >= cc.coupling.established and rc <= cc.coupling.broken:
                    r["coupling"] = "decoupled"
                elif e <= cc.coupling.broken and rc >= cc.coupling.established:
                    r["coupling"] = "coupled"
        start = r.pop("_cstart", None)
        r["coupling_start"] = index_label(r["frequency"], start) if start is not None else None
        r.pop("_family")
