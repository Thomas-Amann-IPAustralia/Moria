# Moria

A broad signal-detection and validation engine for IP Australia's strategic foresight. It scans public data across
the IP system, its adjacent fields and the wider world for trends and weak signals. Each candidate must show a
pathway to the IP system, and people validate it. The validated signals are then read through PESTLE, SWOT/TOWS and
a Futures Cone, each finding traceable to its evidence. Free by default: scikit-learn, DuckDB and open Hugging Face
models (including a free Jev-class decision model), with Cloudflare R2 for storage and GitHub Actions or the GCE
free tier for compute.

**Status: design v0.3 proposed, nothing built yet.** Read [`docs/design.md`](docs/design.md) (§0.1 lists what
changed); the decisions behind it are D-001 to D-005 in [`docs/decisions.md`](docs/decisions.md).

| Path | What it is |
|---|---|
| `docs/design.md` | The system design (v0.3) |
| `docs/decisions.md` | The decision log (append-only) |
| `docs/mining-explained.md` | How the mining works, in plain terms, with a worked example and what labelling looks like |
| `scripts/memprobe.py` | Peak-memory probe of the planned workloads; re-run it on the target runner on day 1 |
| `scripts/probe_jevstyle.py` | Memory, speed and behaviour probe of the free Jev-class decision model |
| `scripts/demo_embed_cluster.py` | A small runnable demo of embedding, clustering, novelty and look-alikes (laptop, Kaggle or Colab) |
| `sop-agent-construction-v2.md` | The owner's SOP for building on evidence; it governs how this repo is built |
| `Access-architecture-and-reusable-adapters.md` | Catalogue of horizon-scanning sources, protocol adapters and the provenance model |
