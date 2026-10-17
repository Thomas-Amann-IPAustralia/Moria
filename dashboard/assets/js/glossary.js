// The explainers behind every dotted term and every "?" on the page. Each entry: a title, a short plain-language
// definition, how Moria uses it, what to watch out for, and (for numbers) a reading of the value being hovered.

import { el, esc, fmt, pct, pval } from "./util.js";

const oneIn = (p) => (p > 0 ? `about 1 time in ${fmt(Math.max(1, Math.round(1 / p)))}` : "almost never");

export const GROUPS = {
  signals: "Signals and what they mean",
  stats: "Statistics",
  ranking: "Ranking and the queue",
  checks: "Checks and flags",
  evidence: "Evidence and sources",
  machine: "The decision model",
  eval: "Testing Moria itself",
};

export const TERMS = {
  // ------------------------------------------------------------------------------------------------ signals
  candidate: {
    title: "Candidate", group: "signals",
    short: "Something a detector noticed: a series or a group of documents that changed in a way worth a look.",
    moria: "Every scan turns tens of thousands of series and documents into a few thousand candidates. Each has an id that stays the same from scan to scan, so its history can be followed.",
    watch: "A candidate is not yet a signal. Only a person can validate it.",
  },
  signal: {
    title: "Signal", group: "signals",
    short: "A candidate that a person has reviewed and judged to be a real, relevant sign of change.",
    moria: "No candidate has been validated yet: the first review round is still to come.",
  },
  trend: {
    title: "Trend (sapphire)", group: "signals",
    short: "Steady change in one direction over years, not just a blip.",
    moria: "A series is a trend when its slope is significant, after Holm's adjustment, in at least 2 of its 3 windows (for monthly data: the last 12, 24 and 36 months), all in the same direction.",
    watch: "Trends are the most reliable kind but also the least new: many are things people already know about.",
  },
  acceleration: {
    title: "Acceleration (fire opal)", group: "signals",
    short: "A trend that is speeding up: the recent slope is steeper than the earlier one.",
    moria: "Either the recent half of the longest window rises faster than the earlier half (a bootstrap test, Holm-adjusted), or a change point to a steeper slope falls on a significant trend. The change must also be material: at least 0.10 a year in the growth rate.",
    watch: "A one-off jump near the end of a window can look like an acceleration. Check the chart.",
  },
  weak_signal: {
    title: "Weak signal (emerald)", group: "signals",
    short: "Something new and small: a new term, a new pairing of ideas or classes, or a sudden rise from almost nothing.",
    moria: "Found in documents (news, policy, legal, research) and in IP RAPID's class pairs. It needs at least 3 separate items (after de-duplication) from at least 2 sources.",
    watch: "Most weak signals are noise. Many sources only started being collected in October 2026, so a 'new' term may simply be new to Moria (the source-break flag says so).",
  },
  anomaly: {
    title: "Anomaly (topaz)", group: "signals",
    short: "A value far outside what the series' own recent past predicted.",
    moria: "The latest value is compared with a band fitted on the periods before it (a 99% band, adjusted for the many series tested), and must also be at least 25% off its expected value.",
    watch: "An anomaly triggers investigation; it is not yet a signal. Moria's own tests found anomalies are weak evidence, so they rank at half weight.",
  },
  ring: {
    title: "Rings", group: "signals",
    short: "How close a change is to the IP system: core (the IP system itself), adjacent fields (science, technology, industry, trade) and the wider world (society, economy, environment, politics).",
    moria: "Each candidate gets one ring, from its source card, its label or its evidence. The review queue keeps quotas: 35% core, 35% adjacent, 30% wider world.",
    watch: "Many rings are guessed by a model from a short label (the 'zero-shot' basis). Check the ring makes sense.",
  },
  ring_basis: {
    title: "Ring basis", group: "signals",
    short: "How Moria decided a candidate's ring.",
    moria: "card: the source belongs to one ring; core_terms: the label matches IP-system words; map: a fixed map from the query or research field; items: most of its documents' ring; zeroshot: a language model's best guess from the label.",
  },
  views: {
    title: "The two views", group: "ranking",
    short: "Two ways of ranking the same candidates. Early warning favours what is new and early; strategic favours what is broad and lasting.",
    moria: "Early warning: strength × novelty × lead time. Strategic: strength × breadth (with impact and pathway once the decision model is trusted). Trends are strategic only; weak signals and anomalies early warning only; accelerations are in both.",
  },
  direction: {
    title: "Direction", group: "signals",
    short: "Whether the change is a rise or a fall. A fall can matter as much as a rise.",
  },
  scope: {
    title: "Scope", group: "signals",
    short: "Where the numbers are about: Australia, the world, the OECD, another country.",
    moria: "Australian series rank a little higher (a factor of 1.0 against 0.85 for world aggregates and 0.7 for other countries): a rough machine stand-in for relevance to Australia.",
  },
  divergence: {
    title: "Divergence (Australia against the world)", group: "signals",
    short: "Australia's share of something moving differently from the world's (or the OECD's).",
    moria: "The ratio of Australia's share to the world's share is tested for a trend, like any series.",
  },
  new_term: {
    title: "New term", group: "signals",
    short: "A key phrase appearing in recent documents that was absent before.",
    moria: "The window is the last 91 days; the baseline the 730 days before. A phrase must reach a minimum count in the window and be absent from the baseline.",
    watch: "A source collected only recently has no baseline, so all its phrases look new.",
  },
  new_combination: {
    title: "New combination", group: "signals",
    short: "Two things that were each known before, now appearing together for the first time (or far more often).",
    moria: "Pairs of key phrases in documents, and pairs of IPC or Nice classes on the same IP application. Each half must have appeared often enough before.",
  },
  cross_family: {
    title: "Cross-family", group: "signals",
    short: "A topic that moved from one kind of source to another, for example from research papers into news and policy.",
  },
  cross_ring: {
    title: "Cross-ring", group: "signals",
    short: "A topic that moved from the wider world or adjacent fields towards the IP system (or the reverse).",
  },
  low_base_surge: {
    title: "Low-base surge", group: "signals",
    short: "A count that jumped from a very low starting point: few in the past, many now.",
    moria: "Tested with an exact Poisson test of two rates, as a share of the source's total volume. Needs a minimum count and a ratio of at least 3.",
    watch: "With small numbers, one journal issue or one book can make a surge. The dossier checks whether the works are concentrated in one venue.",
  },
  novel_items: {
    title: "Micro-cluster of novel items", group: "signals",
    short: "A small group of recent documents that are close to each other in meaning but far from anything seen before.",
    moria: "Measured with text embeddings: each document's distance to its nearest neighbours in the baseline.",
  },
  jurisdiction_shift: {
    title: "Jurisdiction shift", group: "signals",
    short: "Applicants from a country entering, rising in, or leaving a class of IP rights in Australia.",
    moria: "From IP RAPID's applications: applicant countries by IPC or Nice class, window against baseline. Switched on by the owner (D-028).",
  },
  fading_combination: {
    title: "Fading pair", group: "signals",
    short: "Two things that used to appear together and now rarely do.",
    moria: "Tested against the count the baseline would predict (the lower tail of a Poisson count). Switched on by the owner (D-028).",
  },
  known_trend: {
    title: "Known trend", group: "signals",
    short: "One of the trends already recognised in the foresight literature Moria was given (the baseline of 19, plus 5 proposed).",
    moria: "Each candidate is matched to its nearest known trend by meaning. A close match lowers novelty a little; it is a tag, never a reason to reject. Reinforcing a known trend counts (D-014).",
    watch: "The match is made by a model on short labels; it is often loose.",
  },
  territory: {
    title: "Growth territory", group: "signals",
    short: "One of IP Australia's five areas of interest. Candidates are tagged with the territory they seem closest to.",
  },
  cosine: {
    title: "Similarity (cosine)", group: "stats",
    short: "How close two pieces of text are in meaning, from 0 (unrelated) to 1 (the same), as a language model sees them.",
    moria: "Used to match candidates to known trends and territories. A known-trend match needs 0.68 or more.",
    interpret: (v) => `${fmt(v, 2)}: ${v >= 0.68 ? "close enough to count as a match" : v >= 0.6 ? "related, but not a match" : "only loosely related"}.`,
  },

  // ---------------------------------------------------------------------------------------------- statistics
  p_value: {
    title: "p-value", group: "stats",
    short: "If nothing real were going on, how often would a pattern at least this strong turn up by chance? Small means surprising.",
    moria: "Moria never uses a raw p-value alone: it adjusts for the many series tested (see Holm).",
    watch: "A small p-value says a pattern is unlikely to be chance; it does not say the pattern matters.",
    interpret: (v) => `${pval(v)}: by chance alone, a pattern this strong would turn up ${oneIn(v)}.`,
  },
  holm: {
    title: "Holm adjustment (p, Holm)", group: "stats",
    short: "A correction for testing many things at once. Test 20,000 series and hundreds will look significant by luck; Holm raises the bar so that, across a whole family of tests, the chance of even one false alarm stays at 5%.",
    moria: "Moria's rule. Trends, accelerations and surges must have a Holm-adjusted p below 0.05 within their family (one source, one frequency, one taxonomy level, one scope); anomalies below 0.01.",
    watch: "Holm is strict: some real changes are missed. That is the price of keeping false alarms rare.",
    interpret: (v) => `${pval(v)}: ${v < 0.05 ? "passes Moria's bar of 0.05" : "does not pass Moria's bar of 0.05"}. Even allowing for every other series in its family, a pattern this strong would arise by chance ${oneIn(v)}.`,
  },
  bh: {
    title: "Benjamini-Hochberg (q)", group: "stats",
    short: "A gentler correction for many tests: it keeps the share of false alarms among the findings at about 5%, rather than the chance of any false alarm.",
    moria: "Shown for comparison only. In this scan, Benjamini-Hochberg would have passed about five times as many trends as Holm.",
    interpret: (v) => `${pval(v)}: ${v < 0.05 ? "would pass under Benjamini-Hochberg" : "would not pass even under Benjamini-Hochberg"}.`,
  },
  multiple_testing: {
    title: "Multiple testing", group: "stats",
    short: "The more things you test, the more 'discoveries' you make by pure luck. With 27,000 series at p < 0.05, about 1,350 would look significant even if nothing were happening.",
    moria: "Hence Holm's adjustment within families, and the requirement of 2 of 3 windows for a trend.",
  },
  alpha: {
    title: "Significance level (alpha)", group: "stats",
    short: "The bar a p-value must clear: 0.05 for trends, accelerations and surges; 0.01 for anomalies.",
  },
  theil_sen: {
    title: "Theil-Sen slope", group: "stats",
    short: "A sturdy way to draw a trend line: the median of the slopes between every pair of points, so one wild value can't drag it about.",
    moria: "Counts are tested on a log scale as shares of their source's volume, so the slope is roughly a growth rate per period.",
    interpret: (v) => `${fmt(v, 3)} a period on the tested scale.`,
  },
  ci: {
    title: "Confidence interval", group: "stats",
    short: "The range of slopes consistent with the data (here at 95%). If it doesn't include zero, the direction is clear.",
    moria: "Drawn as a shaded bow-tie around each trend line: the narrower the bow-tie, the surer the slope.",
    watch: "It covers the slope only, not what happens next. Moria does not forecast.",
  },
  mann_kendall: {
    title: "Mann-Kendall test", group: "stats",
    short: "Counts how often later values are higher than earlier ones. If 'up' wins by far more than chance allows, there is a trend.",
    moria: "Gives the p-value of each trend window (with a correction for ties).",
  },
  windows: {
    title: "Trend windows (w1, w2, w3)", group: "stats",
    short: "Three look-back periods ending at the latest data: for monthly series 12, 24 and 36 months; quarterly 8, 16 and 24 quarters; yearly 8, 12 and 16 years.",
    moria: "A trend needs at least 2 of the 3 windows significant, all in the same direction, so one lucky stretch isn't enough.",
  },
  growth: {
    title: "Growth a year", group: "stats",
    short: "The trend's slope turned into an approximate yearly rate. For counts, +0.10 is roughly 10% a year more than the source's overall volume.",
    interpret: (v) => `${v > 0 ? "+" : ""}${pct(v, 1)} a year.`,
  },
  log_share: {
    title: "Share of the source's volume (log scale)", group: "stats",
    short: "A count divided by everything that source published in the same period, then logged. So a topic rising only because the source grew doesn't count as a rise.",
    moria: "Used for OpenAlex topics, CPC subclasses, GDELT queries and IP RAPID splits.",
  },
  log_count: {
    title: "Count (log scale)", group: "stats",
    short: "A total, on a log scale so that a slope is a growth rate.",
  },
  level: {
    title: "Level", group: "stats",
    short: "A published statistic (ABS, OECD) tested on its own scale.",
  },
  bootstrap: {
    title: "Bootstrap", group: "stats",
    short: "Re-drawing the data thousands of times to see how much a number would wobble by chance.",
    moria: "Used to test whether the recent half's slope is truly steeper than the earlier half's (an acceleration).",
  },
  change_point: {
    title: "Change point", group: "stats",
    short: "The moment a series' behaviour shifts: its slope or its level changes.",
    moria: "Found by optimal partitioning (the exact answer PELT searches for), with a strict penalty so noise is rarely split.",
  },
  anomaly_band: {
    title: "Expected band", group: "stats",
    short: "Where the latest value 'should' be, given a trend line fitted on the periods before it, with a robust measure of how much the series usually wobbles.",
    moria: "Drawn at 99% before the adjustment for many series; Moria's actual bar (Holm across the family) is stricter still.",
    watch: "The band is a prediction from the past. A value outside it is surprising, not necessarily important.",
  },
  z: {
    title: "z-score", group: "stats",
    short: "How many 'usual wobbles' the value is from what was expected. Beyond about 2.6 is outside the 99% band.",
    interpret: (v) => `${fmt(v, 3)}: the value is ${fmt(Math.abs(v), 2)} usual wobbles ${v >= 0 ? "above" : "below"} what was expected.`,
  },
  poisson: {
    title: "Poisson test", group: "stats",
    short: "The right test for small counts of rare events: given the past rate, how surprising is today's count?",
  },
  percentile: {
    title: "Percentile", group: "ranking",
    short: "Where a value sits among all the others, from 0 (lowest) to 1 (highest). 0.9 means higher than 90% of candidates.",
    moria: "Every ranking component is a percentile, so components measured in different units can be combined fairly.",
    interpret: (v) => `${fmt(v, 2)}: higher than about ${pct(v)} of the candidates it is compared with.`,
  },
  r2: {
    title: "R²", group: "stats",
    short: "How much of the movement a model explains, from 0 (none) to 1 (all).",
  },

  // ------------------------------------------------------------------------------------------------- ranking
  geomean: {
    title: "Weighted geometric mean", group: "ranking",
    short: "Multiplying the components together (then taking the root), rather than adding them. One weak component pulls the whole score down: a chain is only as strong as its weakest link.",
    moria: "A view's score is the weighted geometric mean of its components, times its factors. A component below 0.05 counts as 0.05, so one weak part never zeroes a score.",
  },
  score: {
    title: "Score", group: "ranking",
    short: "How high a candidate ranks in a view, between 0 and 1.",
    moria: "Scores rank candidates within one scan; they are not probabilities and do not compare across scans.",
    interpret: (v) => `${fmt(v, 3)} on a 0 to 1 scale (a rank, not a probability).`,
  },
  strength: {
    title: "Strength", group: "ranking",
    short: "How big the detected change is, as a percentile among candidates of the same type and kind.",
    interpret: (v) => `${fmt(v, 2)}: a bigger change than about ${pct(v)} of its kind.`,
  },
  breadth: {
    title: "Breadth", group: "ranking",
    short: "How many independent lines of evidence back it: sources, families of sources and detectors that agree. A percentile.",
    watch: "Series that move together count once (see redundancy).",
    interpret: (v) => `${fmt(v, 2)}: broader support than about ${pct(v)} of candidates.`,
  },
  lead: {
    title: "Lead time", group: "ranking",
    short: "How early in the life of a change its detector tends to fire. New terms come earliest (1.0); long trends latest (0.2).",
  },
  novelty: {
    title: "Novelty", group: "ranking",
    short: "How new the kind of finding is. Lowered (times 0.6) when it closely matches a known trend.",
  },
  pathway_c: {
    title: "Pathway and impact components", group: "ranking",
    short: "How plausibly a candidate could reach Australia's IP system, and how much it could change it, from the decision model.",
    moria: "Switched off: the model failed its check, so these have no effect on the ranking (D-029).",
  },
  factors: {
    title: "Factors", group: "ranking",
    short: "Multipliers applied after the components: type (anomalies 0.5), flags (each artefact flag lowers the score), scope (Australia 1.0, world 0.85, others 0.7) and context.",
  },
  flag_penalty: {
    title: "Flag penalties", group: "ranking",
    short: "Each artefact flag multiplies the score down: coverage 0.7, ingestion 0.5, duplicate 0.6, news cycle 0.5, source break 0.7, label drift 0.8.",
    watch: "Moria's sensitivity test found the flag penalties decide most of the queue's edge: without them, 12 of the 40 places change.",
  },
  shortlist: {
    title: "Shortlist", group: "ranking",
    short: "The top 100 under the ring quotas. Each gets a full evidence dossier and the decision model's suggestions.",
  },
  queue: {
    title: "Review queue", group: "ranking",
    short: "The 40 candidates put in front of a person for review this round, chosen from the shortlist.",
    moria: "Picks alternate between the two views; each ring is held to its quota, no source fills more than 25%, and only one candidate per redundancy group.",
  },
  quota: {
    title: "Ring quotas", group: "ranking",
    short: "Fixed shares of the queue for each ring (35% core, 35% adjacent, 30% wider world), so one ring can't crowd out the others.",
  },
  pass: {
    title: "Selection pass", group: "ranking",
    short: "Pass 1: within every quota. Pass 2: a ring's unused places given to another ring. Pass 3: the source cap relaxed.",
  },
  sensitivity: {
    title: "Sensitivity (places kept)", group: "ranking",
    short: "Moria changes each weight (halved, or raised by half) and picks the queue again. 'Places kept' counts how many of the 40 stay. Near 40: that weight barely matters. Lower: it decides much of the queue.",
    interpret: (v) => `${v} of 40 places kept.`,
  },
  redundancy: {
    title: "Redundancy group", group: "ranking",
    short: "Candidates whose series move together (correlated indicators). They count as one line of evidence, and only one per group can enter the queue.",
  },
  corroboration: {
    title: "Corroboration", group: "ranking",
    short: "The number of independent lines of evidence: 1 for a series; for documents, the sources of its de-duplicated items.",
  },
  floor: {
    title: "Floor", group: "ranking",
    short: "The lowest value a component can count as (0.05), so one weak component never zeroes a score.",
  },

  // ---------------------------------------------------------------------------------------------------- checks
  flags: {
    title: "Artefact flags", group: "checks",
    short: "Warnings that a candidate might come from how the data was collected rather than from the world. A flag marks a candidate; it never hides it.",
  },
  coverage: {
    title: "Coverage", group: "checks",
    short: "The source's total volume moved by more than 25%: the 'change' may just be the source publishing more (or less) of everything.",
  },
  ingestion: {
    title: "Ingestion", group: "checks",
    short: "Moria had a failed or partial collection from a source in the candidate's window.",
  },
  duplicate: {
    title: "Duplicate", group: "checks",
    short: "Much of the evidence is the same story syndicated or copied.",
  },
  news_cycle: {
    title: "News cycle", group: "checks",
    short: "A burst that lasted only a few days, like a single news story, rather than sustained change.",
  },
  source_break: {
    title: "Source break", group: "checks",
    short: "A source was onboarded inside the baseline, so 'new' may only mean new to Moria.",
    watch: "Most sources started daily collection in October 2026, so this flag is common until a year of baseline builds up.",
  },
  label_drift: {
    title: "Label drift", group: "checks",
    short: "A classification or label changed meaning over time (for example, a taxonomy update).",
  },
  concentrated_works: {
    title: "Concentrated works", group: "checks",
    short: "Most of the research works behind an OpenAlex surge come from one venue, such as a single book or journal issue.",
  },
  reclassified: {
    title: "Reclassified", group: "checks",
    short: "IP applications counted in the window were mostly filed years earlier and only (re)classified now: a paperwork change, not new filings.",
  },
  few_applicants: {
    title: "Few applicants", group: "checks",
    short: "The IP applications behind a class change come from fewer than 3 applicants.",
  },
  administrative: {
    title: "Administrative cause", group: "checks",
    short: "A known recording change (for example, a new classification edition or a change in what IP RAPID records) explains the movement.",
  },
  explained_by_context: {
    title: "Explained by its context", group: "checks",
    short: "The series' peers and its international counterpart moved the same way, predicting most of the jump: the change may be general, not specific.",
    moria: "Shown, never used to filter or rank (the owner, D-028).",
  },
  seasonal: {
    title: "Seasonal pattern", group: "checks",
    short: "The same month or quarter jumps every year: the anomaly may be the calendar.",
  },
  known_trend_check: {
    title: "Known trend check", group: "checks",
    short: "The candidate closely matches a known trend: it may reinforce what is already known (which still counts).",
  },
  redundancy_check: {
    title: "Redundancy check", group: "checks",
    short: "Other candidates move with this one: together they are one line of evidence, not several.",
  },

  // -------------------------------------------------------------------------------------------------- evidence
  dossier: {
    title: "Dossier", group: "evidence",
    short: "The evidence file for a shortlisted candidate: its numbers, its evidence, the alternative explanations checked, counter-evidence, history and ranking.",
  },
  dedup: {
    title: "De-duplication group", group: "evidence",
    short: "Copies of the same item (the same story syndicated, the same page at two addresses) grouped so they count once.",
  },
  observable_at: {
    title: "Observable date", group: "evidence",
    short: "When Moria could first have seen an item: the source's own date, or Moria's first sight of it if later. Scans never use what wasn't visible at the time.",
  },
  backfill: {
    title: "Backfill", group: "evidence",
    short: "History collected in one go when a source was first added. It has no true 'first seen' date, so it can't show what was new at the time.",
  },
  as_of: {
    title: "Scan date (as of)", group: "evidence",
    short: "The day a scan looks from. It sees only what was observable by the end of that day.",
  },
  family: {
    title: "Source family", group: "evidence",
    short: "The kind of source: news, policy, legal, research, statistics, IP Australia's own (ipa_internal), patents.",
  },
  ip_rapid: {
    title: "IP RAPID", group: "evidence",
    short: "IP Australia's weekly open data on patent, trade mark, design and plant breeder's rights applications. Individuals' names are hashed before Moria stores anything.",
  },
  openalex: {
    title: "OpenAlex", group: "evidence",
    short: "An open index of research publications. Moria counts works by topic each week, worldwide and with an Australian author.",
    watch: "OpenAlex assigns topics with a classifier trained in 2024, so old works carry modern topics.",
  },
  register: {
    title: "Register", group: "evidence",
    short: "An append-only log of what happened to each signal: queued, the machine's suggestions, each person's review. Nothing is ever overwritten.",
  },
  status: {
    title: "Review status", group: "evidence",
    short: "Where a signal is in its life: candidate, investigating, validated, rejected, parked, mainstream and so on.",
  },

  // ---------------------------------------------------------------------------------------------- the machine
  decision_model: {
    title: "The decision model", group: "machine",
    short: "A small free language model (Jev-Style, 0.8 billion parameters) asked eleven questions about each dossier: which of six pathways to the IP system apply, how direct, when, and how big.",
    moria: "Its answers are recorded and shown, but not used in the ranking: it failed its check (D-029).",
    watch: "Treat its suggestions as noise for now. They barely vary from candidate to candidate.",
  },
  pathways: {
    title: "Pathways (P1 to P6)", group: "machine",
    short: "Six ways a change could reach Australia's IP system: P1 demand for rights; P2 the value of rights; P3 how rights are examined and enforced; P4 trust and fairness; P5 IP Australia itself; P6 Australia's ability to benefit from ideas.",
  },
  order: {
    title: "Order", group: "machine",
    short: "How directly a change reaches the IP system: 1 directly, 2 through one intermediate change, 3 through a chain of changes.",
  },
  separation: {
    title: "Separation", group: "eval",
    short: "In the decision model's check: how much higher it scores obviously relevant sentences (an AI-inventorship ruling) than obviously irrelevant ones (a football result). It needed 0.05; it managed 0.007.",
    interpret: (v) => `${fmt(v, 3)} against the 0.05 required.`,
  },
  spread: {
    title: "Spread", group: "eval",
    short: "How much the model's top answer varies across real dossiers (the interquartile range). A model that says the same thing about everything isn't discriminating.",
  },

  // -------------------------------------------------------------------------------------------- evaluations
  seeded: {
    title: "Seeded artefacts", group: "eval",
    short: "Fake problems planted on purpose in a copy of the data (a volume spike, syndicated copies, a new source) to check each artefact check catches its own kind.",
    moria: "6 of 6 caught, and 6 of 6 'controls' (real changes of the same size) left unflagged.",
  },
  hindsight: {
    title: "Hindsight test", group: "eval",
    short: "Running Moria as if on past dates, to see whether it would have raised developments before they became mainstream (COVID trade marks, metaverse trade marks, generative AI patents).",
    watch: "So far a smoke test: the developments were proposed by Claude, not yet chosen by the owner blind to Moria's output.",
  },
  lead_months: {
    title: "Lead (months)", group: "eval",
    short: "How many months before a development became mainstream Moria first raised it.",
  },
  recall: {
    title: "Recall", group: "eval",
    short: "Of the changes planted in real series, the share a detector caught.",
  },
  null_rate: {
    title: "False alarm rate", group: "eval",
    short: "Of series with nothing planted, the share a detector flagged anyway.",
  },
  incremental: {
    title: "Incremental value", group: "eval",
    short: "The share of planted changes a new detector caught that none of the older detectors did.",
  },
};

// --------------------------------------------------------------------------------------------- the popover

let pop, hideTimer, current;

function place(target) {
  const r = target.getBoundingClientRect();
  const p = pop.getBoundingClientRect();
  let top = r.bottom + 8;
  if (top + p.height > window.innerHeight - 10) top = Math.max(10, r.top - p.height - 8);
  let left = Math.min(Math.max(10, r.left + r.width / 2 - p.width / 2), window.innerWidth - p.width - 12);
  pop.style.top = `${top}px`;
  pop.style.left = `${left}px`;
}

function show(target) {
  clearTimeout(hideTimer);
  const key = target.dataset.term;
  const t = TERMS[key];
  if (!t) return;
  current = target;
  const value = target.dataset.value != null && target.dataset.value !== "" ? Number(target.dataset.value) : null;
  let html = `<h4>${esc(t.title)}</h4><p>${esc(t.short)}</p>`;
  if (value != null && !Number.isNaN(value) && t.interpret) html += `<p class="p-value">This value: ${esc(t.interpret(value))}</p>`;
  if (t.moria) html += `<p class="p-moria"><strong>In Moria:</strong> ${esc(t.moria)}</p>`;
  if (t.watch) html += `<p class="p-watch"><strong>Watch out:</strong> ${esc(t.watch)}</p>`;
  html += `<p class="p-more"><a href="#/glossary/${esc(key)}">More in the glossary</a></p>`;
  pop.innerHTML = html; // every piece of text above is escaped
  pop.hidden = false;
  place(target);
}

function hideSoon() {
  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => {
    pop.hidden = true;
    current = null;
  }, 180);
}

export function initPopover() {
  pop = document.getElementById("popover");
  const find = (e) => e.target.closest?.("[data-term]");
  document.addEventListener("pointerover", (e) => {
    const t = find(e);
    if (t) show(t);
    else if (e.target.closest?.("#popover")) clearTimeout(hideTimer);
  });
  document.addEventListener("pointerout", (e) => {
    if (find(e) || e.target.closest?.("#popover")) hideSoon();
  });
  document.addEventListener("focusin", (e) => {
    const t = find(e);
    if (t) show(t);
  });
  document.addEventListener("focusout", (e) => {
    if (find(e)) hideSoon();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !pop.hidden) pop.hidden = true;
  });
  window.addEventListener("scroll", () => current && !pop.hidden && place(current), { passive: true, capture: true });
}

/** A term in running text: dotted underline, explainer on hover and focus. */
export function term(key, text, value) {
  return el("span.term", { tabindex: 0, "data-term": key, "data-value": value ?? "", role: "button", "aria-label": `${text}: what is this?` }, text ?? TERMS[key]?.title ?? key);
}

/** A small "?" after a heading or label. */
export function tip(key) {
  return el("button.tipdot", { type: "button", "data-term": key, "aria-label": `What is ${TERMS[key]?.title ?? key}?` }, "?");
}

/** A number with its explainer: the value's own reading appears in the popover. */
export function num(key, value, text) {
  return term(key, text ?? fmt(value), value);
}
