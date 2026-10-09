|In the tables below:|Col2|
|---|---|
|Mark|Meaning|
|A|Core source I would integrate<br>early. Broad value, unusual signal,<br>authoritative provenance, or very<br>strong machine access.|
|B|Strong supplementary source,<br>particularly useful for specialist<br>sub-agents.|
|C|Niche, redundant, more difficult to<br>operate, or primarily useful when a<br>particular horizon-scan domain<br>becomes relevant.|
|Official MCP|MCP implementation operated by<br>or clearly published by the<br>underlying provider.|
|Community MCP|Open/community implementation<br>exists or a credible community<br>integration layer exists; inspect and<br>pin it before use.|
|Generic MCP|I would connect it through a<br>reusable locally hosted protocol<br>adapter such as SDMX, SPARQL,<br>OAI-PMH, CKAN or<br>REST/OpenAPI.|
|Custom MCP|The API is valuable enough to<br>justify a thin provider-specific local<br>wrapper.|
|Bulk/local mirror|Particularly attractive for your<br>architecture because source data<br>can be periodically mirrored and<br>queried locally.|

# Access architecture and reusable adapters

The highest-leverage engineering decision is to normalize protocols before
providers. The sources below repeatedly expose the same families of interfaces:
OECD, IMF, ECB and ABS use SDMX; OpenCitations and EU Cellar expose
SPARQL; arXiv and DataCite support OAI-PMH; many government systems expose
REST/JSON; NASA increasingly exposes both REST and GraphQL; and some
[public-data portals are backed by reusable catalog technologies. [4]](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html)

Sources
unlocked

ClinicalTrials.go
v, openFDA,
World Bank,
Census, SEC,
USAspending,
Federal
Register,
Regulations.gov,
Congress.gov,
EIA, GBIF,
OpenAQ and
[many more. [5]](https://clinicaltrials.gov/data-api/api)

Priority

Local capability
to build once

A Generic
REST/OpenAPI
MCP

A SDMX MCP OECD Data
Explorer, IMF
Data, ECB Data
Portal, ABS
Data API, and
other SDMX
statistical
[providers. [6]](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html)

A SPARQL/RDF
MCP

OpenCitations,
EUR-Lex/Cellar,
TED linked
open data and
other RDF
knowledge
[graphs. [7]](https://opencitations.net/querying/)

Recommended
behavior

Read-only
GET/POST
tools; accept
endpoint-specifi
c schemas from
configuration;
automatically
persist complete
request/respons
e envelopes.

Expose
`list_dataflows`,
```
describe_struc
```

`ture`,
`query_series`,
`get_metadata` ;
optionally
materialize
results into
Parquet/DuckD
B.

Support
SELECT/CONS
TRUCT, graph
limits,
pagination and
stored query
templates;
preserve query
plus endpoint
timestamp.

A OAI-PMH MCP arXiv, DataCite
and scholarly
[repositories. [8]](https://info.arxiv.org/help/bulk_data.html)

A OAI-PMH MCP arXiv, DataCite Ideal for
and scholarly incremental
[repositories. [8]](https://info.arxiv.org/help/bulk_data.html) harvesting using

datestamps/res
umption tokens.
A RSS/Atom Preprints, Poll into an
ingestion MCP government append-only

Preprints,
government
releases,
procurement
notices,
disaster/news
feeds and

Poll into an
append-only
local event
table; retain
GUID,
publication/upda
te times, feed

Sources
unlocked

Sources Recommended
unlocked behavior

targeted URL and
publications; original XML.
TED explicitly
provides RSS
and USGS
provides
Atom/RSS
alongside APIs.

[[9]](https://ted.europa.eu/en/sitemap)

Priority

Local capability
to build once

URL and
original XML.

A Bulk-object/dow
nload MCP

OpenAlex
snapshots,
OpenCitations
dumps,
openFDA bulk
archives, EIA
bulk files, ROR
dumps and
many scientific
[datasets. [10]](https://help.openalex.org/access/sync/)

A GraphQL MCP NASA CMR and
any future
GraphQL-based
source. NASA
provides a
dedicated CMR
GraphQL
interface
alongside
[REST. [11]](https://graphql.earthdata.nasa.gov/)

A Browser/Playwri
ght research
MCP

Public sites
where APIs omit
documents,
tables or
emerging
content.

Prefer
immutable
dated
snapshots; hash
every
downloaded
object; query
locally with
DuckDB/Polars.

Introspect
schema,
whitelist query
depth/cost, and
persist the
original
GraphQL
document.

Keep this
separate from
trusted
structured-data
connectors.
Capture HTML
plus
screenshot/WA
RC where
appropriate and
regard webpage
text as
untrusted agent
input.

Local capability Sources Recommended

Priority to build once unlocked behavior

A Local All raw-source Normalize API
analytical-data connectors. payloads into
MCP DuckDB/Parque

Sources
unlocked

Priority

Local capability
to build once

A Local All raw-source Normalize API
analytical-data connectors. payloads into
MCP DuckDB/Parque

t/Postgres and
give EDA
agents
SQL/statistical
tools rather than
forcing LLMs to
reason over
thousands of
JSON records.
B CKAN-family Government Generic
catalog MCP and operations

All raw-source
connectors.

Government
and
humanitarian
open-data
portals that
expose
CKAN-style
catalogs.

Generic
operations
should be
dataset search,
metadata
retrieval,
resource
discovery and
file retrieval
rather than
provider-specific
tools.

B STAC/geospatia
l-catalog MCP

B STAC/geospatia Satellite and Return asset
l-catalog MCP Earth-observatio metadata first;

n systems that download
expose STAC raster/vector
catalogs. assets only

when an
analysis task
actually requires
them.
B Streaming/event Bluesky Do not make an
MCP firehose/Jetstre LLM consume

Satellite and
Earth-observatio
n systems that
expose STAC
catalogs.

Bluesky
firehose/Jetstre
am and future
real-time feeds.

[[12]](https://bsky.network/docs/consuming-the-firehose/)

Do not make an
LLM consume
raw firehoses.
Persist first,
derive
features/alerts
second, expose
aggregated
windows to
agents third.

Local capability Sources Recommended

Priority to build once unlocked behavior

B Persistent-identi DOI, ORCID, Centralize entity
fier resolver ROR, resolution so
MCP PMID/PMCID, individual

Sources
unlocked

Priority

Local capability
to build once

DOI, ORCID,
ROR,
PMID/PMCID,
LEI, patent IDs,
NCT trial IDs,
[CVEs. [13]](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)

Centralize entity
resolution so
individual
research agents
do not
independently
invent duplicate
entities.

B Search-result
evidence cache

Every source. Cache
query→record
mappings and
distinguish
`first_seen`,
```
         provider_publi
```

`shed`,
```
         provider_updat
```

`ed`, and
`retrieved_at` .
This becomes
critical for
longitudinal
horizon scans.

A useful implication is that you could integrate the majority of the table below while
maintaining perhaps ten to fifteen local MCP codebases, rather than maintaining one
hundred provider-specific MCP servers.

# Science, technology, research, health and intellectual property sources

This is probably the most important source family for detecting weak technological
signals. No single scholarly database is sufficient: OpenAlex is unusually broad;
Crossref and DataCite provide authoritative DOI metadata; Semantic Scholar and
OpenCitations strengthen citation-graph traversal; Europe PMC/NCBI provide
biomedical depth; preprint systems increase timeliness; patent systems reveal
[potential commercialization well before many products appear. [14]](https://help.openalex.org/api/)

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|A|OpenAlex <br>API|Broad<br>discovery<br>across<br>works,<br>authors,|REST/API|Custom or <br>generic <br>REST <br>MCP|Current<br>access is<br>metered;<br>use an<br>API key|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||institution<br>s, sources<br>and<br>research<br>topics;<br>excellent<br>"first-pass<br>" scientific<br>landscape<br>graph.<br>[15]|||and cache<br>aggressiv<br>ely.[16]|
|A|OpenAlex <br>full <br>snapshot|Enables<br>local<br>bibliometri<br>cs,<br>topic-grow<br>th<br>calculatio<br>ns,<br>citation-ne<br>twork<br>mining<br>and<br>reproduci<br>ble<br>historical<br>scans<br>without<br>repeated<br>API calls.|Bulk<br>snapshot|Bulk/local <br>mirror|OpenAlex<br>metadata<br>and its full<br>snapshot<br>are<br>openly<br>download<br>able;<br>particularl<br>y <br>attractive<br>for your<br>local EDA<br>layer.[17]|
|A|OpenAlex <br>full-text <br>service|Allows<br>retrieval<br>of<br>available<br>article<br>PDF/struc<br>tured text,<br>giving<br>deep-rese<br>arch<br>agents<br>evidence|API/file<br>retrieval|Custom<br>MCP|Availabilit<br>y depends<br>on the<br>underlying<br>work;<br>OpenAlex<br>exposes<br>cached<br>full-text<br>content<br>with API<br>limits.[18]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||beyond<br>abstracts.||||
|B|OpenAlex <br>semantic <br>search|Useful for<br>weak-sign<br>al<br>discovery<br>where<br>terminolo<br>gy has not<br>stabilized<br>and<br>keyword<br>search<br>misses<br>semantica<br>lly related<br>work.|Semantic<br>API|Same<br>OpenAlex<br>MCP|Current<br>semantic<br>search<br>has<br>tighter<br>result/rate<br>limits than<br>ordinary<br>graph<br>queries,<br>so use it<br>as a<br>discovery<br>tool rather<br>than<br>corpus<br>export.<br>[19]|
|A|Crossref <br>REST API|Authoritati<br>ve DOI<br>metadata;<br>titles,<br>authors,<br>funders,<br>licenses,<br>updates,<br>reference<br>s and<br>other<br>publicatio<br>n <br>metadata<br>are<br>valuable<br>for<br>provenan<br>ce and<br>entity<br>reconciliat<br>ion.[20]|Public<br>REST|Generic <br>REST <br>MCP|Public<br>access<br>requires<br>no<br>conventio<br>nal<br>subscripti<br>on;<br>Crossref<br>recomme<br>nds<br>identificati<br>on/polite<br>usage.<br>[21]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|A|DataCite <br>REST API|DOI<br>metadata<br>particularl<br>y useful<br>for<br>datasets,<br>software<br>and<br>non-journ<br>al<br>research<br>outputs,<br>compleme<br>nting<br>Crossref.|REST|Generic<br>REST<br>MCP|Public<br>read/quer<br>y access<br>is<br>available<br>without<br>authentica<br>tion; write<br>operation<br>s are for<br>DataCite<br>members.<br>[22]|
|B|DataCite <br>GraphQL|Useful for<br>relationshi<br>p-heavy<br>queries<br>spanning<br>research<br>outputs<br>and<br>persistent<br>identifiers.|GraphQL|Generic<br>GraphQL<br>MCP|Can sit<br>behind<br>the same<br>provenan<br>ce<br>envelope<br>as the<br>REST<br>connector.<br>[23]|
|B|DataCite <br>OAI-PMH|Efficient<br>scheduled<br>metadata<br>harvesting<br>into a<br>local<br>research<br>lake.|OAI-PMH|Generic <br>OAI-PMH <br>MCP|Better<br>suited to<br>bulk/incre<br>mental<br>ingestion<br>than<br>interactive<br>research.<br>[23]|
|A|arXiv API|Extremely<br>valuable<br>early<br>signal for<br>physics,<br>mathemat<br>ics,<br>computer<br>science,|Atom/API|REST/Ato<br>m MCP|Prefer the<br>supported<br>API rather<br>than<br>scraping<br>the<br>website.<br>[24]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||quantitativ<br>e biology,<br>statistics<br>and<br>adjacent<br>disciplines<br>.||||
|A|arXiv <br>OAI-PMH|Efficient<br>daily/incre<br>mental<br>metadata<br>harvesting<br>for local<br>trend<br>detection<br>and topic<br>clustering.|OAI-PMH|Generic<br>OAI-PMH<br>MCP|arXiv<br>identifies<br>OAI-PMH<br>as the<br>preferable<br>bulk-meta<br>data<br>route,<br>while its<br>API is<br>useful for<br>interactive<br>searches.<br>[25]|
|B|arXiv <br>article <br>content|Deep<br>reading of<br>preprints<br>can reveal<br>technique<br>s before<br>journal<br>publicatio<br>n.|Document<br>retrieval|Document<br>acquisitio<br>n pipeline|Do not<br>treat<br>"publicly<br>viewable"<br>as<br>unrestrict<br>ed<br>redistributi<br>on; arXiv<br>specificall<br>y notes<br>copyright/l<br>icense<br>considerat<br>ions<br>around<br>e-print<br>storage<br>and<br>serving.<br>[26]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|A|Europe <br>PMC <br>REST|Strong<br>biomedica<br>l/life-scien<br>ce<br>literature<br>search<br>with richer<br>biomedica<br>l linking<br>than<br>general-p<br>urpose<br>scholarly<br>indexes.|REST|Generic<br>REST<br>MCP|Europe<br>PMC<br>exposes<br>publicatio<br>ns and<br>related<br>informatio<br>n <br>programm<br>atically.<br>[27]|
|A|Europe <br>PMC <br>open-acc<br>ess full <br>text|Deep-rea<br>ding<br>substrate<br>for<br>biomedica<br>l horizon<br>scanning.|API/downl<br>oad|Same<br>Europe<br>PMC<br>MCP|Use OA<br>status and<br>source<br>rights in<br>the<br>evidence<br>record.<br>Europe<br>PMC<br>provides<br>developer<br>access to<br>OA full<br>text.[28]|
|B|Europe <br>PMC <br>annotatio<br>ns|Entity-lev<br>el signals<br>such as<br>genes,<br>diseases<br>and other<br>biomedica<br>l <br>annotatio<br>ns can<br>feed<br>knowledg<br>e-graph<br>constructi<br>on.|API|Same<br>MCP|Particularl<br>y useful<br>before<br>invoking<br>expensive<br>LLM<br>extraction.<br>[28]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|A|Semantic <br>Scholar <br>Academic <br>Graph <br>API|Paper/aut<br>hor<br>discovery<br>plus<br>citation<br>and<br>reference<br>traversal;<br>useful as<br>an<br>independ<br>ent<br>ranking/re<br>commend<br>ation view<br>over<br>science.|REST|Custom/g<br>eneric<br>REST<br>MCP|Strong<br>compleme<br>nt to<br>OpenAlex<br>rather<br>than<br>replacem<br>ent.[29]|
|A|Semantic <br>Scholar <br>datasets|Full-corpu<br>s-oriented<br>research<br>and<br>large-scal<br>e <br>science-of<br>-science<br>analysis.|Dataset<br>download<br>s|Bulk/local<br>mirror|Better for<br>longitudin<br>al<br>analytics<br>than<br>repeatedl<br>y <br>traversing<br>the live<br>API.[30]|
|A|OpenCitat<br>ions <br>REST API|Open<br>citation<br>relationshi<br>ps and<br>citation<br>counts;<br>useful for<br>influence/<br>accelerati<br>on signals<br>without<br>relying<br>entirely on<br>proprietar<br>y|REST|Generic<br>REST<br>MCP|Supports<br>identifiers<br>including<br>DOI/PMID<br>/OMID<br>and<br>structured<br>outputs.<br>[31]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||bibliometri<br>cs.||||
|A|OpenCitat<br>ions <br>SPARQL|Graph-nat<br>ive<br>traversal<br>and<br>cross-linki<br>ng of<br>scholarly<br>entities.|SPARQL|Generic <br>SPARQL <br>MCP|Ideal<br>candidate<br>for a<br>common<br>RDF layer<br>shared<br>with EU<br>legal/publi<br>cation<br>graphs.<br>[32]|
|A|OpenCitat<br>ions bulk <br>dumps|Locally<br>compute<br>citation<br>centrality,<br>burst<br>detection,<br>emerging<br>clusters<br>and<br>research<br>fronts.|Bulk<br>dumps|Bulk/local<br>mirror|OpenCitat<br>ions<br>makes<br>dumps<br>available<br>and<br>publishes<br>its data<br>openly,<br>including<br>CC0<br>material.<br>[33]|
|B|CORE|Aggregate<br>d <br>repository<br>metadata/<br>full text<br>can fill<br>OA-text<br>gaps left<br>by<br>DOI-centri<br>c sources.|API|Custom<br>REST<br>MCP|CORE<br>states that<br>it collects,<br>harmoniz<br>es and<br>enriches<br>metadata<br>and full<br>text from<br>many<br>providers.<br>[34]|
|A|OpenAIR<br>E Graph|Valuable<br>meta-grap<br>h linking<br>publicatio|Public<br>Graph<br>API + bulk|Custom<br>MCP /<br>local<br>mirror|Particularl<br>y useful<br>for<br>funding→|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||ns,<br>datasets,<br>software,<br>organizati<br>ons,<br>projects,<br>funders<br>and<br>repositori<br>es.|||project→o<br>utput <br>lineage<br>and for<br>reducing<br>the<br>number of<br>repository<br>-specific<br>integratio<br>ns.[35]|
|B|Zenodo|Research<br>outputs,<br>datasets,<br>software<br>releases<br>and<br>grey/open<br>-science<br>artifacts<br>not<br>necessaril<br>y <br>prominent<br>in journal<br>indexes.|Repositor<br>y target|Integrate<br>directly or<br>initially<br>through<br>OpenAIR<br>E|OpenAIR<br>E <br>explicitly<br>ingests<br>Zenodo<br>into its<br>research<br>graph, so<br>OpenAIR<br>E can<br>provide a<br>first-stage<br>integratio<br>n before a<br>dedicated<br>connector.<br>[35]|
|B|Figshare|Research<br>datasets<br>and<br>suppleme<br>ntary<br>outputs<br>useful for<br>identifying<br>emerging<br>experime<br>ntal<br>activity.|Repositor<br>y target|Direct<br>connector<br>later;<br>OpenAIR<br>E initially|Figshare<br>is among<br>repositori<br>es<br>aggregate<br>d into<br>OpenAIR<br>E.[35]|
|B|Dryad|Published<br>research<br>datasets;|Repositor<br>y target|Direct<br>connector<br>later;|Also<br>represent<br>ed in the|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||useful for<br>identifying<br>data<br>releases<br>and<br>replicable<br>experime<br>ntal work.||OpenAIR<br>E initially|OpenAIR<br>E <br>aggregati<br>on<br>ecosyste<br>m.[35]|
|B|RePEc|Economic<br>s working<br>papers<br>and<br>research<br>outputs;<br>helpful for<br>policy/eco<br>nomic<br>signals<br>that<br>predate<br>journal<br>publicatio<br>n.|Repositor<br>y target|Specialize<br>d <br>harvester<br>or<br>OpenAIR<br>E|OpenAIR<br>E lists<br>RePEc<br>among<br>prominent<br>sources in<br>its graph.<br>[35]|
|B|DOAJ|Open-acc<br>ess<br>journal/so<br>urce<br>discovery<br>and<br>journal<br>metadata.|Metadata<br>source|Direct<br>later or<br>OpenAIR<br>E|OpenAIR<br>E <br>identifies<br>DOAJ as<br>an input<br>source.<br>[35]|
|B|OpenDOA<br>R|Repositor<br>y <br>discovery<br>rather<br>than<br>primary<br>evidence;<br>useful for<br>finding<br>additional<br>institution|Directory/<br>catalog|Discovery<br>tool|OpenAIR<br>E uses<br>repository<br>registries<br>including<br>OpenDOA<br>R.[35]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||al data<br>silos.||||
|B|re3data|Registry<br>of<br>research-<br>data<br>repositori<br>es;<br>excellent<br>"source<br>discovery<br>source"<br>for<br>recursivel<br>y <br>expanding<br>the<br>system.|Registry/c<br>atalog|Schedule<br>d catalog<br>harvest|OpenAIR<br>E uses<br>re3data<br>among its<br>registered<br>source<br>catalogs.<br>[35]|
|B|FAIRshari<br>ng|Discovery<br>of<br>databases<br>, <br>standards<br>and data<br>policies--<br>particularl<br>y useful<br>for<br>specialist<br>sub-agent<br>s trying to<br>locate<br>domain-s<br>pecific<br>sources.|Registry/c<br>atalog|Research-<br>source<br>discovery<br>MCP|Included<br>among<br>source<br>registries<br>feeding<br>OpenAIR<br>E.[35]|
|A|ORCID <br>Public API|Research<br>er identity<br>resolution,<br>affiliations<br>and links<br>to<br>outputs;<br>prevents|Public API|Persistent<br>-identifier<br>MCP|ORCID<br>operates<br>both<br>Public<br>and<br>Member<br>APIs and<br>publishes|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||entity<br>fragmenta<br>tion<br>across<br>literature<br>sources.|||annual<br>data<br>resources<br>. [36]|
|A|ROR API|Open<br>persistent<br>identifiers<br>and<br>metadata<br>for<br>research/f<br>unding<br>organizati<br>ons--very<br>useful for<br>institution-<br>level<br>technolog<br>y and<br>funding<br>signals.|REST|PID/REST<br>MCP|ROR data<br>are CC0,<br>openly<br>available<br>by REST<br>and<br>dump,<br>and<br>communit<br>y-curated.<br>[37]|
|A|ROR bulk <br>dataset|Local<br>institution<br>reconciliat<br>ion<br>without<br>API calls.|JSON/CS<br>V dump|Bulk/local<br>mirror|Updates<br>are<br>released<br>regularly;<br>v2 is the<br>current<br>stable<br>family<br>after v1<br>was<br>sunset.<br>[38]|
|B|Unpaywall|Determine<br>s whether<br>scholarly<br>works<br>have<br>openly<br>accessibl<br>e versions|REST +<br>snapshot|Resolver<br>MCP|The<br>REST API<br>remains<br>available;<br>in the<br>current<br>architectu<br>re|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||and<br>where<br>they can<br>be<br>retrieved.|||Unpaywall<br>OA facts<br>are<br>powered<br>by the<br>same<br>underlying<br>pipeline<br>as<br>OpenAlex<br>. [39]|
|A|PubMed / <br>NCBI <br>E-utilities|Canonical<br>biomedica<br>l <br>publicatio<br>n indexing<br>and<br>MeSH-dri<br>ven<br>retrieval.|NCBI<br>E-utilities|Custom<br>NCBI<br>MCP|A mature<br>integratio<br>n target;<br>BioMCP,<br>for<br>example,<br>already<br>federates<br>PubMed<br>E-utilities<br>with other<br>biomedica<br>l systems.<br>[40]|
|A|PubMed <br>Central <br>open-acc<br>ess <br>corpus|Biomedic<br>al full text<br>suitable<br>for deep<br>evidence<br>extraction.|OA<br>files/API<br>pathways|Local<br>document<br>mirror /<br>NCBI<br>MCP|BioMCP<br>demonstr<br>ates a<br>practical<br>resolver<br>chain<br>using<br>PMC OA<br>resources<br>, NCBI<br>identifiers<br>and<br>Europe<br>PMC.[41]|
|B|PubTator3|Precompu<br>ted<br>biomedica<br>l entity|API|Biomedic<br>al MCP|Can be<br>combined<br>with<br>PubMed/|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||annotatio<br>ns over<br>literature;<br>excellent<br>for cheap<br>first-stage<br>knowledg<br>e <br>extraction.|||Europe<br>PMC<br>before<br>LLM-base<br>d relation<br>extraction.<br>[41]|
|A|NHGRI-E<br>BI GWAS <br>Catalog|Gene/vari<br>ant-trait<br>associatio<br>ns and<br>GWAS<br>summary-<br>statistic<br>discovery;<br>strong<br>biotechnol<br>ogy and<br>precision-<br>health<br>signal<br>source.|API +<br>download<br>s|Biomedic<br>al REST<br>MCP|Curated<br>by NHGRI<br>and<br>EMBL-EB<br>I; site<br>provides<br>download<br>s and API<br>document<br>ation.[42]|
|A|Open <br>Targets <br>Platform|Integrates<br>diverse<br>evidence<br>around<br>target-dis<br>ease<br>associatio<br>ns and<br>drug<br>discovery;<br>high-value<br>signal for<br>pharma/bi<br>otech<br>horizons.|Program<br>matic<br>platform|Custom<br>biomedica<br>l MCP|Preserve<br>each<br>underlying<br>evidence<br>source<br>rather<br>than<br>attributing<br>a <br>synthesiz<br>ed Open<br>Targets<br>score to a<br>single<br>experime<br>nt.[43]|
|A|ClinicalTri<br>als.gov <br>API|Trial<br>starts,<br>phases,|API v2|Custom <br>REST <br>MCP|Treat<br>registry<br>updates|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||interventio<br>ns,<br>sponsors,<br>outcomes<br>and status<br>changes<br>--often<br>more<br>commerci<br>ally<br>informativ<br>e than<br>publicatio<br>ns alone.|||as<br>time-serie<br>s events;<br>a <br>changed<br>status can<br>itself be a<br>signal.<br>[44]|
|A|openFDA|Drugs,<br>devices,<br>adverse-e<br>vent<br>reports,<br>recalls<br>and other<br>FDA<br>datasets;<br>powerful<br>safety/reg<br>ulatory<br>signal.|REST +<br>bulk<br>JSON|Custom<br>REST<br>MCP +<br>mirror|Bulk<br>download<br>s are<br>available.<br>Some<br>reporting<br>datasets<br>have<br>publicatio<br>n lag, so<br>model<br>event<br>date<br>separately<br>from<br>ingestion<br>date.[45]|
|A|ChEMBL|Compoun<br>ds,<br>assays,<br>targets<br>and<br>bioactivity<br>informatio<br>n for<br>pharmace<br>utical/biot<br>echnology<br>scanning.|REST<br>web<br>services|Biomedic<br>al REST<br>MCP|Excellent<br>machine-r<br>eadable<br>compleme<br>nt to<br>papers<br>and trials.<br>[46]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|A|UniProt|Protein<br>sequence<br>s, function<br>and<br>annotatio<br>n; central<br>source for<br>molecular<br>biology/bi<br>otech<br>sub-agent<br>s.|Multiple<br>APIs/dow<br>nloads|Biomedic<br>al API<br>MCP|UniProt<br>officially<br>exposes<br>multiple<br>programm<br>atic<br>interfaces.<br>[47]|
|B|Ensembl|Genome<br>and<br>gene/tran<br>script<br>annotatio<br>n across<br>many<br>species;<br>useful<br>when<br>horizon<br>scans<br>enter<br>genomics<br>or<br>synthetic<br>biology.|Program<br>matic<br>ecosyste<br>m/downlo<br>ads|Specialist<br>genomics<br>connector|Current<br>Ensembl<br>provides<br>large-scal<br>e genome<br>and<br>annotatio<br>n <br>resources<br>. [48]|
|A|USPTO <br>Open <br>Data <br>Portal|U.S.<br>patent<br>applicatio<br>ns, grants<br>and<br>related IP<br>data;<br>essential<br>for<br>technolog<br>y-commer<br>cialization<br>and<br>assignee/i|APIs/bulk|Custom<br>patent<br>MCP|Official<br>USPTO<br>platform;<br>preferable<br>to<br>scraping<br>patent<br>search<br>pages.<br>[49]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||nventor<br>tracking.||||
|A|PatentsVi<br>ew data <br>through <br>USPTO <br>ODP|Research-<br>friendly<br>U.S.<br>patent<br>entities<br>and<br>analytics<br>lineage.|USPTO<br>ODP|Same<br>patent<br>MCP|PatentsVi<br>ew was<br>migrated<br>into the<br>USPTO<br>Open<br>Data<br>Portal in<br>March<br>2026, so<br>new<br>integratio<br>ns should<br>target<br>ODP<br>rather<br>than<br>legacy<br>PatentsVi<br>ew<br>endpoints.<br>[50]|
|A|EPO <br>Open <br>Patent <br>Services|Worldwid<br>e <br>bibliograp<br>hic,<br>legal-statu<br>s and<br>patent-do<br>cument<br>informatio<br>n;<br>broadens<br>IP<br>scanning<br>beyond<br>the United<br>States.|REST/XM<br>L|Custom<br>patent<br>MCP|EPO OPS<br>provides<br>bibliograp<br>hic,<br>worldwide<br>legal-statu<br>s and<br>document<br>/image<br>services<br>programm<br>atically.<br>[51]|

A particularly strong research workflow is therefore OpenAlex → Crossref/DataCite
identity reconciliation → Semantic Scholar/OpenCitations citation expansion →

source-specific full text → patents/trials/domain databases, rather than asking one
literature search service to do everything. That gives both breadth and independent
[corroboration while retaining each provider's identifiers and timestamps. [52]](https://help.openalex.org/api/)

# Economics, trade, companies, labor, procurement and public statistics

For horizon scanning, macroeconomic APIs are not merely background context.
They allow an agent to test whether a narrative emerging from papers/news is visible
in production, prices, trade, employment, public expenditure, procurement or
corporate reporting. The key implementation advantage here is the high prevalence
[of structured statistical standards such as SDMX. [6]](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html)

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|A|World <br>Bank <br>Indicators <br>API|Global<br>developm<br>ent,<br>demograp<br>hics,<br>economy,<br>infrastruct<br>ure,<br>health,<br>education,<br>environm<br>ent and<br>other<br>country-le<br>vel<br>indicators.|REST/API|Generic<br>REST<br>MCP|Nearly<br>16,000<br>time<br>series<br>across a<br>very<br>broad<br>collection<br>make this<br>one of the<br>best<br>baseline<br>sources.<br>[53]|
|A|World <br>Bank <br>Data360 <br>API|Broader<br>data/meta<br>data<br>discovery<br>and<br>download<br>able data<br>assets;<br>useful<br>where<br>conventio<br>nal<br>Indicators<br>coverage<br>is|API/files|World<br>Bank<br>MCP|Data360<br>provides<br>programm<br>atic<br>access to<br>data and<br>metadata<br>resources<br>. [54]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||insufficien<br>t.||||
|B|World <br>Bank <br>Projects / <br>Finances <br>APIs|Developm<br>ent<br>projects,<br>funding<br>flows and<br>institution<br>al<br>investmen<br>t signals.|APIs|World<br>Bank<br>MCP|The<br>Bank's<br>developer<br>resources<br>expose<br>distinct<br>project/fin<br>ancial<br>services<br>beyond<br>indicators.<br>[55]|
|B|World <br>Bank <br>Document<br>s & <br>Reports <br>API|Grey<br>literature,<br>assessme<br>nts,<br>strategy<br>reports<br>and policy<br>research.|Search/ret<br>rieval API|Document<br>-search<br>MCP|Useful for<br>deep<br>research<br>where the<br>structured<br>statistics<br>identify an<br>anomaly<br>that<br>requires<br>explanato<br>ry<br>document<br>ation.[56]|
|A|World <br>Integrated <br>Trade <br>Solution <br>-- WITS|Trade,<br>tariffs and<br>developm<br>ent<br>indicators;<br>valuable<br>for<br>supply-ch<br>ain and<br>trade-poli<br>cy<br>analysis.|API/data<br>services|Trade<br>MCP|Complem<br>ent rather<br>than<br>replace<br>raw<br>Comtrade<br>. [57]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|A|OECD <br>Data <br>Explorer|Cross-cou<br>ntry<br>economic,<br>social,<br>labor,<br>industry,<br>education,<br>innovation<br>and policy<br>statistics.|SDMX <br>API|Generic <br>SDMX <br>MCP|Official<br>API is free<br>but<br>subject to<br>throttling;<br>OECD<br>recomme<br>nds<br>efficient<br>querying/l<br>ocal<br>caching.<br>[58]|
|A|IMF Data|Macroeco<br>nomics,<br>inflation,<br>balance of<br>payments,<br>public<br>finance,<br>internatio<br>nal<br>reserves,<br>labor and<br>IMF<br>forecast<br>series.|SDMX <br>2.1/3.0 <br>APIs|Generic<br>SDMX<br>MCP|Current<br>IMF Data<br>explicitly<br>exposes<br>SDMX<br>APIs and<br>includes<br>forward-lo<br>oking<br>datasets<br>such as<br>WEO<br>projection<br>s.[59]|
|A|UN SDG <br>API|Official<br>Sustainab<br>le<br>Developm<br>ent Goal<br>indicators;<br>valuable<br>for<br>long-horiz<br>on<br>societal<br>and<br>developm<br>ent<br>monitorin<br>g.|API /<br>SDMX|UN<br>statistics<br>connector|Officially<br>reported<br>SDG data<br>and<br>metadata<br>can be<br>accessed<br>programm<br>atically.<br>[60]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|A|UN <br>Comtrade|Official<br>bilateral<br>merchand<br>ise-trade<br>flows by<br>reporter,<br>partner,<br>commodit<br>y and<br>direction.|API|Trade<br>MCP|Free<br>registratio<br>n <br>currently<br>supports<br>substantia<br>l per-call<br>and daily<br>API<br>allowance<br>s;<br>preserve<br>revision<br>vintage<br>because<br>trade<br>records<br>can be<br>revised.<br>[61]|
|B|WTO <br>Global <br>Trade <br>Data <br>Portal / <br>Data Lab|WTO<br>statistics,<br>tariffs and<br>newer/exp<br>erimental<br>real-time<br>trade<br>signals.|Data<br>services/d<br>ownloads|Trade<br>connector|Useful as<br>both a<br>WTO data<br>source<br>and a<br>directory<br>into<br>compleme<br>ntary<br>public<br>trade<br>resources<br>. [62]|
|A|FAOSTAT|Agricultur<br>e, food,<br>productio<br>n, prices,<br>land use,<br>inputs,<br>trade and<br>food-secu<br>rity<br>indicators|API|Generic<br>REST<br>MCP|FAO<br>operates<br>an API<br>developer<br>portal for<br>FAOSTAT<br>data.[63]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||--critical<br>for<br>bioecono<br>my and<br>food-syste<br>m <br>horizons.||||
|B|UNCTADs<br>tat|Merchand<br>ise trade<br>and<br>broader<br>developm<br>ent/trade<br>indicators<br>from<br>UNCTAD.|Data/dow<br>nload<br>services|UN<br>statistics<br>connector|Particularl<br>y useful<br>as an<br>alternative<br>statistical<br>view for<br>global<br>trade/dev<br>elopment<br>analysis.<br>[64]|
|A|FRED|High-freq<br>uency and<br>long-run<br>U.S./glob<br>al<br>economic<br>time<br>series<br>aggregate<br>d by the<br>St. Louis<br>Fed.|REST API|Economic<br>-data<br>MCP|API<br>supports<br>structured<br>observatio<br>ns in<br>multiple<br>formats.<br>[65]|
|A|ALFRED|Historical<br>vintages<br>of<br>economic<br>series--e<br>xtremely<br>valuable<br>for<br>answering<br>"what<br>informatio<br>n was<br>actually|Same<br>FRED API<br>family|Same<br>MCP|FRED's<br>API family<br>includes<br>ALFRED<br>vintage<br>data,<br>making it<br>unusually<br>good for<br>provenan<br>ce-aware<br>retrospect<br>ive|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||available<br>at the<br>time?"|||horizon<br>scans.<br>[66]|
|A|U.S. <br>Bureau of <br>Labor <br>Statistics|Employm<br>ent,<br>unemploy<br>ment,<br>wages,<br>prices,<br>productivit<br>y and<br>occupatio<br>nal<br>signals.|Public API|Economic<br>REST<br>MCP|BLS<br>exposes<br>JSON-ori<br>ented<br>public API<br>versions<br>with<br>registered<br>/unregiste<br>red usage<br>tiers.[67]|
|A|U.S. <br>Bureau of <br>Economic <br>Analysis|GDP,<br>industries,<br>personal<br>income,<br>trade-relat<br>ed<br>national<br>accounts<br>and<br>regional<br>economic<br>data.|API|Economic<br>REST<br>MCP|Includes<br>both<br>statistics<br>and<br>metadata<br>programm<br>atically.<br>[68]|
|A|U.S. <br>Census <br>Data API|Populatio<br>n,<br>businesse<br>s,<br>demograp<br>hics,<br>housing,<br>trade-relat<br>ed and<br>survey<br>data<br>across<br>many<br>Census<br>products.|APIs|Census<br>MCP|Census<br>has<br>numerous<br>programm<br>atic<br>datasets;<br>since<br>August<br>2026 API<br>queries<br>require a<br>key, so<br>provision<br>credential<br>s <br>centrally.<br>[69]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|A|European <br>Central <br>Bank <br>Data <br>Portal|Monetary,<br>financial,<br>banking,<br>exchange<br>-rate and<br>Euro-area<br>macroeco<br>nomic<br>statistics.|SDMX 2.1 <br>REST|Generic<br>SDMX<br>MCP|The same<br>SDMX<br>layer can<br>be reused<br>for<br>OECD/IM<br>F/ABS.<br>[70]|
|A|Australian <br>Bureau of <br>Statistics <br>Data API|Critical<br>Australian<br>demograp<br>hic,<br>economic,<br>labor,<br>business<br>and social<br>statistics.|SDMX <br>2.1, <br>JSON/XM<br>L/CSV|Generic<br>SDMX<br>MCP|Particularl<br>y high<br>priority<br>given your<br>likely<br>Australian<br>operating<br>context;<br>ABS's<br>Data API<br>is<br>designed<br>for<br>programm<br>atic<br>discovery/<br>retrieval.<br>[71]|
|A|Reserve <br>Bank of <br>Australia <br>statistical <br>tables|Australian<br>monetary,<br>financial,<br>credit,<br>exchange<br>-rate and<br>economic<br>series.|Tables/do<br>wnload<br>files|File<br>harvester<br>or<br>specialize<br>d wrapper|I did not<br>identify an<br>official<br>RBA API<br>during this<br>scan;<br>ingest<br>published<br>statistical<br>files, or<br>use an<br>intermedi<br>ary only<br>while<br>preservin<br>g RBA as|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
||||||the<br>ultimate<br>provenan<br>ce.[72]|
|A|api.gov.au|Discovery<br>layer for<br>Australian<br>Common<br>wealth/sta<br>te/territory<br>governme<br>nt APIs.|API<br>catalog|Source-di<br>scovery <br>connector|Especially<br>useful<br>because<br>your<br>research<br>system<br>can<br>periodicall<br>y discover<br>newly<br>published<br>Australian<br>governme<br>nt APIs<br>instead of<br>hard-codi<br>ng a static<br>list.[73]|
|B|API.NSW|NSW<br>governme<br>nt<br>services<br>and<br>datasets,<br>including<br>live/operat<br>ional<br>sources<br>such as<br>fuel-price<br>and<br>regulatory<br>registers.|API<br>catalog/A<br>PIs|Generic<br>REST<br>MCP|A useful<br>state-level<br>source-dis<br>covery<br>target.<br>[74]|
|A|AusTende<br>r|Australian<br>Common<br>wealth<br>procurem<br>ent<br>opportunit|Portal/dat<br>a|Procurem<br>ent<br>connector|AusTende<br>r is the<br>Australian<br>Governm<br>ent's<br>centralize|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||ies,<br>planned<br>procurem<br>ents and<br>awarded<br>contracts<br>--a<br>powerful<br>early<br>indicator<br>of<br>governme<br>nt<br>priorities<br>and<br>capability<br>acquisitio<br>n.|||d <br>procurem<br>ent<br>informatio<br>n system.<br>[75]|
|A|AusTende<br>r OCDS <br>data/API|Structured<br>contract<br>data<br>suitable<br>for trend<br>analysis,<br>supplier<br>graphs<br>and<br>category-l<br>evel<br>spending<br>signals.|REST/OC<br>DS|OCDS/RE<br>ST MCP|Open<br>Contractin<br>g-style<br>structure<br>is far<br>easier to<br>analyze<br>than<br>rendered<br>procurem<br>ent<br>pages.<br>[76]|
|A|SEC <br>EDGAR <br>public <br>data APIs|Corporate<br>filings,<br>company<br>submissio<br>ns and<br>XBRL<br>financial<br>facts;<br>essential<br>for<br>commerci<br>alization,|REST/JS<br>ON|SEC MCP|SEC<br>exposes<br>submissio<br>ns and<br>extracted<br>XBRL<br>through<br>public<br>APIs;<br>observe<br>its<br>automate|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||investmen<br>t and<br>corporate-<br>strategy<br>signals.|||d-access/f<br>air-access<br>policy.<br>[77]|
|B|SEC <br>EDGAR <br>daily/quart<br>erly <br>indexes|Efficient<br>discovery<br>of new<br>filings<br>without<br>broad<br>repeated<br>API<br>searches.|Bulk<br>indexes|Local<br>event<br>ingestion|SEC<br>provides<br>indexes in<br>formats<br>including<br>JSON/XM<br>L, making<br>them ideal<br>scheduled<br>-ingestion<br>feeds.<br>[78]|
|A|GLEIF <br>Global <br>LEI Index|Global<br>legal-entit<br>y identity<br>and<br>relationshi<br>p data;<br>excellent<br>entity-res<br>olution<br>substrate<br>for<br>company,<br>procurem<br>ent and<br>financial<br>datasets.|REST API<br>+ files|Entity-res<br>olution <br>MCP|GLEIF's<br>API<br>supports<br>searches,<br>filters,<br>fuzzy<br>matching<br>and<br>ownership<br>-related<br>data.[79]|
|A|USAspen<br>ding.gov|U.S.<br>federal<br>contracts,<br>grants,<br>loans and<br>other<br>awards--<br>excellent<br>funding/d|Public<br>REST API|USAspen<br>ding MCP|The API<br>currently<br>requires<br>no<br>authorizati<br>on and<br>exposes<br>comprehe<br>nsive<br>federal|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||emand<br>signal.|||spending<br>data.[80]|
|A|SAM.gov <br>Contract <br>Opportuni<br>ties|Pre-solicit<br>ation,<br>solicitatio<br>n, award<br>and<br>sole-sourc<br>e <br>notices--<br>often a<br>much<br>earlier<br>technolog<br>y/demand<br>signal<br>than final<br>spending<br>records.|Public<br>API/portal|SAM<br>procurem<br>ent MCP|Separate<br>public and<br>sensitive<br>APIs<br>carefully;<br>public-faci<br>ng data<br>should<br>use public<br>API<br>variants.<br>[81]|
|A|SAM.gov <br>contract <br>data|U.S.<br>federal<br>contract-a<br>ward<br>analysis<br>and<br>download<br>able<br>contractin<br>g <br>datasets.|APIs/dow<br>nloads|Same<br>procurem<br>ent MCP|SAM<br>points<br>developer<br>s to<br>contractin<br>g-data<br>APIs and<br>bulk/repor<br>ting<br>facilities.<br>[82]|
|B|SAM.gov <br>subaward/<br>subcontra<br>ct data|Supply-ch<br>ain and<br>downstrea<br>m-recipie<br>nt<br>relationshi<br>ps that<br>primary<br>award<br>data can<br>conceal.|Public<br>APIs|Same<br>MCP|SAM<br>states that<br>public<br>subaward<br>and<br>subcontra<br>ct APIs<br>exist for<br>large data<br>download<br>s.[83]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|A|EU <br>Tenders <br>Electronic <br>Daily <br>Search <br>API|EU public<br>procurem<br>ent<br>notices--<br>excellent<br>technolog<br>y-demand<br>and<br>policy-imp<br>lementatio<br>n signal<br>across<br>Europe.|Search<br>API/XML|Procurem<br>ent MCP|The<br>search<br>API<br>allows<br>published<br>notice<br>retrieval<br>and bulk<br>XML and<br>is<br>available<br>without<br>authentica<br>tion for<br>reuse.<br>[84]|
|A|TED <br>Open <br>Data <br>Service / <br>knowledg<br>e graph|Procurem<br>ent as<br>linked<br>open data<br>enables<br>buyer-su<br>pplier-pla<br>ce-catego<br>ry network<br>analysis.|Linked<br>Open<br>Data|SPARQL/<br>RDF MCP|TED<br>publishes<br>procurem<br>ent<br>informatio<br>n as a<br>reusable<br>knowledg<br>e graph.<br>[85]|
|B|TED RSS <br>feeds|Near-real-<br>time<br>watchlists<br>for<br>procurem<br>ent<br>categories<br>, <br>organizati<br>ons and<br>geographi<br>es.|RSS|Generic<br>feed MCP|TED<br>explicitly<br>exposes<br>RSS<br>alongside<br>APIs and<br>bulk<br>download<br>facilities.<br>[86]|
|A|Our World <br>in Data <br>datasets|Curated<br>cross-do<br>main<br>indicators<br>useful for|CSV/dow<br>nload<br>package|File<br>ingestion|OWID<br>provides<br>reusable<br>download<br>able data|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Access /<br>provenan<br>ce<br>caveats|
|---|---|---|---|---|---|
|||quickly<br>contextual<br>izing<br>signals<br>across<br>demograp<br>hics,<br>climate,<br>health,<br>technolog<br>y and<br>developm<br>ent.|||packages;<br>preserve<br>OWID's<br>original-so<br>urce<br>metadata<br>so it is not<br>mistakenl<br>y treated<br>as the<br>primary<br>producer<br>of every<br>indicator.<br>[87]|
|A|WHO <br>Global <br>Health <br>Observato<br>ry|Global<br>public-hea<br>lth<br>indicators<br>across<br>WHO<br>member<br>states;<br>critical<br>baseline<br>for health,<br>disease<br>and<br>demograp<br>hic<br>horizons.|Structured<br>data<br>repository|WHO<br>connector|WHO<br>describes<br>GHO as<br>its<br>gateway<br>to health<br>statistics<br>spanning<br>a very<br>large<br>indicator<br>set.[88]|

One point worth emphasizing is ALFRED-style vintage preservation. For a real
horizon-scanning system, the question is often not merely "what is
GDP/inflation/trade today?" but "what did the data appear to show when the weak
signal was detected?" Wherever providers expose revisions or vintages, store them
rather than overwriting previous observations. FRED/ALFRED is particularly useful in
[this regard. [66]](https://fred.stlouisfed.org/docs/api/fred/overview.html)

# Government, law, regulation, security and humanitarian sources

Regulation and procurement should be first-class signal streams rather than
supplementary search results. Proposed rules, parliamentary material, official

publications, contracting notices and regulatory consultations can precede actual
market change by months or years. The U.S. GovInfo development is especially
notable for your architecture because it is one of the relatively rare cases where a

|public autho [89]|ority now pro|ovides both a|conventiona|al API and an|n official MCP|
|---|---|---|---|---|---|
|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|A|GovInfo <br>official <br>MCP <br>server|U.S.<br>official<br>governme<br>nt<br>publicatio<br>ns<br>spanning<br>legislative<br>and other<br>federal<br>material,<br>directly<br>exposed<br>to AI<br>clients.|Official <br>MCP -- <br>public <br>preview|Provider<br>MCP, or<br>proxy<br>through<br>your local<br>MCP<br>gateway|GPO<br>announce<br>d the<br>public<br>preview in<br>January<br>2026.<br>Because<br>it is<br>preview-st<br>age,<br>retain the<br>conventio<br>nal API as<br>a fallback.<br>[90]|
|A|GovInfo <br>API|Official<br>U.S.<br>governme<br>nt<br>publicatio<br>ns and<br>metadata<br>from all<br>three<br>branches.|REST API|Local<br>GovInfo<br>wrapper|Mature<br>fallback/pr<br>imary<br>ingestion<br>mechanis<br>m;<br>requires a<br>free<br>api.data.g<br>ov key for<br>relevant<br>endpoints.<br>[91]|
|A|FederalR<br>egister.go<br>v API|Proposed/<br>final rules,<br>notices,<br>executive<br>material<br>and<br>regulatory<br>actions;<br>excellent|JSON/CS<br>V API|Regulator<br>y MCP|Program<br>matic<br>access<br>should<br>use the<br>developer<br>APIs<br>rather<br>than|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|||forward-lo<br>oking<br>policy<br>signal.|||scraping;<br>API<br>coverage<br>includes<br>Federal<br>Register<br>document<br>s back to<br>1994.[92]|
|A|Federal <br>Register <br>bulk data|Reproduci<br>ble local<br>corpus for<br>regulatory<br>-text<br>analytics<br>and<br>historical<br>trend<br>extraction.|Bulk +<br>API|Local<br>mirror|Useful for<br>language-<br>model<br>extraction<br>of<br>regulatory<br>themes<br>while<br>preservin<br>g official<br>document<br>IDs.[93]|
|A|Regulatio<br>ns.gov <br>API|U.S.<br>regulatory<br>dockets,<br>supportin<br>g <br>document<br>s and<br>public<br>comments<br>--useful<br>for<br>identifying<br>contested/<br>emerging<br>technologi<br>es and<br>stakehold<br>er<br>positions.|Official<br>API|Regulator<br>y MCP|Use<br>docket/do<br>cument/co<br>mment<br>IDs as<br>immutable<br>provenan<br>ce<br>anchors.<br>[94]|
|A|Congress.<br>gov API|U.S. bills,<br>legislative<br>activity<br>and|Official<br>API|Legislativ<br>e MCP|Public API<br>access is<br>provided<br>with an|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|||congressi<br>onal data.|||api.data.g<br>ov key.<br>[95]|
|A|EUR-Lex / <br>EU Cellar|EU law,<br>proposals,<br>official<br>publicatio<br>ns and<br>rich<br>document<br>relationshi<br>ps.|SPARQL <br>+ REST|Generic<br>SPARQL<br>MCP plus<br>document<br>fetcher|Cellar<br>exposes<br>metadata<br>through<br>SPARQL<br>and<br>document<br>/metadata<br>retrieval<br>through<br>REST,<br>making it<br>exception<br>ally<br>agent-frie<br>ndly.[96]|
|A|UK <br>Legislatio<br>n service|UK<br>primary/s<br>econdary<br>legislation<br>and<br>associate<br>d <br>legislative<br>data.|Legislatio<br>n <br>API/data|UK<br>legislation<br>MCP|Official<br>developer<br>pages<br>document<br>API<br>limitations<br>; encode<br>version/st<br>atus<br>informatio<br>n in<br>provenan<br>ce.[97]|
|A|NIST <br>National <br>Vulnerabil<br>ity <br>Database|CVE<br>enrichme<br>nt,<br>vulnerabili<br>ty<br>severity/c<br>onfigurati<br>on data<br>and<br>software-s<br>ecurity<br>trends.|NVD API|Cyber<br>MCP|NIST<br>provides<br>official<br>API<br>access<br>and<br>API-key<br>mechanis<br>ms.[98]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|A|CISA <br>Known <br>Exploited <br>Vulnerabil<br>ities <br>Catalog|Distinguis<br>hes<br>merely<br>disclosed<br>vulnerabili<br>ties from<br>those<br>known to<br>be<br>actively<br>exploited;<br>unusually<br>strong<br>operation<br>al cyber<br>signal.|JSON/CS<br>V|Local<br>cyber<br>feed|CISA<br>maintains<br>machine-r<br>eadable<br>KEV data;<br>treat<br>catalog<br>addition<br>date as its<br>own<br>horizon-sc<br>an event.<br>[99]|
|A|OSV|Unified<br>open-sour<br>ce<br>package<br>vulnerabili<br>ty<br>informatio<br>n across<br>ecosyste<br>ms.|API/sche<br>ma|Cyber<br>MCP|Very<br>useful for<br>mapping<br>vulnerabili<br>ty<br>disclosure<br>s onto<br>package/d<br>ependenc<br>y <br>ecosyste<br>ms.[100]|
|A|FIRST <br>EPSS|Probabilis<br>tic<br>exploit-lik<br>elihood<br>signal,<br>useful for<br>prioritizing<br>CVEs<br>rather<br>than<br>treating<br>every<br>disclosure<br>equally.|Public API<br>+ <br>daily/histo<br>rical data|Cyber<br>MCP/local<br>time<br>series|Keep<br>model<br>date/versi<br>on with<br>every<br>score; the<br>probability<br>is<br>time-depe<br>ndent.<br>[101]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|A|ReliefWeb <br>API|Humanitar<br>ian<br>reports,<br>disasters,<br>countries,<br>organizati<br>ons and<br>themes;<br>valuable<br>for<br>geopolitic<br>al,<br>disaster,<br>health<br>and<br>supply-ch<br>ain<br>disruption<br>s.|API|Humanitar<br>ian MCP|ReliefWeb<br>describes<br>the API as<br>a central<br>programm<br>atic<br>channel<br>for timely<br>humanitar<br>ian<br>informatio<br>n.[102]|
|A|HDX <br>HAPI -- <br>Humanitar<br>ian API|Harmoniz<br>ed<br>humanitar<br>ian<br>indicators<br>and<br>contextual<br>data that<br>would<br>otherwise<br>require<br>many<br>separate<br>source<br>integratio<br>ns.|API|Humanitar<br>ian MCP|Particularl<br>y <br>attractive<br>as an<br>aggregati<br>on layer;<br>preserve<br>the<br>original<br>contributin<br>g-source<br>metadata.<br>[103]|
|A|ACLED|Near-real-<br>time<br>political<br>violence,<br>protest<br>and<br>conflict-ev<br>ent data;<br>useful for|Structured<br>data/API<br>ecosyste<br>m|Dedicated<br>conflict<br>connector|ACLED<br>describes<br>itself as a<br>near-real-t<br>ime global<br>political-vi<br>olence/pr<br>otest<br>dataset;|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|||geopolitic<br>al and<br>operation<br>al-risk<br>scanning.|||licensing/<br>access<br>conditions<br>should be<br>represent<br>ed<br>explicitly<br>in your<br>connector<br>metadata.<br>[104]|
|B|UNSD <br>API <br>catalogue|Gateway<br>into<br>multiple<br>official UN<br>statistical<br>services<br>rather<br>than a<br>single<br>dataset.|Multiple<br>APIs|UN<br>meta-con<br>nector|The UN<br>Statistics<br>Division<br>lists<br>services<br>including<br>SDG,<br>Comtrade<br>and other<br>statistical<br>interfaces.<br>[105]|
|B|Indian <br>MoSPI <br>eSankhyik<br>i MCP|Interestin<br>g <br>precedent<br>for direct<br>national-st<br>atistics-to-<br>agent<br>access,<br>initially<br>covering<br>major<br>Indian<br>statistical<br>products.|Official <br>governme<br>nt MCP, <br>beta|Evaluate<br>provider<br>MCP;<br>maintain<br>API<br>fallback|A 2026<br>launch<br>made<br>several<br>major<br>MoSPI<br>statistical<br>collection<br>s <br>available<br>through<br>MCP;<br>treat beta<br>status as<br>operation<br>ally<br>material.<br>[106]|

For the cyber sources, I would derive a joined local object keyed by CVE such as
NVD severity/configuration + CISA KEV active-exploitation status + EPSS exploit

probability + OSV affected packages. That is a substantially stronger horizon signal
[than any one vulnerability feed in isolation. [107]](https://nvd.nist.gov/developers/vulnerabilities)

# Climate, environment, energy, biodiversity and geospatial sources

Environmental horizon scanning benefits enormously from raw numerical sources
because the research system can detect anomalies rather than depending on
someone else to publish a story about them. NASA, NOAA, Copernicus, EIA, USGS,
GBIF and OpenAQ all provide programmatic paths suitable for an analytical
[sub-agent. [108]](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/cmr-api)

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|A|Copernicu<br>s Climate <br>Data <br>Store|Historical,<br>current<br>and<br>modeled<br>future<br>climate;<br>reanalysis<br>and<br>climate-va<br>riable<br>datasets.|CDS API|Climate<br>MCP /<br>bulk<br>download|Program<br>matic<br>access<br>requires<br>account/A<br>PI<br>credential<br>s and<br>acceptanc<br>e of<br>dataset-s<br>pecific<br>terms<br>where<br>applicable<br>. [109]|
|A|Copernicu<br>s ERA5 <br>and <br>related <br>reanalysis <br>products <br>via CDS|Baseline<br>climate/w<br>eather<br>anomaly<br>detection<br>and<br>long-horiz<br>on<br>environm<br>ental<br>trend<br>analysis.|CDS API|Same<br>climate<br>MCP +<br>local<br>arrays|CDS<br>explicitly<br>includes<br>major<br>global/regi<br>onal<br>reanalyse<br>s such as<br>ERA5.<br>[110]|
|A|Copernicu<br>s <br>Atmosphe<br>re Data|Atmosphe<br>ric<br>compositi<br>on/pollutio|Program<br>matic<br>CDS-famil<br>y access|Same<br>MCP|CDS API<br>tooling<br>can<br>address|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
||Store <br>through <br>the CDS <br>API family|n context<br>for<br>climate,<br>health<br>and<br>environm<br>ental<br>scans.|||connected<br>data-store<br>catalogs<br>beyond<br>the core<br>climate<br>store.<br>[111]|
|A|Copernicu<br>s <br>Emergenc<br>y <br>Managem<br>ent <br>early-war<br>ning data <br>through <br>CDS <br>infrastruct<br>ure|Flood/fire/<br>emergenc<br>y-related<br>indicators<br>and<br>early-war<br>ning<br>datasets.|CDS-famil<br>y API|Same<br>MCP|Particularl<br>y suitable<br>for<br>event-trig<br>gered<br>research<br>tasks.<br>[111]|
|A|NOAA <br>Climate <br>Data <br>Online|Global<br>historical<br>station<br>weather<br>and<br>climate<br>measure<br>ments.|REST<br>web<br>services|NOAA<br>MCP|Free<br>archive;<br>token-bas<br>ed API<br>with<br>document<br>ed rate<br>limits.<br>[112]|
|A|NOAA <br>NCEI <br>Access <br>Data <br>Service|Flexible<br>subset/ret<br>rieval of<br>environm<br>ental<br>datasets<br>in<br>structured<br>formats.|REST;<br>CSV/JSO<br>N/NetCDF<br>etc.|NOAA<br>MCP|Not every<br>NCEI<br>dataset is<br>exposed<br>through<br>this<br>particular<br>service,<br>so pair it<br>with NCEI<br>catalog<br>discovery.<br>[113]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|A|NOAA <br>Global <br>Hourly / <br>Integrated <br>Surface <br>Database|High-freq<br>uency<br>global<br>surface<br>weather<br>observatio<br>ns;<br>valuable<br>for<br>supply-ch<br>ain,<br>infrastruct<br>ure and<br>climate<br>anomaly<br>analyses.|Bulk/data<br>access|Local<br>mirror|Aggregate<br>s <br>observatio<br>ns from a<br>very large<br>internatio<br>nal station<br>network.<br>[114]|
|A|NASA <br>Earthdata <br>Common <br>Metadata <br>Repositor<br>y|Discovery<br>across<br>NASA<br>Earth-obs<br>ervation<br>datasets<br>and<br>services<br>by<br>spatial/te<br>mporal<br>parameter<br>s.|CMR<br>APIs|NASA<br>Earthdata<br>MCP|CMR is<br>NASA's<br>metadata<br>registry<br>for Earth<br>Science<br>data and<br>exposes<br>programm<br>atic<br>interfaces.<br>[115]|
|A|NASA <br>CMR <br>GraphQL|More<br>agent-frie<br>ndly<br>targeted<br>metadata<br>retrieval<br>than large<br>REST<br>payloads.|GraphQL|Generic<br>GraphQL<br>MCP|NASA<br>explicitly<br>provides<br>GraphQL<br>as an<br>alternative<br>query<br>language<br>over<br>CMR.[11]|
|A|USGS <br>Earthquak<br>e Catalog <br>/ ComCat|Earthquak<br>e event<br>detection,<br>magnitud<br>es,|FDSN API|Geohazar<br>d MCP|Use the<br>query API<br>for<br>research<br>and|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|||locations<br>and<br>related<br>seismic<br>products.|||USGS's<br>realtime<br>feeds for<br>monitorin<br>g.[116]|
|A|USGS <br>realtime <br>earthquak<br>e <br>GeoJSON|Immediat<br>e event<br>trigger for<br>automate<br>d <br>downstrea<br>m <br>horizon-sc<br>an<br>tasks--e.<br>g.,<br>infrastruct<br>ure/supply<br>-chain<br>exposure.|GeoJSON<br>feed|Streaming<br>/feed<br>MCP|USGS<br>recomme<br>nds<br>realtime<br>GeoJSON<br>feeds for<br>automate<br>d realtime<br>applicatio<br>ns.[117]|
|B|USGS <br>earthquak<br>e <br>Atom/RS<br>S/social <br>feeds|Lightweig<br>ht alerting<br>before<br>launching<br>deeper<br>geospatial<br>/event<br>analysis.|Atom/RS<br>S|Generic<br>feed MCP|USGS<br>maintains<br>realtime<br>notificatio<br>n/feed<br>resources<br>. [118]|
|B|USGS <br>ScienceB<br>ase|Broad<br>U.S.<br>scientific/<br>geospatial<br>datasets<br>beyond<br>earthquak<br>es.|REST/JS<br>ON|Geospatia<br>l REST<br>MCP|ScienceB<br>ase<br>exposes a<br>REST<br>service<br>architectu<br>re with<br>JSON.<br>[119]|
|A|U.S. <br>Energy <br>Informatio<br>n <br>Administr<br>ation|Electricity,<br>petroleum<br>, natural<br>gas and<br>broader<br>energy-m|REST API|Energy<br>MCP|EIA<br>makes<br>public<br>energy<br>data<br>available|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
||Open <br>Data|arket time<br>series;<br>essential<br>for<br>energy-tra<br>nsition<br>scanning.|||through a<br>free API;<br>registratio<br>n is<br>required<br>for API<br>use.[120]|
|A|EIA bulk <br>datasets|Large-sca<br>le local<br>energy<br>analytics<br>without<br>API-rate<br>constraint<br>s.|Bulk files|Bulk/local<br>mirror|EIA states<br>that an<br>API key is<br>not<br>required<br>for its<br>bulk-down<br>load<br>facility.<br>[121]|
|A|GBIF|Global<br>biodiversit<br>y <br>occurrenc<br>e,<br>taxonomy<br>and<br>related<br>biological<br>records;<br>strong<br>signal for<br>biodiversit<br>y,<br>conservati<br>on and<br>ecological<br>change.|REST/JS<br>ON|Biodiversit<br>y MCP|GBIF<br>describes<br>its API as<br>stable and<br>RESTful.<br>[122]|
|A|OpenAQ <br>v3|Aggregate<br>d global<br>ground-le<br>vel<br>air-quality<br>measure<br>ments<br>across<br>many|REST/JS<br>ON|Environm<br>ental<br>MCP|Current<br>API is v3;<br>v1/v2<br>were<br>retired in<br>January<br>2025. API<br>access<br>uses|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|||public<br>providers.|||keys, and<br>third-party<br>source<br>terms<br>remain<br>relevant.<br>[123]|
|A|OpenAQ <br>provider <br>metadata|Important<br>provenan<br>ce layer<br>identifying<br>which<br>organizati<br>on<br>actually<br>supplied<br>each<br>air-quality<br>stream.|API<br>resource|Same<br>MCP|Provider/o<br>wner<br>metadata<br>should<br>flow<br>directly<br>into your<br>source-pr<br>ovenance<br>record.<br>[124]|
|B|Open-Met<br>eo|Convenie<br>nt<br>normalize<br>d access<br>across<br>weather<br>models<br>and<br>archives;<br>valuable<br>for rapid<br>research<br>and<br>prototype<br>analysis.|JSON<br>APIs|Custom/lo<br>cal MCP<br>or<br>self-host|Particularl<br>y <br>interesting<br>for your<br>local<br>preferenc<br>e:<br>Open-Met<br>eo<br>publishes<br>its server<br>code<br>under<br>AGPL and<br>document<br>s <br>self-hostin<br>g, while<br>its hosted<br>API<br>combines<br>many<br>forecast/hi<br>storical<br>sources.|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
||||||Preserve<br>the<br>underlying <br>model/pro<br>vider as<br>provenan<br>ce rather<br>than citing<br>only<br>Open-Met<br>eo.[125]|
|A|Global <br>Forest <br>Watch|Tree-cove<br>r change<br>and forest<br>monitorin<br>g derived<br>from<br>satellite<br>informatio<br>n.|Open-dat<br>a platform|Geospatia<br>l <br>connector|Strong<br>land-use/<br>deforestat<br>ion signal,<br>especially<br>when<br>combined<br>with trade,<br>company<br>and policy<br>datasets.<br>[126]|
|B|Global <br>Forest <br>Watch <br>open-data <br>catalog|Direct<br>dataset<br>discovery<br>and<br>geospatial<br>asset<br>ingestion<br>behind<br>forest<br>monitorin<br>g <br>products.|Data<br>portal|Geospatia<br>l/downloa<br>d MCP|Useful<br>when an<br>analytical<br>agent<br>needs the<br>underlying<br>spatial<br>layer<br>rather<br>than a<br>dashboar<br>d result.<br>[127]|
|A|Global <br>Fishing <br>Watch|Vessel<br>and<br>fishing-eff<br>ort signals<br>relevant<br>to marine<br>resources<br>, supply|APIs|Maritime<br>MCP|Global<br>Fishing<br>Watch<br>document<br>s <br>programm<br>atic report<br>and|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|||chains,<br>illegal<br>fishing<br>and<br>geopolitic<br>al<br>competitio<br>n.|||vessel<br>APIs.<br>[128]|
|A|OpenStre<br>etMap <br>Overpass <br>API|Infrastruct<br>ure,<br>facilities,<br>roads,<br>points of<br>interest<br>and<br>rapidly<br>changing<br>communit<br>y-maintain<br>ed<br>geospatial<br>features.|Read-only<br>query API|Overpass <br>MCP or <br>local <br>Overpass <br>instance|Overpass<br>is<br>optimized<br>for<br>read/quer<br>y use over<br>OSM data<br>and can<br>itself be<br>run on<br>Linux/Doc<br>ker;<br>excellent<br>candidate<br>for a local<br>geospatial<br>tool.[129]|
|B|Overpass <br>Turbo/que<br>ry <br>templates|Human-d<br>esigned<br>query<br>templates<br>can be<br>turned<br>into<br>reusable<br>tools for<br>agents<br>looking for<br>specific<br>facility<br>classes.|Overpass<br>QL|Same<br>MCP|The<br>browser<br>tool itself<br>is less<br>important<br>than<br>preservin<br>g its query<br>language/<br>templates.<br>[130]|
|A|World <br>Bank <br>environm<br>ental/clim|Environm<br>ental<br>metrics<br>aligned<br>with|Indicators<br>API|Existing<br>World<br>Bank<br>MCP|No<br>additional<br>connector<br>is needed<br>once the|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
||ate <br>indicators|economic/<br>developm<br>ent<br>indicators<br>by<br>country.|||Indicators<br>API is<br>integrated<br>. [131]|
|A|FAOSTAT <br>agricultur<br>e/land/foo<br>d datasets|Agricultur<br>al<br>productio<br>n, land<br>use, food<br>and trade<br>signals<br>useful for<br>climate<br>adaptatio<br>n and<br>food-secu<br>rity<br>scenarios.|API|Existing<br>FAOSTAT<br>MCP|Reuse the<br>same<br>connector<br>described<br>above<br>rather<br>than<br>duplicatin<br>g <br>ingestion.<br>[63]|

For geospatial data, I would make the agent workflow metadata-first. An agent
should query a catalog, inspect spatial/temporal extent and variable metadata, and
only then request the actual raster/vector/time-series asset. This prevents a
horizon-scanning agent from accidentally downloading gigabytes of
Earth-observation data simply because a dataset appeared semantically relevant.

# News, web, social, developer and emerging-signal sources

This layer should be treated differently from official statistics. Its purpose is early
detection, not necessarily final evidentiary authority. A sensible architecture lets
social/news/web signals trigger deeper searches into primary scientific, regulatory,
procurement or statistical sources before making a high-confidence report claim.

GDELT is particularly useful for breadth because it monitors global news at very
large scale and provides structured event/document data; Media Cloud provides
another independent news-analysis corpus; Bluesky provides an unusually open
streaming architecture; Hacker News provides near-real-time technology-community
[signals. [132]](https://gdeltproject.org/)

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|A|GDELT <br>Event <br>data|Global<br>event/new<br>s-derived<br>geopolitic<br>al, social<br>and<br>economic<br>event<br>monitorin<br>g; useful<br>for<br>automate<br>d anomaly<br>detection.|Bulk/data<br>services|GDELT<br>MCP +<br>local<br>analytical<br>mirror|Treat<br>GDELT as<br>a derived<br>observatio<br>nal<br>dataset<br>and retain<br>links/ident<br>ifiers back<br>to<br>underlying<br>reporting<br>where<br>possible.<br>[133]|
|A|GDELT <br>Global <br>Knowledg<br>e Graph|Entities,<br>themes,<br>locations<br>and other<br>extracted<br>news<br>signals<br>useful for<br>topic<br>accelerati<br>on/co-occ<br>urrence<br>analysis.|Structured<br>/bulk data|Local<br>mirror +<br>EDA MCP|Very<br>useful as<br>a <br>machine-<br>generated<br>discovery<br>layer; not<br>a <br>substitute<br>for<br>reading<br>source<br>document<br>s.[134]|
|A|GDELT <br>DOC API|Full-text-o<br>riented<br>news<br>search for<br>targeted<br>deep<br>dives after<br>a weak<br>signal is<br>detected.|Search<br>API|Custom<br>REST<br>MCP|Combine<br>with<br>publisher<br>URL/archi<br>ve<br>retrieval<br>so the<br>evidence<br>object<br>points at<br>the<br>underlying<br>article as<br>well as|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
||||||GDELT.<br>[133]|
|A|Media <br>Cloud|Independ<br>ent<br>large-scal<br>e news<br>corpus/so<br>urce<br>directory,<br>useful for<br>comparati<br>ve media<br>coverage<br>and<br>narrative<br>diffusion.|API|Media<br>Cloud<br>MCP|Provides<br>search<br>over a<br>very large<br>story<br>corpus<br>and<br>structured<br>source/col<br>lection<br>organizati<br>on.[135]|
|A|Bluesky <br>firehose|Near-real-<br>time<br>public<br>social<br>discussio<br>n, expert<br>communiti<br>es and<br>rapid<br>technolog<br>y/news<br>diffusion.|Firehose|Streaming <br>ingestion, <br>not direct <br>LLM tool|Persist<br>first;<br>never put<br>an<br>unconstrai<br>ned social<br>firehose<br>directly<br>into an<br>agent<br>context<br>window.<br>Official AT<br>Protocol<br>document<br>ation<br>supports<br>firehose<br>consumpti<br>on.[136]|
|A|Bluesky <br>Jetstream|Filterable<br>JSON<br>represent<br>ation of<br>network<br>activity<br>that is<br>much|Streaming<br>JSON|Local<br>Jetstream<br>consumer|Jetstream<br>is<br>open-sour<br>ce and<br>supports<br>filtered/re<br>playable<br>consumpti|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|||easier to<br>operation<br>alize than<br>the raw<br>firehose.|||on,<br>making it<br>especially<br>attractive<br>for a<br>locally<br>operated<br>signal<br>pipeline.<br>[137]|
|A|Hacker <br>News API|High-sign<br>al early<br>discussio<br>n of<br>developer<br>tools,<br>startups,<br>AI,<br>cybersecu<br>rity and<br>research<br>releases.|Public<br>realtime<br>API|Lightweig<br>ht REST<br>MCP|Official<br>API data<br>are<br>exposed<br>through<br>Firebase<br>and are<br>suitable<br>for<br>inexpensi<br>ve<br>continuou<br>s <br>monitorin<br>g.[138]|
|A|GitHub <br>official <br>MCP <br>server|Repositori<br>es, source<br>code,<br>issues,<br>pull<br>requests<br>and<br>developm<br>ent<br>activity<br>are<br>exception<br>ally<br>valuable<br>signals of<br>emerging<br>technolog<br>y.|Official <br>MCP|Run <br>locally via <br>Docker or <br>binary|This is<br>probably<br>the<br>cleanest<br>match to<br>your<br>stated<br>local-MCP<br>preferenc<br>e. GitHub<br>officially<br>supports<br>local<br>Docker/bi<br>nary<br>operation.<br>[139]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|A|GitHub <br>repositori<br>es/code <br>through <br>official <br>MCP|Detect<br>new<br>implement<br>ations,<br>standards<br>adoption,<br>research-<br>code<br>releases<br>and<br>ecosyste<br>m growth.|MCP|Official<br>local<br>MCP,<br>preferably<br>read-only|Use<br>GitHub's<br>read-only<br>restriction<br>s/toolset<br>configurati<br>on for<br>research<br>agents<br>that do<br>not need<br>write<br>operation<br>s.[140]|
|A|GitHub <br>issues / <br>pull <br>requests <br>through <br>official <br>MCP|Often<br>reveals<br>roadmaps<br>, <br>incompati<br>bilities,<br>adoption<br>problems<br>and<br>implement<br>ation<br>activity<br>before<br>formal<br>announce<br>ments.|MCP|Same<br>official<br>MCP|Pin/versio<br>n the<br>server<br>and<br>expose<br>only<br>required<br>toolsets.<br>[141]|
|B|Reuters <br>MCP|High-quali<br>ty<br>profession<br>al news<br>retrieval<br>through<br>an<br>agent-orie<br>nted<br>interface.|Provider<br>MCP|Provider<br>MCP<br>where<br>entitled|Reuters<br>launched<br>an MCP<br>service in<br>2026, but<br>it is an<br>agency/cu<br>stomer<br>offering<br>rather<br>than a<br>freely<br>open<br>public-dat|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
||||||a source,<br>so it<br>belongs in<br>the<br>optional<br>commerci<br>al tier.<br>[142]|
|A|Federal <br>Register <br>feeds/API <br>as a <br>news-like <br>event <br>stream|New<br>rules/notic<br>es can be<br>treated as<br>immediate<br>horizon-sc<br>an events.|API|Existing<br>regulatory<br>MCP|Prefer the<br>official<br>API rather<br>than<br>scraping<br>the<br>website.<br>[143]|
|A|TED <br>RSS/API <br>as a <br>procurem<br>ent event <br>stream|New<br>procurem<br>ent<br>notices<br>can<br>trigger<br>sector-sp<br>ecific<br>research<br>agents<br>within<br>minutes/h<br>ours of<br>publicatio<br>n.|RSS/API|Existing<br>feed/proc<br>urement<br>MCP|Official<br>TED<br>materials<br>expose<br>both RSS<br>and<br>programm<br>atic<br>search/bul<br>k facilities.<br>[144]|
|A|arXiv <br>increment<br>al stream|New<br>preprints<br>are<br>natural<br>weak-sign<br>al events<br>for<br>science/te<br>chnology<br>scanning.|OAI-PMH/<br>API|Existing<br>scholarly<br>MCP|Poll<br>OAI-PMH/<br>API rather<br>than<br>scraping.<br>[145]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|B|USGS <br>realtime <br>feeds as <br>event <br>triggers|Natural<br>disasters<br>can<br>automatic<br>ally<br>launch<br>research<br>on<br>exposed<br>infrastruct<br>ure,<br>commoditi<br>es and<br>supply<br>chains.|GeoJSON<br>/Atom/RS<br>S|Existing<br>event<br>MCP|USGS<br>explicitly<br>provides<br>realtime<br>programm<br>atic feeds.<br>[146]|
|B|OpenAQ <br>latest <br>measure<br>ments|Sudden<br>pollution<br>anomalies<br>can<br>trigger<br>geographi<br>c/news/po<br>licy<br>correlatio<br>n tasks.|REST|Existing<br>environm<br>ental<br>MCP|Use<br>measure<br>ment/prov<br>ider<br>timestamp<br>s rather<br>than the<br>agent's<br>retrieval<br>time as<br>the<br>observatio<br>n time.<br>[147]|
|A|Official <br>MCP <br>Registry|Not itself<br>a <br>horizon-sc<br>an<br>evidence<br>source;<br>instead,<br>continuou<br>sly<br>discovers<br>potential<br>new agent<br>connector<br>s.|Registry<br>API/site|Connector<br>-discovery <br>agent|Treat it as<br>an<br>inventory<br>to<br>investigat<br>e, not an<br>allowlist.<br>Verify<br>publisher<br>identity,<br>code<br>repository,<br>license,<br>maintena<br>nce and|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
||||||permissio<br>ns<br>independ<br>ently.<br>[148]|
|B|BioMCP|Communit<br>y <br>integratio<br>n layer<br>federating<br>multiple<br>biomedica<br>l <br>resources<br>such as<br>PubMed,<br>Europe<br>PMC,<br>GWAS<br>and<br>related<br>providers.|Communit<br>y <br>MCP/CLI|Evaluate<br>for local<br>deployme<br>nt|Attractive<br>because it<br>already<br>tackles<br>identifier<br>resolution<br>and<br>provenan<br>ce across<br>biomedica<br>l sources;<br>still<br>inspect<br>communit<br>y code<br>and<br>independ<br>ently<br>preserve<br>upstream<br>source<br>attribution<br>. [41]|
|B|Open <br>scientific-<br>knowledg<br>e-graph <br>MCP work <br>such as <br>mcp-proto<br>-okn|Demonstr<br>ates a<br>communit<br>y pattern<br>for<br>exposing<br>scientific<br>knowledg<br>e graphs,<br>ontology<br>expansion<br>and<br>SPARQL-<br>style<br>exploratio|Communit<br>y/open-so<br>urce MCP|Evaluate<br>or borrow<br>architectu<br>re|Better<br>regarded<br>as an<br>architectu<br>ral<br>candidate<br>than an<br>authoritati<br>ve data<br>producer.<br>[149]|

|Pri.|Candidate<br>source|Horizon-s<br>canning<br>value|Machine<br>access|MCP/local<br>recomme<br>ndation|Caveats|
|---|---|---|---|---|---|
|||n to<br>agents.||||
|B|Communit<br>y <br>USAspen<br>ding MCP <br>implement<br>ations|Could<br>avoid<br>writing the<br>initial<br>adapter<br>yourself.|Communit<br>y MCP|Audit<br>against<br>official<br>USAspen<br>ding API|Communit<br>y <br>USAspen<br>ding<br>servers<br>have<br>appeared<br>in the<br>MCP<br>ecosyste<br>m, but the<br>authoritati<br>ve<br>evidence<br>source<br>remains<br>USAspen<br>ding's<br>official<br>API.[150]|

The news/social tier is where I would apply the strongest source-quality separation.
For example, "a Bluesky post claims X" should create a candidate signal whose
lineage points to that post; it should not silently become "X is true." An orchestrator
can then dispatch scientific, regulatory, corporate or statistical agents to seek
stronger evidence.

# Recommended rollout and provenance model

The source inventory becomes much more manageable when thought of as signal
layers rather than a flat collection of APIs. I would start with a relatively small number
of sources that jointly cover science, policy, money, markets, technology
development, news and the physical world, and only then add specialist datasets.

|Rollout tier|Sources / connectors|Why|
|---|---|---|
|Foundation|OpenAlex<br>snapshot/API;<br>Crossref; DataCite;<br>Europe PMC/NCBI;<br>arXiv; OpenCitations;<br>GitHub official MCP|Provides the<br>research/technology<br>graph and both formal<br>and informal<br>development signals.<br>[151]|
|Economic context|World Bank, OECD,<br>IMF, FRED/ALFRED,|Gives comparable<br>macro/trade/time-serie|

|Rollout tier|Sources / connectors|Why|
|---|---|---|
||ABS, ECB, UN<br>Comtrade|s evidence and<br>historical context.<br>[152]|
|Government demand / <br>policy|GovInfo MCP/API,<br>Federal Register,<br>Regulations.gov,<br>Congress.gov,<br>EUR-Lex, AusTender,<br>USAspending,<br>SAM.gov, TED|Captures laws,<br>proposed rules, official<br>documents,<br>government spending<br>and pre-award<br>demand.[153]|
|Corporate / <br>commercialization|SEC EDGAR, GLEIF,<br>USPTO ODP, EPO<br>OPS,<br>ClinicalTrials.gov|Connects research to<br>companies, financial<br>filings, patents and<br>commercialization<br>milestones.[154]|
|Early-signal layer|GDELT, Media Cloud,<br>Bluesky Jetstream,<br>Hacker News,<br>procurement RSS,<br>arXiv incremental feed|Detects emerging<br>narratives/events<br>before stronger<br>evidence is available.<br>[155]|
|Physical-world layer|Copernicus, NOAA,<br>NASA CMR, USGS,<br>EIA, OpenAQ, GBIF,<br>OSM/Overpass|Lets the system test<br>narratives against<br>climate, energy,<br>environmental,<br>biodiversity and<br>geospatial<br>observations.[156]|
|Specialist enrichment|Open Targets,<br>ChEMBL, UniProt,<br>GWAS Catalog,<br>openFDA, ReliefWeb,<br>HDX HAPI, ACLED,<br>NVD/CISA/OSV/EPSS|Deploy domain agents<br>only when the scan<br>enters biotech, health,<br>humanitarian/geopoliti<br>cal or cyber domains.<br>[157]|

For provenance, I would make the evidence object the fundamental unit of your
system, rather than a chunk of text in a vector database. Every API result, scraped
document, statistical observation or feed event should carry a standard envelope:

|Provenance field|What to retain|Why it matters|
|---|---|---|
|`provider`|Canonical upstream<br>producer, not merely<br>the intermediary used<br>to retrieve it|Prevents a record<br>retrieved through<br>OpenAlex/OpenAIRE/<br>Open-Meteo from<br>being incorrectly|

|Provenance field|What to retain|Why it matters|
|---|---|---|
|||attributed to the<br>aggregator.|
|`source_collection`|Dataset/database/feed<br>name and version|Distinguishes, for<br>example, one IMF<br>dataset or FDA<br>collection from<br>another.|
|`provider_record_id`|DOI, PMID, NCT,<br>CVE, LEI, patent ID,<br>legislation ID, award<br>ID, etc.|Stable cross-agent<br>deduplication.|
|`retrieval_method`|MCP server/tool, API,<br>bulk file, RSS,<br>browser, scrape|Makes evidence<br>reproducible and<br>auditable.|
|`tool_identity`|MCP server<br>package/image,<br>version/commit, tool<br>name and<br>tool-schema hash|Essential when tool<br>behavior changes over<br>time.|
|`request`|Full normalized query<br>parameters or POST<br>body|Makes "why did this<br>evidence appear?"<br>answerable.|
|`retrieved_at`|UTC timestamp plus<br>local timezone if<br>operationally useful|Reconstructs the<br>information state at<br>scan time.|
|`provider_published_a`<br>`t`|Original<br>publication/event time|Separates event time<br>from discovery time.|
|`provider_updated_at`|Upstream<br>modification/revision<br>time|Important for mutable<br>statistics and<br>documents.|
|`first_seen_at`|First time your system<br>observed the record|Excellent horizon-scan<br>signal in its own right.|
|`http_metadata`|Status, ETag,<br>Last-Modified and<br>relevant content<br>headers|Supports caching and<br>revision detection.|
|`raw_content_hash`|SHA-256 or equivalent|Demonstrates exactly<br>which<br>payload/document<br>supported the<br>downstream claim.|
|`raw_object_uri`|Pointer into immutable<br>local object storage|Lets auditors inspect<br>the original evidence.|

|Provenance field|What to retain|Why it matters|
|---|---|---|
|`license_rights`|Source license,<br>copyright/OA status,<br>redistribution<br>constraints|Particularly important<br>for papers, news and<br>third-party aggregated<br>datasets.|
|`parser_version`|Extractor/parser code<br>version|Separates source<br>changes from<br>extraction changes.|
|`normalized_record_id`|Your own stable<br>entity/event identifier|Allows several<br>independent providers<br>to support one<br>entity/event.|
|`evidence_locator`|JSONPath,<br>table/row/column,<br>page, paragraph/span<br>or XML element|Lets synthesized<br>claims point to precise<br>supporting evidence.|
|`derivation_parents`|IDs of evidence<br>objects used to<br>compute a<br>statistic/entity/claim|Builds a provenance<br>DAG rather than a flat<br>bibliography.|
|`claim_id`|Synthesized<br>proposition supported<br>or contradicted by the<br>evidence|Enables claim-centric<br>horizon reports.|
|`stance`|Supports / contradicts<br>/ contextualizes /<br>merely mentions|Prevents citation<br>presence from being<br>mistaken for<br>evidentiary support.|
|`confidence`|System's assessed<br>confidence, separate<br>from source authority|Makes uncertainty<br>explicit rather than<br>burying it in prose.|

The resulting architecture is roughly external source → local acquisition MCP →
immutable raw evidence store → normalization/entity resolution → analytical store →
signal detection → specialist deep-research agents → evidence/claim graph →
synthesis agent → horizon-scan report. MCP then serves primarily as the tool
interoperability layer, while immutable data storage and your evidence graph provide
the provenance guarantees.

This separation matters because MCP itself is not a provenance system: it
standardizes how servers expose tools and context to models. Your application
should therefore log every MCP invocation and response as part of the evidence
[chain. [158]](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)

For locally executed servers, I would also impose a research-only security profile:
default read-only scopes, no shell/file access unless explicitly necessary, credentials

isolated per provider, network egress allowlists, pinned container digests or binary
hashes, and a review gate before introducing community MCP code. The current
MCP security guidance explicitly calls out compromise risks for local servers, which
[can have substantial host access if they are not sandboxed appropriately. [159]](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)

The practical conclusion from this research is that the most capable system would
not be an "MCP-only research agent." It would be a local-first federated evidence
system in which MCP provides a consistent agent-facing interface over four
underlying acquisition modes: provider APIs, protocol-standard APIs, bulk/local
mirrors, and feeds/browser acquisition. The relatively few official MCPs--particularly
GitHub and GovInfo--can be used directly; mature public APIs such as OpenAlex,
Crossref, OECD, IMF, SEC, USAspending, ClinicalTrials.gov, NASA, NOAA and EIA
are sufficiently valuable that the absence of an official MCP should not meaningfully
[count against them. [160]](https://github.com/github/github-mcp-server)

[[1]](https://github.com/github/github-mcp-server) [[139]](https://github.com/github/github-mcp-server) [[141]](https://github.com/github/github-mcp-server) [[160] https://github.com/github/github-mcp-server](https://github.com/github/github-mcp-server)

[https://github.com/github/github-mcp-server](https://github.com/github/github-mcp-server)

[[2] https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture](https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture)

[https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture](https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture)

[[3]](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices) [[159]](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)
https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_prac
tices

[https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_prac](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)
[tices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)

[[4]](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html) [[6]](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html) [[58] https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html)

[https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html)

[[5]](https://clinicaltrials.gov/data-api/api) [[44] https://clinicaltrials.gov/data-api/api](https://clinicaltrials.gov/data-api/api)

[https://clinicaltrials.gov/data-api/api](https://clinicaltrials.gov/data-api/api)

[[7]](https://opencitations.net/querying/) [[32] https://opencitations.net/querying/](https://opencitations.net/querying/)

[https://opencitations.net/querying/](https://opencitations.net/querying/)

[[8]](https://info.arxiv.org/help/bulk_data.html) [[25]](https://info.arxiv.org/help/bulk_data.html) [[145] https://info.arxiv.org/help/bulk_data.html](https://info.arxiv.org/help/bulk_data.html)

[https://info.arxiv.org/help/bulk_data.html](https://info.arxiv.org/help/bulk_data.html)

[[9]](https://ted.europa.eu/en/sitemap) [[86]](https://ted.europa.eu/en/sitemap) [[144] https://ted.europa.eu/en/sitemap](https://ted.europa.eu/en/sitemap)

[https://ted.europa.eu/en/sitemap](https://ted.europa.eu/en/sitemap)

[[10]](https://help.openalex.org/access/sync/) [[17] https://help.openalex.org/access/sync/](https://help.openalex.org/access/sync/)

[https://help.openalex.org/access/sync/](https://help.openalex.org/access/sync/)

[[11] https://graphql.earthdata.nasa.gov/](https://graphql.earthdata.nasa.gov/)

[https://graphql.earthdata.nasa.gov/](https://graphql.earthdata.nasa.gov/)

[[12]](https://bsky.network/docs/consuming-the-firehose/) [[136] https://bsky.network/docs/consuming-the-firehose/](https://bsky.network/docs/consuming-the-firehose/)

[https://bsky.network/docs/consuming-the-firehose/](https://bsky.network/docs/consuming-the-firehose/)

[[13]](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) [[20] https://www.crossref.org/documentation/retrieve-metadata/rest-api/](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)

[https://www.crossref.org/documentation/retrieve-metadata/rest-api/](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)

[[14]](https://help.openalex.org/api/) [[15]](https://help.openalex.org/api/) [[52]](https://help.openalex.org/api/) [[151] https://help.openalex.org/api/](https://help.openalex.org/api/)

[https://help.openalex.org/api/](https://help.openalex.org/api/)

[[16] https://help.openalex.org/access/pricing/](https://help.openalex.org/access/pricing/)

[https://help.openalex.org/access/pricing/](https://help.openalex.org/access/pricing/)

[[18] https://help.openalex.org/access/fulltext/](https://help.openalex.org/access/fulltext/)

[https://help.openalex.org/access/fulltext/](https://help.openalex.org/access/fulltext/)

[[19] https://help.openalex.org/api/semantic-search/](https://help.openalex.org/api/semantic-search/)

[https://help.openalex.org/api/semantic-search/](https://help.openalex.org/api/semantic-search/)

[[21]](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)
https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authe
ntication/

[https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authe](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)
[ntication/](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)

[[22] https://support.datacite.org/docs/api](https://support.datacite.org/docs/api)

[https://support.datacite.org/docs/api](https://support.datacite.org/docs/api)

[[23] https://datacite.org/integrate-workflows/](https://datacite.org/integrate-workflows/)

[https://datacite.org/integrate-workflows/](https://datacite.org/integrate-workflows/)

[[24] https://info.arxiv.org/help/api/user-manual.html](https://info.arxiv.org/help/api/user-manual.html)

[https://info.arxiv.org/help/api/user-manual.html](https://info.arxiv.org/help/api/user-manual.html)

[[26] https://info.arxiv.org/help/api/tou.html](https://info.arxiv.org/help/api/tou.html)

[https://info.arxiv.org/help/api/tou.html](https://info.arxiv.org/help/api/tou.html)

[[27] https://europepmc.org/RestfulWebService](https://europepmc.org/RestfulWebService)

[https://europepmc.org/RestfulWebService](https://europepmc.org/RestfulWebService)

[[28] https://europepmc.org/developers](https://europepmc.org/developers)

[https://europepmc.org/developers](https://europepmc.org/developers)

[[29] https://www.semanticscholar.org/product/api](https://www.semanticscholar.org/product/api)

[https://www.semanticscholar.org/product/api](https://www.semanticscholar.org/product/api)

[[30] https://api.semanticscholar.org/api-docs/datasets](https://api.semanticscholar.org/api-docs/datasets)

[https://api.semanticscholar.org/api-docs/datasets](https://api.semanticscholar.org/api-docs/datasets)

[[31] https://api.opencitations.net/index](https://api.opencitations.net/index)

[https://api.opencitations.net/index](https://api.opencitations.net/index)

[[33] https://opencitations.net/](https://opencitations.net/)

[https://opencitations.net/](https://opencitations.net/)

[[34] https://core.ac.uk/](https://core.ac.uk/)

[https://core.ac.uk/](https://core.ac.uk/)

[[35] https://api.openaire.eu/](https://api.openaire.eu/)

[https://api.openaire.eu/](https://api.openaire.eu/)

[[36] https://info.orcid.org/](https://info.orcid.org/)

[https://info.orcid.org/](https://info.orcid.org/)

[[37] https://ror.org/](https://ror.org/)

[https://ror.org/](https://ror.org/)

[[38] https://ror.org/blog/2025-06-11-v1-sunset/](https://ror.org/blog/2025-06-11-v1-sunset/)

[https://ror.org/blog/2025-06-11-v1-sunset/](https://ror.org/blog/2025-06-11-v1-sunset/)

[[39] https://unpaywall.org/products/api](https://unpaywall.org/products/api)

[https://unpaywall.org/products/api](https://unpaywall.org/products/api)

[[40] https://www.ncbi.nlm.nih.gov/](https://www.ncbi.nlm.nih.gov/)

[https://www.ncbi.nlm.nih.gov/](https://www.ncbi.nlm.nih.gov/)

[[41] https://biomcp.org/reference/data-sources/](https://biomcp.org/reference/data-sources/)

[https://biomcp.org/reference/data-sources/](https://biomcp.org/reference/data-sources/)

[[42] https://www.ebi.ac.uk/gwas/](https://www.ebi.ac.uk/gwas/)

[https://www.ebi.ac.uk/gwas/](https://www.ebi.ac.uk/gwas/)

[[43]](https://platform-docs.opentargets.org/evidence) [[157] https://platform-docs.opentargets.org/evidence](https://platform-docs.opentargets.org/evidence)

[https://platform-docs.opentargets.org/evidence](https://platform-docs.opentargets.org/evidence)

[[45] https://open.fda.gov/apis/](https://open.fda.gov/apis/)

[https://open.fda.gov/apis/](https://open.fda.gov/apis/)

[[46] https://www.ebi.ac.uk/chembl/api/data/docs](https://www.ebi.ac.uk/chembl/api/data/docs)

[https://www.ebi.ac.uk/chembl/api/data/docs](https://www.ebi.ac.uk/chembl/api/data/docs)

[[47] https://www.uniprot.org/help/api](https://www.uniprot.org/help/api)

[https://www.uniprot.org/help/api](https://www.uniprot.org/help/api)

[[48] https://www.ensembl.org/](https://www.ensembl.org/)

[https://www.ensembl.org/](https://www.ensembl.org/)

[[49] https://data.uspto.gov/](https://data.uspto.gov/)

[https://data.uspto.gov/](https://data.uspto.gov/)

[[50] https://data.uspto.gov/support/transition-guide/patentsview](https://data.uspto.gov/support/transition-guide/patentsview)

[https://data.uspto.gov/support/transition-guide/patentsview](https://data.uspto.gov/support/transition-guide/patentsview)

[[51] https://www.epo.org/en/searching-for-patents/data/web-services/ops](https://www.epo.org/en/searching-for-patents/data/web-services/ops)

[https://www.epo.org/en/searching-for-patents/data/web-services/ops](https://www.epo.org/en/searching-for-patents/data/web-services/ops)

[[53]](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation)
https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicat
ors-api-documentation

[https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicat](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation)
[ors-api-documentation](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation)

[[54] https://data360.worldbank.org/en/api](https://data360.worldbank.org/en/api)

[https://data360.worldbank.org/en/api](https://data360.worldbank.org/en/api)

[[55]](https://datahelpdesk.worldbank.org/knowledgebase/articles/889386-developer-information-overview)
https://datahelpdesk.worldbank.org/knowledgebase/articles/889386-developer-infor
mation-overview

[https://datahelpdesk.worldbank.org/knowledgebase/articles/889386-developer-infor](https://datahelpdesk.worldbank.org/knowledgebase/articles/889386-developer-information-overview)
[mation-overview](https://datahelpdesk.worldbank.org/knowledgebase/articles/889386-developer-information-overview)

[[56] https://documents.worldbank.org/en/publication/documents-reports/api](https://documents.worldbank.org/en/publication/documents-reports/api)

[https://documents.worldbank.org/en/publication/documents-reports/api](https://documents.worldbank.org/en/publication/documents-reports/api)

[[57] https://wits.worldbank.org/witsapiintro.aspx?lang=en](https://wits.worldbank.org/witsapiintro.aspx?lang=en)

[https://wits.worldbank.org/witsapiintro.aspx?lang=en](https://wits.worldbank.org/witsapiintro.aspx?lang=en)

[[59] https://data.imf.org/](https://data.imf.org/)

[https://data.imf.org/](https://data.imf.org/)

[[60] https://unstats.un.org/sdgapi/swagger/](https://unstats.un.org/sdgapi/swagger/)

[https://unstats.un.org/sdgapi/swagger/](https://unstats.un.org/sdgapi/swagger/)

[[61] https://comtradeplus.un.org/](https://comtradeplus.un.org/)

[https://comtradeplus.un.org/](https://comtradeplus.un.org/)

[[62] https://datalab.wto.org/](https://datalab.wto.org/)

[https://datalab.wto.org/](https://datalab.wto.org/)

[[63] https://www.fao.org/](https://www.fao.org/)

[https://www.fao.org/](https://www.fao.org/)

[[64] https://unctadstat.unctad.org/](https://unctadstat.unctad.org/)

[https://unctadstat.unctad.org/](https://unctadstat.unctad.org/)

[[65]](https://fred.stlouisfed.org/docs/api/fred/overview.html) [[66] https://fred.stlouisfed.org/docs/api/fred/overview.html](https://fred.stlouisfed.org/docs/api/fred/overview.html)

[https://fred.stlouisfed.org/docs/api/fred/overview.html](https://fred.stlouisfed.org/docs/api/fred/overview.html)

[[67] https://www.bls.gov/developers/home.htm](https://www.bls.gov/developers/home.htm)

[https://www.bls.gov/developers/home.htm](https://www.bls.gov/developers/home.htm)

[[68] https://apps.bea.gov/api/signup/](https://apps.bea.gov/api/signup/)

[https://apps.bea.gov/api/signup/](https://apps.bea.gov/api/signup/)

[[69] https://www.census.gov/data/developers/data-sets.html](https://www.census.gov/data/developers/data-sets.html)

[https://www.census.gov/data/developers/data-sets.html](https://www.census.gov/data/developers/data-sets.html)

[[70] https://data.ecb.europa.eu/help/getting-data-web-services-sdmx-0](https://data.ecb.europa.eu/help/getting-data-web-services-sdmx-0)

[https://data.ecb.europa.eu/help/getting-data-web-services-sdmx-0](https://data.ecb.europa.eu/help/getting-data-web-services-sdmx-0)

[[71]](https://www.abs.gov.au/statistics/application-programming-interfaces-apis/data-api-user-guide)
https://www.abs.gov.au/statistics/application-programming-interfaces-apis/data-api-u
ser-guide

[https://www.abs.gov.au/statistics/application-programming-interfaces-apis/data-api-u](https://www.abs.gov.au/statistics/application-programming-interfaces-apis/data-api-user-guide)
[ser-guide](https://www.abs.gov.au/statistics/application-programming-interfaces-apis/data-api-user-guide)

[[72] https://www.rba.gov.au/statistics/](https://www.rba.gov.au/statistics/)

[https://www.rba.gov.au/statistics/](https://www.rba.gov.au/statistics/)

[[73] https://api.gov.au/](https://api.gov.au/)

[https://api.gov.au/](https://api.gov.au/)

[[74] https://api.nsw.gov.au/](https://api.nsw.gov.au/)

[https://api.nsw.gov.au/](https://api.nsw.gov.au/)

[[75] https://www.tenders.gov.au/](https://www.tenders.gov.au/)

[https://www.tenders.gov.au/](https://www.tenders.gov.au/)

[[76] https://github.com/austender/austender-ocds-api](https://github.com/austender/austender-ocds-api)

[https://github.com/austender/austender-ocds-api](https://github.com/austender/austender-ocds-api)

[[77] https://www.sec.gov/search-filings/edgar-application-programming-interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

[https://www.sec.gov/search-filings/edgar-application-programming-interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

[[78] https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)

[https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)

[[79] https://www.gleif.org/en/lei-data/gleif-api](https://www.gleif.org/en/lei-data/gleif-api)

[https://www.gleif.org/en/lei-data/gleif-api](https://www.gleif.org/en/lei-data/gleif-api)

[[80] https://api.usaspending.gov/docs/endpoints](https://api.usaspending.gov/docs/endpoints)

[https://api.usaspending.gov/docs/endpoints](https://api.usaspending.gov/docs/endpoints)

[[81] https://sam.gov/opportunities](https://sam.gov/opportunities)

[https://sam.gov/opportunities](https://sam.gov/opportunities)

[[82] https://sam.gov/contracting](https://sam.gov/contracting)

[https://sam.gov/contracting](https://sam.gov/contracting)

[[83] https://sam.gov/fsrs](https://sam.gov/fsrs)

[https://sam.gov/fsrs](https://sam.gov/fsrs)

[[84] https://docs.ted.europa.eu/api/latest/index.html](https://docs.ted.europa.eu/api/latest/index.html)

[https://docs.ted.europa.eu/api/latest/index.html](https://docs.ted.europa.eu/api/latest/index.html)

[[85] https://data.ted.europa.eu/](https://data.ted.europa.eu/)

[https://data.ted.europa.eu/](https://data.ted.europa.eu/)

[[87] https://ourworldindata.org/](https://ourworldindata.org/)

[https://ourworldindata.org/](https://ourworldindata.org/)

[[88] https://www.who.int/](https://www.who.int/)

[https://www.who.int/](https://www.who.int/)

[[89]](https://www.govinfo.gov/features/mcp-public-preview) [[90]](https://www.govinfo.gov/features/mcp-public-preview) [[153] https://www.govinfo.gov/features/mcp-public-preview](https://www.govinfo.gov/features/mcp-public-preview)

[https://www.govinfo.gov/features/mcp-public-preview](https://www.govinfo.gov/features/mcp-public-preview)

[[91] https://api.govinfo.gov/docs/](https://api.govinfo.gov/docs/)

[https://api.govinfo.gov/docs/](https://api.govinfo.gov/docs/)

[[92]](https://www.federalregister.gov/reader-aids/developer-resources/rest-api) [[143] https://www.federalregister.gov/reader-aids/developer-resources/rest-api](https://www.federalregister.gov/reader-aids/developer-resources/rest-api)

[https://www.federalregister.gov/reader-aids/developer-resources/rest-api](https://www.federalregister.gov/reader-aids/developer-resources/rest-api)

[[93] https://www.federalregister.gov/reader-aids/developer-resources/bulk-data](https://www.federalregister.gov/reader-aids/developer-resources/bulk-data)

[https://www.federalregister.gov/reader-aids/developer-resources/bulk-data](https://www.federalregister.gov/reader-aids/developer-resources/bulk-data)

[[94] https://api.regulations.gov/](https://api.regulations.gov/)

[https://api.regulations.gov/](https://api.regulations.gov/)

[[95] https://api.congress.gov/](https://api.congress.gov/)

[https://api.congress.gov/](https://api.congress.gov/)

[[96]](https://eur-lex.europa.eu/content/help/data-reuse/reuse-contents-eurlex-details.html)
https://eur-lex.europa.eu/content/help/data-reuse/reuse-contents-eurlex-details.html

[https://eur-lex.europa.eu/content/help/data-reuse/reuse-contents-eurlex-details.html](https://eur-lex.europa.eu/content/help/data-reuse/reuse-contents-eurlex-details.html)

[[97] https://www.legislation.gov.uk/developer/contents](https://www.legislation.gov.uk/developer/contents)

[https://www.legislation.gov.uk/developer/contents](https://www.legislation.gov.uk/developer/contents)

[[98]](https://nvd.nist.gov/developers/vulnerabilities) [[107] https://nvd.nist.gov/developers/vulnerabilities](https://nvd.nist.gov/developers/vulnerabilities)

[https://nvd.nist.gov/developers/vulnerabilities](https://nvd.nist.gov/developers/vulnerabilities)

[[99] https://www.cisa.gov/known-exploited-vulnerabilities-catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)

[https://www.cisa.gov/known-exploited-vulnerabilities-catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)

[[100] https://osv.dev/](https://osv.dev/)

[https://osv.dev/](https://osv.dev/)

[[101] https://api.first.org/epss/](https://api.first.org/epss/)

[https://api.first.org/epss/](https://api.first.org/epss/)

[[102] https://reliefweb.int/](https://reliefweb.int/)

[https://reliefweb.int/](https://reliefweb.int/)

[[103] https://hdx-hapi.readthedocs.io/](https://hdx-hapi.readthedocs.io/)

[https://hdx-hapi.readthedocs.io/](https://hdx-hapi.readthedocs.io/)

[[104] https://acleddata.com/](https://acleddata.com/)

[https://acleddata.com/](https://acleddata.com/)

[[105] https://unstats.un.org/unsd/api/](https://unstats.un.org/unsd/api/)

[https://unstats.un.org/unsd/api/](https://unstats.un.org/unsd/api/)

[[106]](https://m.economictimes.com/news/india/mospi-launches-mcp-server-to-link-ai-tools-with-govt-data/articleshow/128005462.cms)
https://m.economictimes.com/news/india/mospi-launches-mcp-server-to-link-ai-toolswith-govt-data/articleshow/128005462.cms

[https://m.economictimes.com/news/india/mospi-launches-mcp-server-to-link-ai-tools-](https://m.economictimes.com/news/india/mospi-launches-mcp-server-to-link-ai-tools-with-govt-data/articleshow/128005462.cms)
[with-govt-data/articleshow/128005462.cms](https://m.economictimes.com/news/india/mospi-launches-mcp-server-to-link-ai-tools-with-govt-data/articleshow/128005462.cms)

[[108]](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/cmr-api) [[115]](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/cmr-api)
https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-deve
loper-portal/cmr-api

[https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-deve](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/cmr-api)
[loper-portal/cmr-api](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/cmr-api)

[[109]](https://cds.climate.copernicus.eu/how-to-api) [[111]](https://cds.climate.copernicus.eu/how-to-api) [[156] https://cds.climate.copernicus.eu/how-to-api](https://cds.climate.copernicus.eu/how-to-api)

[https://cds.climate.copernicus.eu/how-to-api](https://cds.climate.copernicus.eu/how-to-api)

[[110] https://climate.copernicus.eu/the-climate-data-store](https://climate.copernicus.eu/the-climate-data-store)

[https://climate.copernicus.eu/the-climate-data-store](https://climate.copernicus.eu/the-climate-data-store)

[[112] https://www.ncdc.noaa.gov/cdo-web/webservices/getstarted](https://www.ncdc.noaa.gov/cdo-web/webservices/getstarted)

[https://www.ncdc.noaa.gov/cdo-web/webservices/getstarted](https://www.ncdc.noaa.gov/cdo-web/webservices/getstarted)

[[113]](https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation)
https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation

[https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation](https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation)

[[114]](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database)
https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database

[https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database)

[[116]](https://earthquake.usgs.gov/fdsnws/event/1/) [[117] https://earthquake.usgs.gov/fdsnws/event/1/](https://earthquake.usgs.gov/fdsnws/event/1/)

[https://earthquake.usgs.gov/fdsnws/event/1/](https://earthquake.usgs.gov/fdsnws/event/1/)

[[118]](https://earthquake.usgs.gov/earthquakes/feed/) [[146] https://earthquake.usgs.gov/earthquakes/feed/](https://earthquake.usgs.gov/earthquakes/feed/)

[https://earthquake.usgs.gov/earthquakes/feed/](https://earthquake.usgs.gov/earthquakes/feed/)

[[119]](https://www.usgs.gov/sciencebase-instructions-and-documentation/api-and-web-services)
https://www.usgs.gov/sciencebase-instructions-and-documentation/api-and-web-serv
ices

[https://www.usgs.gov/sciencebase-instructions-and-documentation/api-and-web-serv](https://www.usgs.gov/sciencebase-instructions-and-documentation/api-and-web-services)
[ices](https://www.usgs.gov/sciencebase-instructions-and-documentation/api-and-web-services)

[[120] https://www.eia.gov/opendata/](https://www.eia.gov/opendata/)

[https://www.eia.gov/opendata/](https://www.eia.gov/opendata/)

[[121] https://www.eia.gov/opendata/v1/register.php](https://www.eia.gov/opendata/v1/register.php)

[https://www.eia.gov/opendata/v1/register.php](https://www.eia.gov/opendata/v1/register.php)

[[122] https://techdocs.gbif.org/en/openapi/](https://techdocs.gbif.org/en/openapi/)

[https://techdocs.gbif.org/en/openapi/](https://techdocs.gbif.org/en/openapi/)

[[123]](https://docs.openaq.org/about/about) [[147] https://docs.openaq.org/about/about](https://docs.openaq.org/about/about)

[https://docs.openaq.org/about/about](https://docs.openaq.org/about/about)

[[124] https://docs.openaq.org/resources/providers](https://docs.openaq.org/resources/providers)

[https://docs.openaq.org/resources/providers](https://docs.openaq.org/resources/providers)

[[125] https://open-meteo.com/](https://open-meteo.com/)

[https://open-meteo.com/](https://open-meteo.com/)

[[126] https://www.globalforestwatch.org/](https://www.globalforestwatch.org/)

[https://www.globalforestwatch.org/](https://www.globalforestwatch.org/)

[[127] https://data.globalforestwatch.org/](https://data.globalforestwatch.org/)

[https://data.globalforestwatch.org/](https://data.globalforestwatch.org/)

[[128] https://globalfishingwatch.org/](https://globalfishingwatch.org/)

[https://globalfishingwatch.org/](https://globalfishingwatch.org/)

[[129] https://wiki.openstreetmap.org/wiki/Overpass_API](https://wiki.openstreetmap.org/wiki/Overpass_API)

[https://wiki.openstreetmap.org/wiki/Overpass_API](https://wiki.openstreetmap.org/wiki/Overpass_API)

[[130] https://overpass-turbo.eu/](https://overpass-turbo.eu/)

[https://overpass-turbo.eu/](https://overpass-turbo.eu/)

[[131]](https://datahelpdesk.worldbank.org/) [[152] https://datahelpdesk.worldbank.org/](https://datahelpdesk.worldbank.org/)

[https://datahelpdesk.worldbank.org/](https://datahelpdesk.worldbank.org/)

[[132]](https://gdeltproject.org/) [[133]](https://gdeltproject.org/) [[134]](https://gdeltproject.org/) [[155] https://gdeltproject.org/](https://gdeltproject.org/)

[https://gdeltproject.org/](https://gdeltproject.org/)

[[135] https://www.mediacloud.org/documentation/search-api-guide](https://www.mediacloud.org/documentation/search-api-guide)

[https://www.mediacloud.org/documentation/search-api-guide](https://www.mediacloud.org/documentation/search-api-guide)

[[137] https://github.com/bluesky-social/jetstream](https://github.com/bluesky-social/jetstream)

[https://github.com/bluesky-social/jetstream](https://github.com/bluesky-social/jetstream)

[[138] https://github.com/hackernews/api](https://github.com/hackernews/api)

[https://github.com/hackernews/api](https://github.com/hackernews/api)

[[140] https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md)

[https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md)

[[142]](https://www.reuters.com/media-center/reuters-launches-model-context-protocol-server-bring-trusted-news-directly-into-2026-07-08/)
https://www.reuters.com/media-center/reuters-launches-model-context-protocol-serv
er-bring-trusted-news-directly-into-2026-07-08/

[https://www.reuters.com/media-center/reuters-launches-model-context-protocol-serv](https://www.reuters.com/media-center/reuters-launches-model-context-protocol-server-bring-trusted-news-directly-into-2026-07-08/)
[er-bring-trusted-news-directly-into-2026-07-08/](https://www.reuters.com/media-center/reuters-launches-model-context-protocol-server-bring-trusted-news-directly-into-2026-07-08/)

[[148] https://registry.modelcontextprotocol.io/](https://registry.modelcontextprotocol.io/)

[https://registry.modelcontextprotocol.io/](https://registry.modelcontextprotocol.io/)

[[149] https://arxiv.org/abs/2605.30283](https://arxiv.org/abs/2605.30283)

[https://arxiv.org/abs/2605.30283](https://arxiv.org/abs/2605.30283)

[[150] https://registry.modelcontextprotocol.io/?q=diskcleanKit](https://registry.modelcontextprotocol.io/?q=diskcleanKit)

[https://registry.modelcontextprotocol.io/?q=diskcleanKit](https://registry.modelcontextprotocol.io/?q=diskcleanKit)

[[154]](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data

[https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

[[158] https://modelcontextprotocol.io/specification/2026-07-28/server/tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)

[https://modelcontextprotocol.io/specification/2026-07-28/server/tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
