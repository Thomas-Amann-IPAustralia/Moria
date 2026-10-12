# Terms check: how often each search term appears in the news

Run `20261012T131633Z-cdd72551` (`moria terms check`). Generated; do not edit by hand.

**Sample:** 13 days of GDELT GKG files, one a week from 2026-07-19 to 2026-10-11: 686,681 English web documents, 37,344 from `.au` domains.

**How to read it.** *World/day* is the average number of documents a sampled day that mention the term
(whole words, in either spelling and with a plural last word, in the title, URL, quotations or named
entities, with its synonyms counted as the term); *About/day* counts only matches in the title or URL, the
documents about the term; *.au/day* is for `.au` domains. *Names only* is the share found only inside
GDELT's named entities, which is often incidental (D-012). *Via synonyms* is the share found only through a
synonym (D-014), with the number of synonyms in brackets.
Flags are triage: `silent` no hit at all; `rare` under 0.2 a day;
`broad` over 500 a day; `names-heavy` over 60% names-only hits. The hit
samples are in the private bucket; a person reads them before any term is narrowed or dropped.

**239 distinct terms; 153 flagged.**

## T1

| Term | Ring or theme | World/day | About/day | .au/day | Days with hits | Names only | Via synonyms | Flags |
|---|---|---:|---:|---:|---:|---:|---:|---|
| cost of living | wider_world | 105.5 | 100.1 | 5.85 | 13/13 | 1% |  |  |
| organised crime | wider_world | 37.5 | 4.6 | 4.08 | 13/13 | 63% |  | `names-heavy` |
| consumer product safety | wider_world | 5.8 | 0.0 | 0.00 | 11/13 | 100% |  | `names-heavy` |
| economic coercion | wider_world | 4.6 | 4.5 | 0.00 | 2/13 | 0% |  |  |
| trade tensions | wider_world | 1.5 | 1.5 | 0.00 | 7/13 | 0% |  |  |
| cease and desist | core | 1.2 | 1.0 | 0.00 | 8/13 | 6% |  |  |
| digital product passport | adjacent | 1.2 | 0.1 | 0.08 | 7/13 | 94% |  | `names-heavy` |
| counterfeit goods | core | 0.9 | 0.7 | 0.00 | 7/13 | 17% | 33% (3) |  |
| trade mark infringement | core | 0.6 | 0.6 | 0.00 | 5/13 | 0% | 25% (2) |  |
| trademark infringement | core | 0.5 | 0.5 | 0.00 | 5/13 | 0% |  |  |
| cross-border e-commerce | adjacent | 0.4 | 0.2 | 0.00 | 4/13 | 0% |  |  |
| knock-off products | adjacent | 0.4 | 0.2 | 0.00 | 4/13 | 0% | 100% (1) |  |
| patent infringement | core | 0.4 | 0.4 | 0.00 | 3/13 | 0% | 20% (3) |  |
| marketplace takedown | adjacent | 0.3 | 0.2 | 0.00 | 2/13 | 25% | 100% (2) |  |
| counterfeiting | core | 0.2 | 0.1 | 0.00 | 3/13 | 33% | 0% (1) |  |
| intellectual property enforcement | core | 0.2 | 0.2 | 0.00 | 1/13 | 0% | 100% (2) |  |
| online piracy | core | 0.2 | 0.2 | 0.00 | 2/13 | 0% | 50% (5) | `rare` |
| trademark squatting | core | 0.2 | 0.2 | 0.00 | 1/13 | 0% | 0% (2) | `rare` |
| brand protection | core | 0.1 | 0.1 | 0.00 | 1/13 | 0% | 0% (1) | `rare` |
| counterfeit medicines | wider_world | 0.1 | 0.1 | 0.00 | 1/13 | 0% |  | `rare` |
| intellectual property litigation | core | 0.1 | 0.1 | 0.00 | 1/13 | 0% | 100% (3) | `rare` |
| intellectual property theft | core | 0.1 | 0.1 | 0.00 | 1/13 | 0% | 0% (4) | `rare` |
| online platform regulation | wider_world | 0.1 | 0.1 | 0.00 | 1/13 | 0% | 100% (3) | `rare` |
| pirated goods | core | 0.1 | 0.1 | 0.00 | 1/13 | 0% | 100% (3) | `rare` |
| platform liability | adjacent | 0.1 | 0.1 | 0.00 | 1/13 | 0% | 100% (1) | `rare` |
| anti-counterfeiting | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (1) | `silent` |
| bad faith trade mark | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| brand impersonation | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| copycat products | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |
| design infringement | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| dupe culture | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| fake invoice scam | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |
| fake products online | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| intellectual property dispute | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (4) | `silent` |
| intellectual property infringement | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |
| parallel imports | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - | - (3) | `silent` |
| product authenticity | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| small business export | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - | - (1) | `silent` |
| supply chain traceability | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |

## T2

| Term | Ring or theme | World/day | About/day | .au/day | Days with hits | Names only | Via synonyms | Flags |
|---|---|---:|---:|---:|---:|---:|---:|---|
| entrepreneurship | wider_world | 15.2 | 4.7 | 0.62 | 13/13 | 60% |  | `names-heavy` |
| research translation | adjacent | 4.4 | 0.0 | 4.38 | 1/13 | 100% |  | `names-heavy` |
| skills shortage | wider_world | 1.2 | 0.5 | 0.00 | 6/13 | 6% |  |  |
| creator economy | wider_world | 1.0 | 0.9 | 0.00 | 5/13 | 8% |  |  |
| trade secrets | adjacent | 0.9 | 0.3 | 0.00 | 6/13 | 42% | 42% (1) |  |
| startup founders | adjacent | 0.6 | 0.6 | 0.00 | 5/13 | 0% | 38% (2) |  |
| regional innovation | wider_world | 0.5 | 0.2 | 0.00 | 4/13 | 67% |  |  |
| digital adoption | wider_world | 0.4 | 0.2 | 0.00 | 3/13 | 60% |  |  |
| open innovation | adjacent | 0.4 | 0.0 | 0.00 | 3/13 | 100% |  |  |
| trade mark application | core | 0.2 | 0.2 | 0.00 | 3/13 | 33% | 100% (4) |  |
| intangible assets | adjacent | 0.2 | 0.0 | 0.00 | 2/13 | 100% | 0% (1) | `rare` |
| intellectual property strategy | core | 0.2 | 0.1 | 0.00 | 2/13 | 50% | 100% (2) | `rare` |
| research commercialisation | adjacent | 0.2 | 0.1 | 0.00 | 2/13 | 50% |  | `rare` |
| first patent | core | 0.1 | 0.1 | 0.00 | 1/13 | 0% | 0% (1) | `rare` |
| accelerated examination | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (3) | `silent` |
| ai patent drafting | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| ai trademark search | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| collaborative research agreement | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| design registration | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (1) | `silent` |
| first nations business | wider_world | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| generative design | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| intellectual property awareness | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (1) | `silent` |
| intellectual property for small business | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| iterative product development | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| patent application cost | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (3) | `silent` |
| patent grace period | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| provisional patent | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| r&d tax incentive | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |
| rapid prototyping | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| small business ai adoption | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| trademark registration | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |

## T3

| Term | Ring or theme | World/day | About/day | .au/day | Days with hits | Names only | Via synonyms | Flags |
|---|---|---:|---:|---:|---:|---:|---:|---|
| industrial policy | wider_world | 4.2 | 1.4 | 0.00 | 12/13 | 53% |  |  |
| advanced manufacturing | adjacent | 4.0 | 0.7 | 0.23 | 12/13 | 67% |  | `names-heavy` |
| technology transfer | adjacent | 2.3 | 0.4 | 0.00 | 10/13 | 77% |  | `names-heavy` |
| technology licensing | core | 0.3 | 0.1 | 0.00 | 4/13 | 75% | 75% (1) |  |
| critical minerals processing | adjacent | 0.2 | 0.1 | 0.00 | 1/13 | 50% |  | `rare` |
| economic complexity | wider_world | 0.2 | 0.0 | 0.00 | 2/13 | 100% |  | `rare` |
| national reconstruction fund | adjacent | 0.2 | 0.1 | 0.08 | 2/13 | 50% |  | `rare` |
| patent pool | core | 0.2 | 0.0 | 0.00 | 1/13 | 100% |  | `rare` |
| university spin-out | adjacent | 0.2 | 0.2 | 0.00 | 1/13 | 0% | 100% (2) | `rare` |
| intellectual property valuation | core | 0.1 | 0.0 | 0.00 | 1/13 | 0% | 100% (3) | `rare` |
| productivity growth | wider_world | 0.1 | 0.0 | 0.00 | 1/13 | 0% |  | `rare` |
| royalty income | adjacent | 0.1 | 0.0 | 0.00 | 1/13 | 100% | 0% (1) | `rare` |
| small business lending | wider_world | 0.1 | 0.0 | 0.00 | 1/13 | 100% |  | `rare` |
| sovereign capability | wider_world | 0.1 | 0.0 | 0.00 | 1/13 | 0% |  | `rare` |
| standard essential patents | core | 0.1 | 0.0 | 0.00 | 1/13 | 0% | 100% (3) | `rare` |
| brand registry | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| commercialisation funding | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| deep tech venture capital | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| future made in australia | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| innovation diffusion | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| intangible asset valuation | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| intangible investment | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |
| intellectual property audit | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (1) | `silent` |
| intellectual property commercialisation | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (3) | `silent` |
| ip-backed finance | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (5) | `silent` |
| ip-backed lending | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| patent licensing | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |
| patent monetisation | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (6) | `silent` |
| patent valuation | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |

## T4

| Term | Ring or theme | World/day | About/day | .au/day | Days with hits | Names only | Via synonyms | Flags |
|---|---|---:|---:|---:|---:|---:|---:|---|
| industry association | adjacent | 15.7 | 0.2 | 1.77 | 13/13 | 99% |  | `names-heavy` |
| digital public infrastructure | wider_world | 5.3 | 0.1 | 0.00 | 10/13 | 97% |  | `names-heavy` |
| digital identity | adjacent | 1.2 | 0.4 | 0.00 | 7/13 | 47% |  |  |
| platform economy | wider_world | 0.6 | 0.2 | 0.00 | 5/13 | 75% |  |  |
| public sector reform | wider_world | 0.4 | 0.1 | 0.00 | 5/13 | 80% |  |  |
| legal technology | adjacent | 0.2 | 0.0 | 0.00 | 1/13 | 33% |  |  |
| trust in government | wider_world | 0.2 | 0.2 | 0.00 | 2/13 | 0% |  |  |
| business accelerator | adjacent | 0.2 | 0.0 | 0.00 | 2/13 | 100% |  | `rare` |
| startup incubator | adjacent | 0.1 | 0.1 | 0.00 | 1/13 | 0% |  | `rare` |
| trade marks attorney | core | 0.1 | 0.1 | 0.00 | 1/13 | 0% | 100% (2) | `rare` |
| ai in government services | wider_world | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |
| ai legal services | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |
| business platforms | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| government service partnerships | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| intellectual property education | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (1) | `silent` |
| intellectual property firm | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (3) | `silent` |
| intellectual property mediation | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (3) | `silent` |
| intellectual property services | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| ip management software | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| legal tech intellectual property | core | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| one-stop shop for business | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| patent attorney | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |
| small business advisers | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |

## T5

| Term | Ring or theme | World/day | About/day | .au/day | Days with hits | Names only | Via synonyms | Flags |
|---|---|---:|---:|---:|---:|---:|---:|---|
| inequality | wider_world | 9.6 | 5.1 | 0.38 | 13/13 | 18% |  |  |
| open source ai | adjacent | 8.4 | 8.2 | 0.00 | 10/13 | 0% |  |  |
| geographical indications | core | 7.9 | 0.0 | 0.00 | 13/13 | 88% | 86% (4) | `names-heavy` |
| climate adaptation | wider_world | 1.5 | 0.5 | 0.00 | 11/13 | 65% |  | `names-heavy` |
| traditional knowledge | core | 1.5 | 0.7 | 0.00 | 7/13 | 32% |  |  |
| open science | adjacent | 1.3 | 0.0 | 0.08 | 9/13 | 100% |  | `names-heavy` |
| pandemic preparedness | wider_world | 1.2 | 1.0 | 0.00 | 2/13 | 19% |  |  |
| open data | adjacent | 0.9 | 0.1 | 0.00 | 6/13 | 92% |  | `names-heavy` |
| digital sovereignty | wider_world | 0.8 | 0.6 | 0.00 | 7/13 | 27% |  |  |
| right to repair | core | 0.8 | 0.7 | 0.00 | 9/13 | 9% |  |  |
| closing the gap | wider_world | 0.5 | 0.5 | 0.08 | 5/13 | 0% |  |  |
| platform power | adjacent | 0.2 | 0.0 | 0.00 | 2/13 | 100% |  |  |
| trust in institutions | wider_world | 0.2 | 0.2 | 0.00 | 3/13 | 33% | 100% (1) |  |
| data rights | adjacent | 0.2 | 0.0 | 0.00 | 2/13 | 100% |  | `rare` |
| access to medicines patents | core | 0.1 | 0.0 | 0.00 | 1/13 | 100% | 100% (5) | `rare` |
| ai inventorship | core | 0.1 | 0.0 | 0.00 | 1/13 | 0% | 100% (6) | `rare` |
| ai-generated works copyright | core | 0.1 | 0.1 | 0.00 | 1/13 | 0% | 100% (4) | `rare` |
| climate technology transfer | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| compulsory licensing | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |
| digital commons | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| first nations economic empowerment | wider_world | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| generative ai training data | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - | - (1) | `silent` |
| genetic resources disclosure | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (3) | `silent` |
| indigenous cultural and intellectual property | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |
| indigenous knowledge protection | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (3) | `silent` |
| mission-oriented innovation | adjacent | 0.0 | 0.0 | 0.00 | 0/13 | - | - (1) | `silent` |
| patent system reform | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (3) | `silent` |
| patent waiver | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (5) | `silent` |
| plant breeders rights | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (3) | `silent` |
| text and data mining exception | core | 0.0 | 0.0 | 0.00 | 0/13 | - | - (2) | `silent` |

## Broad themes

| Term | Ring or theme | World/day | About/day | .au/day | Days with hits | Names only | Via synonyms | Flags |
|---|---|---:|---:|---:|---:|---:|---:|---|
| brics | global_shifts | 164.9 | 161.9 | 1.23 | 13/13 | 1% |  |  |
| artificial intelligence | technology_general | 153.3 | 38.7 | 8.54 | 13/13 | 69% |  | `names-heavy` |
| inflation | economy_finance | 138.8 | 116.9 | 24.62 | 13/13 | 11% |  |  |
| climate change | climate_energy_resources | 136.4 | 32.1 | 11.23 | 13/13 | 60% |  | `names-heavy` |
| global south | global_shifts | 134.2 | 19.7 | 1.46 | 13/13 | 84% |  | `names-heavy` |
| mental health | demographics_health | 125.7 | 59.4 | 12.54 | 13/13 | 45% |  |  |
| cost of living | society_values_trust | 105.5 | 100.1 | 5.85 | 13/13 | 1% |  |  |
| sanctions | security_conflict | 89.8 | 66.6 | 5.62 | 13/13 | 9% |  |  |
| first nations | society_values_trust | 82.2 | 5.2 | 38.23 | 13/13 | 93% |  | `names-heavy` |
| net zero | climate_energy_resources | 41.4 | 8.1 | 5.31 | 13/13 | 78% |  | `names-heavy` |
| trade agreement | governance_public_sector | 34.4 | 5.8 | 1.00 | 13/13 | 80% |  | `names-heavy` |
| robotics | technology_general | 28.4 | 11.4 | 0.15 | 13/13 | 57% |  |  |
| biodiversity | nature_circularity | 27.8 | 6.7 | 6.69 | 13/13 | 69% |  | `names-heavy` |
| productivity | economy_finance | 26.9 | 11.8 | 9.00 | 13/13 | 42% |  |  |
| consumer protection | society_values_trust | 26.0 | 1.8 | 0.08 | 13/13 | 91% |  | `names-heavy` |
| childcare | care_migration | 25.8 | 21.7 | 0.54 | 13/13 | 9% |  |  |
| extreme weather | climate_energy_resources | 22.5 | 9.7 | 0.00 | 13/13 | 45% |  |  |
| critical minerals | climate_energy_resources | 21.8 | 12.7 | 0.15 | 13/13 | 20% |  |  |
| interest rates | economy_finance | 20.1 | 16.9 | 2.08 | 13/13 | 5% |  |  |
| patent | ip_system | 19.2 | 6.9 | 0.08 | 13/13 | 62% |  | `names-heavy` |
| recession | economy_finance | 18.2 | 2.5 | 0.38 | 13/13 | 83% |  | `names-heavy` |
| misinformation | information_ecosystem | 17.5 | 14.0 | 0.23 | 13/13 | 6% |  |  |
| invasive species | nature_circularity | 16.1 | 2.0 | 11.31 | 12/13 | 87% |  | `names-heavy` |
| online safety | information_ecosystem | 14.2 | 1.6 | 0.31 | 13/13 | 88% |  | `names-heavy` |
| regional development | infrastructure_cities | 13.6 | 5.2 | 1.54 | 13/13 | 59% |  |  |
| pandemic | demographics_health | 13.2 | 8.8 | 0.38 | 13/13 | 19% |  |  |
| infrastructure investment | infrastructure_cities | 13.1 | 1.7 | 3.69 | 13/13 | 85% |  | `names-heavy` |
| social cohesion | society_values_trust | 12.6 | 5.2 | 9.85 | 11/13 | 50% |  |  |
| aged care | demographics_health | 12.4 | 11.3 | 11.77 | 10/13 | 6% |  |  |
| biotechnology | technology_general | 11.0 | 2.1 | 1.08 | 13/13 | 78% |  | `names-heavy` |
| deepfakes | information_ecosystem | 10.3 | 10.2 | 0.31 | 12/13 | 1% |  |  |
| intellectual property | ip_system | 10.1 | 0.8 | 0.15 | 13/13 | 82% | 1% (2) | `names-heavy` |
| inequality | society_values_trust | 9.6 | 5.1 | 0.38 | 13/13 | 18% |  |  |
| energy transition | climate_energy_resources | 9.5 | 3.5 | 0.69 | 13/13 | 59% |  |  |
| migration policy | demographics_health | 9.1 | 1.1 | 0.46 | 10/13 | 84% |  | `names-heavy` |
| e-commerce | cities_consumption | 9.0 | 7.1 | 0.00 | 13/13 | 19% |  |  |
| indo-pacific | global_shifts | 9.0 | 2.3 | 0.23 | 13/13 | 32% |  |  |
| red tape | governance_public_sector | 8.9 | 6.8 | 5.46 | 12/13 | 9% |  |  |
| trade mark | ip_system | 8.4 | 3.1 | 0.00 | 13/13 | 57% |  |  |
| defence industry | security_conflict | 8.2 | 1.8 | 0.85 | 13/13 | 70% |  | `names-heavy` |
| middle class | cities_consumption | 8.2 | 3.8 | 0.31 | 13/13 | 19% |  |  |
| geographical indications | ip_system | 7.9 | 0.0 | 0.00 | 13/13 | 88% | 86% (4) | `names-heavy` |
| housing affordability | infrastructure_cities | 7.5 | 6.9 | 5.85 | 11/13 | 2% |  |  |
| quantum computing | technology_general | 7.1 | 5.2 | 0.00 | 13/13 | 24% |  |  |
| semiconductors | technology_general | 6.4 | 4.1 | 0.00 | 13/13 | 20% |  |  |
| copyright | ip_system | 5.9 | 4.5 | 0.00 | 13/13 | 0% |  |  |
| venture capital | economy_finance | 5.7 | 1.2 | 0.00 | 13/13 | 78% |  | `names-heavy` |
| intellectual property office | ip_system | 5.4 | 0.8 | 0.00 | 13/13 | 84% | 67% (5) | `names-heavy` |
| cyber attack | security_conflict | 5.3 | 5.2 | 1.15 | 10/13 | 0% |  |  |
| geopolitical tensions | security_conflict | 5.2 | 4.2 | 0.08 | 11/13 | 1% |  |  |
| economic security | security_conflict | 4.6 | 0.5 | 0.31 | 12/13 | 58% |  |  |
| data privacy | information_ecosystem | 3.6 | 1.8 | 0.38 | 12/13 | 43% |  |  |
| vocational training | work_education_skills | 3.5 | 0.8 | 0.00 | 11/13 | 56% |  |  |
| digital infrastructure | infrastructure_cities | 3.2 | 0.9 | 0.00 | 12/13 | 63% |  | `names-heavy` |
| international students | care_migration | 3.0 | 2.2 | 0.31 | 12/13 | 21% |  |  |
| circular economy | nature_circularity | 2.8 | 1.0 | 0.00 | 12/13 | 64% |  | `names-heavy` |
| digital government | governance_public_sector | 2.3 | 0.2 | 0.00 | 10/13 | 60% |  |  |
| consumer spending | cities_consumption | 2.1 | 1.8 | 0.00 | 9/13 | 7% |  |  |
| space industry | technology_general | 2.1 | 0.5 | 0.15 | 7/13 | 19% |  |  |
| water security | climate_energy_resources | 2.1 | 1.2 | 0.00 | 13/13 | 30% |  |  |
| chronic disease | demographics_health | 1.8 | 0.7 | 0.00 | 9/13 | 43% |  |  |
| disability support | care_migration | 1.8 | 0.3 | 0.08 | 7/13 | 78% |  | `names-heavy` |
| smart cities | infrastructure_cities | 1.7 | 0.5 | 0.00 | 11/13 | 68% |  | `names-heavy` |
| multipolar | global_shifts | 1.5 | 1.0 | 0.00 | 7/13 | 5% |  |  |
| remote work | work_education_skills | 1.5 | 1.1 | 0.00 | 9/13 | 16% |  |  |
| wipo | ip_system | 1.5 | 0.0 | 0.00 | 10/13 | 100% | 100% (1) | `names-heavy` |
| digital platforms | information_ecosystem | 1.4 | 0.8 | 0.00 | 6/13 | 33% |  |  |
| skills shortage | work_education_skills | 1.2 | 0.5 | 0.00 | 6/13 | 6% |  |  |
| business investment | economy_finance | 1.2 | 0.2 | 0.00 | 11/13 | 67% |  | `names-heavy` |
| fast fashion | cities_consumption | 1.2 | 1.1 | 0.38 | 8/13 | 0% |  |  |
| deforestation | nature_circularity | 0.8 | 0.5 | 0.00 | 7/13 | 30% |  |  |
| future of work | work_education_skills | 0.5 | 0.4 | 0.00 | 4/13 | 0% |  |  |
| urbanisation | cities_consumption | 0.5 | 0.2 | 0.00 | 6/13 | 43% |  |  |
| nature positive | nature_circularity | 0.5 | 0.2 | 0.00 | 3/13 | 50% |  |  |
| registered design | ip_system | 0.5 | 0.0 | 0.00 | 6/13 | 100% | 100% (1) |  |
| ecosystem restoration | nature_circularity | 0.4 | 0.2 | 0.00 | 4/13 | 60% |  |  |
| public sector reform | governance_public_sector | 0.4 | 0.1 | 0.00 | 5/13 | 80% |  |  |
| care economy | care_migration | 0.2 | 0.0 | 0.00 | 3/13 | 67% |  |  |
| skilled migration | care_migration | 0.2 | 0.0 | 0.08 | 2/13 | 67% |  |  |
| trust in institutions | society_values_trust | 0.2 | 0.2 | 0.00 | 3/13 | 33% | 100% (1) |  |
| population ageing | demographics_health | 0.2 | 0.0 | 0.00 | 2/13 | 50% |  | `rare` |
| reshoring | global_shifts | 0.2 | 0.1 | 0.00 | 2/13 | 50% |  | `rare` |
| supply chain disruption | security_conflict | 0.1 | 0.0 | 0.00 | 1/13 | 0% |  | `rare` |
| transport electrification | infrastructure_cities | 0.1 | 0.0 | 0.00 | 1/13 | 100% |  | `rare` |
| university funding | work_education_skills | 0.1 | 0.1 | 0.00 | 1/13 | 0% |  | `rare` |
| aged care workforce | care_migration | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| automation jobs | work_education_skills | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| deglobalisation | global_shifts | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| government ai | governance_public_sector | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| ip australia | ip_system | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| megacities | cities_consumption | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| plant breeders rights | ip_system | 0.0 | 0.0 | 0.00 | 0/13 | - | - (3) | `silent` |
| regulation reform | governance_public_sector | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |
| social media regulation | information_ecosystem | 0.0 | 0.0 | 0.00 | 0/13 | - |  | `silent` |

