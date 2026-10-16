# Handover: the machinery sprint after day 5

For the next Claude Code session. Read `CLAUDE.md` first, then this note and D-029 in `docs/decisions.md`. Days 1 to 5
of the machinery sprint (design §13) are built and run; days 6 and 7 are the buffer (fixes, `docs/methodology.md`,
handover). Nothing in the machinery spends money. `docs/handover-day4.md` is superseded by this note and kept as the
record of day 4.

**Status (2026-10-16):** day 5 built on branch `claude/pensive-gauss-erbzsg` (D-029) and run into the bucket from
clean commits at the scan of 2026-10-15: 2,634 candidates ranked; a shortlist of 100 with dossiers and
the decision model's suggestions; **a queue of 40 ready for review** (14 core, 14 adjacent, 12 wider world; 20 per
view; 3 flagged); 120 register events; the reviewer's spreadsheet and the early-warning digest in the bucket
(`reports/queue.md`). The suggestions failed their check (`reports/eval/pathways.md`) and are recorded, not ranked.
The term-only hindsight smoke run raised all three proposed developments, with a median lead of 2 months
(`reports/eval/hindsight.md`). Next free decision number: D-030.

## What day 5 built
- **`moria rank --as-of D`** (`src/moria/rank.py`): every candidate scored for the early-warning and strategic views.
  One ring per candidate (handover-day4 flag 7): a one-ring card; a label matching the IP-system terms (core); a
  statistics query's ring, a GDELT group's ring, an OpenAlex field's ring (`config/review.yaml` `rank.rings`); else
  the label's zero-shot ring among the card's rings (OpenAlex topics carry no field). Components as percentiles:
  strength within type and subject kind (flag 2), breadth (independent lines of evidence, families, agreeing
  detectors), lead time and novelty by detector, novelty lowered near a known trend (cosine >= 0.68, read on the
  labels). Factors: type (band anomalies 0.5, D-025), flags (shown, never hidden), scope (a machine proxy for
  Australian relevance), and 'explained by its context' (1.0: shown, not ranked, D-028). A shortlist of 100 under
  the ring quotas, a 25% source cap and one per redundancy group (flag 2: counted once).
- **`moria dossier`** (`src/moria/dossier.py`): design §8.4 for each shortlisted candidate, JSON and Markdown in
  `interpretation/dossiers/<id>/<as_of>.*`; OpenAlex sample works by venue for surges and anomalies (flag 3) and IP
  RAPID applications for class pairs (organisations named, individuals never), with two checks they made possible:
  `concentrated_works` and `reclassified`.
- **`moria pathways`** and **`moria eval pathways`** (`src/moria/pathways.py`): the free decision model (read, pinned,
  hash-checked; the scorer built from the pinned commits with `--build-scorer`), eleven questions, a defanged state,
  responses cached in the bucket. **Recorded and shown, not ranked** (`pathways.use_in_ranking: false`) until the
  evaluation passes and the owner switches it on (D-029).
- **`moria queue`** (`src/moria/queue.py`): the queue of 40 from the shortlist, the views alternating, the quotas, the
  source cap, the third-order cap (orders a person confirmed), the redundancy rule; the sensitivity of the queue to
  each weight (`sensitivity.parquet`).
- **`moria register sync|export|import`** (`src/moria/register.py`): append-only events (`interpretation/register/
  events/<run>.parquet`), the state as a view; the reviewer's spreadsheet (`interpretation/register/exports/
  <run>.xlsx`); a validated import (all or nothing; the file kept in `inbox/register/`).
- **`moria digest`** (`src/moria/digest.py`), **`moria queue-report`** (`reports/queue.md`, aggregates only),
  **`moria review`** (the chain), **`moria show`** (a dossier, terminal only).
- **`moria eval hindsight`** (`src/moria/hindsight.py`): the term-only smoke run; `config/hindsight.yaml` is proposed.
- The weekly `prepare` workflow runs the review after the scan, with the decision model and its scorer cached.

## What the next steps read
- `review/as_of=D/{ranked,queue,sensitivity}.parquet`, `interpretation/dossiers/`, `interpretation/pathways/`,
  `interpretation/register/`, `interpretation/digests/`.
- The register's state (`moria.register.state(events(store))`): status, the reviewer's latest review, the machine's
  latest suggestions, the history. The lenses (after the sprint) read validated signals only (design §10).

## Flags for the next session
1. **Nothing in the ranking weighs relevance to the IP system yet.** The decision model doesn't discriminate on
   states that keep SOP §22's markers (separation 0.007 against a rule of 0.05; P2 is 0.50 for every dossier;
   horizon and stance never vary, and flip between runs: near ties in batched mode). A zero-shot baseline (the
   tagger's encoder against the six statements) passes the anchors but ranks the IP RAPID class pairs lowest
   (their labels are codes). So the queue holds some OpenAlex topics with no evident pathway; triage parks them.
   The fix is the owner's labels from the first round (design §11.2), or a stronger model (D-029's options).
2. **The flag penalties decide most of the queue's edge:** without them 12 of the 40 places change (strength
   weights: 5 to 6; the rest: 0 to 3). Review them first after the round.
3. **OpenAlex surges are often one venue:** 8 of 16 sampled were concentrated (the 'Byzantine studies' surge is
   ebook chapters). A rule that lowers a surge whose works are concentrated is a candidate for day 6, measured.
4. **IP RAPID pairs can be reclassification:** the dossier's `reclassified` check found one in the shortlist (old
   applications classified in the window). The class-pair detector itself counts by the classes' observable month
   (D-022), as it should; the check is the alternative explanation.
5. **Hindsight is a smoke run:** the set is proposed, the matches loose (any matching series or class pair with a
   detector of change), the mainstream months approximate; no non-events, so false alarms aren't counted. The
   owner's set comes first; the run takes about 110 s a date.
6. **Weekly runner:** `moria review` in `prepare.yml` builds llama.cpp and the scorer the first time (a few
   minutes; then cached by `config/review.yaml`'s hash, so a config edit rebuilds it), fetches the decision model
   (529 MB) once, and spends about 10 minutes deciding on 4 vCPUs. Not yet run on a runner.
7. Rings: OpenAlex topics take the zero-shot ring (691 candidates); a topic-to-field map needs OpenAlex's topic list
   (a free one-off fetch) if the owner wants it deterministic.

## For the owner
1. **The first review round:** the spreadsheet is at
   `interpretation/register/exports/20261016T014959Z-8741e464.xlsx` in the bucket, or run `uv run moria register
   export --as-of 2026-10-15 --out review.xlsx --store r2`; fill the yellow columns (the rules are on its first
   sheet); `uv run moria register import review.xlsx --store r2`. `uv run moria show <id> --as-of 2026-10-15 --store
   r2` prints a dossier.
2. **The decision model:** leave its suggestions unranked (Claude's recommendation), or choose the T4 test and a
   larger free model, Matilda-Jev (M1, paid), or calibration on your labels (D-029).
3. **The hindsight set:** choose developments blind to Moria's output, with non-events and pass rules (§2.6).
4. **The ranking's settings** after the round: quotas, weights, flag penalties, the scope factor, the ring maps,
   the known-trend threshold.
5. Still open: the T4 test and the codebook (D-021); KT20 to KT24 (D-020); the wishlist; the merge of this branch
   (or a pull request).

## Conventions to keep
- Commit the code, run, then record; don't edit the working tree while a run is going.
- `moria candidates`, `moria search` and `moria show` print labels and titles: the analyst's own terminal only. The
  digest, the dossiers, the register and its spreadsheets hold labels: the private bucket only. Repo reports are
  aggregates only.
- Write invisible and bidirectional characters as escapes built from code points (the hygiene test refuses them):
  this session's tooling turned a typed escape into a literal character again (fixed before commit).
- Stubs and scripted models stay in tests (`tests/test_review.py`'s `ScriptedBackend`); a test checks the CLI never
  reaches them.
- Next free decision number: D-030.
