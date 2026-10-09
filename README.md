# Moria

A signal-detection and validation engine for IP Australia's strategic foresight. It mines public data for trends and
weak signals, has analysts validate them, and reads the validated signals through PESTLE, SWOT/TOWS and a Futures
Cone, each finding traceable to its evidence. Storage is Cloudflare R2; compute is the Google
Compute Engine free tier; mining uses scikit-learn; typed judgements use Jev; a generative model does the writing.

**Status: design v0.2 proposed, nothing built yet.** Read [`docs/design.md`](docs/design.md) (§0.1 lists what
changed from v0.1); the decisions behind it are D-001 and D-002 in [`docs/decisions.md`](docs/decisions.md).

| Path | What it is |
|---|---|
| `docs/design.md` | The system design (v0.2) |
| `docs/decisions.md` | The decision log (append-only) |
| `scripts/memprobe.py` | Peak-memory probe of the planned workloads; re-run it on the e2-micro in Phase 0 |
| `sop-agent-construction-v2.md` | The owner's SOP for building on evidence; it governs how this repo is built |
| `Access-architecture-and-reusable-adapters.md` | Catalogue of horizon-scanning sources, protocol adapters and the provenance model |
