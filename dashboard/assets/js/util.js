// Small shared helpers. Everything from a source (labels, titles, links) is untrusted: it reaches the page only
// through textContent or esc(), and a link only when it is plain http(s).

export const TYPES = ["trend", "acceleration", "weak_signal", "anomaly"]; // the validated slot order
export const RINGS = ["core", "adjacent", "wider_world"];
export const CHECKS = ["coverage", "ingestion", "duplicate", "news_cycle", "source_break", "label_drift"];

export const TYPE_NAMES = { trend: "Trend", acceleration: "Acceleration", weak_signal: "Weak signal", anomaly: "Anomaly" };
export const TYPE_GEMS = { trend: "sapphire", acceleration: "fire opal", weak_signal: "emerald", anomaly: "topaz" };
export const RING_NAMES = { core: "Core: the IP system", adjacent: "Adjacent fields", wider_world: "Wider world" };
export const RING_SHORT = { core: "Core", adjacent: "Adjacent", wider_world: "Wider world" };
export const VIEW_NAMES = { early_warning: "Early warning", strategic: "Strategic" };

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

/** Build an element: el("div.card.flat", {onclick}, child, "text", ...). Strings become text nodes (never HTML). */
export function el(spec, attrs, ...children) {
  const [tag, ...classes] = spec.split(".");
  const node = document.createElement(tag || "div");
  if (classes.length) node.className = classes.join(" ");
  if (attrs && (typeof attrs !== "object" || attrs instanceof Node || Array.isArray(attrs))) {
    children.unshift(attrs);
    attrs = null;
  }
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  append(node, children);
  return node;
}

export function append(node, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

/** Trusted static SVG markup (icons written in this code base) as a node. */
export function svg(markup) {
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  return t.content.firstChild;
}

/** A name from a file (a type, a ring) made safe for a CSS variable or class: letters and underscores only. */
export function key(s) {
  return String(s ?? "").toLowerCase().replace(/[^a-z_]/g, "");
}

export function safeUrl(u) {
  return typeof u === "string" && /^https?:\/\/[^\s<>"']+$/i.test(u) ? u : null;
}

export function link(text, url) {
  const u = safeUrl(url);
  return u ? el("a", { href: u, target: "_blank", rel: "noopener noreferrer nofollow" }, text) : el("span", text);
}

const nf = new Intl.NumberFormat("en-AU");
export function n(v) {
  return v == null || Number.isNaN(v) ? "–" : nf.format(v);
}
export function fmt(v, digits = 3) {
  if (v == null || Number.isNaN(v)) return "–";
  if (typeof v !== "number") return String(v);
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a >= 1e6) return compact(v);
  if (a >= 1000) return nf.format(Math.round(v));
  if (a >= 1) return String(+v.toPrecision(Math.max(digits, 3)));
  if (a >= 0.001) return String(+v.toPrecision(digits));
  return v.toExponential(1);
}
export function pct(v, digits = 0) {
  if (v == null || Number.isNaN(v)) return "–";
  return `${(v * 100).toFixed(digits)}%`;
}
export function signedPct(v, digits = 1) {
  if (v == null || Number.isNaN(v)) return "–";
  return `${v > 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;
}
export function pval(p) {
  if (p == null || Number.isNaN(p)) return "–";
  if (p < 0.0001) return "< 0.0001";
  if (p >= 0.995) return "1.00";
  return p < 0.01 ? p.toFixed(4) : p.toFixed(3);
}
export function compact(v) {
  return new Intl.NumberFormat("en-AU", { notation: "compact", maximumFractionDigits: 1 }).format(v);
}
export function title(s) {
  const t = String(s ?? "").replaceAll("_", " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}
export function words(s) {
  return String(s ?? "").replaceAll("_", " ");
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export function longDate(iso) {
  if (!iso) return "–";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return d ? `${d} ${MONTHS[m - 1]} ${y}` : m ? `${MONTHS[m - 1]} ${y}` : String(y);
}

/** A period label ('2026', '2026-Q3', '2026-09', '2026-09-14') as the Date its period starts. */
export function periodStart(label) {
  const s = String(label);
  if (/^\d{4}$/.test(s)) return Date.UTC(+s, 0, 1);
  let m = s.match(/^(\d{4})-Q(\d)$/);
  if (m) return Date.UTC(+m[1], (+m[2] - 1) * 3, 1);
  m = s.match(/^(\d{4})-(\d{2})$/);
  if (m) return Date.UTC(+m[1], +m[2] - 1, 1);
  m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return Date.UTC(+m[1], +m[2] - 1, +m[3]);
  return null;
}
export function periodName(label, freq) {
  const s = String(label);
  if (/^\d{4}-\d{2}$/.test(s)) return `${MONTHS[+s.slice(5, 7) - 1].slice(0, 3)} ${s.slice(0, 4)}`;
  if (/^\d{4}-Q\d$/.test(s)) return `${s.slice(5)} ${s.slice(0, 4)}`;
  return freq === "D" ? longDate(s) : s;
}
export const FREQ_NAMES = { A: "yearly", Q: "quarterly", M: "monthly", D: "daily" };

export function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
export function typeColour(t) {
  return css(`--t-${t}`) || css("--mithril");
}
export function ringColour(r) {
  return css(`--r-${r}`) || css("--mithril");
}

export function debounce(fn, ms = 200) {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}

export function countBy(items, key) {
  const out = {};
  for (const i of items) {
    const k = typeof key === "function" ? key(i) : i[key];
    out[k] = (out[k] || 0) + 1;
  }
  return out;
}

export function sum(a) {
  return a.reduce((s, v) => s + (v || 0), 0);
}

export function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

/** A seeded random number generator (mulberry32), so playgrounds can be dug again identically. */
export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function gaussian(rand) {
  let u = 0;
  while (u === 0) u = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rand());
}

export function download(name, text, type = "text/csv") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = el("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function toCsv(rows, cols) {
  const q = (v) => {
    let s = v == null ? "" : String(v);
    if (typeof v === "string" && /^[=+\-@\t\r]/.test(s)) s = `'${s}`; // a spreadsheet never runs a source's text
    return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  return [cols.map((c) => q(c.label)).join(","), ...rows.map((r) => cols.map((c) => q(c.value(r))).join(","))].join("\n");
}
