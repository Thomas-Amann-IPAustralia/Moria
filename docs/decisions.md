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

Next free decision number: D-002.
