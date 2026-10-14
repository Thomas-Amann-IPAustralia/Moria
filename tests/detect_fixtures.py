"""Hand-built evidence layers for day 4's tests: upstream stage outputs written straight into a LocalStore with
passed manifests, so the detectors read them through the same checks as real runs. Numbers are synthetic and text is
placeholder."""

from __future__ import annotations

import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np

from moria.manifest import Manifest
from moria.tables import OBSERVATIONS, SERIES, upload, write_rows
from moria.text import period_start

AS_OF = date(2026, 10, 14)
VINTAGE = datetime(2026, 10, 12, tzinfo=UTC)


def put_stage(store, command: str, tables: dict[str, tuple[list[dict], object, tuple]], params: dict | None = None):
    """A passed run of `command` whose outputs are these tables: key -> (rows, schema, sort)."""
    m = Manifest(command=command)
    m.params = params or {}
    with tempfile.TemporaryDirectory() as tmp:
        for key, (rows, schema, sort) in sorted(tables.items()):
            path = Path(tmp) / key.replace("/", "_")
            write_rows(rows, schema, path, sort)
            upload(store, m, key, path)
    return m.finish(store, "passed")


def months(start: str, n: int) -> list[str]:
    y, mo = int(start[:4]), int(start[5:7])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{mo:02d}")
        mo += 1
        if mo == 13:
            y, mo = y + 1, 1
    return out


def obs_rows(series_id: str, source: str, values: dict[str, float]) -> list[dict]:
    rows = []
    for period, v in sorted(values.items()):
        kind, start = period_start(period)
        rows.append({"series_id": series_id, "source": source, "period": period, "period_kind": kind,
                     "period_start": start, "value": float(v), "value_text": None, "status": None,
                     "vintage_at": VINTAGE})  # fmt: skip
    return rows


def series_row(series_id: str, source: str, label: str, scope: str, family: str, rings: list[str],
               frequency: str, unit: str = "works", dims: str = "{}") -> dict:  # fmt: skip
    return {"series_id": series_id, "source": source, "provider": "test", "source_collection": source,
            "label": label, "measure": "m", "unit": unit, "frequency": frequency, "scope": scope, "dimensions": dims,
            "family": family, "rings": rings, "domains": ["D3"], "licence": "test", "n_obs": 1, "first_period": "",
            "last_period": "", "n_vintages": 1, "first_seen_at": VINTAGE, "latest_vintage_at": VINTAGE,
            "raw_object_uri": "raw/test"}  # fmt: skip


def openalex_series(seed: int = 1) -> tuple[list[dict], list[dict]]:
    """Monthly OpenAlex-like counts, 2023-11 to 2026-10 (the last month incomplete), in two scopes:
    - T1 rising steadily worldwide and in Australia (a trend);
    - T2 flat (noise only);
    - T3 tiny until the last three months, then a surge from a low base (Australia);
    - T4 an anomaly in the last complete month (Australia);
    - T5 rising worldwide but flat in Australia (a divergence: Australia falling behind)."""
    rng = np.random.default_rng(seed)
    ms = months("2023-11", 36)
    series, obs = [], []
    for scope, total in (("world", 500_000.0), ("au", 20_000.0)):
        tot = {m: total * (1 + 0.002 * i) for i, m in enumerate(ms)}
        sid = f"openalex_counts|total|{scope}|month"
        series.append(series_row(sid, "openalex_counts", "All works", scope, "research", ["adjacent"], "M"))
        obs += obs_rows(sid, "openalex_counts", tot)
        shapes = {
            "T1": lambda i: 0.002 * np.exp(0.04 * i),
            "T2": lambda i: 0.002,
            "T3": lambda i: 0.00002 if i < 32 else 0.0006,
            "T4": lambda i: 0.002 * (2.5 if i == 34 else 1.0),
            "T5": (lambda i: 0.002 * np.exp(0.04 * i)) if scope == "world" else (lambda i: 0.002),
        }
        for topic, f in shapes.items():
            sid = f"openalex_counts|topic|{topic}|{scope}|month"
            vals = {}
            for i, m in enumerate(ms):
                lam = tot[m] * f(i)
                vals[m] = float(rng.poisson(lam))
            if topic == "T3":
                vals = {m: v for m, v in vals.items() if v > 0}  # taxonomy counts list non-zero groups only
            series.append(series_row(sid, "openalex_counts", f"Topic {topic}", scope, "research", ["adjacent"], "M"))
            obs += obs_rows(sid, "openalex_counts", vals)
    return series, obs


def abs_series(seed: int = 2) -> tuple[list[dict], list[dict]]:
    """Quarterly statistics: L1 shifts level two quarters before the end; L2 is flat noise."""
    rng = np.random.default_rng(seed)
    qs = [f"{y}-Q{q}" for y in range(2019, 2027) for q in range(1, 5)][:31]  # to 2026-Q3 (incomplete at as_of)
    series, obs = [], []
    for name, f in (("L1", lambda i: 100 + (60 if i >= 27 else 0)), ("L2", lambda i: 100)):
        sid = f"abs_headline|ABS:TEST|{name}"
        vals = {q: f(i) + rng.normal(0, 2) for i, q in enumerate(qs)}
        series.append(series_row(sid, "abs_headline", f"Indicator {name}", "AUS", "statistics", ["wider_world"], "Q",
                                 unit="Index"))  # fmt: skip
        obs += obs_rows(sid, "abs_headline", vals)
    return series, obs


def put_normalise(store, docs: dict[str, list[dict]] | None = None, series: list[dict] | None = None,
                  obs: list[dict] | None = None):  # fmt: skip
    """A passed normalise run holding these documents (by source), series and observations (by source)."""
    from moria.tables import DOCUMENTS

    tables = {}
    for source, rows in sorted((docs or {}).items()):
        tables[f"lake/documents/source={source}/documents.parquet"] = (rows, DOCUMENTS, ("item_id",))
    by_src: dict[str, tuple[list, list]] = {}
    for r in series or []:
        by_src.setdefault(r["source"], ([], []))[0].append(r)
    for r in obs or []:
        by_src.setdefault(r["source"], ([], []))[1].append(r)
    for source, (s, o) in sorted(by_src.items()):
        tables[f"lake/series/source={source}/series.parquet"] = (s, SERIES, ("series_id",))
        sort = ("series_id", "period", "vintage_at")
        tables[f"lake/observations/source={source}/observations.parquet"] = (o, OBSERVATIONS, sort)
    return put_stage(store, "normalise", tables)


def minimal_layer(store, as_of: date = AS_OF) -> None:
    """The smallest evidence layer every day-4 stage accepts: one policy source with a few items, the OpenAlex-like
    series, and IP RAPID metrics with two class pairs; each stage's manifest linked to the same normalise run."""
    import pyarrow as pa

    from moria.embed import to_blob
    from moria.features import EMBEDDINGS, GROUPS, KEYPHRASE_ROWS, VOCABULARY
    from moria.iprmetrics import CLASS_COUNTS, CLASS_PAIRS
    from moria.records import sha256_hex
    from moria.tables import STRS

    rng = np.random.default_rng(11)
    docs, kp, emb, groups, tags = [], [], [], [], []
    for k in range(6):
        at = datetime(2025, 3, 1 + k, tzinfo=UTC)
        iid = sha256_hex(f"base|{k}")
        docs.append({"item_id": iid, "source": "base_feed", "evidence_id": iid, "n_versions": 1, "provider": "test",
                     "source_collection": "base_feed", "provider_record_id": str(k), "doc_type": "item",
                     "family": "policy", "rings": ["core"], "domains": ["D1"], "licence": "test",
                     "title": f"Placeholder {k}", "summary": "", "text": "", "text_chars": 0, "text_stored": False,
                     "url": None, "url_canonical": None, "outlet": "base_feed", "country": None, "event_at": at,
                     "observable_at": at, "observable_basis": "source", "first_seen_at": VINTAGE,
                     "retrieved_at": VINTAGE, "raw_object_uri": "raw/test", "parser_version": "t", "extra": "{}",
                     "sweep_codes": [], "title_key": None})  # fmt: skip
        kp.append({"item_id": iid, "phrase": "placeholder phrase", "score": 1.0, "rank": 1})
        v = rng.normal(size=384)
        emb.append({"item_id": iid, "text_sha256": iid, "vector": to_blob((v / np.linalg.norm(v))[None])[0]})
        groups.append({"item_id": iid, "source": "base_feed", "dedup_group": iid, "group_size": 1, "rule": "self",
                       "max_cosine": 0.0})  # fmt: skip
        tags.append({"item_id": iid, "tagger": "zeroshot-test", "term_groups": [], "term_territories": [],
                     "term_phrases": 0, "ring_top": "core", "ring_p_adjacent": 0.1, "ring_p_core": 0.8,
                     "ring_p_wider_world": 0.1})  # fmt: skip
    tag_schema = pa.schema([("item_id", pa.string()), ("tagger", pa.string()), ("term_groups", STRS),
                            ("term_territories", STRS), ("term_phrases", pa.int16()), ("ring_top", pa.string()),
                            ("ring_p_adjacent", pa.float32()), ("ring_p_core", pa.float32()),
                            ("ring_p_wider_world", pa.float32())])  # fmt: skip
    vocab = [{"phrase": "placeholder phrase", "words": 2, "df": 6, "n_sources": 1, "sources": ["base_feed"],
              "families": ["policy"], "first_observable_at": docs[0]["observable_at"],
              "first_item_id": docs[0]["item_id"]}]  # fmt: skip
    s1, o1 = openalex_series()
    nrun = put_normalise(store, {"base_feed": docs}, s1, o1).rsplit("/", 1)[1].removesuffix(".json")
    erun = put_stage(store, "features.embed", {"features/embeddings/source=base_feed/embeddings.parquet":
                     (emb, EMBEDDINGS, ("item_id",))}, {"normalise_run": nrun}).rsplit("/", 1)[1][:-5]  # fmt: skip
    put_stage(store, "features.dedup", {"features/dedup/groups.parquet": (groups, GROUPS, ("item_id",))},
              {"normalise_run": nrun, "embed_run": erun})  # fmt: skip
    put_stage(store, "features.keyphrases", {"features/keyphrases/source=base_feed/keyphrases.parquet":
              (kp, KEYPHRASE_ROWS, ("item_id",)), "features/keyphrases/vocabulary.parquet":
              (vocab, VOCABULARY, ("phrase",))}, {"normalise_run": nrun})  # fmt: skip
    put_stage(store, "tag", {"features/tags/source=base_feed/tags.parquet": (tags, tag_schema, ("item_id",))},
              {"normalise_run": nrun, "embed_run": erun})  # fmt: skip
    pairs = [
        {
            "right": "trade_mark",
            "scheme": "nice",
            "class_a": "9",
            "class_b": "42",
            "period": p,
            "applications": 2,
            "applicant_min": "p1",
            "applicant_max": "p2",
        }
        for p in months("2025-01", 21)
    ]
    counts = [{"right": "trade_mark", "scheme": "nice", "class": c, "period": p, "applications": 10}
              for c in ("9", "42", "*") for p in months("2025-01", 21)]  # fmt: skip
    ipr_s = [series_row("ip_rapid_metrics|applications|trade_mark|all", "ip_rapid_metrics", "Applications", "AUS",
                        "patent", ["core"], "M", unit="applications")]  # fmt: skip
    ipr_o = obs_rows("ip_rapid_metrics|applications|trade_mark|all", "ip_rapid_metrics",
                     {m: 8000.0 for m in months("2023-01", 45)})  # fmt: skip
    put_stage(store, "ipr.metrics", {
        "lake/ipr_metrics/series.parquet": (ipr_s, SERIES, ("series_id",)),
        "lake/ipr_metrics/observations.parquet": (ipr_o, OBSERVATIONS, ("series_id", "period", "vintage_at")),
        "lake/ipr_metrics/class_pairs.parquet": (pairs, CLASS_PAIRS, ("class_a", "period")),
        "lake/ipr_metrics/class_counts.parquet": (counts, CLASS_COUNTS, ("class", "period")),
    })  # fmt: skip
