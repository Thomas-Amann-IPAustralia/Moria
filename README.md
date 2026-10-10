# Moria

A broad signal-detection and validation engine for IP Australia's strategic foresight. It scans public data across
the IP system, its adjacent fields and the wider world for trends and weak signals. Each candidate must show a
pathway to the IP system, and people validate it. The validated signals are then read through PESTLE, SWOT/TOWS and
a Futures Cone, each finding traceable to its evidence. Free by default: scikit-learn, DuckDB and open Hugging Face
models (including a free Jev-class decision model), with Cloudflare R2 for storage and GitHub Actions or the GCE
free tier for compute.

**Status: day 1 of the machinery sprint is built** (D-007): five daily collectors, the store, manifests, the
environment check, and CI. Read [`CLAUDE.md`](CLAUDE.md) for the rules and commands, and
[`docs/design.md`](docs/design.md) for the design. The decisions are in [`docs/decisions.md`](docs/decisions.md).

```bash
uv sync --group dev                          # install
uv run pytest                                # tests (no network)
uv run moria sources                         # the source cards
uv run moria env-check                       # which keys are present; one cheap call per service
uv run moria collect legislation_frl         # yesterday (UTC), into data/store/ (git-ignored)
uv run moria collect-daily --store r2        # what the daily workflow runs
```

| Path | What it is |
|---|---|
| `CLAUDE.md` | The rulebook for build sessions: scope, rules, commands |
| `docs/design.md` | The system design (v0.3) |
| `docs/decisions.md` | The decision log (append-only) |
| `docs/setup.md` | Accounts and keys: what goes where (GitHub Actions secrets, the Claude Code environment) |
| `docs/mining-explained.md` | How the mining works, in plain terms, with a worked example and what labelling looks like |
| `config/` | Settings, source cards, territories (public parts), broad themes |
| `src/moria/` | The package: store, records, manifests, HTTP client, collectors, CLI |
| `.github/workflows/` | `ci`, `collect-daily`, `probe` |
| `config/territories.yaml` | The five Growth Territories: descriptions, search terms, pathways and IP RAPID indicators |
| `scripts/memprobe.py` | Peak-memory probe of the planned workloads; re-run it on the target runner on day 1 |
| `scripts/probe_jevstyle.py` | Memory, speed and behaviour probe of the free Jev-class decision model |
| `scripts/demo_embed_cluster.py` | A small runnable demo of embedding, clustering, novelty and look-alikes (laptop, Kaggle or Colab) |
| `sop-agent-construction-v2.md` | The owner's SOP for building on evidence; it governs how this repo is built |
| `Access-architecture-and-reusable-adapters.md` | Catalogue of horizon-scanning sources, protocol adapters and the provenance model |
