// Change over time: the series behind the candidates over time.
// Choose up to eight, overlay them, and switch on what Moria measured: trend lines with their uncertainty, the
// expected band, accelerations, change points and surge windows. One axis only: different units are indexed.

import { needsPrivate, typeTag } from "../bits.js";
import { axis, chart, chartCard, dataTable, tipHtml, tokens } from "../charts.js";
import { num, term, tip } from "../glossary.js";
import { loadPractice, pickFile } from "../main.js";
import { seriesOption, unitName } from "../seriesChart.js";
import { candidate, hasDetail, state } from "../state.js";
import { css, debounce, el, fmt, FREQ_NAMES, n, pval, signedPct } from "../util.js";

const SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
const SLOTS_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
const slotColour = (k) => (document.documentElement.dataset.theme === "dark" ? SLOTS_DARK : SLOTS)[k % 8];

export function render(root, ctx) {
  root.append(el("div.view-head", el("div",
    el("div.eyebrow", "Series over time"),
    el("h1", "Change over time"),
    el("p.lede", "The series behind the candidates, drawn as Moria tested them. Overlay several, switch on the trend lines and their uncertainty, and see the expected band an anomaly broke out of. Nothing here is a forecast: every line stays inside the data."))));
  if (!hasDetail()) {
    root.append(needsPrivate("The series themselves are private, so this section needs the private file (or the practice data).", { pickFile, loadPractice }));
    root.append(el("div.section", el("h2", "What was tested")), testedCard(state.data));
    root.append(el("div.callout.info.mt", el("div.c-ico", "✦"), el("div", el("h4", "Want to see how a trend line and its band work?"), el("p", "The ", el("a", { href: "#/statistics" }, "Statistics explained"), " has a playground: make up a series, add a trend, noise or a jump, and watch Moria's tests react."))));
    return;
  }
  root.append(mirror(ctx));
  root.append(el("div.section", el("h2", "What was tested")), testedCard(state.data));
}

function seriesCandidates() {
  const out = [];
  for (const c of state.data.candidates) {
    for (const s of c.series || []) {
      if (["subject", "reference"].includes(s.role) && state.data.series[s.id]) out.push({ id: s.id, c, role: s.role, s: state.data.series[s.id] });
    }
  }
  return out;
}

function mirror(ctx) {
  const pool = seriesCandidates();
  const byId = new Map();
  for (const p of pool) if (!byId.has(p.id) || p.c.queue) byId.set(p.id, p);
  const opts = { mode: "natural", fits: "best", band: true, anomaly: true, accel: false, changes: true, surge: true };
  if (!state.series.length) {
    const first = pool.filter((p) => p.c.queue && p.role === "subject").sort((a, b) => a.c.queue.rank - b.c.queue.rank)[0] || pool[0];
    if (first) state.series = [{ id: first.id, slot: 0 }];
  }
  const chips = el("div.pills");
  const box = el("div.chart.tall");
  const note = el("p.small.muted");
  const details = el("div.grid.g2.mt");
  const freeSlot = () => [0, 1, 2, 3, 4, 5, 6, 7].find((k) => !state.series.some((s) => s.slot === k));
  const add = (id) => {
    if (state.series.some((s) => s.id === id)) return;
    if (state.series.length >= 8) { note.textContent = "Eight is the most one chart can show clearly. Remove one first."; return; }
    state.series.push({ id, slot: freeSlot() });
    draw();
  };
  const remove = (id) => { state.series = state.series.filter((s) => s.id !== id); draw(); };
  const draw = () => {
    const items = state.series.map(({ id, slot }) => ({ s: state.data.series[id], colour: slotColour(slot), name: label(state.data.series[id]) })).filter((i) => i.s);
    chips.replaceChildren(...items.map((it, k) => el("span.pill", { "aria-pressed": "true" }, el("span.swatch", { style: { background: it.colour } }), it.name.length > 50 ? `${it.name.slice(0, 48)}…` : it.name,
      el("button.tipdot", { type: "button", "aria-label": "Remove", title: "Remove", onclick: () => remove(state.series[k].id) }, "×"))));
    const transforms = new Set(items.map((i) => `${i.s.transform}|${i.s.unit}`));
    let mode = opts.mode;
    note.textContent = "";
    if (items.length > 1 && mode === "natural" && transforms.size > 1) {
      mode = "indexed";
      note.textContent = "These series are in different units, so they are shown indexed to 100 at the first period they share: one honest axis instead of two.";
    }
    if (!items.length) {
      box.replaceChildren(el("p.muted", { style: { padding: "40px" } }, "Choose a series to draw."));
      details.replaceChildren();
      return;
    }
    const recent = { M: 72, Q: 32, A: 24, D: 180 }[items[0].s.frequency] || 60;
    chart(box, seriesOption(items, { ...opts, mode, zoom: true, recent }));
    details.replaceChildren(...items.map((it) => measured(it, ctx)));
  };
  // the picker
  const search = el("input", { type: "search", placeholder: "Search series by name…", "aria-label": "Search series", style: { width: "360px" } });
  const results = el("div.card.flat", { hidden: true, style: { position: "absolute", zIndex: 30, maxHeight: "340px", overflowY: "auto", width: "560px", marginTop: "6px", padding: "8px" } });
  search.oninput = debounce(() => {
    const q = search.value.trim().toLowerCase();
    if (!q) { results.hidden = true; return; }
    const hits = [...byId.values()].filter((p) => (p.s.label || "").toLowerCase().includes(q)).slice(0, 30);
    results.replaceChildren(...(hits.length ? hits.map((p) => el("button.btn.btn-ghost.btn-small", { type: "button", style: { display: "flex", width: "100%", justifyContent: "flex-start", textAlign: "left", borderRadius: "10px", marginBottom: "2px" },
      onclick: () => { add(p.id); results.hidden = true; search.value = ""; } }, typeTag(p.c.type), el("span", (p.s.label || p.id).slice(0, 80)), el("span.muted.small", ` · ${p.s.source} · ${FREQ_NAMES[p.s.frequency] || p.s.frequency}`))) : [el("p.muted.small", "No series match.")]));
    results.hidden = false;
  }, 150);
  search.addEventListener("blur", () => setTimeout(() => { results.hidden = true; }, 200));
  const quick = el("div.row-flex",
    el("button.btn.btn-small", { type: "button", onclick: () => {
      state.series = pool.filter((p) => p.c.queue && p.role === "subject").sort((a, b) => a.c.queue.rank - b.c.queue.rank).filter((p, i, a) => a.findIndex((x) => x.id === p.id) === i).slice(0, 4).map((p, k) => ({ id: p.id, slot: k }));
      draw();
    } }, "The queue's first four series"),
    el("button.btn.btn-small", { type: "button", onclick: () => {
      const pair = pool.filter((p) => p.c.subject_kind === "pair");
      const c = (pair.find((p) => p.c.queue) || pair[0])?.c;
      if (!c) { note.textContent = "No Australia-against-the-world pairs in this scan."; return; }
      state.series = c.series.filter((s) => state.data.series[s.id]).map((s, k) => ({ id: s.id, slot: k }));
      opts.mode = "indexed";
      modeSel.value = "indexed";
      draw();
    } }, "Australia against the world"),
    el("button.btn.btn-small", { type: "button", onclick: () => {
      const list = [...byId.values()];
      const p = list[Math.floor(Math.random() * list.length)];
      if (p) { state.series = [{ id: p.id, slot: 0 }]; draw(); }
    } }, "⛏ Dig at random"));
  // the controls
  const modeSel = el("select", { "aria-label": "Display" }, el("option", { value: "natural" }, "As published"), el("option", { value: "indexed" }, "Indexed (first shared period = 100)"), el("option", { value: "tested" }, "As Moria tested it (log scale for counts)"));
  modeSel.onchange = () => { opts.mode = modeSel.value; draw(); };
  const fitSel = el("select", { "aria-label": "Trend lines" }, el("option", { value: "best" }, "The longest significant window"), el("option", { value: "all" }, "All three windows"), el("option", { value: "w1" }, "Window 1 (shortest)"), el("option", { value: "w2" }, "Window 2"), el("option", { value: "w3" }, "Window 3 (longest)"), el("option", { value: "none" }, "None"));
  fitSel.onchange = () => { opts.fits = fitSel.value; draw(); };
  const toggle = (key, text, termKey) => el("label.check", el("input", { type: "checkbox", checked: opts[key], onchange: (e) => { opts[key] = e.target.checked; draw(); } }), text, termKey ? tip(termKey) : null);
  const controls = el("div.card.filters",
    el("div.field", "Add a series", el("div", { style: { position: "relative" } }, search, results)),
    el("div.field", "Quick picks", quick),
    el("label.field", "Display", modeSel),
    el("label.field", "Trend lines", fitSel),
    el("div.field", "Show", el("div.row-flex", toggle("band", "Uncertainty", "ci"), toggle("anomaly", "Expected band", "anomaly_band"), toggle("accel", "Acceleration halves", "acceleration"), toggle("changes", "Change points", "change_point"), toggle("surge", "Surge windows", "low_base_surge"))));
  requestAnimationFrame(draw);
  return el("div", controls,
    el("div.card", el("div.card-head", el("div", el("h3", "The mirror"), el("p.card-sub", "Hover for every series at a date; drag the slider below to zoom in time.")), chips), box, note,
      el("div.legend.mt",
        el("span", el("i.line", { style: { background: css("--ink-2") } }), "Trend line (Theil-Sen)"),
        el("span", el("i", { style: { background: "rgba(91,75,214,.18)" } }), "Its 95% range of slopes"),
        el("span", el("i", { style: { background: "rgba(161,156,181,.35)" } }), "Expected band (99%)"),
        el("span", el("i", { style: { background: "transparent", border: `3px solid ${css("--s-critical")}`, borderRadius: "50%" } }), "Anomaly"),
        el("span", el("i", { style: { background: "rgba(242,177,52,.3)" } }), "Surge window"))),
    details);
}

function label(s) {
  return s?.label || s?.series_id || "";
}

function measured(it, ctx) {
  const s = it.s;
  const owners = state.data.candidates.filter((c) => (c.series || []).some((x) => x.id === s.series_id));
  const fits = s.fits || [];
  const t = el("table.data");
  t.append(el("thead", el("tr", el("th", term("windows", "Window")), el("th", "Periods"), el("th.n", term("theil_sen", "Slope")), el("th.n", term("ci", "95% range")), el("th.n", term("holm", "p (Holm)")), el("th", "Significant"))));
  t.append(el("tbody", ...fits.map((f) => el("tr", el("td", f.window), el("td", `${f.start} to ${f.end}`), el("td.n", num("theil_sen", f.slope, fmt(f.slope, 3))), el("td.n", `${fmt(f.lo, 3)} to ${fmt(f.hi, 3)}`), el("td.n", num("holm", f.p_holm, pval(f.p_holm))), el("td", f.sig ? "yes" : "no")))));
  const card = el("div.card.flat",
    el("div.row-flex", el("span.swatch", { style: { width: "14px", height: "14px", borderRadius: "4px", background: it.colour, display: "inline-block" } }), el("h4", { style: { margin: 0 } }, label(s))),
    el("p.small.muted", `${s.source} · ${FREQ_NAMES[s.frequency] || s.frequency} · ${s.periods.length} periods, ${s.first} to ${s.last} · tested as `, term(s.transform, unitName(s)), s.scope ? ` · scope ${s.scope}` : ""),
    s.trend?.dir ? el("p", "Trend: significant in ", el("strong", `${s.trend.sig} of ${s.trend.windows}`), " windows; growth ", num("growth", s.trend.growth, `${signedPct(s.trend.growth)} a year`), ".") : el("p.small", "Not a trend by Moria's rule (2 of 3 windows, Holm-adjusted)."),
    fits.length ? el("div.table-wrap", t) : null,
    s.anomaly ? el("p.small.mt", "Latest value ", el("strong", fmt(s.anomaly.value, 4)), " against an expected ", fmt(s.anomaly.expected, 4), ": ", num("z", s.anomaly.z, `z = ${fmt(s.anomaly.z, 3)}`), ", ", num("holm", s.anomaly.p_holm, `p (Holm) ${pval(s.anomaly.p_holm)}`), s.anomaly.flagged ? ". An anomaly by Moria's rule." : ". Not an anomaly by Moria's rule.") : null,
    s.acceleration ? el("p.small", "Acceleration test: the slope went from ", fmt(s.acceleration.early.slope, 3), " to ", fmt(s.acceleration.recent.slope, 3), " (", num("holm", s.acceleration.p_holm, `p (Holm) ${pval(s.acceleration.p_holm)}`), ")", s.acceleration.flagged ? ": an acceleration." : ": not significant.") : null,
    s.surge ? el("p.small", `Surge window ${s.surge.window}: ${fmt(s.surge.count)} against ${fmt(s.surge.expected, 3)} expected (ratio ${fmt(s.surge.ratio, 3)})`, s.surge.flagged ? ": a low-base surge." : ".") : null,
    el("div.row-flex.mt", ...owners.slice(0, 4).map((c) => el("button.btn.btn-small", { type: "button", onclick: () => ctx.open(c.id) }, typeTag(c.type),
      c.subject_kind === "pair" ? "Open it against the world" : c.queue ? `Open queue place ${c.queue.rank}` : "Open the candidate"))));
  return card;
}

function testedCard(d) {
  const rows = d.scan.series_tested;
  return chartCard({
    title: "Series tested, by source and frequency",
    sub: `${n(d.scan.multiple_testing.series)} series were tested in this scan. 'Testable' series have at least two of their three trend windows covered with enough data.`,
    render: (box) => {
      const tk = tokens();
      const names = rows.map((r) => `${r.source} (${FREQ_NAMES[r.frequency] || r.frequency})`);
      box.style.height = `${rows.length * 30 + 70}px`;
      chart(box, {
        grid: { left: 210, right: 30, top: 30, bottom: 24 },
        legend: { top: 0, left: 0, textStyle: { color: tk.ink2 }, itemWidth: 12, itemHeight: 12 },
        xAxis: axis("log", { min: 1 }),
        yAxis: axis("category", { data: names, inverse: true }),
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => tipHtml(ps[0].name, ps.map((p) => [p.color, p.seriesName, n(p.value)])) },
        series: [
          { name: "Series", type: "bar", data: rows.map((r) => r.series), barMaxWidth: 10, itemStyle: { color: tk.neutral, borderRadius: [0, 3, 3, 0] } },
          { name: "Testable", type: "bar", data: rows.map((r) => r.testable || null), barMaxWidth: 10, itemStyle: { color: tk.mithril2, borderRadius: [0, 3, 3, 0] } },
          { name: "Trends", type: "bar", data: rows.map((r) => r.trends || null), barMaxWidth: 10, itemStyle: { color: css("--t-trend"), borderRadius: [0, 3, 3, 0] } },
          { name: "Anomalies", type: "bar", data: rows.map((r) => r.anomalies || null), barMaxWidth: 10, itemStyle: { color: css("--t-anomaly"), borderRadius: [0, 3, 3, 0] } },
        ],
      });
    },
    table: () => dataTable(rows, [{ label: "Source", value: (r) => r.source }, { label: "Frequency", value: (r) => FREQ_NAMES[r.frequency] || r.frequency }, { label: "Series", value: (r) => r.series, n: true }, { label: "Testable", value: (r) => r.testable, n: true },
      { label: "Trends", value: (r) => r.trends, n: true }, { label: "Accelerations", value: (r) => r.accelerations, n: true }, { label: "Anomalies", value: (r) => r.anomalies, n: true }, { label: "Level changes", value: (r) => r.level_changes, n: true }, { label: "Surges", value: (r) => r.surges, n: true }]),
  });
}

