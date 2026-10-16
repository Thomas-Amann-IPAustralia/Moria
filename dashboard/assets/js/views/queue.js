// Level 2, the review queue (the mithril): the 40 picked for a person, their make-up, and, with the Doors open, the
// cards themselves (click one for its dossier).

import { flagChip, gem, needsPrivate, ringTag, sealedCard, typeTag } from "../bits.js";
import { axis, chart, chartCard, dataTable, sparkline, tipHtml, tokens } from "../charts.js";
import { num, term, tip } from "../glossary.js";
import { loadPractice, pickFile } from "../main.js";
import { dossierOf, hasDetail, seriesOf, state } from "../state.js";
import { download, el, fmt, key, n, RING_SHORT, RINGS, title, toCsv, TYPE_NAMES, TYPES, typeColour, VIEW_NAMES } from "../util.js";

export function render(root, ctx) {
  const d = state.data;
  const q = d.queue;
  root.append(el("div.view-head", el("div",
    el("div.eyebrow", "Mithril worth the digging"),
    el("h1", "The review queue", tip("queue")),
    el("p.lede", `The ${q.size} candidates Moria judged most worth a person's time this round, picked from a shortlist of ${q.shortlist_size} under the ring quotas. Nobody has reviewed them yet: they are questions, not answers.`))));
  root.append(el("div.stats",
    stat("In the queue", q.size, `${n(d.funnel.candidates)} candidates were scored to find them`),
    stat("Carrying a flag", q.flagged, "Shown, never hidden: read their checks first", "flags"),
    stat("Picked by each view", `${q.views.early_warning ?? 0} · ${q.views.strategic ?? 0}`, "Early warning · strategic", "views"),
    stat("Reviewed so far", q.register.reviewed, "The first review round is next", "status")));
  if (hasDetail()) root.append(cards(ctx));
  else {
    root.append(el("div.section", el("h2", "The 40, sealed"), el("p.lede", "Forty places, by type. Their names, charts and evidence are private.")), sealedGrid(q));
    root.append(needsPrivate("To read the 40 (their names, charts and evidence), open the Doors with your private file.", { pickFile, loadPractice }));
  }
  root.append(el("div.section", el("h2", "What the queue is made of")));
  root.append(el("div.grid.g2", ringType(d), sources(d)));
  root.append(el("div.grid.g2.mt", checksCard(d), suggestions(d)));
}

function stat(label, value, note, key) {
  return el("div.card.stat", el("div.stat-label", label, key ? tip(key) : null), el("div.stat-value", typeof value === "number" ? n(value) : value), el("p.stat-note", note));
}

function sealedGrid(q) {
  const g = el("div.sealed-strip");
  for (const t of TYPES) for (let i = 0; i < (q.types[t] || 0); i++) g.append(sealedCard(t));
  return g;
}

// --------------------------------------------------------------------------------------------- the cards

function spark(c) {
  const s = seriesOf(c).find((x) => x.role === "subject")?.data;
  if (s) {
    const vals = s.values.map((v, i) => (v == null ? null : s.transform === "log_share" ? (s.denom?.[i] ? v / s.denom[i] : null) : v)).slice(-36);
    const an = s.anomaly ? s.periods.slice(-36).indexOf(s.anomaly.period) : null;
    return sparkline(vals, typeColour(c.type), { mark: an >= 0 ? an : vals.length - 1 });
  }
  const ch = dossierOf(c.id)?.chart;
  if (ch?.values) return sparkline(ch.values, typeColour(c.type), { mark: ch.values.length - 1 });
  const pn = c.numbers?.jurisdiction_shift || c.numbers?.new_combination || c.numbers?.fading_combination;
  const text = pn?.window != null ? `${pn.window} in the window against ${pn.baseline} in the baseline`
    : c.n_items ? `${c.n_items} ${c.n_items === 1 ? "item" : "items"} from ${c.n_sources} ${c.n_sources === 1 ? "source" : "sources"}` : "";
  return el("div.spark-svg.small.muted", { style: { height: "42px", display: "grid", alignItems: "center" } }, text);
}

function cards(ctx) {
  const all = state.data.candidates.filter((c) => c.queue).sort((a, b) => a.queue.rank - b.queue.rank);
  const f = { type: new Set(), ring: new Set(), view: new Set(), flagged: false, sort: "rank" };
  const grid = el("div.qgrid");
  const count = el("span.muted.small");
  const draw = () => {
    let rows = all.filter((c) => (!f.type.size || f.type.has(c.type)) && (!f.ring.size || f.ring.has(c.ring)) && (!f.view.size || f.view.has(c.queue.view)) && (!f.flagged || c.flags.length));
    const key = { rank: (c) => c.queue.rank, early_warning: (c) => -(c.scores.early_warning ?? -1), strategic: (c) => -(c.scores.strategic ?? -1), type: (c) => TYPES.indexOf(c.type) * 100 + c.queue.rank }[f.sort];
    rows = rows.slice().sort((a, b) => key(a) - key(b));
    count.textContent = `${rows.length} of ${all.length} shown`;
    grid.replaceChildren(...rows.map((c) => card(c, ctx)));
  };
  const pills = (set, values, names, colour) => el("div.pills", ...values.map((v) => {
    const b = el("button.pill", { type: "button", "aria-pressed": "false" }, colour ? el("span.swatch", { style: { background: colour(v) } }) : null, names[v] || title(v));
    b.onclick = () => { set.has(v) ? set.delete(v) : set.add(v); b.setAttribute("aria-pressed", String(set.has(v))); draw(); };
    return b;
  }));
  const sort = el("select", { "aria-label": "Sort by" }, el("option", { value: "rank" }, "Queue place"), el("option", { value: "early_warning" }, "Early-warning score"), el("option", { value: "strategic" }, "Strategic score"), el("option", { value: "type" }, "Type"));
  sort.onchange = () => { f.sort = sort.value; draw(); };
  const flagged = el("label.check", el("input", { type: "checkbox", onchange: (e) => { f.flagged = e.target.checked; draw(); } }), "Flagged only");
  const csv = el("button.btn.btn-small", { type: "button", onclick: () => download(`moria-queue-${state.data.as_of}.csv`, toCsv(all, [
    { label: "place", value: (c) => c.queue.rank }, { label: "label", value: (c) => c.label }, { label: "type", value: (c) => c.type }, { label: "ring", value: (c) => c.ring },
    { label: "source", value: (c) => c.source }, { label: "view", value: (c) => c.queue.view }, { label: "flags", value: (c) => c.flags.join(" ") },
    { label: "score_early_warning", value: (c) => c.scores.early_warning }, { label: "score_strategic", value: (c) => c.scores.strategic }, { label: "id", value: (c) => c.id }])) }, "Download as CSV");
  const bar = el("div.card.filters",
    el("div.field", "Type", pills(f.type, TYPES, TYPE_NAMES, typeColour)),
    el("div.field", "Ring", pills(f.ring, RINGS, RING_SHORT, (r) => `var(--r-${r})`)),
    el("div.field", "Picked by", pills(f.view, ["early_warning", "strategic"], VIEW_NAMES)),
    el("div.field", "Sort", sort), flagged, el("div.row-flex", { style: { marginLeft: "auto" } }, count, csv));
  draw();
  return el("div", el("div.section", el("h2", "The 40, opened"), el("p.lede", "Click a card for its dossier: the evidence, the numbers, the alternative explanations and why it ranked here.")), bar, grid);
}

function card(c, ctx) {
  const k = el("div.card.click.qcard", {
    tabindex: 0, role: "button", "aria-label": `Place ${c.queue.rank}: ${c.label}`,
    onclick: () => ctx.open(c.id), onkeydown: (e) => e.key === "Enter" && ctx.open(c.id),
  },
    el("div.qcard-top", el("span.rank-badge", String(c.queue.rank)), typeTag(c.type), ringTag(c.ring)),
    el("h4", c.label.length > 110 ? `${c.label.slice(0, 108)}…` : c.label),
    spark(c),
    el("div.row.small.muted", el("span", c.source), el("span", "·"), el("span", `${VIEW_NAMES[c.queue.view]} pick`), c.queue.pass > 1 ? el("span.tag", `pass ${c.queue.pass}`) : null),
    (c.flags.length || c.known_trend_match || c.numbers?.context_explains)
      ? el("div.row", ...c.flags.map(flagChip), c.known_trend_match ? el("span.tag.gold", `Known trend ${c.known_trend}`) : null, c.numbers?.context_explains ? el("span.tag", "Explained by context") : null)
      : null);
  k.style.setProperty("--gem", `var(--t-${key(c.type)})`);
  return k;
}

// ------------------------------------------------------------------------------------------------ make-up

function ringType(d) {
  const q = d.queue;
  // queue by ring and type: from the cards when open, else the public counts (by type and ring separately)
  const detail = hasDetail() ? state.data.candidates.filter((c) => c.queue) : null;
  return chartCard({
    title: "By ring and type", tip: tip("quota"),
    sub: detail ? "Each ring's places in the queue, split by type." : "Places by ring against each ring's quota, and the types in the queue.",
    render: (box) => {
      const tk = tokens();
      if (detail) {
        chart(box, {
          grid: { left: 90, right: 30, top: 34, bottom: 24 },
          legend: { top: 0, left: 0, textStyle: { color: tk.ink2 }, itemWidth: 12, itemHeight: 12 },
          xAxis: axis("value", { minInterval: 1 }),
          yAxis: axis("category", { data: RINGS.map((r) => RING_SHORT[r]), inverse: true }),
          tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => tipHtml(ps[0].name, ps.filter((p) => p.value).map((p) => [p.color, p.seriesName, n(p.value)]), `quota: ${q.quotas[RINGS[ps[0].dataIndex]]?.cap ?? "–"} places`) },
          series: TYPES.map((t) => ({ name: TYPE_NAMES[t], type: "bar", stack: "q", barMaxWidth: 24, itemStyle: { color: typeColour(t), borderColor: tk.surface, borderWidth: 2, borderRadius: 4 },
            data: RINGS.map((r) => detail.filter((c) => c.ring === r && c.type === t).length) })),
        });
      } else {
        chart(box, {
          grid: [{ left: 90, right: 30, top: 20, height: "36%" }, { left: 90, right: 30, top: "62%", height: "30%" }],
          xAxis: [axis("value", { gridIndex: 0, minInterval: 1 }), axis("value", { gridIndex: 1, minInterval: 1 })],
          yAxis: [axis("category", { gridIndex: 0, data: RINGS.map((r) => RING_SHORT[r]), inverse: true }), axis("category", { gridIndex: 1, data: TYPES.map((t) => TYPE_NAMES[t]), inverse: true })],
          tooltip: { trigger: "item", formatter: (p) => tipHtml(p.name, [[p.color, p.seriesName, n(p.value)]]) },
          series: [
            { name: "Quota", type: "bar", xAxisIndex: 0, yAxisIndex: 0, barGap: "-100%", barMaxWidth: 22, data: RINGS.map((r) => q.quotas[r]?.cap ?? 0), itemStyle: { color: tk.surface2, borderRadius: 4 }, silent: true },
            { name: "Filled", type: "bar", xAxisIndex: 0, yAxisIndex: 0, barMaxWidth: 22, data: RINGS.map((r) => ({ value: q.quotas[r]?.filled ?? 0, itemStyle: { color: `${getComputedStyle(document.documentElement).getPropertyValue(`--r-${r}`).trim()}`, borderRadius: 4 } })), label: { show: true, position: "right", color: tk.ink2 } },
            { name: "In the queue", type: "bar", xAxisIndex: 1, yAxisIndex: 1, barMaxWidth: 22, data: TYPES.map((t) => ({ value: q.types[t] ?? 0, itemStyle: { color: typeColour(t), borderRadius: 4 } })), label: { show: true, position: "right", color: tk.ink2 } },
          ],
        });
      }
    },
    table: () => dataTable(RINGS, [{ label: "Ring", value: (r) => RING_SHORT[r] }, { label: "Quota", value: (r) => q.quotas[r]?.cap, n: true }, { label: "Filled", value: (r) => q.quotas[r]?.filled, n: true }]),
  });
}

function sources(d) {
  const q = d.queue;
  const rows = Object.entries(q.sources).sort((a, b) => b[1] - a[1]);
  const short = q.shortlist.sources;
  return chartCard({
    title: "By source",
    sub: "No source may fill more than a quarter of the queue. Grey: the shortlist of 100.",
    render: (box) => {
      const tk = tokens();
      const names = [...new Set([...rows.map((r) => r[0]), ...Object.keys(short)])].sort((a, b) => (q.sources[b] || 0) - (q.sources[a] || 0) || (short[b] || 0) - (short[a] || 0));
      box.style.height = `${Math.max(240, names.length * 30 + 60)}px`;
      chart(box, {
        grid: { left: 150, right: 30, top: 30, bottom: 24 },
        legend: { top: 0, left: 0, textStyle: { color: tk.ink2 }, itemWidth: 12, itemHeight: 12 },
        xAxis: axis("value", { minInterval: 1 }),
        yAxis: axis("category", { data: names, inverse: true }),
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => tipHtml(ps[0].name, ps.map((p) => [p.color, p.seriesName, n(p.value)])) },
        series: [
          { name: "Shortlist", type: "bar", data: names.map((s) => short[s] || 0), barMaxWidth: 14, itemStyle: { color: tk.neutral, borderRadius: [0, 4, 4, 0] } },
          { name: "Queue", type: "bar", data: names.map((s) => q.sources[s] || 0), barMaxWidth: 14, itemStyle: { color: tk.mithril, borderRadius: [0, 4, 4, 0] } },
        ],
      });
    },
    table: () => dataTable(rows, [{ label: "Source", value: (r) => r[0] }, { label: "Queue", value: (r) => r[1], n: true }, { label: "Shortlist", value: (r) => short[r[0]] || 0, n: true }]),
  });
}

const CHECK_NAMES = {
  redundancy: "Moves with others", coverage: "Source volume moved", source_break: "Source too new", concentrated_works: "Works in one venue",
  explained_by_context: "Explained by context", known_trend: "Matches a known trend", few_applicants: "Few applicants", administrative: "Administrative cause", reclassified: "Reclassified",
};
const CHECK_TERMS = { redundancy: "redundancy_check", known_trend: "known_trend_check" };

function checksCard(d) {
  const rows = Object.entries(d.queue.checks).sort((a, b) => b[1] - a[1]);
  const total = d.queue.shortlist_size;
  return el("div.card",
    el("div.card-head", el("div", el("h3", "Alternative explanations found", tip("dossier")), el("p.card-sub", `Of the ${total} shortlisted dossiers, how many each check flagged. A flag means 'look closer', not 'wrong'.`))),
    el("div.bars-mini", ...rows.map(([k, v]) => {
      const m = el("div.meter", el("i"));
      m.firstChild.style.width = `${(v / total) * 100}%`;
      m.firstChild.style.background = "var(--s-serious)";
      return el("div.bar-mini", el("span", term(CHECK_TERMS[k] || k, CHECK_NAMES[k] || title(k))), m, el("span.num", `${v}`));
    })),
    el("p.small.muted.mt", `OpenAlex sample works: ${d.queue.openalex_samples.fetched} fetched, ${d.queue.openalex_samples.concentrated} concentrated in one venue.`));
}

function suggestions(d) {
  const pw = d.queue.pathways;
  const ev = pw.evaluation;
  const ids = ["P1", "P2", "P3", "P4", "P5", "P6"].filter((p) => pw.probabilities[p]);
  const statements = d.config?.pathways || {};
  return chartCard({
    title: "What the decision model said", tip: tip("decision_model"),
    sub: "Each pathway's probability across the shortlist (box: middle half; whiskers: lowest to highest). A model that discriminates would spread these out.",
    render: (box) => {
      const tk = tokens();
      chart(box, {
        grid: { left: 40, right: 20, top: 16, bottom: 30 },
        xAxis: axis("category", { data: ids }),
        yAxis: axis("value", { min: 0, max: 1 }),
        tooltip: { trigger: "item", formatter: (p) => { const x = pw.probabilities[ids[p.dataIndex]]; return tipHtml(ids[p.dataIndex], [[null, "lowest", fmt(x.min, 3)], [null, "median", fmt(x.median, 3)], [null, "highest", fmt(x.max, 3)]], statements[ids[p.dataIndex]]); } },
        series: [{ type: "boxplot", data: ids.map((p) => { const x = pw.probabilities[p]; return [x.min, x.q1, x.median, x.q3, x.max]; }), itemStyle: { color: tk.surface2, borderColor: tk.mithril, borderWidth: 2 },
          markLine: { silent: true, symbol: "none", data: [{ yAxis: 0.5 }], lineStyle: { color: tk.muted }, label: { formatter: "coin toss", color: tk.muted, position: "insideEndTop" } } }],
      });
    },
    actions: ev ? el("span", el("span.flag-chip", ev.passes ? "passed its check" : "failed its check")) : null,
    table: () => dataTable(ids, [{ label: "Pathway", value: (p) => p }, { label: "Lowest", value: (p) => pw.probabilities[p].min, n: true }, { label: "Median", value: (p) => pw.probabilities[p].median, n: true }, { label: "Highest", value: (p) => pw.probabilities[p].max, n: true }, { label: "Statement", value: (p) => statements[p] }]),
  });
}

