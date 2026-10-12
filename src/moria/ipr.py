"""IP RAPID, IP Australia's weekly open data on patents, trade marks, designs and plant breeder's rights (CC BY 4.0):
`moria ipr refresh` (design §7).

Each weekly release is one zip of six CSV tables: 1.35 GB zipped, 9.6 GB of CSV and about 93M rows in October 2026.
The tables are read one at a time. Each CSV is streamed out of the zip to a temporary file, then DuckDB converts it to
typed, zstd-compressed Parquet: dates become DATE (strictly parsed, so a malformed date fails the run rather than
being guessed), and is_ flags become BOOLEAN. The zip itself is not kept: its SHA-256, its size and the catalogue's
metadata go into an immutable release manifest at raw/ip_rapid/<release>/manifest.json.

Privacy (design §12): in party_activity, every party that is not an organisation (individuals, and parties with no
type) has its name replaced by 'sha256:' + sha256('moria-ipr-person-v1|' + the name, lower-cased with its spaces
collapsed), and its postcode dropped. This happens inside the conversion query, before anything is written. IP
Australia's own party_id is kept, so filings can still be counted per party without a name. The hash pseudonymises:
anyone with the public file can hash its names too, so the purpose is that Moria's lake and outputs never carry a
person's name, not secrecy. Every table's columns are checked against the published schema first, so a renamed name
column can never slip past the hashing.

The lake holds a base snapshot and weekly deltas against it:
  lake/ip_rapid/base=<release>/<table>.parquet    every row of that release
  lake/ip_rapid/delta=<release>/<table>.parquet   rows added since the base (_change='added') and rows of the base
                                                  no longer present (_change='removed')
A week's state is its base plus its own delta. A new base is written when there is none, when the latest is
`rebase_days` old (91, about quarterly), or when a table's schema changed, so the free 10 GB of storage isn't spent
on weekly full copies (a base is about 1 GB).
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import duckdb

from .collectors.base import CollectError, Window, monitor_entry
from .config import SourceCard, Strict
from .http import FetchError, PoliteClient
from .manifest import Manifest
from .records import canonical_json
from .store import Store

PARSER_VERSION = "ip-rapid-v1"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%gZ"  # every date in the release is midnight UTC in this form (checked 2026-10-12)
PERSON_HASH_LABEL = "moria-ipr-person-v1"  # part of the hash: changing it breaks the continuity of party hashes
LAKE = "lake/ip_rapid"

# The published columns of each table (2026-10-12; the data dictionary of 2023-08-01 differs in order only). An
# unknown or missing column fails the run until a person updates this list.
SCHEMA: dict[str, list[str]] = {
    "application": [
        "ip_right_type", "application_number", "ip_right_sub_type", "status", "application_date",
        "earliest_filed_date", "priority_date", "gained_registration_status_date", "gained_enforceable_status_date",
        "enforceable_from_date", "deemed_retired_date",
    ],
    "application_classification": [
        "ip_right_type", "application_number", "classification_system", "classification",
        "classification_importance", "classification_inventiveness", "classification_source",
        "classifying_country_code", "classification_date", "classification_removal_date",
        "classification_system_version", "is_current", "classification_area", "coarse_classification_area",
    ],
    "application_description": ["ip_right_type", "application_number", "description_type", "description_value"],
    "application_events": [
        "application_number", "ip_right_type", "event_type", "event_category", "event_effective_date",
        "event_declared_date", "is_standing",
    ],
    "application_links": [
        "ip_right_type", "application_number", "link_type", "linked_application_number", "link_date",
        "linked_application_country",
    ],
    "party_activity": [
        "ip_right_type", "application_number", "party_id", "abn", "party_role_category", "party_role", "party_type",
        "party_name", "state_code", "post_code", "country_code", "effective_from_date", "effective_to_date",
        "is_current", "is_founding",
    ],
}  # fmt: skip

log = logging.getLogger("moria.ipr")


class IprParams(Strict):
    ckan_package_url: str
    resource_name: str = "IPRAPID.zip"
    rebase_days: int = 91
    memory_limit: str = "2GB"
    threads: int = 4


@dataclass
class Release:
    url: str
    size: int | None
    last_modified: str
    release_date: date


@dataclass
class IprResult:
    """Shaped like a CollectResult, so `collect` and `collect-weekly` report it the same way."""

    source: str
    status: str
    records: int
    manifest_key: str
    bundle_key: str | None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def _sql_path(path: Path) -> str:
    text = str(path)
    if "'" in text:
        raise CollectError(f"ipr: a path with a quote can't go into SQL: {text!r}")
    return text


def _ident(name: str) -> str:
    # Column names come from the source's header, so they are checked before they go into SQL
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise CollectError(f"ipr: an unexpected column name {name[:40]!r}")
    return f'"{name}"'


def column_sql(table: str, column: str) -> str:
    q = _ident(column)
    if table == "party_activity" and column == "party_name":
        normalised = r"lower(regexp_replace(trim(party_name), '\s+', ' ', 'g'))"
        return (
            "CASE WHEN party_type = 'organisation' THEN party_name WHEN party_name IS NULL THEN NULL "
            f"ELSE 'sha256:' || sha256('{PERSON_HASH_LABEL}|' || {normalised}) END AS party_name"
        )
    if table == "party_activity" and column == "post_code":
        return "CASE WHEN party_type = 'organisation' THEN post_code END AS post_code"
    if column.endswith("_date"):
        return f"CAST(strptime({q}, '{DATE_FORMAT}') AS DATE) AS {q}"
    if column.startswith(("is_", "has_")):
        return f"CAST({q} AS BOOLEAN) AS {q}"
    return q


def connect(params: IprParams, work: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{params.memory_limit}'")
    con.execute(f"SET threads={int(params.threads)}")
    con.execute("SET preserve_insertion_order=false")
    (work / "duckdb-tmp").mkdir(exist_ok=True)
    con.execute(f"SET temp_directory='{_sql_path(work / 'duckdb-tmp')}'")
    return con


def convert_table(con: duckdb.DuckDBPyConnection, zip_path: Path, table: str, work: Path) -> tuple[Path, int]:
    """One table: CSV out of the zip to a temporary file, then typed and privacy-safe Parquet. Returns (path, rows)."""
    csv_path, out = work / f"{table}.csv", work / f"{table}.parquet"
    with zipfile.ZipFile(zip_path) as zf, zf.open(f"{table}.csv") as src, open(csv_path, "wb") as dst:
        shutil.copyfileobj(src, dst, 16 * 1024 * 1024)  # zipfile checks the member's CRC as it reads to the end
    try:
        source = (
            f"read_csv('{_sql_path(csv_path)}', all_varchar=true, header=true, quote='\"', escape='\\', "
            "strict_mode=true)"
        )
        columns = [d[0] for d in con.execute(f"SELECT * FROM {source} LIMIT 0").description]
        expected = SCHEMA[table]
        if sorted(columns) != sorted(expected):
            unknown, missing = sorted(set(columns) - set(expected)), sorted(set(expected) - set(columns))
            raise CollectError(f"ipr: {table} columns changed (unknown {unknown}, missing {missing})")
        select = ", ".join(column_sql(table, c) for c in expected)  # always in the published order
        con.execute(
            f"COPY (SELECT {select} FROM {source}) TO '{_sql_path(out)}' "
            "(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)"
        )
        rows = con.execute(f"SELECT count(*) FROM read_parquet('{_sql_path(out)}')").fetchone()[0]
    except duckdb.Error as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        raise CollectError(f"ipr: {table} could not be converted: {first[:200]}") from e
    finally:
        csv_path.unlink(missing_ok=True)
    return out, int(rows)


def schema_of(con: duckdb.DuckDBPyConnection, path: Path) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{_sql_path(path)}')").fetchall()]


def write_delta(con: duckdb.DuckDBPyConnection, new: Path, base: Path, out: Path) -> tuple[int, int]:
    """Rows added since the base and rows of the base no longer present, as a multiset difference both ways."""
    n, b = f"read_parquet('{_sql_path(new)}')", f"read_parquet('{_sql_path(base)}')"
    con.execute(
        f"COPY (SELECT 'added' AS _change, * FROM (SELECT * FROM {n} EXCEPT ALL SELECT * FROM {b}) "
        f"UNION ALL SELECT 'removed' AS _change, * FROM (SELECT * FROM {b} EXCEPT ALL SELECT * FROM {n})) "
        f"TO '{_sql_path(out)}' (FORMAT parquet, COMPRESSION zstd)"
    )
    counts = dict(con.execute(f"SELECT _change, count(*) FROM read_parquet('{_sql_path(out)}') GROUP BY 1").fetchall())
    return int(counts.get("added", 0)), int(counts.get("removed", 0))


def release_info(client: PoliteClient, params: IprParams) -> Release:
    """The release on offer, from data.gov.au's catalogue (CKAN): its download URL, size and modification time."""
    try:
        result = client.get(params.ckan_package_url).json()["result"]
    except (FetchError, ValueError, KeyError) as e:
        raise CollectError(f"ipr: the catalogue entry could not be read: {e}") from e
    for resource in result.get("resources", []):
        if resource.get("name") == params.resource_name:
            modified = resource.get("last_modified") or resource.get("metadata_modified") or ""
            try:
                day = datetime.fromisoformat(modified).date()
            except ValueError as e:
                raise CollectError(f"ipr: the catalogue's last_modified is not a date: {modified!r}") from e
            size = resource.get("size")
            return Release(resource["url"], int(size) if size else None, modified, day)
    raise CollectError(f"ipr: no resource named {params.resource_name!r} in the catalogue entry")


def _bases(store: Store) -> list[date]:
    found = set()
    for key in store.list(f"{LAKE}/base="):
        part = key[len(f"{LAKE}/base=") :].split("/", 1)[0]
        try:
            found.add(date.fromisoformat(part))
        except ValueError:
            continue
    return sorted(found)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def refresh(
    card: SourceCard,
    store: Store,
    client: PoliteClient,
    zip_path: Path | None = None,
    work_dir: Path | None = None,
    limit: int | None = None,
    config_hash: str | None = None,
) -> IprResult:
    """Ingest the current release unless it is already in the store. Writes a manifest whether it passes or fails."""
    params = IprParams.model_validate(card.params)
    manifest = Manifest(
        command="ipr.refresh",
        params={"zip": "local file" if zip_path else "download", "limit": limit},
        config_hash=config_hash,
    )
    warnings: list[str] = []
    started = time.monotonic()
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="moria-ipr-"))
    work.mkdir(parents=True, exist_ok=True)
    total_rows = 0
    try:
        release = release_info(client, params)
        rel = release.release_date.isoformat()
        release_key = f"raw/ip_rapid/{rel}/manifest.json"
        manifest.params["release"] = rel
        if store.exists(release_key):
            warnings.append(f"ipr: release {rel} is already ingested; nothing to do")
            log.info("ipr: release %s is already ingested", rel)
            manifest.warnings, manifest.counts = warnings, {"unchanged": 1}
            return IprResult(card.id, "passed", 0, manifest.finish(store, "passed"), None, warnings)

        if zip_path is None:
            zip_path = work / "iprapid.zip"
            log.info("ipr: downloading release %s (%s bytes)", rel, release.size)
            zip_sha, zip_bytes = client.download(release.url, zip_path)
            origin = "download"
        else:
            zip_sha, zip_bytes, origin = _file_sha256(zip_path), zip_path.stat().st_size, "local file"
        if release.size is not None and zip_bytes != release.size:
            raise CollectError(f"ipr: the zip has {zip_bytes} bytes; the catalogue's release {rel} has {release.size}")

        with zipfile.ZipFile(zip_path) as zf:
            members = set(zf.namelist())
        missing = sorted(f"{t}.csv" for t in SCHEMA if f"{t}.csv" not in members)
        if missing:
            raise CollectError(f"ipr: the zip lacks {', '.join(missing)}")
        extra = sorted(members - {f"{t}.csv" for t in SCHEMA})
        if extra:
            warnings.append(f"ipr: the zip has tables not ingested yet: {', '.join(extra)}")

        tables = list(SCHEMA)[:limit] if limit else list(SCHEMA)
        con = connect(params, work)
        converted: dict[str, tuple[Path, int]] = {}
        for i, table in enumerate(tables, start=1):
            t0 = time.monotonic()
            converted[table] = convert_table(con, zip_path, table, work)
            log.info("ipr [%d/%d] %s: %d rows in %.0fs", i, len(tables), table, converted[table][1],
                     time.monotonic() - t0)  # fmt: skip

        if limit:
            warnings.append(f"ipr: smoke test of {len(tables)} table(s); nothing uploaded")
            total_rows = sum(rows for _, rows in converted.values())
            manifest.counts = {"rows": total_rows, "zip_bytes": zip_bytes,
                               **{f"rows_{t}": r for t, (_, r) in converted.items()}}  # fmt: skip
            manifest.warnings = warnings
            return IprResult(card.id, "passed", total_rows, manifest.finish(store, "passed"), None, warnings)

        bases = _bases(store)
        base = bases[-1] if bases else None
        mode = "base"
        if base is not None and base > release.release_date:
            raise CollectError(f"ipr: release {rel} is older than the latest base ({base})")
        if base is not None and base < release.release_date and (release.release_date - base).days < params.rebase_days:
            mode = "delta"
            for table, (path, _) in converted.items():
                base_path = work / f"base-{table}.parquet"
                store.get_file(f"{LAKE}/base={base}/{table}.parquet", base_path)
                if schema_of(con, base_path) != schema_of(con, path):
                    warnings.append(f"ipr: {table}'s schema differs from base {base}; writing a new base")
                    mode = "base"
                    break
        log.info("ipr: writing a %s for release %s%s", mode, rel, f" against base {base}" if mode == "delta" else "")

        tables_out: dict[str, dict] = {}
        for table, (path, rows) in converted.items():
            total_rows += rows
            entry: dict = {"rows": rows}
            if mode == "base":
                key, upload = f"{LAKE}/base={rel}/{table}.parquet", path
            else:
                key, upload = f"{LAKE}/delta={rel}/{table}.parquet", work / f"delta-{table}.parquet"
                entry["added"], entry["removed"] = write_delta(con, path, work / f"base-{table}.parquet", upload)
                log.info("ipr: %s delta: %d added, %d removed", table, entry["added"], entry["removed"])
            sha, size = _file_sha256(upload), upload.stat().st_size
            store.put_file(key, upload, "application/vnd.apache.parquet")
            manifest.add_output_file(key, sha, size)
            entry.update({"key": key, "sha256": sha, "bytes": size})
            tables_out[table] = entry

        record = {
            "source": card.id,
            "release_date": rel,
            "parser_version": PARSER_VERSION,
            "catalogue": {"url": release.url, "size": release.size, "last_modified": release.last_modified},
            "zip": {"sha256": zip_sha, "bytes": zip_bytes, "origin": origin},
            "mode": mode,
            "base_release": rel if mode == "base" else base.isoformat(),
            "person_hash": f"'sha256:' + sha256('{PERSON_HASH_LABEL}|' + lower-cased name with spaces collapsed)",
            "tables": tables_out,
            "run_id": manifest.run_id,
            "licence": card.licence,
        }
        data = canonical_json(record).encode("utf-8")
        store.put(release_key, data, "application/json")  # written last: it marks the release as ingested
        manifest.add_output(release_key, data)
        monitor = monitor_entry(card, Window.for_day(release.release_date), total_rows, manifest.run_id, "passed")
        monitor_key = f"monitors/ingestion/source={card.id}/{rel}/{manifest.run_id}.json"
        store.put(monitor_key, monitor, "application/json")
        manifest.add_output(monitor_key, monitor)
        if b'"flag":"ok"' not in monitor:
            warnings.append(f"ingestion monitor: {total_rows} rows is outside the expected band")
        manifest.counts = {
            "rows": total_rows,
            "zip_bytes": zip_bytes,
            **{f"rows_{t}": e["rows"] for t, e in tables_out.items()},
            **{f"added_{t}": e["added"] for t, e in tables_out.items() if "added" in e},
            **{f"removed_{t}": e["removed"] for t, e in tables_out.items() if "removed" in e},
        }
        manifest.params["mode"] = mode
        manifest.warnings = warnings
        mkey = manifest.finish(store, "passed")
        log.info("ip_rapid: passed in %.0fs, %d rows, mode %s, release %s", time.monotonic() - started, total_rows,
                 mode, rel)  # fmt: skip
        return IprResult(card.id, "passed", total_rows, mkey, None, warnings)
    except Exception as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        cause = f"{card.id}: {type(e).__name__}: {first[:300]}"
        manifest.warnings, manifest.counts = warnings, {"rows": total_rows}
        mkey = manifest.finish(store, "failed", cause)
        log.error("ip_rapid: failed in %.0fs; cause: %s", time.monotonic() - started, cause)
        return IprResult(card.id, "failed", 0, mkey, None, warnings, cause)
    finally:
        if not work_dir:
            shutil.rmtree(work, ignore_errors=True)
        else:
            for leftover in Path(work).glob("*.csv"):
                leftover.unlink(missing_ok=True)
