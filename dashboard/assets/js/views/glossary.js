// Level 8, the runes decoded: every term the dashboard explains, searchable, grouped.

import { GROUPS, TERMS } from "../glossary.js";
import { debounce, el } from "../util.js";

export function render(root, ctx) {
  root.append(el("div.view-head", el("div",
    el("div.eyebrow", "Runes decoded"),
    el("h1", "Glossary"),
    el("p.lede", "Every term the dashboard uses, in plain words: what it means, how Moria uses it, and what to watch out for."))));
  const search = el("input", { type: "search", placeholder: "Search the glossary…", "aria-label": "Search the glossary", style: { width: "420px" } });
  const host = el("div");
  const draw = () => {
    const q = search.value.trim().toLowerCase();
    host.replaceChildren();
    for (const [g, name] of Object.entries(GROUPS)) {
      const items = Object.entries(TERMS).filter(([, t]) => t.group === g && (!q || `${t.title} ${t.short} ${t.moria || ""}`.toLowerCase().includes(q)));
      if (!items.length) continue;
      host.append(el("div.section", el("h2", name)), el("div.gloss", ...items.map(([k, t]) => el("div.card.gloss-item", { id: `term-${k}` },
        el("h3", t.title), el("p", t.short),
        t.moria ? el("p.small.ink2", el("strong", "In Moria: "), t.moria) : null,
        t.watch ? el("p.small", { style: { color: "var(--s-serious-ink)" } }, el("strong", "Watch out: "), t.watch) : null))));
    }
    if (!host.childNodes.length) host.append(el("p.muted", "No term matches."));
  };
  search.oninput = debounce(draw, 120);
  root.append(el("div.card.filters", el("label.field", "Search", search)), host);
  draw();
  if (ctx.arg) {
    requestAnimationFrame(() => {
      const node = document.getElementById(`term-${ctx.arg}`);
      if (node) {
        node.scrollIntoView({ behavior: "smooth", block: "center" });
        node.classList.add("flash");
      }
    });
  }
}
