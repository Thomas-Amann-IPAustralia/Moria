"""Australian Bureau of Statistics headline series, through the ABS Data API (SDMX 2.1 REST, CSV with labels).

Each query in the card names a dataflow, an SDMX key (dimension codes joined by dots, `+` for OR, empty for all) and a
start period. Every series a query returns becomes one record holding all its observations, with each dimension's
code and label, its unit and each observation's status. ABS revises figures, so each run is a vintage: an unchanged
series gets the same evidence id run after run, and a revised one gets a new id (design §5.1, revision_policy).

Business entries and exits (CABEE) and business R&D (BERD) are published as spreadsheets, not through this API, so
they are not covered here.
"""

from __future__ import annotations

import csv
import io
import logging

from ..config import Strict
from ..records import RawRecord, make_envelope, utc_now
from .base import CollectContext, CollectError

PARSER_VERSION = "abs-sdmx-v1"
ACCEPT = "application/vnd.sdmx.data+csv;labels=both"
TIME = "TIME_PERIOD"
VALUE = "OBS_VALUE"
SERIES_ATTRIBUTES = ("UNIT_MEASURE", "UNIT_MULT", "DECIMALS")

log = logging.getLogger("moria.collect.abs")


class AbsQuery(Strict):
    id: str  # Moria's name for the query, e.g. "labour_force"
    dataflow: str  # e.g. "LF" or "ABS,LF,1.0.0"
    key: str  # e.g. "M13.3.1599.20.AUS.M"
    start_period: str  # e.g. "1978" or "2010-01"
    note: str = ""


class AbsParams(Strict):
    base_url: str = "https://data.api.abs.gov.au/rest"
    queries: list[AbsQuery]
    max_series_per_query: int = 2000  # a key that pulls far more than intended fails the run


def _split(cell: str) -> tuple[str, str]:
    """'M13: Unemployment rate' -> ('M13', 'Unemployment rate'); a cell without a label keeps an empty label."""
    code, _, label = cell.partition(": ")
    return code.strip(), label.strip()


def _value(cell: str) -> float | None:
    cell = cell.strip()
    if not cell:
        return None
    try:
        return float(cell)
    except ValueError as e:
        raise CollectError(f"abs: a non-numeric observation value {cell[:30]!r}") from e


def parse_sdmx_csv(text: str) -> list[dict]:
    """Group SDMX-CSV rows (labels=both) into series. Dimension columns are those between DATAFLOW and TIME_PERIOD."""
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None:
        return []
    ids = [_split(h)[0] for h in header]
    if not ids or ids[0] != "DATAFLOW" or TIME not in ids or VALUE not in ids:
        raise CollectError(f"abs: unexpected CSV header {header[:4]}")
    t, v = ids.index(TIME), ids.index(VALUE)
    st = ids.index("OBS_STATUS") if "OBS_STATUS" in ids else None
    dims = list(range(1, t))
    series: dict[tuple[str, ...], dict] = {}
    for row in reader:
        if not row:
            continue
        if len(row) != len(header):
            raise CollectError(f"abs: a row has {len(row)} columns, the header {len(header)}")
        codes = tuple(_split(row[i])[0] for i in dims)
        s = series.get(codes)
        if s is None:
            s = series[codes] = {
                "dataflow": row[0],
                "series_key": ".".join(codes),
                "dimensions": {ids[i]: dict(zip(("code", "label"), _split(row[i]), strict=True)) for i in dims},
                "attributes": {},
                "observations": [],
            }
            for i, name in enumerate(ids):
                if name in SERIES_ATTRIBUTES and row[i]:
                    s["attributes"][name] = dict(zip(("code", "label"), _split(row[i]), strict=True))
        status = row[st].strip() if st is not None else ""
        s["observations"].append([row[t].strip(), _value(row[v]), _split(status)[0] or None])
    out = []
    for s in series.values():
        s["observations"].sort(key=lambda o: o[0])
        s["n_obs"] = len(s["observations"])
        s["first_period"], s["last_period"] = s["observations"][0][0], s["observations"][-1][0]
        out.append(s)
    return sorted(out, key=lambda s: s["series_key"])


def _flow_id(dataflow: str) -> str:
    # "ABS,LF,1.0.0" -> "LF"; "LF" -> "LF"
    parts = dataflow.split(",")
    return parts[1] if len(parts) >= 2 else parts[0]


class AbsSdmxCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = AbsParams.model_validate(card.params)
        ids = [q.id for q in self.params.queries]
        if len(set(ids)) != len(ids):
            raise CollectError("abs: query ids must be unique")

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        queries = self.params.queries[: ctx.limit] if ctx.limit else self.params.queries
        retrieved_at = utc_now().isoformat(timespec="seconds")
        records: list[RawRecord] = []
        empty = 0
        for i, q in enumerate(queries, start=1):
            url = f"{self.params.base_url}/data/{q.dataflow}/{q.key}"
            resp = ctx.client.get(
                url, params={"startPeriod": q.start_period}, headers={"Accept": ACCEPT}, ok_statuses=(200, 404)
            )
            if resp.status_code == 404:  # SDMX answers 404 when a key matches no data
                empty += 1
                ctx.warnings.append(f"abs query {q.id}: no data for {q.dataflow}/{q.key}")
                log.warning("abs [%d/%d] %s: no data", i, len(queries), q.id)
                continue
            series = parse_sdmx_csv(resp.text)
            if len(series) > self.params.max_series_per_query:
                raise CollectError(
                    f"abs: query {q.id} returned {len(series)} series, above the card's cap of "
                    f"{self.params.max_series_per_query}; narrow its key"
                )
            flow = _flow_id(q.dataflow)
            for s in series:
                payload = {"query_id": q.id, **s}
                records.append(
                    RawRecord(
                        envelope=make_envelope(
                            provider="Australian Bureau of Statistics",
                            source_collection=f"abs_{flow.lower()}",
                            provider_record_id=f"{flow}|{s['series_key']}",
                            kind="observation",
                            family=self.card.family,
                            rings=self.card.rings,
                            domains=self.card.domains,
                            payload=payload,
                            request={"dataflow": q.dataflow, "key": q.key, "startPeriod": q.start_period},
                            retrieval_method="rest:abs:sdmx-csv",
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
            n_obs = sum(s["n_obs"] for s in series)
            log.info("abs [%d/%d] %s: %d series, %d observations", i, len(queries), q.id, len(series), n_obs)
        if queries and empty == len(queries):
            raise CollectError(f"abs: every query returned no data ({empty})")
        return records
