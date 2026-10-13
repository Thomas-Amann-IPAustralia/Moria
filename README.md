# Moria

A broad signal-detection and validation engine for IP Australia's strategic foresight. It scans public data across
the IP system, its adjacent fields and the wider world for trends and weak signals. Each candidate must show a
pathway to the IP system, and people validate it. The validated signals are then read through PESTLE, SWOT/TOWS and
a Futures Cone, each finding traceable to its evidence. Free by default: scikit-learn, DuckDB and open Hugging Face
models (including a free Jev-class decision model), with Cloudflare R2 for storage and GitHub Actions or the GCE
free tier for compute.

**Status: days 1 and 2 of the machinery sprint and the Tier 1 cleanup are built** (D-007, D-011 to D-013, D-018).
Seventeen daily sources (news, legislation, IP Australia, WIPO, APH's committee feeds, and peer IP offices: UKIPO,
EPO (two feeds), IPONZ, CIPO, USPTO, IPOS and Korea's MOIP), five weekly ones (OpenAlex counts over the whole topic
taxonomy, ABS headline series and spreadsheet data cubes, WIPO treaty notifications, the IP RAPID lake with
individuals' names hashed), bulk sources in the lake (the Open Australian Legal Corpus, WIPO's bulk statistics),
patent counts on BigQuery (dry run), documents read once (foresight syntheses, peer offices' strategies, IP
Australia's publications), a known-trends baseline, the terms check, and census reports. Read
[`CLAUDE.md`](CLAUDE.md) for the rules and commands, and [`docs/design.md`](docs/design.md) for the design. The
decisions are in [`docs/decisions.md`](docs/decisions.md); what's next is in
[`docs/handover-day2.md`](docs/handover-day2.md) and [`docs/sources-backlog.md`](docs/sources-backlog.md).

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
```

| Path | What it is |
|---|---|
| `CLAUDE.md` | The rulebook for build sessions: scope, rules, commands |
| `docs/design.md` | The system design (v0.3) |
| `docs/decisions.md` | The decision log (append-only) |
| `docs/setup.md` | Accounts and keys: what goes where (GitHub Actions secrets, the Claude Code environment) |
| `docs/mining-explained.md` | How the mining works, in plain terms, with a worked example and what labelling looks like |
| `config/` | Settings, source cards, territories (public parts), broad themes |
| `src/moria/` | The package: store, records, manifests, HTTP client, collectors, the bulk stages (IP RAPID, the legal corpus, WIPO statistics), terms check, census, discover, CLI |
| `.github/workflows/` | `ci`, `collect-daily`, `collect-weekly`, `collect-source`, `terms-check`, `probe` |
| `config/territories.yaml` | The five Growth Territories: descriptions, search terms, pathways and IP RAPID indicators |
| `config/baseline.yaml` | The known-trends baseline (a draft for the owner), drafted from the foresight syntheses |
| `reports/` | Generated reports for the owner, aggregates only: the terms check and a census per source |
| `scripts/memprobe.py` | Peak-memory probe of the planned workloads; re-run it on the target runner on day 1 |
| `scripts/probe_jevstyle.py` | Memory, speed and behaviour probe of the free Jev-class decision model |
| `scripts/demo_embed_cluster.py` | A small runnable demo of embedding, clustering, novelty and look-alikes (laptop, Kaggle or Colab) |
| `sop-agent-construction-v2.md` | The owner's SOP for building on evidence; it governs how this repo is built |
| `Access-architecture-and-reusable-adapters.md` | Catalogue of horizon-scanning sources, protocol adapters and the provenance model |
