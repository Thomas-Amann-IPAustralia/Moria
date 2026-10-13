"""The bulk stages: adapters whose sources go to the lake as typed Parquet, once per release, rather than into raw
bundles. Each takes (card, store, client, limit=, config_hash=) and returns a result shaped like a CollectResult."""

from __future__ import annotations

from .bulk import ZipCsvParams
from .bulk import refresh as bulk_refresh
from .corpus import HfCorpusParams
from .corpus import refresh as corpus_refresh
from .delimited import DelimitedParams
from .delimited import refresh as delimited_refresh
from .ipr import IprParams
from .ipr import refresh as ipr_refresh

LAKE_STAGES = {
    "ip_rapid": ipr_refresh,
    "hf_corpus": corpus_refresh,
    "zip_csv": bulk_refresh,
    "delimited_csv": delimited_refresh,
}
LAKE_PARAMS = {
    "ip_rapid": IprParams,
    "hf_corpus": HfCorpusParams,
    "zip_csv": ZipCsvParams,
    "delimited_csv": DelimitedParams,
}
