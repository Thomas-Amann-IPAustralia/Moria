// ECharts, themed from the page's colour tokens. Every tooltip is built here from escaped text; labels from a source
// never reach a chart as HTML.

import { css, el, esc, fmt, n } from "./util.js";

/* global echarts */
const observed = new WeakMap();

export function tokens() {
  return {
    ink: css("--ink"), ink2: css("--ink-2"), muted: css("--muted"), line: css("--line"), surface: css("--surface"),
    surface2: css("--surface-2"), grid: css("--chart-grid"), axis: css("--chart-axis"), mithril: css("--mithril"),
    mithril2: css("--mithril-2"), gold: css("--gold"), good: css("--s-good"), serious: css("--s-serious"),
    critical: css("--s-critical"), neutral: css("--s-neutral"), font: "Nunito, system-ui, sans-serif",
  };
}

export function baseOption() {
  const t = tokens();
  return {
    textStyle: { fontFamily: t.font, color: t.ink2 },
    animationDuration: 700,
    animationEasing: "cubicOut",
    tooltip: {
      backgroundColor: t.surface, borderColor: t.line, borderWidth: 1, padding: [10, 12],
      textStyle: { color: t.ink, fontFamily: t.font, fontSize: 13 },
      extraCssText: "border-radius:12px;box-shadow:0 8px 24px rgba(30,20,70,.18);max-width:360px;white-space:normal;",
      confine: true,
    },
  };
}

export function axis(kind = "value", extra = {}) {
  const t = tokens();
  return {
    type: kind,
    axisLine: { show: kind !== "value", lineStyle: { color: t.axis } },
    axisTick: { show: false },
    axisLabel: { color: t.muted, fontFamily: t.font, fontSize: 12 },
    splitLine: { show: kind === "value" || kind === "log", lineStyle: { color: t.grid } },
    nameTextStyle: { color: t.muted, fontFamily: t.font, fontSize: 12 },
    ...extra,
  };
}

/** Render (or re-render) a chart into a node; resized with its container. */
export function chart(node, option) {
  let c = echarts.getInstanceByDom(node);
  if (!c) {
    c = echarts.init(node, null, { renderer: "canvas" });
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(node);
    observed.set(node, ro);
  }
  const base = baseOption();
  c.setOption({ ...base, ...option, tooltip: option.tooltip === false ? { show: false } : { ...base.tooltip, ...(option.tooltip || {}) } }, true);
  return c;
}

export function disposeAll(root) {
  for (const node of root.querySelectorAll("[_echarts_instance_]")) {
    observed.get(node)?.disconnect();
    echarts.getInstanceByDom(node)?.dispose();
  }
}

/** Tooltip HTML: a heading and rows of [colour, label, value]; every string escaped. */
export function tipHtml(head, rows = [], foot) {
  let h = head ? `<div style="font-weight:800;margin-bottom:4px">${esc(head)}</div>` : "";
  for (const [colour, label, value] of rows) {
    const key = colour ? `<span style="display:inline-block;width:14px;height:3px;border-radius:2px;background:${esc(colour)};margin-right:6px;vertical-align:middle"></span>` : "";
    h += `<div style="display:flex;justify-content:space-between;gap:14px"><span>${key}${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }
  if (foot) h += `<div style="margin-top:6px;color:${esc(tokens().muted)};font-size:12px">${esc(foot)}</div>`;
  return h;
}

/** A card holding a chart with a Chart/Table toggle (the table view is the chart's accessible twin). */
export function chartCard({ title, tip, sub, height = "", render, table, actions }) {
  const box = el(`div.chart${height ? `.${height}` : ""}`);
  const tableBox = el("div.table-wrap", { hidden: true });
  const tog = table
    ? el("div.toggle", { role: "group", "aria-label": "Show as" },
        el("button", { type: "button", "aria-pressed": "true", onclick: (e) => flip(e, false) }, "Chart"),
        el("button", { type: "button", "aria-pressed": "false", onclick: (e) => flip(e, true) }, "Table"))
    : null;
  function flip(e, showTable) {
    const [a, b] = tog.children;
    a.setAttribute("aria-pressed", String(!showTable));
    b.setAttribute("aria-pressed", String(showTable));
    box.hidden = showTable;
    tableBox.hidden = !showTable;
    if (showTable && !tableBox.firstChild) tableBox.append(table());
  }
  const card = el("div.card",
    el("div.card-head", el("div", el("h3", title, tip || null), sub ? el("p.card-sub", sub) : null), el("div.row-flex", actions || null, tog)),
    box, tableBox);
  requestAnimationFrame(() => render(box));
  return card;
}

/** A plain data table from rows and column specs {label, value(row), n: numeric, node(row)}. */
export function dataTable(rows, cols, { onRow, max } = {}) {
  const t = el("table.data");
  t.append(el("thead", el("tr", cols.map((c) => el(`th${c.n ? ".n" : ""}`, c.label)))));
  const tb = el("tbody");
  for (const r of (max ? rows.slice(0, max) : rows)) {
    const tr = el(`tr${onRow ? ".click" : ""}`, onRow ? { onclick: () => onRow(r), tabindex: 0, onkeydown: (e) => e.key === "Enter" && onRow(r) } : null);
    for (const c of cols) {
      const v = c.node ? c.node(r) : c.value(r);
      tr.append(el(`td${c.n ? ".n" : ""}`, v instanceof Node ? v : c.n && typeof v === "number" ? (Number.isInteger(v) ? n(v) : fmt(v)) : v ?? "–"));
    }
    tb.append(tr);
  }
  t.append(tb);
  return t;
}

/** A tiny inline sparkline (SVG) from values; nulls leave gaps. */
export function sparkline(values, colour, { w = 260, h = 42, mark } = {}) {
  const vals = values.map((v) => (v == null || !Number.isFinite(v) ? null : v));
  const ok = vals.filter((v) => v != null);
  const ns = "http://www.w3.org/2000/svg";
  const s = document.createElementNS(ns, "svg");
  s.setAttribute("viewBox", `0 0 ${w} ${h}`);
  s.setAttribute("class", "spark-svg");
  s.setAttribute("preserveAspectRatio", "none");
  s.setAttribute("aria-hidden", "true");
  if (ok.length < 2) return s;
  const lo = Math.min(...ok), hi = Math.max(...ok);
  const x = (i) => (i / (vals.length - 1)) * (w - 6) + 3;
  const y = (v) => (hi === lo ? h / 2 : h - 4 - ((v - lo) / (hi - lo)) * (h - 8));
  let d = "", area = "", started = false, first = null, last = null;
  vals.forEach((v, i) => {
    if (v == null) { started = false; return; }
    d += `${started ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    if (first == null) first = i;
    last = i;
    started = true;
  });
  vals.forEach((v, i) => { if (v != null) area += `${area ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; });
  area += `L${x(last).toFixed(1)},${h}L${x(first).toFixed(1)},${h}Z`;
  const a = document.createElementNS(ns, "path");
  a.setAttribute("d", area);
  a.setAttribute("fill", colour);
  a.setAttribute("opacity", "0.12");
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", d);
  p.setAttribute("fill", "none");
  p.setAttribute("stroke", colour);
  p.setAttribute("stroke-width", "2");
  p.setAttribute("stroke-linejoin", "round");
  p.setAttribute("vector-effect", "non-scaling-stroke");
  s.append(a, p);
  if (mark != null && vals[mark] != null) {
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", x(mark));
    c.setAttribute("cy", y(vals[mark]));
    c.setAttribute("r", "3.5");
    c.setAttribute("fill", colour);
    s.append(c);
  }
  return s;
}
