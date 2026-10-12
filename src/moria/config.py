"""Configuration: YAML files in config/, validated by pydantic. Unknown keys are errors (SOP §15.3)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"

Ring = Literal["core", "adjacent", "wider_world"]
Family = Literal["research", "patent", "policy", "legal", "news", "social", "statistics", "ipa_internal"]
Cadence = Literal["daily", "weekly", "monthly", "quarterly", "once"]
Adapter = Literal[
    "gdelt",
    "gdelt_gkg",
    "feed",
    "sitemap",
    "legislation",
    "openalex_counts",
    "abs_sdmx",
    "ip_rapid",
    "documents",
    "bigquery_cpc",
    "hf_corpus",
]


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
    adapter: Adapter
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


def _key(phrase: str) -> str:
    return " ".join(phrase.lower().split())


def _check_phrase(phrase: str, where: str) -> None:
    if _key(phrase) in {"ip", "i.p."}:
        raise ValueError(f"{where}: a bare 'IP' term matches IP addresses; use 'intellectual property'")


def _check_synonyms(terms: set[str], synonyms: dict[str, list[str]]) -> None:
    """Synonyms are other wordings of a term, counted as the term itself (D-014): each belongs to one term of this
    file, and none is itself a term."""
    seen: dict[str, str] = {}
    for term, others in synonyms.items():
        if _key(term) not in terms:
            raise ValueError(f"synonyms: {term!r} is not a term in this file")
        if not others:
            raise ValueError(f"synonyms: {term!r} has an empty list")
        for s in others:
            _check_phrase(s, f"synonyms of {term!r}")
            if _key(s) in terms:
                raise ValueError(f"synonyms: {s!r} is already a term; a synonym must be a new wording")
            if _key(s) in seen:
                raise ValueError(f"synonyms: {s!r} is listed under both {seen[_key(s)]!r} and {term!r}")
            seen[_key(s)] = term


class TerritoriesFile(Strict):
    version: int
    search_rules: list[str]
    territories: list[Territory]
    synonyms: dict[str, list[str]] = {}

    @field_validator("territories")
    @classmethod
    def _no_bare_ip(cls, territories: list[Territory]) -> list[Territory]:
        for t in territories:
            for ring in ("core", "adjacent", "wider_world"):
                for term in getattr(t.terms, ring):
                    _check_phrase(term, t.id)
        return territories

    @model_validator(mode="after")
    def _synonyms(self) -> TerritoriesFile:
        _check_synonyms(self.terms(), self.synonyms)
        return self

    def terms(self) -> set[str]:
        return {_key(p) for t in self.territories for ring in ("core", "adjacent", "wider_world")
                for p in getattr(t.terms, ring)}  # fmt: skip


class ThemesFile(Strict):
    version: int
    themes: dict[str, list[str]]
    rings: dict[str, Ring] = {}  # a theme's ring when it is not wider_world (the default)
    synonyms: dict[str, list[str]] = {}

    @model_validator(mode="after")
    def _checks(self) -> ThemesFile:
        for name, phrases in self.themes.items():
            for p in phrases:
                _check_phrase(p, f"theme {name}")
        unknown = set(self.rings) - set(self.themes)
        if unknown:
            raise ValueError(f"rings: unknown themes {sorted(unknown)}")
        _check_synonyms(self.terms(), self.synonyms)
        return self

    def terms(self) -> set[str]:
        return {_key(p) for phrases in self.themes.values() for p in phrases}

    def ring(self, theme: str) -> str:
        return self.rings.get(theme, "wider_world")


def synonym_map(territories: TerritoriesFile, themes: ThemesFile) -> dict[str, tuple[str, ...]]:
    """Every term (lower case) with its synonyms (lower case), from both files. A synonym may not be a term in the
    other file either, and a term's synonyms are listed in one file only."""
    terms = territories.terms() | themes.terms()
    out: dict[str, tuple[str, ...]] = {}
    for source in (territories.synonyms, themes.synonyms):
        for term, others in source.items():
            if _key(term) in out:
                raise ValueError(f"synonyms: {term!r} has synonyms in both territories.yaml and themes.yaml")
            for s in others:
                if _key(s) in terms:
                    raise ValueError(f"synonyms: {s!r} is a term in the other file")
            out[_key(term)] = tuple(_key(s) for s in others)
    owners: dict[str, str] = {}
    for term, others in out.items():
        for s in others:
            if s in owners:
                raise ValueError(f"synonyms: {s!r} is listed under both {owners[s]!r} and {term!r}")
            owners[s] = term
    return out


Pestle = Literal["political", "economic", "social", "technological", "legal", "environmental"]


class TrendSource(Strict):
    doc: str  # a document id in config/sources/foresight_syntheses.yaml
    item: str  # the document's own name for the trend


class KnownTrend(Strict):
    id: str
    name: str
    statement: str
    pestle: list[Pestle]
    rings: list[Ring]
    sources: list[TrendSource]


class BaselineDocument(Strict):
    read: Literal["full", "partial", "not_read"]
    items: int | None = None
    note: str = ""


class BaselineFile(Strict):
    """The known-trends baseline (design §2.5): what is already widely expected, drafted from the syntheses."""

    version: int
    status: Literal["draft", "confirmed"]
    documents: dict[str, BaselineDocument]
    trends: list[KnownTrend]

    @field_validator("trends")
    @classmethod
    def _unique_ids(cls, trends: list[KnownTrend]) -> list[KnownTrend]:
        ids = [t.id for t in trends]
        if len(set(ids)) != len(ids):
            raise ValueError("known-trend ids must be unique")
        return trends

    def check_sources(self) -> None:
        """Every trend cites only documents that were read."""
        for t in self.trends:
            for s in t.sources:
                doc = self.documents.get(s.doc)
                if doc is None or doc.read == "not_read":
                    raise ValueError(f"{t.id} cites {s.doc!r}, which is not a document read for the baseline")


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


def load_baseline(config_dir: Path = CONFIG_DIR) -> BaselineFile:
    baseline = BaselineFile.model_validate(_load_yaml(config_dir / "baseline.yaml"))
    baseline.check_sources()
    return baseline


def config_hash(*models: BaseModel) -> str:
    """SHA-256 of the canonical JSON of the given config models: what a manifest records."""
    blob = json.dumps([m.model_dump(mode="json") for m in models], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()
