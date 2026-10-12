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

Next free decision number: D-014.
