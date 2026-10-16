# Moria

A broad signal-detection and validation engine for IP Australia's strategic foresight. It scans public data across
the IP system, its adjacent fields and the wider world for trends and weak signals. Each candidate must show a
pathway to the IP system, and people validate it. The validated signals are then read through PESTLE, SWOT/TOWS and
a Futures Cone, each finding traceable to its evidence. Free by default: scikit-learn, DuckDB and open Hugging Face
models (including a free Jev-class decision model), with Cloudflare R2 for storage and GitHub Actions or the GCE
free tier for compute.

**Status: days 1 to 5 of the machinery sprint, the Tier 1 cleanup and the widening of sources are built** (D-007,
D-011 to D-013, D-018, D-020, D-021, D-022, D-029). 43 sources: daily feeds (news, legislation, IP Australia, WIPO, APH's committee
feeds, peer IP offices, the OECD and a breadth pack), weekly counts and statistics (OpenAlex over the whole topic
taxonomy, ABS and OECD series, WIPO treaty notifications, the IP RAPID lake with individuals' names hashed), bulk
sources in the lake (the Open Australian Legal Corpus, WIPO's statistics, STIP Compass), patent counts on BigQuery,
and documents read once. Day 3 turns them into an evidence layer: 122,243 documents and about a million series,
normalised with both dates and a security sweep, embedded, de-duplicated, keyphrased, indexed and tagged, and
monthly IP RAPID metrics (`reports/evidence-layer.md`). Day 4 scans it: trends, accelerations, change points,
anomalies, low-base surges and Australia/world divergence over about 27,000 series, the five weak-signal indicators
over the documents, and six artefact checks on every candidate, themselves tested against seeded artefacts
(`reports/scan.md`, `reports/eval/artefacts.md`). Day 5 ranks the candidates for the two views under ring quotas,
builds an evidence dossier for each of a shortlist of 100, asks a free decision model for pathway suggestions
(recorded, not yet ranked: they did not pass their check), and picks a queue of 40 for review, with the reviewer's
spreadsheet, the register's events and the early-warning digest in the private bucket (`reports/queue.md`,
`reports/eval/pathways.md`, and a term-only hindsight smoke run, `reports/eval/hindsight.md`). **The dashboard**
(`dashboard/`, D-030; published by GitHub Pages, [`docs/dashboard.md`](docs/dashboard.md)) explains and explores the
scan: counts for everyone, the signals themselves for anyone with the private file, invented practice data to learn
it on. Read
[`CLAUDE.md`](CLAUDE.md) for the rules and commands, and
[`docs/design.md`](docs/design.md) for the design. The decisions are in [`docs/decisions.md`](docs/decisions.md);
what's next is in [`docs/handover-day5.md`](docs/handover-day5.md) and
[`docs/sources-backlog.md`](docs/sources-backlog.md).

```bash
uv sync --group dev                          # install
uv run pytest                                # tests (no network)
uv run moria sources                         # the source cards
uv run moria env-check                       # which keys are present; one cheap call per service
uv run moria collect legislation_frl         # yesterday (UTC), into data/store/ (git-ignored)
uv run moria collect-daily --store r2        # what the daily workflow runs
uv run moria collect-weekly --store r2       # what the weekly workflow runs (OpenAlex, ABS, IP RAPID, WIPO Lex)
uv run moria collect ipaustralia_site --backfill  # a first snapshot: every page in the sitemap
uv run moria discover https://example.org/news   # what a new source's address answers (never its text)
uv run moria ipr refresh --limit 1           # IP RAPID smoke test: convert one table locally, upload nothing
uv run moria terms check --weeks 2           # search terms against sampled days of news
uv run moria census abs_headline             # profile a source's latest collection (aggregates only)
uv run moria baseline                        # the known-trends baseline
uv sync --extra models                       # the local embedding model's runtime (onnxruntime, tokenizers)
uv run moria prepare --store r2              # day 3's chain: normalise, embed, dedup, keyphrases, tag, index, IP RAPID metrics
uv run moria normalise                       # the raw store into lake/documents, lake/series, lake/observations
uv run moria search "plant breeder's rights" --store r2   # BM25 over every document (your own terminal only)
uv run moria evidence-report --store r2      # reports/evidence-layer.md (aggregates only)
uv run moria scan --store r2                 # day 4's chain as of today: monitor, measures, detect, artefact checks
uv run moria scan-report --store r2          # reports/scan.md (aggregates only)
uv run moria eval artefacts --store r2       # the artefact checks against seeded artefacts, with controls
uv run moria candidates --clean --store r2   # the strongest unflagged candidates (your own terminal only)
uv run moria review --store r2 --build-scorer  # day 5's chain: rank, dossiers, pathway suggestions, the queue,
                                               # the register's events, the reviewer's spreadsheet, the digest
uv run moria register export --out review.xlsx --store r2   # the reviewer's spreadsheet (your own disk)
uv run moria register import review.xlsx --store r2         # a reviewed spreadsheet, validated, into the register
uv run moria show sig-0123456789ab --store r2  # a dossier (your own terminal only)
uv run moria queue-report --store r2         # reports/queue.md (aggregates only)
uv run moria eval pathways --store r2        # does the decision model discriminate? (reports/eval/pathways.md)
uv run moria eval hindsight --store r2       # the term-only hindsight smoke run (reports/eval/hindsight.md)
uv run moria dashboard --store r2 --out ~/moria-dashboard.json.gz   # the dashboard's data: public, practice and
                                               # private bundles (the private one to the bucket and your own disk)
python3 -m http.server 8000                  # then http://localhost:8000/dashboard/ (or GitHub Pages)
```

| Path | What it is |
|---|---|
| `dashboard/` | The dashboard (GitHub Pages): the scan, the queue, every candidate, series over time, the ranking's what-if, the statistics explained, sources and limits. Public counts, private detail from a file read in the browser, invented practice data (`docs/dashboard.md`) |
| `index.html` | A visual index (open it in a browser): purpose, the questions and their expected sources, the three rings, what is stored and what is not, what is built and what is still to come |
| `CLAUDE.md` | The rulebook for build sessions: scope, rules, commands |
| `docs/design.md` | The system design (v0.3) |
| `docs/decisions.md` | The decision log (append-only) |
| `docs/setup.md` | Accounts and keys: what goes where (GitHub Actions secrets, the Claude Code environment) |
| `docs/mining-explained.md` | How the mining works, in plain terms, with a worked example and what labelling looks like |
| `config/` | Settings, source cards, territories (public parts), broad themes, the feature stages (`features.yaml`), the tag codebook (`codebook.yaml`, proposed), the detectors and artefact checks (`detect.yaml`), the review (`review.yaml`: ranking, quotas, dossiers, the decision model, the lifecycle, the digest), the hindsight set (`hindsight.yaml`, proposed), the sweep's allowlist (`sweep.yaml`, the owner's) |
| `src/moria/` | The package: store, records, manifests, HTTP client, collectors, the bulk stages (IP RAPID, the legal corpus, WIPO statistics, STIP Compass), terms check, census, discover; day 3's normalise, sweep, embed, features, tags, IP RAPID metrics and the evidence report; day 4's statistics, series and document measures, ingestion monitor, detect, artefact checks, seeded evaluation and scan report; day 5's rank, dossier, pathways, queue, register, digest, queue report and hindsight; CLI |
| `.github/workflows/` | `ci`, `collect-daily` (then normalise), `collect-weekly`, `prepare` (weekly, then the scan, the seeded check and the review), `collect-source`, `terms-check`, `probe` |
| `config/territories.yaml` | The five Growth Territories: descriptions, search terms, pathways and IP RAPID indicators |
| `config/baseline.yaml` | The known-trends baseline (a draft for the owner), drafted from the foresight syntheses |
| `reports/` | Generated reports for the owner, aggregates only: the terms check, a census per source, the evidence layer, the scan, the review queue, and the evaluations (seeded artefacts, the SignalBoost detectors, the decision model's suggestions, hindsight) |
| `scripts/memprobe.py` | Peak-memory probe of the planned workloads; re-run it on the target runner on day 1 |
| `scripts/probe_jevstyle.py` | Memory, speed and behaviour probe of the free Jev-class decision model |
| `scripts/t4_jevstyle_speed.py` | The decision model's speed test on a free T4 (Kaggle or Colab), for the owner to run |
| `scripts/demo_embed_cluster.py` | A small runnable demo of embedding, clustering, novelty and look-alikes (laptop, Kaggle or Colab) |
| `sop-agent-construction-v2.md` | The owner's SOP for building on evidence; it governs how this repo is built |
| `Access-architecture-and-reusable-adapters.md` | Catalogue of horizon-scanning sources, protocol adapters and the provenance model |
