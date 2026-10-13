"""The evidence layer's tables (design §6.2) and the helpers that read and write them as Parquet.

Rows are sorted before writing, and Parquet files carry no timestamps of their own, so the same inputs give the same
bytes (SOP §16.1). Times are UTC, to the second.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .lake import PARQUET, file_sha256
from .manifest import Manifest
from .store import Store

log = logging.getLogger("moria.tables")

TS = pa.timestamp("s", tz="UTC")
STRS = pa.list_(pa.string())

DOCUMENTS = pa.schema(
    [
        ("item_id", pa.string()),  # SHA-256 of source | provider_record_id: one row per item, its latest version
        ("source", pa.string()),
        ("evidence_id", pa.string()),  # the latest version's
        ("n_versions", pa.int32()),
        ("provider", pa.string()),
        ("source_collection", pa.string()),
        ("provider_record_id", pa.string()),
        ("doc_type", pa.string()),
        ("family", pa.string()),
        ("rings", STRS),  # the source card's rings
        ("domains", STRS),
        ("licence", pa.string()),
        ("title", pa.string()),
        ("summary", pa.string()),
        ("text", pa.string()),  # an excerpt of the stored text, or empty when the source's text is not stored
        ("text_chars", pa.int64()),  # the full text's length where it was collected
        ("text_stored", pa.bool_()),
        ("url", pa.string()),
        ("url_canonical", pa.string()),
        ("outlet", pa.string()),  # who published it: a news domain, else the source
        ("country", pa.string()),
        ("event_at", TS),
        ("observable_at", TS),
        ("observable_basis", pa.string()),  # source | first_sight | clamped (a source date after first sight)
        ("first_seen_at", TS),
        ("retrieved_at", TS),
        ("raw_object_uri", pa.string()),
        ("parser_version", pa.string()),
        ("extra", pa.string()),  # canonical JSON: the source's own metadata (categories, GKG themes, statuses...)
        ("sweep_codes", STRS),  # low and medium findings; high ones are quarantined
        ("title_key", pa.string()),
    ]
)

OBSERVATIONS = pa.schema(
    [
        ("series_id", pa.string()),
        ("source", pa.string()),
        ("period", pa.string()),  # as published
        ("period_kind", pa.string()),  # year, half, quarter, month, day, other
        ("period_start", pa.date32()),
        ("value", pa.float64()),
        ("value_text", pa.string()),  # a value published as words
        ("status", pa.string()),
        ("vintage_at", TS),  # when this value became observable to Moria; point in time: latest vintage <= as_of
    ]
)

SERIES = pa.schema(
    [
        ("series_id", pa.string()),
        ("source", pa.string()),
        ("provider", pa.string()),
        ("source_collection", pa.string()),
        ("label", pa.string()),
        ("measure", pa.string()),
        ("unit", pa.string()),
        ("frequency", pa.string()),
        ("scope", pa.string()),  # world, au, or a country or region code
        ("dimensions", pa.string()),  # canonical JSON
        ("family", pa.string()),
        ("rings", STRS),
        ("domains", STRS),
        ("licence", pa.string()),
        ("n_obs", pa.int32()),  # in the latest vintage
        ("first_period", pa.string()),
        ("last_period", pa.string()),
        ("n_vintages", pa.int32()),
        ("first_seen_at", TS),
        ("latest_vintage_at", TS),
        ("raw_object_uri", pa.string()),
    ]
)

QUARANTINE = pa.schema(
    [
        ("item_id", pa.string()),
        ("source", pa.string()),
        ("evidence_id", pa.string()),
        ("codes", STRS),  # finding codes only, never the text
        ("raw_object_uri", pa.string()),
    ]
)


def write_rows(rows: list[dict], schema: pa.Schema, path: Path, sort: tuple[str, ...]) -> int:
    """Rows sorted by `sort`, written as one zstd Parquet file; returns the row count."""
    rows = sorted(rows, key=lambda r: tuple("" if r.get(k) is None else r[k] for k in sort))
    table = pa.Table.from_pylist(rows, schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd", row_group_size=50_000, write_statistics=True)
    return len(rows)


def read_rows(path: Path, columns: list[str] | None = None) -> list[dict]:
    return pq.read_table(path, columns=columns).to_pylist()


def upload(store: Store, manifest: Manifest, key: str, path: Path) -> dict:
    sha, size = file_sha256(path), path.stat().st_size
    store.put_file(key, path, PARQUET)
    manifest.add_output_file(key, sha, size)
    return {"key": key, "sha256": sha, "bytes": size}


def cached_get(store: Store, key: str, sha256: str | None, cache_root: Path) -> Path:
    """A store object as a local file, re-downloaded only when the cached copy's SHA-256 doesn't match."""
    path = cache_root / key
    if path.exists() and sha256 and file_sha256(path) == sha256:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    store.get_file(key, tmp)
    tmp.replace(path)
    if sha256 and file_sha256(path) != sha256:
        raise ValueError(f"{key}: SHA-256 does not match its manifest")
    return path


def latest_manifest(store: Store, command: str) -> dict | None:
    """The newest run manifest of a command (run ids sort by time)."""
    keys = sorted(k for k in store.list(f"manifests/{command}/") if k.endswith(".json"))
    return json.loads(store.get(keys[-1])) if keys else None


class StageInputError(RuntimeError):
    """The upstream stage's output is missing, failed, or no longer matches its manifest."""


def upstream(store: Store, command: str) -> dict:
    """The upstream stage's latest manifest, which must have passed (SOP §16.1)."""
    m = latest_manifest(store, command)
    if m is None:
        raise StageInputError(f"no {command} run in the store; run `moria {command.replace('.', ' ')}` first")
    if m["status"] != "passed":
        raise StageInputError(f"the latest {command} run ({m['run_id']}) {m['status']}: {m.get('error')}")
    return m


def fetch_outputs(store: Store, manifest: dict, prefix: str, cache_root: Path) -> dict[str, Path]:
    """Every output of an upstream manifest under `prefix`, as local files checked against the manifest's hashes."""
    out = {}
    for o in manifest["outputs"]:
        if o["key"].startswith(prefix):
            try:
                out[o["key"]] = cached_get(store, o["key"], o["sha256"], cache_root)
            except ValueError as e:
                raise StageInputError(str(e)) from e
    return out
