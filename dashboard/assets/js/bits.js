// Small visual pieces shared by the sections: the type gems, ring tags, check statuses (always an icon and a word),
// flags, and empty states.

import { tip } from "./glossary.js";
import { el, key, RING_SHORT, svg, title, TYPE_NAMES } from "./util.js";

export function gem(type, size = 22) {
  const g = svg(`<svg class="gem" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">
    <path class="g-fill" d="M6 3h12l4 6-10 12L2 9z"/><path class="g-shine" d="M6 3h5L9 9H2zM9 9h6l-3 12z" opacity=".55"/>
    <path class="g-edge" d="M6 3h12l4 6-10 12L2 9zM2 9h20M9 3 7 9l5 12 5-12-2-6"/></svg>`);
  g.style.setProperty("--gem", `var(--t-${key(type)})`);
  return g;
}

export function typeTag(type, withTip = false) {
  const t = el("span.type-tag", gem(type, 18), TYPE_NAMES[type] || title(type));
  t.style.setProperty("--gem", `var(--t-${key(type)})`);
  t.title = TYPE_NAMES[type] || title(type);
  return withTip ? el("span.row-flex", { style: { gap: "2px" } }, t, tip(type)) : t;
}

export function ringTag(ring) {
  const t = el("span.ring-tag", el("i"), RING_SHORT[ring] || title(ring));
  t.style.setProperty("--ring", `var(--r-${key(ring)})`);
  return t;
}

const ICON = {
  pass: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor" opacity=".15"/><path d="M4.5 8.3l2.2 2.2 4.8-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  flag: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5 15 14H1z" fill="currentColor" opacity=".18"/><path d="M8 6v3.5M8 11.8v.1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  na: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M5 8h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
};

export function statusBadge(outcome) {
  const k = outcome === "pass" ? "pass" : outcome === "flag" ? "flag" : "na";
  const word = k === "pass" ? "Passed" : k === "flag" ? "Flagged" : "Not applicable";
  return el(`span.status.${k}`, svg(ICON[k]), word);
}

export function flagChip(f) {
  return el("span.flag-chip", { "data-term": f, tabindex: 0 }, svg('<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><path d="M3 15V2h9l-2 3 2 3H3" fill="currentColor"/></svg>'), title(f));
}

export function arrow(direction) {
  if (direction > 0) return el("span.tag", { title: "Rising" }, "▲ rising");
  if (direction < 0) return el("span.tag", { title: "Falling" }, "▼ falling");
  return null;
}

export function sealedCard(type) {
  const c = el("div.card.sealed",
    svg('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>'),
    el("strong", TYPE_NAMES[type]), el("small", "sealed"));
  c.style.setProperty("--gem", `var(--t-${key(type)})`);
  return c;
}

export function empty(text, action) {
  return el("div.empty",
    svg('<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 58V30a18 18 0 0 1 36 0v28M6 58h52"/><path d="M32 16l2 4.6 5 .4-3.8 3.3 1.2 4.9L32 26.5l-4.4 2.7 1.2-4.9L25 21l5-.4z" fill="currentColor" opacity=".35"/></svg>'),
    el("p", text), action || null);
}

/** "Open private file" call to action for sections that need the private file. */
export function needsPrivate(what, { pickFile, loadPractice }) {
  return el("div.card.tint.mt",
    el("div.row-flex",
      el("div", { style: { flex: "1 1 360px" } },
        el("h3", "This needs the private file"),
        el("p.ink2", `${what} The public page holds counts only, because the signals' names, titles and links stay in IP Australia's private store.`)),
      el("div.row-flex",
        el("button.btn.btn-primary", { type: "button", onclick: pickFile }, "Open private file"),
        el("button.btn", { type: "button", onclick: loadPractice }, "Try practice data"))));
}
