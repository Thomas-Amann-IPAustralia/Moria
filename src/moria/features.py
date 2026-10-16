"""The feature stages (design §7, §8.1; day 3), each reading the normalise stage's checked outputs:

- `moria features embed`: every document's title, summary and opening text as a 384-number vector (`moria.embed`),
  in `features/embeddings/source=<id>/embeddings.parquet`. A vector is reused while its text is unchanged.
- `moria features dedup`: de-duplication groups (design §8.3) in `features/dedup/groups.parquet`: the same
  canonical URL between news items; the same news title within the window; or cosine >= 0.95 within the window
  between different outlets (syndicated copies and reposts). Counts use one item per group.
- `moria features keyphrases`: n-gram keyphrases by TF-IDF, top k per document, in
  `features/keyphrases/source=<id>/keyphrases.parquet`, and the vocabulary with each phrase's first observable date,
  sources and families (`features/keyphrases/vocabulary.parquet`), which the new-term detector reads (§8.2).
- `moria features index`: a BM25 index for analysts (DuckDB `fts`) in `features/index/bm25.duckdb`.

Each stage checks its upstream manifest (status passed, hashes matching) before it reads, and writes its own.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa

from .config import FeaturesConfig
from .embed import Encoder, from_blobs, to_blob
from .lake import file_sha256
from .manifest import Manifest
from .normalise import COMMAND as NORMALISE
from .records import canonical_json, sha256_hex
from .store import Store
from .tables import (
    STRS,
    TS,
    cache_root,
    cached_get,
    fetch_outputs,
    read_rows,
    upload,
    upstream,
    write_rows,
)
from .text import cut

log = logging.getLogger("moria.features")

EMBED, DEDUP, KEYPHRASES, INDEX = "features.embed", "features.dedup", "features.keyphrases", "features.index"

EMBEDDINGS = pa.schema([("item_id", pa.string()), ("text_sha256", pa.string()), ("vector", pa.binary())])
GROUPS = pa.schema(
    [
        ("item_id", pa.string()),
        ("source", pa.string()),
        ("dedup_group", pa.string()),  # the item id of the group's earliest member
        ("group_size", pa.int32()),
        ("rule", pa.string()),  # how the item joined its group: self, url, title, cosine
        ("max_cosine", pa.float32()),
    ]
)
KEYPHRASE_ROWS = pa.schema(
    [("item_id", pa.string()), ("phrase", pa.string()), ("score", pa.float32()), ("rank", pa.int16())]
)
VOCABULARY = pa.schema(
    [
        ("phrase", pa.string()),
        ("words", pa.int8()),
        ("df", pa.int32()),
        ("n_sources", pa.int16()),
        ("sources", STRS),
        ("families", STRS),
        ("first_observable_at", TS),
        ("first_item_id", pa.string()),
    ]
)


def documents_in(store: Store) -> tuple[dict, dict[str, Path]]:
    """The latest passed normalise run and its documents, by source, as local files checked against its hashes."""
    m = upstream(store, NORMALISE)
    files = fetch_outputs(store, m, "lake/documents/", cache_root())
    return m, {k.split("/source=")[1].split("/")[0]: p for k, p in files.items()}


def embed_text(title: str, summary: str, text: str, limit: int) -> str:
    head = f"{title}." if title and not title.endswith((".", "?", "!")) else title or ""
    return cut(" ".join(x for x in (head, summary, text) if x), limit)


def _previous(store: Store, command: str) -> dict | None:
    """The latest passed run of a command, past any failed runs after it (a failed run reuses nothing, and must not
    stop the next run reusing the last good one)."""
    keys = sorted((k for k in store.list(f"manifests/{command}/") if k.endswith(".json")), reverse=True)
    passed = [m for m in (json.loads(store.get(k)) for k in keys) if m.get("status") == "passed"]
    if not passed:
        return None
    second = passed[0]["run_id"][:16]
    tied = [m for m in passed if m["run_id"][:16] == second]
    return max(tied, key=lambda m: (m.get("started_ns") or 0, m["run_id"]))


def _unchanged(store: Store, previous: dict | None, source: str, digest: str, prefix: str) -> list[dict] | None:
    prev = ((previous or {}).get("params", {}).get("sources") or {}).get(source) or {}
    outs = [o for o in (previous or {}).get("outputs", []) if o["key"].startswith(f"{prefix}source={source}/")]
    if prev.get("digest") == digest and outs and all(store.exists(o["key"]) for o in outs):
        return outs
    return None


# ----------------------------------------------------------------------------------------------------------- embed


def embed(store: Store, cfg: FeaturesConfig, encoder_factory, config_hash: str | None = None,
          only: list[str] | None = None) -> tuple[str, str, dict]:  # fmt: skip
    """Embed every source's documents. `encoder_factory()` returns an object with `.encode(texts)` and `.identity`
    (tests pass a stub; the CLI passes the real encoder)."""
    manifest = Manifest(command=EMBED, config_hash=config_hash)
    previous = _previous(store, EMBED)
    try:
        nm, docs = documents_in(store)
        manifest.params = {"normalise_run": nm["run_id"], "sources": {}}
        encoder = None
        settings = cfg.embed.model_dump(mode="json")
        prefix = "features/embeddings/"
        with tempfile.TemporaryDirectory(prefix="moria-embed-") as tmp:
            for source in sorted(docs):
                path = docs[source]
                digest = sha256_hex(canonical_json({"docs": file_sha256(path), "embed": settings}))
                entry = {"digest": digest}
                manifest.params["sources"][source] = entry
                kept = _unchanged(store, previous, source, digest, prefix)
                if kept is not None or (only and source not in only):
                    prev = ((previous or {}).get("params", {}).get("sources") or {}).get(source) or {}
                    outs = kept or [o for o in (previous or {}).get("outputs", [])
                                    if o["key"].startswith(f"{prefix}source={source}/")]  # fmt: skip
                    manifest.outputs.extend(outs)
                    entry.update(status="unchanged", digest=prev.get("digest", digest), counts=prev.get("counts", {}))
                    continue
                rows = read_rows(path, ["item_id", "title", "summary", "text"])
                texts = [embed_text(r["title"], r["summary"], r["text"], cfg.embed.text_chars) for r in rows]
                shas = [sha256_hex(f"{cfg.embed.model}@{cfg.embed.revision}|{cfg.embed.max_tokens}|{t}") for t in texts]
                pool = _reuse_pool(store, previous, source, prefix)
                pool.update(_checkpoint_load(cfg, source))
                todo = sorted({s: t for s, t in zip(shas, texts, strict=True) if s not in pool}.items())
                log.info("embed: %s: %d documents, %d to embed, %d reused", source, len(rows), len(todo),
                         len(rows) - len(todo))  # fmt: skip
                if todo:
                    encoder = encoder or encoder_factory()
                    step = 4096
                    for start in range(0, len(todo), step):
                        part = todo[start : start + step]
                        vecs = encoder.encode([t for _, t in part])
                        blobs = to_blob(vecs)
                        pool.update({s: b for (s, _), b in zip(part, blobs, strict=True)})
                        _checkpoint_save(cfg, source, {s: b for (s, _), b in zip(part, blobs, strict=True)})
                        log.info("embed: %s: %d of %d embedded", source, min(start + step, len(todo)), len(todo))
                out_rows = [{"item_id": r["item_id"], "text_sha256": s, "vector": pool[s]}
                            for r, s in zip(rows, shas, strict=True)]  # fmt: skip
                local = Path(tmp) / source / "embeddings.parquet"
                write_rows(out_rows, EMBEDDINGS, local, ("item_id",))
                upload(store, manifest, f"{prefix}source={source}/embeddings.parquet", local)
                entry.update(status="built", counts={"documents": len(rows), "embedded": len(todo)})
                _checkpoint_clear(cfg, source)
        manifest.params["model"] = f"{cfg.embed.model}@{cfg.embed.revision}"
        manifest.counts = _totals(manifest.params["sources"], ("documents", "embedded"))
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        return _failed(store, manifest, e)


def _reuse_pool(store: Store, previous: dict | None, source: str, prefix: str) -> dict[str, bytes]:
    for o in (previous or {}).get("outputs", []):
        if o["key"] == f"{prefix}source={source}/embeddings.parquet" and store.exists(o["key"]):
            rows = read_rows(cached_get(store, o["key"], o["sha256"], cache_root()), ["text_sha256", "vector"])
            return {r["text_sha256"]: r["vector"] for r in rows}
    return {}


def _checkpoint_path(cfg: FeaturesConfig, source: str) -> Path:
    return cache_root() / "embed-checkpoints" / f"{cfg.embed.revision[:12]}-{cfg.embed.max_tokens}" / source


def _checkpoint_save(cfg: FeaturesConfig, source: str, part: dict[str, bytes]) -> None:
    """Vectors computed so far, kept locally so an interrupted backfill resumes rather than restarts."""
    d = _checkpoint_path(cfg, source)
    d.mkdir(parents=True, exist_ok=True)
    rows = [{"item_id": "", "text_sha256": s, "vector": b} for s, b in sorted(part.items())]
    write_rows(rows, EMBEDDINGS, d / f"part-{len(list(d.glob('part-*.parquet'))):05d}.parquet", ("text_sha256",))


def _checkpoint_load(cfg: FeaturesConfig, source: str) -> dict[str, bytes]:
    out = {}
    for p in sorted(_checkpoint_path(cfg, source).glob("part-*.parquet")):
        out.update({r["text_sha256"]: r["vector"] for r in read_rows(p, ["text_sha256", "vector"])})
    return out


def _checkpoint_clear(cfg: FeaturesConfig, source: str) -> None:
    for p in _checkpoint_path(cfg, source).glob("part-*.parquet"):
        p.unlink()


def _totals(sources: dict, keys: tuple[str, ...]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for e in sources.values():
        out[f"sources_{e.get('status')}"] += 1
        for k in keys:
            out[k] += (e.get("counts") or {}).get(k, 0)
    return dict(sorted(out.items()))


def _failed(store: Store, manifest: Manifest, e: Exception) -> tuple[str, str, dict]:
    first = (str(e).splitlines() or [type(e).__name__])[0]
    cause = f"{manifest.command}: {type(e).__name__}: {first[:300]}"
    log.error("%s", cause)
    return "failed", manifest.finish(store, "failed", cause), {"error": cause}


def embeddings_in(store: Store) -> tuple[dict, dict[str, Path]]:
    m = upstream(store, EMBED)
    files = fetch_outputs(store, m, "features/embeddings/", cache_root())
    return m, {k.split("/source=")[1].split("/")[0]: p for k, p in files.items()}


def load_vectors(paths: dict[str, Path], dim: int) -> tuple[list[str], np.ndarray]:
    ids, blobs = [], []
    for source in sorted(paths):
        for r in read_rows(paths[source], ["item_id", "vector"]):
            ids.append(r["item_id"])
            blobs.append(r["vector"])
    return ids, from_blobs(blobs, dim)


# ----------------------------------------------------------------------------------------------------------- dedup


class _Union:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def join(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def dedup(store: Store, cfg: FeaturesConfig, config_hash: str | None = None) -> tuple[str, str, dict]:
    manifest = Manifest(command=DEDUP, config_hash=config_hash)
    try:
        nm, docs = documents_in(store)
        em, emb = embeddings_in(store)
        if em["params"].get("normalise_run") != nm["run_id"]:
            raise ValueError(f"embeddings are from normalise run {em['params'].get('normalise_run')}, not the latest "
                             f"({nm['run_id']}); run `moria features embed` first")  # fmt: skip
        manifest.params = {"normalise_run": nm["run_id"], "embed_run": em["run_id"]}
        rows = []
        for source in sorted(docs):
            rows.extend(read_rows(docs[source], ["item_id", "source", "family", "outlet", "observable_at",
                                                 "url_canonical", "title_key"]))  # fmt: skip
        groups, counts = dedup_groups(rows, emb, cfg)
        with tempfile.TemporaryDirectory(prefix="moria-dedup-") as tmp:
            local = Path(tmp) / "groups.parquet"
            write_rows(groups, GROUPS, local, ("item_id",))
            upload(store, manifest, "features/dedup/groups.parquet", local)
        manifest.counts = counts
        return "passed", manifest.finish(store, "passed"), counts
    except Exception as e:
        return _failed(store, manifest, e)


def dedup_groups(rows: list[dict], emb_paths: dict[str, Path], cfg: FeaturesConfig) -> tuple[list[dict], dict]:
    """Union of three rules; each group is named by its earliest member (observable date, then id)."""
    d = cfg.dedup
    rows = sorted(rows, key=lambda r: (r["observable_at"], r["item_id"]))
    index = {r["item_id"]: i for i, r in enumerate(rows)}
    uf = _Union(len(rows))
    rule = ["self"] * len(rows)
    best = np.zeros(len(rows), dtype=np.float32)
    counts: dict[str, int] = defaultdict(int)
    # The same URL is the same item only in news, where the URL is the article. Elsewhere a link can be a page that
    # many items share (a committee's page for an inquiry and its reports, a ministry's site); near-identical text
    # between outlets is caught by the cosine rule instead
    by_url: dict[str, int] = {}
    for i, r in enumerate(rows):
        u = r["url_canonical"]
        if not u:
            continue
        j = by_url.get(u)
        if j is None:
            by_url[u] = i
        elif r["family"] == "news" and rows[j]["family"] == "news":
            uf.join(j, i)
            rule[i] = "url"
            counts["joined_url"] += 1
    window = timedelta(days=d.window_days)
    last_title: dict[str, int] = {}
    for i, r in enumerate(rows):
        k = r["title_key"]
        if not k:
            continue
        j = last_title.get(k)
        if j is not None and r["observable_at"] - rows[j]["observable_at"] <= window and uf.find(i) != uf.find(j):
            uf.join(j, i)
            if rule[i] == "self":
                rule[i] = "title"
            counts["joined_title"] += 1
        last_title[k] = i
    # near-duplicates: cosine within the window, between different outlets
    ids, vectors = load_vectors(emb_paths, cfg.embed.dim)
    pos = np.array([index.get(i, -1) for i in ids])
    keep = pos >= 0
    order = np.argsort(pos[keep], kind="stable")
    vec = vectors[keep][order]
    at = np.array([rows[p]["observable_at"].timestamp() for p in pos[keep][order]])
    outlets = np.array([rows[p]["outlet"] for p in pos[keep][order]], dtype=object)
    rowpos = pos[keep][order]
    span = d.window_days * 86400
    chunk = 2048
    for start in range(0, len(vec), chunk):
        end = min(start + chunk, len(vec))
        lo = int(np.searchsorted(at, at[start] - span, side="left"))
        if end - lo <= 1:
            continue
        sims = vec[start:end] @ vec[lo:end].T
        for a in range(end - start):
            i = start + a
            cand = np.nonzero(sims[a, : i - lo] >= d.cosine)[0]
            for c in cand[-d.max_neighbours :]:
                j = lo + c
                if outlets[j] == outlets[i] or at[i] - at[j] > span:
                    continue
                ri, rj = int(rowpos[i]), int(rowpos[j])
                best[ri] = max(best[ri], sims[a, c])
                if uf.find(ri) != uf.find(rj):
                    uf.join(rj, ri)
                    if rule[ri] == "self":
                        rule[ri] = "cosine"
                    counts["joined_cosine"] += 1
    members: dict[int, list[int]] = defaultdict(list)
    for i in range(len(rows)):
        members[uf.find(i)].append(i)
    out = []
    for root, ms in members.items():
        for i in ms:
            out.append({"item_id": rows[i]["item_id"], "source": rows[i]["source"],
                        "dedup_group": rows[root]["item_id"], "group_size": len(ms), "rule": rule[i],
                        "max_cosine": float(best[i])})  # fmt: skip
    counts["items"] = len(rows)
    counts["groups"] = len(members)
    counts["groups_with_copies"] = sum(1 for ms in members.values() if len(ms) > 1)
    counts["not_embedded"] = int(len(rows) - keep.sum())
    return out, dict(sorted(counts.items()))


# ------------------------------------------------------------------------------------------------------ keyphrases

# punctuation that ends a phrase, including curly quotes, en and em dashes and bullets
_SEGMENTS = re.compile("[.,;:!?()\\[\\]{}\"/|<>\n\t'\u2018\u2019\u201c\u201d\u2022\u00b7\u2013\u2014]+|\\s-\\s")
_TOKEN = re.compile(r"[a-z][a-z0-9\-]*[a-z0-9]|[a-z]")


def _stopwords() -> frozenset[str]:
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    extra = {"said", "says", "new", "also", "would", "could", "may", "one", "two", "year", "years", "per", "via",
             "including", "within", "without", "s", "t", "u", "v", "pty", "ltd", "inc", "re"}  # fmt: skip
    return frozenset(ENGLISH_STOP_WORDS | extra)


def candidates(text: str, ngram_max: int, stop: frozenset[str]) -> Counter:
    """Candidate phrases: runs of words between punctuation and stopwords, and their n-grams up to ngram_max.
    Tokens are lower case; numbers alone are not words of a phrase."""
    out: Counter = Counter()
    for seg in _SEGMENTS.split(text.lower()):
        run: list[str] = []
        for tok in [*_TOKEN.findall(seg), None]:
            if tok is None or tok in stop or len(tok) < 2:
                for n in range(1, ngram_max + 1):
                    for k in range(len(run) - n + 1):
                        out[" ".join(run[k : k + n])] += 1
                run = []
            else:
                run.append(tok)
    return out


@dataclass
class _Doc:
    item_id: str
    source: str
    family: str
    observable_at: object
    text: str


def keyphrases(store: Store, cfg: FeaturesConfig, config_hash: str | None = None) -> tuple[str, str, dict]:
    manifest = Manifest(command=KEYPHRASES, config_hash=config_hash)
    try:
        nm, paths = documents_in(store)
        manifest.params = {"normalise_run": nm["run_id"]}
        docs = []
        for source in sorted(paths):
            for r in read_rows(paths[source], ["item_id", "source", "family", "observable_at", "title", "summary",
                                               "text"]):  # fmt: skip
                text = embed_text(r["title"], r["summary"], r["text"], cfg.keyphrases.text_chars)
                docs.append(_Doc(r["item_id"], r["source"], r["family"], r["observable_at"], text))
        per_source, vocab, counts = keyphrase_tables(docs, cfg)
        with tempfile.TemporaryDirectory(prefix="moria-keyphrases-") as tmp:
            for source in sorted(paths):
                local = Path(tmp) / source / "keyphrases.parquet"
                write_rows(per_source.get(source, []), KEYPHRASE_ROWS, local, ("item_id", "rank"))
                upload(store, manifest, f"features/keyphrases/source={source}/keyphrases.parquet", local)
            local = Path(tmp) / "vocabulary.parquet"
            write_rows(vocab, VOCABULARY, local, ("phrase",))
            upload(store, manifest, "features/keyphrases/vocabulary.parquet", local)
        manifest.counts = counts
        return "passed", manifest.finish(store, "passed"), counts
    except Exception as e:
        return _failed(store, manifest, e)


def keyphrase_tables(docs: list[_Doc], cfg: FeaturesConfig) -> tuple[dict[str, list[dict]], list[dict], dict]:
    """Three passes: document frequencies through hashed buckets (bounded memory), exact frequencies for the phrases
    that can pass, then each document's top-k by TF-IDF, with a phrase dropped when a longer kept phrase holds it."""
    k = cfg.keyphrases
    stop = _stopwords()
    n_docs = len(docs)
    buckets = np.zeros(1 << 24, dtype=np.int32)
    for d in docs:
        hs = np.fromiter((zlib.crc32(p.encode()) & 0xFFFFFF for p in candidates(d.text, k.ngram_max, stop)),
                         dtype=np.int64)  # fmt: skip
        np.add.at(buckets, np.unique(hs), 1)
    df: Counter = Counter()
    for d in docs:
        for p in candidates(d.text, k.ngram_max, stop):
            if buckets[zlib.crc32(p.encode()) & 0xFFFFFF] >= k.min_df:
                df[p] += 1
    max_df = max(k.min_df, int(k.max_df * n_docs))
    allowed = [(p, n) for p, n in df.items() if k.min_df <= n <= max_df]
    allowed.sort(key=lambda pn: (-pn[1], pn[0]))
    vocab_df = dict(allowed[: k.max_features])
    del df
    idf = {p: float(np.log((1 + n_docs) / (1 + n)) + 1.0) for p, n in vocab_df.items()}
    first: dict[str, tuple] = {}
    sources: dict[str, set] = defaultdict(set)
    families: dict[str, set] = defaultdict(set)
    per_source: dict[str, list[dict]] = defaultdict(list)
    with_phrases = 0
    for d in sorted(docs, key=lambda d: (d.observable_at, d.item_id)):
        tf = {p: n for p, n in candidates(d.text, k.ngram_max, stop).items() if p in idf}
        for p in tf:
            if p not in first:
                first[p] = (d.observable_at, d.item_id)
            sources[p].add(d.source)
            families[p].add(d.family)
        scored = sorted(((1 + np.log(n)) * idf[p] * len(p.split()) ** 0.5, p) for p, n in tf.items())[::-1]
        kept: list[tuple[float, str]] = []
        for score, p in scored:
            if any(f" {p} " in f" {q} " for _, q in kept):
                continue
            kept.append((score, p))
            if len(kept) == k.top_k:
                break
        with_phrases += bool(kept)
        for rank, (score, p) in enumerate(kept, 1):
            per_source[d.source].append({"item_id": d.item_id, "phrase": p, "score": float(score), "rank": rank})
    vocab = [{"phrase": p, "words": len(p.split()), "df": n, "n_sources": len(sources[p]),
              "sources": sorted(sources[p]), "families": sorted(families[p]),
              "first_observable_at": first[p][0], "first_item_id": first[p][1]}
             for p, n in vocab_df.items()]  # fmt: skip
    counts = {"documents": n_docs, "documents_with_keyphrases": with_phrases, "vocabulary": len(vocab),
              "keyphrases": sum(len(v) for v in per_source.values())}  # fmt: skip
    return per_source, vocab, counts


# ----------------------------------------------------------------------------------------------------------- index


def index(store: Store, cfg: FeaturesConfig, config_hash: str | None = None) -> tuple[str, str, dict]:
    """A BM25 index over title, summary and the start of the text, with each item's source, family, dates and URL,
    so `moria search` and the dossiers (day 5) can filter by source and observable date."""
    manifest = Manifest(command=INDEX, config_hash=config_hash)
    try:
        nm, paths = documents_in(store)
        manifest.params = {"normalise_run": nm["run_id"]}
        with tempfile.TemporaryDirectory(prefix="moria-index-") as tmp:
            db = Path(tmp) / "bm25.duckdb"
            n = build_index(db, paths, cfg.index.text_chars)
            upload(store, manifest, "features/index/bm25.duckdb", db)
        manifest.counts = {"documents": n}
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        return _failed(store, manifest, e)


def build_index(db: Path, paths: dict[str, Path], text_chars: int) -> int:
    files = ", ".join(f"'{p.as_posix()}'" for _, p in sorted(paths.items()))
    con = duckdb.connect(str(db))
    con.execute("INSTALL fts; LOAD fts")
    con.execute(
        f"CREATE TABLE docs AS SELECT item_id, source, family, doc_type, outlet, country, observable_at, event_at, "
        f"url, title, summary, left(text, {int(text_chars)}) AS body FROM read_parquet([{files}]) ORDER BY item_id"
    )
    con.execute(
        "PRAGMA create_fts_index('docs', 'item_id', 'title', 'summary', 'body', stemmer = 'porter', "
        "stopwords = 'english', strip_accents = 1, lower = 1, overwrite = 1)"
    )
    n = con.execute("SELECT count(*) FROM docs").fetchone()[0]
    con.execute("CHECKPOINT")
    con.close()
    return n


def search(db: Path, query: str, limit: int = 20, source: str | None = None, since: str | None = None) -> list[tuple]:
    """BM25 matches: (score, item_id, source, observable date, title). Titles are shown to the analyst running the
    search, on their own machine; scheduled jobs never call this."""
    con = duckdb.connect(str(db), read_only=True)
    con.execute("LOAD fts")
    where, args = ["score IS NOT NULL"], [query]
    if source:
        where.append("source = ?")
        args.append(source)
    if since:
        where.append("observable_at >= CAST(? AS TIMESTAMPTZ)")
        args.append(since)
    args.append(limit)
    rows = con.execute(
        f"SELECT round(score, 3), item_id, source, strftime(observable_at, '%Y-%m-%d'), title FROM ("
        f"SELECT *, fts_main_docs.match_bm25(item_id, ?) AS score FROM docs) WHERE {' AND '.join(where)} "
        f"ORDER BY score DESC, item_id LIMIT ?",
        args,
    ).fetchall()
    con.close()
    return rows


def real_encoder(cfg: FeaturesConfig, client) -> Encoder:
    return Encoder(cfg.embed, client)
