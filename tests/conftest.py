"""Shared fixtures. Tests make no network calls: every HTTP exchange goes through httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from moria.config import HttpConfig, SourceCard
from moria.http import PoliteClient
from moria.store import LocalStore


@pytest.fixture
def http_cfg() -> HttpConfig:
    return HttpConfig(user_agent="Moria-test/0", timeout_s=5, max_retries=2, backoff_s=0, default_min_interval_s=0)


def make_client(http_cfg: HttpConfig, handler) -> PoliteClient:
    return PoliteClient(http_cfg, transport=httpx.MockTransport(handler), sleep=lambda _s: None)


@pytest.fixture
def store(tmp_path) -> LocalStore:
    return LocalStore(tmp_path / "store")


def card(adapter: str, params: dict, **overrides) -> SourceCard:
    base = {
        "id": f"test_{adapter}",
        "name": f"Test {adapter}",
        "adapter": adapter,
        "rings": ["core"],
        "domains": ["D1"],
        "family": "policy",
        "cadence": "daily",
        "publication_lag": "same day",
        "coverage": "placeholder",
        "history_start": None,
        "stable_since": None,
        "known_biases": [],
        "revision_policy": "none",
        "licence": "placeholder licence",
        "snapshot_rights": "placeholder",
        "expected_volume": {"min_per_run": 0, "max_per_run": 100},
        "params": params,
    }
    base.update(overrides)
    return SourceCard.model_validate(base)
