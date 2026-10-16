// Level 6, the lore of the delvers: the statistics, learnt by playing. Three playgrounds use the same tests as Moria
// (ported in stats.js) on made-up data; the real scan's p-values sit beside them.

import { axis, chart, chartCard, dataTable, tipHtml, tokens } from "../charts.js";
import { num, term, tip } from "../glossary.js";
import { seriesOption } from "../seriesChart.js";
import { bh, holm, mannKendall, normSf, poissonRateTest, robustSigma, theilSen } from "../stats.js";
import { state } from "../state.js";
import { css, el, fmt, gaussian, n, pct, pval, rng } from "../util.js";

export function render(root) {
  const d = state.data;
  root.append(el("div.view-head", el("div",
    el("div.eyebrow", "Lore of the delvers"),
    el("h1", "Statistics explained"),
    el("p.lede", "The ideas behind Moria's numbers, learnt by playing with made-up data. Each playground runs the same tests Moria runs (ported from its code), so what you see here is how the real detectors behave."))));
  root.append(el("div.section", el("h2", "1. Dig a series: is it a trend?", tip("trend"))), digSeries(d));
  root.append(el("div.section", el("h2", "2. Durin's Bane: why delving too greedily wakes false alarms", tip("multiple_testing"))), bane(d));
  root.append(pvalues(d));
  root.append(el("div.section", el("h2", "3. Rare finds: when is a small count a surge?", tip("low_base_surge"))), surge(d));
  root.append(el("div.section", el("h2", "Moria's rules at a glance")), rules(d));
}

// ------------------------------------------------------------------------------------------------ 1. dig a series

function labels(n_) {
  const out = [];
  let y = 2022, m = 11;
  for (let i = 0; i < n_; i++) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
    m += 1;
    if (m > 12) { m = 1; y += 1; }
  }
  return out;
}

function digSeries(d) {
  const N = 48;
  const p = { trend: 6, noise: 4, jump: 0, jumpAt: 36, spike: 0, seed: 7 };
  const box = el("div.chart.tall");
  const verdicts = el("div");
  const draw = () => {
    const rand = rng(p.seed);
    const v = [];
    for (let t = 0; t < N; t++) v.push(100 + (p.trend / 12) * t + p.noise * gaussian(rand) + (t >= p.jumpAt ? p.jump : 0) + (t === N - 1 ? p.spike : 0));
    const periods = labels(N);
    const fits = [];
    const rows = [];
    [12, 24, 36].forEach((w, j) => {
      const win = v.slice(N - w);
      const x = win.map((_, i) => i);
      const ts = theilSen(x, win, 0.05);
      const mk = mannKendall(win);
      const sig = mk.p < 0.05 && (ts.lo > 0 || ts.hi < 0);
      const xs = x;
      fits.push({ window: `w${j + 1}`, periods: w, start: periods[N - w], end: periods[N - 1], slope: ts.slope, lo: ts.lo, hi: ts.hi, intercept: ts.intercept,
        x_mid: (xs[(xs.length - 1) >> 1] + xs[xs.length >> 1]) / 2, y_mid: median(win), sig });
      rows.push({ w: `w${j + 1} (last ${w} months)`, slope: ts.slope * 12, lo: ts.lo * 12, hi: ts.hi * 12, p: mk.p, sig });
    });
    const sigs = rows.filter((r) => r.sig);
    const dirs = new Set(sigs.map((r) => Math.sign(r.slope)));
    const isTrend = sigs.length >= 2 && dirs.size === 1;
    // the anomaly test on the latest value: a line fitted on the 24 months before it
    const b = 24;
    const baseV = v.slice(N - 1 - b, N - 1);
    const bx = baseV.map((_, i) => i);
    const bt = theilSen(bx, baseV);
    const pred = bt.intercept + bt.slope * b;
    const scale = Math.max(robustSigma(baseV.map((y, i) => y - (bt.intercept + bt.slope * i))), 1e-9);
    const z = (v[N - 1] - pred) / scale;
    const pz = 2 * normSf(Math.abs(z));
    const change = Math.abs(v[N - 1] - pred) / Math.max(Math.abs(pred), robustSigma(baseV));
    const isAnomaly = pz < 0.01 && change >= 0.25;
    // the acceleration's halves over the longest window
    const w36 = v.slice(N - 36), x36 = w36.map((_, i) => i);
    const early = theilSen(x36.slice(0, 18), w36.slice(0, 18)), recent = theilSen(x36.slice(18), w36.slice(18));
    const s = {
      series_id: "playground", label: "Your series", periods, values: v, y: v, transform: "level", frequency: "M", fits,
      anomaly: { period: periods[N - 1], start: periods[N - 1 - b], baseline: b, slope: bt.slope, intercept: bt.intercept, scale, z_band: 2.5758, flagged: isAnomaly },
      acceleration: { periods: 36, start: periods[N - 36], half: 18, early: { slope: early.slope, intercept: early.intercept }, recent: { slope: recent.slope, intercept: recent.intercept } },
    };
    chart(box, seriesOption([{ s, colour: css("--t-trend"), name: "Your series" }], { mode: "natural", fits: "all", band: true, anomaly: true, accel: true, changes: false }));
    verdicts.replaceChildren(
      el("div.row-flex.mb", el("span.verdict." + (isTrend ? "yes" : "no"), isTrend ? "✓ A trend" : "Not a trend"), el("span.verdict." + (isAnomaly ? "yes" : "no"), isAnomaly ? "✓ The last value is an anomaly" : "The last value is within reach")),
      el("div.table-wrap", el("table.data",
        el("thead", el("tr", el("th", term("windows", "Window")), el("th.n", term("theil_sen", "Slope a year")), el("th.n", term("ci", "95% range")), el("th.n", term("p_value", "p (Mann-Kendall)")), el("th", "Significant?"))),
        el("tbody", ...rows.map((r) => el("tr", el("td", r.w), el("td.n", fmt(r.slope, 3)), el("td.n", `${fmt(r.lo, 3)} to ${fmt(r.hi, 3)}`), el("td.n", num("p_value", r.p, pval(r.p))), el("td", r.sig ? "yes" : "no")))))),
      el("p.small.mt", `A trend needs 2 of the 3 windows significant, all the same way (here: ${sigs.length}). The last value is `, num("z", z, `${fmt(Math.abs(z), 2)} wobbles`), ` ${z >= 0 ? "above" : "below"} the expected ${fmt(pred, 4)}; Moria's bar is p below 0.01 and at least 25% off. The halves of the last 36 months slope at ${fmt(early.slope * 12, 3)} then ${fmt(recent.slope * 12, 3)} a year.`),
      el("p.small.muted", "In Moria, each p-value is also adjusted for the thousands of other series in its family (see Durin's Bane, below), so the real bar is higher than here."));
  };
  const slider = (key, label, min, max, step, unit = "") => {
    const input = el("input", { type: "range", min, max, step, value: p[key], "aria-label": label });
    const o = el("output", `${p[key]}${unit}`);
    input.oninput = () => { p[key] = Number(input.value); o.textContent = `${p[key]}${unit}`; draw(); };
    return el("div.slider", el("label", label), o, input);
  };
  const dig = el("button.btn.btn-gold", { type: "button", onclick: (e) => { p.seed += 1; e.currentTarget.animate([{ transform: "rotate(0)" }, { transform: "rotate(-14deg)" }, { transform: "rotate(8deg)" }, { transform: "rotate(0)" }], { duration: 450 }); draw(); } }, "⛏ Dig again (new noise)");
  requestAnimationFrame(draw);
  return el("div.playground",
    el("div.card",
      el("h3", "Shape your series"),
      el("p.small.muted", "48 months of a made-up index. Change the ingredients and watch the tests."),
      slider("trend", "Trend (points a year)", -30, 30, 1),
      slider("noise", "Noise (wobble)", 0, 20, 0.5),
      slider("jump", "A jump of", -40, 40, 1),
      slider("jumpAt", "… at month", 1, 47, 1),
      slider("spike", "A spike in the last month", -60, 60, 1),
      dig,
      el("p.small.mt", "Try: no trend and lots of noise (rarely a trend); a jump at month 36 (a level change can fake a trend in the short window); a big last-month spike (an anomaly, not a trend).")),
    el("div.card", box, verdicts));
}

function median(a) {
  const s = a.slice().sort((x, y) => x - y);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

// ----------------------------------------------------------------------------------------------- 2. Durin's Bane

function bane(d) {
  const mt = d.scan.multiple_testing;
  const p = { tests: 2000, real: 5, effect: 3.5, method: "holm", seed: 3 };
  const canvas = el("canvas.dots-grid", { width: 900, height: 360, role: "img", "aria-label": "Each dot is one series tested" });
  const tally = el("div.grid.g3");
  const draw = () => {
    const rand = rng(p.seed);
    const N = p.tests;
    const isReal = [], pv = [];
    for (let i = 0; i < N; i++) {
      const r = rand() < p.real / 100;
      isReal.push(r);
      const z = gaussian(rand) + (r ? p.effect : 0);
      pv.push(2 * normSf(Math.abs(z)));
    }
    const adj = { raw: pv, bh: bh(pv), holm: holm(pv) };
    const res = {};
    for (const [k, a] of Object.entries(adj)) {
      let tp = 0, fp = 0;
      a.forEach((q, i) => { if (q < 0.05) (isReal[i] ? tp++ : fp++); });
      res[k] = { tp, fp, found: tp + fp };
    }
    const realN = isReal.filter(Boolean).length;
    const name = { raw: "No adjustment", bh: "Benjamini-Hochberg", holm: "Holm (Moria's rule)" };
    tally.replaceChildren(...["raw", "bh", "holm"].map((k) => el(`div.card.flat${k === p.method ? ".tint" : ""}`, { style: { cursor: "pointer" }, onclick: () => { p.method = k; draw(); } },
      el("h4", name[k], " ", tip(k === "raw" ? "p_value" : k)),
      el("p", el("strong", n(res[k].tp)), ` of ${n(realN)} real changes found`),
      el("p", el("strong", { style: { color: css("--s-critical") } }, n(res[k].fp)), " false alarms (Balrogs woken)"),
      el("p.small.muted", res[k].found ? `${pct(res[k].fp / res[k].found)} of what it found is false` : "Found nothing"))));
    // the dots: a sample when there are many
    const ctx2 = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx2.clearRect(0, 0, W, H);
    const shown = Math.min(N, 2400);
    const cols = Math.ceil(Math.sqrt((shown * W) / H));
    const cell = W / cols;
    const a = adj[p.method];
    const colours = { tp: css("--s-good"), fp: css("--s-critical"), miss: css("--t-trend"), quiet: css("--line-strong") };
    for (let i = 0; i < shown; i++) {
      const x = (i % cols) * cell + cell / 2, y = Math.floor(i / cols) * cell + cell / 2;
      const flagged = a[i] < 0.05;
      const k = flagged ? (isReal[i] ? "tp" : "fp") : isReal[i] ? "miss" : "quiet";
      ctx2.beginPath();
      ctx2.arc(x, y, Math.max(1.5, cell * 0.36), 0, Math.PI * 2);
      if (k === "miss") { ctx2.strokeStyle = colours.miss; ctx2.lineWidth = 1.5; ctx2.stroke(); }
      else { ctx2.fillStyle = colours[k]; ctx2.fill(); }
    }
    note.textContent = N > shown ? `Showing the first ${n(shown)} of ${n(N)} series.` : "";
  };
  const note = el("p.small.muted");
  const slider = (key, label, min, max, step, fmtV = (v) => String(v)) => {
    const input = el("input", { type: "range", min, max, step, value: p[key], "aria-label": label });
    const o = el("output", fmtV(p[key]));
    input.oninput = () => { p[key] = Number(input.value); o.textContent = fmtV(p[key]); draw(); };
    return el("div.slider", el("label", label), o, input);
  };
  requestAnimationFrame(draw);
  return el("div",
    el("p.lede", `The dwarves of Moria delved too greedily and too deep, and woke Durin's Bane. Test enough series and you will wake false alarms: at p < 0.05, about 1 in 20 series with nothing going on looks significant. Moria tested ${n(mt.series)} series this scan.`),
    el("div.playground",
      el("div.card",
        el("h3", "Set the dig"),
        slider("tests", "Series tested", 100, 27000, 100, (v) => n(v)),
        slider("real", "Share with a real change (%)", 0, 30, 1, (v) => `${v}%`),
        slider("effect", "How strong the real changes are", 1, 6, 0.5),
        el("button.btn.btn-gold", { type: "button", onclick: () => { p.seed += 1; draw(); } }, "⛏ Dig again"),
        el("p.small.mt", "Click a method on the right to colour the dots by it.")),
      el("div.card",
        tally,
        canvas,
        el("div.legend.mt",
          el("span", el("i", { style: { background: css("--s-good"), borderRadius: "50%" } }), "Real change, found"),
          el("span", el("i", { style: { background: css("--s-critical"), borderRadius: "50%" } }), "False alarm (a Balrog)"),
          el("span", el("i", { style: { border: `2px solid ${css("--t-trend")}`, borderRadius: "50%" } }), "Real change, missed"),
          el("span", el("i", { style: { background: css("--line-strong"), borderRadius: "50%" } }), "Nothing going on, left alone")),
        note)),
    el("div.callout.info.mt", el("div.c-ico", "✦"), el("div",
      el("h4", "The trade-off"),
      el("p", "No adjustment finds the most real changes but wakes many Balrogs. Holm keeps the chance of even one false alarm in a family at 5%, at the cost of missing some real changes. Benjamini-Hochberg sits between: about 5% of what it finds is false. Moria uses Holm and also asks for 2 of 3 windows; it shows Benjamini-Hochberg's count for comparison."),
      el("p", `In this scan: `, el("strong", n(mt.trends_holm)), " trends under Holm, against ", el("strong", n(mt.trends_bh)), " under Benjamini-Hochberg."))));
}

function pvalues(d) {
  const mt = d.scan.multiple_testing;
  let w = 2;
  const host = el("div.mt");
  const draw = () => {
    const W = mt.windows[w];
    host.replaceChildren(chartCard({
      title: `The real scan: p-values of every trend test (window ${W.window.slice(1)})`,
      sub: `${n(W.tested)} series tested in this window. If nothing were changing anywhere, the bars would sit level at the dashed height. The tall bar at the left is real change (plus some luck).`,
      tip: tip("p_value"),
      actions: el("div.toggle", ...mt.windows.map((x, i) => el("button", { type: "button", "aria-pressed": String(i === w), onclick: () => { w = i; draw(); } }, x.window))),
      render: (box) => {
        const tk = tokens();
        const flat = W.tested / 20;
        chart(box, {
          grid: { left: 60, right: 20, top: 20, bottom: 40 },
          xAxis: axis("category", { data: W.hist_raw.map((_, i) => `${(i * 0.05).toFixed(2)}`), name: "p-value (before adjustment)", nameLocation: "middle", nameGap: 26 }),
          yAxis: axis("value", { name: "series" }),
          tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => tipHtml(`p from ${ps[0].name} to ${(+ps[0].name + 0.05).toFixed(2)}`, [[tk.mithril, "series", n(ps[0].value)], [null, "if nothing were changing", n(Math.round(flat))]]) },
          series: [{ type: "bar", data: W.hist_raw.map((v, i) => ({ value: v, itemStyle: { color: i === 0 ? tk.mithril : tk.neutral, borderRadius: [4, 4, 0, 0] } })), barCategoryGap: "10%",
            markLine: { silent: true, symbol: "none", data: [{ yAxis: flat }], lineStyle: { color: tk.critical, type: [6, 4] }, label: { formatter: "chance alone", color: tk.muted, position: "insideEndTop" } } }],
        });
      },
      table: () => dataTable(W.hist_raw.map((v, i) => ({ v, i })), [{ label: "p from", value: (r) => (r.i * 0.05).toFixed(2) }, { label: "Series", value: (r) => r.v, n: true }]),
    }), el("div.grid.g3.mt",
      el("div.card.flat.stat", el("div.stat-label", "Below 0.05 with no adjustment"), el("div.stat-value", n(W.raw_05)), el("p.stat-note", `About ${n(Math.round(W.tested * 0.05))} would get there by chance alone`)),
      el("div.card.flat.stat", el("div.stat-label", "Benjamini-Hochberg q below 0.05", tip("bh")), el("div.stat-value", n(W.bh_05)), el("p.stat-note", "Shown for comparison")),
      el("div.card.flat.stat", el("div.stat-label", "Holm p below 0.05", tip("holm")), el("div.stat-value", n(W.holm_05)), el("p.stat-note", "Moria's rule, before the 2-of-3 windows test"))));
  };
  draw();
  return host;
}

// -------------------------------------------------------------------------------------------------- 3. rare finds

function surge(d) {
  const sv = d.config.detect.surge || {};
  const p = { x0: 2, x1: 6, e0: 24, e1: 3 };
  const box = el("div.chart.short");
  const verdict = el("div");
  const draw = () => {
    const t = poissonRateTest(p.x1, p.e1, p.x0, p.e0);
    const expected = (p.x0 * p.e1) / p.e0;
    const ok = t.p < 0.05 && t.ratio >= (sv.min_ratio ?? 3) && p.x1 >= (sv.min_count ?? 3);
    verdict.replaceChildren(
      el("span.verdict." + (ok ? "yes" : "no"), ok ? "✓ A low-base surge" : "Not a surge"),
      el("p.mt", `${p.x1} in the last ${p.e1} months against ${fmt(expected, 3)} expected from the baseline: a rate `, el("strong", `${fmt(t.ratio, 3)} times`), " the baseline's. ", num("p_value", t.p, `p = ${pval(t.p)}`), "."),
      el("p.small.muted", `Moria's bar: p (Holm-adjusted) below 0.05, a ratio of at least ${sv.min_ratio ?? 3}, and at least ${sv.min_count ?? 3} in the window. Counts are also taken as shares of the source's volume, so a source that grew doesn't fake a surge.`));
    const tk = tokens();
    chart(box, {
      grid: { left: 50, right: 20, top: 16, bottom: 28 },
      xAxis: axis("category", { data: ["Expected from the baseline", "Seen in the window"] }),
      yAxis: axis("value", { minInterval: 1 }),
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => tipHtml(ps[0].name, [[ps[0].color, "count", fmt(ps[0].value, 3)]]) },
      series: [{ type: "bar", barMaxWidth: 60, data: [{ value: expected, itemStyle: { color: tk.neutral, borderRadius: [6, 6, 0, 0] } }, { value: p.x1, itemStyle: { color: ok ? tk.good : tk.mithril, borderRadius: [6, 6, 0, 0] } }], label: { show: true, position: "top", color: tk.ink2, formatter: (x) => fmt(x.value, 3) } }],
    });
  };
  const slider = (key, label, min, max) => {
    const input = el("input", { type: "range", min, max, step: 1, value: p[key], "aria-label": label });
    const o = el("output", String(p[key]));
    input.oninput = () => { p[key] = Number(input.value); o.textContent = String(p[key]); draw(); };
    return el("div.slider", el("label", label), o, input);
  };
  requestAnimationFrame(draw);
  return el("div.playground",
    el("div.card", el("h3", "Count the finds"),
      slider("x0", "Found in the baseline", 0, 40), slider("e0", "Baseline length (months)", 6, 36),
      slider("x1", "Found in the window", 0, 40), slider("e1", "Window length (months)", 1, 6),
      el("p.small.mt", "With small numbers, chance is lumpy: 3 where you expected 1 is less surprising than it sounds. The exact Poisson test knows how lumpy.")),
    el("div.card", box, verdict,
      el("div.callout.mt", el("div.c-ico", "✦"), el("div", el("h4", "And for documents"), el("p.small", `A weak signal from documents also needs at least ${d.documents.min_items} separate items (after copies are merged) from at least ${d.documents.min_sources} sources, so one press release syndicated forty times can't make one.`)))));
}

// ------------------------------------------------------------------------------------------------- the rules

function rules(d) {
  const c = d.config.detect;
  const w = c.windows || {};
  const rows = [
    ["Trend", `Theil-Sen slope and Mann-Kendall test in 3 windows (monthly ${w.M?.join(", ")}; quarterly ${w.Q?.join(", ")}; yearly ${w.A?.join(", ")} periods); Holm-adjusted p below ${c.alpha} in at least ${c.trend_min_windows} windows, the same direction.`, "trend"],
    ["Acceleration", `The recent half steeper than the earlier half (bootstrap, Holm p below ${c.alpha}), or a change point to a steeper slope on a trend; at least ${c.accel_min_change} a year of change in the growth rate.`, "acceleration"],
    ["Anomaly", `The latest value outside a band fitted on the ${c.anomaly_baseline?.M} months before it (Holm p below ${c.anomaly_alpha}) and at least ${pct(c.anomaly_min_change)} off.`, "anomaly"],
    ["Low-base surge", `An exact Poisson test of the window's rate against the baseline's, as shares of the source's volume; ratio at least ${c.surge?.min_ratio}.`, "low_base_surge"],
    ["Weak signal", `New terms, pairings or sudden rises in the last ${c.documents?.window_days} days against the ${c.documents?.baseline_days} before; at least ${c.documents?.min_items} items from ${c.documents?.min_sources} sources.`, "weak_signal"],
    ["Coverage", `A window needs ${pct(c.min_coverage)} of its periods; a count series a mean of ${c.min_mean_count} a period (smaller ones go to the surge test).`, "windows"],
  ];
  return el("div.table-wrap", el("table.data",
    el("thead", el("tr", el("th", "Finding"), el("th", "Moria's rule"))),
    el("tbody", ...rows.map(([a, b, k]) => el("tr", el("td", el("strong", term(k, a))), el("td", b))))));
}
