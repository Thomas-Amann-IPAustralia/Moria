// Sources and limits: where the data comes from, what it can't tell you, and
// how Moria has been tested. All of it public.

import { ringTag } from "../bits.js";
import { axis, chart, chartCard, dataTable, tipHtml, tokens } from "../charts.js";
import { term, tip } from "../glossary.js";
import { state } from "../state.js";
import { css, debounce, el, fmt, longDate, n, pct, RINGS, signedPct, title, words } from "../util.js";

export function render(root) {
  const d = state.data;
  root.append(el("div.view-head", el("div",
    el("div.eyebrow", "Data and tests"),
    el("h1", "Sources and limits"),
    el("p.lede", "Where Moria's data comes from, what it can't tell you, and how Moria has been tested. Read this before leaning on anything in the other sections."))));
  root.append(el("div.section", el("h2", "What to keep in mind")), limits(d));
  root.append(el("div.section", el("h2", `The sources (${d.config.sources.length})`)), catalogue(d));
  root.append(el("div.section", el("h2", "Why so many weak signals are flagged", tip("source_break"))), volumes(d));
  root.append(el("div.mt"), ingestion(d));
  root.append(el("div.section", el("h2", "How Moria has been tested")), evals(d));
  root.append(el("div.section", el("h2", "The audit trail")), audit(d));
}

// ------------------------------------------------------------------------------------------------------ limits

function limits(d) {
  const flagsRow = d.queue.sensitivity.find((r) => r.component === "flags");
  const oa = d.queue.openalex_samples;
  const ev = d.queue.pathways.evaluation;
  const young = d.documents.sources.filter((s) => s.change == null).length;
  const L = [
    ["high", "Nobody has reviewed anything yet", "Every candidate is a question for a person, not a finding. The first review round is still to come."],
    ["high", "Nothing in the ranking weighs relevance to the IP system yet", `The free decision model was meant to judge each candidate's pathway to the IP system, but it failed its check${ev ? ` (separation ${fmt(ev.separation, 3)} against the ${ev.rule.min_separation} required)` : ""}. So some queued research topics have no evident pathway; reviewers park those.`],
    ["high", "Most sources are too new to have a baseline", `${young} document sources have no baseline yet: most began daily collection in October 2026. Their weak signals carry the source-break flag until a year or so of collection builds one.`],
    ["medium", "The flag penalties decide much of the queue's edge", flagsRow ? `Without them, ${flagsRow.size - flagsRow.overlap} of the ${flagsRow.size} places change. They are the first setting to review after the first round.` : "They are the first setting to review after the first round."],
    ["medium", "A research 'surge' can be one book or one journal", `Of ${oa.fetched} OpenAlex surges sampled, ${oa.concentrated} were concentrated in one venue. The dossier's 'concentrated works' check catches these.`],
    ["medium", "An IP class pairing can be paperwork", "Applications filed years ago and (re)classified now can look like new activity. The dossier's 'reclassified' check looks for this."],
    ["medium", "Many rings are a model's guess", `${n(d.ranking.ring_basis.zeroshot || 0)} candidates got their ring from a language model reading their label (zero-shot), not from a fixed map.`],
    ["medium", "Public, mostly English sources", "Non-English sources are absent. Some sources refuse automated access (EUIPO and JPO news, the Federal and High Courts, AustLII, CSIRO's publications): known gaps."],
    ["medium", "The hindsight test is a smoke test", "It raised all three past developments it was given, with a median lead of 2 months; but the developments were proposed by Claude, the matching is loose, and there are no non-events to count false alarms."],
    ["low", "News is titles and links only", "Moria never stores article text. A story is judged by its title and metadata."],
    ["low", "Backfilled history has no true 'first seen'", "History collected in one go can't show what was new at the time."],
    ["low", "Known-trend matches are loose", "They come from a model comparing short labels with trend statements: a tag to read, not a judgement."],
    ["low", "IP Australia's customers are hard to see in public data", "How applicants and attorneys behave shows only indirectly."],
  ];
  return el("div.limits", ...L.map(([sev, head, body]) => el("div.card.flat.limit",
    el("span.sev." + sev, sev === "high" ? "▲ Big" : sev === "medium" ? "◆ Medium" : "● Small"),
    el("div", el("strong", head), el("p.small.ink2", { style: { margin: "2px 0 0" } }, body)))));
}

// ------------------------------------------------------------------------------------------------------ sources

function catalogue(d) {
  const all = d.config.sources;
  const f = { q: "", ring: "", family: "", cadence: "" };
  const grid = el("div.src-grid");
  const more = el("div.row-flex.mt");
  let showAll = false;
  const draw = () => {
    const rows = all.filter((s) => (!f.q || `${s.id} ${s.name} ${s.coverage}`.toLowerCase().includes(f.q)) && (!f.ring || s.rings.includes(f.ring)) && (!f.family || s.family === f.family) && (!f.cadence || s.cadence === f.cadence));
    const filtered = f.q || f.ring || f.family || f.cadence;
    grid.replaceChildren(...(showAll || filtered ? rows : rows.slice(0, 9)).map(sourceCard));
    more.replaceChildren(!filtered && rows.length > 9 ? el("button.btn", { type: "button", onclick: () => { showAll = !showAll; draw(); } }, showAll ? "Show fewer" : `Show all ${rows.length} sources`) : null);
  };
  const sel = (label, key, values) => {
    const s = el("select", { "aria-label": label }, el("option", { value: "" }, `Any ${label.toLowerCase()}`), ...values.map((v) => el("option", { value: v }, typeof v === "string" ? title(v) : v)));
    s.onchange = () => { f[key] = s.value; draw(); };
    return el("label.field", label, s);
  };
  const search = el("input", { type: "search", placeholder: "Search sources…", "aria-label": "Search sources" });
  search.oninput = debounce(() => { f.q = search.value.trim().toLowerCase(); draw(); }, 150);
  draw();
  return el("div",
    el("div.card.filters", el("label.field", "Search", search), sel("Ring", "ring", RINGS), sel("Family", "family", [...new Set(all.map((s) => s.family))].sort()), sel("Cadence", "cadence", [...new Set(all.map((s) => s.cadence))].sort())),
    grid, more);
}

function sourceCard(s) {
  return el("div.card.flat.src-card",
    el("h4", s.name),
    el("div.small.muted.mono", s.id),
    el("div.row", ...s.rings.map(ringTag), el("span.tag", s.family), el("span.tag", s.cadence), el("span.tag", s.adapter)),
    el("p.small.clamp", s.coverage),
    el("details", el("summary.small", "Licence, lags and known biases"),
      el("dl.kv.small.mt",
        el("dt", "Licence"), el("dd", s.licence),
        el("dt", "What is kept"), el("dd", s.snapshot_rights),
        el("dt", "Lag"), el("dd", s.publication_lag),
        el("dt", "History from"), el("dd", s.history_start || "–"),
        s.known_biases.length ? [el("dt", "Known biases"), el("dd", el("ul", { style: { margin: 0, paddingLeft: "1.1em" } }, ...s.known_biases.map((b) => el("li", b))))] : null,
        s.breaks.length ? [el("dt", "Breaks"), el("dd", s.breaks.join("; "))] : null)));
}

// ----------------------------------------------------------------------------------------------- volumes

function volumes(d) {
  const rows = d.documents.sources.slice().sort((a, b) => (b.window_groups || 0) - (a.window_groups || 0));
  return chartCard({
    title: "Each document source's volume: the last 91 days against the 730 before",
    sub: "Items a day after merging copies. A source with no grey dot has no baseline: everything in it looks new, so its weak signals are flagged (source break). A big gap between the dots trips the coverage check.",
    render: (box) => {
      const tk = tokens();
      box.style.height = `${rows.length * 24 + 70}px`;
      chart(box, {
        grid: { left: 190, right: 90, top: 30, bottom: 30 },
        legend: { top: 0, left: 0, data: ["Baseline (730 days)", "Window (91 days)"], textStyle: { color: tk.ink2 } },
        xAxis: axis("log", { name: "items a day", nameLocation: "middle", nameGap: 22, min: 0.001 }),
        yAxis: axis("category", { data: rows.map((r) => r.source), inverse: true }),
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => { const r = rows[ps[0].dataIndex]; return tipHtml(r.source, [[tk.neutral, "baseline a day", r.baseline_per_day == null ? "none" : fmt(r.baseline_per_day, 3)], [tk.mithril, "window a day", fmt(r.window_per_day, 3)], [null, "change", r.change == null ? "no baseline" : signedPct(r.change, 0)]], `onboarded ${longDate(r.onboarded)}; history from ${r.history_from ?? "–"}`); } },
        series: [
          { name: "_link", type: "custom", renderItem: (params, api) => { const a = api.value(1), b = api.value(2); if (!(a > 0) || !(b > 0)) return null; const p1 = api.coord([a, api.value(0)]), p2 = api.coord([b, api.value(0)]); return { type: "line", shape: { x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1] }, style: { stroke: tk.axis, lineWidth: 3 } }; },
            data: rows.map((r, i) => [i, r.baseline_per_day, r.window_per_day]), encode: { x: [1, 2], y: 0 }, silent: true, tooltip: { show: false } },
          { name: "Baseline (730 days)", type: "scatter", symbolSize: 11, data: rows.map((r, i) => (r.baseline_per_day > 0 ? [r.baseline_per_day, i] : null)), itemStyle: { color: tk.neutral, borderColor: tk.surface, borderWidth: 2 } },
          { name: "Window (91 days)", type: "scatter", symbolSize: 12, data: rows.map((r, i) => (r.window_per_day > 0 ? [r.window_per_day, i] : null)), itemStyle: { color: tk.mithril, borderColor: tk.surface, borderWidth: 2 },
            label: { show: true, position: "right", color: tk.muted, fontSize: 11, formatter: (p) => { const r = rows[p.data[1]]; return r.change == null ? "no baseline" : signedPct(r.change, 0); } } },
        ],
      });
    },
    table: () => dataTable(rows, [{ label: "Source", value: (r) => r.source }, { label: "Family", value: (r) => r.family }, { label: "Onboarded", value: (r) => r.onboarded }, { label: "Window groups", value: (r) => r.window_groups, n: true }, { label: "Baseline groups", value: (r) => r.baseline_groups, n: true }, { label: "Change a day", value: (r) => (r.change == null ? "no baseline" : signedPct(r.change, 0)) }]),
  });
}

function ingestion(d) {
  const cutoff = new Date(Date.parse(d.as_of) - 30 * 864e5).toISOString().slice(0, 10);
  const days = d.ingestion.days.filter((x) => x.day >= cutoff);
  const inc = d.ingestion.incidents.length;
  const sources = [...new Set(days.map((x) => x.source))].sort();
  const dates = [...new Set(days.map((x) => x.day))].sort();
  const code = { ok: 3, below_expected: 2, above_expected: 2, gap: 1, failed: 0 };
  return chartCard({
    title: "Collection, day by day", tip: tip("ingestion"),
    sub: `Each square is a source on a day in the 30 days to the scan: did its collection pass? ${inc} ${inc === 1 ? "incident" : "incidents"} recorded. One-off and weekly sources show only on the days they ran.`,
    render: (box) => {
      const tk = tokens();
      box.style.height = `${sources.length * 18 + 90}px`;
      chart(box, {
        grid: { left: 190, right: 20, top: 10, bottom: 70 },
        xAxis: axis("category", { data: dates.map((x) => x.slice(5)), splitArea: { show: false } }),
        yAxis: axis("category", { data: sources, inverse: true }),
        visualMap: { type: "piecewise", orient: "horizontal", left: "center", bottom: 0, textStyle: { color: tk.ink2 },
          pieces: [{ value: 3, label: "Passed", color: tk.good }, { value: 2, label: "Unusual volume", color: css("--s-warn") }, { value: 1, label: "Gap", color: tk.neutral }, { value: 0, label: "Failed", color: tk.critical }] },
        tooltip: { trigger: "item", formatter: (p) => { const x = days.find((y) => y.source === sources[p.value[1]] && y.day === dates[p.value[0]]); return x ? tipHtml(`${x.source}, ${longDate(x.day)}`, [[null, "runs", n(x.runs)], [null, "failed", n(x.failed)], [null, "records", n(x.records)], [null, "status", words(x.flag)]]) : ""; } },
        series: [{ type: "heatmap", data: days.map((x) => [dates.indexOf(x.day), sources.indexOf(x.source), code[x.flag] ?? 3]), itemStyle: { borderColor: tk.surface, borderWidth: 2, borderRadius: 3 } }],
      });
    },
    table: () => dataTable(days, [{ label: "Source", value: (x) => x.source }, { label: "Day", value: (x) => x.day }, { label: "Runs", value: (x) => x.runs, n: true }, { label: "Failed", value: (x) => x.failed, n: true }, { label: "Records", value: (x) => x.records, n: true }, { label: "Status", value: (x) => words(x.flag) }]),
  });
}

// ------------------------------------------------------------------------------------------------- evaluations

function evals(d) {
  const e = d.evals;
  const out = el("div.grid.g2");
  if (e.artefacts) {
    out.append(el("div.card",
      el("h3", "Seeded artefacts: does each check catch its own trap?", tip("seeded")),
      el("p.small.ink2", `Fake problems were planted in a copy of the data. ${e.artefacts.caught} of ${e.artefacts.seeds.length} were caught by their check, and ${e.artefacts.controls_ok} of ${e.artefacts.seeds.length} genuine changes of the same size were left unflagged.`),
      el("ul.checklist", ...e.artefacts.seeds.map((s) => el("li", { style: { gridTemplateColumns: "1fr 140px 140px" } }, el("span", words(s.seed)), el("span.status." + (s.caught ? "pass" : "flag"), s.caught ? "✓ caught" : "✗ missed"), el("span.status." + (s.control_ok ? "pass" : "flag"), s.control_ok ? "✓ control clean" : "✗ control flagged"))))));
  }
  const ev = d.queue.pathways.evaluation;
  if (ev) {
    out.append(chartCard({
      title: "The decision model's check", tip: tip("separation"),
      sub: `Sentences everyone would call relevant (an AI-inventorship ruling) and irrelevant (a football result) were scored. It needed to separate them by ${ev.rule.min_separation}; it managed ${fmt(ev.separation, 3)}.`,
      actions: el("span.flag-chip", ev.passes ? "passed" : "failed"),
      render: (box) => {
        const tk = tokens();
        chart(box, {
          grid: { left: 90, right: 20, top: 16, bottom: 40 },
          xAxis: axis("value", { name: "the model's top-pathway score (0 to 1)", nameLocation: "middle", nameGap: 26, min: 0, max: 1 }),
          yAxis: axis("category", { data: ["Irrelevant", "Relevant"] }),
          tooltip: { trigger: "item", formatter: (p) => tipHtml(p.seriesName, [[p.color, "score", fmt(p.value[0], 4)]]) },
          graphic: [{ type: "text", right: 20, top: 4, style: { text: "On the full scale, relevant and irrelevant sit on top of each other.", fill: tk.muted, font: "12px Nunito" } }],
          series: [
            { name: "Relevant sentences", type: "scatter", symbolSize: 16, data: (ev.relevant || []).map((v) => [v, "Relevant"]), itemStyle: { color: tk.good, borderColor: tk.surface, borderWidth: 2 } },
            { name: "Irrelevant sentences", type: "scatter", symbolSize: 16, data: (ev.irrelevant || []).map((v) => [v, "Irrelevant"]), itemStyle: { color: tk.critical, borderColor: tk.surface, borderWidth: 2 } },
          ],
        });
      },
    }));
  }
  if (e.detectors) {
    const v = e.detectors.verdicts;
    out.append(chartCard({
      title: "New detectors: worth switching on?", tip: tip("recall"),
      sub: "Each new detector was tested on changes planted in real series. Up is more planted changes caught; right is more false alarms. Green ones passed every rule and two were switched on (D-028).",
      render: (box) => {
        const tk = tokens();
        chart(box, {
          grid: { left: 54, right: 110, top: 24, bottom: 44 },
          xAxis: axis("value", { name: "false alarm rate", nameLocation: "middle", nameGap: 28, axisLabel: { formatter: (x) => pct(x, 0) } }),
          yAxis: axis("value", { name: "recall", min: 0, max: 1, axisLabel: { formatter: (x) => pct(x, 0) } }),
          tooltip: { trigger: "item", formatter: (p) => { const x = v[p.dataIndex]; return tipHtml(words(x.detector), [[null, "recall", pct(x.recall, 1)], [null, "incremental", pct(x.incremental, 1)], [null, "false alarms", pct(x.null_rate, 1)], [null, "verdict", x.retain ? "retain" : `no (${x.failed.join(", ")})`]]); } },
          series: [{ type: "scatter", symbolSize: 16, data: v.map((x) => ({ value: [x.null_rate ?? 0, x.recall ?? 0], itemStyle: { color: x.retain ? tk.good : tk.neutral, borderColor: tk.surface, borderWidth: 2 } })),
            label: { show: true, position: "right", color: tk.ink2, fontSize: 11, formatter: (p) => words(v[p.dataIndex].detector) }, labelLayout: { moveOverlap: "shiftY" } }],
        });
      },
      table: () => dataTable(v, [{ label: "Detector", value: (x) => words(x.detector) }, { label: "Recall", value: (x) => pct(x.recall, 1) }, { label: "Incremental", value: (x) => pct(x.incremental, 1) }, { label: "False alarms", value: (x) => pct(x.null_rate, 1) }, { label: "Retain", value: (x) => (x.retain ? "yes" : `no (${x.failed.join(", ")})`) }]),
    }));
  }
  if (e.hindsight) {
    const h = e.hindsight;
    out.append(chartCard({
      title: "Hindsight: would Moria have seen it coming?", tip: tip("hindsight"),
      sub: `Moria re-run as if on past dates (term-only, no models). Each bar runs from when Moria first raised a development to when it became mainstream. Median lead: ${h.median_lead_months} months. A smoke test: the set is proposed, not yet the owner's.`,
      render: (box) => {
        const tk = tokens();
        const devs = h.developments;
        const t = (s) => Date.parse(s.length === 7 ? `${s}-01` : s);
        chart(box, {
          grid: { left: 210, right: 30, top: 16, bottom: 30 },
          xAxis: axis("time"),
          yAxis: axis("category", { data: devs.map((x) => `${x.name.length > 30 ? `${x.name.slice(0, 28)}…` : x.name}\n${x.lead_months} months ahead${x.queued ? ", queued" : ""}`), inverse: true, axisLabel: { color: tk.ink2, lineHeight: 16 } }),
          tooltip: { trigger: "item", formatter: (p) => { const x = devs[p.dataIndex]; return tipHtml(x.name, [[null, "first raised", longDate(x.first_raised)], [null, "mainstream", longDate(x.mainstream)], [null, "lead", `${x.lead_months} months`], [null, "made a queue", x.queued ? "yes" : `no (${words(x.miss)})`]]); } },
          series: [
            { type: "custom", renderItem: (params, api) => { const a = api.coord([api.value(1), api.value(0)]), b = api.coord([api.value(2), api.value(0)]); return { type: "group", children: [
              { type: "line", shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, style: { stroke: tk.mithril, lineWidth: 8, lineCap: "round", opacity: 0.35 } },
              { type: "circle", shape: { cx: a[0], cy: a[1], r: 7 }, style: { fill: tk.gold } }, { type: "circle", shape: { cx: b[0], cy: b[1], r: 7 }, style: { fill: tk.mithril } }] }; },
              data: devs.map((x, i) => [i, t(x.first_raised), t(x.mainstream)]), encode: { x: [1, 2], y: 0 } },
          ],
        });
      },
      table: () => dataTable(h.developments, [{ label: "Development", value: (x) => x.name }, { label: "First raised", value: (x) => x.first_raised }, { label: "Mainstream", value: (x) => x.mainstream }, { label: "Lead (months)", value: (x) => x.lead_months, n: true }, { label: "Queued", value: (x) => (x.queued ? "yes" : "no") }]),
    }));
  }
  return out;
}

function audit(d) {
  const rows = Object.entries(d.runs).filter(([, r]) => r);
  return el("div.card",
    el("p.small.ink2", "Every number on this dashboard comes from these runs of Moria's stages. Each run's manifest (in the private store) records its inputs, outputs with their checksums, the code's commit and the settings' hash."),
    el("div.table-wrap", el("table.data", el("thead", el("tr", el("th", "Stage"), el("th", "Run"), el("th", "Code commit"), el("th", "Uncommitted changes?"))),
      el("tbody", ...rows.map(([k, r]) => el("tr", el("td.mono", k), el("td.mono", r.run_id), el("td.mono", r.commit || "–"), el("td", r.dirty ? "yes" : "no")))))));
}

