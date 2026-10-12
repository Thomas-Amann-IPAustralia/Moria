"""Patent families counted by CPC subclass and priority year, worldwide and with an Australian member, from Google
Patents Public Datasets on BigQuery (design §5.2: "aggregate SQL, dry-run first and capped").

Spending guard (CLAUDE.md: nothing in the machinery spends money):
- the card defaults to `dry_run: true`: the run asks BigQuery how many bytes the query would scan, records that in
  the manifest, and stops. The owner switches it off once the estimate is known (D-011);
- every real query carries `maximumBytesBilled`, so BigQuery refuses one that would scan more than the cap;
- the project should be a BigQuery sandbox, with no billing account, so nothing can ever be billed (docs/setup.md).

Credentials are Google's application default credentials: whatever GOOGLE_APPLICATION_CREDENTIALS points to (a
service-account key, or a workload identity federation file from GitHub Actions). The project id comes from the
environment variable named in the card. Neither is ever logged.
"""

from __future__ import annotations

import logging
import os
import re
import time

import httpx

from ..config import Strict
from ..records import RawRecord, make_envelope, sha256_hex, utc_now
from .base import CollectContext, CollectError

PARSER_VERSION = "bigquery-cpc-v1"
API = "https://bigquery.googleapis.com/bigquery/v2"
SCOPE = "https://www.googleapis.com/auth/bigquery"

QUERY = """
-- Patent families by CPC subclass and earliest priority year: all families, and families with an Australian member
WITH pub AS (
  SELECT
    family_id,
    country_code,
    priority_date,
    ARRAY(SELECT DISTINCT SUBSTR(c.code, 1, 4) FROM UNNEST(cpc) AS c WHERE c.code IS NOT NULL) AS subclasses
  FROM `{table}`
  WHERE family_id IS NOT NULL AND family_id != '-1' AND priority_date > 0
),
family AS (
  SELECT
    family_id,
    DIV(MIN(priority_date), 10000) AS priority_year,
    LOGICAL_OR(country_code = 'AU') AS has_au,
    ARRAY_CONCAT_AGG(subclasses) AS subclasses
  FROM pub
  GROUP BY family_id
)
SELECT subclass, priority_year, COUNT(*) AS families, COUNTIF(has_au) AS au_families
FROM family, UNNEST(ARRAY(SELECT DISTINCT s FROM UNNEST(family.subclasses) AS s)) AS subclass
WHERE priority_year >= @from_year
GROUP BY subclass, priority_year
ORDER BY subclass, priority_year
""".strip()

log = logging.getLogger("moria.collect.bigquery")


class BigQueryCpcParams(Strict):
    project_env: str = "GCP_PROJECT_ID"  # the environment variable's name; its value is never logged
    table: str = "patents-public-data.patents.publications"
    from_year: int = 2000
    location: str = "US"
    dry_run: bool = True  # only estimate the bytes until the owner switches this off
    max_bytes_billed: int = 200_000_000_000  # 200 GB a run; the free tier is 1 TiB of queries a month
    page_size: int = 20000
    wait_s: int = 900  # how long to wait for the query to finish


def default_credentials():
    """Google's application default credentials, scoped to BigQuery. Raises CollectError when there are none."""
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError

    try:
        credentials, _ = google.auth.default(scopes=[SCOPE])
    except DefaultCredentialsError as e:
        raise CollectError("bigquery: no Google credentials (set GOOGLE_APPLICATION_CREDENTIALS; docs/setup.md)") from e
    return credentials


class _AuthRequest:
    """google-auth's transport interface over httpx, so token refreshes follow the environment's proxy settings."""

    def __init__(self):
        self._client = httpx.Client(timeout=60)

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        resp = self._client.request(method, url, content=body, headers=headers, timeout=timeout or 60)
        return _AuthResponse(resp)


def _auth_response_base():
    from google.auth.transport import Response

    return Response


class _AuthResponse(_auth_response_base()):
    def __init__(self, resp: httpx.Response):
        self._resp = resp

    @property
    def status(self) -> int:
        return self._resp.status_code

    @property
    def headers(self) -> dict:
        return dict(self._resp.headers)

    @property
    def data(self) -> bytes:
        return self._resp.content


class BigQueryCpcCollector:
    parser_version = PARSER_VERSION
    credentials_factory = staticmethod(default_credentials)  # tests replace this

    def __init__(self, card):
        self.card = card
        self.params = BigQueryCpcParams.model_validate(card.params)
        if not re.fullmatch(r"[a-z0-9-]+\.[a-z0-9_]+\.[a-z0-9_]+", self.params.table):
            raise CollectError(f"bigquery: an unexpected table name {self.params.table!r}")
        self.counts: dict[str, int] = {}

    def _headers(self) -> dict[str, str]:
        creds = self.credentials_factory()
        if not getattr(creds, "valid", False):
            creds.refresh(_AuthRequest())
        return {"Authorization": f"Bearer {creds.token}"}

    def _project(self) -> str:
        project = os.environ.get(self.params.project_env, "")
        if not project:
            raise CollectError(f"bigquery: {self.params.project_env} is not set (docs/setup.md)")
        return project

    def _body(self, dry_run: bool) -> dict:
        return {
            "query": QUERY.format(table=self.params.table),
            "useLegacySql": False,
            "dryRun": dry_run,
            "location": self.params.location,
            "maximumBytesBilled": str(self.params.max_bytes_billed),
            "maxResults": self.params.page_size,
            "timeoutMs": 60_000,
            "parameterMode": "NAMED",
            "queryParameters": [
                {
                    "name": "from_year",
                    "parameterType": {"type": "INT64"},
                    "parameterValue": {"value": str(self.params.from_year)},
                }
            ],
        }

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        project, headers = self._project(), self._headers()
        url = f"{API}/projects/{project}/queries"
        estimate = ctx.client.post(url, json=self._body(dry_run=True), headers=headers).json()
        planned = int(estimate.get("totalBytesProcessed") or 0)
        self.counts["bytes_estimated"] = planned
        log.info(
            "bigquery: the query would scan %.1f GB (cap %.0f GB)", planned / 1e9, self.params.max_bytes_billed / 1e9
        )
        if planned > self.params.max_bytes_billed:
            raise CollectError(
                f"bigquery: the query would scan {planned / 1e9:.1f} GB, above the card's cap of "
                f"{self.params.max_bytes_billed / 1e9:.0f} GB"
            )
        if self.params.dry_run:
            ctx.warnings.append(f"bigquery: dry run only; the query would scan {planned / 1e9:.1f} GB (D-011)")
            return []

        resp = ctx.client.post(url, json=self._body(dry_run=False), headers=headers).json()
        job = resp.get("jobReference", {})
        started = time.monotonic()
        while not resp.get("jobComplete"):
            if time.monotonic() - started > self.params.wait_s:
                raise CollectError(f"bigquery: the query did not finish within {self.params.wait_s}s")
            resp = ctx.client.get(
                f"{API}/projects/{project}/queries/{job['jobId']}",
                params={
                    "location": job.get("location", self.params.location),
                    "timeoutMs": "60000",
                    "maxResults": str(self.params.page_size),
                },
                headers=headers,
            ).json()
        self.counts["bytes_processed"] = int(resp.get("totalBytesProcessed") or 0)
        self.counts["bytes_billed"] = int(resp.get("totalBytesBilled") or 0)
        self.counts["cache_hit"] = int(bool(resp.get("cacheHit")))
        names = [f["name"] for f in resp.get("schema", {}).get("fields", [])]
        rows = list(resp.get("rows", []))
        token = resp.get("pageToken")
        while token:
            page = ctx.client.get(
                f"{API}/projects/{project}/queries/{job['jobId']}",
                params={
                    "location": job.get("location", self.params.location),
                    "pageToken": token,
                    "maxResults": str(self.params.page_size),
                },
                headers=headers,
            ).json()
            rows.extend(page.get("rows", []))
            token = page.get("pageToken")
        if int(resp.get("totalRows", len(rows))) != len(rows):
            raise CollectError(f"bigquery: read {len(rows)} rows of {resp.get('totalRows')}")
        return self._records(ctx, names, rows)

    def _records(self, ctx: CollectContext, names: list[str], rows: list[dict]) -> list[RawRecord]:
        by_subclass: dict[str, list[list[int]]] = {}
        for row in rows:
            values = dict(zip(names, (cell.get("v") for cell in row["f"]), strict=True))
            by_subclass.setdefault(values["subclass"], []).append(
                [int(values["priority_year"]), int(values["families"]), int(values["au_families"])]
            )
        retrieved_at = utc_now().isoformat(timespec="seconds")
        query_hash = sha256_hex(QUERY)
        records = []
        for subclass, years in sorted(by_subclass.items()):
            payload = {
                "cpc_subclass": subclass,
                "years": sorted(years),  # [priority year, families, families with an AU member]
                "table": self.params.table,
                "query_sha256": query_hash,
            }
            records.append(
                RawRecord(
                    envelope=make_envelope(
                        provider="Google Patents Public Datasets (BigQuery)",
                        source_collection="patents_cpc_family_counts",
                        provider_record_id=subclass,
                        kind="observation",
                        family=self.card.family,
                        rings=self.card.rings,
                        domains=self.card.domains,
                        payload=payload,
                        request={
                            "table": self.params.table,
                            "from_year": self.params.from_year,
                            "query_sha256": query_hash,
                        },
                        retrieval_method="bigquery:query",
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
        return records
