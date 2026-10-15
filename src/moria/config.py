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
    "listpage",
    "xlsx",
    "zip_csv",
    "oecd_sdmx",
    "json_list",
    "delimited_csv",
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


# A trend or a citation Claude drafts stays "proposed" until the owner confirms it (D-014, D-020)
Confirmation = Literal["confirmed", "proposed"]


class TrendSource(Strict):
    doc: str  # a document id in config/sources/foresight_syntheses.yaml
    item: str  # the document's own name for the trend
    status: Confirmation = "confirmed"


class KnownTrend(Strict):
    id: str
    name: str
    statement: str
    pestle: list[Pestle]
    rings: list[Ring]
    sources: list[TrendSource]
    status: Confirmation = "confirmed"


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


class NormaliseConfig(Strict):
    summary_chars: int
    text_chars: int
    near_future_days: int


class DedupConfig(Strict):
    cosine: float
    window_days: int
    title_min_words: int
    max_neighbours: int


class EmbedConfig(Strict):
    model: str
    revision: str
    files: dict[str, str]  # path in the model repo -> SHA-256
    dim: int
    max_tokens: int
    text_chars: int
    batch_size: int
    cache_dir: str


class KeyphrasesConfig(Strict):
    ngram_max: int
    min_df: int
    max_df: float
    max_features: int
    top_k: int
    text_chars: int


class IndexConfig(Strict):
    text_chars: int


class TagsConfig(Strict):
    backend: Literal["zeroshot"]
    version: str
    temperature: float


class FeaturesConfig(Strict):
    """config/features.yaml: the settings of normalise, dedup, embed, keyphrases, the index and the tags."""

    version: int
    normalise: NormaliseConfig
    dedup: DedupConfig
    embed: EmbedConfig
    keyphrases: KeyphrasesConfig
    index: IndexConfig
    tags: TagsConfig


class CodebookLabel(Strict):
    description: str
    examples: list[str] = []


class CodebookSet(Strict):
    choice: Literal["single", "multi"]
    labels: dict[str, CodebookLabel]


class CodebookFile(Strict):
    """config/codebook.yaml: the labels of the descriptive tags (ring, domain, PESTLE origin, rights)."""

    version: int
    status: Confirmation
    sets: dict[str, CodebookSet]


def load_features(config_dir: Path = CONFIG_DIR) -> FeaturesConfig:
    return FeaturesConfig.model_validate(_load_yaml(config_dir / "features.yaml"))


def load_codebook(config_dir: Path = CONFIG_DIR) -> CodebookFile:
    return CodebookFile.model_validate(_load_yaml(config_dir / "codebook.yaml"))


Freq = Literal["M", "Q", "A", "D"]


class LagRule(Strict):
    prefix: str | None = None
    pattern: str | None = None  # a regular expression searched in the series id
    periods: int

    @model_validator(mode="after")
    def _one(self) -> LagRule:
        if (self.prefix is None) == (self.pattern is None):
            raise ValueError("a lag rule has a prefix or a pattern")
        return self

    def matches(self, series_id: str) -> bool:
        import re

        return series_id.startswith(self.prefix) if self.prefix else bool(re.search(self.pattern, series_id))


class ChangePointConfig(Strict):
    penalty_factor: float
    min_size: dict[Freq, int]
    min_size_level: dict[Freq, int]
    recent: dict[Freq, int]
    level_frequencies: list[Freq]


class BootstrapConfig(Strict):
    reps: int
    seed: int


class SeriesSurgeConfig(Strict):
    window: dict[Freq, int]
    baseline: dict[Freq, int]
    min_count: int
    max_expected: float
    min_ratio: float


class DimsRule(Strict):
    source: str
    dims: dict[str, str]


class SeriesDetectConfig(Strict):
    sources: list[str]
    windows: dict[Freq, list[int]]
    min_coverage: float
    min_mean_count: float
    alpha: float
    trend_min_windows: int
    anomaly_alpha: float
    anomaly_min_change: float
    accel_min_change: float
    anomaly_baseline: dict[Freq, int]
    stale_after: dict[Freq, int]
    change_points: ChangePointConfig
    bootstrap: BootstrapConfig
    surge: SeriesSurgeConfig
    lags: list[LagRule] = []
    exclude_months: dict[str, list[int]] = {}
    divergence_reference: dict[str, str] = {}
    scopes: dict[str, list[str]] = {}
    exclude_dims: list[DimsRule] = []

    def tested(self, source: str, scope: str | None, dims: dict) -> bool:
        if source in self.scopes and scope not in self.scopes[source]:
            return False
        return not any(r.source == source and all(dims.get(k) == v for k, v in r.dims.items())
                       for r in self.exclude_dims)  # fmt: skip

    @field_validator("windows")
    @classmethod
    def _three_windows(cls, windows: dict[str, list[int]]) -> dict[str, list[int]]:
        for f, ws in windows.items():
            if len(ws) != 3 or ws != sorted(ws):
                raise ValueError(f"windows[{f}]: three windows, shortest first")
        return windows

    def lag(self, series_id: str) -> int:
        return next((r.periods for r in self.lags if r.matches(series_id)), 0)


class ClusterConfig(Strict):
    k: int
    seed: int
    batch: int
    sample: int
    name_terms: int


class NoveltyConfig(Strict):
    neighbours: int
    min_baseline: int
    baseline_sample: int
    threshold: float
    micro_distance: float


class DocumentsDetectConfig(Strict):
    window_days: int
    baseline_days: int
    credible_families: list[Family]
    min_items: int
    min_sources: int
    new_term_min_df: int
    cross_family_min: int
    cross_family_max_before: int
    surge_min_ratio: float
    surge_max_expected: float
    surge_min_baseline_items: int
    alpha: float
    combination_min_items: int
    combination_min_each_before: int
    combination_lift_ratio: float
    clusters: ClusterConfig
    novelty: NoveltyConfig
    ipr_window_months: int
    ipr_baseline_months: int
    ipr_min_applicants: int


class ArtefactsConfig(Strict):
    coverage_change: float
    duplicate_ratio: float
    news_cycle_days: int
    primary_families: list[Family]


class ShortHorizonConfig(Strict):
    months: list[int]
    baseline_factor: int  # the baseline: this many times the horizon, at least the series' anomaly baseline
    min_baseline: float  # share of the baseline's periods present
    alpha: float
    min_change: float


class MediumHorizonConfig(Strict):
    months: list[int]
    min_points: int


class LongHorizonConfig(Strict):
    months: list[int]
    min_points: int
    min_segment_months: int
    penalty_factor: float  # the change-point penalty over long windows, times BIC's
    autocorrelation: bool  # inflate Mann-Kendall's variance by the residuals' lag-1 autocorrelation


class HorizonsConfig(Strict):
    """The SignalBoost proposal's item 1 (D-025): horizons in months, each read by the method that suits it."""

    short: ShortHorizonConfig
    medium: MediumHorizonConfig
    long: LongHorizonConfig
    by_source: dict[str, list[int]] = {}

    @model_validator(mode="after")
    def _disjoint(self) -> HorizonsConfig:
        every = self.short.months + self.medium.months + self.long.months
        if len(set(every)) != len(every) or any(m <= 0 for m in every):
            raise ValueError("horizons: each horizon (positive months) belongs to one method")
        for src, ms in self.by_source.items():
            if not set(ms) <= set(every):
                raise ValueError(f"horizons.by_source[{src}]: {sorted(set(ms) - set(every))} is not a horizon")
        return self

    def months(self, source: str) -> list[int]:
        every = sorted(self.short.months + self.medium.months + self.long.months)
        return sorted(self.by_source.get(source, every))

    def method(self, months: int) -> str:
        return ("short" if months in self.short.months else "medium" if months in self.medium.months
                else "long")  # fmt: skip


class CouplingConfig(Strict):
    min_points: int
    max_points: int
    alpha: float
    established: float
    broken: float


class ContextConfig(Strict):
    """The proposal's item 2 (D-025): the latest value against a model of its context."""

    baseline: dict[Freq, int]
    min_baseline: float
    peers: int
    peer_min_corr: float
    ridge: float
    alpha: float
    min_change: float
    explained_share: float
    coupling: CouplingConfig


class RelationshipsConfig(Strict):
    """The proposal's item 3 (D-025): established associations that break down, and jurisdictions by class."""

    fade_min_baseline: int
    fade_min_expected: float
    fade_ratio: float
    fade_min_each_window: int
    jurisdictions: bool


class RedundancyConfig(Strict):
    min_corr: float
    min_points: int


class InjectionsConfig(Strict):
    spike: float
    shift: float
    slope: float
    structural: float
    contextual: float
    volume_jump: float
    duplicated_period: float


class BacktestConfig(Strict):
    every_months: int
    back_months: int
    confirm_months: int


class RetainConfig(Strict):
    min_incremental: float
    null_margin: float
    max_null_rate: float
    max_artefact_excess: float


class EvaluationConfig(Strict):
    """The proposal's item 4 (D-025): `moria eval detectors`, and the rules committed before its first run."""

    seed: int
    per_class: int
    injections: InjectionsConfig
    placebo_repeats: int
    backtest: BacktestConfig
    retain: RetainConfig


NEW_DETECTORS = ("short_shift", "long_trend", "structural_shift", "contextual_anomaly", "decoupling",
                 "fading_combination", "jurisdiction_shift")  # fmt: skip


class DetectConfig(Strict):
    """config/detect.yaml: the detectors' windows, tests and thresholds, and the artefact checks' rules."""

    version: int
    series: SeriesDetectConfig
    documents: DocumentsDetectConfig
    artefacts: ArtefactsConfig
    horizons: HorizonsConfig
    context: ContextConfig
    relationships: RelationshipsConfig
    redundancy: RedundancyConfig
    evaluation: EvaluationConfig
    new_detectors: dict[str, bool]

    @field_validator("new_detectors")
    @classmethod
    def _known(cls, v: dict[str, bool]) -> dict[str, bool]:
        if set(v) != set(NEW_DETECTORS):
            raise ValueError(f"new_detectors: exactly {', '.join(NEW_DETECTORS)}")
        return v

    def on(self, detector: str) -> bool:
        """Whether a SignalBoost detector adds candidates (it is measured and evaluated either way)."""
        return self.new_detectors.get(detector, False)


def load_detect(config_dir: Path = CONFIG_DIR) -> DetectConfig:
    return DetectConfig.model_validate(_load_yaml(config_dir / "detect.yaml"))
