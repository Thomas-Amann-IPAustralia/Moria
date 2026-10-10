# Handover: the machinery sprint after day 1

For the next Claude Code session. Read `CLAUDE.md` first, then this note and D-006 to D-007 in `docs/decisions.md`.
Build day 2 when the owner asks. Nothing in the machinery spends money.

**Status (2026-10-10):** day 1 is done (D-007), on branch `claude/confident-curie-o51eog`.

## Where things stand
- **Five daily collectors run against real data into a local store:** `legislation_frl` (16 records for 2026-10-09),
  `wipo_press`, `ukipo_news` and `ipaustralia_site`. `gdelt_news` got HTTP 429 from the Claude Code session's shared
  network exit. Expect it to work from Actions runners; this is unverified.
- **Reusable pieces:**
  - `moria.store` (`LocalStore`, `R2Store`, `open_store`);
  - `moria.records` (`make_envelope`, `encode_bundle`, `decode_bundle`, `bundle_key`);
  - `moria.manifest.Manifest`;
  - `moria.http.PoliteClient` (per-host intervals, retries, robots.txt);
  - `moria.collectors.run_collection` (bundle, monitor and manifest for any collector);
  - the adapters `gdelt`, `feed`, `sitemap` and `legislation`.
- **Adding a source:** a new card in `config/sources/` (and a new adapter only if no existing one fits). Add a fixture
  test with a hand-built replica, then run `moria collect <id> --store local` on real data.

## Open items
1. **Day 2:**
   - IP RAPID (bulk: unzip one table at a time, hash individuals' names at ingest);
   - ABS headline series (SDMX);
   - BigQuery CPC counts (dry run, then capped; needs a GCP project);
   - OpenAlex whole-taxonomy counts (needs `OPENALEX_API_KEY`);
   - the foresight syntheses and the known-trends baseline draft (CSIRO's site resets connections from the session, so
     the owner may need to download its PDF);
   - peer-office feeds;
   - `moria terms check`, run from Actions.
2. **The first full snapshot of the IP Australia site** (850 pages): a one-off run with a higher page cap.
3. **Confirm the licences** marked "to confirm" in the source cards: FRL, IP Australia, WIPO.
4. **The FRL `registeredAt` timezone** is unconfirmed. Windows are contiguous, so nothing is lost.
5. **The private territory context** is in `config/territories.context.yaml` in this container only (git-ignored).
   Upload it to `interpretation/territories/context.yaml` in the bucket once the R2 token exists. The owner has the
   original text.

## For the owner
1. Add the four secrets to GitHub Actions and the Claude Code environment (`docs/setup.md`).
2. Merge this branch to `main`, or ask for a pull request. Scheduled workflows run only from the default branch.
3. Then run `collect-daily` once from the Actions tab, to confirm R2 writes and GDELT from a runner.

## Conventions to keep
- Commit the code, run, then record.
- Never commit data or the territory context.
- Logs print counts and keys, never content.
- Next free decision number: D-008.
