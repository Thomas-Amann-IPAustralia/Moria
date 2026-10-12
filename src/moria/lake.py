"""Shared steps of the bulk stages that write typed Parquet to the lake rather than raw bundles (design §4.3): the
Open Australian Legal Corpus (`moria.corpus`) and the WIPO statistics files (`moria.bulk`). IP RAPID (`moria.ipr`)
came first and keeps its own copy of these steps.

A bulk release is ingested once. Its release manifest, `raw/<source>/<release>/manifest.json`, is immutable and
written last, so it marks the release as ingested; it records where the files came from, their SHA-256 and size,
and each table written. The run also writes an ingestion-monitor entry and a run manifest, failed runs included.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .collectors.base import Window, monitor_entry
from .config import SourceCard
from .manifest import Manifest
from .records import canonical_json
from .store import Store

PARQUET = "application/vnd.apache.parquet"

log = logging.getLogger("moria.lake")


@dataclass
class LakeResult:
    """Shaped like a CollectResult, so `collect` and the scheduled commands report it the same way."""

    source: str
    status: str
    records: int
    manifest_key: str
    bundle_key: str | None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def release_key(source: str, release: str) -> str:
    return f"raw/{source}/{release}/manifest.json"


def releases(store: Store, source: str) -> list[dict]:
    """The release manifests of a source, oldest first (by release id)."""
    import json

    keys = sorted(k for k in store.list(f"raw/{source}/") if k.endswith("/manifest.json"))
    return [json.loads(store.get(k)) for k in keys]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_table(store: Store, manifest: Manifest, key: str, path: Path) -> dict:
    """Upload one Parquet file to the lake; returns its key, SHA-256 and size for the release manifest."""
    sha, size = file_sha256(path), path.stat().st_size
    store.put_file(key, path, PARQUET)
    manifest.add_output_file(key, sha, size)
    return {"key": key, "sha256": sha, "bytes": size}


def finish_release(
    store: Store,
    card: SourceCard,
    manifest: Manifest,
    release: str,
    release_day: date,
    record: dict,
    rows: int,
    warnings: list[str],
    counts: dict[str, int],
) -> LakeResult:
    """Write the release manifest (last, as the release's mark), the monitor entry and the run manifest."""
    key = release_key(card.id, release)
    data = canonical_json({"source": card.id, "release": release, "run_id": manifest.run_id, **record}).encode()
    store.put(key, data, "application/json")
    manifest.add_output(key, data)
    monitor = monitor_entry(card, Window.for_day(release_day), rows, manifest.run_id, "passed")
    monitor_key = f"monitors/ingestion/source={card.id}/{release_day.isoformat()}/{manifest.run_id}.json"
    store.put(monitor_key, monitor, "application/json")
    manifest.add_output(monitor_key, monitor)
    if b'"flag":"ok"' not in monitor:
        warnings.append(f"ingestion monitor: {rows} rows is outside the expected band")
    manifest.params["release"] = release
    manifest.counts, manifest.warnings = counts, warnings
    return LakeResult(card.id, "passed", rows, manifest.finish(store, "passed"), None, warnings)


def fail(
    card: SourceCard, store: Store, manifest: Manifest, e: Exception, warnings: list[str], rows: int
) -> LakeResult:
    first = (str(e).splitlines() or [type(e).__name__])[0]
    cause = f"{card.id}: {type(e).__name__}: {first[:300]}"
    manifest.warnings, manifest.counts = warnings, {"rows": rows}
    mkey = manifest.finish(store, "failed", cause)
    log.error("%s: failed; cause: %s", card.id, cause)
    return LakeResult(card.id, "failed", 0, mkey, None, warnings, cause)
