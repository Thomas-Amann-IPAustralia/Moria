# Handover: the machinery sprint after day 4

For the next Claude Code session. Read `CLAUDE.md` first, then this note and D-022 in `docs/decisions.md`. Day 4
(design §13) is built and run; build day 5 when the owner asks. Nothing in the machinery spends money.
`docs/handover-day3.md` is superseded by this note and kept as the record of day 3.

**Status (2026-10-14):** day 4 built on branch `claude/awesome-wright-eu9uos` (D-022) and run into the bucket from
clean commits: 2,486 candidates at as_of 2026-10-14, 2,129 with no artefact flag; the seeded artefacts all caught
(`reports/scan.md`, `reports/eval/artefacts.md`).

## Since day 4: the SignalBoost detectors (D-025)
The owner's proposal (`docs/SignalBoost-Proposal.md`) was built before day 5 on branch `claude/charming-sagan-quk1nw`:
horizons (3 to 180 months), contextual anomalies and coupling, fading pairs, applicant countries by class (IP
RAPID's new `country_classes.parquet`), redundancy groups and corroboration, and `moria eval detectors`. Every new
detector is measured at each scan; **all seven are switched off** (`config/detect.yaml` `new_detectors`) until the
owner answers D-025. The evaluation (`reports/eval/detectors.md`) passes fading pairs and jurisdictions by class;
the others fail its rules (the contextual model adds precision, not recall).

What day 5 gains: `candidates.parquet` has `corroboration`, `redundancy_group` and `redundancy_size` (count a
redundancy group once in the quotas and in "breadth"); `measures/series/as_of=D/` has `horizons.parquet` (the
horizon profile of a series), `context.parquet` (each covariate's contribution; `explained` marks a band anomaly
its context predicts: an alternative explanation for the dossier) and `redundancy.parquet`. Flags for day 5:
- Day 4's band anomaly is weak evidence: it catches 53% of doubled spikes, flags 2.5 to 3.8% of null series, and
  7.8% of its onsets are confirmed by a trend a year later. Rank band anomalies low unless something else agrees.
- The layer was prepared and scanned at 2026-10-15 from the build session (D-026): 2,567 candidates, 2,129 clean;
  977 of them sit behind another candidate in a redundancy group. The BM25 index is stale (DuckDB's `fts` extension
  host was refused); the weekly `prepare` rebuilds it. `prepare.yml` did not parse on main from day 4 until this
  branch (fixed).
- Next free decision number: D-027.

## What day 4 built
- **`moria measure series --as-of D`** (`src/moria/measures.py`, `src/moria/stats.py`): trends (Theil–Sen, Mann–
  Kendall, Holm within families, three windows), accelerations (bootstrap; a steeper change point on a trend), change
  points (optimal partitioning, 3 times BIC), anomalies (99% family-wise band and a 25% floor; recent level changes in
  sub-annual series), low-base surges (exact Poisson test of rates), and AU/world divergence, over every count and
  statistical series, counts as rates per source volume. `measures/series/as_of=D/`.
- **`moria measure documents --as-of D`** (`src/moria/concepts.py`): the five weak-signal indicators over a 91-day
  window and a 730-day baseline, with clusters fitted at D; item rings; IP RAPID class pairs.
  `measures/documents/as_of=D/` (the `evidence` table lists the window items behind each concept that fired).
- **`moria monitor ingestion`**, **`moria detect`**, **`moria artefacts`** (six checks), **`moria scan`** (the
  chain), **`moria scan-report`**, **`moria candidates`** (terminal only), **`moria eval artefacts`** (seeded
  artefacts with controls on a copy of the layer). `moria ipr metrics` now writes class series and class pairs.
- `config/detect.yaml` holds every window, test and threshold. The weekly `prepare` workflow runs the scan and the
  seeded check after preparing; a missed seed fails the job.

## What day 5 reads
- `candidates/as_of=D/candidates.parquet`: one row per subject; `type`, `detectors`, `numbers` (JSON), `strength`
  (the primary detector's effect: yearly growth for trends and accelerations, the change for anomalies, the log rate
  ratio for surges; not comparable across types), `direction`, `sources`, `families`, `rings`, `views`, the window.
  `candidate_id` comes from the subject alone, so the register can follow a subject across scans.
- `candidates/as_of=D/evidence.parquet`: series (subject, denominator, reference) or window items (with dedup
  groups, families, rings, observable dates): the dossiers' "original evidence".
- `candidates/as_of=D/artefacts.parquet`: each check's outcome and its numbers (`details`, JSON); `clean`.
- `measures/series/as_of=D/measures.parquet` for the detectors' numbers and windows; `measures/documents/as_of=D/`
  for volumes, concepts, clusters (`assignments`) and novelty.
- The BM25 index (day 3) for counter-evidence and analogues.

## Flags for day 5
1. **Weak signals from documents are all flagged today** (onboarding and coverage): the feeds started in October
   2026 have no baseline. The ranking should show flags, not drop flagged candidates (design §8.3); a shorter
   baseline for a weekly early-warning scan is a measured choice for later.
2. **The candidate list is large** (2,486): ranking within the ring quotas (§2.5) and the third-order cap cut it to
   the review queue of about 40. Strengths differ by type; rank within type or normalise first.
3. **Series surges can't be checked for 2 sources:** an OpenAlex surge of 5 works may be one book or one journal
   issue. The dossier should show sample works (OpenAlex's API, by topic and period).
4. **Hindsight:** the keyphrase vocabulary was fitted on all evidence; the term-only hindsight run needs a refit at
   each past date (design §11.3).
5. **IP RAPID:** trade mark registrations are counted from registration dates since D-022 (the `granted` event
   stopped in March 2026); design series lag 2 months. The rise in provisional patent applications (from about 220–440
   a month in 2023–24 to 760–1,270 in early 2026) explains the jump in Australian and self-filed shares; D-021's
   composition-lag reading is corrected in D-022.
6. GDELT's daily series become testable after about 35 days of collection; until then, news enters only as items.
7. Rings: a series carries its card's rings (OpenAlex: adjacent and wider world together); the quotas need a ring per
   candidate. For OpenAlex, a field-to-ring map (or the subject's zero-shot ring) is a day-5 choice.

## For the owner
1. **IP RAPID's trade mark registrations:** the `granted` event has all but stopped being recorded since March 2026.
   If you know of a change in IP Australia's systems then, say so.
2. Day 5 when you ask: dossiers, pathway suggestions by Jev-Style 0.8B, ranking and quotas, the register export and
   import, the early-warning digest, a term-only hindsight smoke run.
3. Still open: the T4 speed test and the codebook (D-021); KT20 to KT24 (D-020); the wishlist; the merge of this
   branch (or a pull request).

## Conventions to keep
- Commit the code, run, then record; don't edit the working tree while a run is going (manifests record the dirty
  flag at each stage's start).
- `moria candidates` and `moria search` print labels and titles: the analyst's own terminal only, never a scheduled
  job (public logs). Repo reports are aggregates only.
- Write invisible and bidirectional characters as escapes built from code points (the hygiene test refuses them).
- Next free decision number: D-023.
