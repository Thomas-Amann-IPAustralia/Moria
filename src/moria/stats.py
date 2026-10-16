"""The statistics of the detectors (design §8.1, §8.2), vectorised over many series at once: each function takes a
matrix with one series per row and one period per column (NaN where a period is missing), so a whole taxonomy is
tested in a few array operations rather than a loop per series.

- Theil-Sen slopes with Sen's (1968) confidence interval, as `scipy.stats.theilslopes` computes them;
- Mann-Kendall's test, with the tie correction;
- Holm's and Benjamini-Hochberg's adjustments within families of tests;
- the exact conditional test of two Poisson rates (a binomial test given the total), for low-base surges;
- change points by optimal partitioning: the exact minimum of PELT's penalised cost (PELT prunes the same search),
  for changes in level or in slope;
- a bootstrap of the change in slope between the halves of a window, for accelerations;
- the lower tail of a Poisson count against its expectation, for associations that break down;
- Fisher's test of a change in correlation between two spans, for relationships that couple or decouple;
- ridge regressions fitted row by row in one batched solve, with prediction errors, for contextual anomalies.

Everything here is deterministic: the bootstrap takes its seed from the caller.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import binom, norm, poisson


def _pairs(n: int) -> tuple[np.ndarray, np.ndarray]:
    i, j = np.triu_indices(n, k=1)
    return i, j


def _tie_term(values: np.ndarray) -> np.ndarray:
    """Per row, the sum of t(t-1)(2t+5) over groups of equal values (missing values ignored)."""
    s = np.sort(values, axis=1)
    same = s[:, 1:] == s[:, :-1]  # NaN never equals NaN
    out = np.zeros(len(values))
    for r in np.nonzero(same.any(axis=1))[0]:
        row = s[r][~np.isnan(s[r])]
        _, t = np.unique(row, return_counts=True)
        t = t[t > 1].astype(float)
        out[r] = float((t * (t - 1) * (2 * t + 5)).sum())
    return out


def theil_sen(x: np.ndarray, y: np.ndarray, alpha: float = 0.05) -> dict[str, np.ndarray]:
    """Theil-Sen slope per row of `y` against positions `x` (strictly increasing), with Sen's confidence interval at
    level 1 - alpha and the intercept (median of y minus slope times median of x, scipy's 'separate' method).
    Returns slope, lo, hi, intercept and n (points present) per row; NaN where a row has fewer than 3 points."""
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    i, j = _pairs(y.shape[1])
    slopes = (y[:, j] - y[:, i]) / (x[j] - x[i])
    slopes.sort(axis=1)  # NaN last
    nt = np.sum(~np.isnan(slopes), axis=1)
    n = np.sum(~np.isnan(y), axis=1)
    out = {k: np.full(len(y), np.nan) for k in ("slope", "lo", "hi", "intercept")}
    out["n"] = n
    ok = (n >= 3) & (nt > 0)
    if not ok.any():
        return out
    rows = np.nonzero(ok)[0]
    s = slopes[rows]
    k = nt[rows]
    mid_lo, mid_hi = (k - 1) // 2, k // 2
    r = np.arange(len(rows))
    med = (s[r, mid_lo] + s[r, mid_hi]) / 2
    nn = n[rows].astype(float)
    sigsq = (nn * (nn - 1) * (2 * nn + 5) - _tie_term(y[rows])) / 18.0
    z = -norm.ppf(alpha / 2)
    sigma = np.sqrt(np.maximum(sigsq, 0))
    upper = np.minimum(np.round((k + z * sigma) / 2).astype(int), k - 1)
    lower = np.maximum(np.round((k - z * sigma) / 2).astype(int) - 1, 0)
    out["slope"][rows] = med
    out["lo"][rows] = s[r, lower]
    out["hi"][rows] = s[r, upper]
    xm = np.where(np.isnan(y[rows]), np.nan, x)
    out["intercept"][rows] = np.nanmedian(y[rows], axis=1) - med * np.nanmedian(xm, axis=1)
    return out


def mann_kendall(y: np.ndarray) -> dict[str, np.ndarray]:
    """Mann-Kendall's S, its variance (with ties), Z (continuity-corrected) and two-sided p per row."""
    y = np.asarray(y, dtype=float)
    i, j = _pairs(y.shape[1])
    signs = np.nan_to_num(np.sign(y[:, j] - y[:, i]))
    s = signs.sum(axis=1)
    n = np.sum(~np.isnan(y), axis=1).astype(float)
    var = (n * (n - 1) * (2 * n + 5) - _tie_term(y)) / 18.0
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(var > 0, (s - np.sign(s)) / np.sqrt(var), 0.0)
    p = np.where(n >= 3, 2 * norm.sf(np.abs(z)), np.nan)
    return {"s": s, "var": var, "z": z, "p": p, "n": n}


def _by_group(p: np.ndarray, groups) -> dict:
    out: dict = {}
    for idx, g in enumerate(groups):
        out.setdefault(g, []).append(idx)
    return out


def holm(p: np.ndarray, groups) -> np.ndarray:
    """Holm-adjusted p-values within each group; NaN p-values are left out of the family and stay NaN."""
    p = np.asarray(p, dtype=float)
    adj = np.full(len(p), np.nan)
    for idx in _by_group(p, groups).values():
        idx = np.array([i for i in idx if not np.isnan(p[i])], dtype=int)
        m = len(idx)
        if not m:
            continue
        order = idx[np.argsort(p[idx], kind="stable")]
        vals = np.minimum(1.0, (m - np.arange(m)) * p[order])
        adj[order] = np.maximum.accumulate(vals)
    return adj


def bh(p: np.ndarray, groups) -> np.ndarray:
    """Benjamini-Hochberg q-values within each group (reported beside Holm; Holm decides)."""
    p = np.asarray(p, dtype=float)
    q = np.full(len(p), np.nan)
    for idx in _by_group(p, groups).values():
        idx = np.array([i for i in idx if not np.isnan(p[i])], dtype=int)
        m = len(idx)
        if not m:
            continue
        order = idx[np.argsort(p[idx], kind="stable")]
        vals = p[order] * m / np.arange(1, m + 1)
        q[order] = np.minimum(1.0, np.minimum.accumulate(vals[::-1])[::-1])
    return q


def poisson_rate_test(x1, e1, x0, e0) -> tuple[np.ndarray, np.ndarray]:
    """One-sided exact test that the window's rate (x1 events over exposure e1) exceeds the baseline's (x0 over e0):
    given x0 + x1, x1 is binomial with p = e1 / (e0 + e1) under equal rates. Returns (p-value, rate ratio); the ratio
    adds half an event to an empty baseline so that it stays finite."""
    x1, e1, x0, e0 = (np.asarray(a, dtype=float) for a in (x1, e1, x0, e0))
    with np.errstate(divide="ignore", invalid="ignore"):
        share = e1 / (e0 + e1)
        p = binom.sf(x1 - 1, x0 + x1, share)
        ratio = (x1 / e1) / (np.maximum(x0, 0.5) / e0)
    bad = ~((e1 > 0) & (e0 > 0))
    p = np.where(bad, np.nan, p)
    ratio = np.where(bad, np.nan, ratio)
    return p, ratio


def robust_sigma(values: np.ndarray, axis: int = 1) -> np.ndarray:
    """1.4826 times the median absolute deviation: the standard deviation of normal noise, unmoved by outliers."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # an all-NaN row gives NaN
        med = np.nanmedian(values, axis=axis, keepdims=True)
        return 1.4826 * np.nanmedian(np.abs(values - med), axis=axis)


def _segment_costs(y: np.ndarray, x: np.ndarray, kind: str):
    """Cumulative sums from which any segment's cost (squared error about its mean, or about its line) is O(1)."""
    c = lambda a: np.concatenate([np.zeros((a.shape[0], 1)), np.cumsum(a, axis=1)], axis=1)  # noqa: E731
    xx = np.broadcast_to(x, y.shape)
    sums = {"n": c(np.ones_like(y)), "y": c(y), "yy": c(y * y)}
    if kind == "linear":
        sums.update(x=c(xx), xx=c(xx * xx), xy=c(xx * y))

    def cost(s: np.ndarray, t: int) -> np.ndarray:
        # s: (R, S) start indices; t: the end (exclusive); returns (R, S) costs
        g = lambda k: np.take_along_axis(sums[k], np.full_like(s, t), axis=1) - np.take_along_axis(sums[k], s, 1)  # noqa: E731
        m, sy, syy = g("n"), g("y"), g("yy")
        syy_c = syy - sy * sy / m
        if kind == "mean":
            return syy_c
        sx, sxx, sxy = g("x"), g("xx"), g("xy")
        sxx_c = sxx - sx * sx / m
        sxy_c = sxy - sx * sy / m
        with np.errstate(divide="ignore", invalid="ignore"):
            fit = np.where(sxx_c > 0, sxy_c * sxy_c / sxx_c, 0.0)
        return syy_c - fit

    return cost


def change_points(y: np.ndarray, x: np.ndarray, kind: str, min_size: int, penalty_factor: float = 1.0) -> list:
    """Change points per row (complete rows only), by optimal partitioning of the penalised squared error: segments
    in level (`mean`) or in slope (`linear`), each at least `min_size` long. The penalty is BIC's, from a robust noise
    estimate (the MAD of first differences over the square root of 2): (parameters per segment + 1) sigma^2 log n per
    extra segment. Returns, per row, the indices where new segments start (empty: no change)."""
    y = np.asarray(y, dtype=float)
    r, n = y.shape
    if n < 2 * min_size:
        return [[] for _ in range(r)]
    sigma = robust_sigma(np.diff(y, axis=1)) / np.sqrt(2)
    scale = np.nanmedian(np.abs(y), axis=1)
    sigma = np.maximum(sigma, 1e-9 * (1 + scale))
    beta = penalty_factor * (3 if kind == "linear" else 2) * sigma**2 * np.log(n)
    cost = _segment_costs(y, x, kind)
    f = np.full((r, n + 1), np.inf)
    f[:, 0] = -beta
    last = np.zeros((r, n + 1), dtype=int)
    for t in range(min_size, n + 1):
        starts = np.array([0, *range(min_size, t - min_size + 1)])
        s = np.broadcast_to(starts, (r, len(starts)))
        total = f[:, starts] + cost(np.ascontiguousarray(s), t) + beta[:, None]
        k = np.argmin(total, axis=1)
        f[:, t] = total[np.arange(r), k]
        last[:, t] = starts[k]
    out = []
    for row in range(r):
        cps, t = [], n
        while t > 0:
            s = int(last[row, t])
            if s > 0:
                cps.append(s)
            t = s
        out.append(sorted(cps))
    return out


def ols_slope(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2 or np.ptp(x) == 0:
        return float("nan")
    return float(np.polyfit(x, y, 1)[0])


def bootstrap_slope_change(x: np.ndarray, y: np.ndarray, reps: int, seed: int,
                           alpha: float = 0.05) -> dict[str, np.ndarray]:  # fmt: skip
    """The Theil-Sen slope of the recent half of each row minus that of the earlier half, with a bootstrap (points
    resampled within each half, the same draws for every row) standard error, percentile interval and normal
    p-value. Rows with missing values use the points they have."""
    y = np.asarray(y, dtype=float)
    n = y.shape[1]
    half = n // 2
    early, recent = np.arange(half), np.arange(half, n)
    point = theil_sen(x[recent], y[:, recent])["slope"] - theil_sen(x[early], y[:, early])["slope"]
    rng = np.random.default_rng(seed)
    draws = np.empty((reps, len(y)))

    def slope(idx: np.ndarray) -> np.ndarray:
        xs, ys = x[idx], y[:, idx]
        i, j = _pairs(len(idx))
        dx = xs[j] - xs[i]
        keep = dx != 0
        sl = (ys[:, j[keep]] - ys[:, i[keep]]) / dx[keep]
        with np.errstate(all="ignore"):
            return np.nanmedian(sl, axis=1) if sl.shape[1] else np.full(len(y), np.nan)

    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for b in range(reps):
            draws[b] = slope(rng.choice(recent, len(recent))) - slope(rng.choice(early, len(early)))
        se = np.nanstd(draws, axis=0, ddof=1)
        lo = np.nanpercentile(draws, 100 * alpha / 2, axis=0)
        hi = np.nanpercentile(draws, 100 * (1 - alpha / 2), axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(se > 0, point / se, np.nan)
    p = 2 * norm.sf(np.abs(z))
    return {"diff": point, "se": se, "lo": lo, "hi": hi, "p": p}


def poisson_lower(x, expected) -> np.ndarray:
    """One-sided exact test that a count is below its expectation: P(X <= x) for X ~ Poisson(expected)."""
    x, expected = np.asarray(x, dtype=float), np.asarray(expected, dtype=float)
    with np.errstate(all="ignore"):
        return np.where(expected > 0, poisson.cdf(x, expected), np.nan)


def correlation_change(r1, n1, r2, n2) -> np.ndarray:
    """Two-sided p of Fisher's z test that two correlations (from n1 and n2 pairs) differ; NaN under 4 pairs."""
    r1, r2, n1, n2 = (np.asarray(a, dtype=float) for a in (r1, r2, n1, n2))
    with np.errstate(all="ignore"):
        z1 = np.arctanh(np.clip(r1, -0.9999, 0.9999))
        z2 = np.arctanh(np.clip(r2, -0.9999, 0.9999))
        se = np.sqrt(1 / (n1 - 3) + 1 / (n2 - 3))
        p = 2 * norm.sf(np.abs(z2 - z1) / se)
    return np.where((n1 >= 4) & (n2 >= 4) & np.isfinite(p), p, np.nan)


def row_corr(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pearson's correlation of each row of a with the same row of b, over the columns both have; NaN under 3."""
    ok = ~np.isnan(a) & ~np.isnan(b)
    n = ok.sum(axis=1)
    a0, b0 = np.where(ok, a, 0.0), np.where(ok, b, 0.0)
    with np.errstate(all="ignore"):
        ma, mb = a0.sum(axis=1) / n, b0.sum(axis=1) / n
        da, db = np.where(ok, a - ma[:, None], 0.0), np.where(ok, b - mb[:, None], 0.0)
        r = (da * db).sum(axis=1) / np.sqrt((da * da).sum(axis=1) * (db * db).sum(axis=1))
    return np.where(n >= 3, r, np.nan)


def ridge_rows(x: np.ndarray, y: np.ndarray, w: np.ndarray, x0: np.ndarray, ridge: float) -> dict[str, np.ndarray]:
    """Per row r, a weighted ridge regression of y[r] on the covariates x[r] (columns), with a free intercept and
    the penalty `ridge` times the row's weighted length on standardised covariates; predicts at x0[r].

    x: (R, T, K), y: (R, T), w: (R, T) weights (0 leaves a period out), x0: (R, K). Returns the prediction, its
    standard error (a robust residual sigma, with the leverage of x0), the coefficients on the original scale, the
    weighted means of y and x (so that the prediction is y_mean + sum(beta * (x0 - x_mean))), sigma, the fit's R^2
    and the periods used."""
    k = x.shape[2]
    n = w.sum(axis=1)
    with np.errstate(all="ignore"):
        ym = (w * y).sum(axis=1) / n
        xm = (w[:, :, None] * x).sum(axis=1) / n[:, None]
        xc = x - xm[:, None, :]
        sd = np.sqrt((w[:, :, None] * xc * xc).sum(axis=1) / n[:, None])
        sd = np.where(sd > 1e-12, sd, np.inf)  # a constant covariate drops out (its standardised column is 0)
        z = xc / sd[:, None, :]
        yc = np.where(w > 0, y - ym[:, None], 0.0)
        wz = w[:, :, None] * z
        a = np.einsum("rtk,rtl->rkl", wz, z) + (ridge * n)[:, None, None] * np.eye(k)[None]
        a = a + np.eye(k)[None] * (~np.isfinite(sd))[:, None, :]  # keeps a dropped covariate's row solvable
        b = np.einsum("rtk,rt->rk", wz, yc)
        beta_z = np.linalg.solve(a, b[:, :, None])[:, :, 0]
        beta = beta_z / sd
        fit = ym[:, None] + np.einsum("rtk,rk->rt", xc, beta)
        resid = np.where(w > 0, y - fit, np.nan)
        dof = np.maximum(n - k - 1, 1)
        sigma = robust_sigma(resid) * np.sqrt(n / dof)
        z0 = (x0 - xm) / sd
        ainv = np.linalg.inv(a)
        lev = np.einsum("rk,rkl,rl->r", z0, ainv, z0) + 1 / n
        pred = ym + ((x0 - xm) * beta).sum(axis=1)
        ss_tot = np.nansum(np.where(w > 0, (y - ym[:, None]) ** 2, np.nan), axis=1)
        r2 = 1 - np.nansum(resid**2, axis=1) / ss_tot
    return {"pred": pred, "se": sigma * np.sqrt(1 + lev), "beta": beta, "y_mean": ym, "x_mean": xm,
            "sigma": sigma, "r2": r2, "n": n}  # fmt: skip


def lag1_inflation(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Per row, the factor by which positive lag-1 autocorrelation of the residuals about the Theil-Sen line inflates
    Mann-Kendall's variance: 1 + 2 (1 - 1/n) rho1 (the effective sample size of Yue and Wang, 2004, lag 1 only);
    1 when rho1 <= 0 or there are under 6 points. Missing values are skipped (their neighbours are not paired)."""
    ts = theil_sen(x, y)
    r = y - (ts["intercept"][:, None] + ts["slope"][:, None] * x[None, :])
    n = np.sum(~np.isnan(r), axis=1)
    rho = row_corr(r[:, :-1], r[:, 1:])
    return np.where((n >= 6) & (rho > 0), 1 + 2 * (1 - 1 / np.maximum(n, 1)) * np.nan_to_num(rho), 1.0)
