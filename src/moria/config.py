"""Configuration: YAML files in config/, validated by pydantic. Unknown keys are errors (SOP §15.3)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"

Ring = Literal["core", "adjacent", "wider_world"]
Family = Literal["research", "patent", "policy", "legal", "news", "social", "statistics", "ipa_internal"]
Cadence = Literal["daily", "weekly", "monthly", "quarterly"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StoreConfig(Strict):
    backend: Literal["local", "r2"]
    bucket: str
    local_root: str = Field(description="Directory for the local store, relative to the repo root")
    # Names of the environment variables that hold credentials. Values are never read into config or logged.
    account_id_env: str
    access_key_id_env: str
    secret_access_key_env: str


class HttpConfig(Strict):
    user_agent: str
    timeout_s: float = 60.0
    max_retries: int = 3
    backoff_s: float = 5.0
    default_min_interval_s: float = 1.0
    host_min_interval_s: dict[str, float] = {}


class MoriaConfig(Strict):
    store: StoreConfig
    http: HttpConfig
    secrets: dict[str, str] = Field(description="Logical name -> environment variable name")


class VolumeBand(Strict):
    min_per_run: int
    max_per_run: int


class SourceCard(Strict):
    """A source's card (design §5.1). `params` is validated by the source's adapter."""

    id: str
    name: str
    adapter: Literal["gdelt", "feed", "sitemap", "legislation"]
    rings: list[Ring]
    domains: list[str]
    family: Family
    cadence: Cadence
    publication_lag: str
    coverage: str
    history_start: str | None
    stable_since: str | None
    breaks: list[str] = []
    known_biases: list[str]
    revision_policy: str
    licence: str
    snapshot_rights: str
    expected_volume: VolumeBand
    params: dict[str, Any] = {}


class TerritoryTerms(Strict):
    core: list[str]
    adjacent: list[str]
    wider_world: list[str]


class Territory(Strict):
    id: str
    name: str
    aim: str
    description: str
    pathways: list[Literal["P1", "P2", "P3", "P4", "P5", "P6"]]
    terms: TerritoryTerms
    exclude: list[str] = []
    ipr_indicators: list[str] = []


class TerritoriesFile(Strict):
    version: int
    search_rules: list[str]
    territories: list[Territory]

    @field_validator("territories")
    @classmethod
    def _no_bare_ip(cls, territories: list[Territory]) -> list[Territory]:
        for t in territories:
            for ring in ("core", "adjacent", "wider_world"):
                for term in getattr(t.terms, ring):
                    if term.strip().lower() in {"ip", "i.p."}:
                        raise ValueError(f"{t.id}: a bare 'IP' term matches IP addresses; use 'intellectual property'")
        return territories


class ThemesFile(Strict):
    version: int
    themes: dict[str, list[str]]


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(config_dir: Path = CONFIG_DIR) -> MoriaConfig:
    return MoriaConfig.model_validate(_load_yaml(config_dir / "moria.yaml"))


def load_sources(config_dir: Path = CONFIG_DIR) -> dict[str, SourceCard]:
    cards: dict[str, SourceCard] = {}
    for path in sorted((config_dir / "sources").glob("*.yaml")):
        card = SourceCard.model_validate(_load_yaml(path))
        if card.id != path.stem:
            raise ValueError(f"{path.name}: id {card.id!r} must match the file name")
        cards[card.id] = card
    return cards


def load_territories(config_dir: Path = CONFIG_DIR) -> TerritoriesFile:
    return TerritoriesFile.model_validate(_load_yaml(config_dir / "territories.yaml"))


def load_themes(config_dir: Path = CONFIG_DIR) -> ThemesFile:
    return ThemesFile.model_validate(_load_yaml(config_dir / "themes.yaml"))


def config_hash(*models: BaseModel) -> str:
    """SHA-256 of the canonical JSON of the given config models: what a manifest records."""
    blob = json.dumps([m.model_dump(mode="json") for m in models], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()
