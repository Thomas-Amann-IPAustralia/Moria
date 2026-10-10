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
            resp = client.get("https://api.openalex.org/works", params={"per_page": "1", "api_key": key}, retries=1)
            checks.append(Check("api:openalex", "ok", f"HTTP {resp.status_code}"))
        except FetchError as e:
            checks.append(Check("api:openalex", "failed", str(e)))
    else:
        checks.append(Check("api:openalex", "skipped", "no key"))

    probes = {
        "api:gdelt": (
            "https://api.gdeltproject.org/api/v2/doc/doc",
            {"query": "patent", "mode": "artlist", "maxrecords": "1", "format": "json"},
        )
    }
    for card in cards.values():
        if card.adapter == "feed":
            probes[f"source:{card.id}"] = (card.params["url"], None)
        elif card.adapter == "sitemap":
            probes[f"source:{card.id}"] = (card.params["sitemap_url"], None)
        elif card.adapter == "legislation":
            base = card.params.get("base_url", "https://api.prod.legislation.gov.au/v1")
            probes[f"source:{card.id}"] = (f"{base}/Titles", {"$top": "1", "$select": "id"})
    for name, (url, params) in sorted(probes.items()):
        try:
            resp = client.get(url, params=params, retries=1)
            checks.append(Check(name, "ok", f"HTTP {resp.status_code}"))
        except FetchError as e:
            checks.append(Check(name, "failed", str(e)))
    return checks
