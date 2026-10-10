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

Next free decision number: D-007.
