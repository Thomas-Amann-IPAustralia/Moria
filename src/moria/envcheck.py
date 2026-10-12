"""The environment check (SOP §15.4): which keys are present, and one cheap call to each service.

Values are never printed: a check reports present or missing, and the HTTP status or error class of its call.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .config import MoriaConfig, SourceCard
from .http import FetchError, PoliteClient
from .store import R2Store, StoreError


@dataclass
class Check:
    name: str
    status: str  # ok | failed | skipped
    detail: str


def run_checks(cfg: MoriaConfig, cards: dict[str, SourceCard], client: PoliteClient) -> list[Check]:
    checks: list[Check] = []
    for logical, env_name in sorted(cfg.secrets.items()):
        present = bool(os.environ.get(env_name))
        checks.append(
            Check(
                f"secret:{logical}", "ok" if present else "skipped", f"{env_name} {'present' if present else 'missing'}"
            )
        )

    try:
        store = R2Store(cfg.store)
        store.list("manifests/")
        checks.append(Check("store:r2", "ok", f"listed bucket {cfg.store.bucket!r}"))
    except StoreError as e:
        checks.append(Check("store:r2", "skipped", str(e)))
    except Exception as e:
        checks.append(Check("store:r2", "failed", type(e).__name__))

    key = os.environ.get(cfg.secrets.get("openalex", ""), "")
    if key:
        try:
            # The free /rate-limit endpoint: proves the key works and reports the day's credits, at no cost
            resp = client.get(
                "https://api.openalex.org/rate-limit", headers={"Authorization": f"Bearer {key}"}, retries=1
            )
            left = resp.json().get("rate_limit", {}).get("credits_remaining", "?")
            checks.append(Check("api:openalex", "ok", f"HTTP {resp.status_code}; {left} credits left today"))
        except (FetchError, ValueError) as e:
            checks.append(Check("api:openalex", "failed", str(e) or type(e).__name__))
    else:
        checks.append(Check("api:openalex", "skipped", "no key"))

    project = os.environ.get(cfg.secrets.get("gcp_project", ""), "")
    has_key = bool(
        os.environ.get(cfg.secrets.get("gcp_sa_key", ""), "") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    )
    if project and has_key:
        try:
            from .collectors.bigquery import API, default_credentials

            creds = default_credentials()
            if not creds.valid:
                from .collectors.bigquery import _AuthRequest

                creds.refresh(_AuthRequest())
            # A dry run is free: it proves the credentials and the project without scanning anything
            resp = client.post(
                f"{API}/projects/{project}/queries",
                json={"query": "SELECT 1", "useLegacySql": False, "dryRun": True},
                headers={"Authorization": f"Bearer {creds.token}"},
                retries=1,
            )
            checks.append(Check("api:bigquery", "ok", f"dry run HTTP {resp.status_code}"))
        except Exception as e:
            checks.append(Check("api:bigquery", "failed", type(e).__name__))
    else:
        checks.append(Check("api:bigquery", "skipped", "no GCP project or credentials (docs/setup.md)"))

    probes: dict[str, tuple[str, dict | None]] = {}
    for card in cards.values():
        if card.adapter == "gdelt_gkg":
            base = card.params.get("base_url", "https://data.gdeltproject.org/gdeltv2")
            probes[f"source:{card.id}"] = (f"{base}/lastupdate.txt", None)
        elif card.adapter == "feed":
            probes[f"source:{card.id}"] = (card.params["url"], None)
        elif card.adapter == "sitemap":
            probes[f"source:{card.id}"] = (card.params["sitemap_url"], None)
        elif card.adapter == "legislation":
            base = card.params.get("base_url", "https://api.prod.legislation.gov.au/v1")
            probes[f"source:{card.id}"] = (f"{base}/Titles", {"$top": "1", "$select": "id"})
        elif card.adapter == "abs_sdmx" and card.params.get("queries"):
            base = card.params.get("base_url", "https://data.api.abs.gov.au/rest")
            flow = card.params["queries"][0]["dataflow"].split(",")
            probes[f"source:{card.id}"] = (f"{base}/dataflow/ABS/{flow[1] if len(flow) > 1 else flow[0]}", None)
    for name, (url, params) in sorted(probes.items()):
        try:
            resp = client.get(url, params=params, retries=1)
            checks.append(Check(name, "ok", f"HTTP {resp.status_code}"))
        except FetchError as e:
            checks.append(Check(name, "failed", str(e)))
    return checks
