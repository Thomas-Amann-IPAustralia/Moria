"""`moria tag --backend zeroshot`: per-item descriptive tags (design §6.2, §9.1; day 3). What an item is ABOUT, never
what it means (design §3).

Each item's embedding is compared, by cosine similarity, with one prototype vector per label: the mean of the
embedded description and examples of each label in `config/codebook.yaml` (ring, domain, PESTLE origin, rights),
of each Growth Territory (`config/territories.yaml`: name, aim and description, plus the owner's private context
when it is in the bucket), and of each known trend (`config/baseline.yaml`: name and statement).

- Single-choice sets (ring, PESTLE) get a softmax over the similarities (`p_*`), the top label and its margin over
  the second. They are uncalibrated until the owner's labels exist; the margin finds the items the tagger is least
  sure of, for the labelling sample (docs/mining-explained.md).
- Multi-label sets (domain, rights, territories) keep the raw similarities (`sim_*`).
- Known trends: the nearest trend and its similarity, and the second (design §6.4, `known_trend_match`).
- Territory terms, wired in for every source: the 47 query groups GDELT is searched with (territory terms and broad
  themes, with synonyms and both spellings) are matched in each item's title, summary and text, so the same groups
  count across every family, not only news.

The tagger's version names the backend, the codebook and the prototype texts' hash, so counts across a window can
use one tagger version (design §8.3, label drift).
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from .collectors.gdelt import build_groups
from .collectors.gkg import GkgParams, PhraseMatcher
from .config import BaselineFile, CodebookFile, FeaturesConfig, SourceCard, TerritoriesFile
from .embed import from_blobs
from .features import _failed, documents_in, embeddings_in
from .lake import file_sha256
from .manifest import Manifest
from .records import canonical_json, sha256_hex
from .store import Store
from .tables import STRS, read_rows, upload

log = logging.getLogger("moria.tags")

COMMAND = "tag"
CONTEXT_KEY = "interpretation/territories/context.yaml"


def prototype_texts(codebook: CodebookFile, territories: TerritoriesFile, baseline: BaselineFile,
                    context: dict | None) -> dict[str, dict[str, list[str]]]:  # fmt: skip
    """set -> label -> the texts whose embeddings are averaged into the label's prototype."""
    out: dict[str, dict[str, list[str]]] = {}
    for name, s in codebook.sets.items():
        out[name] = {label: [lab.description, *lab.examples] for label, lab in s.labels.items()}
    private = {t["id"]: t for t in (context or {}).get("territories", [])}
    out["territory"] = {}
    for t in territories.territories:
        texts = [f"{t.name}. {t.aim}", t.description]
        c = private.get(t.id)
        if c:
            texts += [*c.get("imagine", []), *c.get("recently_changed", [])]
            texts += [*(c.get("jobs_to_be_done") or {}).get("items", [])]
        out["territory"][t.id] = texts
    out["known_trend"] = {t.id: [f"{t.name}. {t.statement}"] for t in baseline.trends}
    return out


def prototypes(encoder, texts: dict[str, dict[str, list[str]]]) -> dict[str, tuple[list[str], np.ndarray]]:
    out = {}
    for name, labels in texts.items():
        keys = sorted(labels)
        mats = []
        for k in keys:
            v = encoder.encode(labels[k]).mean(axis=0)
            mats.append(v / max(np.linalg.norm(v), 1e-12))
        out[name] = (keys, np.vstack(mats).astype(np.float32))
    return out


def tag_schema(protos: dict[str, tuple[list[str], np.ndarray]], codebook: CodebookFile) -> pa.Schema:
    fields = [("item_id", pa.string()), ("tagger", pa.string())]
    for name in sorted(protos):
        labels = protos[name][0]
        if name == "known_trend":
            fields += [("known_trend_top", pa.string()), ("known_trend_sim", pa.float32()),
                       ("known_trend_second", pa.string()), ("known_trend_second_sim", pa.float32())]  # fmt: skip
        elif name in codebook.sets and codebook.sets[name].choice == "single":
            fields += [(f"{name}_top", pa.string()), (f"{name}_margin", pa.float32())]
            fields += [(f"{name}_p_{label}", pa.float32()) for label in labels]
        else:
            fields += [(f"{name}_sim_{label}", pa.float32()) for label in labels]
            if name == "territory":
                fields += [("territory_top", pa.string())]
    fields += [("term_groups", STRS), ("term_territories", STRS), ("term_phrases", pa.int16())]
    return pa.schema(fields)


def score(vectors: np.ndarray, protos, codebook: CodebookFile, temperature: float) -> dict[str, np.ndarray | list]:
    cols: dict[str, np.ndarray | list] = {}
    for name in sorted(protos):
        labels, mat = protos[name]
        sims = vectors @ mat.T
        if name == "known_trend":
            order = np.argsort(-sims, axis=1, kind="stable")
            rows = np.arange(len(sims))
            cols["known_trend_top"] = [labels[i] for i in order[:, 0]]
            cols["known_trend_sim"] = sims[rows, order[:, 0]]
            cols["known_trend_second"] = [labels[i] for i in order[:, 1]] if len(labels) > 1 else [None] * len(rows)
            cols["known_trend_second_sim"] = sims[rows, order[:, 1]] if len(labels) > 1 else np.zeros(len(rows))
        elif name in codebook.sets and codebook.sets[name].choice == "single":
            z = (sims - sims.max(axis=1, keepdims=True)) / temperature
            p = np.exp(z)
            p /= p.sum(axis=1, keepdims=True)
            top2 = np.sort(p, axis=1)[:, -2:] if len(labels) > 1 else np.hstack([np.zeros_like(p), p])
            cols[f"{name}_top"] = [labels[i] for i in p.argmax(axis=1)]
            cols[f"{name}_margin"] = top2[:, 1] - top2[:, 0]
            for j, label in enumerate(labels):
                cols[f"{name}_p_{label}"] = p[:, j]
        else:
            for j, label in enumerate(labels):
                cols[f"{name}_sim_{label}"] = sims[:, j]
            if name == "territory":
                cols["territory_top"] = [labels[i] for i in sims.argmax(axis=1)]
    return cols


def term_matcher(cards: dict[str, SourceCard]) -> PhraseMatcher:
    card = next(c for c in cards.values() if c.adapter == "gdelt_gkg")
    return PhraseMatcher(build_groups(GkgParams.model_validate(card.params)))


def term_tags(matcher: PhraseMatcher, row: dict) -> tuple[list[str], list[str], int]:
    """(query groups, territories, number of distinct terms) matched in the item's title, summary and text."""
    phrases = set()
    for f in ("title", "summary", "text"):
        phrases |= matcher.phrases_in(row.get(f) or "")
    groups = sorted({g for p in phrases for g in matcher.groups_by_phrase.get(p, [])})
    territories = sorted({g.split(":")[0] for g in groups if g.startswith("T")})
    return groups, territories, len(phrases)


def tag(store: Store, cfg: FeaturesConfig, codebook: CodebookFile, territories: TerritoriesFile,
        baseline: BaselineFile, cards: dict[str, SourceCard], encoder_factory,
        config_hash: str | None = None) -> tuple[str, str, dict]:  # fmt: skip
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        nm, docs = documents_in(store)
        em, emb = embeddings_in(store)
        if em["params"].get("normalise_run") != nm["run_id"]:
            raise ValueError(f"embeddings are from normalise run {em['params'].get('normalise_run')}, not the latest "
                             f"({nm['run_id']}); run `moria features embed` first")  # fmt: skip
        context = yaml.safe_load(store.get(CONTEXT_KEY)) if store.exists(CONTEXT_KEY) else None
        texts = prototype_texts(codebook, territories, baseline, context)
        texts_hash = sha256_hex(canonical_json(texts))
        tagger = f"{cfg.tags.version}|codebook-v{codebook.version}|{texts_hash[:12]}"
        encoder = encoder_factory()
        protos = prototypes(encoder, texts)
        schema = tag_schema(protos, codebook)
        matcher = term_matcher(cards)
        manifest.params = {"normalise_run": nm["run_id"], "embed_run": em["run_id"], "tagger": tagger,
                           "territory_context": context is not None, "sources": {}}  # fmt: skip
        if em["params"].get("model") and em["params"]["model"] != encoder.identity:
            raise ValueError(f"embeddings are from {em['params']['model']}, the encoder is {encoder.identity}")
        totals = {"items": 0, "items_with_terms": 0}
        with tempfile.TemporaryDirectory(prefix="moria-tag-") as tmp:
            for source in sorted(docs):
                rows = {r["item_id"]: r for r in read_rows(docs[source], ["item_id", "title", "summary", "text"])}
                er = read_rows(emb[source], ["item_id", "vector"]) if source in emb else []
                ids = [r["item_id"] for r in er]
                vecs = from_blobs([r["vector"] for r in er], cfg.embed.dim)
                cols = score(vecs, protos, codebook, cfg.tags.temperature) if ids else {}
                out = {f.name: [] for f in schema}
                for i, item in enumerate(ids):
                    out["item_id"].append(item)
                    out["tagger"].append(tagger)
                    for name, values in cols.items():
                        v = values[i]
                        out[name].append(float(v) if isinstance(v, np.floating) else v)
                    g, t, n = term_tags(matcher, rows[item])
                    out["term_groups"].append(g)
                    out["term_territories"].append(t)
                    out["term_phrases"].append(min(n, 32767))
                    totals["items_with_terms"] += bool(g)
                totals["items"] += len(ids)
                missing = len(rows) - len(ids)
                if missing:
                    raise ValueError(f"{source}: {missing} documents have no embedding")
                table = pa.Table.from_pydict(out, schema=schema).sort_by("item_id")
                local = Path(tmp) / source / "tags.parquet"
                local.parent.mkdir(parents=True, exist_ok=True)
                pq.write_table(table, local, compression="zstd", row_group_size=50_000)
                upload(store, manifest, f"features/tags/source={source}/tags.parquet", local)
                manifest.params["sources"][source] = {"items": len(ids), "sha256": file_sha256(local)}
        manifest.counts = totals
        return "passed", manifest.finish(store, "passed"), totals
    except Exception as e:
        return _failed(store, manifest, e)
