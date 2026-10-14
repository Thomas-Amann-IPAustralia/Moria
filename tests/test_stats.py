"""The detectors' statistics against scipy and against planted changes."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import binomtest, theilslopes

from moria import stats as S


def test_theil_sen_matches_scipy_including_missing_values():
    rng = np.random.default_rng(1)
    y = rng.poisson(5, size=(20, 18)).astype(float) + np.arange(18) * 0.3
    y[3, 5] = np.nan
    x = np.arange(18, dtype=float)
    ts = S.theil_sen(x, y)
    for r in range(20):
        keep = ~np.isnan(y[r])
        ref = theilslopes(y[r][keep], x[keep])
        assert ts["slope"][r] == pytest.approx(ref.slope)
        assert ts["lo"][r] == pytest.approx(ref.low_slope) and ts["hi"][r] == pytest.approx(ref.high_slope)
        assert ts["intercept"][r] == pytest.approx(ref.intercept)


def test_mann_kendall_on_a_monotonic_series_and_on_ties():
    mk = S.mann_kendall(np.array([np.arange(10.0), np.ones(10)]))
    assert mk["s"][0] == 45 and mk["p"][0] < 0.001
    assert mk["s"][1] == 0 and mk["p"][1] == 1.0  # all tied: no trend


def test_holm_and_bh_within_groups():
    p = np.array([0.01, 0.04, 0.03, 0.2, np.nan, 0.01])
    groups = ["a", "a", "a", "a", "a", "b"]
    h = S.holm(p, groups)
    assert h[:4] == pytest.approx([0.04, 0.09, 0.09, 0.2]) and np.isnan(h[4]) and h[5] == pytest.approx(0.01)
    q = S.bh(p, groups)
    assert q[0] == pytest.approx(0.04) and q[1] == pytest.approx(0.04 * 4 / 3)


def test_poisson_rate_test_is_the_conditional_binomial():
    p, ratio = S.poisson_rate_test([10], [1.0], [2], [4.0])
    assert p[0] == pytest.approx(binomtest(10, 12, 0.2, alternative="greater").pvalue)
    assert ratio[0] == pytest.approx(20.0)
    p, ratio = S.poisson_rate_test([5], [1.0], [0], [0.0])
    assert np.isnan(p[0])  # no baseline exposure: no rate to compare with


def test_change_points_find_planted_changes_and_leave_noise_alone():
    rng = np.random.default_rng(3)
    x = np.arange(36, dtype=float)
    step = np.r_[np.zeros(24), np.full(12, 3.0)] + rng.normal(0, 0.5, 36)
    kink = np.r_[np.arange(24) * 0.05, 1.2 + np.arange(12) * 0.8] + rng.normal(0, 0.3, 36)
    noise = rng.normal(0, 1, (200, 36))
    assert S.change_points(step[None], x, "mean", 3, 3)[0] == [24]
    assert 22 <= S.change_points(kink[None], x, "linear", 6, 3)[0][-1] <= 26
    false = sum(bool(c) for c in S.change_points(noise, x, "mean", 3, 3))
    assert false <= 4  # about 0.5% of noise series split at this penalty (D-022)


def test_bootstrap_slope_change_is_deterministic_and_finds_an_acceleration():
    rng = np.random.default_rng(5)
    x = np.arange(24, dtype=float)
    y = np.vstack([np.r_[np.arange(12) * 0.1, 1.2 + np.arange(12) * 0.5] + rng.normal(0, 0.2, 24),
                   rng.normal(0, 1, 24)])  # fmt: skip
    a = S.bootstrap_slope_change(x, y, 200, 7)
    b = S.bootstrap_slope_change(x, y, 200, 7)
    assert np.array_equal(a["p"], b["p"])
    assert a["diff"][0] > 0.3 and a["p"][0] < 1e-6 and a["lo"][0] > 0
    assert a["p"][1] > 0.01
