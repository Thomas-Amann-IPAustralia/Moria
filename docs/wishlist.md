# Documents wishlist: for the owner to download

Some sites refuse cloud addresses, so Moria's collectors can't fetch these documents. You download them, and Moria
reads them from the private bucket (D-014). Started 2026-10-12. Tick an item off by uploading it, or by telling me it
can't be had.

**Status (2026-10-13, D-020):** eleven files uploaded and read. Still wanted: the Critical Technologies list, the OECD
STI Outlook 2025, the Government's response to the Patents Accessibility Review, WEF's two top-10 lists, and the EPO's
terms (section 4). The KIPO report has no text layer; a text version would help.

## How to hand a document over

1. **Upload only if its licence allows it.** If you're not sure, leave it and tell me what the site says.
2. Cloudflare dashboard → **R2 Object Storage** → bucket **`moria`** → folder **`inbox/documents/`** (create it the
   first time) → **Upload**. Name the file as in the *Save as* column, or keep its own name and tell me which
   document it is (D-020). A web page: save it as *Web page, HTML only*, with `.html`. Word files are read too.
3. Tell me, or run **Actions → collect-source** with the card named in the table. The run reads the upload instead of
   the website and records its SHA-256, size and page count.
4. **The licence check runs on every document.** It searches the first and last pages for licence statements
   (Creative Commons and its version, the Open Government Licence, the EU reuse notice, "all rights reserved", "no
   part may be reproduced", public domain). It stores the text only where the card and the document agree, and warns
   when they don't. The result is on record in the run's manifest and in `reports/census/<card>.md` (licence names
   only, never the text).

Not GitHub: the repo is public, so a document committed there is republished to everyone.

## 1. Foresight and national strategies (card `foresight_syntheses`)

| Save as | Document | Where to get it | Licence, as far as known | Text stored when |
|---|---|---|---|---|
| ✅ uploaded (text stored, CC BY 4.0) | Australia's National Science and Research Priorities 2024 (DISR) | [industry.gov.au](https://www.industry.gov.au/sites/default/files/2024-08/australias-national-science-and-research-priorities-2024.pdf) | CC BY 4.0, by search results | the PDF states an open licence |
| `critical_technologies_list.html` | List of Critical Technologies in the National Interest (DISR; a web page, no PDF) | [industry.gov.au](https://www.industry.gov.au/publications/list-critical-technologies-national-interest) | to confirm | the page states an open licence |
| ✅ uploaded (text stored, CC BY 4.0) | Australia's Net Zero Plan (DCCEEW, 2025; the corrected version of 2026-03-17 if offered) | [dcceew.gov.au](https://www.dcceew.gov.au/sites/default/files/documents/net-zero-report.pdf) | CC BY 4.0, by search results | the PDF states an open licence |
| ✅ uploaded, with the Integrated Investment Program (both reserve their rights: metadata only) | 2026 National Defence Strategy (Defence; the strategy, not the factsheet) | [defence.gov.au/nds](https://www.defence.gov.au/nds) | © Commonwealth of Australia 2026; licence to confirm | the PDF states an open licence |
| `oecd_sti_outlook_2025.pdf` | OECD Science, Technology and Innovation Outlook 2025 | [oecd.org](https://www.oecd.org/en/publications/oecd-science-technology-and-innovation-outlook-2025_5fe57b90-en.html) | CC BY 4.0, by its copyright page as quoted in search results | the PDF states an open licence. Still wanted: the OECD's robots.txt disallows its PDF path (`/content/dam/`) to Moria (D-020) |
| **don't upload** | WEF, *Global Risks Report 2026* | [weforum.org](https://www.weforum.org/publications/global-risks-report-2026/) | WEF reserves its rights (to confirm) | never: metadata only |

For WEF, paste instead the report's two **top-10 lists** (2-year and 10-year horizon), names only, into the chat:
they are facts, and enough for the known-trends baseline.

## 2. Peer IP offices (card `peer_office_strategies`)

| Save as | Document | Where to get it | Licence, as far as known | Text stored when |
|---|---|---|---|---|
| ✅ uploaded (no licence stated: metadata only) | JPO Status Report 2026 (the whole report, about 25 MB) | [jpo.go.jp](https://www.jpo.go.jp/e/resources/report/statusreport/2026/index.html) | JPO website terms, to confirm | the PDF states an open licence |
| ✅ uploaded (text stored under its reproduction notice and D-017) | CIPO 2023-2028 Business Strategy, linked from the release | [canada.ca](https://www.canada.ca/en/intellectual-property-office/news/2023/02/cipo-releases-its-20232028-business-strategy.html) | Government of Canada terms (section 4) | you confirm those terms |
| ✅ uploaded, 2025 (its text is outlines, not text: unreadable without OCR) | KIPO's latest annual report in English | kipo.go.kr | to find | I add a card entry when it's there |

No action needed for these, which answer from here: the UKIPO's Corporate Plan 2026 to 2027, the USPTO's strategy
page, the EPO's Strategic Plan 2028 page and its [Annual Work Plan 2026](https://link.epo.org/web/about-us/transparency-portal/en-annual-work-plan-2026.pdf),
and the EUIPO's [Strategic Plan 2030](https://euipo.europa.eu/tunnel-web/secure/webdav/guest/document_library/contentPdfs/about_euipo/strategic_plan/strategic-plan-2030_en.pdf).
Not wanted: IPONZ (its newest published business plan is for 2021-22) and IPOS (its terms forbid reproduction).

## 3. Documents the Growth Territories cite (card `territory_evidence`)

Public reports that your territory context cites, listed here with your approval (D-015).

| Save as | Document | Where to get it | Licence, as far as known | Text stored when |
|---|---|---|---|---|
| ✅ uploaded (reserves its rights: metadata only) | AIC, *Estimating the costs of serious and organised crime in Australia, 2020-21* (Statistical Report 38): the 2021 value of counterfeit and pirated goods | [aic.gov.au](https://www.aic.gov.au/sites/default/files/2022-04/sr38_estimating_the_costs_of_serious_and_organised_crime_v2.pdf) | to confirm | the PDF states an open licence |
| ✅ uploaded (reserves its rights: metadata only) | AIC, *The costs of serious and organised crime in Australia, 2023-24* (Statistical Report 55): the newer edition | [aic.gov.au](https://www.aic.gov.au/sites/default/files/2025-11/sr55_costs_of_serious_and_organised_crime_in_australia_2023-24.pdf) | to confirm | the PDF states an open licence |
| ✅ uploaded as Word (text stored, CC BY 4.0) | *Patents Accessibility Review: Final report* (2021). It is offered as a Word file: open it and save it as PDF | [industry.gov.au](https://www.industry.gov.au/publications/patents-accessibility-review) | to confirm | the PDF states an open licence |
| `patents_accessibility_review_government_response_2022.pdf` | The Government's response to the review (2022) | [industry.gov.au](https://www.industry.gov.au/sites/default/files/2022-06/iga_patents_accessibility_review.pdf) | to confirm | the PDF states an open licence |

No action needed for these, which answer from here: the Productivity Commission's *Innovation for the 98%*
([interim report, 2022](https://assets.pc.gov.au/inquiries/completed/productivity/interim3-innovation/productivity-interim3-innovation.pdf),
and [Volume 5 of the final report, 2023](https://assets.pc.gov.au/inquiries/completed/productivity/report/productivity-volume5-innovation-diffusion.pdf)),
and IP Australia's [Australian IP Report 2026](https://www.ipaustralia.gov.au/-/media/Project/IPA/IPAustralia/PDF/IP-Reports/Australian-IP-Report-2026.pdf),
whose first chapter links a first patent grant or trade mark registration with later income and productivity.

## 4. Terms to read (nothing to download)

| Site | What I could read from here | Your call |
|---|---|---|
| **EPO** ([terms of use](https://www.epo.org/en/terms-of-use/terms-and-conditions-use-website-european-patent-office), section 6) | Read on 2026-10-12. The EPO's own information may be downloaded, printed and processed "for private and commercial purposes", displayed accurately and citing the website. Excluded: third-party content, the EPO's logos and trade marks, and images not offered for download. | Confirm, and I'll store the text of EPO news, Boards of Appeal news, the Strategic Plan 2028 page and the Annual Work Plan, citing the EPO. |
| **Canada.ca**, settled (D-020): CIPO's own strategy carries the same notice, and Moria's use is non-commercial (D-017); CIPO's strategy text and news summaries are stored ([terms and conditions](https://www.canada.ca/en/transparency/terms.html)) | Canada.ca refuses this session; from search results: materials may be reproduced "for non-commercial purposes, and in any format, without charge or further permission", stating the title and author and that the copy is not an official version; the official symbols are excluded. | Confirm that Moria's private, internal storage counts as non-commercial, and I'll store CIPO's news summaries and its strategy. |
| **CSIRO Data Access Portal** (card `csiro_dap`), settled (D-024): the owner approved storing the descriptions | CSIRO's sites refuse this session. From search results: each collection's data carry their own licence, CC BY 4.0 by default under CSIRO's deposit terms; no licence for the portal's metadata (titles, descriptions, keywords) was found, and csiro.au states CSIRO copyright without an open licence. | Settled: descriptions are stored. |

## Not needed from you

- ABS business entries and exits (CABEE) and business R&D (BERD): read since D-018 (`abs_datacubes`).
- The EUIPO, JPO and other legal notices beyond those above: each document's own licence statement decides.
