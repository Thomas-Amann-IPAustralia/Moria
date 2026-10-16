// Level 5, the forge: how a candidate's score is made, how the queue is picked, and a what-if playground that
// re-runs Moria's own ranking (ported line for line) under your settings. It first proves itself: at Moria's
// settings it must reproduce the real shortlist and queue. Nothing here changes Moria.

import { needsPrivate, ringTag, typeTag } from "../bits.js";
import { axis, chart, chartCard, dataTable, tipHtml, tokens } from "../charts.js";
import { term, tip } from "../glossary.js";
import { loadPractice, pickFile } from "../main.js";
import { geomean, settingsFrom, whatIf } from "../ranking.js";
import { candidate, hasDetail, state } from "../state.js";
import { debounce, el, fmt, key, n, pct, RING_SHORT, RINGS, title, TYPE_NAMES, TYPES, VIEW_NAMES } from "../util.js";

export function render(root, ctx) {
  const d = state.data;
  root.append(el("div.view-head", el("div",
    el("div.eyebrow", "The forge"),
    el("h1", "How ranking works"),
    el("p.lede", "How Moria turns thousands of candidates into a queue of 40: what each score is made of, the rules of the pick, and a forge where you can change the settings and watch the queue change. It's a what-if: Moria itself is never changed."))));
  root.append(recipe(d));
  if (hasDetail()) root.append(playground(ctx));
  else {
    root.append(needsPrivate("The full what-if (re-running the queue under your settings and seeing which candidates come and go) needs the candidates themselves.", { pickFile, loadPractice }));
  }
  root.append(el("div.grid.g2.mt", sensitivity(d), calculator(d)));
}

// ------------------------------------------------------------------------------------------------- the recipe

function recipe(d) {
  const r = d.config.rank, q = d.config.queue;
  const step = (n_, head, body) => el("div.card.flat", el("div.eyebrow", `Step ${n_}`), el("h3", head), body);
  return el("div.grid.g4",
    step(1, "Measure four components", el("div",
      el("p.small", term("strength", "Strength"), ", ", term("breadth", "breadth"), ", ", term("lead", "lead time"), " and ", term("novelty", "novelty"), ", each turned into a ", term("percentile", "percentile"), " between 0 and 1."),
      el("p.small.muted", "Pathway and impact would join once the decision model is trusted. ", tip("pathway_c")))),
    step(2, "Combine them", el("div",
      el("p.small", "Each view takes a ", term("geomean", "weighted geometric mean"), ": early warning of strength, novelty and lead; strategic of strength and breadth."),
      el("p.small.muted", `Nothing counts below ${r.floor}, so one weak component can't zero a score.`))),
    step(3, "Apply the factors", el("div",
      el("p.small", "Multiply by the ", term("factors", "factors"), ": type (anomalies ", fmt(r.type_weight.anomaly), "), ", term("flag_penalty", "flags"), ", ", term("scope", "scope"), " and context."),
      el("p.small.muted", "A flag lowers the score but never removes the candidate."))),
    step(4, "Pick under quotas", el("div",
      el("p.small", `Shortlist ${r.shortlist}, then a queue of ${q.size}: the views take turns; `, term("quota", "rings"), ` ${pct(q.rings.core)} / ${pct(q.rings.adjacent)} / ${pct(q.rings.wider_world)}; no source over ${pct(q.source_max)}; one per `, term("redundancy", "redundancy group"), "."),
      el("p.small.muted", "Places a ring can't fill pass to the others. ", tip("pass")))));
}

// ------------------------------------------------------------------------------------------------- the forge

const SLIDERS = [
  { group: "Early-warning weights", items: [["weights.early_warning.strength", "Strength", 0, 3, 0.1], ["weights.early_warning.novelty", "Novelty", 0, 3, 0.1], ["weights.early_warning.lead", "Lead time", 0, 3, 0.1]], open: true, term: "views" },
  { group: "Strategic weights", items: [["weights.strategic.strength", "Strength", 0, 3, 0.1], ["weights.strategic.breadth", "Breadth", 0, 3, 0.1]], open: true, term: "views" },
  { group: "Flag penalties", items: [["flag_penalty.coverage", "Coverage", 0.1, 1, 0.05], ["flag_penalty.ingestion", "Ingestion", 0.1, 1, 0.05], ["flag_penalty.duplicate", "Duplicate", 0.1, 1, 0.05], ["flag_penalty.news_cycle", "News cycle", 0.1, 1, 0.05], ["flag_penalty.source_break", "Source break", 0.1, 1, 0.05], ["flag_penalty.label_drift", "Label drift", 0.1, 1, 0.05]], term: "flag_penalty" },
  { group: "Type weights", items: [["type_weight.trend", "Trend", 0, 1.5, 0.05], ["type_weight.acceleration", "Acceleration", 0, 1.5, 0.05], ["type_weight.weak_signal", "Weak signal", 0, 1.5, 0.05], ["type_weight.anomaly", "Anomaly", 0, 1.5, 0.05]], term: "factors" },
  { group: "The queue", items: [["size", "Queue size", 10, 80, 1], ["shortlist", "Shortlist size", 40, 200, 5], ["source_max", "Most from one source", 0.1, 1, 0.05], ["views.early_warning", "Early-warning share", 0, 1, 0.05]], term: "queue" },
  { group: "Ring quotas", items: [["rings.core", "Core", 0, 1, 0.05], ["rings.adjacent", "Adjacent", 0, 1, 0.05], ["rings.wider_world", "Wider world", 0, 1, 0.05]], term: "quota" },
];

function getPath(o, path) {
  return path.split(".").reduce((a, k) => a[k], o);
}
function setPath(o, path, v) {
  const ks = path.split(".");
  const last = ks.pop();
  ks.reduce((a, k) => a[k], o)[last] = v;
}

function playground(ctx) {
  const cands = state.data.candidates;
  const base = settingsFrom(state.data.config);
  let s = structuredClone(base);
  const real = whatIf(cands, base, state.data.register);
  const realQueue = cands.filter((c) => c.queue).sort((a, b) => a.queue.rank - b.queue.rank).map((c) => c.id);
  const realShort = cands.filter((c) => c.shortlist).sort((a, b) => a.shortlist.rank - b.shortlist.rank).map((c) => c.id);
  const sameQueue = realQueue.length === real.queue.length && real.queue.every((p, i) => p.id === realQueue[i]);
  const sameShort = realShort.length === real.shortlist.length && real.shortlist.every((p, i) => p.id === realShort[i]);
  const proof = el(`div.callout.${sameQueue && sameShort ? "good" : "warn"}.mb`, el("div.c-ico", sameQueue && sameShort ? "✓" : "!"), el("div",
    el("h4", sameQueue && sameShort ? "The forge is true to Moria" : "The forge doesn't quite match Moria"),
    el("p.small", sameQueue && sameShort
      ? `At Moria's own settings, this playground re-ran the ranking in your browser and picked exactly the same shortlist (${realShort.length}) and queue (${realQueue.length}), in the same order. So what you see when you move a slider is what Moria would do.`
      : `At Moria's own settings it reproduced ${real.queue.filter((p) => realQueue.includes(p.id)).length} of ${realQueue.length} queue places. Treat the what-if as approximate.`)));
  const panel = el("div.card.sliders");
  const out = el("div");
  const sliders = [];
  const run = debounce(() => compute(), 90);
  const reset = el("button.btn.btn-small", { type: "button", onclick: () => { s = structuredClone(base); for (const x of sliders) x.sync(); compute(); } }, "Reset to Moria's settings");
  panel.append(el("div.row-flex.space-between", el("h3", { style: { margin: 0 } }, "Your settings"), reset),
    el("p.small.muted", "Each slider changes one setting. A dot marks those you've moved."));
  for (const g of SLIDERS) {
    const det = el("details.group", { open: g.open || null }, el("summary", el("span", g.group, " ", tip(g.term))));
    for (const [path, label, min, max, stepV] of g.items) {
      const input = el("input", { type: "range", min, max, step: stepV, "aria-label": label });
      const output = el("output");
      const row = el("div.slider", el("label", label), output, input);
      const sync = () => {
        const v = getPath(s, path);
        input.value = v;
        output.textContent = Number.isInteger(stepV) ? String(v) : fmt(v, 3);
        row.classList.toggle("changed", Math.abs(v - getPath(base, path)) > 1e-9);
      };
      input.oninput = () => {
        let v = Number(input.value);
        setPath(s, path, v);
        if (path.startsWith("rings.")) normalise(s.rings, path.split(".")[1]);
        if (path === "views.early_warning") s.views.strategic = +(1 - v).toFixed(4);
        for (const x of sliders) x.sync();
        run();
      };
      sliders.push({ sync });
      sync();
      det.append(row);
    }
    panel.append(det);
  }
  panel.append(el("p.small.muted.mt", "Pathway and impact weights aren't here: the decision model's suggestions are switched off, so they change nothing."));

  let prev = new Set(realQueue);
  const compute = () => {
    const res = whatIf(cands, s, state.data.register);
    const ids = res.queue.map((p) => p.id);
    const kept = ids.filter((id) => realQueue.includes(id)).length;
    const joined = ids.filter((id) => !realQueue.includes(id));
    const left = realQueue.filter((id) => !ids.includes(id));
    const big = el("div.big-number", `${kept}`);
    const carts = el("div.carts", ...res.queue.map((p) => {
      const c = candidate(p.id);
      const k = el(`div.cart${!realQueue.includes(p.id) ? ".new" : ""}`, { title: `${p.rank}. ${c.label}`, tabindex: 0, role: "button", onclick: () => ctx.open(p.id), onkeydown: (e) => e.key === "Enter" && ctx.open(p.id) });
      k.style.setProperty("--gem", `var(--t-${key(c.type)})`);
      if (!prev.has(p.id) && realQueue.includes(p.id)) k.classList.add("new");
      return k;
    }));
    prev = new Set(ids);
    const list = (head, xs, empty) => el("div.card.flat", el("h4", head, ` (${xs.length})`), xs.length
      ? el("ul.items", ...xs.slice(0, 12).map((id) => { const c = candidate(id); return el("li", { style: { cursor: "pointer" }, onclick: () => ctx.open(id) }, el("div.row-flex", typeTag(c.type), ringTag(c.ring)), el("div", c.label.length > 90 ? `${c.label.slice(0, 88)}…` : c.label)); }), xs.length > 12 ? el("li.muted.small", `and ${xs.length - 12} more`) : null)
      : el("p.small.muted", empty));
    const compBox = el("div.chart.short");
    out.replaceChildren(
      el("div.card",
        el("div.row-flex.space-between",
          el("div", el("div.eyebrow", "Places kept"), el("div.row-flex", big, el("span.lede", `of Moria's ${realQueue.length} are still in your queue of ${ids.length}`, tip("sensitivity")))),
          el("div.small.muted", { style: { maxWidth: "320px" } }, "Each square is a place in your queue, coloured by type. Gold rings: candidates that aren't in Moria's queue. Click one to open it.")),
        el("div.mt", carts)),
      el("div.grid.g2.mt", list("Joined the queue", joined, "Nothing new: your settings pick the same candidates."), list("Left the queue", left, "Nothing lost.")),
      el("div.card.mt", el("h3", "What your queue is made of, against Moria's"), compBox));
    requestAnimationFrame(() => {
      const tk = tokens();
      const mine = res.queue.map((p) => candidate(p.id));
      const theirs = realQueue.map(candidate);
      const cats = [...TYPES.map((t) => TYPE_NAMES[t]), ...RINGS.map((r) => RING_SHORT[r])];
      const count = (xs) => [...TYPES.map((t) => xs.filter((c) => c.type === t).length), ...RINGS.map((r) => xs.filter((c) => c.ring === r).length)];
      chart(compBox, {
        grid: { left: 40, right: 16, top: 30, bottom: 30 },
        legend: { top: 0, left: 0, textStyle: { color: tk.ink2 }, itemWidth: 12, itemHeight: 12 },
        xAxis: axis("category", { data: cats }),
        yAxis: axis("value", { minInterval: 1 }),
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => tipHtml(ps[0].name, ps.map((p) => [p.color, p.seriesName, n(p.value)])) },
        series: [
          { name: "Moria's queue", type: "bar", data: count(theirs), barMaxWidth: 18, itemStyle: { color: tk.neutral, borderRadius: [4, 4, 0, 0] } },
          { name: "Your queue", type: "bar", data: count(mine), barMaxWidth: 18, itemStyle: { color: tk.mithril, borderRadius: [4, 4, 0, 0] } },
        ],
      });
    });
  };
  requestAnimationFrame(compute);
  return el("div.section", el("h2", "The forge: try your own settings"), proof, el("div.forge", panel, out));
}

/** Keep the ring quotas adding up to 1: the others shrink or grow in proportion when one moves. */
function normalise(rings, moved) {
  const v = Math.min(1, Math.max(0, rings[moved]));
  const others = Object.keys(rings).filter((k) => k !== moved);
  const rest = others.reduce((a, k) => a + rings[k], 0);
  for (const k of others) rings[k] = rest > 0 ? (rings[k] / rest) * (1 - v) : (1 - v) / others.length;
  rings[moved] = v;
  for (const k of Object.keys(rings)) rings[k] = +rings[k].toFixed(4);
}

// ---------------------------------------------------------------------------------------------- public parts

function sensitivity(d) {
  const rows = d.queue.sensitivity;
  const name = (r) => (r.view === "both" ? `No ${r.component === "flags" ? "flag penalties" : "type weights"}` : `${VIEW_NAMES[r.view]}: ${r.component} × ${r.factor}`);
  return chartCard({
    title: "How much each setting matters", tip: tip("sensitivity"),
    sub: "Moria's own test: each weight halved (× 0.5) or raised by half (× 1.5), and the queue picked again. Bars show the places of the 40 that stay.",
    render: (box) => {
      const tk = tokens();
      const sorted = rows.slice().sort((a, b) => a.overlap - b.overlap);
      box.style.height = `${sorted.length * 24 + 60}px`;
      chart(box, {
        grid: { left: 230, right: 40, top: 10, bottom: 28 },
        xAxis: axis("value", { min: 0, max: rows[0]?.size ?? 40 }),
        yAxis: axis("category", { data: sorted.map(name), inverse: true }),
        tooltip: { trigger: "item", formatter: (p) => tipHtml(p.name, [[null, "places kept", `${p.value} of ${sorted[p.dataIndex].size}`]], ["pathway", "impact"].includes(sorted[p.dataIndex].component) ? "No effect while the decision model's suggestions are switched off." : null) },
        series: [{ type: "bar", data: sorted.map((r) => ({ value: r.overlap, itemStyle: { color: r.overlap < r.size * 0.8 ? tk.serious : r.overlap < r.size ? tk.mithril2 : tk.neutral, borderRadius: [0, 4, 4, 0] } })), barMaxWidth: 14,
          label: { show: true, position: "right", color: tk.ink2, formatter: (p) => `${p.value}` } }],
      });
    },
    table: () => dataTable(rows, [{ label: "Setting", value: name }, { label: "Places kept", value: (r) => r.overlap, n: true }, { label: "Of", value: (r) => r.size, n: true }]),
  });
}

function calculator(d) {
  const r = d.config.rank;
  const v = { strength: 0.8, novelty: 0.6, lead: 0.7, breadth: 0.5, type: "acceleration", flags: 0, scope: 1 };
  const outBox = el("div");
  const histBox = el("div.chart.tiny");
  const draw = () => {
    const flag = (d.config.rank.flag_penalty.coverage) ** v.flags;
    const factor = v.scope * r.type_weight[v.type] * flag;
    const ew = geomean({ strength: v.strength, novelty: v.novelty, lead: v.lead }, r.weights.early_warning, r.weights_order?.early_warning || ["strength", "novelty", "lead"], r.floor) * factor;
    const st = geomean({ strength: v.strength, breadth: v.breadth }, r.weights.strategic, r.weights_order?.strategic || ["strength", "breadth"], r.floor) * factor;
    const views = { trend: ["strategic"], acceleration: ["early_warning", "strategic"], weak_signal: ["early_warning"], anomaly: ["early_warning"] }[v.type];
    const beat = (view, score) => {
      const h = d.ranking.histograms[view];
      const bin = Math.min(d.ranking.bins - 1, Math.floor(score * d.ranking.bins));
      const below = h.all.slice(0, bin).reduce((a, b) => a + b, 0) + h.all[bin] / 2;
      return below / Math.max(1, h.in_view);
    };
    outBox.replaceChildren(...views.map((view) => {
      const sc = view === "early_warning" ? ew : st;
      return el("div.card.flat.mb", el("div.row-flex.space-between", el("strong", `${VIEW_NAMES[view]} score`), el("span.big-number", { style: { fontSize: "2rem" } }, fmt(sc, 3))),
        el("p.small", `Higher than about ${pct(beat(view, sc))} of this scan's candidates in that view.`));
    }));
    const tk = tokens();
    const view = views[0];
    const h = d.ranking.histograms[view];
    chart(histBox, {
      grid: { left: 30, right: 10, top: 26, bottom: 22 },
      xAxis: axis("category", { data: h.all.map((_, i) => (i / d.ranking.bins).toFixed(2)), axisLabel: { color: tk.muted, interval: 9 } }),
      yAxis: axis("value", { show: false }),
      tooltip: false,
      series: [{ type: "bar", data: h.all, itemStyle: { color: tk.neutral, borderRadius: 2 }, barCategoryGap: "8%",
        markLine: { silent: true, symbol: "none", data: [{ xAxis: Math.min(d.ranking.bins - 1, Math.floor((view === "early_warning" ? ew : st) * d.ranking.bins)) }], lineStyle: { color: tk.gold, width: 3 }, label: { formatter: "yours", color: tk.ink } } }],
    });
  };
  const slider = (key, label, min, max, step, termKey) => {
    const input = el("input", { type: "range", min, max, step, value: v[key], "aria-label": label });
    const o = el("output", fmt(v[key], 2));
    input.oninput = () => { v[key] = Number(input.value); o.textContent = fmt(v[key], 2); draw(); };
    return el("div.slider", el("label", term(termKey, label)), o, input);
  };
  const typeSel = el("select", { "aria-label": "Type" }, ...TYPES.map((t) => el("option", { value: t, selected: t === v.type }, TYPE_NAMES[t])));
  typeSel.onchange = () => { v.type = typeSel.value; draw(); };
  const scopeSel = el("select", { "aria-label": "Scope" }, el("option", { value: "1" }, "Australia (1.0)"), el("option", { value: String(r.scope.factor_aggregate) }, `World or OECD (${r.scope.factor_aggregate})`), el("option", { value: String(r.scope.factor_other) }, `Another country (${r.scope.factor_other})`));
  scopeSel.onchange = () => { v.scope = Number(scopeSel.value); draw(); };
  requestAnimationFrame(draw);
  return el("div.card",
    el("div.card-head", el("div", el("h3", "Build a candidate", tip("geomean")), el("p.card-sub", "Set its components and see how it would score, and where that sits in this scan."))),
    el("div.grid.g2",
      el("div", slider("strength", "Strength", 0, 1, 0.01, "strength"), slider("novelty", "Novelty", 0.2, 1, 0.05, "novelty"), slider("lead", "Lead time", 0.2, 1, 0.05, "lead"), slider("breadth", "Breadth", 0, 1, 0.01, "breadth"),
        el("div.row-flex", el("label.field", "Type", typeSel), el("label.field", "Scope", scopeSel)),
        slider("flags", "Coverage flags", 0, 2, 1, "flag_penalty")),
      el("div", outBox, histBox, el("p.small.muted", "Try setting one component near zero: the geometric mean drags the whole score down. A chain is only as strong as its weakest link."))));
}

