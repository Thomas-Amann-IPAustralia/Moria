# Handover: the machinery sprint after day 2

For the next Claude Code session. Read `CLAUDE.md` first, then this note, D-011 to D-020 in `docs/decisions.md`,
and `docs/sources-backlog.md`. The Tier 1 cleanup (D-018) and the widening of sources (D-020) are built; build day 3
when the owner asks. Nothing in the machinery spends money.

**Status (2026-10-13):** day 2 is done (D-011 to D-013), the owner's answers are in (D-014, D-015, D-017), and the
Tier 1 cleanup is built (D-018, branch `claude/youthful-hypatia-27egln`). Day 1's handover
(`docs/handover-day1.md`) is superseded by this note.

## The widening of sources (D-020, branch `claude/keen-dijkstra-od5g3s`)
- **The OECD** (the owner's request): `oecd_publications` and `oecd_data_releases` (daily feeds with abstracts and
  categories), `oecd_ai_blog` (daily, titles), `oecd_ai_haip_reports` (weekly, the new `json_list` adapter),
  `oecd_headline` (weekly, the new `oecd_sdmx` adapter: 13 queries, at most 18 a run) and `stip_compass` (weekly
  check, the new `delimited_csv` bulk stage: the whole STIP Compass database in the lake).
- **A breadth pack** (the owner's choice): eight daily feeds, `un_news`, `conversation_au`, `lowy_interpreter`,
  `ec_presscorner`, `aspi_strategist`, `arxiv_ai_society`, `standards_australia_news`, `us_federal_register_ip`.
  Many gov.au sites, the WTO, the ACCC and the IEA could not be used (D-020 lists why).
- **The owner's uploads:** read through `upload` names in the document cards; Word files are read. Text stored for
  the Science and Research Priorities, the Net Zero Plan, the Patents Accessibility Review and CIPO's strategy; the
  Defence and AIC documents reserve their rights; the JPO report states no licence; the KIPO report has no text.
- **The baseline:** KT20 to KT24 and twelve citations are `proposed`, waiting on the owner (`moria baseline`).
- **Sources:** 43 (core 33, adjacent 29, wider world 15; a source can sit in several rings).

## The Tier 1 cleanup (D-018)
- **Daily, six more sources:** APH's five committee feeds (summaries kept, D-017) and `moip_news` (Korea's Ministry
  of Intellectual Property, formerly KIPO; titles only).
- **Weekly, two more:** `abs_datacubes` (CABEE and BERD spreadsheets, the new `xlsx` adapter) and
  `wipo_treaty_notifications` (26 treaties' notification lists in WIPO Lex, the new `listpage` adapter).
- **Bulk, in the lake:** `oalc` (the Open Australian Legal Corpus 7.1.0: Commonwealth legislation and the Federal
  and High Courts, the new `hf_corpus` stage) and `wipo_ipstats` (WIPO's bulk indicators to 2022, the new `zip_csv`
  stage). Both skip a release already ingested.
- **Once:** `ipaustralia_publications` (six PDFs) and the full IP Australia snapshot (`ipaustralia_site --backfill`).
- **Tools:** `moria discover` (a source's addresses from wherever it runs, never text; `collect-source` runs it on a
  runner), `moria collect --backfill`, feed ids for guid-less feeds, first-sight dates for undated items.
- **Gaps** (403 or timeouts to the session and to a runner): EUIPO and JPO news, the Federal Court, the High Court and
  AustLII (with IP Australia's hearing decisions). A draft request for the owner is in `docs/sources-backlog.md`, T7.

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
- **Once:** `foresight_syntheses` (three of nine documents read), `peer_office_strategies` (UKIPO, EPO, USPTO and
  EUIPO; JPO and CIPO wait on uploads) and `config/baseline.yaml` (19 known trends, confirmed by the owner, D-014).
  Refused documents come as owner uploads in the bucket's `inbox/documents/` (`docs/wishlist.md`), with a licence
  check on every document. `territory_evidence` (D-015) holds the public documents the territory context cites:
  three read, four waiting on uploads.
- **Built, not running:** `patent_cpc_counts` on BigQuery, a dry run by default. It waits on the owner's GCP project
  (`docs/setup.md`).
- **The terms check** (D-012, D-014): three runs over the same 13 sampled days; see open item 6. The territory
  context is back in the bucket (`interpretation/territories/context.yaml`).
- **The bucket:** 1.00 GB of the free 10 GB.
- **Reusable pieces:**
  - `moria.collectors.abs.parse_sdmx_csv` (SDMX-CSV with labels into series);
  - `moria.collectors.openalex.periods` and the budget guard (`/rate-limit`, reserve, prepaid refusal);
  - `moria.ipr` (`convert_table`, `column_sql` with the privacy transform, `write_delta`, `SCHEMA`);
  - `moria.collectors.documents.pdf_pages` (capped PDF text);
  - `moria.collectors.gkg`: `web_documents`, `searchable_texts`, `phrase_hits`, `phrase_variants`;
  - `moria.census.census_markdown`; `Store.put_file` / `get_file`; `PoliteClient.download` and `post`.

## Open items
0. **After the merge:** `collect-daily` and `collect-weekly` pick up the new cards by cadence. Watch the first week:
   the House and joint APH feeds (empty so far, so their expected volumes are placeholders), `moip_news`'s pattern
   (a run warns if the page stops matching), and the APH hearings feed (undated: every item every day).
1. **Day 3:** normalise into the lake (dates in several source formats, sitemap `lastmod` included; ABS series into
   observations with vintages; OpenAlex groups into long form; GKG `about_documents` as the primary news series),
   de-duplicate, embeddings, BM25, tags. `moria ipr metrics` (demand, timeliness, outcomes) belongs with it.
2. **BigQuery:** switched on (D-019); the first live run is in the bucket (961 codes, 17.07 GB). Monthly, by hand
   with `collect-source`; the AU series needs a coverage check against IP RAPID first.
3. **The wishlist** (`docs/wishlist.md`, D-014, D-015): the owner uploads the refused documents; then run
   `foresight_syntheses`, `peer_office_strategies` and `territory_evidence` (from a runner or with `--store r2`), read the new documents, and
   add their trends to the baseline (the owner expects several). The OECD publication is the STI Outlook 2025.
4. **ABS gaps:** closed (D-018, `abs_datacubes`); day 3 pivots their tables into series.
5. **Peer offices not covered:** EUIPO and JPO refuse runners too (D-018); KIPO is `moip_news`.
6. **The terms** (D-012, D-014): the owner keeps the silent terms and revisits the search strategy once the machinery
   is built. With synonyms and the `ip_system` theme, 79 of 239 terms never match in 13 sampled days (38 of the 65
   core terms). Names-only matches are often incidental, so day 4's detectors use `about_documents`. The synonym
   "takedown request" was removed after the third run.
7. **`collect-daily` retrying failed sources once** at the end of the run (suggested in D-010; still open).
8. **The daily schedule** didn't fire at 02:23 UTC on 2026-10-12 (D-011). Check that runs appear; if not, a
   one-line change to `collect-daily.yml` in a pull request should register it again.

## For the owner
0. **D-020:** confirm or edit the five proposed trends (KT20 to KT24) and twelve proposed citations; object if D-017
   shouldn't cover CIPO's reproduction notice.
1. Merge this branch, or ask for a pull request.
2. The wishlist (`docs/wishlist.md`): uploads before day 3 (D-019), WEF's two top-10 lists, and the EPO's and
   Canada.ca's terms.
3. The gaps (D-018): you are looking for feeds; day 3 doesn't wait (D-019). A draft access request is in
   `docs/sources-backlog.md`, T7, if you want it later.

## Conventions to keep
- Commit the code, run, then record. Never commit data or the territory context.
- Read a source's terms before storing its text; when unclear, store titles and links only.
- Logs print counts and keys, never content. Reports in the repo are aggregates only; hit samples stay in the bucket.
- The OpenAlex key's daily budget is shared by every run that day: the weekly run estimates about 2,900 credits
  (it used 2,424) and won't start unless 1,000 would be left after it.
- `sdmx.oecd.org` allows as few as 20 data downloads an hour per address: run `oecd_headline` once an hour at most,
  and check structures with structure queries (`/dataflow/...`, `/availableconstraint/...`), which are not data
  downloads.
- Next free decision number: D-021.
