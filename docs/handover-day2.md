# Handover: the machinery sprint after day 2

For the next Claude Code session. Read `CLAUDE.md` first, then this note and D-011 to D-013 in `docs/decisions.md`.
Build day 3 when the owner asks. Nothing in the machinery spends money.

**Status (2026-10-12):** day 2 is done (D-011 to D-013), on branch `claude/nice-lovelace-eroum3`. Day 1's handover
(`docs/handover-day1.md`) is superseded by this note.

## Where things stand
- **Daily, eleven sources** (`collect-daily`): GDELT news (GKG bulk files), the Federal Register of Legislation, IP
  Australia's site, WIPO, and peer IP offices: UKIPO, EPO news and Boards of Appeal, IPONZ, CIPO, USPTO and IPOS.
  EPO, CIPO and IPOS keep titles, links and dates only, because their terms don't clearly allow storing text.
- **Weekly, three sources** (`collect-weekly`, Mondays 03:41 UTC once merged):
  - `openalex_counts`: works by primary topic at four taxonomy levels, each year from 2010 and each of the last 36
    months, worldwide and Australian; research output types only. About 2,400 of the 10,000 free daily credits.
  - `abs_headline`: eleven SDMX queries, 839 series.
  - `ip_rapid`: the 2026-10-12 release is the first base in the bucket (`lake/ip_rapid/base=2026-10-12/`, 1.00 GB,
    92.7M rows). The next release becomes a delta against it.
- **Once:** `foresight_syntheses` (three of eight documents read), `peer_office_strategies` (UKIPO, EPO and USPTO;
  the EPO and USPTO pages are short landing pages, their full plans are separate files) and
  `config/baseline.yaml` (19 known trends, a draft for the owner, D-013).
- **Built, not running:** `patent_cpc_counts` on BigQuery, a dry run by default. It waits on the owner's GCP project
  (`docs/setup.md`).
- **The terms check** (D-012): two runs over 13 sampled days; see open item 6.
- **The bucket:** 1.00 GB of the free 10 GB.
- **Reusable pieces:**
  - `moria.collectors.abs.parse_sdmx_csv` (SDMX-CSV with labels into series);
  - `moria.collectors.openalex.periods` and the budget guard (`/rate-limit`, reserve, prepaid refusal);
  - `moria.ipr` (`convert_table`, `column_sql` with the privacy transform, `write_delta`, `SCHEMA`);
  - `moria.collectors.documents.pdf_pages` (capped PDF text);
  - `moria.collectors.gkg`: `web_documents`, `searchable_texts`, `phrase_hits`, `phrase_variants`;
  - `moria.census.census_markdown`; `Store.put_file` / `get_file`; `PoliteClient.download` and `post`.

## Open items
1. **Day 3:** normalise into the lake (dates in several source formats, sitemap `lastmod` included; ABS series into
   observations with vintages; OpenAlex groups into long form; GKG `about_documents` as the primary news series),
   de-duplicate, embeddings, BM25, tags. `moria ipr metrics` (demand, timeliness, outcomes) belongs with it.
2. **BigQuery:** the dry run once the owner has a project; then the owner decides on switching it on (D-011).
3. **Five foresight documents** refused from the build session. Try `collect-source` with `foresight_syntheses` from
   a runner; otherwise the owner downloads them. Then extend the baseline (D-013). The OECD publication is still to
   be chosen.
4. **ABS gaps:** business entries and exits (CABEE) and business R&D (BERD) are spreadsheets; an xlsx adapter would
   cover them.
5. **Peer offices not covered:** EUIPO and JPO (HTTP 403 to the build session; try from a runner), KIPO (no feed).
6. **The terms** (D-012): 92 of 207 terms never match in 13 sampled days, in either spelling (49 of the 65 core
   terms); names-only matches are often incidental, so day 4's detectors use `about_documents`. Once merged, run
   `terms-check` on Actions to check themes v2's 24 new phrases. The recommendations wait on the owner: keep the
   silent terms, add a broad IP-system theme, and rephrase core terms the way news writes them.
7. **`collect-daily` retrying failed sources once** at the end of the run (suggested in D-010; still open).
8. **The daily schedule** didn't fire at 02:23 UTC on 2026-10-12 (D-011). Check that runs appear; if not, a
   one-line change to `collect-daily.yml` in a pull request should register it again.

## For the owner
1. Merge this branch, or ask for a pull request.
2. BigQuery: a sandbox project and a key (`docs/setup.md`), then `collect-source` with `patent_cpc_counts`.
3. Confirm, edit or cut the 19 known trends (`config/baseline.yaml`, D-013).
4. The terms check's recommendations (D-012).
5. Paste your territory context again, for the bucket (it was in day 1's container only).

## Conventions to keep
- Commit the code, run, then record. Never commit data or the territory context.
- Read a source's terms before storing its text; when unclear, store titles and links only.
- Logs print counts and keys, never content. Reports in the repo are aggregates only; hit samples stay in the bucket.
- The OpenAlex key's daily budget is shared by every run that day: the weekly run estimates about 2,900 credits
  (it used 2,424) and won't start unless 1,000 would be left after it.
- Next free decision number: D-014.
