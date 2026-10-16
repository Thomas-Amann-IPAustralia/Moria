// Level 3, the deep delvings: every candidate the detectors raised. Public: where they came from and where they
// went, their flags, their detectors and their scores. With the Doors open: a map of every candidate (choose the
// axes) and a table to search, filter and sort; click any one for its drawer.

import { flagChip, needsPrivate, ringTag, typeTag } from "../bits.js";
import { axis, chart, chartCard, dataTable, tipHtml, tokens } from "../charts.js";
import { term, tip, TERMS } from "../glossary.js";
import { loadPractice, pickFile } from "../main.js";
import { hasDetail, state } from "../state.js";
import { CHECKS, debounce, el, fmt, n, pct, RING_SHORT, RINGS, title, TYPE_NAMES, TYPES, typeColour, VIEW_NAMES, words } from "../util.js";

const SYMBOLS = { trend: "circle", acceleration: "triangle", weak_signal: "diamond", anomaly: "rect" };

export function render(root, ctx) {
  const d = state.data;
  root.append(el("div.view-head", el("div",
    el("div.eyebrow", "The deep delvings"),
    el("h1", "All candidates", tip("candidate")),
    el("p.lede", `Every candidate the detectors raised in the scan: ${n(d.funnel.candidates)} of them, from ${n(d.funnel.series)} series and the last ${d.documents.window_days} days of documents. Most will never reach the queue; this is where to see why.`))));
  if (hasDetail()) root.append(explorer(ctx));
  root.append(el("div.section", el("h2", "Where they came from, and where they went")), flow(d));
  root.append(el("div.grid.g-21.mt", flags(d), detectors(d)));
  root.append(el("div.section", el("h2", "How they scored", tip("score"))), scoresCard(d));
  if (!hasDetail()) root.append(needsPrivate("To search every candidate by name, map them and open their evidence, open the Doors with your private file.", { pickFile, loadPractice }));
}

// ----------------------------------------------------------------------------------------------- public charts

function flow(d) {
  const rows = d.ranking.flow;
  const stages = ["queue", "shortlist", "not shortlisted"];
  const stageName = { queue: "Queue (40)", shortlist: "Shortlist only", "not shortlisted": "Not shortlisted" };
  return chartCard({
    title: "From source to type to outcome",
    sub: "Each band's width is a number of candidates. Follow a band to see what became of a source's finds.",
    height: "tall",
    render: (box) => {
      const tk = tokens();
      const nodes = new Map();
      const links = new Map();
      const add = (name, colour) => nodes.has(name) || nodes.set(name, { name, itemStyle: { color: colour, borderColor: tk.surface } });
      for (const r of rows) {
        add(r.origin, tk.neutral);
        add(TYPE_NAMES[r.type], typeColour(r.type));
        add(stageName[r.stage], r.stage === "queue" ? tk.gold : r.stage === "shortlist" ? tk.mithril2 : tk.axis);
        const k1 = `${r.origin}|${TYPE_NAMES[r.type]}`, k2 = `${TYPE_NAMES[r.type]}|${stageName[r.stage]}`;
        links.set(k1, (links.get(k1) || 0) + r.n);
        links.set(k2, (links.get(k2) || 0) + r.n);
      }
      chart(box, {
        tooltip: { trigger: "item", formatter: (p) => (p.dataType === "edge" ? tipHtml(`${p.data.source} → ${p.data.target}`, [[null, "candidates", n(p.data.value)]]) : tipHtml(p.name, [[null, "candidates", n(p.value)]])) },
        series: [{
          type: "sankey", left: 10, right: 130, top: 10, bottom: 10, nodeGap: 10, nodeWidth: 14, draggable: true, layoutIterations: 64,
          emphasis: { focus: "adjacency" }, lineStyle: { color: "gradient", opacity: 0.32, curveness: 0.5 },
          label: { color: tk.ink, fontFamily: "Nunito", fontWeight: 700, fontSize: 12 },
          data: [...nodes.values()], links: [...links].map(([k, v]) => { const [source, target] = k.split("|"); return { source, target, value: v }; }),
        }],
      });
    },
    table: () => dataTable(rows, [{ label: "From", value: (r) => r.origin }, { label: "Type", value: (r) => TYPE_NAMES[r.type] }, { label: "Outcome", value: (r) => stageName[r.stage] }, { label: "Candidates", value: (r) => r.n, n: true }]),
  });
}

function flags(d) {
  const t = d.scan.types;
  const used = CHECKS.filter((k) => TYPES.some((ty) => t[ty]?.flags?.[k]));
  const max = Math.max(1, ...TYPES.flatMap((ty) => used.map((k) => t[ty]?.flags?.[k] ?? 0)));
  const cell = (v, total, colour) => {
    const td = el("td.cell", v ? n(v) : "·");
    if (v) td.style.background = `color-mix(in srgb, ${colour} ${Math.round(12 + 70 * (v / total))}%, var(--surface))`;
    td.title = total ? `${pct(v / total)} of this type` : "";
    return td;
  };
  const table = el("table.data.heat",
    el("thead", el("tr", el("th", "Type"), el("th.n", "Candidates"), el("th", term("flags", "No flag")), ...used.map((k) => el("th", term(k, title(k)))))),
    el("tbody", ...TYPES.map((ty) => el("tr",
      el("td", typeTag(ty)), el("td.n", n(t[ty]?.candidates ?? 0)),
      cell(t[ty]?.clean ?? 0, t[ty]?.candidates || 1, "var(--s-good)"),
      ...used.map((k) => cell(t[ty]?.flags?.[k] ?? 0, max, "var(--s-serious)"))))));
  return el("div.card",
    el("div.card-head", el("div", el("h3", "Flags by type", tip("flags")), el("p.card-sub", "How many candidates of each type each artefact check flagged. A candidate can carry several flags, so a row can add up to more than its total. Darker: more."))),
    el("div.table-wrap", table),
    el("p.small.muted.mt", "Weak signals are flagged far more often than series: most document sources began daily collection in October 2026, so they have no baseline yet (source break) and their volume swings (coverage)."));
}

function detectors(d) {
  const rows = d.scan.detectors;
  return chartCard({
    title: "Which detectors fired",
    sub: "A candidate counts under every detector that fired on it. Darker: with no artefact flag.",
    render: (box) => {
      const tk = tokens();
      box.style.height = `${Math.max(280, rows.length * 26 + 50)}px`;
      chart(box, {
        grid: { left: 150, right: 40, top: 30, bottom: 24 },
        legend: { top: 0, left: 0, textStyle: { color: tk.ink2 }, itemWidth: 12, itemHeight: 12 },
        xAxis: axis("value"),
        yAxis: axis("category", { data: rows.map((r) => words(r.detector)), inverse: true, axisLabel: { color: tk.muted } }),
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => tipHtml(ps[0].name, [[tk.mithril, "with no flag", n(rows[ps[0].dataIndex].clean)], [tk.mithril2, "flagged", n(rows[ps[0].dataIndex].candidates - rows[ps[0].dataIndex].clean)]], TERMS[rows[ps[0].dataIndex].detector]?.short) },
        series: [
          { name: "With no flag", type: "bar", stack: "d", barMaxWidth: 16, data: rows.map((r) => r.clean), itemStyle: { color: tk.mithril, borderColor: tk.surface, borderWidth: 2, borderRadius: 4 } },
          { name: "Flagged", type: "bar", stack: "d", barMaxWidth: 16, data: rows.map((r) => r.candidates - r.clean), itemStyle: { color: tk.mithril2, opacity: 0.55, borderColor: tk.surface, borderWidth: 2, borderRadius: 4 } },
        ],
      });
    },
    table: () => dataTable(rows, [{ label: "Detector", value: (r) => words(r.detector) }, { label: "Candidates", value: (r) => r.candidates, n: true }, { label: "With no flag", value: (r) => r.clean, n: true }]),
  });
}

function scoresCard(d) {
  const H = d.ranking.histograms;
  let view = "early_warning";
  const host = el("div");
  const draw = () => {
    host.replaceChildren(chartCard({
      title: `${VIEW_NAMES[view]} scores`,
      sub: `${n(H[view].in_view)} candidates are in this view. Scores rank candidates within one scan; they are not probabilities. The shortlist and queue sit in the right-hand tail.`,
      actions: el("div.toggle", ...["early_warning", "strategic"].map((v) => el("button", { type: "button", "aria-pressed": String(v === view), onclick: () => { view = v; draw(); } }, VIEW_NAMES[v]))),
      render: (box) => {
        const tk = tokens();
        const bins = d.ranking.bins;
        const labels = Array.from({ length: bins }, (_, i) => (i / bins).toFixed(3));
        const h = H[view];
        chart(box, {
          grid: { left: 54, right: 20, top: 34, bottom: 34 },
          legend: { top: 0, left: 0, textStyle: { color: tk.ink2 }, itemWidth: 12, itemHeight: 12 },
          xAxis: axis("category", { data: labels, name: "score", nameLocation: "middle", nameGap: 24, axisLabel: { color: tk.muted, interval: 4 } }),
          yAxis: axis("value"),
          tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => tipHtml(`score ${ps[0].name} to ${(+ps[0].name + 1 / bins).toFixed(3)}`, ps.map((p) => [p.color, p.seriesName, n(p.value)])) },
          series: [
            { name: "Not shortlisted", type: "bar", stack: "s", data: h.all.map((v, i) => v - h.shortlist[i]), itemStyle: { color: tk.neutral, borderRadius: 2 }, barCategoryGap: "8%" },
            { name: "Shortlist only", type: "bar", stack: "s", data: h.shortlist.map((v, i) => v - h.queue[i]), itemStyle: { color: tk.mithril2, borderRadius: 2 } },
            { name: "Queue", type: "bar", stack: "s", data: h.queue, itemStyle: { color: tk.gold, borderRadius: 2 } },
          ],
        });
      },
      table: () => dataTable(H[view].all.map((v, i) => ({ i, v })), [{ label: "Score from", value: (r) => (r.i / d.ranking.bins).toFixed(3) }, { label: "Candidates", value: (r) => r.v, n: true }, { label: "Shortlisted", value: (r) => H[view].shortlist[r.i], n: true }, { label: "Queued", value: (r) => H[view].queue[r.i], n: true }]),
    }));
  };
  draw();
  return el("div", host,
    el("p.small.muted.mt", "Why isn't the queue simply the top 40? Because of the ring quotas, the source cap and one-per-redundancy-group: a high score in a crowded ring can lose its place to a lower one in an emptier ring. See ", el("a", { href: "#/forge" }, "how ranking works"), "."));
}

// ---------------------------------------------------------------------------------------------- the explorer

const AXES = {
  strength_pct: { label: "Strength (percentile)", get: (c) => c.strength_pct, term: "strength" },
  breadth: { label: "Breadth (percentile)", get: (c) => c.breadth, term: "breadth" },
  score_early_warning: { label: "Early-warning score", get: (c) => c.scores.early_warning, term: "score" },
  score_strategic: { label: "Strategic score", get: (c) => c.scores.strategic, term: "score" },
  best: { label: "Best score (either view)", get: (c) => Math.max(c.scores.early_warning ?? 0, c.scores.strategic ?? 0), term: "score" },
  lead: { label: "Lead time", get: (c) => c.lead, term: "lead" },
  novelty: { label: "Novelty", get: (c) => c.novelty, term: "novelty" },
  known_trend_sim: { label: "Similarity to a known trend", get: (c) => c.known_trend_sim, term: "cosine" },
  territory_sim: { label: "Similarity to a territory", get: (c) => c.territory_sim, term: "cosine" },
  corroboration: { label: "Independent lines of evidence", get: (c) => c.corroboration, term: "corroboration" },
};

function explorer(ctx) {
  const all = state.data.candidates;
  const preset = state.filter || {};
  state.filter = null;
  const f = { q: "", type: new Set(preset.type ? [preset.type] : []), ring: new Set(), source: "", stage: "", flags: "", detector: "", x: "strength_pct", y: "best", page: 0, sort: "best", dir: 1 };
  const mapBox = el("div.chart.tall");
  const tableHost = el("div");
  const count = el("strong");
  const sources = [...new Set(all.map((c) => c.source))].sort();
  const dets = [...new Set(all.flatMap((c) => c.detectors))].sort();
  const pass = (c) => (!f.q || c.label.toLowerCase().includes(f.q) || c.id.includes(f.q)) && (!f.type.size || f.type.has(c.type)) && (!f.ring.size || f.ring.has(c.ring))
    && (!f.source || c.source === f.source) && (!f.detector || c.detectors.includes(f.detector))
    && (!f.stage || (f.stage === "queue" ? c.queue : f.stage === "shortlist" ? c.shortlist : !c.shortlist))
    && (!f.flags || (f.flags === "clean" ? !c.flags.length : c.flags.length));
  const draw = () => {
    const rows = all.filter(pass);
    count.textContent = `${n(rows.length)} of ${n(all.length)}`;
    drawMap(rows);
    drawTable(rows);
  };
  const drawMap = (rows) => {
    const tk = tokens();
    const X = AXES[f.x], Y = AXES[f.y];
    chart(mapBox, {
      grid: { left: 60, right: 30, top: 40, bottom: 56 },
      legend: { top: 0, left: 0, textStyle: { color: tk.ink2 } },
      xAxis: axis("value", { name: X.label, nameLocation: "middle", nameGap: 30, scale: true }),
      yAxis: axis("value", { name: Y.label, nameLocation: "end", scale: true }),
      dataZoom: [{ type: "inside", xAxisIndex: 0 }, { type: "inside", yAxisIndex: 0 }],
      tooltip: { trigger: "item", formatter: (p) => { const c = p.data.c; return tipHtml(c.label.length > 90 ? `${c.label.slice(0, 88)}…` : c.label, [[p.color, TYPE_NAMES[c.type], RING_SHORT[c.ring]], [null, X.label, fmt(X.get(c), 3)], [null, Y.label, fmt(Y.get(c), 3)]], c.queue ? `Queue place ${c.queue.rank}` : c.shortlist ? `Shortlist place ${c.shortlist.rank}` : "Click for details"); } },
      series: TYPES.map((t) => ({
        name: TYPE_NAMES[t], type: "scatter", symbol: SYMBOLS[t], large: rows.length > 3000,
        data: rows.filter((c) => c.type === t && X.get(c) != null && Y.get(c) != null).map((c) => ({
          value: [X.get(c), Y.get(c)], c,
          symbolSize: c.queue ? 15 : c.shortlist ? 11 : 8,
          itemStyle: { color: typeColour(t), opacity: c.shortlist ? 0.95 : 0.55, borderColor: c.queue ? tk.gold : tk.surface, borderWidth: c.queue ? 3 : 1 },
        })),
        emphasis: { scale: 1.6 },
      })),
    }).off("click");
    echarts.getInstanceByDom(mapBox).on("click", (p) => p.data?.c && ctx.open(p.data.c.id));
  };
  const COLS = [
    { key: "label", label: "Candidate", get: (c) => c.label, node: (c) => el("span", c.label.length > 80 ? `${c.label.slice(0, 78)}…` : c.label) },
    { key: "type", label: "Type", get: (c) => TYPES.indexOf(c.type), node: (c) => typeTag(c.type) },
    { key: "ring", label: "Ring", get: (c) => RINGS.indexOf(c.ring), node: (c) => ringTag(c.ring) },
    { key: "source", label: "Source", get: (c) => c.source, node: (c) => el("span.small", c.source) },
    { key: "ew", label: "Early warning", n: true, get: (c) => c.scores.early_warning ?? -1, node: (c) => fmt(c.scores.early_warning, 3) },
    { key: "st", label: "Strategic", n: true, get: (c) => c.scores.strategic ?? -1, node: (c) => fmt(c.scores.strategic, 3) },
    { key: "best", label: "Place", n: true, get: (c) => (c.queue ? -1000 + c.queue.rank : c.shortlist ? -500 + c.shortlist.rank : -Math.max(c.scores.early_warning ?? 0, c.scores.strategic ?? 0)), node: (c) => (c.queue ? el("strong", `Q${c.queue.rank}`) : c.shortlist ? `S${c.shortlist.rank}` : "–") },
    { key: "flags", label: "Flags", get: (c) => c.flags.length, node: (c) => el("span.row-flex", { style: { gap: "4px" } }, ...c.flags.map(flagChip)) },
  ];
  const PER = 25;
  const drawTable = (rows) => {
    const col = COLS.find((c) => c.key === f.sort);
    rows = rows.slice().sort((a, b) => {
      const va = col.get(a), vb = col.get(b);
      return (va < vb ? -1 : va > vb ? 1 : 0) * f.dir || (a.id < b.id ? -1 : 1);
    });
    const pages = Math.max(1, Math.ceil(rows.length / PER));
    f.page = Math.min(f.page, pages - 1);
    const t = el("table.data");
    t.append(el("thead", el("tr", ...COLS.map((c) => el(`th.sortable${c.n ? ".n" : ""}`, { onclick: () => { f.dir = f.sort === c.key ? -f.dir : ["label", "source", "best", "type", "ring"].includes(c.key) ? 1 : -1; f.sort = c.key; f.page = 0; drawTable(all.filter(pass)); } }, c.label, f.sort === c.key ? (f.dir > 0 ? " ▲" : " ▼") : "")))));
    t.append(el("tbody", ...rows.slice(f.page * PER, f.page * PER + PER).map((c) => el("tr.click", { tabindex: 0, onclick: () => ctx.open(c.id), onkeydown: (e) => e.key === "Enter" && ctx.open(c.id) }, ...COLS.map((k) => el(`td${k.n ? ".n" : ""}`, k.node(c)))))));
    tableHost.replaceChildren(el("div.table-wrap", t), el("div.pager",
      el("button.btn.btn-small", { type: "button", disabled: f.page === 0, onclick: () => { f.page -= 1; drawTable(all.filter(pass)); } }, "← Previous"),
      el("span", `Page ${f.page + 1} of ${pages}`),
      el("button.btn.btn-small", { type: "button", disabled: f.page >= pages - 1, onclick: () => { f.page += 1; drawTable(all.filter(pass)); } }, "Next →")));
  };
  const pills = (set, values, names, colour) => el("div.pills", ...values.map((v) => {
    const b = el("button.pill", { type: "button", "aria-pressed": String(set.has(v)) }, colour ? el("span.swatch", { style: { background: colour(v) } }) : null, names[v]);
    b.onclick = () => { set.has(v) ? set.delete(v) : set.add(v); b.setAttribute("aria-pressed", String(set.has(v))); f.page = 0; draw(); };
    return b;
  }));
  const select = (label, key, options) => {
    const s = el("select", { "aria-label": label }, ...options.map(([v, t]) => el("option", { value: v, selected: f[key] === v }, t)));
    s.onchange = () => { f[key] = s.value; f.page = 0; draw(); };
    return el("label.field", label, s);
  };
  const search = el("input", { type: "search", placeholder: "Search names…", "aria-label": "Search candidates" });
  search.oninput = debounce(() => { f.q = search.value.trim().toLowerCase(); f.page = 0; draw(); }, 180);
  const axisSel = (label, key) => {
    const s = el("select", { "aria-label": label }, ...Object.entries(AXES).map(([v, a]) => el("option", { value: v, selected: f[key] === v }, a.label)));
    s.onchange = () => { f[key] = s.value; drawMap(all.filter(pass)); };
    return el("label.field", label, s);
  };
  const bar = el("div.card.filters",
    el("label.field", "Search", search),
    el("div.field", "Type", pills(f.type, TYPES, TYPE_NAMES, typeColour)),
    el("div.field", "Ring", pills(f.ring, RINGS, RING_SHORT, (r) => `var(--r-${r})`)),
    select("Source", "source", [["", "All sources"], ...sources.map((s) => [s, s])]),
    select("Detector", "detector", [["", "All detectors"], ...dets.map((s) => [s, words(s)])]),
    select("Stage", "stage", [["", "Every candidate"], ["queue", "In the queue"], ["shortlist", "Shortlisted"], ["none", "Not shortlisted"]]),
    select("Flags", "flags", [["", "Flagged or not"], ["clean", "No flag"], ["flagged", "Flagged"]]),
    el("div.field", "Showing", count));
  const mapCard = el("div.card",
    el("div.card-head", el("div", el("h3", "The candidate map"), el("p.card-sub", "Each mark is a candidate (shape and colour: its type). Bigger marks are shortlisted; gold rings are in the queue. Scroll to zoom; click a mark for its drawer.")),
      el("div.row-flex", axisSel("Across", "x"), axisSel("Up", "y"))),
    mapBox, el("p.small.muted", "Tip: try 'Strength' across and 'Breadth' up to see big-but-narrow against small-but-broad finds. ", term("percentile", "What's a percentile?")));
  requestAnimationFrame(draw);
  return el("div", bar, mapCard, el("div.card.mt", el("div.card-head", el("h3", "Every candidate"), el("p.card-sub", "Click a heading to sort; click a row for its drawer. Place: Q = queue, S = shortlist.")), tableHost));
}

