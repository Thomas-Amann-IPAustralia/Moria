"""OECD headline series, through the OECD Data API (SDMX 2.1 REST at sdmx.oecd.org, CSV with labels).

The OECD answers the same SDMX-CSV as the ABS, so each query works as in `moria.collectors.abs`: a dataflow (agency,
flow and version; an empty version means the latest), an SDMX key and a start period; every series becomes one record
holding all its observations, and an unchanged series keeps its evidence id from one weekly vintage to the next.

What is the OECD's own:
- **A small budget of queries.** The OECD limits its API per user (its best-practices page gives 20 data downloads
  an hour in one version and 60 in another, and says a user over the limit is blocked for a while). A card may hold
  at most `max_queries` data queries (18 by default), the host waits several seconds between requests
  (`config/moria.yaml`), and a refused query is retried once at most.
- **Qualitative tables.** Some dataflows (the corporate tax statistics' QDD tables, such as IP regimes) hold words,
  not numbers; their queries set `text_values: true`.
- **Record ids** name the agency and flow but not the version, so a series keeps its id when the OECD publishes a
  new version of a dataflow; the version each vintage came from is in the payload (`dataflow`).

The OECD's data are offered under its Terms and Conditions; since 1 July 2024 its data and new written content are
under CC BY 4.0 (D-020). Observations are stored privately and cited "OECD".
"""

from __future__ import annotations

import logging

from pydantic import field_validator

from ..config import Strict
from ..records import RawRecord, make_envelope, utc_now
from .abs import parse_sdmx_csv
from .base import CollectContext, CollectError

PARSER_VERSION = "oecd-sdmx-v1"
ACCEPT = "application/vnd.sdmx.data+csv; charset=utf-8; labels=both"
SERIES_ATTRIBUTES = ("UNIT_MEASURE", "UNIT_MULT", "DECIMALS", "BASE_PER")

log = logging.getLogger("moria.collect.oecd")


class OecdQuery(Strict):
    id: str  # Moria's name for the query, e.g. "msti"
    dataflow: str  # "agency,flow,version", e.g. "OECD.STI.STP,DSD_MSTI@DF_MSTI,1.3"; an empty version is the latest
    key: str  # e.g. ".A....." (one position per dimension, `+` for OR, empty for all)
    start_period: str  # e.g. "2000"
    text_values: bool = False
    note: str = ""

    @field_validator("dataflow")
    @classmethod
    def _three_parts(cls, v: str) -> str:
        parts = v.split(",")
        if len(parts) != 3 or not parts[0] or not parts[1]:
            raise ValueError("dataflow must be 'agency,flow,version' (the version may be empty)")
        return v

    @property
    def agency_flow(self) -> str:
        agency, flow, _ = self.dataflow.split(",")
        return f"{agency}:{flow}"


class OecdParams(Strict):
    base_url: str = "https://sdmx.oecd.org/public/rest"
    queries: list[OecdQuery]
    max_series_per_query: int = 5000  # a key that pulls far more than intended fails the run
    max_queries: int = 18  # the OECD's rate limit: as few as 20 data downloads an hour


class OecdSdmxCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = OecdParams.model_validate(card.params)
        ids = [q.id for q in self.params.queries]
        if len(set(ids)) != len(ids):
            raise CollectError("oecd: query ids must be unique")
        if len(ids) > self.params.max_queries:
            raise CollectError(
                f"oecd: {len(ids)} queries, above the card's cap of {self.params.max_queries} (the OECD's rate limit)"
            )

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        queries = self.params.queries[: ctx.limit] if ctx.limit else self.params.queries
        retrieved_at = utc_now().isoformat(timespec="seconds")
        records: list[RawRecord] = []
        empty = 0
        n_series = n_obs = 0
        for i, q in enumerate(queries, start=1):
            url = f"{self.params.base_url}/data/{q.dataflow}/{q.key}"
            resp = ctx.client.get(
                url,
                params={"startPeriod": q.start_period},
                headers={"Accept": ACCEPT},
                retries=1,
                ok_statuses=(200, 404),
            )
            if resp.status_code == 404:  # SDMX answers 404 when a key matches no data
                empty += 1
                ctx.warnings.append(f"oecd query {q.id}: no data for {q.dataflow}/{q.key}")
                log.warning("oecd [%d/%d] %s: no data", i, len(queries), q.id)
                continue
            series = parse_sdmx_csv(resp.text, SERIES_ATTRIBUTES, text_values=q.text_values)
            if len(series) > self.params.max_series_per_query:
                raise CollectError(
                    f"oecd: query {q.id} returned {len(series)} series, above the card's cap of "
                    f"{self.params.max_series_per_query}; narrow its key"
                )
            for s in series:
                payload = {"query_id": q.id, **s}
                records.append(
                    RawRecord(
                        envelope=make_envelope(
                            provider="OECD",
                            source_collection=f"oecd_{q.id}",
                            provider_record_id=f"{q.agency_flow}|{s['series_key']}",
                            kind="observation",
                            family=self.card.family,
                            rings=self.card.rings,
                            domains=self.card.domains,
                            payload=payload,
                            request={"dataflow": q.dataflow, "key": q.key, "startPeriod": q.start_period},
                            retrieval_method="rest:oecd:sdmx-csv",
                            tool_identity=f"moria:{PARSER_VERSION}",
                            licence=self.card.licence,
                            parser_version=PARSER_VERSION,
                            event_at=None,
                            observable_at=retrieved_at,
                            retrieved_at=retrieved_at,
                        ),
                        payload=payload,
                    )
                )
            obs = sum(s["n_obs"] for s in series)
            n_series, n_obs = n_series + len(series), n_obs + obs
            log.info("oecd [%d/%d] %s: %d series, %d observations", i, len(queries), q.id, len(series), obs)
        if queries and empty == len(queries):
            raise CollectError(f"oecd: every query returned no data ({empty})")
        self.counts = {"queries": len(queries), "queries_empty": empty, "series": n_series, "observations": n_obs}
        return records
