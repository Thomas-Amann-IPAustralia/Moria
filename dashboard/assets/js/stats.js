// The statistics behind the teaching playgrounds, ported from Moria's own src/moria/stats.py so that the toy
// series behave as the real detectors would (Theil-Sen with Sen's interval, Mann-Kendall with ties, Holm,
// Benjamini-Hochberg, the exact Poisson rate test, the robust sigma). The real scan's numbers never come from here:
// they come from Moria's outputs.

/** The standard normal upper tail, P(Z > z) (Abramowitz and Stegun 7.1.26 via erfc; ample for teaching). */
export function normSf(z) {
  return 0.5 * erfc(z / Math.SQRT2);
}
function erfc(x) {
  const z = Math.abs(x);
  const t = 1 / (1 + 0.5 * z);
  const r = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (-0.18628806 +
    t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))));
  return x >= 0 ? r : 2 - r;
}
export function normPpf(p) {
  // Acklam's rational approximation
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239];
  const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572];
  const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416];
  const pl = 0.02425;
  if (p < pl) {
    const q = Math.sqrt(-2 * Math.log(p));
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  if (p > 1 - pl) return -normPpf(1 - p);
  const q = p - 0.5, r = q * q;
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}

function median(a) {
  const s = a.filter((v) => v != null && Number.isFinite(v)).sort((x, y) => x - y);
  if (!s.length) return NaN;
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function tieTerm(y) {
  const counts = new Map();
  for (const v of y) if (v != null && Number.isFinite(v)) counts.set(v, (counts.get(v) || 0) + 1);
  let t = 0;
  for (const c of counts.values()) if (c > 1) t += c * (c - 1) * (2 * c + 5);
  return t;
}

/** Theil-Sen slope with Sen's interval (level 1 - alpha) and scipy's 'separate' intercept, as stats.theil_sen. */
export function theilSen(x, y, alpha = 0.05) {
  const slopes = [];
  for (let i = 0; i < y.length; i++) {
    for (let j = i + 1; j < y.length; j++) {
      if (y[i] == null || y[j] == null || !Number.isFinite(y[i]) || !Number.isFinite(y[j])) continue;
      slopes.push((y[j] - y[i]) / (x[j] - x[i]));
    }
  }
  const n = y.filter((v) => v != null && Number.isFinite(v)).length;
  if (n < 3 || !slopes.length) return { slope: NaN, lo: NaN, hi: NaN, intercept: NaN, n };
  slopes.sort((a, b) => a - b);
  const k = slopes.length;
  const med = (slopes[(k - 1) >> 1] + slopes[k >> 1]) / 2;
  const sigsq = (n * (n - 1) * (2 * n + 5) - tieTerm(y)) / 18;
  const z = -normPpf(alpha / 2);
  const sigma = Math.sqrt(Math.max(sigsq, 0));
  const upper = Math.min(Math.round((k + z * sigma) / 2), k - 1);
  const lower = Math.max(Math.round((k - z * sigma) / 2) - 1, 0);
  const xs = x.filter((_, i) => y[i] != null && Number.isFinite(y[i]));
  return { slope: med, lo: slopes[lower], hi: slopes[upper], intercept: median(y) - med * median(xs), n };
}

/** Mann-Kendall's S, variance with ties, continuity-corrected z and two-sided p, as stats.mann_kendall. */
export function mannKendall(y) {
  let s = 0;
  for (let i = 0; i < y.length; i++) {
    for (let j = i + 1; j < y.length; j++) {
      if (y[i] == null || y[j] == null) continue;
      s += Math.sign(y[j] - y[i]);
    }
  }
  const n = y.filter((v) => v != null && Number.isFinite(v)).length;
  const v = (n * (n - 1) * (2 * n + 5) - tieTerm(y)) / 18;
  const z = v > 0 ? (s - Math.sign(s)) / Math.sqrt(v) : 0;
  return { s, z, p: n >= 3 ? 2 * normSf(Math.abs(z)) : NaN, n };
}

/** 1.4826 times the median absolute deviation. */
export function robustSigma(values) {
  const m = median(values);
  return 1.4826 * median(values.map((v) => Math.abs(v - m)));
}

/** Holm-adjusted p-values in one family. */
export function holm(p) {
  const idx = p.map((v, i) => i).filter((i) => Number.isFinite(p[i])).sort((a, b) => p[a] - p[b] || a - b);
  const m = idx.length;
  const out = p.map(() => NaN);
  let run = 0;
  idx.forEach((i, r) => {
    run = Math.max(run, Math.min(1, (m - r) * p[i]));
    out[i] = run;
  });
  return out;
}

/** Benjamini-Hochberg q-values in one family. */
export function bh(p) {
  const idx = p.map((v, i) => i).filter((i) => Number.isFinite(p[i])).sort((a, b) => p[a] - p[b] || a - b);
  const m = idx.length;
  const out = p.map(() => NaN);
  let run = 1;
  for (let r = m - 1; r >= 0; r--) {
    run = Math.min(run, (p[idx[r]] * m) / (r + 1));
    out[idx[r]] = Math.min(1, run);
  }
  return out;
}

function logChoose(n, k) {
  return lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1);
}
function lgamma(z) {
  // Lanczos approximation
  const g = 7;
  const c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059,
    12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  if (z < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * z)) - lgamma(1 - z);
  z -= 1;
  let x = c[0];
  for (let i = 1; i < g + 2; i++) x += c[i] / (z + i);
  const t = z + g + 0.5;
  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(x);
}

/** One-sided exact test that the window's rate exceeds the baseline's, as stats.poisson_rate_test. */
export function poissonRateTest(x1, e1, x0, e0) {
  if (!(e1 > 0 && e0 > 0)) return { p: NaN, ratio: NaN };
  const share = e1 / (e0 + e1);
  const nTot = x0 + x1;
  let p = 0;
  for (let k = x1; k <= nTot; k++) p += Math.exp(logChoose(nTot, k) + k * Math.log(share) + (nTot - k) * Math.log(1 - share));
  return { p: Math.min(1, p), ratio: (x1 / e1) / (Math.max(x0, 0.5) / e0) };
}
