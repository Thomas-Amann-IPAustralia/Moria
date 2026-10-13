# Sources backlog: the Tier 1 cleanup before day 3, and what waits

*Started 2026-10-12; the cleanup was built on 2026-10-12 and 13 (D-018, §2), and sources were widened on 2026-10-13
(D-020, §2a). The owner's decisions are D-016, D-017 and D-020. Checks marked "today" were run from a Claude Code session's
cloud address with Moria's own user agent; a GitHub Actions runner may get different answers. Licence readings are
Claude's, not legal advice.*

## Decisions (D-016, 2026-10-12)

| Topic | The owner's words | What follows |
|---|---|---|
| **Scope** | "Lets not go for tier 2 stuff yet then. But I would like to clean up Tier 1 before we move to day 3 work." | §2 is the cleanup list, built before day 3. Tier 2 stays "not to build yet" (§5). |
| **Open Australian Legal Corpus** | "Something is better than nothing, I bet there's still plenty we can learn from mining bits of it as required." | Adopted as a once source, taken in parts (T2). |
| **Pile of Law** | "Please double check whether it might [have useful sources] and if not, we can discard." | Checked (§4). Nothing Moria can't get better from the upstream sources: **discarded**. |
| **Parliament** | "Lets go with the RSS feeds and we can add the other stuff from them to the backlog." | Five APH feeds join the cleanup (T1). ParlInfo, Hansard, the Library's pages, the other feeds and the statistics go to the backlog (§5). |

**The owner's answers (D-017, 2026-10-12):**
1. **NonCommercial:** "Moria's use would be considered non-commercial research purposes." This covers APH's
   CC BY-NC-ND 4.0, and the Federal and High Courts' "use within an organisation".
2. **APH summaries:** "Yes it can." The APH feeds keep their summaries (`keep_summary: true`).
3. **ParlInfo:** "We'll address that later. We do not need permission to access the RSS feeds though." L1 waits; T1
   goes ahead without asking APH.
4. **Day 3 and the items waiting on the owner (W1, W2):** deferred ("I'll defer judgement for now"). The
   recommendation stands: day 3 starts once T1 to T7 are done or are themselves waiting on an answer.

**Still a recommendation:** the default parts of the corpus (Commonwealth legislation, the Federal Court and the High
Court); the owner may widen them if a question needs more.

## 1. The steps every new source goes through

From `CLAUDE.md` and the day-1 handover ("Adding a source"). Each item below lists only what it needs beyond these.

1. **Terms.** Read before any text is stored. Set `keep_summary` (feeds) or `store_text` (sitemaps, documents) from
   them; titles, links and dates only while unclear.
2. **Access.** One honest request from a runner (`collect-source`), with Moria's user agent and robots.txt honoured.
   A block is reported as a gap, not worked around (D-011).
3. **Card.** `config/sources/<id>.yaml` with every design §5.1 field: rings, domains, family, cadence, publication
   lag, coverage, history start, breaks, known biases, revision policy, licence, snapshot rights, expected volume.
4. **Adapter.** Reuse one of the nine (`feed`, `sitemap`, `legislation`, `documents`, `gdelt_gkg`, `gdelt`,
   `openalex_counts`, `abs_sdmx`, `bigquery_cpc`, plus `moria ipr` for IP RAPID). A new one only if none fits. The
   `feed` adapter takes one URL per card.
5. **Host settings.** A minimum interval for each new host in `config/moria.yaml`.
6. **Keys.** Any API key goes into GitHub Actions secrets and the Claude Code environment, `docs/setup.md`, and
   `moria env-check` (presence only, never values).
7. **Tests.** Hand-built replicas of each format through `httpx.MockTransport`, with placeholder text. No network in
   CI.
8. **First runs.** From a clean commit: `--store local`, then `--store r2`; a manifest and a monitor entry; then
   `moria census <id>`.
9. **Schedule.** `collect-daily`, `collect-weekly`, or once by hand.
10. **Record.** A decision entry; the sources table in `CLAUDE.md`; the handover note.

## 2. The Tier 1 cleanup (before day 3)

Effort: **S** is a card on an existing adapter; **M** is a new small adapter; **L** is a new adapter plus lake
storage.

| # | Item | Status (D-018) | Adapter | Cards | Waits on |
|---|---|---|---|---|---|
| T1 | APH feeds: Senate new inquiries, reports, upcoming hearings; House and joint inquiries | **built**, backfilled into the bucket | `feed` | `aph_senate_new_inquiries`, `aph_senate_reports`, `aph_senate_hearings`, `aph_house_inquiries`, `aph_joint_inquiries` | nothing |
| T2 | Open Australian Legal Corpus: Commonwealth legislation, Federal Court, High Court | **built**, release 7.1.0 in the lake | new `hf_corpus` | `oalc` | nothing |
| T3 | IP Australia: the full first snapshot, and the PDFs its pages link | **built**: a backfill run, and six PDFs | `sitemap --backfill`, `documents` | `ipaustralia_site`, `ipaustralia_publications` | nothing |
| T4 | Peer offices: EUIPO and JPO news; KIPO | **KIPO built** (now MOIP); **EUIPO and JPO are gaps**: 403 to the session and to a runner | new `listpage` | `moip_news` | **you**, for EUIPO and JPO (below) |
| T5 | WIPO statistics and treaties | **built**: treaty notifications (WIPO Lex) and the bulk statistics files | `listpage`, new `zip_csv` | `wipo_treaty_notifications`, `wipo_ipstats` | nothing |
| T6 | ABS business entries and exits (CABEE), business R&D (BERD) | **built** | new `xlsx` | `abs_datacubes` | nothing |
| T7 | Courts after March 2025; IP Australia's hearing decisions | **gap**: the Federal Court and AustLII answer 403 to the session and to a runner; the High Court times out | — | — | the owner is looking for feeds; day 3 doesn't wait (D-019) |
| W1 | Wishlist documents (11, plus KIPO's optional report) and the EPO's and Canada.ca's terms | waiting on your uploads and answers | `documents` | — | **you** |
| W2 | `patent_cpc_counts` on BigQuery | **switched on** (D-019): the first live run gave 961 codes, 17.07 GB of the free 1 TiB a month | `bigquery_cpc` | `patent_cpc_counts` | nothing; monthly by hand |

**New tools from the cleanup (D-018):**
- `moria discover URL…` checks a new source's addresses (status, type, item counts and dates, feed links; never
  text). `collect-source` runs it from a runner with the source `discover`, so a site that refuses the build session
  can be tried from GitHub's addresses.
- `moria collect <source> --backfill` takes a first snapshot: a feed's every item, a sitemap's every page (up to
  `backfill_max_pages`), a list page's every item. `collect-source` takes a `backfill` input.

### T1. APH RSS feeds

**What answered today** (Moria's user agent, requests 2 s apart):

| URL | Result today |
|---|---|
| `www.aph.gov.au/Help/RSS_feeds` | 200 (the feed list) |
| `/senate/rss/new_inquiries` | 200, RSS, 34 items |
| `/senate/rss/reports` | 200, RSS, 134 items |
| `/senate/rss/upcoming_hearings` | 200, RSS, 30 items |
| `/house/rss/house_inquiries`, `/house/rss/joint_inquiries` | 200, RSS, empty today |
| `www.aph.gov.au/robots.txt` | 403, "Page Blocked by WAF" |

**Why they matter.**
- A new inquiry is the earliest public sign of Parliament turning to IP, AI, scams, trade or medicines.
- Reports show where an inquiry landed.
- Hearings include Estimates, where IP Australia appears with its portfolio.

**Licence.** The site says CC BY-NC-ND 4.0, except the Coat of Arms and where otherwise noted. My reading:
- **NonCommercial:** Moria's use is non-commercial research (the owner, D-017).
- **NoDerivatives:** Moria may make adaptations (extracted text, embeddings, summaries) for its own use, but may not
  share them. Shared outputs quote unaltered with attribution, or link. The public repo keeps counts only. The feeds'
  own summaries may be stored (the owner, D-017).

**To do.**
1. **Five cards:** `aph_senate_new_inquiries`, `aph_senate_reports`, `aph_senate_hearings`, `aph_house_inquiries`
   and `aph_joint_inquiries`. Each has core and adjacent rings, domains D1 and D6, family `policy`, and cadence daily.
2. **`keep_summary: true`** (the owner, D-017).
3. **Expected volume.** Watch the House feeds for a week before setting `expected_volume`; they were empty today.
4. **Host interval.** Add one for `www.aph.gov.au` in `config/moria.yaml`.
5. **robots.txt.** `www.aph.gov.au/robots.txt` itself answers 403, and Moria's client treats a 401/403 robots.txt as
   "no rules" (`src/moria/http.py:70`), as RFC 9309 permits. The `feed` adapter doesn't read robots.txt in any case.
   The owner: no permission is needed to read the RSS feeds (D-017).
6. **Run from a runner first.** The WAF may treat GitHub's addresses differently.

**Built (D-018).** The five cards, daily, with a 30-day lookback: items are dated by their referral or tabling and
may be added later. The feeds have no guids and repeat an inquiry's link for several items, so each item's id is
its link plus a hash of its title, date and summary (`item_id: link_and_content`). The hearings feed carries no
dates: every item is kept each run, observable from the run that first sees it. First runs (backfill, from this
session): 34 new inquiries, 134 reports, 30 hearings; the House and joint feeds were still empty. The feeds answered
from both the session and, through `env-check`, a runner.

### T2. Open Australian Legal Corpus (Isaacus)

**What it is.** Release 7.1.0: 232,560 documents in one file, `corpus.jsonl` (9.4 GB). Fields: `version_id`,
`type`, `jurisdiction`, `source`, `mime`, `date`, `citation`, `url`, `when_scraped`, `text`.

| Source in the corpus | Documents | Taken by default |
|---|---:|---|
| Federal Register of Legislation (in-force Acts and instruments) | 32,356 | yes |
| Federal Court of Australia (including the Copyright Tribunal and the Australian Competition Tribunal) | 63,749 | yes |
| High Court of Australia | 8,096 | yes |
| NSW Caselaw | 117,371 | no |
| NSW, Queensland, WA, SA and Tasmanian legislation (plus Queensland and SA bills) | 10,988 | no |

**Why it's worth having.** It fills the courts gap without AustLII. Federal Court and High Court IP judgments are
the case law that changes how rights are enforced (pathway P3). The back catalogue of Commonwealth law is a baseline
for `legislation_frl`, which collects only from day 1 forward.

**Limits.**
- **A snapshot, not a feed:** every source was last scraped on 10 March 2025.
- **Latest versions only:** it can't show how a law changed over time.
- **Not all of AustLII:** no IP Australia hearing decisions, no tribunals outside its list, and no Commonwealth
  bills.

**Licence.** The corpus as a collection is CC BY 4.0. Its documents keep their own terms (its `LICENCE.md`):
- **Legislation:** CC BY 4.0, with set attribution wording naming 10 March 2025.
- **Federal Court and High Court:** reproduction **in unaltered form**, for personal, non-commercial use **or use
  within an organisation**. The High Court's copyright notice must be kept.
- **NSW Caselaw:** among other conditions, use must be consistent with the current official version, comply with
  suppression orders, and exclude robots' indexing. That is one reason it is left out by default: a 2025 copy can't
  honour orders made since.

Moria's use is non-commercial research (the owner, D-017), so storing the text privately fits these terms.
Republishing it does not.

**To do.**
1. **A new adapter, `hf_corpus`:**
   - download the file pinned to a dataset **commit hash** (never `main`), by stream;
   - hash it, and record the SHA-256 and the commit in an immutable release manifest, as `moria ipr` does;
   - keep only the default sources during conversion.
2. **Lake, not raw bundles.** Typed zstd Parquet at `lake/oalc/release=7.1.0/<source>.parquet`. My estimate is about
   1 to 1.5 GB; Hugging Face's own Parquet export of the whole corpus is 2.3 GB. The bucket now holds 1.00 GB of its
   free 10 GB.
3. **Envelope dates (design §11.3).** `kind: document`, `family: legal`, and a per-document licence from `source`:
   - **judgments:** `event_at` and `observable_at` are the decision date;
   - **legislation:** `observable_at` is `when_scraped` (2025-03-10). The latest version's text wasn't public earlier,
     so a hindsight test must not see it before then.
4. **Privacy.** Judgments name parties and witnesses. Text stays in the bucket. Logs and the census report counts by
   source, type and year only.
5. **Card `oalc`.** Cadence once; re-run when a new release appears.
6. **"Mining bits as required" on day 3.** 1.4 billion tokens can't be embedded on free CPU within the sprint. Embed
   a slice instead: decisions citing the Patents, Trade Marks, Designs, Copyright or Plant Breeder's Rights Acts, the
   Copyright Tribunal's decisions, and titles for everything. Further slices are pulled by question later.

**Built (D-018).** The `hf_corpus` stage downloads `corpus.jsonl` at dataset commit `ef45e3fe` (2026-03-07), checks
it against its SHA-256 (the file's LFS object id), checks its ten fields, and lets DuckDB keep the three default
parts as Parquet with row groups capped at 64 MB (20,000-row groups ran out of memory at 3 GB). Each row has its
own licence, `event_at` (the document's date), `observable_at` (judgments: the decision date; legislation:
`when_scraped`, which runs from 2024-09-15 to 2025-03-10 within the legislation part, not one day), its text's
length and SHA-256, and an evidence id. Results are in D-018 and `reports/census/oalc.md`. The slice for embeddings
(step 6) is day 3's.

### T3. IP Australia
- **The full first snapshot** (about 850 pages): a one-off run with a higher page cap (handover-day1, item 2).
- **PDFs linked from pages** (the Corporate Plan and the Annual Report) aren't in the sitemap. Add them as
  `documents` entries; the Australian IP Report 2026 is already in `territory_evidence`.

**Built (D-018).** The snapshot is `moria collect ipaustralia_site --backfill` (every page in the sitemap, with or
without a lastmod, up to 2,000): 844 of 846 pages on 2026-10-13, in 29 minutes. `ipaustralia_publications` reads six PDFs from the accountability pages: the
Strategic Corporate Plan 2026-27, the Annual Report 2024-25, the AI transparency statement, the Minister's statement
of expectations, IP Australia's statement of intent and the cost recovery implementation statement. The licence
check found CC BY in two; the Minister's letter states no licence, so its text is not stored.

### T4. Peer offices not covered
- **EUIPO and JPO** answered 403 to the build session. Try from a runner; if they still refuse, they become gaps or
  owner uploads.
- **KIPO** has no feed, only an HTML list. It needs a small list-page adapter, or a sitemap if it has one.
- Each office's terms are read before any text is stored.

**Built and checked (D-018).** From a runner (`collect-source` with `discover`, 2026-10-12):
- **KIPO** answered. It is now Korea's Ministry of Intellectual Property (MOIP). Its robots.txt addresses only
  Googlebot. Its English news board has no feed, so the new `listpage` adapter reads the first page with a pattern
  (`moip_news`, daily). Its footer reads "All Rights Reserved", so titles, links and dates only.
- **EUIPO** (www.euipo.europa.eu, robots.txt included) and **JPO** (www.jpo.go.jp, robots.txt included) answered
  403 to the runner as to the build session. The EU's own press-release feed carries no EUIPO items. Both are gaps.
  Routes, for the owner: ask EUIPO and JPO (through IP Australia's contacts with the offices) whether Moria's user
  agent may read their news pages or feeds; until then, their annual reports can come as owner uploads.

### T5. WIPO statistics and treaties
The design's Tier 1 names "WIPO statistics, news and treaties", but only the press feed is carded. To do:
- choose the statistics route (WIPO's IP Statistics Data Center downloads: format and terms to check);
- choose the treaty route (membership and ratification notifications: a feed or a page to watch);
- a small CSV adapter for the statistics, and `feed` or `sitemap` for the treaty notices.

WIPO's online content is CC BY 4.0 (D-011); the statistics' terms are still to confirm.

**Built (D-018).** WIPO's robots.txt disallows its treaty notification pages (`/treaties/*/notifications/`), the
newsletter archive's data (`/o/`) and the IP Statistics Data Center (`www3.wipo.int` disallows everything but a
list). Two routes are allowed:
- **Treaties:** WIPO Lex lists each treaty's notifications as a dated table. `wipo_treaty_notifications` (weekly)
  reads 26 treaties' lists with the `listpage` adapter: 2,945 notifications from 1967 to 2026-09-28 on the first
  run. The Rome and Brussels Conventions have no list there (the UN Secretary-General is their depositary).
- **Statistics:** the bulk ZIPs on WIPO's statistics page (`wipo_ipstats`, the new `zip_csv` stage): patents by
  technology field, trade marks and designs by class, by office and origin, 2000-2022, 6.2 million rows in the lake.
  The files were last rebuilt in 2024, so they are a baseline, not a current series. WIPO's terms: no republishing
  or reselling of its datasets, and cite "WIPO Statistics Database"; Moria keeps them private.

### T6. ABS business entries and exits (CABEE) and business R&D (BERD)
These are spreadsheet releases a runner can fetch. They need a new `xlsx` adapter (a new dependency, such as
openpyxl), producing series as observations with vintages, as `abs_headline` does. ABS data are CC BY 4.0.

**Built (D-018).** `abs_datacubes` (weekly) finds the workbooks on each latest-release page (CABEE: one workbook of
16 tables, June 2026, released 2026-08-18; BERD: twelve workbooks of 21 tables, 2023-24, released 2025-08-22). Each
table is one observation record, kept as published: headings, sections, labelled rows, the ABS's symbols, notes. It
is dated by the release date printed in the workbook, and an unchanged table keeps its evidence id. Turning tables
into series is normalisation's job (day 3).

### T7. Courts and tribunals the corpus misses
- **Federal Court and High Court decisions after 10 March 2025.** Read the courts' own judgment lists, checking for
  feeds and robots.txt first. The corpus's author had each source's permission to scrape, and Moria should ask too
  if it scrapes rather than reads a feed. The corpus's creator code is open source
  (`isaacus-dev/open-australian-legal-corpus-creator`) and can be read for the formats.
- **IP Australia's hearing decisions** on patents, trade marks, designs and plant breeder's rights. As far as I
  know, they are published on AustLII, whose terms restrict automated bulk access. Ask AustLII, or IP Australia, for
  a public route.
- **The Administrative Review Tribunal**, if a question needs it.

**Checked (D-018): a gap until the owner asks.** From both the build session and a runner, with Moria's user agent:
`www.fedcourt.gov.au` and `www.judgments.fedcourt.gov.au` (robots.txt, the RSS page, the IP practice area) and
`www.austlii.edu.au` (robots.txt and the Patent and Trade Marks Office databases) answered 403;
`www.hcourt.gov.au` and `eresources.hcourt.gov.au` timed out or reset. IP Australia's own site lists no decisions.
Nothing is collected; the corpus covers the Federal and High Courts to 10 March 2025.

*A draft request, for the owner to send if they choose (to the Federal Court's web team, AustLII, and the High
Court):*

> IP Australia is building Moria, a non-commercial research tool for its strategic foresight. It reads public
> sources politely: it names itself in its user agent (`Moria/0.1 (+https://github.com/Thomas-Amann-IPAustralia/Moria;
> public-data horizon scanning)`), honours robots.txt, waits between requests and runs at most once a day from
> GitHub Actions. We would like to read your [judgments RSS feed / list of new decisions, including IP Australia's
> hearing decisions] once a day: titles, citations, dates and links, and the text of decisions about intellectual
> property for internal analysis, which we would not republish. Our requests from GitHub's addresses currently
> receive HTTP 403. Could Moria's user agent be allowed, or is there a route you prefer (a feed, a data export)?

### W1. Wishlist documents and two sites' terms (`docs/wishlist.md`)
- **Waiting on your uploads to `inbox/documents/`:**
  - `foresight_syntheses`: National Science and Research Priorities 2024, the Critical Technologies list, the Net
    Zero Plan, the 2026 National Defence Strategy, and the OECD STI Outlook 2025. For WEF, paste its two top-10 lists
    (names only).
  - `territory_evidence`: the AIC's Statistical Reports 38 and 55, the Patents Accessibility Review and the
    Government's response. The review is offered as Word: save it as PDF, or adopt the DOCX reader noted in L1.
  - `peer_office_strategies`: the JPO Status Report 2026 and CIPO's 2023–2028 strategy; KIPO's annual report is
    optional.
- **Terms to confirm:** the EPO (section 6) and Canada.ca. That lets Moria store text for `epo_news`,
  `epo_boards_of_appeal`, the EPO's plans, `cipo_news` and CIPO's strategy.
- **Then:** run the three cards from a runner, read the new documents, add their trends to `config/baseline.yaml`
  for your confirmation, and run the census.

### W2. `patent_cpc_counts`
1. Create a BigQuery sandbox with no billing account (`docs/setup.md`, about ten minutes).
2. Add `GCP_PROJECT_ID` and `GCP_SA_KEY` as secrets.
3. Run `collect-source` with `patent_cpc_counts` (a dry run). Claude reports the byte estimate.
4. You decide whether to switch `dry_run` off (D-011). Every real query is capped by `maximumBytesBilled`.

## 2a. The widening (D-020, 2026-10-13)

The owner asked for the OECD's sources (STIP Compass above all) and a stronger footing before day 3, and chose "OECD +
a breadth pack" when the session showed 25 of 29 sources in the core ring and 5 in the wider world.

| Group | Cards | Adapter | Text kept | Notes |
|---|---|---|---|---|
| OECD feeds | `oecd_publications`, `oecd_data_releases` | `feed` (`keep_categories`) | abstracts (CC BY 4.0, owner's approval) | `api.oecd.org` search feeds, `pageSize=50`; `www.oecd.org` itself is behind a Cloudflare challenge |
| OECD.AI | `oecd_ai_blog`, `oecd_ai_haip_reports` | `feed`, new `json_list` | none | OECD.AI reserves its rights; the HAIP reports are organisations' own words |
| OECD Data API | `oecd_headline` | new `oecd_sdmx` | observations | 13 queries, at most 18 a run, 6 s apart (the OECD's hourly limit) |
| STIP Compass | `stip_compass` | new `delimited_csv` (lake) | every column (owner's approval) | the database file answers; the portal's pages are behind the challenge |
| Breadth pack, wider world | `un_news`, `conversation_au`, `lowy_interpreter`, `ec_presscorner` | `feed` | titles only; the Commission's opening lines | see each card's licence |
| Breadth pack, adjacent and core | `aspi_strategist`, `arxiv_ai_society`, `standards_australia_news`, `us_federal_register_ip` | `feed` | opening lines (ASPI), abstracts (arXiv, CC0; no author names), titles (Standards Australia), abstracts (Federal Register) | |

**Checked and not added (D-020):** WTO news (robots.txt disallows it); the ACCC and the IEA (403 from the session and
a runner); cyber.gov.au and the TGA (time out from both); eSafety, the ARC, the Chief Scientist (time out) and the
AIHW (403) from the session; WHO's and the US Copyright Office's feeds (stopped); GOV.UK's DSIT feed (stale); the
OAIC's feed (undated); the Productivity Commission and Treasury (no feed found); the RBA (RSS 1.0, which the feed
adapter doesn't read). The industry.gov.au, cyber.gov.au, TGA, eSafety, ARC and Chief Scientist sites all refuse or
hang on cloud addresses; an owner upload is the route for their documents.

**Uploads (D-020):** a document entry may name its upload in `inbox/documents/` (`upload`), and Word files are read.
Ten of the owner's eleven files are evidence; the OECD Data API documentation was read to build `oecd_headline`.

## 3. Day 3 implications of the cleanup

- **Normalisation** gains feed items from APH (dates in RSS format) and legal documents from the corpus (dates as
  above).
- **Embeddings** take only the corpus slice in T2, step 6.
- **BM25** can index the corpus's titles and citations cheaply; its full text only for the slice.
- **New record shapes (D-020):** feed categories (the OECD's content types and policy areas, the Commission's policy
  areas, ASPI's tags); JSON-list items (HAIP reports); OECD series, some with words for values (`ip_tax_regimes`);
  STIP Compass's lake table (a row per instrument, 521 text columns, labels in the release manifest); arXiv items whose
  abstract starts with the announcement type (new, cross, replace).
- **New record shapes (D-018):** list-page items (`moip_news`, `wipo_treaty_notifications`: a date, no text);
  spreadsheet tables (`abs_datacubes`: headings, sections and labelled rows, to pivot into series with vintages);
  lake parts (`oalc`, `wipo_ipstats`) read straight from Parquet; undated feed items (APH hearings) observable from
  first sight.

## 4. Pile of Law: checked and discarded

Pile of Law is about 291 GB of mostly US legal text. It was checked on 2026-10-12 at dataset commit `2e96169e`. The
small subsets were read whole. For the large subsets, the first 3,000 records of each training file were read; that
is a sample, not a random one. Counts only: no text was kept. "IP term" means intellectual property, patent,
copyright, trade mark, TRIPS, plant breeder, industrial design or geographical indication, anywhere in the text.

| Subset | What it is (upstream) | Records read | Years | With an IP term | The better route |
|---|---|---:|---|---:|---|
| `undebates` | UN General Debate speeches (Harvard Dataverse's UN General Debate Corpus) | 8,481 (all) | 1970–2020 | 2.0% | The upstream corpus, if wanted (L5) |
| `ijc` | International Court of Justice and its predecessor: judgments and opinions (Zenodo) | 4,932 (all) | 1940s–2020s | 3.8% | None needed: cases between states, rarely about IP |
| `tos` | Terms of service (the CLAUDETTE project, EUI) | 50 (all) | about 2014–2017 | 98% (licence clauses) | Too few and too old |
| `uspto_oab` | USPTO office actions, 2019–2022 (USPTO open data) | 3,000 (sample) | 2019–2022 (card) | 99.9%; AI term 6.2% | USPTO's own open data: public domain and current (Tier 2, C2) |
| `congressional_hearings` | US Congress hearings (GovInfo) | 3,000 (sample) | 2017–2021 in the sample | 32.8%; AI term 17.9% | The GovInfo API (Tier 2, C5) |
| `federal_register` | US Federal Register (GovInfo) | 3,000 (sample) | 2004–2020 | 16.2% | The Federal Register API (Tier 2, C5) |
| `eurlex` | EU law (Harvard Dataverse) | 3,000 (sample) | to 2019 | 5.6% | EUR-Lex/Cellar (Tier 2, C5) |

The rest (US court opinions and dockets, contracts, US codes and rules, agency opinions, casebooks, Reddit legal
advice) is US-specific or carries personal information, and was not considered.

**Verdict: discarded.**
- Every useful subset is a copy of an upstream source Moria can read directly. The upstreams are newer and often in
  the public domain.
- The copies end between 2019 and 2022, and Moria looks for change.
- Its licence (CC BY-NC-SA 4.0) is stricter than most of the upstreams.
- Its loading script (`pile-of-law.py`) is third-party code.

On "UN decisions": the UN material is the General Debate speeches and the ICJ's judgments. It contains no UN
resolutions.

## 5. The backlog (not now)

### Parliament, beyond T1
- **L1. ParlInfo: Hansard, Bills Digests, Library papers.** Today ParlInfo, including its robots.txt and its Bills
  Digest feed, answered 403 with an Azure WAF JavaScript challenge. The owner will take this up later (D-017). The
  routes, in order:
  1. **Ask APH.** The block page gives a reference code and a contact link for "WAF Block" errors. As an IP Australia
     project, ask the Parliament's web team or the Parliamentary Library for a data route (Hansard XML, Bills
     Digests), or for Moria's user agent to be let through.
  2. **Try from a runner.**
  3. **A headless browser that identifies itself honestly** (Chromium and Playwright are available) would run the
     challenge as any browser does. This is a design change, because Moria would execute third-party JavaScript. It
     needs the owner's decision.
  4. **Other copies:** OpenAustralia (also behind Cloudflare in D-004), or bulk Hansard downloads, if APH offers
     them. Not checked.

  *A scraper the owner shared from another project was read, not run:*
  - **Its stealth parts conflict with D-011 and are not adopted:** the spoofed browser identity, the hidden automation
    flags, the randomised scrolling against timing fingerprints, the proxy retries for IP-reputation blocks, and a
    driver downloaded unpinned at run time.
  - **Parts that may be reused:**
    - its text normalisation, which day 3 needs;
    - trafilatura extraction, which removes boilerplate better than Moria's own HTML parser;
    - a DOCX reader through mammoth (useful for W1);
    - a block-page check, so that a challenge page is never stored as a document.

    trafilatura and mammoth would be new dependencies, pinned. The block signatures would need narrowing first:
    APH's real RSS page contains the word "captcha".
- **L2. The Library's pages:** FlagPost (its listed link is a reader page, not the feed), Research, and Issues and
  Insights. These answered 403 (WAF block) today.
- **L3. The other APH feeds:** House news, media releases, daily program, today's hearings, divisions and senators'
  details. They are mostly procedural, so they are not wanted for now.
- **L4. The statistics pages:** House statistics, Senate StatsNet (a JavaScript application) and the Library's
  Search Data. They count parliamentary business and hold electorate data, which has little bearing on IP signals.
- **L5. The UN General Debate Corpus** (Harvard Dataverse; the upstream of Pile of Law's `undebates`). States'
  speeches each year since 1970: a long-run, wider-world baseline (D5; legitimacy, P4). Its terms and newest year are
  to check.

### Tier 2 (design §5.4): not to build yet

These wait until the saturation rule (design §2.5) shows a ring needs more evidence. This is what each would need.
Catalogue line numbers refer to `Access-architecture-and-reusable-adapters.md`.

| # | Item | Route | Key or account | Adapter | Notes |
|---|---|---|---|---|---|
| C1 | AusTender | OCDS data API (catalogue 571–576) | none known; to confirm | new `ocds` | Contract notices by category over time, including IP Australia's own; licence to confirm |
| C2 | More patent offices | USPTO Open Data Portal, including PatentsView and office actions (499–504); EPO Open Patent Services (505) | USPTO: API key (to confirm); EPO: free registration, fair-use quota | new `patent_api` | Overlaps the BigQuery counts; take legal status, office-level detail and office actions |
| C3 | arXiv | OAI-PMH daily metadata (424, 783) | none | new `oai_pmh` | Metadata only; article text has its own licences (425). **Partly built (D-020):** the daily RSS listings of four categories (`arxiv_ai_society`) |
| C4 | Standards bodies | Not in the catalogue. Candidates: ETSI's IPR (standard-essential patent) declarations, the IETF Datatracker API, Standards Australia news | — | `feed` or new | ETSI's declarations are the most IP-specific; terms to check |
| C5 | Foreign regulation | US Federal Register API (no key); Regulations.gov, Congress.gov and GovInfo (api.data.gov key); EUR-Lex/Cellar (SPARQL); UK legislation (626–639) | api.data.gov key, free | `feed`; new `sparql` | Filter to IP, AI, data and trade; titles and metadata first. **Partly built (D-020):** the Federal Register's USPTO and Copyright Office documents (`us_federal_register_ip`), and the European Commission's press corner (`ec_presscorner`) |
| C6 | OECD, IMF | SDMX (536–537) | none (OECD throttles) | `abs_sdmx` may extend | Headline series chosen as for ABS; keep vintages. **OECD built (D-020):** `oecd_headline` (new `oecd_sdmx`), with the OECD's feeds, OECD.AI and STIP Compass; the IMF waits |
| C7 | World Bank, UN Comtrade | World Bank REST (524); Comtrade API (542) | Comtrade: free registration, daily limits | new small adapters | Keep vintages |
| C8 | Copernicus | Climate Data Store API (676–683) | account, key, per-dataset licence acceptance | new `cds` | Store monthly anomalies for Australia and the world only |
| C9 | Media Cloud | API (762) | account, key | new | Titles, URLs and metadata only (Moria's news rule) |
| C10 | Bluesky Jetstream | public stream (764) | none | new streaming consumer | Doesn't fit a daily batch; counts per term only, no handles or text; a personal-data decision first |
| C11 | Hacker News, GitHub | HN's Firebase API (769); GitHub search (770–775) | GitHub: the Actions token | new small adapters | Titles, URLs, scores and counts; no code stored |
| C12 | Search trends | Not in the catalogue. Wikipedia page views (Wikimedia's REST API) are an open stand-in; no open Google Trends API was confirmed | none | new small | Terms to confirm |

## 6. What this note rests on

- **Moria:** design §2.5, §5.2 to §5.4, §11.3 and §13; `CLAUDE.md`; `docs/handover-day2.md`; `docs/wishlist.md`;
  decisions D-004, D-011 and D-013 to D-016; `Access-architecture-and-reusable-adapters.md`; `src/moria/http.py`
  and the feed adapter.
- **Hugging Face, read 2026-10-12:** the corpus's README, `LICENCE.md`, `CHANGELOG.md` and file list; Pile of Law's
  README, file list and data (§4).
- **APH:** the requests in T1 and L1, 2026-10-12.
