"""One delimited text file into the lake (adapter `delimited_csv`): the EC-OECD STIP Compass database (D-020).

STIP Compass publishes its whole database as one file: pipe-separated, with no quoting, a second line of column
labels, and `\\r\\r\\n` line endings; a row is one policy instrument of a policy initiative. Each run:
1. downloads the file (size-capped) and takes its SHA-256 and Last-Modified date;
2. does nothing if the server says the file hasn't changed since the latest release's Last-Modified (a conditional
   request), or if its hash equals that release's (the file is rebuilt after each survey round);
3. otherwise reads it as published: line endings normalised, the label line kept for the manifest, every column as
   text. A row whose field count differs from the header's (an unescaped delimiter inside a field) can't be split
   safely: it is left out, and its first field (the row's id) and the count are in the release manifest. The rest
   becomes one zstd Parquet table at `lake/<source id>/release=<release>/<table>.parquet`, where the release is the
   file's Last-Modified date (else the run's day);
4. writes the release manifest last, with the file's hash, the column ids and labels, and the row counts.

A card whose licence doesn't allow storing text lists its free-text columns in `text_columns` and sets
`store_text: false`; those columns then keep only each value's length.
"""

from __future__ import annotations

import csv
import logging
import shutil
import tempfile
import time
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Literal

import duckdb

from .collectors.base import CollectError
from .config import SourceCard, Strict
from .http import PoliteClient
from .lake import LakeResult, fail, finish_release, release_key, releases, upload_table
from .manifest import Manifest
from .records import sha256_hex

PARSER_VERSION = "delimited-csv-v1"
MAX_MALFORMED_LISTED = 50

log = logging.getLogger("moria.delimited")


class CensusSpec(Strict):
    """What `moria census` counts (aggregates only): distinct ids by code or year columns, and by 0/1 flag columns."""

    id_column: str | None = None
    group_columns: tuple[str, ...] = ()
    flag_prefix: str | None = None


class DelimitedParams(Strict):
    url: str
    table: str  # the Parquet table's name, e.g. "instruments"
    delimiter: str = ","
    quoting: Literal["csv", "none"] = "csv"  # "none": fields are split on the delimiter alone
    label_row: bool = False  # the second line holds column labels
    max_bytes: int = 200_000_000
    max_malformed_share: float = 0.01  # more rows than this that can't be split fails the run
    text_columns: tuple[str, ...] = ()
    store_text: bool = True
    census: CensusSpec = CensusSpec()


def _sql_path(path: Path) -> str:
    text = str(path)
    if "'" in text:
        raise CollectError(f"delimited: a path with a quote can't go into SQL: {text!r}")
    return text


def split_rows(text: str, params: DelimitedParams):
    """Yield the file's rows as lists of fields, line endings normalised ("\\r\\r\\n", "\\r\\n" and "\\n")."""
    text = text.replace("\r\r\n", "\n").replace("\r\n", "\n")
    if params.quoting == "none":
        for line in text.split("\n"):
            if line:
                yield line.split(params.delimiter)
    else:
        csv.field_size_limit(16 * 1024 * 1024)
        for row in csv.reader(text.split("\n"), delimiter=params.delimiter):
            if row:
                yield row


def convert(text: str, params: DelimitedParams, csv_out: Path) -> dict:
    """Write the well-formed rows to a clean CSV; returns the header, labels and counts."""
    rows = split_rows(text, params)
    header = next(rows, None)
    if not header:
        raise CollectError("delimited: the file is empty")
    header = [h.strip() for h in header]
    if len(set(header)) != len(header) or not all(header):
        raise CollectError("delimited: the header has empty or repeated column names")
    labels = next(rows, None) if params.label_row else None
    if params.label_row and (labels is None or len(labels) != len(header)):
        raise CollectError("delimited: the label line doesn't match the header")
    blanked = {header.index(c) for c in params.text_columns if c in header} if not params.store_text else set()
    good, malformed = 0, []
    with open(csv_out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        for row in rows:
            if len(row) != len(header):
                malformed.append(row[0][:200] if row else "")
                continue
            if blanked:
                row = [str(len(v)) if i in blanked else v for i, v in enumerate(row)]
            w.writerow(row)
            good += 1
    missing = [c for c in params.text_columns if c not in header]
    return {
        "header": header,
        "labels": dict(zip(header, labels, strict=True)) if labels else {},
        "rows": good,
        "malformed": len(malformed),
        "malformed_ids": malformed[:MAX_MALFORMED_LISTED],
        "text_columns_missing": missing,
    }


def refresh(
    card: SourceCard,
    store,
    client: PoliteClient,
    limit: int | None = None,
    config_hash: str | None = None,
) -> LakeResult:
    params = DelimitedParams.model_validate(card.params)
    manifest = Manifest(command=f"collect.{card.id}", params={"limit": limit}, config_hash=config_hash)
    warnings: list[str] = []
    started = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix="moria-delimited-"))
    rows = 0
    try:
        previous = releases(store, card.id)
        since = previous[-1].get("file", {}).get("last_modified_header") if previous else None
        resp = client.get(params.url, check_robots=True, headers={"If-Modified-Since": since} if since else None,
                          ok_statuses=(200, 304))  # fmt: skip
        if resp.status_code == 304:
            warnings.append(f"delimited: not modified since release {previous[-1]['release']}; nothing to do")
            manifest.warnings, manifest.counts = warnings, {"unchanged": 1}
            return LakeResult(card.id, "passed", 0, manifest.finish(store, "passed"), None, warnings)
        data = resp.content
        if len(data) > params.max_bytes:
            raise CollectError(f"delimited: the file is {len(data)} bytes, above the cap")
        modified = resp.headers.get("last-modified")
        day = parsedate_to_datetime(modified).astimezone(UTC).date() if modified else None
        file_entry = {"url": params.url, "sha256": sha256_hex(data), "bytes": len(data),
                      "last_modified": day.isoformat() if day else None, "last_modified_header": modified}  # fmt: skip
        if previous and previous[-1].get("file", {}).get("sha256") == file_entry["sha256"]:
            warnings.append(f"delimited: the file is unchanged since release {previous[-1]['release']}; nothing to do")
            manifest.warnings, manifest.counts = warnings, {"unchanged": 1}
            return LakeResult(card.id, "passed", 0, manifest.finish(store, "passed"), None, warnings)
        release = (day or datetime.now(UTC).date()).isoformat()
        if store.exists(release_key(card.id, release)):
            raise CollectError(f"delimited: release {release} exists but its file differs; a person should look")

        csv_path, out = work / "clean.csv", work / f"{params.table}.parquet"
        info = convert(data.decode("utf-8-sig"), params, csv_path)
        del data
        rows = info["rows"]
        if info["malformed"] > params.max_malformed_share * max(rows + info["malformed"], 1):
            raise CollectError(f"delimited: {info['malformed']} rows can't be split, above the card's share")
        if info["malformed"]:
            warnings.append(
                f"delimited: {info['malformed']} rows with a stray delimiter left out (ids in the manifest)"
            )
        if info["text_columns_missing"]:
            warnings.append(f"delimited: text columns not in the file: {', '.join(info['text_columns_missing'])}")
        con = duckdb.connect()
        con.execute("SET memory_limit='2GB'")
        try:
            con.execute(f"COPY (SELECT * FROM read_csv('{_sql_path(csv_path)}', header=true, all_varchar=true, "
                        f"quote='\"', escape='\"', delim=',')) TO '{_sql_path(out)}' "
                        "(FORMAT parquet, COMPRESSION zstd)")  # fmt: skip
            written = con.execute(f"SELECT count(*) FROM read_parquet('{_sql_path(out)}')").fetchone()[0]
        except duckdb.Error as e:
            first = (str(e).splitlines() or [type(e).__name__])[0]
            raise CollectError(f"delimited: could not be converted: {first[:200]}") from e
        finally:
            csv_path.unlink(missing_ok=True)
        if written != rows:
            raise CollectError(f"delimited: {rows} rows read but {written} written")
        counts = {"rows": rows, "rows_malformed": info["malformed"], "columns": len(info["header"])}
        log.info("delimited: %s: %d rows, %d columns, %d left out", card.id, rows, len(info["header"]),
                 info["malformed"])  # fmt: skip
        if limit:
            warnings.append("delimited: smoke test; nothing uploaded")
            manifest.counts, manifest.warnings = counts, warnings
            return LakeResult(card.id, "passed", rows, manifest.finish(store, "passed"), None, warnings)
        table = upload_table(store, manifest, f"lake/{card.id}/release={release}/{params.table}.parquet", out)
        record = {
            "parser_version": PARSER_VERSION,
            "file": file_entry,
            "tables": {params.table: {**table, "rows": rows}},
            "columns": info["header"],
            "labels": info["labels"],
            "malformed": {"rows": info["malformed"], "first_fields": info["malformed_ids"]},
            "text_stored": params.store_text or not params.text_columns,
            "licence": card.licence,
        }
        result = finish_release(store, card, manifest, release, date.fromisoformat(release), record, rows, warnings,
                                counts)  # fmt: skip
        log.info("%s: passed in %.0fs, %d rows, release %s", card.id, time.monotonic() - started, rows, release)
        return result
    except Exception as e:
        return fail(card, store, manifest, e, warnings, rows)
    finally:
        shutil.rmtree(work, ignore_errors=True)
