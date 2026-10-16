// The candidate drawer: everything Moria knows about one candidate, from the headline down (progressive
// disclosure): at a glance; the detectors' numbers; the alternative explanations; the evidence; why it ranked where
// it did; what the decision model suggested; its history. Titles and links from sources are untrusted: text only.

import { arrow, flagChip, ringTag, statusBadge, typeTag } from "./bits.js";
import { axis, chart, tipHtml, tokens } from "./charts.js";
import { num, term, tip, TERMS } from "./glossary.js";
import { seriesOption } from "./seriesChart.js";
import { candidate, dossierOf, hasDetail, seriesOf, state } from "./state.js";
import { el, fmt, link, longDate, n, pct, periodName, pval, RING_NAMES, signedPct, title, TYPE_NAMES, typeColour, VIEW_NAMES, words } from "./util.js";

const drawer = () => document.getElementById("drawer");
const veil = () => document.getElementById("drawer-veil");
let lastFocus = null;

export function closeDrawer() {
  const d = drawer();
  if (!d.classList.contains("open")) return;
  d.classList.remove("open");
  d.setAttribute("aria-hidden", "true");
  veil().hidden = true;
  setTimeout(() => {
    for (const node of d.querySelectorAll("[_echarts_instance_]")) echarts.getInstanceByDom(node)?.dispose();
    d.replaceChildren();
  }, 400);
  lastFocus?.focus?.();
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && drawer().classList.contains("open") && document.getElementById("popover").hidden) closeDrawer();
});

export function openCandidate(id) {
  if (!hasDetail()) return;
  const c = candidate(id);
  if (!c) return;
  lastFocus = document.activeElement;
  const d = drawer();
  for (const node of d.querySelectorAll("[_echarts_instance_]")) echarts.getInstanceByDom(node)?.dispose();
  const dos = dossierOf(id);
  const place = c.queue ? `Queue place ${c.queue.rank} of ${state.data.queue?.size ?? 40}` : c.shortlist ? `Shortlist place ${c.shortlist.rank}` : "Not shortlisted";
  const tabs = [
    ["glance", "At a glance", () => glance(c, dos)],
    ["numbers", "The numbers", () => numbers(c, dos)],
    ["checks", "Could it be something else?", () => checks(c, dos)],
    ["evidence", "The evidence", () => evidence(c, dos)],
    ["rank", "Why it ranked here", () => ranking(c)],
    ["machine", "Machine suggestions", () => machine(c)],
    ["history", "History", () => history(c, dos)],
  ];
  const body = el("div.drawer-body");
  const tabBar = el("div.tabs", { role: "tablist" });
  const show = (key) => {
    for (const b of tabBar.children) b.setAttribute("aria-selected", String(b.dataset.key === key));
    for (const node of body.querySelectorAll("[_echarts_instance_]")) echarts.getInstanceByDom(node)?.dispose();
    body.replaceChildren(tabs.find((t) => t[0] === key)[2]());
    body.scrollTop = 0;
  };
  for (const [key, name] of tabs) tabBar.append(el("button", { type: "button", role: "tab", "data-key": key, onclick: () => show(key) }, name));
  const head = el("div.drawer-head",
    el("button.btn.btn-small.drawer-close", { type: "button", onclick: closeDrawer, "aria-label": "Close" }, "Close ✕"),
    el("div.eyebrow", `${place}${state.mode === "practice" ? " · practice data" : ""}`),
    el("h2", c.label),
    el("div.facts", typeTag(c.type, true), ringTag(c.ring), arrow(c.direction), ...(c.flags || []).map(flagChip),
      c.known_trend_match ? el("span.tag.gold", { "data-term": "known_trend", tabindex: 0 }, `Known trend ${c.known_trend}`) : null,
      c.numbers?.context_explains ? el("span.tag", { "data-term": "explained_by_context", tabindex: 0 }, "Explained by its context") : null),
    tabBar);
  d.replaceChildren(head, body);
  d.classList.add("open");
  d.setAttribute("aria-hidden", "false");
  veil().hidden = false;
  veil().onclick = closeDrawer;
  show("glance");
  tabBar.firstChild.focus({ preventScroll: true });
}

// ------------------------------------------------------------------------------------------------- at a glance

function summarySentence(c, dos) {
  if (dos?.summary) return dos.summary;
  const nums = c.numbers || {};
  const up = (c.direction ?? 1) >= 0 ? "rising" : "falling";
  if (nums.trend?.growth_per_year != null) return `${c.label}: a ${up} trend, about ${signedPct(nums.trend.growth_per_year)} a year.`;
  if (nums.anomaly) return `${c.label}: ${nums.anomaly.period} was ${signedPct((nums.anomaly.value - nums.anomaly.expected) / Math.abs(nums.anomaly.expected || 1), 0)} off its expected value.`;
  if (c.n_items) return `${c.label}: ${c.n_items} de-duplicated items from ${c.n_sources} sources in the window to ${c.window?.[1] ?? "the scan"}.`;
  return c.label;
}

function glance(c, dos) {
  const wrap = el("div");
  wrap.append(el("p.summary-line", summarySentence(c, dos)));
  const facts = el("dl.kv.mt",
    el("dt", "Where it comes from"), el("dd", (c.sources || []).join(", ") || "–"),
    el("dt", "Kind of subject"), el("dd", subjectKind(c)),
    el("dt", "Window"), el("dd", c.window?.filter(Boolean).join(" to ") || "–"),
    el("dt", term("ring", "Ring")), el("dd", RING_NAMES[c.ring], el("span.muted", ` (basis: ${c.ring_basis})`), tip("ring_basis")),
    el("dt", term("views", "Views")), el("dd", (c.views || []).map((v) => VIEW_NAMES[v]).join(", ")),
    el("dt", term("corroboration", "Independent lines")), el("dd", String(c.corroboration ?? 1), c.redundancy_size > 1 ? el("span.muted", ` · moves with ${c.redundancy_size - 1} other candidate(s)`) : null),
    el("dt", term("scope", "Scope")), el("dd", c.scope || "–"));
  wrap.append(el("div.grid.g-21.mt", el("div.card.flat", el("h3", "The evidence, drawn"), mainChart(c, dos)), el("div.card.flat", el("h3", "Key facts"), facts)));
  const kt = c.known_trend ? (state.data.config?.known_trends || []).find((k) => k.id === c.known_trend) : null;
  const terr = c.territory ? (state.data.config?.territories || []).find((t) => t.id === c.territory) : null;
  wrap.append(el("div.grid.g2.mt",
    el("div.card.flat",
      el("h3", "Nearest known trend", tip("known_trend")),
      kt ? [el("p", el("strong", `${kt.id}: ${kt.name}`), kt.status === "proposed" ? el("span.tag.gold", " proposed") : null), el("p.small.ink2", kt.statement)] : el("p.muted", "None recorded."),
      c.known_trend_sim != null ? el("p.small", "Similarity ", num("cosine", c.known_trend_sim, fmt(c.known_trend_sim, 2)), c.known_trend_match ? ": a match (novelty lowered a little; reinforcing a known trend still counts)." : ": not close enough to count as a match.") : null),
    el("div.card.flat",
      el("h3", "Nearest growth territory", tip("territory")),
      terr ? [el("p", el("strong", `${terr.id}: ${terr.name}`)), el("p.small.ink2", terr.aim)] : el("p.muted", "None recorded."),
      c.territory_sim != null ? el("p.small", "Similarity ", num("cosine", c.territory_sim, fmt(c.territory_sim, 2)), (c.territory_terms || []).length ? `; its words match ${c.territory_terms.join(", ")}` : "") : null)));
  if ((c.flags || []).length) {
    wrap.append(el("div.callout.warn.mt", el("div.c-ico", "⚑"), el("div",
      el("h4", `${c.flags.length === 1 ? "One flag" : `${c.flags.length} flags`}: read before you trust it`),
      el("p", "A flag says the candidate might come from how the data was collected. It lowers the rank but never hides the candidate. "),
      el("p", ...c.flags.map((f) => [term(f, title(f)), ": ", TERMS[f]?.short || "", " "])))));
  }
  return wrap;
}

const SCHEMES = { kp: "key phrases", ipc: "IPC classes", nice: "Nice classes", ipc_country: "applicant countries in IPC classes", nice_country: "applicant countries in Nice classes" };
const schemeOf = (c) => Object.values(c.numbers || {}).find((v) => v && typeof v === "object" && v.scheme)?.scheme;

function subjectKind(c) {
  const scheme = schemeOf(c);
  const pairing = scheme && scheme !== "kp" ? `A pairing of ${SCHEMES[scheme] || scheme} in IP applications` : "A new pairing of key phrases";
  return { series: "A statistical or count series", pair: "Australia against the world (a pair of series)", concept: "A concept found in documents", combination: pairing, micro: "A micro-cluster of novel documents" }[c.subject_kind] || c.subject_kind;
}

const SLOTS = ["--t-trend", "--t-acceleration", "--t-weak_signal", "--t-anomaly"];

function mainChart(c, dos) {
  const box = el("div.chart");
  const ser = seriesOf(c).filter((s) => ["subject", "reference"].includes(s.role));
  if (ser.length) {
    const tk = getComputedStyle(document.documentElement);
    const items = ser.map((s, k) => ({ s: s.data, colour: tk.getPropertyValue(SLOTS[k]).trim(), name: s.role === "reference" ? `${s.data.scope || "Reference"} (counterpart)` : shortLabel(s.data.label) }));
    const mode = items.length > 1 ? "indexed" : "natural";
    const controls = el("div.row-flex.mt.small");
    const state2 = { mode, fits: "best" };
    const recent = { M: 72, Q: 32, A: 24, D: 180 }[items[0].s.frequency] || 60;
    box.classList.add("tall");
    const draw = () => chart(box, seriesOption(items, { ...state2, anomaly: true, accel: c.type === "acceleration", changes: true, surge: true, zoom: true, recent }));
    const sel = el("select", { "aria-label": "Display" },
      ...[["natural", "As published"], ["indexed", "Indexed to 100"], ["tested", "As Moria tested it"]].map(([v, t]) => el("option", { value: v, selected: v === mode }, t)));
    sel.onchange = () => { state2.mode = sel.value; draw(); };
    const fits = el("select", { "aria-label": "Trend lines" },
      ...[["best", "Trend line: the longest significant window"], ["all", "Trend lines: all three windows"], ["none", "No trend lines"]].map(([v, t]) => el("option", { value: v }, t)));
    fits.onchange = () => { state2.fits = fits.value; draw(); };
    controls.append(sel, fits, tip("ci"), el("span.muted", "Shaded: the slope's 95% range; grey: the 99% expected band; ring: the anomaly. Drag the slider for the whole history."));
    requestAnimationFrame(draw);
    return el("div", box, controls);
  }
  if (dos?.chart?.values) {
    const ch = dos.chart;
    requestAnimationFrame(() => {
      const tk = tokens();
      const last3 = ch.periods.length - 3;
      chart(box, {
        grid: { left: 44, right: 16, top: 26, bottom: 32 },
        xAxis: axis("category", { data: ch.periods.map((p) => periodName(p)) }),
        yAxis: axis("value", { name: "items a month", minInterval: 1 }),
        tooltip: { trigger: "axis", formatter: (ps) => tipHtml(ps[0].name, [[typeColour(c.type), "De-duplicated items", ps[0].value]], ps[0].dataIndex >= last3 ? "In the scan's window" : "Baseline") },
        series: [{ type: "bar", data: ch.values.map((v, i) => ({ value: v, itemStyle: { color: i >= last3 ? typeColour(c.type) : tk.neutral, borderRadius: [4, 4, 0, 0] } })), barMaxWidth: 22 }],
      });
    });
    return el("div", box, el("p.small.muted", "Grey: the baseline months. Coloured: the window. A weak signal is a sudden rise from a low base."));
  }
  const items = state.data.items?.[c.id] || dos?.evidence?.items || [];
  if (items.length) {
    requestAnimationFrame(() => {
      const srcs = [...new Set(items.map((i) => i.source))];
      chart(box, {
        grid: { left: 150, right: 20, top: 16, bottom: 32 },
        xAxis: axis("time"),
        yAxis: axis("category", { data: srcs }),
        tooltip: { trigger: "item", formatter: (p) => tipHtml(longDate(p.data.at), [[typeColour(c.type), p.data.src, p.data.title]]) },
        series: [{ type: "scatter", symbolSize: 14, itemStyle: { color: typeColour(c.type), borderColor: tokens().surface, borderWidth: 2 },
          data: items.filter((i) => i.observable_at).map((i) => ({ value: [Date.parse(i.observable_at), i.source], at: i.observable_at, src: i.source, title: (i.title || "(untitled)").slice(0, 120) })) }],
      });
    });
    return el("div", box, el("p.small.muted", "Each dot is one item in the window (copies counted once), by source and date."));
  }
  const pairNums = c.numbers?.jurisdiction_shift || c.numbers?.new_combination || c.numbers?.fading_combination;
  if (pairNums && pairNums.window != null) {
    requestAnimationFrame(() => {
      const tk = tokens();
      const bars = [["Baseline", pairNums.baseline, tk.neutral], ...(pairNums.expected_window != null ? [["Expected in the window", pairNums.expected_window, tk.axis]] : []), ["Window", pairNums.window, typeColour(c.type)]];
      chart(box, {
        grid: { left: 50, right: 20, top: 20, bottom: 30 },
        xAxis: axis("category", { data: bars.map((b) => b[0]) }),
        yAxis: axis("value", { minInterval: 1 }),
        tooltip: { trigger: "item", formatter: (p) => tipHtml(p.name, [[p.color, "count", fmt(p.value, 3)]]) },
        series: [{ type: "bar", barMaxWidth: 56, data: bars.map((b) => ({ value: b[1], itemStyle: { color: b[2], borderRadius: [6, 6, 0, 0] } })), label: { show: true, position: "top", color: tokens().ink2, formatter: (p) => fmt(p.value, 3) } }],
      });
    });
    const lift = pairNums.lift_ratio != null ? ` Lift ratio ${fmt(pairNums.lift_ratio, 3)}: the pairing is that many times more common than before, given how common each half is.` : "";
    return el("div", box, el("p.small.muted", `${pairNums.scheme ? `Pairs of ${SCHEMES[pairNums.scheme] || words(pairNums.scheme)}. ` : ""}How often the two appear together in the window against the baseline.${lift}`));
  }
  if (c.numbers) return el("p.muted", "No chart for this kind of candidate: see its numbers.");
  return el("p.muted", "No chart.");
}

function shortLabel(s) {
  const t = String(s || "");
  return t.length > 60 ? `${t.slice(0, 58)}…` : t;
}

// ------------------------------------------------------------------------------------------------- the numbers

const KEY_TERMS = {
  p_holm: "holm", q_bh: "bh", p: "p_value", z: "z", slope: "theil_sen", growth_per_year: "growth", lo: "ci", hi: "ci",
  ratio: "low_base_surge", expected: "anomaly_band", lift_ratio: "new_combination", change_point: "change_point", share: "explained_by_context", r2: "r2",
};
const DETECTOR_NAMES = {
  trend: "Trend", acceleration: "Acceleration", anomaly: "Anomaly", low_base_surge: "Low-base surge", divergence: "Australia against its counterpart",
  new_term: "New term", cross_family: "Cross-family", cross_ring: "Cross-ring", new_combination: "New combination", novel_items: "Novel items",
  jurisdiction_shift: "Jurisdiction shift", fading_combination: "Fading pair", context_explains: "Explained by its context",
};

function numbers(c) {
  const wrap = el("div");
  const nums = c.numbers || {};
  wrap.append(el("p.lede", "What each detector measured. Hover any dotted number for what it means."));
  for (const [det, v] of Object.entries(nums)) {
    const card = el("div.card.flat.mb", el("div.card-head", el("h3", DETECTOR_NAMES[det] || title(det), TERMS[det] ? tip(det) : null)));
    if (v && typeof v === "object" && (v.w1 || v.w2 || v.w3)) {
      const r = reading(det, v);
      if (r) card.append(el("p.summary-line", r));
      card.append(forest(v), windowsTable(v));
      if (v.growth_per_year != null) card.append(el("p", "Growth: ", num("growth", v.growth_per_year, `${signedPct(v.growth_per_year)} a year`), v.reference ? ` against ${v.reference}` : ""));
    } else if (v && typeof v === "object") {
      const r = reading(det, v);
      if (r) card.append(el("p.summary-line", r));
      card.append(kvTable(v));
    } else {
      card.append(el("p", String(v)));
    }
    wrap.append(card);
  }
  const ser = seriesOf(c).find((s) => s.role === "subject");
  if (ser?.data?.fits?.length && !nums.trend && !nums.divergence) {
    const f = Object.fromEntries(ser.data.fits.map((x) => [x.window, x]));
    wrap.append(el("div.card.flat.mb", el("h3", "The series' trend windows (for context)", tip("windows")), forest(f), windowsTable(f)));
  }
  if (!Object.keys(nums).length) wrap.append(el("p.muted", "No numbers recorded."));
  return wrap;
}

const KEY_NAMES = {
  bootstrap: "Tested by the bootstrap", change: "Size of the change", change_point: "Change point at", change_point_change: "Change in growth at the change point (a year)",
  early: "Slope, earlier half", recent: "Slope, recent half", lo: "95% range, low end", hi: "95% range, high end", p_holm: "p (Holm)", q_bh: "q (Benjamini-Hochberg)",
  periods: "Periods in the window", band: "Outside the expected band", expected: "Expected value", value: "Actual value", level_change: "Change in level",
  level_change_point: "Level shift at", period: "Period", z: "z-score", ratio: "Rate ratio", count: "Count in the window", window: "In the window",
  baseline: "In the baseline", new: "New", rising: "Rising", fading: "Fading", lift_ratio: "Lift ratio", scheme: "Classification", a_baseline: "First half, in the baseline",
  b_baseline: "Second half, in the baseline", expected_window: "Expected in the window", window_families: "Source families now", baseline_families: "Source families before",
  growth_per_year: "Growth a year", reference: "Compared with", transform: "Tested as", share: "Share of the move its context predicts", observed: "Observed", r2: "R²",
  terms: "Terms", phrase: "Phrase", df: "Documents", window_items: "Items in the window", baseline_items: "Items in the baseline", sources: "Sources",
};
const PROB = /^(p|q|p_holm|q_bh|p_raw)$/;

/** One plain sentence per detector, from its numbers. */
function reading(det, v) {
  const sp = (x) => signedPct(x, 0);
  try {
    if (det === "acceleration") return `The slope went from ${fmt(v.early, 3)} (earlier half) to ${fmt(v.recent, 3)} (recent half)${v.change_point ? `, with a change to a steeper slope at ${v.change_point}` : ""}. ${v.p_holm != null && v.p_holm < 0.05 ? "The bootstrap test passes." : "The bootstrap test alone doesn't pass; the change point on a significant trend is what makes it an acceleration."}`;
    if (det === "anomaly") return `${v.period}: ${fmt(v.value, 4)} against ${fmt(v.expected, 4)} expected (${sp((v.value - v.expected) / Math.abs(v.expected || 1))}), ${fmt(Math.abs(v.z), 3)} usual wobbles away.`;
    if (det === "trend") return `A ${v.growth_per_year >= 0 ? "rising" : "falling"} trend of about ${sp(v.growth_per_year)} a year, significant in enough windows after Holm's adjustment.`;
    if (det === "low_base_surge") return `${fmt(v.count)} in ${v.window} against ${fmt(v.expected, 3)} expected from a low base: ${fmt(v.ratio, 3)} times the usual rate.`;
    if (det === "divergence") return `Australia's share is ${v.growth_per_year >= 0 ? "pulling ahead of" : "falling behind"} the ${v.reference}'s by about ${sp(Math.abs(v.growth_per_year))} a year.`;
    if (["new_combination", "jurisdiction_shift", "fading_combination"].includes(det)) return `${v.new ? "New" : v.rising ? "Rising" : "Fading"}: ${fmt(v.window)} in the window against ${fmt(v.baseline)} in the baseline${v.lift_ratio != null ? `, a lift of ${fmt(v.lift_ratio, 3)}` : ""}.`;
    if (det === "cross_family") return `Seen before in ${(v.baseline_families || []).join(", ") || "no family"}; now in ${(v.window_families || []).join(", ")}.`;
    if (det === "context_explains") return `Its peers and counterpart predict ${pct(v.share)} of the move: it may be general, not specific to this series.`;
  } catch { /* fall through to the table alone */ }
  return null;
}

function kvTable(v) {
  const dl = el("dl.kv");
  for (const [k, x] of Object.entries(v)) {
    if (x == null || (typeof x === "object" && !Array.isArray(x))) continue;
    const key = KEY_TERMS[k];
    let shown;
    if (Array.isArray(x)) shown = x.join(", ") || "none";
    else if (typeof x === "boolean") shown = x ? "yes" : "no";
    else if (typeof x === "number" && PROB.test(k)) shown = pval(x);
    else shown = typeof x === "number" ? fmt(x, 4) : String(x);
    dl.append(el("dt", KEY_NAMES[k] || words(k)), el("dd", key && typeof x === "number" ? num(key, x, shown) : shown));
  }
  return dl;
}

function windowsTable(v) {
  const t = el("table.data.mt");
  t.append(el("thead", el("tr", el("th", term("windows", "Window")), el("th.n", term("theil_sen", "Slope")), el("th.n", term("ci", "95% range")),
    el("th.n", term("holm", "p (Holm)")), el("th.n", term("bh", "q (BH)")), el("th", "Significant?"))));
  const tb = el("tbody");
  for (const w of ["w1", "w2", "w3"]) {
    const x = v[w];
    if (!x) continue;
    tb.append(el("tr", el("td", `${w}${x.periods ? ` (${x.periods} periods)` : ""}`), el("td.n", num("theil_sen", x.slope, fmt(x.slope, 3))),
      el("td.n", `${fmt(x.lo, 3)} to ${fmt(x.hi, 3)}`), el("td.n", x.p_holm != null ? num("holm", x.p_holm, pval(x.p_holm)) : "–"),
      el("td.n", x.q_bh != null ? num("bh", x.q_bh, pval(x.q_bh)) : "–"), el("td", statusBadge(x.sig ? "pass" : "na").cloneNode(true))));
  }
  t.append(tb);
  for (const s of t.querySelectorAll(".status.pass")) s.lastChild.textContent = "Yes";
  for (const s of t.querySelectorAll(".status.na")) s.lastChild.textContent = "No";
  return el("div.table-wrap", t);
}

/** A forest plot: each window's slope with its 95% range, against zero. */
function forest(v) {
  const box = el("div.chart.tiny");
  const rows = ["w1", "w2", "w3"].filter((w) => v[w]);
  requestAnimationFrame(() => {
    const tk = tokens();
    chart(box, {
      grid: { left: 54, right: 24, top: 10, bottom: 28 },
      xAxis: axis("value", { name: "slope", scale: true }),
      yAxis: axis("category", { data: rows, inverse: true }),
      tooltip: { trigger: "item", formatter: (p) => { const x = v[rows[p.dataIndex]]; return tipHtml(rows[p.dataIndex], [[null, "slope", fmt(x.slope, 3)], [null, "95% range", `${fmt(x.lo, 3)} to ${fmt(x.hi, 3)}`], [null, "p (Holm)", pval(x.p_holm)]]); } },
      series: [
        { type: "custom", renderItem: (params, api) => {
          const lo = api.coord([api.value(1), api.value(0)]), hi = api.coord([api.value(2), api.value(0)]);
          return { type: "line", shape: { x1: lo[0], y1: lo[1], x2: hi[0], y2: hi[1] }, style: { stroke: api.value(3) ? tk.mithril : tk.neutral, lineWidth: 4, lineCap: "round" } };
        }, data: rows.map((w, i) => [i, v[w].lo, v[w].hi, v[w].sig ? 1 : 0]), encode: { x: [1, 2], y: 0 }, z: 2 },
        { type: "scatter", data: rows.map((w, i) => [v[w].slope, i]), symbolSize: 12, itemStyle: { color: tk.surface, borderColor: tk.mithril, borderWidth: 3 }, z: 3,
          markLine: { silent: true, symbol: "none", data: [{ xAxis: 0 }], lineStyle: { color: tk.critical, type: "solid", width: 1 }, label: { formatter: "no change", color: tk.muted } } },
      ],
    });
  });
  return el("div", box, el("p.small.muted", "Each bar is the range of slopes the data allows (95%). A bar clear of the red zero line has a clear direction; Holm then decides if it beats the luck of many tests."));
}

// --------------------------------------------------------------------------------------------- alternative explanations

function checks(c, dos) {
  const wrap = el("div");
  wrap.append(el("p.lede", "Before believing a candidate, Moria asks what else could explain it. A flag doesn't mean it's wrong: it means look closer."));
  const list = dos?.checklist || Object.entries(c.checks || {}).map(([check, outcome]) => ({ check, outcome, detail: "" }));
  const ul = el("ul.checklist");
  for (const ck of list) {
    ul.append(el("li", el("strong", TERMS[ck.check] ? term(ck.check, title(ck.check)) : title(ck.check)), statusBadge(ck.outcome), el("span.detail", readableDetail(ck))));
  }
  wrap.append(ul);
  if (dos?.redundancy?.others?.length) {
    wrap.append(el("div.card.flat.mt", el("h3", "Moves together with", tip("redundancy")),
      el("ul.items", ...dos.redundancy.others.map((o) => el("li", el("button.btn.btn-small.btn-ghost", { type: "button", onclick: () => openCandidate(o.candidate_id) }, o.label || o.candidate_id), " ", TYPE_NAMES[o.type] || "")))));
  }
  if (!dos) wrap.append(el("p.small.muted.mt", "This candidate wasn't shortlisted, so it has no dossier: only the six artefact checks ran on it. Shortlisted candidates get more checks (seasonality, administrative causes, concentrated works, reclassification, known trends)."));
  return wrap;
}

function readableDetail(ck) {
  const d = ck.detail;
  if (!d) return ck.outcome === "n/a" ? "Doesn't apply to this kind of candidate." : "";
  if (ck.check === "coverage" && /^-?\d/.test(d)) return `The source's volume changed ${signedPct(Number(d), 0)} over the window.`;
  try {
    const j = JSON.parse(d);
    if (j && typeof j === "object") return Object.entries(j).map(([k, v]) => `${k}: ${v == null ? "no baseline" : typeof v === "number" ? signedPct(v, 0) : v}`).join("; ");
  } catch { /* plain text */ }
  return String(d);
}

// ------------------------------------------------------------------------------------------------- the evidence

function itemList(items, { score = false, similarity = false } = {}) {
  return el("ul.items", ...items.map((i) => el("li",
    link(i.title || "(untitled)", i.url),
    el("div.meta", el("span", i.source), i.family ? el("span", i.family) : null, el("span", longDate(i.observable_at || i.event_at)),
      i.copies > 1 ? el("span", `${i.copies} copies`) : null, score && i.score != null ? el("span", `match ${fmt(i.score, 3)}`) : null,
      similarity && i.similarity != null ? el("span", `similarity ${fmt(i.similarity, 2)}`) : null))));
}

function evidence(c, dos) {
  const wrap = el("div");
  const items = dos?.evidence?.items || state.data.items?.[c.id] || [];
  if (items.length) {
    wrap.append(el("div.card.flat.mb", el("h3", `The documents behind it (${dos?.evidence?.groups ?? items.length} after de-duplication)`, tip("dedup")),
      el("p.small.muted", "Titles and links as the sources published them. Moria stores titles and links for news, never the article text."), itemList(items)));
  }
  const apps = dos?.evidence?.applications;
  if (apps?.status === "ok") {
    wrap.append(el("div.card.flat.mb", el("h3", "IP applications behind it", tip("ip_rapid")),
      el("p", `${n(apps.applications)} applications from ${n(apps.applicants)} founding applicants in ${apps.period}; ${n(apps.filed_before_period)} filed before the period.`),
      el("div.table-wrap", el("table.data", el("thead", el("tr", el("th", "Application"), el("th", "Right"), el("th", "Title"), el("th", "Applicants"), el("th", "Filed"))),
        el("tbody", ...(apps.sample || []).map((a) => el("tr", el("td.mono", a.application_number), el("td", a.right), el("td", a.title || ""), el("td", (a.applicants || []).join(", ")), el("td", a.filed || ""))))))));
  }
  const ser = seriesOf(c);
  if (ser.length) {
    wrap.append(el("div.card.flat.mb", el("h3", "The series behind it"),
      el("ul.items", ...ser.map((s) => el("li", el("strong", s.data.label || s.id), el("div.meta", el("span", s.role), el("span", s.data.source), el("span", `${s.data.first} to ${s.data.last}`), el("span", `${s.data.periods.length} periods`), el("span", s.data.scope || ""))))),
      el("button.btn.btn-small.mt", { type: "button", onclick: () => { state.series = ser.map((s, k) => ({ id: s.id, slot: k })); closeDrawer(); location.hash = "#/time"; } }, "Open in Change over time")));
  }
  const samp = dos?.samples?.openalex;
  if (samp?.status === "ok") {
    wrap.append(el("div.card.flat.mb", el("h3", "Research works behind the count", tip("concentrated_works")),
      el("p", `${n(samp.works)} works in ${n(samp.venues)} venues; the largest venue holds ${pct(samp.top_venue_share)}.`, samp.concentrated ? el("span.flag-chip", " concentrated") : null)));
  }
  if (dos?.related?.length) wrap.append(el("div.card.flat.mb", el("h3", "Primary sources that mention it"), el("p.small.muted", "Legal and policy documents found by a word search: to read, not established links."), itemList(dos.related, { score: true })));
  if (dos?.counter_evidence?.length) wrap.append(el("div.card.flat.mb", el("h3", "Possible counter-evidence"), el("p.small.muted", "Items that use the candidate's words alongside words of the opposite direction. Hits to read, not established contradiction."), itemList(dos.counter_evidence, { score: true })));
  if (Array.isArray(dos?.analogues) && dos.analogues.length) wrap.append(el("div.card.flat.mb", el("h3", "Earlier look-alikes"), el("p.small.muted", "The earlier items nearest in meaning to this candidate's."), itemList(dos.analogues, { similarity: true })));
  if (!wrap.childNodes.length) wrap.append(el("p.muted", "No evidence items recorded for this candidate."));
  return wrap;
}

// ------------------------------------------------------------------------------------------------- the ranking

function ranking(c) {
  const wrap = el("div");
  const cfg = state.data.config?.rank;
  wrap.append(el("p.lede", "How this candidate's score was built: components (each a percentile) combined by a weighted geometric mean, times factors."));
  const comps = [["strength", c.strength_pct], ["breadth", c.breadth], ["lead", c.lead], ["novelty", c.novelty]];
  const box = el("div.chart.short");
  requestAnimationFrame(() => {
    const tk = tokens();
    chart(box, {
      grid: { left: 90, right: 40, top: 10, bottom: 28 },
      xAxis: axis("value", { min: 0, max: 1 }),
      yAxis: axis("category", { data: comps.map(([k]) => title(k)), inverse: true }),
      tooltip: { trigger: "item", formatter: (p) => tipHtml(p.name, [[tk.mithril, "value", fmt(p.value, 3)]], TERMS[comps[p.dataIndex][0]]?.short) },
      series: [{ type: "bar", data: comps.map(([, v]) => v), barMaxWidth: 18, itemStyle: { color: tk.mithril, borderRadius: [0, 4, 4, 0] }, label: { show: true, position: "right", color: tk.ink2, formatter: (p) => fmt(p.value, 2) } }],
    });
  });
  wrap.append(el("div.grid.g2",
    el("div.card.flat", el("h3", "Components", tip("percentile")), box),
    el("div.card.flat", el("h3", "Factors", tip("factors")),
      el("dl.kv", el("dt", term("scope", "Scope")), el("dd", fmt(c.factors.scope, 3)),
        el("dt", "Type"), el("dd", fmt(c.factors.type, 3), c.type === "anomaly" ? el("span.muted", " (anomalies rank at half weight)") : null),
        el("dt", term("flag_penalty", "Flags")), el("dd", fmt(c.factors.flags, 3), c.flags?.length ? el("span.muted", ` (${c.flags.join(", ")})`) : null),
        el("dt", term("explained_by_context", "Context")), el("dd", fmt(c.factors.context, 3))))));
  for (const view of ["early_warning", "strategic"]) {
    if (c.scores[view] == null) continue;
    const order = cfg?.weights_order?.[view] || [];
    const parts = order.filter((k) => ({ strength: 1, novelty: 1, lead: 1, breadth: 1 })[k]);
    const val = { strength: c.strength_pct, novelty: c.novelty, lead: c.lead, breadth: c.breadth };
    const eq = el("div.equation.mt");
    eq.append(el("span", `${VIEW_NAMES[view]}:`), el("span.op", "("));
    parts.forEach((k, i) => {
      if (i) eq.append(el("span.op", "×"));
      eq.append(el("span.term-box", `${title(k)} ${fmt(Math.max(val[k], cfg?.floor ?? 0.05), 3)}`));
    });
    eq.append(el("span.op", `)^(1/${parts.length})`), el("span.op", "×"), el("span.term-box", `factors ${fmt(c.factors.scope * c.factors.type * c.factors.flags * c.factors.context, 3)}`), el("span.op", "="),
      el("span.term-box.result", num("score", c.scores[view], fmt(c.scores[view], 3))));
    wrap.append(el("div.card.flat.mt", el("h3", `${VIEW_NAMES[view]} score`, tip("geomean")), eq,
      el("p.small.muted.mt", "Equal weights shown; the forge lets you change them and watch the queue move.")));
  }
  wrap.append(el("p.mt", c.queue ? `Picked for the queue at place ${c.queue.rank}, by the ${VIEW_NAMES[c.queue.view]} view (pass ${c.queue.pass}).` : c.shortlist ? `Shortlisted at place ${c.shortlist.rank}, but not picked for the queue of 40.` : "Not shortlisted: its scores fell below the 100 picked under the ring quotas.", " ", tip("pass")));
  return wrap;
}

// ---------------------------------------------------------------------------------------- the machine's suggestions

function machine(c) {
  const wrap = el("div");
  const s = state.data.suggestions?.[c.id];
  wrap.append(el("div.callout.warn", el("div.c-ico", "⚠"), el("div",
    el("h4", "Treat these as noise for now"),
    el("p", "The free decision model failed its check (it scored relevant and irrelevant test sentences almost the same), so its suggestions are recorded but not used in the ranking. They are shown so a reviewer can see them, attributed to the model."))));
  if (!s?.pathways) {
    wrap.append(el("p.muted.mt", "No suggestions: the model is asked only about the shortlist's dossiers."));
    return wrap;
  }
  const statements = state.data.config?.pathways || {};
  const ids = ["P1", "P2", "P3", "P4", "P5", "P6"];
  const box = el("div.chart.short");
  requestAnimationFrame(() => {
    const tk = tokens();
    chart(box, {
      grid: { left: 40, right: 40, top: 10, bottom: 28 },
      xAxis: axis("value", { min: 0, max: 1 }),
      yAxis: axis("category", { data: ids, inverse: true }),
      tooltip: { trigger: "item", formatter: (p) => tipHtml(`${p.name}: ${fmt(p.value, 3)}`, [], statements[p.name]) },
      series: [{ type: "bar", data: ids.map((id) => s.pathways[id]), barMaxWidth: 16, itemStyle: { color: tk.neutral, borderRadius: [0, 4, 4, 0] },
        markLine: { silent: true, symbol: "none", data: [{ xAxis: 0.5 }], lineStyle: { color: tk.muted }, label: { formatter: "coin toss", color: tk.muted } },
        label: { show: true, position: "right", color: tk.ink2, formatter: (p) => fmt(p.value, 2) } }],
    });
  });
  wrap.append(el("div.card.flat.mt", el("h3", "How likely each pathway applies, as the model put it", tip("pathways")), box,
    el("p.small.muted", `Author: ${s.author}`)));
  const dl = el("dl.kv.mt");
  for (const [k, label, key] of [["order_top", "Order", "order"], ["origin_top", "Origin", null], ["horizon_top", "Horizon", null], ["stance_top", "Stance", null], ["impact_top", "Impact", null]]) {
    dl.append(el("dt", key ? term(key, label) : label), el("dd", s[k] ?? "–"));
  }
  wrap.append(el("div.card.flat.mt", el("h3", "Its other answers"), dl));
  return wrap;
}

// --------------------------------------------------------------------------------------------------- history

function history(c, dos) {
  const wrap = el("div");
  const h = dos?.history || [];
  const reg = (state.data.register || []).find((r) => r.signal_id === c.id);
  wrap.append(el("div.card.flat.mb", el("h3", "In the register", tip("register")),
    reg ? el("p", "Status: ", el("strong", reg.status), reg.reviews ? ` · reviewed ${reg.reviews} time(s)` : " · not reviewed yet") : el("p.muted", "Not in the register (only queued candidates are)."),
    reg?.review?.notes ? el("p.small", "Reviewer's note: ", reg.review.notes) : null));
  if (h.length) {
    wrap.append(el("div.card.flat", el("h3", "In earlier scans"),
      el("div.table-wrap", el("table.data", el("thead", el("tr", el("th", "Scan"), el("th", "Present"), el("th", "Type"), el("th.n", "Strength"), el("th", "Detectors"))),
        el("tbody", ...h.map((x) => el("tr", el("td", longDate(x.as_of)), el("td", x.present ? "yes" : "no"), el("td", x.type ? TYPE_NAMES[x.type] : "–"), el("td.n", fmt(x.strength, 3)), el("td", (x.detectors || []).join(", ")))))))));
  } else {
    wrap.append(el("p.muted", "No earlier scans recorded for this candidate (or it has no dossier)."));
  }
  if (dos?.limits?.length) wrap.append(el("div.card.flat.mt", el("h3", "Limits of this dossier"), el("ul", ...dos.limits.map((l) => el("li", l)), ...(dos.notes || []).map((l) => el("li", l)))));
  if (dos?.runs) wrap.append(el("details.group.mt", el("summary", "The runs behind it (audit trail)"), el("dl.kv", ...Object.entries(dos.runs).flatMap(([k, v]) => [el("dt", words(k)), el("dd.mono", v || "–")]))));
  return wrap;
}

