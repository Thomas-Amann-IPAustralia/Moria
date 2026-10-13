# Handover: the machinery sprint after day 3

For the next Claude Code session. Read `CLAUDE.md` first, then this note and D-021 in `docs/decisions.md`. Day 3
(design §13) is built and run; build day 4 when the owner asks. Nothing in the machinery spends money.
`docs/handover-day2.md` is superseded by this note and kept as the record of day 2 and the source widening.

**Status (2026-10-13):** day 3 built on branch `ccr-ca15595c-exzu0h` (D-021) and run into the bucket from clean
commits; `reports/evidence-layer.md` profiles every stage's latest run (aggregates only).

## What day 3 built
- **`moria normalise`** (`src/moria/normalise.py`): every passed raw bundle (checked against its run manifest's
  SHA-256) and the latest release of each bulk source into `lake/documents/`, `lake/series/` and
  `lake/observations/`, one file per source (`source=<id>`). Dates from every source format (`moria.text`), first
  sight across runs, `observable_basis` (source, first sight, or clamped when a source's date is after first sight),
  vintages (snapshot sources: a run whose values match the last vintage adds nothing; append sources: GDELT's daily
  volumes). Sources whose inputs are unchanged are carried over. Runs after every daily collection.
- **The sweep** (`src/moria/sweep.py`), inside normalise: hidden characters removed; AI-directed instructions,
  secrets and active content graded; personal data counted. High severity quarantines an item
  (`lake/quarantine/`, ids and codes only). The allowlist (`config/sweep.yaml`) is the owner's alone.
- **`moria features embed|dedup|keyphrases|index`** (`src/moria/features.py`, `src/moria/embed.py`): bge-small's own
  ONNX export at a pinned revision, every file hash-checked, 256 tokens; de-duplication groups (news URL, news
  title, cosine >= 0.95 between outlets within 30 days); keyphrases (1–3-grams, top 8 a document) and a vocabulary
  with each phrase's first observable date, sources and families (the new-term detector's input); the BM25 index.
- **`moria tag`** (`src/moria/tags.py`): zero-shot ring, domain, PESTLE origin, rights (`config/codebook.yaml`,
  proposed), territory similarity (with the owner's private context when it is in the bucket), nearest known trend,
  and the 47 territory and theme query groups matched in every source's text (`term_groups`, `term_territories`).
- **`moria ipr metrics`** (`src/moria/iprmetrics.py`): monthly IP RAPID series in `lake/ipr_metrics/` (same shapes
  as `lake/series` and `lake/observations`).
- **`moria search`**, **`moria evidence-report`**, **`moria prepare`** (the chain), the weekly `prepare` workflow,
  and `scripts/t4_jevstyle_speed.py` (the decision model on a free T4, for the owner).

## What day 4 reads
- Documents: `lake/documents/source=*/documents.parquet`; count one item per `dedup_group`
  (`features/dedup/groups.parquet`); filter by `observable_at` (point in time) and `first_seen_at`.
- Counts: `lake/observations/` and `lake/ipr_metrics/` with `lake/series/`; the value at `as_of` is the latest
  `vintage_at <= as_of` for each series and period. Drop `status = 'incomplete'` (the release month of IP RAPID).
- Tags: `features/tags/source=*/tags.parquet` (one tagger version per window: `tagger`).
- New terms: `features/keyphrases/vocabulary.parquet` (`first_observable_at`, `families`, `n_sources`).
- Every stage's latest manifest must have passed; `moria.tables.upstream` and `fetch_outputs` check that.

## Open items
1. **Day 4** (design §8.2, §8.3): rates per source volume, trends, accelerations and change points over the whole
   taxonomies, world/AU divergence, anomalies, the five weak-signal indicators, cross-ring convergence, artefact
   checks with seeded artefacts.
2. **Flags for day 4's detectors** (D-021):
   - the legal corpus is 85% of the documents: shares and quotas must be per source or per family;
   - IP RAPID's last 30 months of patents are composition-lagged (national-phase entries arrive later), so the AU
     and self-filed shares jump in 2025–26;
   - the CPC counts' AU series still needs its coverage check against IP RAPID (D-019);
   - GDELT's first GKG day (2026-10-11) has one measure, not three; the about/names-only series start 2026-10-12;
   - ABS spreadsheet tables are one period each (as published) until more releases arrive;
   - the zero-shot ring tag is weak on legal text and short titles (the legal corpus is 57% core, WIPO's treaty
     notifications 56%): until the owner's labels, use the cards' rings and `term_groups` (core-ring terms and the
     `ip_system` theme) for the core ring;
   - the nearest known trend per item sits in a narrow similarity band (medians 0.54 to 0.58): a weak tag, meant
     for signals, not items.
3. **Scale**: dedup's cosine pass compares items within 30-day windows; a year of GDELT (about 1.2M titles) will need
   an approximate-neighbour index or per-day blocking. The BM25 index is 0.5 GB; dossiers can download it.
4. **The owner's labels** (about 200, docs/mining-explained.md): after the codebook is confirmed; the least-sure
   sample comes from `ring_margin`.
5. Still open from day 2: `collect-daily` retrying a failed source once; the daily schedule's first runs.

## For the owner
1. **The T4 speed test**: run `scripts/t4_jevstyle_speed.py` in a free Kaggle or Colab T4 notebook (one cell; the
   docstring has it) and paste its one JSON line back. The rule is fixed: per-item tags if the median item takes
   <= 0.15 s, else signals only.
2. **The codebook** (`config/codebook.yaml`, proposed): confirm or edit the descriptions and examples of the ring,
   domain, PESTLE and rights labels.
3. Still open: D-020's proposed trends KT20 to KT24; the wishlist; the merge of this branch (or a pull request).

## Conventions to keep
- Commit the code, run, then record; don't edit the working tree while a run is going (its manifests record the
  tree's dirty flag when each stage starts).
- `moria search` prints titles: the analyst's own terminal only, never a scheduled job (public logs).
- Reports in the repo are aggregates only: no titles, text, URLs or keyphrases.
- Write invisible and bidirectional characters as escapes built from code points: the hygiene test refuses them
  literally, and some tooling turns a typed escape into the character.
- Next free decision number: D-022.
