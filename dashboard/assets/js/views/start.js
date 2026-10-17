// Start here: what Moria is, how a signal reaches the queue, the four kinds of candidate, the three rings, the scans
// so far, and opening the private file.

import { gem } from "../bits.js";
import { axis, chart, chartCard, dataTable, tipHtml, tokens } from "../charts.js";
import { tip } from "../glossary.js";
import { loadPractice, openFile, pickFile } from "../main.js";
import { hasDetail, state } from "../state.js";
import { compact, el, longDate, n, pct, RING_NAMES, RING_SHORT, RINGS, svg, TYPE_NAMES, TYPES, typeColour } from "../util.js";

export function render(root, ctx) {
  const d = state.data;
  const f = d.funnel;
  root.append(hero(d));
  root.append(el("div.grid.g3.mt",
    caution("Nothing here is a finding yet", "No person has reviewed these candidates. Moria finds things worth a look; people decide what they mean.", "info"),
    caution("Flags are warnings, not verdicts", `${n(f.candidates - f.clean)} of ${n(f.candidates)} candidates carry an artefact flag. Flagged candidates are shown, never hidden.`, "warn"),
    caution("The machine's opinions are switched off", "The free decision model failed its check, so nothing in the ranking yet weighs relevance to the IP system.", "warn")));
  root.append(el("div.section", el("h2", "How a signal reaches the queue", tip("candidate"))),
    el("p.lede", "Every week Moria tests tens of thousands of documents and series and passes a handful to a person. Click a stage to see what happens there, and what can go wrong."),
    shaft(f, ctx));
  root.append(el("div.section", el("h2", "Four kinds of candidate")),
    el("p.lede", "Each candidate is one of four types, each found in a different way and each worth a different kind of look."),
    types(d, ctx));
  root.append(el("div.grid.g2.mt", rings(d), historyCard(d)));
  root.append(el("div.section", el("h2", hasDetail() ? "Your private file is open" : "Open your private file")), doors(ctx));
  root.append(el("div.section", el("h2", "How to use this dashboard")), guide());
}

function hero(d) {
  const art = svg(`<svg class="hero-door" viewBox="0 0 320 300" aria-hidden="true">
    <defs><radialGradient id="hg" cx="50%" cy="38%" r="55%"><stop offset="0" stop-color="#f2b134" stop-opacity=".55"/><stop offset="1" stop-color="#f2b134" stop-opacity="0"/></radialGradient></defs>
    <circle cx="160" cy="120" r="120" fill="url(#hg)"/>
    <path d="M60 290V130a100 100 0 0 1 200 0v160" fill="none" stroke="#c9c1ff" stroke-width="5" stroke-linecap="round"/>
    <path d="M80 290V132a80 80 0 0 1 160 0v158M160 290V52" fill="none" stroke="#8d7ff0" stroke-width="2" opacity=".7"/>
    <g fill="#f2b134" opacity=".8"><circle cx="40" cy="60" r="1.6"/><circle cx="290" cy="40" r="1.3"/><circle cx="270" cy="200" r="1.4"/><circle cx="30" cy="190" r="1.2"/><circle cx="300" cy="120" r="1"/></g>
  </svg>`);
  return el("section.hero",
    el("div",
      el("div.eyebrow", "IP Australia's signal-detection engine"),
      el("h1", "What has Moria found?"),
      el("p.lede", `Moria scans public data for early signs of change that could reach Australia's IP system over the next ten years. This is the scan of ${longDate(d.as_of)}: what it found, how it got there, and how far to trust it.`),
      el("div.hero-actions",
        el("a.btn.btn-gold", { href: "#/queue" }, "See the review queue"),
        hasDetail() ? null : el("button.btn.btn-ghost", { type: "button", onclick: pickFile }, "Open private file"),
        state.mode === "public" ? el("button.btn.btn-ghost", { type: "button", onclick: loadPractice }, "Try practice data") : null)),
    art);
}

function caution(head, body, kind) {
  return el(`div.callout.${kind}`, el("div.c-ico", kind === "info" ? "✦" : "⚑"), el("div", el("h4", head), el("p.small", body)));
}

// ------------------------------------------------------------------------------------------------ the stages

const SHAFT = [
  { key: "sources", name: "1. Sources", go: "records",
    what: "Moria collects from public sources every day or week: global news (GDELT), Commonwealth legislation, IP Australia's site and open data (IP RAPID), peer IP offices, WIPO, the OECD, the ABS, research counts (OpenAlex), patent counts, Parliament's committee feeds, think tanks and more.",
    watch: "Public data only, and mostly in English. Many sources only began daily collection in October 2026. Some refuse automated access (EUIPO, JPO, the courts) and are known gaps." },
  { key: "evidence", name: "2. Evidence", go: "records",
    what: "Every item is cleaned, dated by when Moria could first have seen it, swept for anything suspicious, de-duplicated, tagged and indexed. Series are lined up period by period, each value as it was known at the time.",
    watch: "History collected in one go (backfill) has no true 'first seen' date. News is kept as titles and links only, never the article text." },
  { key: "candidates", name: "3. Detectors", go: "candidates",
    what: "Detectors test every series for trends, accelerations, anomalies and surges, and the last 91 days of documents for new terms, new pairings and sudden rises. Each test allows for the thousands of others (Holm's adjustment). Six artefact checks then flag candidates that might come from how the data was collected.",
    watch: "About one candidate in six carries a flag. Most weak signals are flagged because their sources are too new to have a baseline." },
  { key: "shortlist", name: "4. Ranking", go: "ranking",
    what: "Every candidate is scored for two views, early warning and strategic, then 100 are shortlisted under ring quotas. Each gets an evidence dossier and the decision model's suggestions.",
    watch: "Nothing in the ranking yet weighs relevance to the IP system: the decision model failed its check. The flag penalties decide much of the queue's edge." },
  { key: "queue", name: "5. The queue", go: "queue",
    what: "The 40 most worth a person's time, picked from the shortlist: about a third from each ring, half by each view, no more than a quarter from one source, and one per group of series that move together.",
    watch: "Some research topics with no evident path to the IP system made the queue; reviewers park those." },
  { key: "reviewed", name: "6. People", go: "queue",
    what: "A reviewer reads each dossier and decides: investigate, validate, reject or park, with reasons. Validated signals then feed PESTLE, SWOT and the Futures Cone.",
    watch: "No review has happened yet: none of these candidates is a finding." },
];

function shaft(f, ctx) {
  const num0 = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0); // a file's counts are numbers, never markup
  const counts = { sources: num0(f.sources), evidence: num0(f.documents) + num0(f.series), candidates: num0(f.candidates), shortlist: num0(f.shortlist), queue: num0(f.queue), reviewed: num0(f.reviewed) };
  const sub = {
    sources: "public sources", evidence: `${compact(f.documents)} documents · ${compact(f.series)} series tested`,
    candidates: `candidates (${n(f.clean)} with no flag)`, shortlist: "shortlisted, each with a dossier", queue: "in the review queue", reviewed: "reviewed by a person",
  };
  const W = 620, top = 26, gap = 14, h = 62;
  const max = Math.log10(Math.max(...Object.values(counts)) + 1);
  const ns = "http://www.w3.org/2000/svg";
  const s = document.createElementNS(ns, "svg");
  s.setAttribute("viewBox", `0 0 ${W} ${top + SHAFT.length * (h + gap) + 10}`);
  s.setAttribute("class", "shaft-svg");
  s.setAttribute("role", "list");
  const fills = ["#8a7a63", "#7a6a8f", "#6a5bc6", "#5b4bd6", "#c48a12", "#1baf7a"];
  const detail = el("div.card.shaft-detail");
  const pick = (i) => {
    s.querySelectorAll(".shaft-level").forEach((g, k) => g.classList.toggle("active", k === i));
    const L = SHAFT[i];
    detail.replaceChildren(
      el("div.eyebrow", `${n(counts[L.key])} ${sub[L.key]}`),
      el("h3", L.name),
      el("p", L.what),
      el("div.callout.warn", el("div.c-ico", "⚑"), el("div", el("h4", "What can go wrong here"), el("p.small", L.watch))),
      el("button.btn.mt", { type: "button", onclick: () => ctx.go(L.go) }, "Go to this section →"));
  };
  // the stages and the marker at the queue
  const line = document.createElementNS(ns, "path");
  line.setAttribute("d", `M18 8V${top + SHAFT.length * (h + gap)}`);
  line.setAttribute("stroke", "var(--line-strong)");
  line.setAttribute("stroke-width", "3");
  line.setAttribute("stroke-dasharray", "1 7");
  line.setAttribute("stroke-linecap", "round");
  s.append(line);
  SHAFT.forEach((L, i) => {
    const c = counts[L.key];
    const w = 140 + (W - 220) * (Math.log10(c + 1) / max);
    const x = 40 + (W - 40 - w) / 2;
    const y = top + i * (h + gap);
    const g = document.createElementNS(ns, "g");
    g.setAttribute("class", "shaft-level");
    g.setAttribute("role", "listitem");
    g.setAttribute("tabindex", "0");
    g.setAttribute("aria-label", `${L.name}: ${c} ${sub[L.key]}`);
    g.innerHTML = `<rect class="band" x="${x}" y="${y}" width="${w}" height="${h}" rx="16" fill="${fills[i]}"/>
      <text x="${x + w / 2}" y="${y + 28}" text-anchor="middle" font-family="Fredoka, sans-serif" font-size="22" font-weight="600" fill="#fff">${c.toLocaleString("en-AU")}</text>
      <text x="${x + w / 2}" y="${y + 48}" text-anchor="middle" font-family="Nunito, sans-serif" font-size="12.5" font-weight="700" fill="#fff" opacity=".9"></text>
      <circle cx="18" cy="${y + h / 2}" r="5" fill="var(--surface)" stroke="${fills[i]}" stroke-width="3"/>`;
    g.querySelectorAll("text")[1].textContent = sub[L.key]; // set as text, never markup
    g.addEventListener("click", () => pick(i));
    g.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), pick(i)));
    s.append(g);
  });
  const lantern = document.createElementNS(ns, "g");
  lantern.setAttribute("class", "lantern-dot");
  lantern.innerHTML = `<circle cx="18" cy="${top + 4 * (h + gap) + h / 2}" r="11" fill="#f2b134" opacity=".35"/><circle cx="18" cy="${top + 4 * (h + gap) + h / 2}" r="6" fill="#f2b134"/>`;
  s.append(lantern);
  requestAnimationFrame(() => pick(4));
  return el("div.shaft", el("div.card", s), detail);
}

// ------------------------------------------------------------------------------------------------- the types

const TYPE_LINES = {
  trend: "Steady change in one direction over years.",
  acceleration: "A trend that is speeding up.",
  weak_signal: "Something new and small in documents or IP filings.",
  anomaly: "A value far outside what was expected.",
};

function types(d, ctx) {
  const t = d.scan.types;
  return el("div.stats", ...TYPES.map((k) => {
    const c = el("div.card.stat.click", {
      tabindex: 0, role: "button",
      onclick: () => { state.filter = { type: k }; ctx.go("candidates"); },
      onkeydown: (e) => e.key === "Enter" && (state.filter = { type: k }, ctx.go("candidates")),
    },
      el("div.stat-label", gem(k), TYPE_NAMES[k], tip(k)),
      el("div.stat-value", n(t[k]?.candidates ?? 0)),
      el("p.stat-note", TYPE_LINES[k]),
      el("p.stat-note", `${n(t[k]?.clean ?? 0)} with no flag (${pct((t[k]?.clean ?? 0) / Math.max(1, t[k]?.candidates ?? 1))}) · ${n(d.queue.types[k] ?? 0)} in the queue`));
    c.style.borderTop = `4px solid ${typeColour(k)}`;
    return c;
  }));
}

// ------------------------------------------------------------------------------------------------- the rings

function rings(d) {
  const q = d.queue.quotas;
  const all = d.ranking.rings;
  const ns = "http://www.w3.org/2000/svg";
  const s = document.createElementNS(ns, "svg");
  s.setAttribute("viewBox", "10 10 280 280");
  s.setAttribute("class", "rings-svg");
  const info = el("p.small.ink2", "Hover a ring.");
  const R = { wider_world: 136, adjacent: 96, core: 54 };
  const blurb = {
    core: "The IP system itself: patents, trade marks, designs, plant breeder's rights, IP Australia and its customers.",
    adjacent: "Fields that feed or use IP: science, technology, industry, trade, research.",
    wider_world: "Society, the economy, the environment and politics: the forces that shape everything else.",
  };
  for (const r of ["wider_world", "adjacent", "core"]) {
    const g = document.createElementNS(ns, "g");
    g.setAttribute("tabindex", "0");
    g.innerHTML = `<circle class="ring" cx="150" cy="150" r="${R[r]}" fill="var(--r-${r})" fill-opacity="${r === "core" ? 0.9 : r === "adjacent" ? 0.55 : 0.3}" stroke="var(--surface)" stroke-width="3"/>`;
    const enter = () => info.replaceChildren(el("strong", RING_NAMES[r]), `: ${blurb[r]} ${n(all[r] ?? 0)} candidates; ${q[r]?.filled ?? 0} of ${q[r]?.cap ?? 0} queue places filled.`);
    g.addEventListener("pointerenter", enter);
    g.addEventListener("focus", enter);
    s.append(g);
  }
  const labels = [["core", 150, 155], ["adjacent", 150, 76], ["wider_world", 150, 36]];
  for (const [r, x, y] of labels) {
    const t = document.createElementNS(ns, "text");
    t.setAttribute("x", x);
    t.setAttribute("y", y);
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("font-family", "Fredoka, sans-serif");
    t.setAttribute("font-weight", "600");
    t.setAttribute("font-size", r === "core" ? "15" : "13");
    t.setAttribute("fill", r === "core" ? "#fff" : "var(--ink)");
    t.setAttribute("pointer-events", "none");
    t.textContent = RING_SHORT[r];
    s.append(t);
  }
  // the queue's fill beside the rings
  const bars = el("div.bars-mini", ...RINGS.map((r) => el("div.bar-mini",
    el("span", RING_SHORT[r]),
    (() => { const m = el("div.meter", el("i")); m.firstChild.style.width = `${((q[r]?.filled ?? 0) / Math.max(1, q[r]?.cap ?? 1)) * 100}%`; m.firstChild.style.background = `var(--r-${r})`; return m; })(),
    el("span.num", `${q[r]?.filled ?? 0} / ${q[r]?.cap ?? 0}`))));
  return el("div.card",
    el("div.card-head", el("div", el("h3", "Three rings around the IP system", tip("ring")), el("p.card-sub", "The closer to the centre, the more directly a change touches the IP system. The queue keeps a quota for each ring."))),
    el("div.grid", { style: { gridTemplateColumns: "1.1fr 1fr", alignItems: "center" } }, s, el("div", info, el("h4.mt", "Queue places by ring", tip("quota")), bars)));
}

// ------------------------------------------------------------------------------------------------- the scans

function historyCard(d) {
  const h = d.history || [];
  return chartCard({
    title: "Scans so far",
    sub: `Candidates found by each scan, by type. Each weekly scan adds a point; ${h.length === 1 ? "there is one so far" : `there are ${h.length} so far`}.`,
    render: (box) => {
      const tk = tokens();
      chart(box, {
        grid: { left: 54, right: 20, top: 36, bottom: 30 },
        legend: { top: 0, left: 0, textStyle: { color: tk.ink2 }, icon: "roundRect", itemWidth: 14, itemHeight: 4 },
        xAxis: axis("category", { data: h.map((x) => x.as_of.slice(5)), boundaryGap: false, name: "scan (month-day)", nameLocation: "middle", nameGap: 24 }),
        yAxis: axis("value"),
        tooltip: { trigger: "axis", formatter: (ps) => tipHtml(ps[0].name, ps.map((p) => [p.color, p.seriesName, n(p.value)])) },
        series: TYPES.map((t) => ({ name: TYPE_NAMES[t], type: "line", data: h.map((x) => x.types?.[t] ?? 0), symbolSize: 9, lineStyle: { width: 2, color: typeColour(t) }, itemStyle: { color: typeColour(t), borderColor: tk.surface, borderWidth: 2 } })),
      });
    },
    table: () => dataTable(h, [{ label: "Scan", value: (x) => longDate(x.as_of) }, ...TYPES.map((t) => ({ label: TYPE_NAMES[t], value: (x) => x.types?.[t] ?? 0, n: true })), { label: "With no flag", value: (x) => x.clean, n: true }, { label: "Queue", value: (x) => x.queue, n: true }]),
  });
}

// ---------------------------------------------------------------------------------------------- the private file

function doorsArt() {
  return svg(`<svg class="doors-art" viewBox="0 0 220 240" aria-hidden="true">
    <circle class="glow" cx="110" cy="140" r="90"/>
    <path class="arch" d="M30 236V110a80 80 0 0 1 160 0v126"/>
    <path class="leaf-l" d="M40 232V112a70 70 0 0 1 70-70v190z"/>
    <path class="leaf-r" d="M180 232V112a70 70 0 0 0-70-70v190z"/>
  </svg>`);
}

function doors(ctx) {
  const art = doorsArt();
  if (hasDetail()) {
    const c = el("div.card.doors.open", art, el("div",
      el("p.inscription", state.mode === "practice" ? "Practice data is open." : "Your private file is open."),
      el("p", state.mode === "practice"
        ? "You're exploring invented practice data. Every section now shows signals, evidence and charts, all made up."
        : `Your private file (${state.fileName}) is open in this tab only. Every section now shows the signals themselves: names, evidence, series and dossiers. Nothing has been uploaded anywhere; closing the tab forgets it.`),
      el("div.row-flex", el("a.btn.btn-primary", { href: "#/queue" }, "See the 40 in the queue"), el("a.btn", { href: "#/candidates" }, "Explore every candidate"))));
    return c;
  }
  const input = el("button.btn.btn-primary", { type: "button", onclick: pickFile }, "Choose the file…");
  const zone = el("div.dropzone",
    el("p", el("strong", "Drop your private file here"), " (dashboard.json.gz), or ", input),
    el("p.small.muted", "It is read by this browser tab and nothing else: this page cannot send data anywhere, and closing the tab forgets it."));
  zone.addEventListener("drop", (e) => { e.preventDefault(); openFile(e.dataTransfer?.files?.[0]); });
  return el("div.card.doors", art, el("div",
    el("p", "The signals themselves (their names, the documents behind them, their series and dossiers) are private to IP Australia, so this public page shows counts only. If you have access to Moria's private store, open this week's file:"),
    el("ol.steps",
      el("li", "Sign in to Cloudflare and open ", el("strong", "R2"), ", then the bucket ", el("strong", "moria"), "."),
      el("li", "Open ", el("code", "interpretation/dashboard/"), ", then the newest ", el("code", "as_of=…"), " folder, and download ", el("code", "dashboard.json.gz"), "."),
      el("li", "Drop it below, or choose it. (Or, from a terminal: ", el("code", "uv run moria dashboard --out ~/moria-dashboard.json.gz --store r2"), ".)")),
    zone,
    el("p.small.muted.mt", "No access? ", el("button.btn.btn-small", { type: "button", onclick: loadPractice }, "Explore the practice data"), " (invented, to learn the dashboard).")));
}

function guide() {
  const items = [
    ["Hover anything dotted", "A dotted underline or a small ? means there's an explainer. Numbers explain themselves: hover a p-value to read what that particular value means."],
    ["Go deeper section by section", "The sections on the left go from the overview down to the methods and sources. Each starts simple; open cards and drawers for more."],
    ["Click a candidate", "Any candidate opens a drawer with its evidence, its numbers, the alternative explanations Moria checked, and why it ranked where it did."],
    ["Try the what-if", "Change the ranking's weights and watch the queue change. It's a what-if: Moria itself is never changed."],
    ["Charts have tables", "Most charts have a Table switch, for exact numbers and for screen readers."],
    ["Light or dark", "The lantern at the top right switches between light and dark mode."],
  ];
  return el("div.grid.g3", ...items.map(([h, p]) => el("div.card.flat", el("h4", h), el("p.small.ink2", p))));
}

