"""The Open Australian Legal Corpus (Isaacus, on Hugging Face), into the lake in parts (D-016): adapter `hf_corpus`.

The corpus is one newline-delimited JSON file (9.4 GB, 232,560 documents in release 7.1.0) of legislation and
judgments, each a document with nine fields. It is a snapshot, re-run when a new release appears:
1. The file is downloaded by stream at a pinned dataset commit (never `main`) and its SHA-256 is checked against the
   card's (the Hugging Face file's LFS object id). The file itself is not kept.
2. Its first record's fields are checked against the nine published ones, so a schema change fails the run.
3. DuckDB keeps only the card's sources (by default the Federal Register of Legislation, the Federal Court and the
   High Court) and writes one zstd Parquet file per source to `lake/<source id>/release=<release>/<source>.parquet`.
4. A release manifest (`raw/<source id>/<release>/manifest.json`) records the commit, the file's hash and size, the
   rows and licence of each part, and how dates were set. It is written last and marks the release as ingested.

Each row keeps the corpus's fields, typed (`date` as DATE, `when_scraped` as TIMESTAMPTZ), plus:
- `event_at`: the document's own date;
- `observable_at` (design §11.3): for judgments, the decision date; for legislation, `when_scraped`, because only the
  latest version is in the corpus and its text was not public before it was in force, so a hindsight test must not
  see it earlier;
- `licence`: each document keeps its own source's terms (the corpus's LICENCE.md);
- `text_chars`, `text_sha256`, and `evidence_id` = sha256(provider | version_id | text_sha256).

Privacy: judgments name parties and witnesses. Text stays in the private bucket; logs and the census show counts by
source, type and year only.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import field_validator

from .collectors.base import CollectError
from .config import SourceCard, Strict
from .http import PoliteClient
from .lake import LakeResult, fail, file_sha256, finish_release, release_key, upload_table
from .manifest import Manifest

PARSER_VERSION = "hf-corpus-v1"
FIELDS = ("version_id", "type", "jurisdiction", "source", "mime", "date", "citation", "url", "when_scraped", "text")

log = logging.getLogger("moria.corpus")


class CorpusSource(Strict):
    provider: str  # the publisher, e.g. "Federal Court of Australia"
    licence: str
    observable_from: Literal["date", "when_scraped"]


class HfCorpusParams(Strict):
    repo: str  # e.g. "isaacus/open-australian-legal-corpus"
    revision: str  # a dataset commit hash
    file: str = "corpus.jsonl"
    sha256: str  # the file's SHA-256 (Hugging Face's LFS object id)
    release: str  # the corpus's own version, e.g. "7.1.0"
    released: str  # the release's date (ISO), for the monitor entry
    sources: dict[str, CorpusSource]
    max_object_bytes: int = 64 * 1024 * 1024  # the largest single document DuckDB will read (its buffer is twice this)
    memory_limit: str = "3GB"
    threads: int = 4
    base_url: str = "https://huggingface.co"

    @field_validator("revision")
    @classmethod
    def _pinned(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("revision must be a full commit hash, never a branch such as main")
        return value

    @field_validator("sources")
    @classmethod
    def _safe_names(cls, value: dict[str, CorpusSource]) -> dict[str, CorpusSource]:
        for name in value:
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
                raise ValueError(f"source names go into SQL and paths: {name!r}")
        return value


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_path(path: Path) -> str:
    text = str(path)
    if "'" in text:
        raise CollectError(f"corpus: a path with a quote can't go into SQL: {text!r}")
    return text


def check_fields(path: Path) -> None:
    """The first record must have exactly the published fields."""
    with open(path, encoding="utf-8") as f:
        first = f.readline()
    try:
        keys = set(json.loads(first))
    except ValueError as e:
        raise CollectError("corpus: the first line is not JSON") from e
    if keys != set(FIELDS):
        unknown, missing = sorted(keys - set(FIELDS)), sorted(set(FIELDS) - keys)
        raise CollectError(f"corpus: fields changed (unknown {unknown}, missing {missing})")


def convert(con: duckdb.DuckDBPyConnection, params: HfCorpusParams, src: Path, out_dir: Path) -> dict[str, Path]:
    """One pass over the JSON: the card's sources, typed and with Moria's columns, partitioned by source."""
    columns = "{" + ", ".join(f"'{f}': 'VARCHAR'" for f in FIELDS) + "}"
    reader = (
        f"read_json('{_sql_path(src)}', format='newline_delimited', columns={columns}, "
        f"maximum_object_size={int(params.max_object_bytes)})"
    )
    names = ", ".join(_sql_text(s) for s in params.sources)
    licence = "CASE source " + " ".join(f"WHEN {_sql_text(s)} THEN {_sql_text(c.licence)}"
                                        for s, c in params.sources.items()) + " END"  # fmt: skip
    provider = "CASE source " + " ".join(f"WHEN {_sql_text(s)} THEN {_sql_text(c.provider)}"
                                         for s, c in params.sources.items()) + " END"  # fmt: skip
    by_date = [s for s, c in params.sources.items() if c.observable_from == "date"]
    observable = (
        f"CASE WHEN source IN ({', '.join(_sql_text(s) for s in by_date) or 'NULL'}) "
        "THEN CAST(CAST(date AS DATE) AS TIMESTAMPTZ) ELSE CAST(when_scraped AS TIMESTAMPTZ) END"
    )
    select = (
        "SELECT version_id, type, jurisdiction, source, mime, CAST(date AS DATE) AS date, citation, url, "
        "CAST(when_scraped AS TIMESTAMPTZ) AS when_scraped, text, "
        f"CAST(date AS DATE) AS event_at, {observable} AS observable_at, {licence} AS licence, "
        f"{provider} AS provider, length(text) AS text_chars, sha256(text) AS text_sha256, "
        f"sha256({provider} || '|' || version_id || '|' || sha256(text)) AS evidence_id "
        f"FROM {reader} WHERE source IN ({names})"
    )
    try:
        con.execute(
            f"COPY ({select}) TO '{_sql_path(out_dir)}' (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (source), "
            "WRITE_PARTITION_COLUMNS true, ROW_GROUP_SIZE 20000)"
        )
    except duckdb.Error as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        raise CollectError(f"corpus: conversion failed: {first[:200]}") from e
    out: dict[str, Path] = {}
    for name in params.sources:
        parts = sorted((out_dir / f"source={name}").glob("*.parquet"))
        if len(parts) > 1:
            merged = out_dir / f"{name}.parquet"
            listed = ", ".join(f"'{_sql_path(p)}'" for p in parts)
            con.execute(f"COPY (SELECT * FROM read_parquet([{listed}])) TO '{_sql_path(merged)}' "
                        "(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 20000)")  # fmt: skip
            out[name] = merged
        elif parts:
            out[name] = parts[0]
    return out


def profile(con: duckdb.DuckDBPyConnection, path: Path) -> dict:
    """Counts for the release manifest: rows, documents without a date or text, and rows by type."""
    p = f"read_parquet('{_sql_path(path)}')"
    rows, no_date, no_text, dupes = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE date IS NULL), count(*) FILTER (WHERE coalesce(text_chars, 0) = 0), "
        f"count(*) - count(DISTINCT version_id) FROM {p}"
    ).fetchone()
    types = dict(con.execute(f"SELECT coalesce(type, '(none)'), count(*) FROM {p} GROUP BY 1 ORDER BY 1").fetchall())
    return {"rows": int(rows), "no_date": int(no_date), "no_text": int(no_text), "duplicate_ids": int(dupes),
            "types": {k: int(v) for k, v in types.items()}}  # fmt: skip


def refresh(
    card: SourceCard,
    store,
    client: PoliteClient,
    path: Path | None = None,
    work_dir: Path | None = None,
    limit: int | None = None,
    config_hash: str | None = None,
) -> LakeResult:
    """Ingest the card's release unless it is already in the store. `path` reads a local copy instead of
    downloading (its hash is checked all the same); `limit` converts but uploads nothing (a smoke test)."""
    params = HfCorpusParams.model_validate(card.params)
    manifest = Manifest(
        command=f"collect.{card.id}",
        params={"file": "local copy" if path else "download", "revision": params.revision, "limit": limit},
        config_hash=config_hash,
    )
    warnings: list[str] = []
    started = time.monotonic()
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="moria-corpus-"))
    work.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        key = release_key(card.id, params.release)
        if store.exists(key):
            warnings.append(f"corpus: release {params.release} is already ingested; nothing to do")
            manifest.warnings, manifest.counts = warnings, {"unchanged": 1}
            return LakeResult(card.id, "passed", 0, manifest.finish(store, "passed"), None, warnings)

        url = f"{params.base_url}/datasets/{params.repo}/resolve/{params.revision}/{params.file}"
        origin = "local copy" if path else "download"
        if path is None:
            path = work / params.file
            log.info("corpus: downloading %s at %s", params.file, params.revision[:12])
            sha, size = client.download(url, path)
        else:
            sha, size = file_sha256(path), path.stat().st_size
        if sha != params.sha256:
            raise CollectError(f"corpus: the file's SHA-256 is {sha[:16]}..., the card's {params.sha256[:16]}...")
        check_fields(path)

        con = duckdb.connect()
        con.execute(f"SET memory_limit='{params.memory_limit}'")
        con.execute(f"SET threads={int(params.threads)}")
        con.execute("SET preserve_insertion_order=false")
        con.execute("SET TimeZone='UTC'")  # a decision date becomes midnight UTC
        (work / "duckdb-tmp").mkdir(exist_ok=True)
        con.execute(f"SET temp_directory='{_sql_path(work / 'duckdb-tmp')}'")
        t0 = time.monotonic()
        parts = convert(con, params, path, work / "parts")
        log.info("corpus: converted in %.0fs", time.monotonic() - t0)
        if origin == "download":
            path.unlink(missing_ok=True)  # the download is not kept
        missing = sorted(set(params.sources) - set(parts))
        if missing:
            raise CollectError(f"corpus: no documents for {', '.join(missing)}")

        tables: dict[str, dict] = {}
        for name, part in sorted(parts.items()):
            entry = profile(con, part)
            if entry["duplicate_ids"]:
                warnings.append(f"corpus: {name} has {entry['duplicate_ids']} repeated version ids")
            total += entry["rows"]
            tables[name] = {**entry, "licence": params.sources[name].licence,
                            "observable_from": params.sources[name].observable_from}  # fmt: skip
            log.info("corpus: %s: %d documents", name, entry["rows"])
        counts = {"rows": total, "file_bytes": size, **{f"rows_{n}": t["rows"] for n, t in tables.items()}}

        if limit:
            warnings.append("corpus: smoke test; nothing uploaded")
            manifest.counts, manifest.warnings = counts, warnings
            return LakeResult(card.id, "passed", total, manifest.finish(store, "passed"), None, warnings)

        for name, part in sorted(parts.items()):
            lake_key = f"lake/{card.id}/release={params.release}/{name}.parquet"
            tables[name].update(upload_table(store, manifest, lake_key, part))
        record = {
            "parser_version": PARSER_VERSION,
            "repo": params.repo,
            "revision": params.revision,
            "file": {"name": params.file, "sha256": sha, "bytes": size, "origin": origin},
            "released": params.released,
            "evidence_id": "sha256(provider | version_id | sha256(text))",
            "tables": tables,
            "licence": card.licence,
        }
        result = finish_release(
            store, card, manifest, params.release, date.fromisoformat(params.released), record, total, warnings, counts
        )
        log.info("%s: passed in %.0fs, %d documents, release %s", card.id, time.monotonic() - started, total,
                 params.release)  # fmt: skip
        return result
    except Exception as e:
        return fail(card, store, manifest, e, warnings, total)
    finally:
        if not work_dir:
            shutil.rmtree(work, ignore_errors=True)
