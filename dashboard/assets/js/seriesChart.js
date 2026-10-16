// A series as Moria tested it, drawn so a person can read it: the values over time; each trend window's Theil-Sen
// line with its 95% interval as a bow-tie band (the slopes' range, pivoting at the window's middle); the anomaly's
// expected band (a line fitted on the periods before the latest one, plus or minus 2.58 robust wobbles: 99%); the
// acceleration's two halves; change points; the surge window. Nothing is forecast: every line stays inside the data.
//
// Display modes: "natural" (counts, shares or levels as published), "indexed" (each series = 100 at the first
// period they all share: for comparing different units on one axis) and "tested" (the exact quantity the detectors
// tested: the log of a share or count, or the level).

import { axis, tipHtml, tokens } from "./charts.js";
import { fmt, periodName, periodStart } from "./util.js";

const UNIT_NAMES = { log_share: "share of the source's volume", log_count: "count", level: "level" };

/** Inverse of the tested transform at position i (so a fitted line can be drawn in natural units). */
function untransform(s, v, i) {
  if (v == null) return null;
  if (s.transform === "level") return v;
  if (s.transform === "log_count") return Math.exp(v) - 0.5;
  const d = s.denom?.[i];
  return d ? Math.exp(v) - 0.5 / d : null;
}

function natural(s, i) {
  const v = s.values[i];
  if (v == null) return null;
  if (s.transform === "log_share") return s.denom?.[i] ? v / s.denom[i] : null;
  return v;
}

export function unitName(s) {
  return UNIT_NAMES[s.transform] || "value";
}

/** One series' layers in a mode: {points, fits:[{line, lo, hi, w}], anomaly, accel, changes, surge}. */
export function layers(s, mode, base = 1) {
  const idx = Object.fromEntries(s.periods.map((p, i) => [p, i]));
  const t = s.periods.map(periodStart);
  const conv = (v, i) => {
    if (v == null || !Number.isFinite(v)) return null;
    if (mode === "tested") return v;
    const nat = untransform(s, v, i);
    return nat == null ? null : mode === "indexed" ? (nat / base) * 100 : nat;
  };
  const show = (i) => {
    if (mode === "tested") return s.y[i];
    const v = natural(s, i);
    return v == null ? null : mode === "indexed" ? (v / base) * 100 : v;
  };
  const points = s.periods.map((p, i) => [t[i], show(i), p]);
  const fits = (s.fits || []).map((f) => {
    const i0 = idx[f.start];
    if (i0 == null) return null;
    const line = [], lo = [], hi = [];
    for (let x = 0; x < f.periods; x++) {
      const i = i0 + x;
      if (i >= s.periods.length) break;
      const yl = f.intercept + f.slope * x;
      const a = f.y_mid + f.lo * (x - f.x_mid);
      const b = f.y_mid + f.hi * (x - f.x_mid);
      line.push([t[i], conv(yl, i)]);
      lo.push([t[i], conv(Math.min(a, b), i)]);
      hi.push([t[i], conv(Math.max(a, b), i)]);
    }
    return { w: f.window, f, line, lo, hi };
  }).filter(Boolean);
  let anomaly = null;
  if (s.anomaly) {
    const a = s.anomaly, i0 = idx[a.start];
    if (i0 != null) {
      const mid = [], lo = [], hi = [];
      for (let x = 0; x <= a.baseline; x++) {
        const i = i0 + x;
        if (i >= s.periods.length) break;
        const c = a.intercept + a.slope * x;
        mid.push([t[i], conv(c, i)]);
        lo.push([t[i], conv(c - a.z_band * a.scale, i)]);
        hi.push([t[i], conv(c + a.z_band * a.scale, i)]);
      }
      const k = idx[a.period];
      anomaly = { a, mid, lo, hi, point: k != null ? [t[k], show(k)] : null };
    }
  }
  let accel = null;
  if (s.acceleration) {
    const a = s.acceleration, i0 = idx[a.start];
    if (i0 != null) {
      const seg = (part, from, to) => {
        const out = [];
        for (let x = from; x < to; x++) if (i0 + x < s.periods.length) out.push([t[i0 + x], conv(part.intercept + part.slope * x, i0 + x)]);
        return out;
      };
      accel = { a, early: seg(a.early, 0, a.half), recent: seg(a.recent, a.half, a.periods) };
    }
  }
  const changes = [];
  if (s.change_slope && idx[s.change_slope.period] != null) changes.push({ at: t[idx[s.change_slope.period]], what: "slope", c: s.change_slope });
  if (s.change_level && idx[s.change_level.period] != null) changes.push({ at: t[idx[s.change_level.period]], what: "level", c: s.change_level });
  let surge = null;
  if (s.surge?.window) {
    const [a, b] = s.surge.window.split("/");
    if (idx[a] != null && idx[b] != null) surge = { from: t[idx[a]], to: t[idx[b]], s: s.surge };
  }
  return { points, fits, anomaly, accel, changes, surge };
}

/** The base for indexing: each series' natural value at the first period every series has (or its own first). */
export function indexBases(list) {
  const firsts = list.map((s) => s.periods.findIndex((_, i) => natural(s, i) != null && natural(s, i) !== 0));
  const common = Math.max(...list.map((s, k) => periodStart(s.periods[Math.max(0, firsts[k])])));
  return list.map((s, k) => {
    let i = s.periods.findIndex((p, j) => periodStart(p) >= common && natural(s, j) != null && natural(s, j) !== 0);
    if (i < 0) i = firsts[k];
    return { base: i >= 0 ? Math.abs(natural(s, i)) || 1 : 1, at: i >= 0 ? s.periods[i] : null };
  });
}

/**
 * The chart option for one or more series. items: [{s, colour, name}]. opts: {mode, fits: "best"|"all"|"none"|"w1".."w3",
 * band, anomaly, accel, changes, surge, zoom}.
 */
export function seriesOption(items, opts = {}) {
  const tk = tokens();
  const mode = opts.mode || "natural";
  const bases = mode === "indexed" ? indexBases(items.map((i) => i.s)) : items.map(() => ({ base: 1 }));
  const series = [];
  const legend = [];
  let bandN = 0;
  const band = (lo, hi, colour, name, opacity = 0.16) => {
    const stack = `band${bandN++}`;
    const loData = lo.map(([x, v]) => [x, v]);
    const diff = hi.map(([x, v], k) => [x, v == null || lo[k][1] == null ? null : v - lo[k][1]]);
    series.push({ name: `_${name}_lo`, type: "line", data: loData, stack, stackStrategy: "all", symbol: "none", lineStyle: { opacity: 0 }, silent: true, z: 1, tooltip: { show: false } });
    series.push({ name: `_${name}_hi`, type: "line", data: diff, stack, stackStrategy: "all", symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color: colour, opacity }, silent: true, z: 1, tooltip: { show: false } });
  };
  items.forEach(({ s, colour, name }, k) => {
    const L = layers(s, mode, bases[k].base);
    legend.push(name);
    const markArea = opts.surge !== false && L.surge
      ? { silent: true, itemStyle: { color: tk.gold, opacity: 0.16 }, label: { color: tk.muted, fontSize: 11 }, data: [[{ xAxis: L.surge.from, name: "surge window" }, { xAxis: L.surge.to }]] }
      : undefined;
    const fitsWanted = opts.fits ?? "best";
    let fits = [];
    if (fitsWanted === "all") fits = L.fits;
    else if (fitsWanted === "best") {
      const sig = L.fits.filter((f) => f.f.sig);
      fits = sig.length ? [sig[sig.length - 1]] : L.fits.slice(-1);
    } else if (fitsWanted !== "none") fits = L.fits.filter((f) => f.w === fitsWanted);
    for (const f of fits) {
      if (opts.band !== false) band(f.lo, f.hi, colour, `${name} ${f.w}`);
      series.push({ name: `_fit ${name} ${f.w}`, type: "line", data: f.line, symbol: "none", lineStyle: { color: colour, width: 2, opacity: 0.85 }, z: 3, tooltip: { show: false } });
    }
    if (opts.anomaly !== false && L.anomaly) {
      band(L.anomaly.lo, L.anomaly.hi, tk.neutral, `${name} expected`, 0.22);
      series.push({ name: `_expected ${name}`, type: "line", data: L.anomaly.mid, symbol: "none", lineStyle: { color: tk.ink2, width: 1.5, opacity: 0.6 }, z: 2, tooltip: { show: false } });
      if (L.anomaly.point) {
        series.push({ name: `_anomaly ${name}`, type: "scatter", data: [L.anomaly.point], symbolSize: 16, itemStyle: { color: "transparent", borderColor: L.anomaly.a.flagged ? tk.critical : tk.serious, borderWidth: 3 }, z: 6, tooltip: { show: false } });
      }
    }
    if (opts.accel && L.accel) {
      series.push({ name: `_early ${name}`, type: "line", data: L.accel.early, symbol: "none", lineStyle: { color: tk.ink2, width: 2, type: [2, 3] }, z: 4, tooltip: { show: false } });
      series.push({ name: `_recent ${name}`, type: "line", data: L.accel.recent, symbol: "none", lineStyle: { color: tk.critical, width: 2.5 }, z: 4, tooltip: { show: false } });
    }
    const markLine = opts.changes !== false && L.changes.length
      ? { silent: true, symbol: "none", lineStyle: { color: tk.muted, type: "solid", width: 1 }, label: { show: items.length === 1, formatter: (p) => p.name, color: tk.muted, fontSize: 11, position: "insideEndTop" },
          data: L.changes.map((c) => ({ xAxis: c.at, name: c.what === "slope" ? "slope changes" : "level shifts" })) }
      : undefined;
    series.push({
      name, type: "line", data: L.points, showSymbol: L.points.length <= 60, symbolSize: 6, connectNulls: false,
      lineStyle: { color: colour, width: 2 }, itemStyle: { color: colour, borderColor: tk.surface, borderWidth: 2 }, emphasis: { focus: "series" }, z: 5,
      markLine,
      markArea,
    });
  });
  // open on the recent periods (the windows Moria tested) when a series is long; the slider widens it
  let recent = {};
  if (opts.recent && items.length) {
    const longest = items.reduce((a, i) => (i.s.periods.length > a.s.periods.length ? i : a), items[0]).s;
    if (longest.periods.length > opts.recent) recent = { startValue: periodStart(longest.periods[longest.periods.length - opts.recent]) };
  }
  const unit = mode === "tested" ? "as tested (log scale for counts)" : mode === "indexed" ? "index (first shared period = 100)" : items.length ? unitName(items[0].s) : "";
  return {
    grid: { left: 64, right: 24, top: 36, bottom: opts.zoom ? 70 : 36 },
    legend: { data: legend, top: 0, right: 0, textStyle: { color: tk.ink2 }, icon: "roundRect", itemWidth: 16, itemHeight: 4, type: "scroll", width: "60%" },
    xAxis: axis("time", { axisLabel: { color: tk.muted, hideOverlap: true } }),
    yAxis: axis("value", { name: unit, nameLocation: "end", nameGap: 14, nameTextStyle: { color: tk.muted, align: "left" }, scale: true, axisLabel: { color: tk.muted, formatter: (v) => (mode === "natural" && items[0]?.s.transform === "log_share" ? `${+(v * 100).toPrecision(3)}%` : fmt(v)) } }),
    dataZoom: opts.zoom ? [{ type: "inside", ...recent }, { type: "slider", height: 22, bottom: 14, borderColor: tk.line, fillerColor: "rgba(123,107,227,.15)", textStyle: { color: tk.muted }, ...recent }] : [],
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: tk.axis } },
      formatter: (ps) => {
        const rows = ps.filter((p) => !p.seriesName.startsWith("_") && p.value?.[1] != null).map((p) => {
          const it = items.find((i) => i.name === p.seriesName);
          const v = p.value[1];
          const shown = mode === "natural" && it?.s.transform === "log_share" ? `${fmt(v * 100, 3)}%` : fmt(v, 4);
          return [p.color, p.seriesName.length > 44 ? `${p.seriesName.slice(0, 42)}…` : p.seriesName, shown];
        });
        const label = ps.find((p) => p.value?.[2])?.value[2];
        return tipHtml(label ? periodName(label) : "", rows);
      },
    },
    series,
  };
}
