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

Next free decision number: D-003.
