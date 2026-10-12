"""The bulk stages: adapters whose sources go to the lake as typed Parquet, once per release, rather than into raw
bundles. Each takes (card, store, client, limit=, config_hash=) and returns a result shaped like a CollectResult."""

from __future__ import annotations

from .corpus import HfCorpusParams
from .corpus import refresh as corpus_refresh
from .ipr import IprParams
from .ipr import refresh as ipr_refresh

LAKE_STAGES = {"ip_rapid": ipr_refresh, "hf_corpus": corpus_refresh}
LAKE_PARAMS = {"ip_rapid": IprParams, "hf_corpus": HfCorpusParams}
