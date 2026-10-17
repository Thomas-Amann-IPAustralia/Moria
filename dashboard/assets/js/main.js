// The app shell: the sections (navigation), the data modes (public, practice, private), opening a private file in
// this tab, the light and dark switch, and a little polish.

import { disposeAll } from "./charts.js";
import { closeDrawer, openCandidate } from "./dossier.js";
import { initPopover } from "./glossary.js";
import { fetchJson, readBundle, setData, state } from "./state.js";
import { el, longDate, svg } from "./util.js";
import * as candidates from "./views/candidates.js";
import * as glossary from "./views/glossary.js";
import * as queue from "./views/queue.js";
import * as ranking from "./views/ranking.js";
import * as records from "./views/records.js";
import * as start from "./views/start.js";
import * as statistics from "./views/statistics.js";
import * as time from "./views/time.js";

const ICONS = {
  door: '<svg viewBox="0 0 24 24"><path d="M5 21V10a7 7 0 0 1 14 0v11M3 21h18M12 3v18M9.5 8.5l2.5-2 2.5 2"/></svg>',
  gem: '<svg viewBox="0 0 24 24"><path d="M6 3h12l4 6-10 12L2 9zM2 9h20M9 3 7 9l5 12 5-12-2-6"/></svg>',
  pick: '<svg viewBox="0 0 24 24"><path d="M14 10 4 20M17 4c-3 0-6 1-8 3 3-.5 6 0 9 2 2 3 2.5 6 2 9 2-2 3-5 3-8"/></svg>',
  mirror: '<svg viewBox="0 0 24 24"><path d="M3 15c2-2 4-2 6 0s4 2 6 0 4-2 6 0M3 19c2-2 4-2 6 0s4 2 6 0 4-2 6 0M12 3l1 2.5 2.5.3-1.9 1.7.6 2.5-2.2-1.3-2.2 1.3.6-2.5L8.5 5.8 11 5.5z"/></svg>',
  anvil: '<svg viewBox="0 0 24 24"><path d="M3 8h13a5 5 0 0 0 5-5v0M5 8c0 3 2 5 5 5h2c3 0 4-2 4-5M9 13l-2 6h10l-2-6M5 19h14"/></svg>',
  scroll: '<svg viewBox="0 0 24 24"><path d="M7 3h11a2 2 0 0 1 2 2v1h-4M7 3a2 2 0 0 0-2 2v12a2 2 0 0 1-2 2h11a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2M8 8h5M8 12h5"/></svg>',
  book: '<svg viewBox="0 0 24 24"><path d="M4 4h6a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4zM20 4h-6a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h6zM7 8h2M15 8h2"/></svg>',
  glossary: '<svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h11M4 18h14M19 12h1"/></svg>',
};

const LEVELS = [
  { id: "start", name: "Start here", sub: "What Moria is", icon: "door", view: start },
  { id: "queue", name: "The review queue", sub: "The 40 for review", icon: "gem", view: queue },
  { id: "candidates", name: "All candidates", sub: "Everything raised", icon: "pick", view: candidates },
  { id: "time", name: "Change over time", sub: "Series and fits", icon: "mirror", view: time },
  { id: "ranking", name: "How ranking works", sub: "Scores and a what-if", icon: "anvil", view: ranking },
  { id: "statistics", name: "Statistics explained", sub: "Playgrounds", icon: "scroll", view: statistics },
  { id: "records", name: "Sources and limits", sub: "Data and tests", icon: "book", view: records },
  { id: "glossary", name: "Glossary", sub: "Every term", icon: "glossary", view: glossary },
];
const OLD_ROUTES = { forge: "ranking", lore: "statistics" }; // links from before the sections were renamed

const main = document.getElementById("main");
let currentView = null;

// ------------------------------------------------------------------------------------------------- navigation

function buildNav() {
  const nav = document.getElementById("nav");
  LEVELS.forEach((l, i) => {
    nav.append(el("li", el("a", { href: `#/${l.id}`, "data-level": l.id, title: `${i + 1}. ${l.name}: ${l.sub}` },
      el("span.lvl-ico", svg(ICONS[l.icon])),
      el("span.lvl-text", el("span.lvl-name", l.name), el("span.lvl-sub", l.sub)))));
  });
}

export function go(route) {
  location.hash = `#/${route}`;
}

function parse() {
  const h = location.hash.replace(/^#\/?/, "");
  const [given, ...rest] = h.split("/");
  const name = OLD_ROUTES[given] || given;
  return { name: LEVELS.some((l) => l.id === name) ? name : "start", arg: rest.join("/") || null };
}

function render() {
  const { name, arg } = parse();
  const level = LEVELS.find((l) => l.id === name);
  document.querySelectorAll(".levels a").forEach((a) => a.toggleAttribute("aria-current", false));
  const a = document.querySelector(`.levels a[data-level="${name}"]`);
  if (a) a.setAttribute("aria-current", "page");
  const i = LEVELS.indexOf(level);
  const dot = document.getElementById("depth-dot");
  dot.style.left = `calc(${(i / (LEVELS.length - 1)) * 100}% - 6px)`;
  disposeAll(main);
  main.replaceChildren();
  const root = el("div.view");
  main.append(root);
  currentView = name;
  try {
    level.view.render(root, { go, open: openCandidate, arg, rerender: render });
  } catch (e) {
    console.error(e);
    root.append(el("div.card", el("h3", "Something went wrong drawing this section"), el("p.muted", String(e.message || e))));
  }
  document.title = `${level.name} · Moria dashboard`;
}

window.addEventListener("hashchange", () => {
  closeDrawer();
  render();
  main.focus({ preventScroll: true });
  window.scrollTo({ top: 0 });
});

// ------------------------------------------------------------------------------------------------------ modes

function updateChrome() {
  const d = state.data;
  const chip = document.getElementById("scan-chip");
  chip.replaceChildren(el("span.dot"), `Scan of ${longDate(d.as_of)}`);
  const mode = document.getElementById("mode-chip");
  const banner = document.getElementById("banner");
  const rail = document.getElementById("rail-mode");
  const practice = document.getElementById("btn-practice");
  mode.hidden = state.mode === "public";
  mode.className = `chip chip-mode ${state.mode}`;
  banner.className = `banner ${state.mode}`;
  banner.hidden = false;
  if (state.mode === "public") {
    rail.textContent = "Public view: counts only";
    practice.hidden = false;
    banner.replaceChildren(
      svg('<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>'),
      el("span", "Public view: counts only. The signals themselves (their names, evidence and charts) stay private. Open your private file to see them, or try the practice data."),
      el("button.btn.btn-small", { type: "button", onclick: () => pickFile() }, "Open private file"));
  } else if (state.mode === "practice") {
    rail.textContent = "Practice data: invented";
    practice.hidden = true;
    mode.replaceChildren(el("span.dot"), "Practice data");
    banner.replaceChildren(
      el("strong", "Practice data."),
      el("span", "Every signal, chart, title and dossier here is invented, to show how the dashboard works: none of it is a finding. Only what's about Moria itself (its sources, settings and self-tests, in Sources and limits) is real."),
      el("button.btn.btn-small", { type: "button", onclick: () => backToPublic() }, "Back to the real scan"));
  } else {
    rail.textContent = "Private file open in this tab";
    practice.hidden = true;
    mode.replaceChildren(el("span.dot"), "Private file open");
    banner.replaceChildren(
      el("strong", "Your private file is open in this tab only."),
      el("span", `Nothing is uploaded, and closing the tab forgets it. ${state.data.as_of !== state.pub?.as_of ? "(It is for a different scan from the public page's.)" : ""}`),
      el("button.btn.btn-small", { type: "button", onclick: () => backToPublic() }, "Close the file"));
  }
}

function backToPublic() {
  setData(state.pub, "public");
  updateChrome();
  render();
  toast("Back to the public counts.");
}

export async function loadPractice() {
  try {
    const b = await fetchJson("data/practice.json");
    setData(b, "practice");
    updateChrome();
    render();
    toast("Practice data loaded. Everything here is invented.");
  } catch (e) {
    toast(`The practice data couldn't be loaded (${e.message}).`, true);
  }
}

export function pickFile() {
  document.getElementById("file-input").click();
}

export async function openFile(file) {
  if (!file) return;
  try {
    const b = await readBundle(file);
    setData(b, "private", file.name);
    document.querySelectorAll(".doors").forEach((d) => d.classList.add("open"));
    await new Promise((r) => setTimeout(r, matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 900));
    updateChrome();
    render();
    toast(`Private file opened: ${b.candidates.length.toLocaleString("en-AU")} candidates from the scan of ${longDate(b.as_of)}.`);
  } catch (e) {
    toast(e.message || String(e), true);
  }
}

// ----------------------------------------------------------------------------------------------- the little things

export function toast(text, err = false) {
  const t = el(`div.toast${err ? ".err" : ""}`, el("span", err ? "⚠" : "✦"), el("span", text));
  document.getElementById("toasts").append(t);
  setTimeout(() => t.remove(), err ? 7000 : 4200);
}

function sparkle(e) {
  const b = e.target.closest(".btn, .pill");
  if (!b || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const r = b.getBoundingClientRect();
  for (let i = 0; i < 6; i++) {
    const s = el("span.spark");
    const ang = (Math.PI * 2 * i) / 6 + Math.random();
    s.style.left = `${e.clientX - r.left - 4}px`;
    s.style.top = `${e.clientY - r.top - 4}px`;
    s.style.setProperty("--dx", `${Math.cos(ang) * 28}px`);
    s.style.setProperty("--dy", `${Math.sin(ang) * 28}px`);
    if (b.classList.contains("btn")) {
      b.append(s);
      setTimeout(() => s.remove(), 650);
    }
  }
}

function theme(next) {
  const root = document.documentElement;
  const t = next || (root.dataset.theme === "dark" ? "light" : "dark");
  root.dataset.theme = t;
  try {
    localStorage.setItem("moria-theme", t);
  } catch {
    /* private window: the choice lasts this visit */
  }
}

function dropAnywhere() {
  let depth = 0;
  document.addEventListener("dragenter", (e) => {
    if (![...(e.dataTransfer?.types || [])].includes("Files")) return;
    depth += 1;
    document.querySelectorAll(".dropzone").forEach((z) => z.classList.add("over"));
  });
  document.addEventListener("dragleave", () => {
    depth = Math.max(0, depth - 1);
    if (!depth) document.querySelectorAll(".dropzone").forEach((z) => z.classList.remove("over"));
  });
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", (e) => {
    e.preventDefault();
    depth = 0;
    document.querySelectorAll(".dropzone").forEach((z) => z.classList.remove("over"));
    const f = e.dataTransfer?.files?.[0];
    if (f) openFile(f);
  });
}

// ----------------------------------------------------------------------------------------------------- start up

async function boot() {
  let saved = null;
  try {
    saved = localStorage.getItem("moria-theme");
  } catch {
    /* no storage: follow the system */
  }
  theme(saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  buildNav();
  initPopover();
  dropAnywhere();
  document.addEventListener("click", sparkle);
  document.getElementById("btn-theme").addEventListener("click", () => {
    theme();
    render();
  });
  document.getElementById("btn-doors").addEventListener("click", pickFile);
  document.getElementById("btn-practice").addEventListener("click", loadPractice);
  document.getElementById("file-input").addEventListener("change", (e) => {
    openFile(e.target.files?.[0]);
    e.target.value = "";
  });
  main.replaceChildren(el("div.loading", svg('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 1v3M9 4h6l2 4v9l-2 3H9l-2-3V8z"/><path d="M12 10c1.4 1.4 2 2.5 2 3.5a2 2 0 0 1-4 0c0-1 .6-2.1 2-3.5z" fill="#f2b134" stroke="none"/></svg>'), "Loading the scan…"));
  try {
    state.pub = await fetchJson("data/public.json");
  } catch (e) {
    main.replaceChildren(el("div.card", el("h2", "The scan's data couldn't be loaded"),
      el("p", "The public data file (data/public.json) is missing or unreadable. If you opened this page from your own disk, open it through a web server instead (GitHub Pages does this)."),
      el("p.muted", String(e.message || e))));
    return;
  }
  setData(state.pub, "public");
  updateChrome();
  render();
}

boot();
