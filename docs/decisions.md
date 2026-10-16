# Decision log

Append-only, numbered and dated. Each entry says whose decision it was. To change a decision, add an entry that
supersedes it. Template: `sop-agent-construction-v2.md` §26 T3.

---

## D-001 — Moria's design proposed: a CRISP-DM scan cycle on R2 and an e2-micro, with scikit-learn mining, Jev decisions and checked write-ups (2026-10-09)

**Context.** The owner asked for a data-mining operation to inform IP Australia's strategic direction: "stuff like
PESTLE, SWOT, and the Futures Cone but all being informed by traditional data mining processes. Design a system."
They named scikit-learn and Jev for processing, Cloudflare R2 for storage, and the Google Compute Engine free tier for
compute.

**Decision (a recommendation; the owner decides adoption).** The design is `docs/design.md` v0.1. Its main choices:
- **Method.** CRISP-DM is the quarterly scan cycle. Owner gates come after business understanding (questions,
  codebook, hindsight set) and at each measured adoption. An analyst workshop comes at deployment.
- **Infrastructure.**
  - R2 is the system of record: raw data immutable, a Parquet lake, labels, models, scans and manifests.
  - One e2-micro in us-west1 runs everything, one job at a time.
  - BigQuery is used for global patent aggregates only, with each query capped.
- **Unit of data.** The evidence object, with the Access architecture document's provenance envelope, trimmed. It has
  three kinds: documents, observations and IP RAPID records.
- **Mining.** scikit-learn throughout, in its out-of-core forms (`partial_fit`), with vocabularies capped at 20k
  terms. DuckDB runs with a 300 MB memory limit. Embeddings are local (`bge-small-en-v1.5` through fastembed).
- **Typed decisions.** Jev answers a two-stage, versioned question set: relevance and PESTLE for all items; stance,
  impact, horizon, settledness, signal kind and rights affected for relevant items. Its probabilities are used as
  expected counts. Jev sits behind an adapter beside `sklearn` and `llm` backends, and the labeller is chosen on a
  600-item gold set by a rule fixed in advance.
- **Writing.** A generative model names themes and writes the drivers, TOWS options, scenarios and reports. A
  deterministic check covers citations, verbatim quotes and every number in the prose. A judge comes from the other
  model family.
- **Frameworks.**
  - PESTLE: themes per dimension, with trend tests, and drivers.
  - SWOT: strengths and weaknesses from IP RAPID metrics against WIPO peers; opportunities and threats from driver
    stance; TOWS by shared keys.
  - Futures Cone: projected and probable zones from backtested forecasts; plausible scenarios on data-selected
    critical uncertainties; possible futures from weak signals; the preferable zone left to leadership, with
    backcasting support.
- **Pilot.** A thin slice: one question (AI and the IP system, 2026–2036), Tier 1 sources only, one complete scan.

**Rejected, a line each:**
- **Mirroring OpenAlex, Google Patents or GDELT.** Too large for R2's 10 GB free. Aggregate queries and capped samples
  answer the same questions.
- **Jev as the only labeller.** It is early access, signups were reported paused on 2026-09-22, and its benchmarks are
  the vendor's own.
- **Collectors on Cloudflare Workers.** That is a second runtime and language for little gain at this volume.
- **Serving reports from the VM.** GCP's free egress excludes Australia, while R2's egress is free.
- **A dense NMF over hashed features.** It measured 844 MB on synthetic data, so it would exhaust the 1 GB VM.
- **HDBSCAN on the full corpus.** Its memory and time grow too fast, so it runs on samples of 20k or fewer.

**Checked:**
- **Memory.** `scripts/memprobe.py` ran on synthetic data at the planned scale, on this session's CPU. The numbers are
  in design §3.2. They have not yet been measured on the e2-micro; Phase 0 does that.
- **IP RAPID.** Its data.gov.au CKAN record shows `IPRAPID.zip` at 1,347,388,270 bytes, modified 2026-10-05, licensed
  CC BY 4.0. Its data dictionary lists six tables.
- **Free tiers, as Google and Cloudflare document them.**
  - e2-micro: us-west1, us-central1 or us-east1; 30 GB standard disk; 1 GB a month of egress from North America,
    excluding China and Australia.
  - BigQuery: 1 TiB of queries a month.
  - R2: 10 GB-month, 1M Class A and 10M Class B operations, and free egress.
- **Not verified:**
  - whether the free tier waives the in-use external IPv4 charge ($0.005 an hour);
  - Jev's API details, which come from third-party write-ups.

**Spend:** $0. No paid calls were made. The probe used synthetic data, and the embedding model was downloaded from
Hugging Face.

**Consequences.**
- Nothing is built.
- The build order is design §12, starting with Phase 0 (kickoff: skeleton, VM, R2, environment check, the probe on
  the VM, the Tier 1 inventory).
- For the owner: the seven decisions in design §14. They are adopting the design; the pilot question; Jev access; the
  public-only scope; the budget ($50, then about $25 a quarter, with a $5 a month infrastructure alert); who labels
  and reviews; and the repo's visibility.

---

## D-002 — Design v0.2: signal-first and question-led, after reviewing an alternative view; supersedes D-001's design (2026-10-09)

**Context.** The owner supplied an alternative view, "not to redirect your design but to see whether improvements
can/should be made". Its main points:
- build around questions and six intelligence domains, not frameworks;
- use a layered analytical pipeline;
- separate trends from weak signals;
- run artefact checks, because a spike may be a news cycle, a coverage change or an ingestion failure;
- use a portfolio of sources, with source cards;
- keep event dates apart from observable dates;
- validate signals with analysts before interpreting them;
- separate the evidence, interpretation and decision layers;
- evaluate the intelligence itself, with leakage-aware hindsight tests;
- run a six-week proof of concept;
- settle the primary purpose: whole-of-agency strategy, IPAVentures, or both.

**Decision (a recommendation; the owner decides adoption).** `docs/design.md` v0.2 replaces v0.1. Section 0.1 of the
design tabulates every point against v0.1 and v0.2.

**Adopted:**
- **Questions and domains.** Six intelligence domains (D1–D6) structure the sources, questions and register. Seven
  starter questions are drafted. PESTLE tags external drivers only; SWOT combines internal and external.
- **A signal register** that is an append-only event log. Its lifecycle runs: candidate, investigating, validated or
  rejected, tracked, then strengthened, weakened, disproved or mainstream. An analyst validation step comes before
  every lens.
- **An operational taxonomy:** trend, acceleration, anomaly, weak signal and wild card. There are five weak-signal
  indicators: new term, new combination, cross-family, low-base surge, and novel items. Wild cards are proposed and
  curated, never detected.
- **Artefact checks** on every candidate: coverage, ingestion, duplication, news cycle, source break and label drift,
  with per-source ingestion monitors.
- **Source cards:** coverage, cadence, lag, history, biases, revisions and licence. No trend claim may run beyond a
  source's stable history.
- **`event_at` and `observable_at`.** All point-in-time logic uses `observable_at`.
- **Evidence dossiers:** the original evidence, the nearest historical analogues, an alternative-explanations
  checklist, and counter-evidence from BM25 and neighbour search.
- **Three layers.**
  - Per-item tags (what an item is about) are evidence.
  - Stance, impact, horizon and uncertainty (what it means) are interpretations, at signal level, attributed to
    analysts or to a model with its version.
  - Decisions are a separate log.
- **Intelligence evaluation:**
  - the measures: recovery, lead time, precision, novelty, source diversity, decision usefulness and cost;
  - a missed-signal register;
  - a blind conventional scan as the baseline. The success test is at least 3 validated signals the conventional
    scan missed.
- **Leakage rules.**
  - Observable dates only.
  - Every model used at a past date is fitted on data observable by then.
  - Hindsight runs report a term-only and a full variant, because pretrained models were trained after the events.
  - The hindsight set includes non-events.
- **A six-week PoC** with six named deliverables. The gold set shrinks from 600 items to 300, covering per-item tags
  only.
- **Robustness of options.** Each option is rated against every scenario and classified as no-regret, hedge or bet.
  The PoC develops 2 or 3 scenarios.
- **Mining priorities:** temporal (adding acceleration and change points), semantic, anomaly and relationship mining.
  Keyphrases and BM25 search are added. Forecasting stays at baselines in the PoC.
- **Purpose becomes owner decision 1.** The ranking criteria are a configurable lens. The recommendation is agency
  strategy for the PoC, with IPAVentures as a later lens.

**Adapted to the owner's constraints:**
- **Customer signals.** Public proxies only, and domain D4 is labelled *low coverage* in every output.
- **The stack.** GCE and R2 as the owner specified. DuckDB and Parquet rather than SQLite. fastembed, not PyTorch
  Sentence Transformers: it runs the same models, and was measured at 462 MB. GitHub Actions only as a fallback for
  heavy one-off jobs. spaCy only if n-gram keyphrases prove poor.

**Kept from v0.1:**
- CRISP-DM as the outer cycle;
- Jev behind an adapter, with measured selection;
- the deterministic write-up check, including the number check;
- the cross-family judge;
- the free-tier rules;
- the security rules.

**Checked:**
- **Two new probe workloads.** They ran on this session's CPU, on synthetic data:
  - BM25 over 100k documents with DuckDB's `fts` index: 484–489 MB, 59–78 s;
  - chunked cosine top-10 over 200k float16 vectors: 341 MB, 5.7 s.

  A first version of the neighbour workload peaked at 644 MB. It built a full float32 copy that a real job would not
  make, so the probe was corrected to build vectors in chunks. All planned workloads now peak at 206 to 489 MB, with
  hashed-feature NMF (844 MB) still ruled out.
- **The architecture diagram** was rendered with mermaid-cli 11.4.2 and shows no syntax errors.
- **IPAVentures** is IP Australia's in-house innovation lab (since 2021; stage-gated; IP First Response), per IP
  Australia's "Innovation at IP Australia" page.

**Spend:** $0.

**Consequences.**
- Nothing is built.
- The build plan is design §13, weeks 1 to 6.
- **For the owner:** the eight decisions in design §15:
  1. the purpose;
  2. adopting v0.2;
  3. the questions;
  4. the baseline scan;
  5. Jev access;
  6. the public-only scope;
  7. the $50 PoC cap;
  8. analyst time (about 22 hours plus a workshop, plus about 3 days for a blind scan), and the repo's visibility.

---

## D-003 — The owner's answers on v0.2: one purpose for both audiences, broader scope, free first, one week (2026-10-09)

**Context.** The owner answered the v0.2 decisions (design §15 there).

**Decision (owner).**
1. **Purpose: both.** "IPAVentures is the agency's strategic 'canary in a coal mine', so by shaping the purpose for
   IP Australia inherently shapes it for IPAVentures."
2. **Speed and breadth.** Be ambitious and move quickly: about one week for the machinery, while the analysis takes
   longer. The analysis was too IP-specific: "There are MANY factors which may impact the Australian IP system over
   the course of 10 years," so think broadly, but not so broadly as to waste time.
3. **Questions.** The owner couldn't see the drafted questions, and will add five Growth Territories of their own. The
   investigation may be broader than those five.
4. **Model.** The owner will likely use Matilda, a Jev-class model on Hugging Face.
5. **Scope.** Public data only (confirmed).
6. **Money.** No spend is approved until its exact purpose is known. Free options first, including open Hugging Face
   models for encoding and clustering.
7. **Clarification.** The owner asked what item 8 (people and repo visibility) meant.
8. **Compute.** Asked mid-turn: can the GPUs or TPUs on Google Colab be used?

**Consequences.** Design v0.3 (D-004) applies these answers.

---

## D-004 — Design v0.3: broad by design, free first, a one-week machinery sprint (2026-10-09)

**Context.** The owner's answers in D-003.

**Decision (a recommendation; the owner decides adoption).** `docs/design.md` v0.3:

- **One register, two views.** The early-warning view (IPAVentures) shows weak signals, low-base surges and novel
  items once past the artefact checks. The strategic view (agency) shows validated trends and drivers. The lens
  decision of v0.2 is removed.
- **Breadth by design.**
  - There is no IP filter at collection.
  - There are three rings: core (the IP system), adjacent (economy, technology, international) and the wider world.
  - Big sources are read as whole-taxonomy counts: all OpenAlex topics, all CPC subclasses, ABS headline series, and
    about 200 broad news themes, each for the world and for Australia.
  - Every candidate must show one of **six pathways** to the IP system (demand, value, function, legitimacy, the
    organisation, outcomes), with an order from 1 to 3; order 3 must name its chain.
  - Four outside-in questions lead, and the v0.2 questions become sub-questions. Growth Territories have a slot.
- **Breadth controls.**
  - The pathway gate applies to signals, never to items.
  - Ring quotas in the review queue: 35% core, 35% adjacent, 30% wider world, with third-order pathways capped at 20%.
  - A review budget of about 40 dossiers a round.
  - A known-trends baseline drawn from foresight syntheses.
  - A saturation rule for adding sources.
  - A breadth measure: if the wider world yields nothing, the scan is too narrow; if it yields only order-3 noise, it
    is too broad.
- **Novelty baseline.** The known-trends baseline plus the five territories replace the three-day blind scan. The
  success test is at least 3 validated signals outside both.
- **Free first.**
  - Embeddings: local `bge-small-en-v1.5`.
  - Per-item tags: zero-shot similarity, then logistic regression on about 200 of the owner's labels.
  - Signal-level decisions: the free Jev-class model `Jev-Style-0.8B-Decision-v3` (Apache-2.0).
  - Cluster names and dossiers: deterministic. Write-ups: written by people.
  - A **paid menu** (M1–M4) lists each optional item with its purpose, quantity, cost and free alternative. Nothing
    on it runs without its own approval.
- **Matilda-Jev** is the measured upgrade (M1), not the default.
  - For it: Apache-2.0; an Australian maker; the same `/v1/systemone` API, so the adapter takes it unchanged.
  - Against running it for free: 26.1B parameters, about 49 GiB in bf16 or about 16.3 GiB in FP4, tested only on AMD
    MI355X. Its runtime needs `trust_remote_code`, which needs the owner's security exception.
- **Compute, a decision for the owner.**
  - Option A (recommended): GitHub Actions, which is free for this **public** repo, plus R2. $0.
  - Option B: as first specified, adding the e2-micro. About $0.60 to $3.65 a month for its IPv4 address.
  - Free Colab or Kaggle GPUs serve as optional manual bursts. A free T4 can't run Matilda-Jev, and our stack doesn't
    use TPUs.
- **The one-week sprint:** three parallel sessions; daily collectors live on day 1, because first sightings can't be
  backfilled; the first ranked queue of about 40 dossiers on day 5; two buffer days.

**Rejected, a line each:**
- **An item-level IP-relevance gate.** It would discard wider-world change before its pathway could be judged.
- **Matilda-Jev as the default.** It isn't free to run, and needs a security exception.
- **The decision model over every item on CPU.** At about 5 s an item, 150k items take about 9 days.
- **TPUs.** Nothing in the stack targets them.

**Checked:**
- **Free decision model.** `scripts/probe_jevstyle.py` ran `Jev-Style-0.8B-Decision-v3` (Q4_K_M, llama.cpp at
  `441df11`) on this session's 4 CPUs.
  - Scorer peak about 1,711 MB, plus 237 MB of Python.
  - About 5.1 s per short item with 7 questions; 88 s for an 8,189-token state with 7 questions.
  - On six test sentences it ranked relevant items above irrelevant ones, but its probabilities were low (an
    AI-inventorship ruling scored 0.29 on P3), and it misplaced one origin. So its outputs are suggestions, to be
    recalibrated on the owner's labels.
  - The model's Python wrapper and C++ scorer were read before running: no network calls; it launches only the local
    scorer.
- **Matilda-Jev's** model cards (v1 and FP4) were read on Hugging Face.
- **Repo visibility:** public, via the GitHub API.
- **The connected Cloudflare account has no R2 buckets.**
- **Reachability from the build environment:**
  - ABS, legislation.gov.au, WIPO, IP Australia, Hugging Face and Kaggle answered 200;
  - OpenAlex and GDELT answered 429 (OpenAlex needs a key);
  - APH and OpenAustralia answered 403 with a Cloudflare bot challenge;
  - CSIRO reset the connection.
- **GCP** has no credentials in this environment.
- **GitHub Actions:** GitHub's docs say standard runners are free for public repositories. The runner hardware is to
  confirm on day 1.
- **Colab:** the free tier gives a T4, with sessions of at most about 12 hours (third-party summaries of Google's
  FAQ).
- **The diagram** renders with mermaid-cli 11.4.2.

**Spend:** $0.

**Consequences.**
- Nothing is built.
- For the owner, design §15:
  1. compute option A or B;
  2. the questions;
  3. the five territories;
  4. a yes to create the R2 bucket, then an R2 token as repo secrets;
  5. an OpenAlex key (and GCP only for option B or BigQuery);
  6. who reviews and labels;
  7. comfort with the public repo.

---

## D-005 — The owner approves v0.3's direction, adopts the four outside-in questions, and reviews alone; an explainer of the mining (2026-10-09)

**Context.** The owner replied to v0.3: "Very happy with basically all of that." They asked:
- why an embedding model can't be used on Kaggle;
- how the process works ("I've not done data mining before… I'm imagining we'd need to create an embedding and then
  cluster them by k-means or something like that?");
- what the 200 items to label would look like.

They also said that it's just them at this stage.

**Decision (owner).**
- The direction of design v0.3 is approved.
- **The four outside-in questions are adopted** ("Absolutely bang on").
- **The owner is the only reviewer and labeller,** for now.

**Settled in the build (Claude), following from these:**
- **A misunderstanding corrected.** Embeddings *can* run on Kaggle, and v0.3 already used Colab and Kaggle for the
  backfill. What can't run there is Matilda-Jev (too large) or anything on TPUs. Design §4.1 now names the free
  Kaggle or Colab GPU as the default place for the embedding backfill, with weekly new items on the Actions runner.
- **Two-stage review for one person.**
  - Triage: up to 40 candidates at about 1 to 2 minutes each, choosing keep, park or reject.
  - Deep review: the 8 to 10 kept, at about 15 to 20 minutes each.
  - About 3 to 4 hours a round, against about 10 hours for 40 full dossiers.
- **Labelling for one person.**
  - About 200 items: about 150 stratified by source type, about 50 the tagger is least sure of, and about 10 hidden
    repeats.
  - The repeats measure self-consistency, which replaces two-annotator agreement.
  - Four menu answers per item: mainly about (PESTLE), ring, territories, usable. About 30 seconds an item, so 1.5 to
    2 hours in sittings.
- **The explainer** `docs/mining-explained.md` and the demo `scripts/demo_embed_cluster.py`:
  - the demo embeds 28 made-up headlines with `bge-small-en-v1.5`, chooses k by silhouette (k=5, at 0.167), names
    clusters by class-based TF-IDF, ranks novelty by distance from each cluster's centre, and lists nearest
    neighbours;
  - **result:** the four planted themes mostly came back, and all four planted odd ones out were among the five worst
    fits;
  - **the limit it shows:** k-means put the odd ones into a meaningless grab-bag cluster. This is why the design keeps
    HDBSCAN beside it, a stability check, and novelty as a signal.

**Spend:** $0.

**Consequences.**
- For the owner, design §15:
  1. compute option A or B;
  2. the five territories;
  3. a yes to create the R2 bucket, then an R2 token as repo secrets;
  4. an OpenAlex key;
  5. comfort with the public repo;
  6. the labelling format: a spreadsheet, or a phone page.

---

## D-006 — Option A, a public repo, spreadsheet labelling, the R2 bucket created, and the five Growth Territories turned into search terms (2026-10-10)

**Context.** The owner answered the open items in design §15:
- "option A";
- "Yes, please create the R2 bucket";
- the repo "can/should be public";
- "Spreadsheet will be better".

They supplied five Growth Territories, each with an aim, "imagine a world where", what has recently changed, the jobs
to be done, and a 2022 "why now" statement. They asked for search terms to be created from that context, and where
the OpenAlex key should go.

**Decision (owner).**
- **Compute:** option A (GitHub Actions and R2).
- **Repo:** public.
- **Labelling:** by spreadsheet.
- **Bucket:** create the R2 bucket.
- **The territories:** T1 Protect Australian IP; T2 Empower others; T3 Amplify Australian IP; T4 Cultivate our
  ecosystem; T5 Revisit our purpose.

**Done, and settled in the build (Claude):**
- **The bucket `moria` was created** through the connected Cloudflare tool, and confirmed with a read-back. It is
  private (no public access), Standard storage, `ENAM` location (Eastern North America, near the Actions runners),
  default jurisdiction, created 2026-10-10T16:58:02Z.
- **`config/territories.yaml` (public)** holds, for each territory:
  - a description for similarity tagging;
  - search terms in three rings (about 120 core and adjacent phrases, plus wider-world forces);
  - exclusions and search rules: never a bare "IP"; both "trade mark" and "trademark"; each query run worldwide and in
    Australian sources;
  - the main pathways;
  - the IP RAPID indicators to compute.
- **The owner's verbatim context is kept out of the public repo,** in `config/territories.context.yaml`, which is
  git-ignored and destined for the private bucket. It includes internal findings (for example the IP First Response
  insights and customer-testing results). Publishing it would be outward-facing and irreversible, and the owner's yes
  covered the design, not this text. **For the owner:** may it be published?
- **A fifth use of territories:** a "what has changed since 2022" note per territory, testing each 2022 "why now" claim
  against 2022–2026 data.
- **Where keys go** (`docs/setup.md`): wherever the code that uses them runs.
  - GitHub Actions secrets: for the scheduled jobs.
  - The Claude Code environment's network secrets or environment variables: for building and testing.
  - Kaggle or Colab secrets, later.
  - The OpenAlex key and the three R2 values go in **both** Actions and the Claude Code environment, under
    `OPENALEX_API_KEY`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`.

**Checked:**
- **GDELT and the terms:** a check of all 122 core and adjacent terms against GDELT was attempted from this session.
  - Calls took about 20 s each.
  - Even when paced at one start every 5.5 s, they drew HTTP 429 after the first call. That call returned zero
    results for "intellectual property enforcement", so it isn't trusted.
  - The check was stopped. It becomes `moria terms check` on day 2, run from the Actions runners.
- **R2 from this session:** a TLS connection to an R2 endpoint with a placeholder account ID failed the handshake. It
  is retested once the real account ID is in the environment.

**Spend:** $0. R2 storage is empty, within the free tier.

**Consequences.**
- **For the owner:**
  1. the R2 token and the OpenAlex key, in both places;
  2. whether the territory context may be public;
  3. any edits to the search terms;
  4. a go for day 1, whose skeleton needs no keys.

---

## D-007 — Day 1 built: skeleton, store, manifests, polite HTTP, five daily collectors, the environment check, workflows (2026-10-10)

**Context.** The owner said "Yes, start day 1", and "Keep it private for now" for the territory context (D-006).

**Decision (owner: start day 1, keep the context private; the details below settled in the build).**
- **Stack.** Python 3.11; uv with a committed `uv.lock`; ruff (line length 120; rule sets E, F, W, I, B, UP, SIM,
  RUF); pytest. One package `src/moria`, with a typer CLI `moria`. Dependencies: boto3, defusedxml, httpx, pydantic,
  pyyaml, typer and zstandard.
- **Config.** `config/moria.yaml`, `config/sources/*.yaml` (source cards), `config/territories.yaml` and
  `config/themes.yaml`, validated by pydantic with unknown keys as errors. Validation caught a real bug on the first
  run: search rules containing `: ` had been parsed as mappings. They are now quoted.
- **The store.** It writes either to R2 through its S3-compatible API (credentials only from the environment) or to
  a local directory with the same layout (`data/store/`, git-ignored). Writes are atomic. `raw/` and `manifests/`
  are immutable: overwriting fails loudly.
- **Records.**
  - The evidence envelope follows design §6.1, including `event_at` against `observable_at`.
  - `evidence_id` is the SHA-256 of provider, record id and content hash.
  - Raw bundles are one zstd JSON-lines object per source per run, sorted, so the same records give the same bytes.
- **Manifests.** One per run, failed runs included. Each holds the outputs with SHA-256, counts, warnings, the
  config hash, the git commit and dirty flag, and package versions.
- **Ingestion monitors.** One entry per run: records against the card's expected band, flagged
  `below_expected` or `above_expected`.
- **The HTTP client.**
  - An identifying user agent and a minimum interval per host (GDELT at 5.5 s).
  - Retries with backoff that honour `Retry-After`.
  - robots.txt for web pages.
  - Errors name host and path only, never query strings, which may carry keys.
- **Collectors:**
  - `gdelt` (41 balanced query groups of up to 6 phrases; for each, an article list plus daily volumes worldwide and
    from Australian sources);
  - `legislation` (the Federal Register of Legislation's OData `Versions` by `registeredAt`, and `Titles` by
    `asMadeRegisteredAt`. The API rejects a `Z` suffix, so datetimes are sent without a zone);
  - `sitemap` (IP Australia; extracted text and metadata, plus the original HTML's SHA-256 and size, not the full
    HTML. Pages can exceed 500 KB, and the free storage is 10 GB);
  - `feed` (RSS and Atom: WIPO press, UKIPO news).
- **`moria env-check`** reports each secret as present or missing, then makes one cheap call to R2, OpenAlex, GDELT
  and each source. `--require` turns chosen checks into a gate (exit 2).
- **Workflows.**
  - `ci.yml`: lint, format and tests on every push and PR. No secrets.
  - `collect-daily.yml`: 02:23 UTC daily and on demand; the bucket check gates collection. Secrets come only from
    Actions secrets.
  - `probe.yml`: the memory probe on a real runner, with results in the job summary.
- **`CLAUDE.md`** is the rulebook from now on.

**Rejected:**
- **Storing full HTML** of web pages: storage, for little analytic gain. The hash keeps provenance.
- **GDELT exclusion terms inside queries:** the negation syntax is unverified. Exclusions are applied at
  normalisation instead.
- **The `astral-sh/setup-uv` action:** pinning its version tag couldn't be verified from here. Workflows install uv
  with pip on a pinned Python 3.11.

**Checked:**
- **Tests:** 17 pass, lint and format are clean, and CI makes no network calls.
- **Real data, local store, 2026-10-10:**

  | Source | Day | Result |
  |---|---|---|
  | `legislation_frl` | 2026-10-09 | 16 records |
  | `wipo_press`, `ukipo_news`, `ipaustralia_site` | 2026-10-09 | 0 records, correctly. Their newest items are dated 2026-09-29, 2026-09-17 and 2026-10-06. |
  | `wipo_press` | 2026-09-29 | 1 record (the Global Innovation Index 2026 release) |
  | `ukipo_news` | 2026-09-17 | 1 record |
  | `ipaustralia_site` | 2026-10-06 | 2 pages: 12,544 and 1,712 characters of extracted text |
  | `gdelt_news` | 2026-10-09 | **Failed:** HTTP 429 from this session's shared network exit, after 4 attempts with backoff. Its manifest was written, and the command exited 2. It is expected to work from Actions runners; unverified until the first scheduled run. |

- **`moria env-check` without keys:** every secret reported missing (no values), sources HTTP 200, GDELT 429.

**Spend:** $0.

**Consequences.**
- **The schedule starts only from the default branch,** so this branch must be merged to `main`.
- **The first real run needs the four secrets** in GitHub Actions.
- **For the owner:**
  1. add the secrets (`docs/setup.md`);
  2. merge this branch (or ask for a pull request) so `collect-daily` starts;
  3. after the merge, run `collect-daily` once by hand from the Actions tab, to confirm R2 writes and GDELT from a
     runner.

## D-008 — The memory probe on the target runner: 235 to 603 MB peaks; 3 to 6 times faster than the session machine (2026-10-10)

**Context.** Day 1's "done when" included probe numbers from a real runner (design §4.2, §13). The design's numbers
came from this session's machine, not from the machine that will run the jobs (option A, D-006).

**Decision (settled in the build: a measurement, nothing to approve).** The runner numbers replace the session
numbers for planning. They are in design §4.2. Job sizing assumes a 4-vCPU, 16 GB GitHub-hosted runner.

**Checked:**
- **Probe run** [38072692475](https://github.com/Thomas-Amann-IPAustralia/Moria/actions/runs/38072692475):
  `ubuntu-latest`, 4 vCPUs (AMD EPYC 9V45), 15,989 MB RAM, 3 GB swap.
- **Peaks:** 235 to 603 MB for every planned workload. The ruled-out hashed NMF peaked at 860 MB.
- **Speed:** 3 to 6 times faster than the session machine. Embeddings ran at 64.1 texts a second on one thread, so a
  backfill of about 150k items takes about 40 minutes.
- **CI run** [38072692650](https://github.com/Thomas-Amann-IPAustralia/Moria/actions/runs/38072692650) passed:
  lint, format and 17 tests.
- **A warning, not a failure:** GitHub warns that `actions/checkout@v4` and `actions/setup-python@v5` run on Node 20,
  which it is deprecating. They still run. Move to the next major versions when GitHub's deadline is close.

**Not yet measured:** the decision model (`Jev-Style-0.8B-Decision-v3`) on a runner. That is day 3.

**Spend:** $0.

**Consequences.**
- No job needs the 1 GB VM. The BM25 index (603 MB on the runner) would not fit it reliably anyway.
- Memory limits inside jobs (DuckDB's `memory_limit`) stay, so jobs also run on smaller machines.

## D-009 — GDELT's API throttles shared cloud addresses; take GDELT from its bulk files instead; progress logs (2026-10-12)

**Context.** The first `collect-daily` run that reached the bucket (run
[38159541723](https://github.com/Thomas-Amann-IPAustralia/Moria/actions/runs/38159541723), attempt 2) passed, but
`gdelt_news` took 93 minutes and 35 of its 41 query groups failed with HTTP 429 after 4 attempts each: 246 requests,
about one every 22 seconds, far slower than GDELT's limit of one every 5 seconds. The Actions log showed nothing
while it ran, so it looked hung.

**Cause (measured).**
- GDELT's DOC API limits by IP address. GitHub runners and this session leave through shared cloud addresses, so other
  users' traffic counts against Moria's allowance. From this session, the first request after hours of silence was
  refused at once; later requests took 7 to 16 seconds each and failed intermittently. Pacing cannot fix a limit that
  other users spend.
- GDELT's 429 answer says: "All high-traffic users should switch to our ngrams dataset", or contact GDELT for larger
  queries.
- GDELT's bulk files (`data.gdeltproject.org/gdeltv2/`) are a static file server with no such limit. From this session
  the 96 Global Knowledge Graph (GKG) files for 2026-10-10 (268 MB zipped) downloaded in 28 seconds without a refusal.
  The day has 64,598 English web documents, each with its URL, source domain and page title; 2,402 come from `.au`
  domains. Matching all 41 groups' phrases against the titles took 17 seconds.
- **Comparison, same day.** Where the API answered, title matches in GKG were of the same order or higher (for example
  `theme:technology_general` 29 API articles against 36 GKG titles; `theme:climate_energy_resources` 18 against 34).
  Territory groups are sparse either way (0 to 11 a day).

**Decision (a recommendation; the owner decides adoption).**
- Replace the DOC API calls in `gdelt_news` with a GKG bulk-file adapter: download the day's 96 GKG files, keep only
  web documents whose title (or URL) matches a query group, and store their URL, domain, title, time and GKG metadata
  (themes, tone). Never store GKG's `Quotations` field: it is article text. Daily volumes become exact counts of
  matching documents over all documents, worldwide and for `.au` domains.
- Trade-offs: titles, not full text, are searched, so recall per article is lower; "Australian sources" means `.au`
  domains rather than GDELT's own country mapping; a day costs about 270 MB of download (free). In return: no rate
  limit, no 250-article cap, an exact denominator, and a run of about a minute rather than 90.
- Not recommended: a residential proxy. It would not be needed, it would get round a limit GDELT asks heavy users to
  respect, and the reputable providers offer paid trials rather than free tiers.
- Optional, free: write to GDELT asking about an allowance for the DOC API, should full-text search be wanted later.

**Settled in the build (logging; nothing to approve).**
- Every HTTP attempt logs its host and path (never the query string), status, time taken and attempt number. Every
  retry logs its wait. Each source logs a start line and a finish line with its time, records and request outcomes.
  GDELT logs `[i/n]` progress per query group. Logs go to stderr with UTC timestamps; `moria --quiet` keeps warnings
  and errors only. `collect-daily.yml` sets `PYTHONUNBUFFERED=1` so lines appear as they happen.
- Manifests count request outcomes (`requests_http_200`, `requests_http_429`, `requests_error_<name>`).
- The client no longer waits after its last failed attempt. That wait was 40 seconds per failed GDELT group.

**Spend:** $0.

## D-010 — GDELT from GKG bulk files: built and run; quotations searched, never stored; the DOC adapter's partial-group bug fixed (2026-10-12)

**Context.** The owner adopted D-009 ("Approved, build the GKG bulk-file collector") and asked for the separate bug to
be fixed. They also asked whether quotations deserve more than being dropped: keywords from YAKE before dropping
them, or using them as context for the embeddings and dropping them afterwards. They assumed the reason for dropping
was size.

**Decision (owner: build it, fix the bug; the details below settled in the build).**
- **`gdelt_news` uses the new `gdelt_gkg` adapter** (`src/moria/collectors/gkg.py`). It downloads the day's 96 GKG 2.1
  files (one per 15 minutes, stamped inside the UTC day) and reads every English web document once. A document is
  kept when a query-group phrase appears, as whole words, in its title, URL, quotations or named entities. A phrase
  matches regardless of case, and spaces, hyphens and underscores are interchangeable. Duplicate URLs count once.
- **Each kept document stores:** URL, domain, the `.au` flag, title (capped at 500 characters), GDELT's timestamp
  (`observable_at`) and the page's publication time (`event_at`, when GDELT has it), every group and phrase matched
  with the fields it matched in, and GDELT's metadata derived from the full text: themes, organisations, location
  countries, tone and word count. It also stores whether the document had quotations.
- **Each group stores two volumes a day:** worldwide English and `.au` domains. Each is the count of matching
  documents against every document read, with matches by field and the number of files read.
- **Fails loudly** when more than 4 of the 96 files are missing (GDELT sometimes skips one), or when a file is not a
  valid zip with exactly one member. A missing file within the allowance is a warning.
- **Not stored:** quotations, person names and page authors.
- **`moria env-check`** now probes `data.gdeltproject.org` instead of the DOC API.
- **The DOC API adapter (`gdelt`) stays, unused.** Its bug is fixed: a group whose later call failed used to keep its
  article records although the group was reported as failed. A group's records are now kept only when every call
  for it succeeds.

**Quotations: searched in memory, never stored.**
- The reason they aren't stored is the licence, not size: design §12 stores news as titles and URLs, because article
  text belongs to its publishers. Size would be no issue. 588 of the 2,294 matched documents on 2026-10-10 had
  quotations, about 140 characters each: under 100 KB a day, beside a 523 KB bundle.
- Searching them costs nothing and adds recall: on 2026-10-10, 107 documents matched in quotations, 75 of them
  nowhere else (3% of matches; 4 of 222 territory-group documents).
- **YAKE over quotations: not now.** GKG already gives what YAKE would, and better, because GDELT derives it from the
  whole article rather than a sentence or two: themes, organisations and named entities. Named entities are the
  strongest matching field (1,619 matches; 1,136 found nowhere else). Keywords from about 140 characters would mostly
  repeat those words. YAKE remains a deterministic, model-free option if the labels later show a gap.
- **Quotations as embedding context: no.**
  - Embeddings are day 3, a separate stage that reads the raw bundles. Feeding it quotations would mean storing
    article text in an immutable bundle, which the rule forbids, or embedding during collection, which breaks
    "no model calls in collection".
  - Only about a quarter of documents have quotations, so the embeddings would mix title-only and title-plus-quote
    inputs, which skews similarity.
  - Day 3 can embed the title with GDELT's derived metadata instead: the same input for every document.

**Checked:**
- **Local run, 2026-10-10:** 96 files, 64,598 documents (2,402 `.au`), 2,294 matched, 2,376 records, 1m35s, 10 s of
  CPU (the rest is the one-second interval between downloads). 16 of 31 territory groups had matches; the DOC API
  gave 103 articles that day. Name-only matches were checked by phrase and look genuine ("extreme weather",
  "mental health", "climate change", "artificial intelligence"). Day 4's artefact checks should watch them anyway.
- **Runner:** `collect-daily` on this branch, run
  [38194632825](https://github.com/Thomas-Amann-IPAustralia/Moria/actions/runs/38194632825), 2026-10-11: 96 of 96
  files, 52,835 documents (2,771 `.au`), 1,249 matched, 1,331 records, 1m36s.
- **That run failed on another source:** `legislation_frl` timed out four times, 90 s each, between 02:10 and 02:17 UTC.
  From this session minutes later the same query took 62 s, then 0.5 s, so the API was briefly slow, not down.
- **Tests:** 25 pass, with hand-built GKG files (placeholder text).

**Spend:** $0.

**Consequences.**
- `moria terms check` (day 2) cannot read three months of GKG cheaply (about 24 GB), so it samples days.
- GKG runs back to 2015-02-19, so a news backfill is possible later.
- **For the owner:** a short slow spell at a source fails that source for the day, because retries give up after about
  7 minutes. A cheap remedy is for `collect-daily` to retry failed sources once at the end of the run.

## D-011 — Day 2 built: peer offices, OpenAlex and ABS counts, the IP RAPID lake with names hashed, weekly collection; BigQuery waits on a GCP project (2026-10-12)

**Context.** The owner asked: "I would like you to commence the Day 2 build" (design §13, day 2: IP RAPID, ABS
headline series, BigQuery CPC counts, OpenAlex whole-taxonomy counts, the foresight syntheses and the baseline draft,
peer offices, `moria terms check`). All four keys were present in this session, and R2 and OpenAlex answered
`moria env-check`. The terms check is D-012; the syntheses and the baseline are D-013.

**Decision (owner: start day 2; the details below settled in the build).**
- **Peer offices, daily** (existing adapters): `epo_news`, `epo_boards_of_appeal`, `iponz_news` and `cipo_news`
  (feeds), and `uspto_news` and `ipos_news` (sitemaps). Each office's terms were read before any text was stored:
  - USPTO: public domain (US federal works), so page text is stored;
  - IPONZ: reproduction for in-house use is allowed, so summaries are stored;
  - IPOS: reproduction is forbidden without authorisation, so titles, links and dates only (new switch
    `store_text: false`);
  - EPO and CIPO: no reuse licence found for web text (Canada.ca's terms page doesn't answer from here), so titles,
    links and dates only (new switch `keep_summary: false`), until confirmed.
  - Not added: EUIPO and JPO (HTTP 403 to this session), KIPO (no feed; an HTML list only).
- **Licences confirmed** for day 1's cards (handover open item 3): WIPO's online content is CC BY 4.0; the Federal
  Register of Legislation's content is CC BY 4.0; IP Australia's website is CC BY 4.0.
- **OpenAlex whole-taxonomy counts, weekly** (`openalex_counts`): works by primary topic at all four levels (4
  domains, 26 fields, 252 subfields, about 4,400 topics), each year from 2010 and each of the last 36 months,
  worldwide and with an author at an Australian institution, by cursor-paged `group_by`.
  - **Research output types only** (article, review, preprint, conference paper, book, chapter, dissertation,
    report). The first full run counted every type and found 33.0M works dated 2026 against 14.8M for 2025: 18.9M
    of them datasets (1.9M in 2025), a bulk ingest that would read as a research surge.
  - **The free budget is guarded in code:** the key goes in a header, never a URL; the run reads the day's credits
    from the free `/rate-limit` endpoint first and refuses to start if its estimate would leave under 1,000; it
    stops at the same reserve; and it refuses a key with a prepaid balance, so it can never be billed.
- **ABS headline series, weekly** (`abs_headline`): eleven SDMX queries, chosen and tested one by one against the API:
  population by single year of age, components of population change, labour force, job vacancies, the wage price
  index, the CPI (the new monthly CPI; the old monthly indicator `CPI_M` ends 2025-09), national accounts and
  productivity, output by industry, industry structure, trade in services by partner country (charges for the use of
  IP and its parts, computer and R&D services) and business innovation. One record per series with all its
  observations; a revised series gets a new evidence id, an unchanged one keeps its id.
  - Left out: business turnover (ends 2025-09). Business entries and exits (CABEE) and business R&D (BERD) are
    spreadsheet releases, not in the API.
- **IP RAPID, weekly** (`moria ipr refresh`, also run by `collect-weekly`):
  - The 1.35 GB zip is downloaded by stream, hashed, and read one table at a time. DuckDB converts each CSV to typed
    zstd Parquet (dates by strict `strptime`; flags as booleans). The CSV escapes quotes with a backslash.
  - **Privacy, inside the conversion query, before anything is written:** every party that is not an organisation
    (individuals, and parties with no type) has its name replaced by `'sha256:' + sha256('moria-ipr-person-v1|' +
    lower-cased name with spaces collapsed)`, and its postcode dropped; the state is kept, and so is IP Australia's
    own `party_id`. Every table's columns are checked against the published schema first, so a renamed name column
    fails the run rather than slipping past the hashing.
  - The hash pseudonymises; it does not anonymise: anyone holding the public file can hash its names too. Its
    purpose is that Moria's lake and outputs never carry a person's name. A secret key (HMAC) would add little while
    the source is public; it can be added if the owner wants it.
  - **The lake:** a base about quarterly (`rebase_days: 91`), and weekly deltas against it (`EXCEPT ALL` both ways,
    `_change` added or removed). A base is about 1.0 GB, so weekly full copies would fill the free 10 GB in about
    ten weeks. The zip is not kept; its SHA-256 and the catalogue's metadata go in an immutable release manifest.
- **BigQuery patent counts** (`patent_cpc_counts`, monthly): patent families by CPC subclass and earliest priority
  year, worldwide and with an Australian member, in one aggregate query on Google Patents Public Datasets. Built and
  tested, not run: **no GCP project or credentials exist yet.**
  - The card defaults to `dry_run: true`: the run records BigQuery's byte estimate in its manifest and stops.
  - Every real query carries `maximumBytesBilled` (200 GB; the free tier is 1 TiB a month).
  - The recommended project is a **BigQuery sandbox with no billing account**, so nothing can be billed at all
    (`docs/setup.md`, six steps).
- **Peer offices' strategies** (`peer_office_strategies`, documents read once a year): the UKIPO's Corporate Plan
  2026 to 2027 (OGL, text stored), the EPO's Strategic Plan 2028 (metadata only) and the USPTO's strategy page
  (public domain).
- **Collection:** `moria collect-weekly` and `collect-weekly.yml` (Mondays 03:41 UTC, after IP Australia rebuilds
  IP RAPID and OpenAlex's budget resets); `collect-source.yml` collects one source by hand on a runner; `moria census`
  writes aggregate-only reports to `reports/census/`.
- **Infrastructure:** streamed downloads (`PoliteClient.download`) and POST with headers; `put_file` and `get_file`
  on both stores (R2 through boto3's multipart transfer); collectors may add their own manifest counts (OpenAlex
  credits, BigQuery bytes). New dependencies: duckdb, pypdf and google-auth (which brings cryptography).

**Rejected, a line each:**
- **Storing the IP RAPID zip, or a full weekly lake copy:** storage (above).
- **DuckDB's `CAST` for dates:** it is lenient (`'1993-02-3x'` becomes 1993-02-03). Strict `strptime` fails loudly.
- **Counting every OpenAlex work type:** the 2026 dataset ingest (above).
- **A browser user agent to get past the sites that refuse this session:** Moria identifies itself honestly; the
  blocks are reported as gaps.

**Checked:**
- **Tests:** 62 pass (25 at day 1), with hand-built replicas of every format: SDMX-CSV, OpenAlex `group_by` pages,
  a six-table IP RAPID zip, BigQuery's REST answers, a one-page PDF. Lint and format clean; CI green on the branch.
- **Real runs, 2026-10-12** (each from a clean commit unless said):

  | Source | Result |
  |---|---|
  | `ip_rapid` | Release 2026-10-12 (zip 1,345,756,191 bytes, SHA-256 `6606cb1f…`): 92,704,007 rows in six tables, in 93 s; a 1.00 GB base. Into the bucket too (manifest `20261012T043841Z-79f13c49`, commit `cf7494d`), because data.gov.au offers only the latest release. |
  | IP RAPID privacy | Individuals: 1,816,579 rows, every name hashed, no postcode. No type: 17,874 rows, the same. Organisations: 10,672,114 rows, names kept. |
  | IP RAPID delta | On the real events table (49.3M rows), a planted release with 968 rows dropped and 2,000 added: the delta found exactly those, in 158 s, a 22 KB file. |
  | `openalex_counts` | 424 records (53 periods × 2 scopes × 4 levels), 2,424 credits, 2.2 MB; commit `906c7ea`; copied byte for byte into the bucket (hashes checked). Australia's share of works rose from 1.05% (2010) to 1.65% (2022), then 1.35% (2025). |
  | `abs_headline` | 11 queries, 839 series, 49,335 observations, 0.3 MB, 18 s; into the bucket (manifest `20261012T050437Z-0ce6d86c`). |
  | Peer offices | Each collected locally from `047b918`, for 2026-10-11 and for a day with a known item: EPO 1, EPO Boards of Appeal 1, IPONZ 1, CIPO 1 (its newest item is 2025-11-26), USPTO 2, IPOS 1 (title only). USPTO's sitemap lists removed pages: each 404 is a warning. |
  | `peer_office_strategies` | 3 documents into the bucket (manifest `20261012T051747Z-7ae74cfb`): the UKIPO's plan (34,066 characters, text stored), and the EPO's and USPTO's pages, which are short landing pages (about 2,000 characters each; the EPO's as metadata only). Their full plans are separate files, to add. |
  | `patent_cpc_counts` | Not run: no GCP project. |

- **Census reports** for the new sources: `reports/census/*.md`. Sentinel dates in IP RAPID are few (for example 101
  `effective_from_date` values of 1800-01-01).
- **Bucket:** 1.00 GB of the free 10 GB, almost all the IP RAPID base.

**Runs, disclosed in order:**
- The first full OpenAlex run counted every work type and started before its code was committed, so its manifest
  is dirty. It found the dataset ingest and is superseded by the filtered run from `906c7ea`.
- The first ABS run (04:18) also preceded its commit; the bucket's copy is a re-run from a clean commit.
- The first IP RAPID attempt never started: the shell wrapper called a missing `time` binary. The ingest then ran
  as recorded.
- The peer offices were first collected as smoke tests before their cards were committed (dirty manifests, local
  store); the runs above repeat them from a clean commit, with the same counts.

**Spend:** $0. OpenAlex used 5,759 of the day's free 10,000 credits, about 4,900 of them by this session (853 were
used before it began); the key's prepaid balance is $0, so it cannot be billed. R2: 1.00 GB stored, within the free
tier. BigQuery: none. GKG: about 7 GB downloaded for two terms checks, free.

**Consequences.**
- After the merge, `collect-daily` collects eleven sources and `collect-weekly` three. The first weekly run writes a
  delta against the 2026-10-12 base, if IP Australia has published a new release.
- `ipr metrics` (demand, timeliness and outcome measures from IP RAPID) comes with day 3's normalisation.
- **For the owner:**
  1. **Merge this branch** (or ask for a pull request): the weekly schedule and the new daily sources start from
     `main`.
  2. **The daily schedule didn't fire.** `collect-daily` has run only by hand (twice): no run appeared at or after
     02:23 UTC today (checked at 08:57 UTC), although the workflow has been on `main` since 2026-10-11 17:21 UTC.
     GitHub drops scheduled runs under load, and a schedule sometimes registers only once its file is saved again
     on `main`. If tomorrow's run doesn't appear either, I'll put a one-line change to the workflow in a pull request
     for you to merge.
  3. **BigQuery:** create a sandbox project and a key (`docs/setup.md`, about ten minutes), then run `collect-source`
     with `patent_cpc_counts`. I'll report the dry run's estimate; you say whether to switch the dry run off.
  4. **Your territory context** is not in this container or the bucket (it was in day 1's container only). Paste it
     again when convenient, and I'll put it in the bucket at `interpretation/territories/context.yaml`.
  5. **Optional:** EPO's and Canada.ca's terms for storing their text, if you know them; until then, titles only.

## D-012 — The terms check: 92 of 207 terms never match, in either spelling; names-only matches are often incidental, which corrects D-010's reading (2026-10-12)

**Context.** Design §2.4: every term is checked on day 2 for its volume worldwide and in Australian sources over the
last three months, and a sample of its hits is read for noise; noisy terms are narrowed or dropped ("Otherwise the
day-2 check prunes them", design §15). GDELT's API throttles cloud addresses (D-009), so the check reads GKG bulk
files, matching every term as the daily collector does.

**Decision (settled in the build, under the design's day-2 check; the recommendations on terms are the owner's to
adopt).**
- **`moria terms check`:** one GKG day a week for 13 weeks (2026-07-19 to 2026-10-11), every territory term and theme
  phrase, worldwide and for `.au` domains, with up to 12 hits per term kept by seeded reservoir sampling. The hit
  samples are news titles, so they stay in the bucket (`reports/terms-check/<run_id>.json`); the repo gets counts and
  triage flags only (`reports/terms-check.md`). `terms-check.yml` re-runs it by hand.
- **First run (matcher v1, run `20261012T044357Z-72f39b02`):** 686,681 English web documents (37,344 from `.au`
  domains); 207 distinct terms.
  - **94 terms never matched**, 23 more were rare (under one hit in five sampled days), 29 were names-heavy (over
    60% of hits only in GDELT's named entities), none was too broad. 50 of the 65 core (IP-language) territory terms
    never matched.
  - Of 18,191 term hits, 46% were names-only and 37% were in titles.
- **Diagnosis, from the silent list and from reading the samples:**
  1. **Whole-word matching missed plurals and US spellings** (a small effect, the second run shows). The terms are
     mostly in Australian spelling ("commercialisation", "monetisation", "organised crime", "population ageing")
     while most news is in US spelling, and a term in the singular missed the plural. The territories' search rule
     already asked for both spellings; the matcher didn't apply it.
  2. **Names-only matches are often incidental.** GDELT's named entities list proper names from the whole article,
     so a generic phrase matches inside unrelated names. In the samples, "industry association" hit stories naming
     some "…Industry Association"; "consumer protection" hit stories on other subjects; "recession", "open science",
     "open data", "infrastructure investment", "regional development", "migration policy", "venture capital" and
     "smart cities" were mostly off-topic. For proper nouns they do help: "online safety" (Australia's online
     safety regulator's actions), "First Nations", "consumer product safety" (US product recalls by the agency of
     that name). "research translation" was one syndicated story across 57 regional `.au` mastheads.
- **Changes (parser `gdelt-gkg-v2`; the card records the break):**
  - every phrase also matches in the other spelling (explicit word lists, -isation and -ization always, and -ise
    forms for known stems only, so words like "enterprise" are untouched) and with a plural last word; word order is
    not varied;
  - each group's daily volume also counts documents **about** it (a phrase in the title or URL) and
    **names-only** documents. `about_documents` is the series day 4's detectors should use; nothing is dropped.
- **Second run (matcher v2, run `20261012T050858Z-2e48c391`, commit `42be77e`), the same 13 days:**
  - **The variants added 2.5% of hits** (18,646 against 18,191), mostly to terms that already matched: "organised
    crime" 344 to 488 ("organized"), "defence industry" 46 to 106 ("defense"), "trade agreement" 364 to 447 and
    "skills shortage" 4 to 16 (plurals).
  - **Two silent terms matched:** "trade mark infringement" (6, as "trademark infringement") and "supply chain
    disruption" (1). **92 terms stay silent**, 49 of them core; 24 are rare and 29 names-heavy. So the silence is in
    the phrasing, not the spelling: "population ageing" has 2 hits in 13 days, and "patent monetisation" and
    "intellectual property commercialisation" none, in either spelling.
  - Of the hits, 45% are in a title or URL (about the term) and 46% are names-only.
  - The -isation rule committed after this run began (`831bd5e`) changes none of these 207 terms' variants
    (checked); the four new themes (24 phrases) are not yet checked.
- **Correction of D-010.** D-010 said name-only matches "were checked by phrase and look genuine". That came from a
  few spot checks of common phrases ("extreme weather", "mental health", "climate change", "artificial
  intelligence"). Twelve samples per term over thirteen days show they are often incidental for generic phrases.
  The named entities still add recall for proper nouns.

**Recommendations for the owner (the terms are yours; nothing is pruned without your yes):**
1. **Keep the silent terms.** A silent term costs nothing and can't add noise; it waits for a rare event, which is
   what weak signals are. Nothing needs dropping for noise either, now that the about series is separate.
2. **Add a broad IP-system theme**, so the core ring has a news volume of its own: for example "intellectual
   property", "patent", "trade mark", "copyright", "plant breeder's rights", "IP Australia", each checked for breadth
   first ("patent" also matches "patent leather"). Without it, the core ring's news rests on its 65 territory
   terms, 49 of which never match.
3. **Rephrase a few core terms the way news writes them,** for example "AI inventor" beside "AI inventorship" and
   "TRIPS waiver" beside "patent waiver" (both silent now). I can draft a list for you to edit.
4. The four new themes from the baseline (D-013, themes v2) are checked on the next run (`terms-check` on Actions).

**Spend:** $0 (about 7 GB of GKG files downloaded for the two runs; free).

**Consequences.** Volumes before 2026-10-12 aren't comparable with later ones (the card's `breaks`). Day 4's
detectors use `about_documents`; names-only counts feed the artefact checks.

## D-013 — The foresight syntheses: three of eight read; a 19-trend known-trends baseline drafted for the owner (2026-10-12)

**Context.** Day 2 includes "the foresight syntheses ingested and the baseline draft" (design §13). The baseline is
what is already widely expected: a candidate that only restates it is marked `already_known` at triage, and a
validated signal outside it and outside every Growth Territory counts towards the sprint's novelty test (design
§2.5, §11.1). The owner confirms the baseline before mining (design §2.6).

**Decision (a recommendation; the owner decides adoption).**
- **`foresight_syntheses`, a `documents` source read once** (a new `once` cadence keeps it out of the daily and weekly
  runs). It fetches PDF or HTML, caps size and pages, and stores page texts only where the document's own licence
  allows; otherwise the title, URL, hash, size and page count. Eight documents are listed:

  | Document | From the build session | Text stored |
  |---|---|---|
  | CSIRO, *Our Future World* (2022) | read (60 pages) | no: "all rights reserved" |
  | JRC, Megatrends Hub booklet (2018) | read (9 pages) | yes: the Commission's reuse policy |
  | Treasury, *Intergenerational Report 2023* | read (296 pages) | yes: CC BY 3.0 AU |
  | National Science and Research Priorities (2024) | refused: the connection drops after TLS | (CC BY 4.0 by search results) |
  | List of Critical Technologies in the National Interest | refused, the same | to confirm |
  | Australia's Net Zero Plan (2025) | refused, the same | (CC BY 4.0 by search results) |
  | 2026 National Defence Strategy (16 April 2026; supersedes the 2024 strategy the design names) | refused, the same | to confirm |
  | WEF, *Global Risks Report 2026* | HTTP 403 | no: WEF reserves rights (to confirm) |

  The three refusing sites (industry.gov.au, dcceew.gov.au, defence.gov.au) complete the TLS handshake and then
  close the connection; industry.gov.au also answered 503 to the fetch tool. It looks like a block on cloud
  addresses, like Parliament's (D-004). The OECD is left out until a specific publication is chosen.
- **`config/baseline.yaml`: 19 known trends, drafted from the three documents read.** Each trend cites the
  documents' own names for it, with paraphrased statements (no quotations, since CSIRO reserves its rights), PESTLE
  origins and rings. The CSIRO and IGR items were checked against their text; the JRC items are the booklet's 14
  names, and their statements are paraphrases of those names. Validated by pydantic: a trend may cite only a
  document that was read. `moria baseline` prints it.
  - KT01 to KT04, climate and environment: adaptation; the net zero transformation; resource scarcity;
    biodiversity loss.
  - KT05 and KT06: population ageing; rising demand for health, care and support.
  - KT07 to KT09: geopolitical competition and fragmentation; economic weight shifting east and south; a changing
    security paradigm.
  - KT10 and KT11: the digital and data economy; artificial intelligence and autonomous systems.
  - KT12 to KT19: the changing nature of work; diversifying education; inequalities; diversity, equity and
    transparency; urbanisation; consumerism; migration; new governing systems.
- **Themes v2** (`config/themes.yaml`): four wider-world themes for known trends the v1 themes missed: nature and
  circularity (KT03, KT04), the shift east and south (KT08), cities and consumption (KT16, KT17), and care and
  migration (KT06, KT18). 45 query groups in all; the terms check hasn't read the new themes yet (D-012).

**Checked:** the three documents went into the bucket (manifest `20261012T045244Z-7574c849`): CSIRO as metadata
only, the JRC booklet and the IGR with their page texts. Tests cover the adapter (a hand-built PDF, an HTML page, a
refused document, the size cap) and the baseline's citations.

**Spend:** $0.

**Consequences.**
- The five refused documents can be read from a runner (`collect-source` with `foresight_syntheses`), if the sites
  let runners through, or from files you download. Their trends are added to the baseline when read.
- Day 3 embeds the trend statements, so candidates can be compared with them.
- **For the owner:** confirm, edit or cut the 19 trends (about 15 minutes; `config/baseline.yaml`). In particular:
  are national priorities (the science priorities, critical technologies, net zero, defence) part of "already
  known", or should signals that confirm them still count as new evidence?

## D-014 — The owner's answers on day 2: the baseline confirmed, and known trends still count; synonyms and an IP-system theme; a document wishlist with owner uploads and a licence check (2026-10-12)

**Context.** The owner answered the day-2 report (D-011 to D-013) in one message:
- BigQuery: "I've added the credentials to Github Secrets. Are you SURE you mean the WHOLE JSON that downloaded?"
- The baseline: "19 intial trends confirmed." And: "just because trends are already 'known' in the sense of them
  being national priorities, it's entirely feasible that they may not be priorities or even front of mind for
  IPAVentures or IP Australia's strategic leadership. Hearing something is a priority and understanding its urgency
  are two very different things. Reinforcement of what is already known is still valuable. I'm sure we'll be adding
  several new trends over the next few days."
- Documents: "Are you able to produce a write a wishlist of the public documents in the Github repo and I can go to
  the sites and get the documents for you? I'll make sure to only upload them if their licensing allows and maybe
  you can run a check too so we can have it on record." EPO's and Canada.ca's terms: "I'll have a look when gathering
  the documents from your wish list. Please include it on the list so I don't forget."
- Terms: "For now, keep the search terms that never matched. We'll revisit the search strategy once we've got all of
  the plumbing and infrastructure set up." "Sure, please add a a broad IP-system theme so the core ring gets a news
  count of its own". "As long as the any new terms are treated as synonyms then sure, feel free to add terms the way
  news writes them."
- The owner pasted the territory context again.

**Decision (the owner's, in the words above; the details below were settled in the build).**
- **The baseline is confirmed:** `config/baseline.yaml` is `status: confirmed`, 19 trends. **A known trend is never a
  reason to reject a signal.** The design changes accordingly (§2.5, §2.6, §6, §11.1): `already_known` is no longer
  a rejection reason; a signal records its `baseline_relation`, `novel` or `reinforces` (with what it adds: pace,
  urgency, arrival in Australia or in the IP system); reinforcement is reported beside novelty. Novelty (the sprint's
  success test) is unchanged: outside both the baseline and every territory.
- **The silent terms stay.** No term is pruned; the search strategy is revisited once the machinery is built.
- **Synonyms, counted as the term** (`synonyms` in `config/territories.yaml` v2 and `config/themes.yaml` v3): 173
  wordings for 72 terms, drafted the way news writes them ("TRIPS waiver" for "patent waiver", "DABUS" and "AI
  inventor" for "AI inventorship", the singular of terms written in the plural). The terms themselves are unchanged.
  A synonym must be a new wording of exactly one term (validated); a match on it counts as the term, and the match
  record names it. Left out on purpose: boilerplate and figurative wordings ("registered trademark", "patent
  pending", "trademarked", "knock off") and "IP" wordings that are also networking terms.
- **An IP-system theme, `ip_system`, in the core ring:** intellectual property, patent, trade mark, copyright,
  registered design, plant breeders rights, geographical indications, intellectual property office, IP Australia,
  WIPO (with their synonyms). Themes gain a `rings` map (default wider world), and every volume record carries its
  group's ring. Parser `gdelt-gkg-v3`; the card records the break.
- **A wishlist, owner uploads, and a licence check** (`docs/wishlist.md`):
  - The owner downloads what the build session can't reach and puts it in the private bucket at
    `inbox/documents/<document id>.pdf` (or `.html`); never in the repo, which is public. The `documents` collector
    reads an upload instead of the URL, and the record says so (`obtained: owner_upload`).
  - **Every document's licence is checked:** its first six and last four pages are searched, in memory, for licence
    statements (Creative Commons with version, the Open Government Licence, the EU reuse notice, "all rights
    reserved", "no part may be reproduced", public domain). The statements and a verdict go in the record, the
    manifest and the census report (names only). A document that reserves its rights with no open licence is never
    stored as text, whatever its card says; `store_text: if_open_licence` stores text only when the document itself
    states an open licence. The refused foresight documents move to `if_open_licence`.
  - New card entries: the OECD *STI Outlook 2025* (the OECD publication for the baseline), the EPO's *Annual Work
    Plan 2026*, the EUIPO's *Strategic Plan 2030*, the JPO's *Status Report 2026* and CIPO's *2023-2028 Business
    Strategy*.
  - **Terms read for the owner to confirm:** the EPO's website terms of use, section 6 (read from here): its own
    information may be downloaded, printed and processed "for private and commercial purposes", displayed accurately
    and citing the website; third-party content, logos and images excluded. Canada.ca's terms (from search results;
    the site refuses this session): non-commercial reproduction "without charge or further permission", with title,
    author and a not-an-official-version statement. EPO and CIPO stay titles and links only until the owner confirms.
- **The territory context** is back in the private bucket (`interpretation/territories/context.yaml`, 8,486 bytes,
  hash checked) and in the git-ignored local file. It is not in the repo. The public wishlist leaves out the
  documents that the context cites, since listing them would hint at it; they are put to the owner in the chat.
- **BigQuery:** yes, the whole JSON key file, as downloaded (its private key, the account's email and the token
  address are all needed to sign in). The dry run waits on the merge: `collect-source` runs only from `main`.

**Rejected, a line each:**
- **Uploads to the repo:** it is public, so an upload would republish the document.
- **Adding news wordings as new terms:** the owner asked for synonyms; a synonym keeps the term list, and its
  counts, unchanged.
- **Trusting the cards' licences alone:** the check costs nothing and catches a document whose own notice disagrees.

**Checked:**
- **Tests:** 69 pass, with synonyms in the matcher and the terms check, validation of synonyms and theme rings,
  owner uploads, the licence patterns and the census across runs.
- **Third terms check** (run `20261012T131633Z-cdd72551`, commit `3485769`, the same 13 days as D-012): 239 terms.
  - On the 207 earlier terms: silent 92 to 75, rare 24 to 35, names-heavy 29 (unchanged). Core terms silent: 49 to
    38 of 65. 17 silent terms matched through a synonym, each a handful of times (for example "intellectual property
    enforcement" 3, "trade mark application" 3, "knock-off products" 5).
  - Synonyms added 140 documents that only they found (0.7% of hits). The largest by far: "geographical indication"
    in the singular (geographical indications 14 to 103 documents, mostly India's GI tags, in named entities).
  - The IP-system theme: at most about 16 documents a day are about one of its terms (title or URL; the sum over
    terms, which overlap), at most 59 a day mention one, and 0.2 a day in `.au` domains. "IP Australia" never
    appeared in the 13 sampled days.
  - Themes v2 (24 phrases): 3 silent (aged care workforce, deglobalisation, megacities), 1 rare.
  - **Read from the samples** (12 per term) for patent, trade mark, copyright and intellectual property: title or URL
    hits were on topic in 17 of 19; names-only hits in about 4 of 23. So `about_documents` stays the series to use
    (D-012). The synonym "takedown request" was off topic in all 4 samples (government content takedowns) and is
    removed (`c68f5af`, after the run).
- **Document runs** (commit `cc8c54f`, into the bucket): `peer_office_strategies` 6 records (manifest
  `20261012T132413Z-24fe112c`), `foresight_syntheses` 2 records (`20261012T132431Z-d312b25a`; CSIRO's site failed this
  time, its morning record stands). The licence check agrees with the cards for the UKIPO plan (Open Government
  Licence) and the Intergenerational Report (CC BY 3.0). For the JRC booklet it found CC BY 2.0 and CC BY-SA 2.0,
  most likely photo credits: the statements are evidence for a person, not a verdict. The EUIPO plan, the EPO's work
  plan and pages, CIPO's release and the USPTO page state none; the EUIPO plan's text is therefore not stored.
- The census of a document card across runs shows the newest record of each document.

**Runs and slips, disclosed:**
- Commit `97f02ad` went in while a census test failed in the full suite: the command piped pytest's output and lost
  its exit code. The test was order-dependent (two runs in one second); fixed in `87a3d3e`, which CI checks.
- The public terms report was regenerated from the run's own result after a formatting fix (one header line); its
  numbers are the run's.

**Spend:** $0. GKG: about 3.5 GB downloaded for the third check, free. OpenAlex: no credits used.

**Consequences.**
- After the merge: `collect-source` with `patent_cpc_counts` (the dry run), then with `foresight_syntheses` and
  `peer_office_strategies` once uploads are in the inbox.
- Day 3 reads `ring` from volume records and embeds the trend statements for `known_trend_match`.
- **For the owner:**
  1. **Merge this branch** (or ask for a pull request): the BigQuery dry run, the weekly schedule and the
     terms-check workflow all start from `main`.
  2. **The wishlist** (`docs/wishlist.md`): five foresight documents, two peer-office documents, WEF's two top-10
     lists pasted in the chat, and the EPO's and Canada.ca's terms to confirm.
  3. Whether the documents your territory context cites may go on the public wishlist.

## D-015 — The public documents the territory context cites go on the public wishlist; a pull request for days 1 and 2 (2026-10-12)

**Context.** The owner's territory context is private (D-006). It cites four public documents, and D-014 kept them off
the public wishlist because listing them hints at the context. Asked whether they could go on it, the owner said:
"Add them to the public wishlist then open a PR".

**Decision (the owner's).**
- **A new `documents` card, `territory_evidence`** (read once), and section 3 of `docs/wishlist.md`. Only the
  documents' titles, publishers and links are public, with a one-line description each; the context itself stays
  private. The documents:
  - the AIC's *Estimating the costs of serious and organised crime in Australia, 2020-21* (Statistical Report 38),
    and its newer edition, *2023-24* (Statistical Report 55): owner uploads (aic.gov.au refuses this session);
  - the Productivity Commission's *Innovation for the 98%*: the 2022 interim report and Volume 5 of the 2023 final
    report, fetched from here;
  - the *Patents Accessibility Review: Final report* (2021, offered as Word: saved as PDF for upload) and the
    Government's response (2022): owner uploads (industry.gov.au refuses this session);
  - IP Australia's *Australian IP Report 2026*, fetched from here.
- Text is stored only where the document states an open licence, except the IP Report: its PDF states none, and it
  is stored under IP Australia's website licence (CC BY 4.0, D-011), as IP Australia's pages already are.
- **A pull request** for the branch, as the owner asked.

**Checked:** both Productivity Commission PDFs state CC BY 4.0, so their text is stored (99 and 105 pages); the IP
Report (86 pages) states no licence anywhere in its text. Runs into the bucket: `20261012T140358Z-e1fa4b2e`
(commit `7cd731f`; the IP Report's text not stored) and `20261012T140936Z-1151738a` (commit `c7492f8`, stored).
`reports/census/territory_evidence.md`. Tests: 69 pass.

**Spend:** $0.

**Consequences.** The four uploads join the wishlist. The documents serve the territories' "what changed since 2022"
comparisons (design §2.4).

Next free decision number: D-016.

## D-016 — The Tier 1 cleanup before day 3: APH's RSS feeds and the Open Australian Legal Corpus; Pile of Law checked and discarded; Tier 2 waits (2026-10-12)

**Context.** The owner asked for every source not yet added and what each still needs. They suggested the Open
Australian Legal Corpus in lieu of AustLII, Pile of Law for its UN material, and Parliament's sites (ten APH and
ParlInfo addresses), with a scraper from another project for ParlInfo. The list, the checks and the open questions
are in `docs/sources-backlog.md`.

**Decision (the owner's).**
- **Scope:** "Lets not go for tier 2 stuff yet then. But I would like to clean up Tier 1 before we move to day 3
  work." The cleanup is §2 of `docs/sources-backlog.md` (T1 to T7, and W1 and W2, which wait on the owner). Tier 2
  stays "not to build yet".
- **The Open Australian Legal Corpus:** "Something is better than nothing, I bet there's still plenty we can learn
  from mining bits of it as required." Adopted as a once source in the lake, taken in parts. The default parts are
  Commonwealth legislation, the Federal Court and the High Court; that is a recommendation, which the owner may
  widen.
- **Pile of Law:** "Please double check whether it might [have useful sources] and if not, we can discard." Checked
  (below); discarded.
- **Parliament:** "Lets go with the RSS feeds and we can add the other stuff from them to the backlog." Five APH
  feeds join the cleanup (T1). ParlInfo, Hansard, the Library's pages, the other feeds and the statistics pages go to
  the backlog (L1 to L4).

**Checked (2026-10-12, from this session's cloud address, with Moria's user agent):**
- **APH:**
  - three Senate feeds answered: new inquiries (34 items), reports (134) and upcoming hearings (30);
  - the House and joint inquiry feeds answered, empty;
  - `www.aph.gov.au/robots.txt`, the Hansard page, the hearings page and Issues and Insights answered 403 ("Page
    Blocked by WAF");
  - ParlInfo, including its robots.txt and its Bills Digest feed, answered 403 with an Azure WAF JavaScript
    challenge.

  The site's licence, as quoted by the owner, is CC BY-NC-ND 4.0.
- **The corpus:** release 7.1.0, 232,560 documents in one 9.4 GB file, every source scraped on 10 March 2025, latest
  versions only. The collection is CC BY 4.0, but its documents keep their own terms. The Federal and High Courts
  allow unaltered reproduction for personal, non-commercial use or use within an organisation. NSW Caselaw requires
  compliance with suppression orders and no robots' indexing; it is left out by default.
- **Pile of Law** (dataset commit `2e96169e`): `undebates` (8,481 UN General Debate speeches, 1970–2020, 2.0% with an
  IP term), `ijc` (4,932 ICJ and PCIJ texts, 3.8%) and `tos` (50 terms of service, about 2014–2017) were read whole.
  The first 3,000 records of `uspto_oab`, `congressional_hearings`, `federal_register` and `eurlex` were read as
  samples. Each useful subset is a copy of an upstream Moria can read directly (USPTO open data, GovInfo, the Federal
  Register, EUR-Lex), and the copies end between 2019 and 2022. Counts only; no text was kept.
- **The shared scraper** was read, not run. Its stealth parts (a spoofed browser identity, hidden automation flags,
  timing-fingerprint evasion, proxy retries, an unpinned driver download) conflict with D-011 and are not adopted. Its
  text normalisation, trafilatura extraction, DOCX reading and block-page check may be reused. Its block signatures
  need narrowing first: APH's real RSS page contains "captcha".

**Rejected, a line each:**
- **Pile of Law:** copies of upstream sources, ending 2019–2022, under a stricter licence (CC BY-NC-SA 4.0), loaded
  by a third-party script.
- **The scraper's stealth path:** D-011; Moria identifies itself honestly.
- **Tier 2 now:** the owner's call above.

**Still open (the owner's):**
1. Whether Moria's use counts as non-commercial (APH; the Federal and High Courts' terms).
2. Whether APH summaries may be stored (titles, links and dates until then).
3. Asking APH for a route to ParlInfo (recommended).
4. Whether W1 and W2 hold up day 3. The recommendation: day 3 starts once T1 to T7 are done or are themselves waiting
   on an answer.

**Spend:** $0. About 75 MB of Pile of Law, and samples of four large subsets, were downloaded to the session's
scratch space for the counts, then deleted.

**Consequences.**
- The next session builds the Tier 1 cleanup, then day 3.
- `CLAUDE.md`'s scope and `docs/handover-day2.md` point at `docs/sources-backlog.md`.

Next free decision number: D-017.

## D-017 — The owner's answers on D-016: non-commercial research; APH summaries stored; ParlInfo later (2026-10-12)

**Context.** D-016 left four questions for the owner (`docs/sources-backlog.md`).

**Decision (the owner's).**
1. **NonCommercial:** "Yes, Moria's use would be considered non-commercial research purposes." This settles APH's
   CC BY-NC-ND 4.0 and the Federal and High Courts' terms in the Open Australian Legal Corpus.
2. **APH summaries:** "Yes it can." The five APH feed cards set `keep_summary: true`. Shared outputs still quote
   unaltered or link (NoDerivatives).
3. **ParlInfo:** "We'll address that later. We do not need permission to access the RSS feeds though." The ParlInfo
   route (L1) waits, and the feeds (T1) go ahead without asking APH.
4. **Whether W1 and W2 hold up day 3:** "I'll defer judgement for now." The recommendation in D-016 stands until the
   owner decides.

**Spend:** $0.

**Consequences.** `docs/sources-backlog.md` carries the answers. The Tier 1 cleanup's licence questions are settled.

Next free decision number: D-018.

## D-018 — The Tier 1 cleanup built: APH's feeds, the legal corpus, IP Australia's snapshot and PDFs, MOIP, WIPO's treaties and statistics, CABEE and BERD; EUIPO, JPO and the courts are gaps (2026-10-13)

**Context.** The owner asked: "Please finish adding all the sources that need to be added before Day 3 (as defined
in docs/sources-backlog.md)." That is T1 to T7 of the Tier 1 cleanup (D-016, D-017); W1 and W2 wait on the owner.

**Decision (the owner's request; the build choices are this session's and stand until the owner says otherwise).**
- **T1, APH:** five `feed` cards, daily, summaries kept (D-017), a 30-day lookback (items are dated by referral or
  tabling and may be added later). The feeds have no guids and repeat an inquiry's link, so an item's id is its link
  plus a hash of its title, date and summary. The hearings feed has no dates: each item is observable from the run
  that first sees it, and the whole feed is kept every run (parser `feed-v2`).
- **T2, the Open Australian Legal Corpus:** a bulk stage (`hf_corpus`, card `oalc`) into the lake, not raw bundles.
  The file is read at a pinned dataset commit, checked against its SHA-256 and its ten fields, and DuckDB keeps the
  three default parts (Commonwealth legislation, the Federal Court, the High Court) as Parquet at
  `lake/oalc/release=7.1.0/`. Each row carries its own licence, `event_at`, `observable_at` (judgments: the
  decision date; legislation: the scrape), its text's length and hash, and an evidence id. A release manifest,
  written last, marks the release as ingested. The day-3 slice for embeddings is unchanged (D-016).
- **T3, IP Australia:** `moria collect --backfill` takes a first snapshot (a sitemap's every page, up to 2,000; a
  feed's or list page's every item), and the full site snapshot is a backfill run of `ipaustralia_site`.
  `ipaustralia_publications` reads six PDFs its accountability pages link: the Strategic Corporate Plan 2026-27,
  the Annual Report 2024-25, the AI transparency statement, the Minister's statement of expectations, IP Australia's
  statement of intent and the cost recovery implementation statement.
- **T4, peer offices:** KIPO is now Korea's Ministry of Intellectual Property (MOIP). Its English news board has no
  feed, so a new `listpage` adapter reads its first page with a pattern (`moip_news`, daily). Its footer reserves all
  rights: titles, links and dates only. EUIPO and JPO are gaps (below).
- **T5, WIPO:** WIPO's robots.txt disallows its treaty notification pages, the newsletter archive's data and the IP
  Statistics Data Center. Allowed routes: WIPO Lex's notification list for each treaty (`wipo_treaty_notifications`,
  weekly, `listpage`, 26 treaties; Rome and Brussels have no list there), and the bulk indicator ZIPs on WIPO's
  statistics page (`wipo_ipstats`, a new `zip_csv` stage into the lake; unchanged files are skipped).
- **T6, ABS:** a new `xlsx` adapter (openpyxl, a new pinned dependency) and `abs_datacubes` (weekly): the workbooks
  on CABEE's and BERD's latest-release pages; each table one observation record kept as published (headings,
  sections, labelled rows, the ABS's symbols, notes), dated by the release date printed in the workbook. An
  unchanged table keeps its evidence id; turning tables into series is day 3's.
- **T7, courts:** nothing is collected. The Federal Court and AustLII refuse the build session and a runner (403), and
  the High Court times out, so post-March 2025 judgments and IP Australia's hearing decisions (on AustLII) wait on
  permission. A draft request for the owner is in `docs/sources-backlog.md`, T7.
- **Tools:** `moria discover` checks a source's addresses (status, type, item counts and dates, feed links; never
  text), and `collect-source` runs it from a runner (the source `discover`) or a backfill. `env-check` probes the new
  adapters. `moria census` has sections for list pages, data cubes, the corpus and bulk tables (counts only).

**Rejected, a line each:**
- **A browser identity to get past the 403s:** D-011; Moria names itself.
- **WIPO's notification pages, newsletter archive and IP Statistics Data Center:** robots.txt disallows them.
- **The EU's press-release feed as an EUIPO route:** it carried no EUIPO items.
- **Raw bundles for the corpus and WIPO's statistics:** 104,201 long texts and 6.2 million rows; the lake, as for IP
  RAPID.
- **Hugging Face's own Parquet copy of the corpus:** a conversion made by Hugging Face, not the release file whose
  hash the dataset publishes.
- **Interpreting ABS tables into series in the collector:** layouts vary (two-level headings, sections, footnotes);
  normalisation does it from a faithful record.

**Checked:**
- **Tests:** 87 pass (no network): the APH-like feed (shared links, undated items), backfill for feeds and
  sitemaps, list pages (a notification table, a news board, a layout change failing loudly), data cubes (headings,
  sections, symbols, notes, a stable evidence id), the corpus (pinned commit, hash and field checks, parts,
  observable dates, the census), the bulk ZIPs (conversion, unchanged files skipped, changed files under an
  existing release refused), `discover`.
- **From a runner** (`collect-source` with `discover`, run 38322410092, 2026-10-12): EUIPO and JPO (robots.txt
  included) 403; the Federal Court (both hosts) and AustLII 403; the High Court timed out; KIPO 200 (robots.txt
  addresses only Googlebot). The `env-check` of run 38325135244 (2026-10-13) got HTTP 200 from a runner for every
  new card: the five APH feeds, MOIP, WIPO Lex, the ABS release pages and Hugging Face.
- **First runs into the bucket:**

  | Source | Run | Commit | Result |
  |---|---|---|---|
  | APH: new inquiries, reports, hearings, House, joint (backfill) | `20261012T233628Z-953977c2` to `…233645Z-d565170d` | `75fb646` | 34, 134, 30, 0 and 0 items |
  | `oalc` | `20261012T235416Z-c73a8ca6` | `5e33029` | 104,201 documents (32,356 legislation; 63,749 Federal Court; 8,096 High Court), 981 MB of Parquet; file hash matched |
  | `wipo_treaty_notifications` (backfill) | `20261012T235442Z-55e3a98e` | `5e33029` | 2,945 notifications, 1967 to 2026-09-28 |
  | `abs_datacubes` | `20261012T235425Z-2fe86bdb` | `5e33029` | 37 tables (CABEE 16, released 2026-08-18; BERD 21, 2025-08-22) |
  | `ipaustralia_publications` | `20261012T235537Z-a9ae9eca` | `5e33029` | 6 PDFs; CC BY found in 2; the Minister's letter states none (metadata only) |
  | `moip_news` (backfill) | `20261012T235558Z-24769863` | `5e33029` | 10 items |
  | `wipo_ipstats` | `20261012T235949Z-e420e5ab` | `facf9c0` | 6,242,077 rows in 6 tables, release 2024-06-21 (data 2000-2022) |
  | `ipaustralia_site` (backfill) | `20261012T235611Z-a03315ee` | `5e33029` | 844 of 846 sitemap pages in 29 minutes; one 404, and the site's own 404 page loops on redirects |
  | `patent_cpc_counts` (a runner, dry run) | `20261013T000152Z-ec6d9eab` | `facf9c0` | the query would scan 17.1 GB (cap 200 GB); nothing billed |

- **Census reports** for the new sources are in `reports/census/` (aggregates only). The corpus's census shows 4,354
  of the 8,096 High Court decisions without a date.
- **The bucket:** 2.00 GB of the free 10 GB.

**Runs and slips, disclosed:**
- The first `oalc` run failed (manifest `20261012T233623Z-6cfa4e46`): DuckDB ran out of memory at its 3 GB limit
  writing 20,000-row groups of long texts. Row groups are now capped at 64 MB (`5e33029`); a smoke conversion of a
  hash-checked local copy passed (peak about 4.8 GB of memory, 54 s) before the run from a fresh download.
- `wipo_ipstats` ran with `CLAUDE.md` edited but not committed (its manifest says `dirty: true`); the change was
  documentation only, and the code is `facf9c0`'s.
- Release 7.1.0 was ingested with parser `hf-corpus-v1`, which leaves `observable_at` empty for the 4,354 undated
  High Court decisions. `hf-corpus-v2` falls back to the scrape (never too early); normalisation applies the same
  fallback to release 7.1.0.
- The first runner discovery waited 90 s per timeout at the High Court; `discover` now waits 30 s, once.
- Two `collect-source` runs were dispatched on this branch (its workflow file), not on `main`.

**Spend:** $0. Downloads, all free: the corpus three times (28 GB from Hugging Face: the failed run, a local copy for
the smoke test, the run), WIPO's ZIPs (23 MB), ABS's workbooks (1 MB). BigQuery: one dry run, nothing billed.

**Consequences.**
- After the merge, `collect-daily` takes six more sources and `collect-weekly` two more, by their cadence.
- Day 3 reads new record shapes: list items, data-cube tables, lake parts and undated feed items
  (`docs/sources-backlog.md`, §3). The recommendation of D-016 is met: T1 to T7 are built or wait on an answer.
- **For the owner:**
  1. **Merge this branch** (or ask for a pull request).
  2. **BigQuery (W2):** the monthly query would scan 17.1 GB, under 2% of the free 1 TiB a month, and every real
     query is capped at 200 GB. Switch `dry_run` off? (D-011)
  3. **The gaps:** whether to ask the Federal Court, AustLII and the High Court (draft request in the backlog, T7),
     and EUIPO and JPO, for access for Moria's user agent.
  4. **The wishlist (W1)** is unchanged.

Next free decision number: D-019.

## D-019 — The owner's answers on D-018: BigQuery switched on; the court and office gaps don't hold up day 3; uploads before day 3 (2026-10-13)

**Context.** D-018 asked the owner four things: merge, switch BigQuery on, ask the courts and offices for access, and
the wishlist uploads.

**Decision (the owner's).**
1. **BigQuery:** "Yes switch on BigQuery." `patent_cpc_counts` sets `dry_run: false`. Every query still carries
   `maximumBytesBilled` (200 GB), and the run checks its dry-run estimate against that cap before the real query.
   The card stays monthly, by hand (`collect-source`), since the key is only in GitHub's secrets.
2. **The gaps** (EUIPO, JPO, the Federal Court, the High Court, AustLII): "Not right now I'll see if I can find RSS
   feeds or something but I don't want it to stop our progress." No request is sent; day 3 does not wait on them.
   A feed the owner finds is checked from a runner first (`collect-source` with `discover`).
3. **The wishlist:** "I'll add some documents between now and when we commence Day 3." Uploads go to the private
   bucket at `inbox/documents/<name>` (`docs/wishlist.md`); each card is then run with `collect-source`.
4. **The merge** was not answered; it stays open.

**Checked: the first live run** (from a runner, run 38332703599, manifest `20261013T013416Z-66227a80`, commit
`ce45929`, clean): 961 records, one per four-character CPC code, priority years 2000 to 2026; 17.07 GB processed
and billed against the free 1 TiB a month (the estimate was exact), in one query. `reports/census/patent_cpc_counts.md`.
- The 961 codes are more than the card expected (500 to 800): they include subclasses no longer in use (290 have
  fewer than 100 families), the Y section (21) and 17 malformed codes (`Z…`, `C121`). The card's band is now 800 to
  1,100 and its biases say so; normalisation filters to the current scheme.
- **A flag for day 3, not a finding:** summed over codes, the share of families with an Australian member falls from
  about 22% (priority year 2000) to 5% (2010) and 2% (2020) while world counts rise. That looks like the dataset's
  coverage of AU publications, not a trend; check it against IP RAPID before using the AU series.
- The last three priority years are incomplete (publication lag), as the card says.

**Spend:** $0. BigQuery: 17.07 GB of the free 1 TiB a month.

**Consequences.** Day 3 starts when the owner asks, with the uploads that are in the inbox by then. The next BigQuery
run is due about mid-November (monthly).

Next free decision number: D-020.

## D-020 — Sources widened before day 3: the OECD (STIP Compass first), a breadth pack of eight feeds, the owner's uploads read, and five proposed known trends (2026-10-13)

**Context.** The owner: "I'm concerned that our sources aren't broad enough yet to really get a good sense of things.
I've gone out and found some useful resources from the OECD that I'd like you to add … The STIP Compass one seems
particularly valuable. In addition to these sources I've also added many of the documents from your wishlist into the
inbox folder in the R2 db. Please ensure that we've got a really strong footing on information sources before we
commence with the Day 3 build." The addresses: the OECD Data API's two explainers, three of the OECD's search feeds,
its briefs page, OECD.AI's blog feed and transparency reports, and STIP Compass and its download page. A count of
the cards showed the imbalance behind the concern: of 29 sources, 25 sat in the core ring and 5 in the wider world,
against review quotas of 35/35/30 (design §2.5); 17 were policy feeds, and the research family held counts only.

**Decision (the owner's, asked in the session).**
1. **Breadth:** "OECD + a breadth pack (Recommended)": about ten free, no-account feeds on the existing adapters, for
   the wider world and adjacent rings, each checked for terms and access first. This brings part of Tier 2 (the
   OECD, design §5.4 and the backlog's C6) forward, and supersedes D-016's "Tier 2 waits" for these sources only;
   the rest of Tier 2 still waits.
2. **OECD text:** "Yes, store it (CC BY 4.0)": the OECD's publication abstracts and STIP Compass's descriptions,
   objectives and background are stored privately, citing the OECD. The OECD's terms page and STIP Compass's pages
   sit behind a Cloudflare challenge that refuses the session and a runner; search results say OECD data, and OECD
   written content from 1 July 2024, are CC BY 4.0. OECD.AI's blog and the HAIP reports keep metadata only (OECD.AI
   reads "© OECD. All rights reserved"; the reports are their organisations' own words).

**Built (this session's choices; they stand until the owner says otherwise).**
- **The OECD, six cards:**
  - `oecd_publications` and `oecd_data_releases` (`feed`, daily): the search feeds at `api.oecd.org` with
    `pageSize=50` (the default is 15), abstracts, and each item's content type and policy areas (`keep_categories`,
    a new feed option that leaves other feeds' records unchanged). The owner's two publication feeds overlap: the
    wider one covers the other and the briefs page, which `www.oecd.org` refuses to cloud addresses.
  - `oecd_ai_blog` (`feed`, daily; titles and links) and `oecd_ai_haip_reports` (a new `json_list` adapter, weekly):
    the Hiroshima AI Process transparency reports from the JSON endpoint OECD.AI's own page reads (`api.oecd.ai`,
    paginated), metadata only: organisation, country, website, reporting period, date, link.
  - `oecd_headline` (a new `oecd_sdmx` adapter, weekly): 13 queries to the OECD Data API (`sdmx.oecd.org`) chosen
    for the IP system and its context: MSTI (R&D, researchers, patents, high-tech trade); PCT and IP5 patents in AI,
    biotech and other selected technologies; firms' use of patents, designs and trade marks (innovation surveys);
    R&D tax incentives and IP-income tax support, and the IP regimes themselves (words, not numbers); firms' use of
    AI, cloud and big data; charges for the use of IP in services trade; leading indicators; the latest Economic
    Outlook; FDI restrictiveness; business entries, exits and bankruptcies; environmental policy stringency. It
    reuses the ABS parser (the same SDMX-CSV), keys series by agency and flow without the version (a new version
    keeps a series' id; each vintage records its version), caps a card at 18 queries (the OECD's best-practices page
    gives 20 or 60 data downloads an hour, in two versions), retries a refusal once, and waits 6 s between requests.
  - `stip_compass` (a new `delimited_csv` bulk stage, weekly, into the lake): the whole database file, which answers
    although the portal's pages are behind the challenge. It is pipe-separated with no quoting, a label line and
    `\r\r\n` line endings; five rows hold a stray delimiter inside a field and can't be split safely, so they are
    left out and listed in the release manifest. A re-run sends `If-Modified-Since` and does nothing on 304.
- **The breadth pack, eight cards (`feed`, daily):** `un_news`, `conversation_au` and `lowy_interpreter` (wider
  world; titles and links only: the UN's terms allow personal non-commercial use, The Conversation is news under
  Moria's rule though CC BY-ND 4.0, and the Lowy Institute bars storing its content); `ec_presscorner` (the European
  Commission's press releases, speeches and statements; reuse authorised with acknowledgement; opening lines and
  policy areas); `aspi_strategist` (ASPI's commentary; CC BY-NC-ND 4.0, with Moria non-commercial under D-017;
  opening lines and topic tags); `arxiv_ai_society` (arXiv's daily listings in cs.AI, cs.CY, cs.DL and econ.GN;
  metadata, abstracts included, are CC0 under arXiv's API terms; one request every 3 s; author names not stored);
  `standards_australia_news` (titles); `us_federal_register_ip` (the USPTO's and the Copyright Office's rules and
  notices; public domain).
- **Checked and not added:** WTO news (its robots.txt disallows the feed); the ACCC and the IEA (403, from the session
  and a runner); cyber.gov.au and the TGA (time out from the session and a runner); eSafety, the ARC, the Chief
  Scientist and the AIHW (time out or 403 from the session); WHO's feed (stopped in February 2026) and the US
  Copyright Office's NewsNet (stopped in January 2025); GOV.UK's DSIT feed (newest item August 2026); the OAIC's feed
  (no dates); the Productivity Commission and Treasury (no feed found); the RBA (RSS 1.0, which the feed adapter
  doesn't read; macro data come from the ABS and the OECD).
- **The owner's uploads (eleven files, under their own names):** a document entry may name its upload (`upload`),
  and Word files are read from their XML. Mapped: the National Science and Research Priorities, the Net Zero Plan,
  the 2026 National Defence Strategy and (a new entry) the 2026 Integrated Investment Program; AIC Statistical
  Reports 38 and 55; the Patents Accessibility Review (Word); the JPO Status Report, CIPO's strategy and (a new
  entry) the KIPO Annual Report 2025. The OECD Data API documentation was read to build `oecd_headline`; it is not
  evidence.
- **The licence check** now reads "no part may be reproduced" and "no part of this publication may in any form …
  be reproduced" as reserved (the Defence and AIC documents), and the Government of Canada's "may be reproduced …
  without charge or further permission" as permitted.
- **CIPO (this session's reading of D-017):** CIPO's strategy carries that Government of Canada notice, and the
  wishlist's open question was whether Moria's private storage counts as non-commercial; the owner's D-017 answer
  ("Moria's use would be considered non-commercial research purposes") settles it. CIPO's strategy text and
  `cipo_news` summaries are now stored. The EPO's terms (a different question) still wait.
- **The baseline:** trends and citations carry a status (`confirmed` or `proposed`). Proposed from the uploads, for
  the owner: KT20 Indigenous knowledge, data sovereignty and cultural and intellectual property (the Science and
  Research Priorities, Priority 3); KT21 espionage, foreign interference and cyber threats to critical systems;
  KT22 mis- and disinformation and the contest for trust; KT23 rearmament and a sovereign defence industrial base;
  KT24 the return of industrial policy; and twelve citations adding the new documents to confirmed trends (KT01,
  KT02, KT03, KT04, KT06, KT07, KT09, KT11). The Defence documents reserve their rights: read in the session and
  cited by item name, their text not stored.

**Rejected, a line each:**
- **Running the Cloudflare challenge** on `www.oecd.org` and `stip.oecd.org`: D-011, and the file STIP Compass offers
  answers without it.
- **One card per OECD feed the owner listed:** the publications feed with every content type covers the narrower one
  and the briefs page.
- **Storing the HAIP reports' text:** each is its organisation's own response on a site that reserves its rights.
- **OCR for the KIPO report:** its text was converted to outlines (no fonts on any page); OCR would be a new
  dependency for a document whose licence is unknown.
- **Interpreting STIP's malformed rows:** which field holds the stray delimiter can't be known; five of 12,811 rows.

**Checked:**
- **Tests:** 98 pass (no network): OECD series (codes, words, a version-free id, the query cap, one retry), feed
  categories, JSON lists (pages, lookback, backfill, an empty list failing), the delimited stage (labels, `\r\r\n`,
  rows left out, 304, an unchanged hash, a changed file under an existing release, text columns kept as lengths),
  named uploads and Word files, the new licence wordings.
- **From a runner** (`collect-source` with `discover`, runs 38389709143 and 38395160791): STIP's pages, its sitemap
  and `www.oecd.org` answered 403 (a Cloudflare challenge) as to the session; OECD.AI answered; the OECD Data API's
  structure endpoint answered 200; cyber.gov.au and the TGA timed out; the ACCC and the IEA answered 403.
- **First runs into the bucket** (from clean commits):

  | Source | Run | Commit | Result |
  |---|---|---|---|
  | `oecd_publications`, `oecd_data_releases`, `oecd_ai_blog`, `oecd_ai_haip_reports` (backfill) | `20261013T114352Z-cd5241ce` to `…114405Z-df68c3a6` | `db9eb7d` | 47, 49, 10 and 56 items |
  | `stip_compass` | `20261013T114414Z-2abf650e` | `db9eb7d` | release 2026-09-08: 12,806 instruments of 8,817 initiatives from 68 countries and the EU (Australia 197); 5 rows left out |
  | `foresight_syntheses`, `territory_evidence`, `peer_office_strategies` | `20261013T115352Z-d195a64a`, `…115642Z-320ed7df`, `…115833Z-2811d035` | `7c1f370` | 10 uploads read; text stored for the Science and Research Priorities, the Net Zero Plan, the Patents Accessibility Review and CIPO's strategy; the Defence and AIC documents reserve their rights; the JPO report states no licence; the KIPO report has no text layer |
  | The breadth pack and `cipo_news` (backfill) | `20261013T122021Z-93df8773` to `…122057Z-da7dbd34` | `1ec3ed6` | UN News 30, The Conversation 42, ASPI 98, Lowy 50, Federal Register 5, the Commission 47, Standards Australia 100, arXiv 0 (no announcement that day), CIPO 23 |
  | `oecd_headline` (a runner, `collect-source` run 38397223310) | `20261013T122654Z-dc45ffd9` | `8b20c86` | 13 queries, all HTTP 200: 17,712 series, 458,442 observations |

- **Census reports** for the new and re-read sources are in `reports/census/` (aggregates only).

**Runs and slips, disclosed:**
- The three document cards were first run at 11:46 to 11:51 UTC from an uncommitted tree (their manifests say
  `dirty: true`); the licence check then missed the Defence and AIC wordings. They were re-run from `7c1f370`; the
  earlier records stay in the bucket (raw bundles are immutable), and the newest record of each document wins.
- The first local run of `oecd_headline` found no data for the patents query: its key had one dot too many. Fixed
  and checked with one query before the commit. With a few structure queries, about 18 data downloads went to the
  OECD from this session's address in that hour, near the lower of the two published limits; no 429 came back.
- The session's discovery runs used `collect-source` on `main`, whose code already had `discover`. The
  `oecd_headline` run was dispatched on this branch (its workflow file and code), from a runner, so that its first
  run used a fresh address's hourly allowance and proved the weekly job's route.

**Spend:** $0. Downloads, all free: STIP Compass twice (37 MB), the OECD feeds and API (about 40 MB of CSV), the
owner's uploads read from the bucket (about 100 MB).

**Consequences.**
- Sources: 29 to 43. By ring (a source can sit in several): core 25 to 33, adjacent 17 to 29, wider world 5 to 15.
  By family: news 1 to 3, research 1 to 2 (arXiv adds titles and abstracts), statistics 3 to 5, policy 17 to 25,
  legal 3 to 4. After the merge, `collect-daily` takes 11 more sources and `collect-weekly` 3 more.
- Day 3 reads new shapes: feed categories; JSON-list items; OECD series (some with words for values); STIP's lake
  table (one row per instrument, 521 text columns, a label for each); arXiv's announcement type inside each abstract.
- **For the owner:**
  1. **The baseline:** confirm, edit or drop KT20 to KT24 and the twelve proposed citations (`moria baseline` marks
     them).
  2. **CIPO:** object if D-017 shouldn't cover CIPO's notice.
  3. **Still wanted** (`docs/wishlist.md`): the Critical Technologies list, the OECD STI Outlook 2025 (its PDF sits
     under a path the OECD's robots.txt disallows), the Government's response to the Patents Accessibility Review,
     WEF's two top-10 lists, and the EPO's terms. The KIPO report can't be read; a text version would help.
  4. **Merge this branch** (or ask for a pull request).

Next free decision number: D-021.

## D-021 — Day 3 built and run: the evidence layer normalised, swept, embedded, de-duplicated, keyphrased, indexed and tagged; IP RAPID metrics; the T4 test waits on the owner (2026-10-13)

**Context.** The owner: "You are to commence the Day 3 build." Design §13 day 3: normalise, de-duplicate, event and
observable dates; territories wired in; embeddings, keyphrases, BM25, zero-shot tags; the decision model's speed on a
T4. Done when every Tier 1 item is embedded and tagged. The handover (open item 1) added `moria ipr metrics`.

**Built (this session's engineering choices; they stand until the owner says otherwise).**
- **`moria normalise`** (`src/moria/normalise.py`). It reads every raw bundle whose collection run passed, checked
  against that run manifest's SHA-256, and the latest release of each bulk source. It writes, per source:
  `lake/documents/` (one row per item: its latest version, `n_versions` and `first_seen_at` across runs), and
  `lake/series/` with `lake/observations/` (long form, one row per series, period and vintage). IP RAPID is left to
  its metrics stage.
  - **Dates** (`src/moria/text.py`): ISO with and without zones, FRL's seven-digit fractions, RFC 2822 (feeds),
    GDELT's stamps and bare years, all to UTC; a time without a zone is read as UTC. `observable_at` is the source's
    date, or first sight when the source gives none, or first sight when the source's date is more than a day after
    it (`observable_basis`: `source`, `first_sight`, `clamped`). Every source date parsed: 0 clamped; 4,363 items
    observable from first sight (4,354 legal-corpus documents without a date, and 9 documents without a
    publication date).
  - **Vintages:** a snapshot source (ABS, the OECD, OpenAlex, the CPC counts, spreadsheets) adds a vintage only when
    a series' values change; an append source (GDELT's daily volumes) adds each period once. The value at `as_of`
    is the latest `vintage_at <= as_of`.
  - **Per source:** GDELT's GKG volumes become `matching`, `about` and `names_only` series per query group and
    scope, plus the day's total (the DOC API's early timelines, D-009, are left out); OpenAlex groups become one
    series per topic, level, scope and period kind; CPC counts become world and AU series, 17 malformed codes left
    out; ABS spreadsheet cells are one series each, as published, their period the release's (`2023-24`); SDMX
    series keep words as `value_text`; WIPO's bulk tables become 966,306 office-by-origin-by-class series; STIP
    Compass becomes one document per initiative (its instruments' names and descriptions in the text, observable
    from `CreatedInSurvey`); the legal corpus keeps a 4,000-character excerpt (the full text stays in its lake).
  - **Unchanged sources are carried over:** a digest of a source's inputs (bundle keys and hashes, its card, the
    normaliser's settings) skips the rebuild and carries the outputs into the new manifest. The re-run took 40 s.
  - **Layout:** partitioned by source, not by family and month or by series and vintage (design §4.3): a source is
    the unit of collection and of rebuilding, and per-series files would be 17,712 objects for the OECD alone. DuckDB
    filters on `observable_at` and `family` across the files.
- **The sweep** (`src/moria/sweep.py`), inside normalise rather than a separate `moria sweep` stage, so that every
  text field normalise keeps is swept once, before anything reads it. It removes hidden characters (zero-width,
  bidirectional controls, Unicode tag characters) and grades AI-directed instructions, chat markup, secrets and
  active content; personal data (e-mail addresses, phone numbers) is counted, not changed. High severity quarantines
  the item: left out of `lake/documents`, listed by id and finding codes in `lake/quarantine/`. It does not fail the
  run (design §12; SOP §22 would also fail it): one abstract quoting an injection should not stop the daily chain.
  The allowlist (`config/sweep.yaml`) is empty and the owner's alone.
- **`moria features embed`** (`src/moria/embed.py`): `BAAI/bge-small-en-v1.5`, its own ONNX export at revision
  `5c38ec7c`, each file checked against its SHA-256 before loading, run by onnxruntime and `tokenizers` (an optional
  `models` extra, so CI stays light); CLS pooling, L2-normalised, as the model's pooling config says; vectors stored
  as float16. Text: the title, summary and opening text, cut at 1,500 characters, read to **256 tokens**, measured on
  600 sampled items here (4 threads): 22.1 texts/s at 256 tokens against 9.2 at 512. A vector is reused while its
  text is unchanged; local checkpoints let an interrupted backfill resume.
- **`moria features dedup`:** union of three rules within 30 days, each group named by its earliest member: the same
  canonical URL between news items; the same news title of at least six words; cosine >= 0.95 between different
  outlets (design §8.3). Two corrections came from reading the first groups: the URL rule had joined 344 STIP
  initiatives that share a ministry's link and an APH progress report with the inquiry it reports on (both link the
  committee's page). URLs identify an item only in news, so the rule now needs both items to be news.
- **`moria features keyphrases`:** candidate phrases are runs of words between punctuation and stopwords, and their
  1- to 3-grams. Document frequencies are counted in hashed buckets first, then exactly for phrases that can pass
  (memory bounded), with min_df 3, max_df 5% and at most 200,000 phrases. The top 8 per document are scored by
  TF-IDF times the square root of the phrase's length, a phrase dropped when a longer kept one holds it. The
  vocabulary records each phrase's first observable date, sources and families: the input of day 4's `new_term`.
- **`moria features index`:** DuckDB `fts` (BM25, Porter stemming) over the title, summary and 4,000 characters,
  with source, family, dates and URL; `moria search` for the analyst's own terminal.
- **`moria tag --backend zeroshot`** (`src/moria/tags.py`): cosine similarity to prototypes, each the mean of its
  label's embedded description and examples. Ring and PESTLE are single-choice (a softmax at temperature 0.02, with
  the top label and its margin). Domains, rights and territories keep raw similarities, and each item gets its
  nearest known trend and the second. **Territories wired in:** the territory prototypes use the name, aim and
  description, plus the owner's private context (imagine, recently changed, jobs to be done) read from the bucket.
  Only vectors and similarities are derived from it, in the bucket. The 47 query groups GDELT is searched with are
  now matched in every source's text too (`term_groups`, `term_territories`). The tagger's name carries the
  codebook's version and a hash of every prototype text (design §8.3, label drift). **`config/codebook.yaml`** is
  drafted from the design's definitions (§2.1, §10.1) and is `proposed`.
- **`moria ipr metrics`** (`src/moria/iprmetrics.py`): 59 monthly series from 2000 in `lake/ipr_metrics/`, from the
  latest base with the latest delta applied (base minus its removed rows, plus its added rows).
  - Demand: applications by sub-type, by founding applicants' origin, self-filed, first-time applicants, Madrid
    designations of Australia, and patent applications in G06N (AI).
  - Outcomes by event month: registrations, grants, acceptances, lapses, withdrawals, refusals, oppositions, non-use
    removals, ownership changes, examination requests.
  - Timeliness: median days from filing to registration, by registration month.
  - Each release is a vintage, and its own month is marked `incomplete`.
  - Three corrections came from reading the first output. Country codes are lower case, so origin had matched
    nothing. In 715,462 of 2,331,535 trade mark applications the founding agent is the applicant itself, so
    self-filed now ignores such an agent. The `accepted` event gave 3 to 14 days to acceptance for trade marks, so
    it isn't examination acceptance; timeliness now uses the application table's registration date, a median
    221 days for trade marks, and about 600 to 1,200 days for patents (rising since 2021).
  - Six series with no month in the last 12 are left out and listed: trade mark renewals and examination requests
    stop in November 2018 (a system change); petty patents ended in 2001; design and PBR refusals are too sparse.
  - Check: applications by year match the IP RAPID census exactly (2025: 97,343 trade marks, 37,379 patents).
- **`moria prepare`** runs the chain and stops at the first failure. **`.github/workflows/prepare.yml`** runs it
  weekly (Mondays 07:17 UTC, after collect-weekly), with the model files cached by revision, and **`collect-daily`**
  now normalises after collecting.
- **`moria evidence-report`** writes `reports/evidence-layer.md`, aggregates only.
- **The T4 test** (`scripts/t4_jevstyle_speed.py`): free Kaggle and Colab GPUs need a person to start them, so the
  test is a one-cell script for the owner. It fetches the decision model's files at revision `edf37c26`, each
  hash-checked; builds llama.cpp at the card's commit with CUDA, and the model's own scorer; and times 60 synthetic
  items and an 8k-token state. The model repo's wrapper, scorer and build script were read first: the wrapper
  launches only the local scorer, with no network calls. **The rule, fixed before the number:** per-item tags if the
  median item (7 questions) takes <= 0.15 s, so the 122k items take <= 5 h in one free session; otherwise signals
  only.

**Rejected, a line each:**
- **fastembed:** it downloads at run time and serves Qdrant's quantised re-export, not the design's model at a
  pinned revision.
- **scikit-learn's `TfidfVectorizer` for keyphrases:** it builds the whole n-gram vocabulary before pruning, too
  much memory for 122k documents.
- **512 tokens:** 2.4 times slower, for text past the opening of a judgment or report.
- **A per-item decision model:** not before the T4 number (the CPU took 5.1 s an item, design §4.2).
- **Embedding series labels** (topics, indicators): series keep their cards' rings; day 4 can embed labels if a
  detector needs them.
- **Tuning the codebook further** against unlabelled outputs: the owner's labels are the yardstick (§11.2).

**Checked:**
- **Tests:** 118 pass with no network: dates, URLs, text, the sweep and its allowlist; normalise (versions, first
  sight, clamping, quarantine, a failed run's bundle left out, carrying over, vintages, GDELT volumes, an unmapped
  payload failing loudly); embed reuse; dedup's three rules and its refusal of stale embeddings; keyphrases; tags
  with territory terms; BM25; IP RAPID metrics over a base and a delta. The BM25 test is skipped in CI, which makes
  no downloads. A new hygiene test refuses literal invisible or bidirectional characters in tracked files.
- **CI:** green on `9356410`; red on `2cc8e7e` (see below).
- **Runs into the bucket** (this session's machine, `--store r2`), from clean commits:

  | Stage | Run | Commit | Result |
  |---|---|---|---|
  | `normalise` | `20261013T160437Z-613b21bb`, then `…161842Z-c5694100` | `2cc8e7e`, `9356410` | 122,243 documents from 28 sources; 1,012,530 series, 7,214,318 observations; 0 quarantined; then all 42 sources unchanged |
  | `features.embed` | `20261013T161922Z-93c79f44` | `9356410` | 122,243 documents; 112,161 embedded, 8,192 taken from the stopped run's checkpoints; 86 minutes |
  | `features.dedup` | `20261013T174549Z-51a8353d` | `9356410` | 120,344 groups; 354 with copies, all GDELT news (URL 20, title 1,703, cosine 176 joins) |
  | `features.keyphrases` | `20261013T174606Z-9f6c8132` | `9356410` | 200,000 phrases; 954,535 kept for 122,155 documents |
  | `tag` | `20261013T180027Z-9f045240` | `353e458` | 122,243 items, tagger `zeroshot-v1\|codebook-v2\|fcafc078c410`; 16,632 match a territory or theme term |
  | `features.index` | `20261013T175042Z-439c893c` | `9356410` | 122,243 documents, 517 MB |
  | `ipr.metrics` | `20261013T175207Z-2dd7d5c0` | `9356410` | 59 series, 17,540 observations, release 2026-10-12 |

- **Read in the output:**
  - Near-duplicate joins are syndication: the same wire story on different outlets at cosine 0.96 to 0.99, and a
    radio network's 146 copies of one item.
  - The sweep found 554 items with e-mail addresses, 230 with hidden characters and 98 with phone numbers, mostly
    in judgments, nothing of high severity.
  - The first tags put 97% of the legal corpus in the core ring: the codebook showed law only under the IP system.
    Examples drawn from §2.1 (law on migration, tax, employment and administration under the wider world;
    competition and consumer law under adjacent) bring it to 57%. Of the legal-corpus items matching IP-system
    terms, 90% stay core.
  - The same examples pull WIPO's treaty notifications from 88% core to 56%: the zero-shot ring is weak on legal text
    and short titles.

**Runs and slips, disclosed:**
- **The first chain** started from `2cc8e7e` and was stopped while embedding: files edited for the next commit would
  have marked its later manifests dirty, though the code that ran was the commit's. It was restarted from
  `9356410`; its normalise run passed clean, and its partial embeddings were overwritten.
- **CI red on `2cc8e7e`:** run ids sort to the second, so two runs in the same second could come back in the wrong
  order (a test caught it). Manifests now carry a nanosecond start time, which breaks ties.
- **The tests wrote embedding checkpoints into the real cache** under fixture source ids. Removed; tests now cache
  in their own directory (`MORIA_CACHE_DIR`).
- **Literal invisible characters:** this session's tooling turned typed escapes into literal zero-width and
  bidirectional characters in two files, and an older fixture held a literal BOM. All are escapes now, and the new
  hygiene test refuses them.
- **A dirty tag manifest:** `tag` run `20261013T175717Z-9c466acf` says `dirty: true`, because the untracked
  evidence report sat in the tree. It was re-run clean (`…175844Z`, then `…180027Z` with the codebook's version
  bumped). The dirty manifest stays in the bucket (manifests are immutable).

**Spend:** $0. The bucket grows from 2.09 GB to 2.92 GB of the free 10 GB, of which the index is 0.52 GB.
Downloads: the model's files (134 MB) from Hugging Face; the legal corpus and IP RAPID from the bucket to this
session's cache.

**Consequences.**
- Day 4 reads the evidence layer as `docs/handover-day3.md` lists it, with its flags:
  - the legal corpus is 85% of documents, so shares and quotas go per source or family;
  - IP RAPID's latest 30 months of patents are composition-lagged: national-phase entries arrive later, so the AU
    and self-filed shares jump in 2025 and 2026;
  - the zero-shot ring and the nearest known trend are weak until calibrated, so use the cards' rings and the term
    matches for the core ring;
  - GDELT's first GKG day has one measure, not three.
- Scale: dedup's cosine pass will need approximate neighbours or day blocking once GDELT holds months of titles.
- **For the owner:**
  1. **The T4 test:** run `scripts/t4_jevstyle_speed.py` in a free Kaggle or Colab T4 notebook and paste back its
     one JSON line. The rule decides between per-item tags and signals only.
  2. **The codebook** (`config/codebook.yaml`, proposed): confirm or edit the labels' descriptions and examples.
     They also frame the 200 labels (docs/mining-explained.md).
  3. **The territory context:** it now shapes the territory prototypes inside the bucket; nothing of it is
     published. Say so if it shouldn't be used that way.
  4. Still open: KT20 to KT24 (D-020), the wishlist, and the merge of this branch (or a pull request).

Next free decision number: D-022.

## D-022 — Day 4 built and run: the detectors over every series and document, six artefact checks, all six seeded artefacts caught; 2,486 candidates, 2,129 unflagged (2026-10-14)

**Context.** The owner: "Commence Day 4 build." Design §13 day 4: rates; trends, accelerations and change points over
the whole taxonomies; world/AU divergence; anomalies; the five weak-signal indicators; cross-ring convergence;
artefact checks with seeded artefacts. Done when there is a candidate list with artefact flags. The handover's flags
(D-021) were read first: the legal corpus is 85% of documents; GDELT has two days; the zero-shot ring is weak.

**Built (this session's engineering choices; they stand until the owner says otherwise).** The settings are in
`config/detect.yaml` (`DetectConfig`); every stage checks its upstream manifests and writes its own.
- **`moria measure series --as-of D`** (`src/moria/measures.py`, statistics in `src/moria/stats.py`). Every series
  of OpenAlex, the CPC counts, ABS, the OECD, GDELT and the IP RAPID metrics, at a point in time: each period's
  latest vintage observable by the end of D (else the earliest: backfilled history has no true first sighting), the
  period containing D dropped (never complete), and lagged periods dropped (CPC and OECD patents 2 years; IP RAPID
  design series 2 months, below; OpenAlex Januaries left out, being works dated by year only).
  - **Rates per source volume** (§8.3): a count is tested as its share of the source's volume in the same period
    (a topic over all works in its scope, a CPC subclass over all subclasses, a query group over every GKG
    document, an IP RAPID split over the right's applications), on a log scale, so a slope is a growth rate. A
    count absent from a period its source covered is a zero. Statistics are tested on their own scale.
  - **Trend:** Theil–Sen with Sen's interval (matches `scipy.stats.theilslopes` exactly) and Mann–Kendall in three
    windows: 12, 24 and 36 months as designed; 8, 12 and 16 years for annual series and 8, 16 and 24 quarters,
    because 8 annual points can never reach p < 1e-4, which Holm needs across thousands of series. Significant in
    at least 2 windows, in one direction, after Holm within a family (source, frequency, taxonomy level or
    dataflow, scope class, window); a window needs 90% of its periods; a count needs a mean of 5 a period.
    Benjamini–Hochberg's q is kept beside it for comparison only: 1,295 trends under Holm, 7,007 under BH.
  - **Acceleration:** the recent half's Theil–Sen slope minus the earlier half's, with a bootstrap (300 resamples,
    fixed seed) standard error and Holm; or a change point to a steeper slope on a series that is itself a trend
    (§8.2: a trend whose growth increases). Both must change the yearly growth by at least 0.10 (counts), or the
    yearly slope by 0.10 of the level (statistics).
  - **Change points:** optimal partitioning of the penalised squared error, PELT's exact objective without its
    pruning, in level and in slope. The penalty is 3 times BIC's from a robust noise estimate: on simulated noise
    of 36 points, BIC split 17% of series in level and 15% in slope; 3 times BIC split 0.55% and 0.3%, and still
    found a 2-sigma level shift 77% of the time (a 0.4-sigma-a-period slope change 45%). A level change is sought
    about the window's trend line, so a trend is not read as steps.
  - **Anomaly:** the latest value against a Theil–Sen line fitted on the periods before it (24 months, 8 years),
    with a robust band, family-wise at 99% (Holm), and at least 25% off the expected value; or a recent change in
    level (monthly, quarterly and daily series only).
  - **Low-base surge:** the latest periods (3 months, 1 year, 7 days) against a trailing baseline (12 months, 5
    years, 28 days), the exact conditional Poisson test of two rates with the source volume as exposure, a low
    base (at most 5 expected), at least 5 items and a ratio of at least 2, Holm.
  - **Divergence (§8.5):** Australia's share against the world's (OpenAlex, CPC, GDELT) or Australia's level
    against the OECD's (the log ratio, so relative growth), tested for a trend like any series.
  - Writes `measures/series/as_of=D/{measures,divergence}.parquet`. 26,999 series in 23 s.
- **`moria measure documents --as-of D`** (`src/moria/concepts.py`). A 91-day window and the 730 days before it.
  An item is visible when observable by D and seen by Moria by D, or observable before its source's onboarding
  (backfill, §6.3). Undated items from a source's first collection (4,360, nearly all legal-corpus judgments) carry
  no date and are left out of every window. Counts are of de-duplication groups.
  - Concepts: keyphrases, the 47 term groups, and 200 MiniBatchKMeans clusters fitted at D (named by their
    keyphrases' class-based TF-IDF).
  - `new_term`, `cross_family` (3 families in the window, at most 1 before), `cross_ring` (rising in wider-world
    items by the exact test, and in core items for the first time), `low_base_surge` per family, `new_combination`
    (keyphrase pairs; IPC subclass and Nice class pairs from IP RAPID, by the month the application's classes were
    assigned, at least 3 applications from 2 applicants), and `novel_items` (LocalOutlierFactor fitted on each
    family's baseline, novel items grouped into micro-clusters at cosine distance 0.25).
  - An item's ring: its card's ring when there is one; else core when it matches core-ring terms (D-021's flag);
    else the zero-shot ring among the card's other rings.
- **`moria ipr metrics`** now also writes applications by IPC subclass, Nice class and Locarno class (731 series in
  all, from 59) and the co-classification tables (679,869 pair rows) the new-combination detector reads.
- **`moria monitor ingestion`** (`src/moria/monitor.py`): days and incidents per source from the monitor entries and
  collection manifests: a day is judged by its best passed run against the card's current band (daily and weekly
  sources only); failed days; gaps in daily sources up to two days before D. A snapshot (a source's first day, a
  `--backfill` run) is not above its band; a bulk release is filed under its release date.
- **`moria detect --as-of D`** (`src/moria/detect.py`): one candidate per subject, typed acceleration, trend, weak
  signal or anomaly, with every detector that fired, their numbers (canonical JSON), a strength for day 5's ranking,
  the views (early warning, strategic), and the evidence (series, or window items with sources, families, rings and
  groups). A weak signal needs 3 groups from 2 sources (45 dropped). Ids come from the subject alone, so a subject
  keeps its id across scans.
- **`moria artefacts --as-of D`** (`src/moria/artefacts.py`): six checks, each shown, never hiding a candidate. For a
  weak signal from documents the question is whether it would still meet the minimum without the evidence the check
  doubts: sources whose volume moved more than ±25% or that have no baseline (coverage), sources whose history
  doesn't cover the baseline (source break), sources with an incident in the window (ingestion); and raw items at
  least twice its groups (duplicate), news only inside 14 days (news cycle), tags with more than one tagger version
  (label drift). For a series: its source's volume over the detector's window (coverage), the latest collection's
  incident (ingestion), a dated break on its card inside the window (source break), and for GDELT volumes,
  syndicated copies and news bursts without a primary-source item. A class pair with a class new to the scheme
  (first seen inside the baseline, as IPC's 2025 subclasses H10D, H10F and H10H) is a source break.
- **`moria eval artefacts --as-of D`** (`src/moria/seeded.py`): the yardstick of §11.2. The evidence layer is copied
  to a temporary store, six artefacts are planted in synthetic sources and scopes, each with a control (a genuine
  change of the same size without the artefact), and the whole chain runs on the copy: a volume spike in a series
  scope and in a document source (coverage), duplicated syndication (duplicate), a source onboarded two days before
  with 60 days of backfill (source break), a failed collection (ingestion), and a news burst with no primary source
  (news cycle). A seed counts as caught only if it became a candidate and its check flagged it, and its control
  became a candidate without that flag. The same evaluation on a hand-built layer is the end-to-end test.
- **`moria scan`** (the chain: monitor, measures, detect, artefacts), **`moria scan-report`** (`reports/scan.md`,
  counts only), **`moria candidates`** (labels, for the analyst's terminal only), and the weekly `prepare` workflow
  now runs the scan and the seeded check after preparing.
- **Departures from the design, a line each:** `moria measure` has two subcommands (series, documents) rather than
  one per analysis, because each needs one point-in-time read of its inputs; forecasts are not built (deferred, §13);
  WIPO's bulk statistics (stale: they end in 2022) and the ABS spreadsheets (one period each) are not tested; OECD
  series are tested for Australia, the aggregates and 19 economies that file most in Australia or are its peers,
  and national-currency series are left out (their US-dollar PPP versions are tested); the anomaly and acceleration
  effect floors and the 3-times-BIC penalty are additions.

**Runs, disclosed in order** (`--store r2`, this session's machine; every manifest kept):
1. `ipr.metrics` `20261014T003957Z-86002796` and the first scan from `309cb43` (detect `20261014T004220Z-f94501b2`):
   3,449 candidates. Reading them found four faults, fixed in `b460e70`:
   - divergence on statistics took the raw difference, so Australia's GDP "diverged" from the OECD total by 2.3
     million (US dollars, millions): now the log ratio;
   - Argentina's and Türkiye's national-currency series (inflation) filled the accelerations, and small economies'
     volatility the anomalies: the OECD scope and unit rules above (OECD series tested: 16,168 to 4,642 annual);
   - **trade mark registrations in the IP RAPID metrics fell from about 5,000 a month to near zero from March 2026.
     The scan raised it; the cause is a recording change, not a fall:** the `granted` event all but stops (821 from
     April to September 2026, against 36,581 a year before) while `publish_registered` events and the application
     table's registration dates go on at about 6,000 a month. Registrations are now counted from the application
     table, and the card's known biases say so;
   - in a release's last month, design applications have no Locarno class or Australian applicant recorded yet
     (September 2026: 953 designs, all "overseas", 6 in class 14 against about 50): design series now lag 2 months;
   - the monitor counted dry runs, backfills and bulk releases as incidents, and the day before D as a gap.
2. The second scan (`b460e70`) passed; the first seeded evaluation failed (`20261014T005224Z-65e6a676`): a source
   with no items has an empty tags file. Fixed in `be8ead3` (the fixture now has one); the re-run caught 6 of 6.
3. Reading the class pairs: the new-class rule (`9ea53c4`).
4. **The final runs, from `9ea53c4`, clean:** `monitor.ingestion` `20261014T005950Z-f7f54a3c`, `measure.series`
   `20261014T010016Z-e7f4b90b`, `measure.documents` `20261014T010046Z-bfc90615`, `detect`
   `20261014T010124Z-004fa171`, `artefacts` `20261014T010126Z-e67d87df` (with `ipr.metrics`
   `20261014T005005Z-4aa7deae` from `b460e70`); `eval.artefacts` `20261014T010131Z-fd47baa0`. The scan takes about
  2 minutes; the seeded evaluation about 1.5.

**Results (as of 2026-10-14; `reports/scan.md`, `reports/eval/artefacts.md`):**
- **2,486 candidates, 2,129 with no flag:** 1,068 trends (974 clean), 452 accelerations (381), 830 anomalies (733),
  136 weak signals (41). Flags: coverage 354, source break 91, duplicate 2, news cycle 1, ingestion 0, label drift 0.
- **Every weak signal from documents is flagged,** as it should be today: the window is full of feeds onboarded this
  week with no baseline (GDELT, the breadth pack, the OECD feeds), the legal corpus ends in 2025 while daily
  legislation began in October (the legal family's window holds 40 groups against 33,382 in the baseline), and STIP
  Compass's window holds 22 initiatives against 2,514 in the baseline. The 41 clean weak signals are IP RAPID class
  pairs (28) and series surges (13).
- **Seeded artefacts: 6 of 6 caught; 6 of 6 controls detected without the flag,** on the real layer.
- Series: 26,999 tested; 1,295 trends (Holm); 339 bootstrap accelerations; 808 anomalies; 124 recent level changes;
  14 surges; 5,120 AU/world pairs, 42 diverging.
- Documents: 5,405 items in the window and 36,773 in the baseline; new terms 18, cross-family 31, cross-ring 9,
  low-base surges 71, new combinations 28 and rising 7, novel micro-clusters 8, before the weak-signal minimum.
- **A correction of D-021's reading.** D-021 read the jump in IP RAPID's Australian and self-filed patent shares in
  2025–26 as composition lag (national-phase entries arriving late). The counts don't support it: overseas
  applications stay at about 2,100 to 2,550 a month from January 2025 to September 2026, with no shortfall in recent
  months, while provisional applications rose from about 220–440 a month in 2023–24 to 760–1,270 in early 2026. The
  scan reads the provisional share of patent applications as a trend (growing about 41% a year) and the self-filed
  share as an accelerating trend (about 58% a year). No lag is applied to patent series.

**Checked:** 135 tests pass with no network (stats against scipy and planted changes; series detectors on planted
trends, a surge, an anomaly, a level shift and a divergence; point in time; the monitor's rules; rings; class pairs;
the seeded evaluation end to end on a hand-built layer; the report holds no labels or keyphrases). CI green on
`309cb43`. Lint and format clean.

**Spend:** $0. The bucket gains the measures, candidates and monitor summaries: 8.1 MB a scan.

**Consequences.**
- Day 5 reads `candidates/as_of=D/{candidates,evidence,artefacts}.parquet` and the measures behind them;
  `docs/handover-day4.md` lists what it needs and the flags.
- The weak signals from documents will stay flagged until daily collection builds a baseline: a feed whose history
  starts in October 2026 covers the 730-day baseline (before a 91-day window) from about January 2029, and the
  source-break check passes a candidate earlier when its evidence stands without such feeds. A shorter baseline for
  a weekly early-warning scan is a measured choice for later.
- Known limits: series surges can't be checked for 2 sources (an OpenAlex surge of 5 works may be one book); the
  keyphrase vocabulary was fitted on all evidence, so a hindsight scan at a past date needs a refit (day 5's
  term-only run); GDELT's daily series become testable after 35 days of collection; the candidate list is large,
  by design: day 5 ranks it within the ring quotas.
- **For the owner:**
  1. **IP RAPID's trade mark registrations:** the `granted` event has all but stopped being recorded since March
     2026. If you know of a change in IP Australia's systems then, say so; the metric now uses registration dates.
  2. Day 5 (dossiers, pathway suggestions, ranking and quotas, the register export) when you ask.
  3. Still open: the T4 speed test and the codebook (D-021), KT20 to KT24 (D-020), the wishlist, and the merge of this
     branch (or a pull request).

Next free decision number: D-023.

## D-023 — CSIRO added before day 5: the Data Access Portal as one source over 22 topic feeds; CSIRO's publications are a gap; robots.txt read as RFC 9309 (2026-10-15)

**Context.** The owner, before day 5: "I would like to add some extra data to the mix", with CSIRO's publications
API (`publications.csiro.au/rpr/swagger-ui/`) and 22 Atom feeds from the CSIRO Data Access Portal (DAP), one per
ANZSRC 2020 field of research (division), and: "All the CSIRO sources can probably just be treated as one source with
each RSS feed just being a different topic tag or something."

**Access (checked 2026-10-15).** Every CSIRO host refuses this build session (the egress policy), so each address was
checked from a runner (`collect-source` with `discover`; runs 38738506473, 38738869888, 38739306934, 38739694165):
- **publications.csiro.au answers 403 to the runner** for everything, robots.txt included (a firewall page). From
  search results, CSIRO's library guide says the RPR API is for CSIRO staff; external users ask its librarians for a
  key. **A gap**, until the owner wants to ask CSIRO for a key.
- **data.csiro.au answers.** Its robots.txt (now printed by `moria discover`, rules only) reads `Disallow: /dap/` then
  `Allow: /dap/ws/v2/`, with the data downloads under it disallowed. Moria's check called the search API disallowed:
  Python's `urllib.robotparser` applies the first matching rule in file order and reads `*` literally. RFC 9309
  (§2.2.2) says the most specific (longest) match wins, which allows `/dap/ws/v2/collections/searchbylocation`.
- The search's `sb` takes `RELEVANCE` and `RECENT` (`PUBLISHED_DATE`, `PUBLICATION_DATE` and `DATE` answer 417).
  `RECENT` is newest first: environmental sciences' first 100 run from 2026-04-30 to 10-08, its next 100 from
  2025-09-04 to 2026-04-29. Law and legal studies, the 23rd division, has no collections.

**Built (Claude's engineering choices; they stand until the owner says otherwise).**
- **`moria.robots`**: robots.txt read as RFC 9309 reads it: the group naming Moria's product token, else `*`; the
  longest matching pattern wins, an allow on a tie; `*` and `$` are wildcards; percent-encoding compared decoded.
  It replaces `urllib.robotparser` in the polite client. Checked from a runner against the robots.txt of every host
  a check covers (IP Australia, the USPTO, IPOS, WIPO, the ABS, OECD.AI, STIP Compass): none of Moria's addresses
  changes verdict (IPOS's `/search` and the ABS's `/*/print$` now apply as written; Moria fetches neither).
- **`moria discover`** prints a robots.txt's user-agent, allow, disallow and crawl-delay lines (directives for
  crawlers, never comments), so a runner's log shows why an address is refused.
- **The feed adapter's `topics`**: a `url` holding `{topic}` is read once per topic (the topic URL-encoded as the
  owner's addresses are); an item found under several topics is one record whose payload lists them (`topics`);
  normalise keeps them in the document's `extra`. A topic whose feed is empty is a warning. `moria env-check`
  probes the first topic's address.
- **`csiro_dap`** (daily; adjacent and wider world; D3, D0, D2; family research): the owner's 22 divisions,
  `sb=RECENT`, 100 a feed, a 7-day lookback, 2 seconds between requests (22 requests, under a minute). The owner's
  addresses also asked for facets (`showFacets=true`), which Moria doesn't read: left out.
- **Titles, links, dates and divisions only** (`keep_summary: false`). Each collection's data carry their own
  licence (CC BY 4.0 by default under CSIRO's deposit terms, by search results); no licence for the portal's
  metadata was found, and CSIRO's site states its copyright without an open licence (read through search results:
  csiro.au refuses this session). Not stored either: the entries' categories, unread.

**Run.** `collect csiro_dap --backfill` from a runner (run 38740097893, `fea146e`): passed, 22 requests, all HTTP
200; 899 collections (900 in the feeds, one dated after the window), 220 under more than one division, every one
dated (`published`); from 2012-10-02 to 2026-10-14. Divisions at the 100 cap: agricultural, biological, chemical,
engineering and environmental sciences (earth, information and computing, and physical sciences 98 to 99); the
smallest: philosophy 1, language 3, education 5, Indigenous studies 8. About 140 new collections a month across
the divisions (2026-09-15 to 10-14), up to 12 a day. The ingestion monitor's band warning is the backfill's size.

**Checked:** 142 tests pass (one skipped) with no network (RFC 9309 precedence, wildcards, end anchors, ties, agent groups and
percent-encoding; topic feeds merged, tagged and warned; a topic needs a template; normalise keeps topics). Lint
and format clean.

**Spend:** $0.

**Consequences.**
- Sources: 44. `collect-daily` reads `csiro_dap` from the next run after this branch is merged (schedules run from
  the default branch).
- The divisions are CSIRO's filing: day 5 can read them as a field-of-research tag beside the zero-shot tags.
- CSIRO's publications stay a gap. Two routes, for the owner: ask CSIRO's librarians for an RPR API key; or count
  and list CSIRO-affiliated works through OpenAlex (CSIRO's ROR id), which Moria already pays nothing for.
- **For the owner:**
  1. **The DAP's descriptions:** confirm whether Moria may store the collections' descriptions (CSIRO states no
     licence for its metadata; the data are mostly CC BY 4.0). Until then, titles only.
  2. **CSIRO's publications:** ask CSIRO for an RPR API key, or take the OpenAlex route, or leave the gap.
  3. **data.gov.au's robots.txt** disallows everything for every agent (`Disallow: /`), seen in passing. IP RAPID's
     refresh reads data.gov.au's catalogue API and download, which Moria's adapters don't check against robots.txt
     (an API and a bulk file, not web pages). It has worked for weeks and data.gov.au exists to publish these files;
     raised so that the reading is the owner's.
  4. Day 5 when you ask.

Next free decision number: D-024.

## D-024 — The owner's answers on D-023: the DAP's descriptions stored; CSIRO's publications to the backlog; IP RAPID's reading of data.gov.au accepted (2026-10-15)

**The owner's answers** to D-023's questions:
1. **The DAP's descriptions:** "Yes, Moria can store the collections' descriptions." `csiro_dap` now has
   `keep_summary: true`; its card's licence and snapshot rights say so. The entries' categories stay unread.
2. **CSIRO's publications:** "We'll leave the gap for now. Add it to the backlog to revisit later." In
   `docs/sources-backlog.md` §5, with both routes (OpenAlex by CSIRO's institution; a key and leave to use it from
   a runner, from CSIRO's library). Asked how 899 records were collected if a key is needed, Claude explained in
   chat: the 899 are data collections from the Data Access Portal, whose search API is public; the gap is the
   separate publications repository (articles, papers, reports), which refuses every address to a runner (a
   firewall, by the look of it). That its API needs a key comes from search results only, not verified.
3. **data.gov.au's robots.txt:** "Yes, that's very acceptable for us to continue accessing IP RAPID data." IP
   RAPID's refresh keeps reading data.gov.au's catalogue API and download; CLAUDE.md records the acceptance.

**Run.** From `5d2d747`: `collect csiro_dap --backfill` from a runner (`20261015T134625Z-b0252ac2`): passed, 22
requests, all HTTP 200; 899 collections, every one with a description (median 786 characters, longest 3,982; 19
hold HTML, which normalise strips). Then `moria normalise csiro_dap --store r2` from this session: the first attempt
failed reading a bundle from R2 (a broken connection, `20261015T134737Z-fe65bd71`); the re-run passed
(`20261015T134810Z-44a7efe5`): 899 documents, each at its latest version (two bundles, 1,798 records); the sweep
found one email address (low severity: flagged, not quarantined) and nothing high.

**Spend:** $0.

**Consequences.** The descriptions reach embeddings, keyphrases, tags and the index at the next `prepare`. Day 5
when the owner asks.

Next free decision number: D-025.

## D-025 — The SignalBoost proposal built before day 5: horizons, context, relationship change and corroboration, measured against day 4; two detectors pass, five don't, all switched off for the owner (2026-10-15)

**Context.** The owner, before day 5: "I've added a suggestion which I would like you to implement before the Day 5
build" (`docs/SignalBoost-Proposal.md`): multi-horizon analysis (3 to 180 months); multivariate (contextual) anomaly
detection; relationship-change detection; and evidence-based evaluation, retaining an enhancement "only where [it
demonstrates] measurable improvements in detection quality". Acceptance: horizons configurable by source and method
with minimum history; interpretable explanations with provenance; evaluation of incremental value, false positives
and robustness to artefacts; overlapping windows and correlated indicators not counted as independent corroboration.
"Please tell me if you disagree or have concerns. Otherwise, please implement."

**Claude's concerns, raised with the build rather than before it (none is a disagreement with the proposal):**
1. **Short horizons can't be trends.** Mann-Kendall on 3 monthly points can't reach significance, and 6 points can't
   survive Holm across thousands of series; so 3 and 6 months are read as shifts in the recent mean (anomalies), as
   the proposal's "methods appropriate to each horizon" allows.
2. **History.** Measured at as_of 2026-10-14: OpenAlex has 35 months monthly and 16 years annual; the CPC counts 26
   years; ABS and OECD statistics up to 583 months; IP RAPID 321 months; GDELT 3 days. A horizon is tested only where
   a series reaches it, and the long horizons fall mostly on annual statistics and IP RAPID.
3. **More horizons mean more tests.** Each horizon and method is its own Holm family, and a series that fires at
   several horizons is still one line of evidence (the proposal's last criterion applies to day 4's own "2 of 3
   windows" rule too: it is a robustness check, not corroboration).
4. **Context can explain a real signal away** (a whole field rising). So a contextual model adds a detector and an
   alternative explanation; it never hides a band anomaly.
5. **No labelled hindsight set yet** (design §11.3 is day 5's and the owner's). The backtest therefore uses a
   label-free proxy (a flag confirmed by day 4's trend detectors a year later), beside planted changes and nulls.
6. **Adopting a detector is the owner's call** (CLAUDE.md). Every new detector is measured at each scan, but adds
   candidates only when switched on; Claude recommends from the evaluation.

**Built (Claude's engineering choices; they stand until the owner says otherwise).** Settings in `config/detect.yaml`
(`horizons`, `context`, `relationships`, `redundancy`, `evaluation`, `new_detectors`).
- **Horizons** (`src/moria/horizons.py`, inside `moria measure series`): each horizon becomes the series' own
  periods (6 months = 2 quarters = 182 days; shorter than a period, not tested). Short (3, 6 months): the recent mean
  against the trailing baseline's Theil-Sen line, the band from the baseline's own rolling means, 99% after Holm and
  a 25% minimum change. Medium (12, 36): Theil-Sen and Mann-Kendall (at least 8 points). Long (60, 120, 180): the
  same with Mann-Kendall's variance inflated by the residuals' lag-1 autocorrelation (Yue and Wang's effective
  sample size), and the last structural break in slope or level (day 4's optimal partitioning, segments of at least
  24 months). `by_source` limits a source's horizons (GDELT: 3 and 6 months). A profile per series:
  structural_shift, reversal, sustained, long_run or transient. `horizons.parquet`.
- **Context** (`src/moria/context.py`): the latest value against a ridge regression fitted on the baseline before it
  (24 months, 16 quarters, 12 years), row by row in one batched solve: a time trend, the mean of up to 5 peers (the
  series of its own test family whose changes correlated best with its own over the baseline, at least 0.5; chosen
  on the baseline alone), the world or OECD counterpart of an Australian series, and the log volume of a share's
  source. Tested against the full context, the peers alone and the counterpart alone, keeping the context that
  explains it best: a first version credited the less noisy world series when peers and counterpart carried the
  same movement, so an Australia-wide move shared by every peer still read as contextual (found by a test). Each row
  keeps each covariate's contribution and the peers' and counterpart's series ids. A band anomaly whose move the
  context predicts (at least half of it) is marked `explained`. **Coupling:** an Australian series' period-to-period
  changes against its counterpart's, early half against recent half of up to 72 periods, Fisher's test with Holm;
  decoupled (from at least 0.5 to at most 0.2) or coupled. Peers are not tested for coupling (chosen for their
  correlation). `context.parquet`.
- **Relationship change** (`src/moria/concepts.py`, inside `moria measure documents`): **fading** pairs, an
  established pair (at least 10 groups or applications in the baseline, from 2 sources or applicants) whose window
  count falls well below what its baseline lift predicts from each side's activity in the window (exact Poisson
  lower tail, Holm; at least 5 expected, lift at most halved, each side still active), over keyphrase, IPC and Nice
  pairs. **Jurisdictions by class:** `moria ipr metrics` now writes `country_classes.parquet` (applications by
  founding applicants' country and IPC subclass or Nice class, by the month the classes were observable; countries
  only, no party named), and the new, rising and fading tests run on country-class pairs (`ipc_country`,
  `nice_country`). Day 4's rising test keeps its own family (only pairs it tested before), so its results don't move.
- **Corroboration** (`moria measure series`, `moria detect`): flagged series whose first differences correlate at
  least 0.8 (absolute, over the longest trend window, average linkage) share a redundancy group
  (`redundancy.parquet`); candidates carry `redundancy_group`, `redundancy_size` and `corroboration` (1 per series;
  a document candidate's sources, each de-duplication group counted once by its earliest item). An AU/world pair
  takes its Australian series' group.
- **Candidates** (`moria detect`): the new detectors (`short_shift`, `long_trend`, `structural_shift`,
  `contextual_anomaly`, `decoupling`, `fading_combination`, `jurisdiction_shift`) join only when switched on; their
  numbers carry the explanation and their evidence the peers and counterpart (`peer`, `reference`). `moria
  scan-report` adds a section with each detector's counts.
- **`moria eval detectors`** (`src/moria/evaldetect.py`): in memory, on the real layer: changes planted in series no
  detector flags (40 per source and frequency per kind: a doubled period, a 3-month shift, 0.25 more growth a year
  over 36 months, 0.15 more from 60 months back, a 60% jump alone, the same jump with its peers and counterpart, a
  shuffled relationship); null series (the series' own residuals, resampled in blocks of 3, about a flat level or
  its own line); artefacts (every count source's volume and counts up 60% in the last 3 months, or one period
  counted twice); a backtest at 17 dates over 4 years; placebo (window and baseline reassigned) and synthetic
  (pairs cut or tripled) tests of the relationship detectors. Every detector runs over the whole layer with the
  plants in place, so Holm's families are real. The weekly `prepare` workflow runs it after the scan, its report in
  the job summary.

**Calibration and a change of rules, both before the recorded run.**
- A development run (seed 20261015, not recorded) showed the **absolute retention rules miscalibrated**: day 4's own
  band catches 47% of doubled spikes and flags 4.4% of the null series, so "recall at least 50%" and "at most 1%
  false positives" would have rejected day 4 itself. The rules were changed to compare with day 4: incremental value
  (plants caught by the new detector and by no day-4 detector) at least 10%; false positives at most day 4's
  comparable detector's rate on the same nulls plus 1 point, and at most 5%; artefact flags at most 2 points beyond
  day 4's. **This change was made after seeing the development run;** the owner should confirm or replace the rules.
- **Long-window break penalty:** on nulls built with a separate seed (seed + 100), a penalty of 3 times BIC split
  15% of null series, 6 times split 5 to 6% while still catching 17% of planted breaks that day 4 missed, and 10
  times split no fewer while catching half as many. Set to 6. (The 0.3 to 0.6% day 4 measured at 36 points was on
  simulated white noise; these nulls carry real series' heavy-tailed residuals.)
- Long-run trends: Mann-Kendall's variance is inflated for autocorrelation; without it, 6.7% of flat nulls passed.

**Run.** From `7105962` (code at `a0ec05e`): `moria ipr metrics --store r2` (`20261015T171058Z-c2295f58`): passed,
731 series and 679,869 class-pair rows as before, 857,250 country-class rows. `moria eval detectors --as-of
2026-10-15 --store r2` (`20261015T172147Z-0a1a9610`, about 17 minutes): passed; `reports/eval/detectors.md`.
`moria prepare` couldn't run in this session (huggingface.co is refused, and the embeddings need the pinned model),
so the features are one normalise run behind (CSIRO's descriptions, D-024): the keyphrase pairs were skipped in this
run (the report says why), and no scan was run at a new date. A development run of `measure series` at 2026-10-14
took 66 s (23 s for day 4's detectors alone): 12,339 short, 12,112 medium and 26,528 long horizon tests; 18,612
series modelled in context, 348 contextual and 283 band anomalies explained; 1,558 coupling tests; 6,327 flagged
series in 3,209 redundancy groups.

**Results** (`reports/eval/detectors.md`; recall where a detector could test):

| Detector | Recall | Incremental | False positives (day 4's) | Artefact excess | Verdict |
|---|---:|---:|---:|---:|---|
| short-term shift | 31% | 4.8% | 0% (3.8%) | +0.6 pt | fails: incremental |
| long-run trend | 4.2% | 0.8% | 0% (1.2%) | -0.5 pt | fails: incremental |
| structural break | 35% | 13% | 9.5% (3.8%) | -0.4 pt | fails: false positives |
| contextual anomaly | 25% | 0% | 0.6% (3.8%) | -0.4 pt | fails: incremental |
| decoupling | 4.7% | 3.4% | 0% (3.8%) | -0.5 pt | fails: incremental |
| fading pair (IPC and Nice only) | 95% | 95% | 0.0% (0.3%) | n/a | **passes** |
| jurisdiction by class | 85% | 85% | 0.3% (0.3%) | n/a | **passes** |

- **The contextual model adds precision, not recall.** It catches nothing day 4's band misses, but on a jump shared
  by its peers and counterpart it fires on 10% where the band fires on 39%; on nulls 0.6% against 3.8%; and in the
  backtest 15% of its onsets are confirmed a year later against 7.8% of the band's. Its value is the `explained`
  marking (an alternative explanation for the dossier), which the incremental rule doesn't measure.
- **Structural breaks** catch 13% of planted long-run changes that day 4 misses, but split 9.5 to 11% of null series
  (the calibration seed had suggested 5 to 6%; with 116 to 120 nulls the margin of error is about 3 points). The
  backtest confirms 19% of their onsets (the band: 7.8%).
- **Short-term shifts** mostly re-find the band's anomalies (median lead 4 months in the backtest, same confirmation).
- **Decoupling** has little power: 88 established relationships planted, 4.7% found. Few series are long enough.
- **Relationships:** in the real data, 7 fading class pairs; country-class pairs: 26 fading, 14 new, 20 rising.
  Placebo detections stay at day 4's level (0.0 to 0.3% of tests).
- **Artefacts:** no new detector fires more than 0.6 points beyond day 4 under a volume jump or a duplicated period.
- **Day 4's own numbers, for day 5:** the band catches 53% of doubled spikes and flags 2.5 to 3.8% of null series;
  only 7.8% of its onsets are confirmed by a trend a year later. Ranking should not treat band anomalies as strong.

**Checked:** 155 tests pass (one skipped) with no network: horizons tell a break from a shift and from noise, and
skip horizons beyond a series' history; context separates a lone jump from a shared one; coupling finds a broken
relationship; fading pairs and jurisdictions on hand-built tables; the switches; corroboration; the planter; the
evaluation end to end on hand-built series and a minimal layer. Lint and format clean. **Also fixed:**
`prepare.yml` hasn't parsed on main since day 4 (an unquoted colon in a step name: `Scan (day 4): …`), so its
Monday schedule would not have run; fixed on this branch.

**Spend:** $0.

**Consequences.**
- All seven switches are off: the candidates are day 4's, with the new `corroboration` and `redundancy_group`
  columns. The shadow measures are written at every scan and the evaluation reruns weekly.
- The keyphrase half of the fading test, and a scan with every new table, wait for `prepare` on a runner: the next
  Monday after this branch is merged (or `prepare` by hand from main).
- **For the owner:**
  1. **Switch on `fading_combination` and `jurisdiction_shift`?** Claude recommends both (for keyphrase pairs, after
     the first weekly evaluation that tests them).
  2. **The contextual model:** keep it off as a detector, but let day 5's dossiers show "explained by its context"
     on band anomalies? That needs a switch of its own (today it rides with `contextual_anomaly`).
  3. **Confirm or replace the retention rules,** changed after the development run (above).
  4. **Structural breaks:** leave off, or Claude can raise the long-window penalty and re-measure (it costs recall).
  5. Short-term shifts, long-run trends and decoupling: leave off; Claude would keep measuring them in the
     background (they cost about 40 s a scan) unless you'd rather remove them.
  6. Merge this branch (or a pull request) so the weekly `prepare` runs again.

Next free decision number: D-026.

## D-026 — Prepare and the scan run from the build session once Hugging Face was allowed; the keyphrase half of D-025's evaluation; an embedding-reuse bug fixed (2026-10-15)

**Context.** D-025 couldn't run `moria prepare` (huggingface.co refused), so the features were a normalise run behind
and the keyphrase half of the evaluation was skipped. The owner added the Hugging Face connector, then
`huggingface.co` and `us.aws.cdn.hf.co` (where the model's large file is served) to the environment's allowed
domains. The connector alone browses the Hub as text and can't deliver the 133 MB model file.

**Run** (from `7746f71`, then `6908ca2`, all into the bucket):
- `moria prepare --store r2`: the first attempt failed at `features.embed` (`20261015T215717Z-37acbc23`: the model's
  file redirects to `us.aws.cdn.hf.co`, then refused). After the owner allowed it: normalise
  (`20261015T215959Z-2149c365`, nothing new), embed (`20261015T220108Z-39112825`: 132,939 documents, 126,665
  embedded, about 75 minutes), dedup (`20261015T231559Z-ac0eb697`: 126,178 groups), keyphrases
  (`20261015T231628Z-e361eea6`), tags (`20261015T231910Z-eecc5c6c`) passed; **`features.index` failed**
  (`20261015T232004Z-a1b00263`): DuckDB downloads its `fts` extension from `extensions.duckdb.org`, refused to this
  session. The scan doesn't read the index; `moria search` and day 5's counter-evidence do. IP RAPID's metrics were
  current (D-025's `20261015T171058Z-c2295f58`).
- `moria scan --as-of 2026-10-15` (monitor `20261015T232118Z-6ec3b796` to artefacts `20261015T232404Z-bf8ca879`):
  **2,567 candidates, 2,129 with no artefact flag** (acceleration 452, trend 1,068, weak signal 217, anomaly 830).
  All new detectors off, so the candidates are day 4's detectors on the newer layer. **Redundancy:** 1,370 groups
  hold 977 candidates beyond the first of each; for day 5, more than a third of the list is not independent
  evidence. `reports/scan.md`.
- `moria eval artefacts` (`20261015T232417Z-5373a20c`): 6 of 6 seeds caught, 6 of 6 controls clean.
- `moria eval detectors` (`20261015T232643Z-c9954ebf`, with the keyphrase pairs): the series results are D-025's
  (same layer, same seed). **Keyphrase pairs:** 0 fading and 16 new in the real data; placebo 0% fading; only 4
  established pairs were eligible for a planted breakdown, and none was caught. Class pairs: 39 of 40 planted
  breakdowns caught; country-class: 37 of 40 fading and 36 of 40 rising caught. Verdicts unchanged: fading pairs
  (89%, carried by the class pairs) and jurisdictions by class (91%) pass; the other five fail.
  `reports/eval/detectors.md`.

**Fixed (`6908ca2`).** `features.embed` reused vectors only from the *latest* embed manifest, and only if it had
passed; the failed first attempt therefore made the next run re-embed nearly everything (126,665 of 132,939, about
75 minutes, the same vectors) instead of the roughly 1,000 changed items. It now reuses the latest passed run past
any failed ones; a test plants a failed run between two passes.

**Spend:** $0.

**Consequences.**
- The layer is current except the BM25 index. **For the owner:** allow `extensions.duckdb.org` (or let the weekly
  `prepare` on a runner rebuild the index after the merge).
- D-025's questions stand. On the first: the evaluation supports switching on fading pairs for IPC and Nice classes;
  for keyphrase pairs it is unproven (too few established pairs while most feeds are weeks old), though harmless
  (none fire, none in the placebos).

Next free decision number: D-027.

## D-027 — The BM25 index rebuilt from the build session (2026-10-15)

**Context.** D-026 left `features.index` failed: DuckDB fetches its `fts` extension over plain HTTP from
`extensions.duckdb.org`, which the session couldn't reach. The owner then enabled all network access for the
environment.

**Done.** Plain HTTP still had no proxy in this environment, so the extension (DuckDB 1.5.6, linux_amd64) was
downloaded over HTTPS and installed from the file into DuckDB's own extension folder (outside the repo). DuckDB
checks an extension's signature before loading it, and it loaded: the official build. Then `moria features index
--store r2` from `d107ba1` (`20261015T234656Z-74ca25ce`): passed, 132,939 documents. The layer, its index included,
is now current.

**Spend:** $0.

**Consequences.** Nothing in the repo changed for this; a runner installs the extension itself over HTTP. D-025's
questions stand.

Next free decision number: D-028.

## D-028 — The owner's answers on D-025: two detectors on, the context note shown, the rules confirmed, structural breaks off; nothing removed (2026-10-16)

**The owner's answers** to D-025's questions:
1. **"Yes turn on the two passing detectors."** `fading_combination` and `jurisdiction_shift` are on. **"Please don't
   delete/remove the underperforming time series analyses you created. I'd like to revisit them once we've got the
   project into a stable position."** Short-term shifts, long-run trends, structural breaks, the contextual detector
   and decoupling stay in the code, measured at every scan and scored by the weekly evaluation, switched off.
2. **"Yes, show 'explained by its context' in day 5's dossiers."** New setting `context.annotate_explained: true`: a
   band anomaly whose move its context predicts carries `context_explains` in its numbers (the prediction, each
   covariate's contribution, the share explained) and its peers and counterpart as evidence (`peer`,
   `reference`), while `contextual_anomaly` stays off as a detector. An explanation, never a filter.
3. **"Yes, use your 'first look' thresholds. We'll likely run a few calibration and refinement passes later to
   ensure our thresholds are behaving correctly."** The retention rules D-025 revised after its development run
   stand (incremental value at least 10%; false positives at most day 4's comparable rate plus 1 point, at most 5%;
   artefact excess at most 2 points), with the long-window break penalty of 6.
4. **"Agreed. Leave it off for now and revisit later."** Structural breaks stay off.

**Run** (from `75162ee`): `moria scan --as-of 2026-10-15 --store r2` (monitor `20261016T001255Z-876b1e80`, detect
`20261016T001558Z-8e347bd5`, artefacts `20261016T001603Z-77caa023`): **2,634 candidates, 2,191 with no artefact
flag** (acceleration 452, trend 1,068, weak signal 284, anomaly 830); the switches added 7 fading class pairs and 60
country-by-class changes (new, rising or fading); 295 candidates carry the context note; redundancy as D-026 (1,370
groups, 977 candidates behind another). `moria eval artefacts` (`20261016T001608Z-7bb555df`): 6 of 6 caught, 6 of 6
controls clean. `reports/scan.md`.

**Checked:** 156 tests pass (one skipped), the new one showing the note on while the detector is off. Lint and format
clean.

**Spend:** $0.

**Consequences.**
- Day 5 reads the candidates as they now are; the dossier renders `context_explains` beside the alternative
  explanations checklist (design §8.4).
- **To revisit later (the owner):** calibration and refinement passes on the retention thresholds; the five detectors
  switched off (`reports/eval/detectors.md` holds their latest numbers each week); structural breaks' false
  positives (a different fix than a larger penalty, D-025); keyphrase fading pairs once the feeds have a baseline.
- The merge of this branch (or a pull request) is still the owner's.

Next free decision number: D-029.


## D-029 — Day 5 built and run: a ranked queue of 40 dossiers ready for review; the free decision model's suggestions recorded, not ranked (it does not discriminate on marked states); the register's spreadsheet round trip; the digest; a term-only hindsight smoke run (2026-10-16)

**Context.** The owner: "Please complete the Day 5 build." Design §13 day 5: the register export (spreadsheet) and
import (validated, appended as events); the early-warning digest; dossiers; pathway suggestions by Jev-Style 0.8B;
ring quotas and ranking; a term-only hindsight smoke run. Done when there is "the first ranked queue of about 40
dossiers, ready for review". The handover's flags (`docs/handover-day4.md`) were read first: weak signals from
documents are all flagged (show, don't drop); rank within type; OpenAlex surges need sample works; the hindsight run
needs a refit at each date; one ring per candidate; band anomalies are weak; count a redundancy group once.

**Built (Claude's engineering choices; they stand until the owner says otherwise).** Settings in
`config/review.yaml` (`ReviewConfig`); every stage checks its upstream manifests and writes its own.
- **`moria rank --as-of D`** (`src/moria/rank.py`). Every candidate gets **one ring** (flag 7): a one-ring card's;
  core when its label matches the IP-system terms (the core-ring query groups); a statistics series' query ring
  (`rank.rings.by_query`: MSTI, patents and IP regimes adjacent, firms' IP use core, the Economic Outlook and ABS
  population, labour and prices wider world); a GDELT group's ring; an OpenAlex field's, subfield's or domain's
  ring (a map of the 26 fields); else the label's zero-shot ring among its card's rings (OpenAlex topics carry no
  field in the counts); a document candidate the ring most of its de-duplication groups carry. Of 2,634
  candidates: map 1,164, zero-shot 691 (OpenAlex topics), card 321, core terms 286, items 172.
  **Components**, each in (0, 1]: strength as a percentile within type and subject kind (flag 2); breadth (lines
  of evidence, families beyond the first, agreeing detectors) as a percentile; lead time and novelty from the
  most anticipatory and the most novel detector that fired (tables in config), novelty times 0.6 when the nearest
  known trend matches. **Factors:** type (anomaly-only 0.5: D-025's band is weak), flags (coverage 0.7, source
  break 0.7, ingestion 0.5, duplicate 0.6, news cycle 0.5, label drift 0.8: shown, never hidden), scope (a machine
  proxy for Australian relevance: Australia 1.0, aggregates 0.85, another economy 0.7), and 'explained by its
  context' (1.0: shown in the dossier, not ranked, keeping D-028's 'never a filter'). A view's score is the
  weighted geometric mean of its components times the factors. **Selection** (shared with the queue): picks
  alternate between the views by their shares (half each); each ring held to its quota (35/35/30), each source to
  25%, third-order pathways to 20%, one candidate per redundancy group (flag 2's 'count once'); unused ring places
  pass to the other rings (pass 2), then the source cap relaxes (pass 3). **The shortlist** is 100 under the same
  rules: 35 core, 35 adjacent, 30 wider world, all in pass 1; 41 weak signals, 37 accelerations, 22 trends; 10
  flagged. Run `20261016T013509Z-d1d92350` (22 s).
  - **The known-trend threshold was read on the output:** labels' nearest-trend similarities sit at 0.50 to 0.68
    (5th to 95th percentile), so the first setting (0.80) matched 2 of 2,634; reading 32 labels across the range,
    those above 0.68 were mostly apt (an AI-ethics topic to KT11, climate communication to KT01), 0.65 to 0.68
    mixed (Madrid registrations to industrial policy). Set to 0.68: 148 candidates match.
- **`moria dossier`** (`src/moria/dossier.py`): design §8.4 for each shortlisted candidate, as JSON and Markdown in
  `interpretation/dossiers/<id>/<as_of>.*`. The one-line summary, a small chart (a sparkline of the share or the
  level, zeros filled where the source covered the period), the detectors' numbers and runs, the original evidence
  (one item per de-duplication group, primary sources first, with copies), the alternative-explanations
  checklist (the six artefact checks; a seasonal check on monthly and quarterly anomalies; recorded
  administrative causes, `dossier.administrative_events`, two from D-022; 'explained by its context' with its
  share, D-028; the nearest known trend; the redundancy group's other members), counter-evidence (BM25 hits for the
  label's words that also use words of the opposite direction, at least half the words present), primary sources
  in the window that mention the subject, analogues (earlier items nearest the candidate's own, by embedding, for
  documents; the series' own similar past moves and whether they lasted, or how unusual its latest growth is, for
  series), the history in earlier scans and the ranking's components. Untrusted text is escaped in the Markdown
  (no links or images can be made from a title). Two additions made checks possible that the detectors couldn't:
  - **OpenAlex sample works** (flag 3): for a surge or anomaly, the works behind the count by venue (one group_by
    call, exact) and a seeded random sample to read (one call), from the free daily budget with the collector's
    guard (no prepaid key, a reserve kept). **8 of 16 sampled were concentrated** (one venue holds half or more):
    the 'Byzantine studies' surge is 13 works, 85% of them chapters of Cambridge University Press ebooks.
  - **IP RAPID applications** behind a class pair or a country-by-class change, from the lake (organisations named;
    an individual only as 'an individual'). It found that a 'rising' pair can be **reclassification**: the
    coffee-and-tea pair's seven window applications were filed in 2019 to 2022 and classified in the window. A
    `reclassified` check (half the applications filed before the period) and a `few_applicants` check follow.
  - Shortlist: 100 dossiers in 5.4 minutes (`20261016T013532Z-a9a73742`); checks flagged: redundancy 32, coverage
    10, source break 10, concentrated works 8, explained by context 6, known trend 4, few applicants 3,
    administrative 1, reclassified 1; 75 with a chart, 25 with counter-evidence, 58 with related primary sources.
- **`moria pathways`** (`src/moria/pathways.py`). The model's wrapper, scorer and build script were read again
  before running (D-021's review holds: the wrapper launches only the local scorer; the scorer is a JSON-lines
  server over libllama with no network code; the build runs CMake and the compiler with curl off); every file is
  pinned to revision `edf37c26` and its SHA-256 (all matched); the scorer is built from llama.cpp `441df11f`
  (`--build-scorer`). Eleven questions per dossier: P1 to P6 as true-or-false statements (§2.2, in Australian
  terms), the order, and a machine interpretation (origin, horizon, stance, impact; design §7's `moria interpret`
  folded in, since the state is shared). The state wraps every source text in `<data>` markers, defanged, after a
  line saying it is data (SOP §22). Responses are cached in the bucket under a key of the model, the questions and
  the state. 100 dossiers in 9 minutes on this session's 4 CPUs, 7.3 of them deciding (about 4.4 s a dossier;
  `20261016T014054Z-2b6ca37d`).
- **What the model said, read before using it:** P2 is exactly 0.50 for every dossier; P3 to P6 barely move (0.43 to
  0.58 across the 100); horizon and stance were the same answer for every dossier; only P1 varies, and sensibly
  (higher for IP RAPID's filings). The top pathway was P6 for 77, so a ranking by it would have followed the order
  answer (37 order-3), which put population series at order 1.
- **So a check, with its rule fixed before the recorded run:** relevant synthetic anchors (an AI-inventorship
  ruling, a renewal scam, a filing surge, falling fee income, a patent-system review) must score at least 0.05
  above irrelevant ones (a cash-rate decision, a cyclone, a football result, rain) on the top pathway, and the top
  pathway's interquartile range over 20 of the scan's dossiers must be at least 0.02. **Disclosed in order:** the
  rule came after the first run's degenerate output, and an exploratory comparison of five state formats on six
  anchors and 20 dossiers (not recorded) came before it: the full marked state separated by 0.002; the summary
  sentence alone 0.066 and with examples 0.058 (both pass, both unmarked, so they break SOP §22); the summary
  inside markers 0.040, and with the 'it is data' line 0.024 (every order 3). The model discriminates only when
  the security rule is broken, and weakly then. **`moria eval pathways`** (`20261016T015033Z-77d0d9f7`): separation
  0.007 (rule 0.05), spread 0.025: **fails**.
- **Decision (Claude's, inside the step; the switch is the owner's):** the suggestions are recorded in the register,
  shown in the dossiers, the spreadsheet and the digest, attributed to the model and labelled unconfirmed, and
  **left out of the ranking and the third-order cap** (`pathways.use_in_ranking: false`); the cap reads orders a
  person confirmed. With the switch on, the queue uses each pathway as a percentile among the shortlist (each
  question has its own level), never the raw probabilities. A cheaper baseline was also tried and not built: the
  tagger's encoder against the six statements passes the anchor rule easily (0.19, spread 0.065) but ranks the
  scan's IP RAPID class pairs lowest (their labels are codes) and private education income near the top. The
  anchor rule is necessary, not sufficient; the owner's labels are the yardstick (§11.2).
- **`moria queue`** (`src/moria/queue.py`): the queue of 40 from the shortlist, the views alternating, the quotas,
  the source cap, the redundancy rule; and the sensitivity of the queue to each weight. **40 places, 14 core, 14
  adjacent, 12 wider world, all within their quotas; 20 picked by each view; 16 weak signals, 15 accelerations, 9
  trends; 3 flagged** (`20261016T014955Z-67cef29f`). Sensitivity (`reports/queue.md`): with no flag penalty 28 of the 40 places
  stay; halving the strength weight keeps 34 (early warning) and 35 (strategic); every other weight halved or
  raised by half keeps 37 to 40. The flag penalties decide most of the queue's edge, and are the first setting to
  review after the first round.
- **`moria register sync|export|import`** (`src/moria/register.py`): an append-only log (`queued`,
  `machine_pathways`, `machine_interpretation`, `review`, `missed`), each event's id the hash of its content (a
  re-run appends nothing), the state a view. The spreadsheet (labelling by spreadsheet, D-006) has the rules, the
  queue (grey machine columns, yellow reviewer columns, lists of allowed values), the dossiers line by line, and a
  sheet for missed signals (§6.3). The import validates every row (allowed values; the lifecycle's transitions,
  `lifecycle.transitions`; a reason for every rejection; an order for every confirmed pathway and a chain for an
  order of 3; 'validated' needs pathways, Australian relevance and a baseline relation; 'reinforces' a known
  trend), sweeps the reviewer's free text, and appends one `review` event per changed row; any error rejects the
  whole file and names the first rows and columns. Sync: 120 events for the 40 (`20261016T014958Z-1625986c`);
  export `20261016T014959Z-8741e464` (`interpretation/register/exports/20261016T014959Z-8741e464.xlsx`). The round
  trip was tested on a copy of the real layer in a scratch store (a bad file refused whole, a good one appended, a
  re-import appended nothing); nothing was imported into the bucket.
- **`moria digest`** (`src/moria/digest.py`): the early-warning view for IPAVentures: the 15 highest clean
  early-warning candidates (at most 3 from one source), the 5 highest flagged ones with their flags, what moved by
  10% or more since the previous scan (clean ones only: flagged ones move with their sources' onboarding), the
  territories' coverage in the queue, and the limits (`20261016T015002Z-ed7d7570`; 1,566 in the view, 1,217 clean,
  172 new since 2026-10-14, none moved by 10%; every territory matched in the queue).
- **`moria queue-report`** (`reports/queue.md`, aggregates only), **`moria review`** (the chain: rank, dossier,
  pathways, queue, register sync and export, digest), **`moria show`** (a dossier, the analyst's terminal only).
- **`moria eval hindsight`** (`src/moria/hindsight.py`): the term-only smoke run (§11.3). At each date: series at
  their point-in-time vintages without OpenAlex (its topics come from a classifier trained in 2024) or GDELT (no
  history); the keyphrase vocabulary and its first-seen dates **fitted again on the documents visible then**;
  de-duplication by URL and title only; no embeddings, clusters, micro-clusters, zero-shot tags, decision model or
  artefact checks; rings from the cards and maps; a term-only queue of 40. `config/hindsight.yaml` is **Claude's
  draft (proposed)**: the three candidate developments of §11.3 with approximate mainstream months and match rules,
  no non-events. **Disclosed:** a first look at H1 (not recorded) matched a plain trend in Nice class 5 that had
  run since 2017, two months before the shock of March 2020, so matches now need a detector of change
  (`match_detectors`: no plain trend or divergence); the recorded run came after that change. **Result**
  (`20261016T015244Z-4dbb7b93`, nine dates, 100 to 118 s each, `reports/eval/hindsight.md`): all three raised by
  their mainstream month (rule: at least 50%); leads of 2 months (COVID: the March 2020 anomaly in Nice class 5),
  0 (metaverse: an acceleration in a class 9, 35 or 41 series at March 2022) and 6 (generative AI: new and rising
  G06N combinations and applicant countries from December 2022), a median of 2 (rule: at least 6); only COVID made
  a term-only queue (the other two are ranking cut-offs). With a proposed set, loose match rules and approximate
  mainstream months, these numbers test the machinery, not Moria.
- **Also changed:** `measures.load_series` takes an `only` set (pushed into the SQL); `concepts.build` runs without
  embeddings (no clusters or micro-clusters) for the term-only variant; the weekly `prepare` workflow runs the
  review after the scan, with the model and its scorer cached, and puts the two aggregate reports in the job
  summary.
- **Departures from the design, a line each:** dossiers are versioned by scan date; `moria interpret` is part of
  `moria pathways`; a scope factor and a 25% source cap are additions; the third-order cap uses confirmed orders
  until the suggestions are switched on; counter-evidence is by BM25 (no neighbour search); 'what became of'
  analogues waits for register history; the register is Parquet event files per run, not one partitioned table.

**The queue, read (in this session; labels stay in the bucket).** It is a first queue: IP RAPID class pairs and
country-by-class changes, AI patent families (OECD), IP charges in services trade (ABS), provisional patent
applications, OpenAlex topics and macro series, and three flagged news concepts. **Nothing in it weighs relevance
to the IP system yet** (the suggestions are off), so some OpenAlex topics with no evident pathway (history, number
theory) are in it, one of them already flagged by its dossier as concentrated works: triage parks those
(`no_pathway`).

**Checked:** 173 tests pass with no network (the BM25 test is skipped where DuckDB's `fts` extension can't be
fetched, as in CI): the selection rules (quotas, redundancy, the source and
third-order caps, the passes), rings, percentiles, the defanged state, Markdown escaping, the chain end to end on a
hand-built layer (rank, dossiers, a scripted backend, the cache, the queue with the switch off and on, no backend),
the register's round trip (a refused file appends nothing, hidden characters swept, a forbidden move refused), the
digest, the queue report (no labels or ids), the pathway check and the hindsight run; and the CLI never reaches the
scripted backend. Lint and format clean. Every recorded run is from `b3e5f4e`, clean.

**Spend:** $0. OpenAlex: 32 list calls of the free daily credits. Downloads: the decision model (529 MB) from
Hugging Face and llama.cpp from GitHub, both pinned. The bucket gains the dossiers, the review tables, the
register and the spreadsheet (a few MB).

**Consequences.**
- The first ranked queue of 40 dossiers is ready for review: day 5's 'done when'. `docs/handover-day5.md` lists
  the flags.
- **For the owner:**
  1. **The first review round** (about 3 to 4 hours, §2.5): the spreadsheet is in the bucket at
     `interpretation/register/exports/20261016T014959Z-8741e464.xlsx`, or `uv run moria register export --as-of
     2026-10-15 --out review.xlsx --store r2` on your machine; fill the yellow columns; then `uv run moria register
     import review.xlsx --store r2`. The rules are on its first sheet.
  2. **The decision model:** its suggestions don't discriminate on states that keep the security rule. Options:
     (a) leave them recorded and unranked (Claude's recommendation for now); (b) the T4 test and a larger free model
     on a free GPU (the 2B sibling or JEV-9B; free, but a notebook needs a person); (c) Matilda-Jev (paid menu M1);
     (d) your labels from the first round calibrate a free one (design §11.2). Switching `pathways.use_in_ranking`
     on is yours, after `moria eval pathways` passes.
  3. **The hindsight set** (`config/hindsight.yaml`, proposed): choose the developments blind to Moria's output,
     add non-events and pass rules (about an hour, §2.6). The smoke run's numbers are not the sprint's result.
  4. **The ranking's settings** (quotas, weights, flag penalties, the scope factor, the ring maps, the known-trend
     threshold): after the first review round, with `reports/queue.md`'s sensitivity table.
  5. Still open: the T4 test and the codebook (D-021); KT20 to KT24 (D-020); the wishlist; the merge of this
     branch (or a pull request).

Next free decision number: D-030.

## D-030 — The dashboard: public counts on GitHub Pages, the signals from a private file read in the browser, practice data to learn on; every statistic explained (2026-10-16)

**Context.** The owner: "Information is only useful if it is interpretable. Right now, the findings of Moria are
difficult to interpret and understand." They asked for a dashboard that visualises the findings of day 5 (and later
work) for exploratory analysis; accessible via the GitHub webpage; for a reader of low technical sophistication; that
never influences or reshapes the data; intuitive charts (lines over time, error bands on predictions), interactive
and overlayable; a hover explainer for every statistical number and method; fun and colourful, with progressive
disclosure and small touches of whimsy; that educates about what the data represents, its shortcomings and how it
was sourced; with small references to Khazad-dûm. CLAUDE.md listed a dashboard under "not to build yet"; the owner's
request supersedes that line, which is updated.

**The constraint that shaped it.** The repo is public and GitHub Pages serves it publicly, while labels, titles,
links and dossiers live only in the private bucket (CLAUDE.md's security rules). So the page has three modes:
- **public**, the default: aggregates only (`dashboard/data/public.json`), the same rule as `reports/`;
- **private**: the analyst opens a file from the bucket (`interpretation/dashboard/as_of=<D>/dashboard.json.gz`,
  downloadable from Cloudflare's R2 console) and the browser reads it. Nothing is uploaded: the page's content
  security policy allows no outbound connection and no third-party script, font or tracker (ECharts 5.6.0 and three
  OFL fonts are vendored in `dashboard/assets/`); the file isn't stored; closing the tab forgets it;
- **practice**: invented Middle-earth data (`dashboard/data/practice.json`) so the private views can be seen and
  learnt without the file.
No new security exception: nothing private is published, and `--out` refuses a path in the repo outside `data/`.

**Built (Claude's engineering choices; they stand until the owner says otherwise).**
- **`moria dashboard [--as-of D] [--out PATH] [--practice-only]`** (`src/moria/dashboard.py`): one read of the scan
  and the review; the public bundle (funnel, candidates by type, detector, origin and ring, flags, series tested,
  p-value histograms with Holm and Benjamini-Hochberg counts, score histograms, the flow from source to type to
  outcome, the queue's make-up and quotas, the sensitivity table, the dossiers' checks, the suggestions'
  distributions, document volumes, collection days, the evaluations, the scans' history, the public config); the
  private bundle (every candidate with its numbers, components, factors and checks; each series candidate's series as
  tested, with each trend window's Theil-Sen line and interval, the anomaly's expected band, the acceleration's halves,
  change points and surge windows; the window items behind document candidates; the dossiers, suggestions and the
  register's state). **The data is not reshaped:** values are copied; the two things the outputs don't store (each
  fit's intercept, each anomaly's band) are recomputed with the detectors' own functions on the same matrices
  (`measures.build_group`, `stats.theil_sen`) and checked against the stored slopes and z-scores, a mismatch left
  out and counted. On the scan of 15 October: 2,634 candidates, 2,386 series, **6,980 fits, every one matching**,
  7,076 items, 100 dossiers; private bundle 2.8 MB (gzip), public 133 KB. Run `20261016T055322Z-c0959d05`, from
  `4859a91`, clean.
- **The practice bundle** (`src/moria/dashboard_practice.py`): 228 invented series (Middle-earth labels) through the
  real detectors (`measures._run`, `detect.series_candidates`), 30 invented document concepts and 6 IP pairings, and
  every candidate through the real ranking and selection (`rank.score_candidates`, `rank.select`, `queue.rescore`,
  `queue.sensitivity`): 192 candidates, 97 shortlisted, 40 queued. Deterministic; built from the public bundle
  alone (`--practice-only`, no store). What is about Moria itself (sources, settings, evaluations, volumes,
  collection days) stays real, and the page says so.
- **The page** (`dashboard/index.html`, ES modules in `dashboard/assets/js/`, no build step): eight levels of the
  mine, each starting simple: Start here (the West-gate: the journey of a signal as a clickable cross-section of the
  mine, the four types as gems, the rings, the Doors of Durin); the review queue (mithril: cards, and a drawer per
  candidate: the evidence drawn, the numbers with plain readings and a forest plot, the alternative explanations, the
  documents, why it ranked here as an equation, the model's suggestions with their caveat, history); all candidates (a
  Sankey from source to outcome, a flags heat table, a candidate map with selectable axes, a searchable table); change
  over time (the Mirrormere: up to eight series overlaid, as published, indexed or as tested, with trend lines and
  bow-tie intervals, expected bands, accelerations, change points, surge windows; one axis only); how ranking works
  (the forge: a what-if that re-runs the ranking under the reader's settings); statistics explained (playgrounds that
  run Moria's own tests, ported: dig a series; Durin's Bane, multiple testing with the real p-values; rare finds);
  sources and limits (the Chamber of Mazarbul); a glossary. About 80 explainers; hovering a number reads that value.
  Colours validated (the four types adjacent-safe in both modes, with a shape per type in the scatter; the rings an
  ordinal ramp); light and dark ("light a lantern"); every chart with a table view; reduced motion respected.
- **The forge proves itself:** its ranking is a line-for-line port of `rank.geomean`, `view_scores` and `select`
  (the weights' configured order is exported so the sums match to the bit). At Moria's settings it reproduces the
  real shortlist (100) and queue (40) in order, shown on the page; the tests run it under Node on the hand-built
  layer and the practice bundle.
- **Elsewhere:** `prepare.yml` runs `moria dashboard` after the review; `.nojekyll`; the visual index links to the
  dashboard; `dashboard/data/` is git-ignored but for the two public files; `docs/dashboard.md` is the owner's
  guide; the hygiene test now covers `.js` and `.css`.

**Checked:** 179 tests pass with no network (one skip as before): the public bundle holds no candidate id, label,
title or link; the private bundle's fits match; `--out` refuses the repo; the practice bundle is deterministic and
invented, and the committed copy is current; the JavaScript what-if reproduces both queues. Lint and format clean.
The page was driven in Chromium (Playwright) in all three modes, both themes: no console errors, no request outside
the site. An audit of every place the page builds markup: source text reaches it only as text, or escaped in chart
tooltips; counts are coerced to numbers before any SVG; links open only when they are plain http(s) addresses; a
CSV download neutralises spreadsheet formulas.

**Spend:** $0. Downloads: ECharts and three fonts from npm's CDN, pinned and vendored (licences beside them).

**Consequences.**
- The findings can be read by anyone with the page, and in full by anyone with the private file.
- **For the owner:**
  1. **Switch on GitHub Pages** (Settings, Pages: deploy from the branch `main`, folder `/ (root)`), after merging
     this branch; then the dashboard is at https://thomas-amann-ipaustralia.github.io/Moria/dashboard/
     (`docs/dashboard.md`).
  2. **The private file** for this scan is in the bucket at `interpretation/dashboard/as_of=2026-10-15/
     dashboard.json.gz`; the weekly workflow writes a new one each Monday.
  3. The public page's counts change when a build session commits `dashboard/data/` (as with `reports/`). If you
     would rather the weekly workflow publish them, that needs the workflow to commit to `main`, or a Pages
     deployment from the workflow: your call.

Next free decision number: D-031.
