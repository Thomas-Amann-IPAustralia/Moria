"""Zipped CSV files into the lake (adapter `zip_csv`): WIPO's bulk IP statistics (D-016, T5).

WIPO's IP Statistics Data Center is disallowed by robots.txt, but WIPO publishes bulk ZIP files of its indicators on
its statistics page (patent publications and grants by technology field, trade mark and design applications and
registrations by class, by office and origin, yearly). Each run:
1. downloads every file in the card (size-capped) and takes its SHA-256 and Last-Modified date;
2. does nothing if every file's hash equals the latest release's (the files change rarely);
3. otherwise converts each CSV member to zstd Parquet with DuckDB (types detected, the header required) at
   `lake/<source id>/release=<release>/<file id>__<member stem>.parquet`, where the release is the newest
   Last-Modified date among the files (else the run's day);
4. writes the release manifest last, with each file's hash and each table's columns and rows.
The ZIP files are not kept. Members that are not CSV are listed in the manifest, not converted.
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import tempfile
import time
import zipfile
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import duckdb

from .collectors.base import CollectError
from .config import SourceCard, Strict
from .http import PoliteClient
from .lake import LakeResult, fail, finish_release, release_key, releases, upload_table
from .manifest import Manifest
from .records import sha256_hex

PARSER_VERSION = "zip-csv-v1"

log = logging.getLogger("moria.bulk")


class ZipFileSpec(Strict):
    id: str  # Moria's name for the file, e.g. "patent_indicators"
    url: str


class ZipCsvParams(Strict):
    files: list[ZipFileSpec]
    max_bytes: int = 200_000_000  # per downloaded file
    max_member_bytes: int = 500_000_000  # per CSV, uncompressed


def _safe(name: str) -> str:
    stem = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    if not stem:
        raise CollectError(f"bulk: an unusable member name {name[:40]!r}")
    return stem


def _sql_path(path: Path) -> str:
    text = str(path)
    if "'" in text:
        raise CollectError(f"bulk: a path with a quote can't go into SQL: {text!r}")
    return text


def refresh(
    card: SourceCard,
    store,
    client: PoliteClient,
    limit: int | None = None,
    config_hash: str | None = None,
) -> LakeResult:
    params = ZipCsvParams.model_validate(card.params)
    manifest = Manifest(command=f"collect.{card.id}", params={"limit": limit}, config_hash=config_hash)
    warnings: list[str] = []
    started = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix="moria-bulk-"))
    total = 0
    try:
        files = params.files[:limit] if limit else params.files
        got: dict[str, dict] = {}
        for spec in files:
            resp = client.get(spec.url)
            data = resp.content
            if len(data) > params.max_bytes:
                raise CollectError(f"bulk: {spec.id} is {len(data)} bytes, above the cap")
            modified = resp.headers.get("last-modified")
            day = parsedate_to_datetime(modified).astimezone(UTC).date() if modified else None
            got[spec.id] = {"data": data, "sha256": sha256_hex(data), "bytes": len(data), "url": spec.url,
                            "last_modified": day.isoformat() if day else None}  # fmt: skip
        previous = releases(store, card.id)
        if previous and all(previous[-1].get("files", {}).get(i, {}).get("sha256") == g["sha256"]
                            for i, g in got.items()):  # fmt: skip
            warnings.append(f"bulk: the files are unchanged since release {previous[-1]['release']}; nothing to do")
            manifest.warnings, manifest.counts = warnings, {"unchanged": 1}
            return LakeResult(card.id, "passed", 0, manifest.finish(store, "passed"), None, warnings)
        days = [date.fromisoformat(g["last_modified"]) for g in got.values() if g["last_modified"]]
        release = max(days).isoformat() if days else datetime.now(UTC).date().isoformat()
        if store.exists(release_key(card.id, release)):
            raise CollectError(f"bulk: release {release} exists but its files differ; a person should look")

        con = duckdb.connect()
        con.execute("SET memory_limit='2GB'")
        tables: dict[str, dict] = {}
        file_entries: dict[str, dict] = {}
        for file_id, g in got.items():
            skipped = []
            with zipfile.ZipFile(io.BytesIO(g["data"])) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    if not info.filename.lower().endswith(".csv"):
                        skipped.append(info.filename)
                        continue
                    if info.file_size > params.max_member_bytes:
                        raise CollectError(
                            f"bulk: {info.filename} is {info.file_size} bytes uncompressed, above the cap"
                        )
                    name = f"{_safe(file_id)}__{_safe(Path(info.filename).stem)}"
                    csv_path, out = work / f"{name}.csv", work / f"{name}.parquet"
                    with zf.open(info) as src, open(csv_path, "wb") as dst:
                        shutil.copyfileobj(src, dst, 16 * 1024 * 1024)
                    try:
                        con.execute(f"COPY (SELECT * FROM read_csv('{_sql_path(csv_path)}', header=true)) TO "
                                    f"'{_sql_path(out)}' (FORMAT parquet, COMPRESSION zstd)")  # fmt: skip
                        desc = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{_sql_path(out)}')").fetchall()
                        rows = con.execute(f"SELECT count(*) FROM read_parquet('{_sql_path(out)}')").fetchone()[0]
                    except duckdb.Error as e:
                        first = (str(e).splitlines() or [type(e).__name__])[0]
                        raise CollectError(f"bulk: {info.filename} could not be converted: {first[:200]}") from e
                    finally:
                        csv_path.unlink(missing_ok=True)
                    tables[name] = {"file": file_id, "member": info.filename, "rows": int(rows),
                                    "columns": [[d[0], d[1]] for d in desc], "path": out}  # fmt: skip
                    total += int(rows)
                    log.info("bulk: %s: %d rows", name, rows)
            file_entries[file_id] = {k: v for k, v in g.items() if k != "data"} | {"not_converted": skipped}
        if not tables:
            raise CollectError("bulk: no CSV in any file")
        counts = {"rows": total, **{f"rows_{n}": t["rows"] for n, t in tables.items()}}
        if limit:
            warnings.append("bulk: smoke test; nothing uploaded")
            manifest.counts, manifest.warnings = counts, warnings
            return LakeResult(card.id, "passed", total, manifest.finish(store, "passed"), None, warnings)
        for name, t in tables.items():
            t.update(upload_table(store, manifest, f"lake/{card.id}/release={release}/{name}.parquet", t.pop("path")))
        record = {"parser_version": PARSER_VERSION, "files": file_entries, "tables": tables, "licence": card.licence}
        result = finish_release(store, card, manifest, release, date.fromisoformat(release), record, total, warnings,
                                counts)  # fmt: skip
        log.info("%s: passed in %.0fs, %d rows, release %s", card.id, time.monotonic() - started, total, release)
        return result
    except Exception as e:
        return fail(card, store, manifest, e, warnings, total)
    finally:
        shutil.rmtree(work, ignore_errors=True)
