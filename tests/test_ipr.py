"""The IP RAPID ingest, against a hand-built six-table zip (placeholder values, never real IP RAPID rows)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import duckdb
import httpx
import pytest

from moria.config import SourceCard
from moria.ipr import PERSON_HASH_LABEL, SCHEMA, refresh

from .conftest import card, make_client

D = "T00:00:00.000Z"
ROWS = {
    "application": [
        f"patent,2026000001,standard_complete,filed,2026-01-05{D},2026-01-05{D},2025-12-01{D},,,,",
        f"trade_mark,2026000002,trade_mark,registered,2026-02-01{D},2026-02-01{D},2026-02-01{D},2026-06-01{D},"
        f"2026-06-01{D},2026-02-01{D},",
    ],
    "application_classification": [
        f"patent,2026000001,ipc_mark,G06N 3/08,primary,inventive,machine,au,2026-03-01{D},,None,true,"
        "06_computer_technology,electrical_engineering",
    ],
    "application_description": ["patent,2026000001,description,Placeholder title of an invention"],
    "application_events": [
        f"2026000001,patent,filed,filing,2026-01-05{D},,1",
        f"2026000002,trade_mark,registered,registered,2026-06-01{D},2026-06-01{D},0",
    ],
    "application_links": [f"patent,2026000001,convention,XX123,2025-12-01{D},us"],
    "party_activity": [
        f"patent,2026000001,o1,12345678901,applicant,applicant,organisation,"
        f'"placeholder \\"quoted\\" org",VIC,3000,au,2026-01-05{D},,true,true',
        f"patent,2026000001,i2,,applicant,inventor,individual,Placeholder  Person,NSW,2000,au,2026-01-05{D},,true,true",
        f"trade_mark,2026000002,p3,,other,other,,Untyped Party,,1234,nz,2026-02-01{D},2026-03-01{D},false,false",
    ],
}


def make_zip(rows: dict[str, list[str]] | None = None, header_extra: dict[str, str] | None = None) -> bytes:
    rows = rows or ROWS
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for table, columns in SCHEMA.items():
            header = ",".join(columns) + ((header_extra or {}).get(table, ""))
            zf.writestr(f"{table}.csv", "\n".join([header, *rows[table]]) + "\n")
    return buf.getvalue()


def ipr_card() -> SourceCard:
    return card(
        "ip_rapid",
        {"ckan_package_url": "https://cat.test/api/3/action/package_show?id=x", "memory_limit": "512MB", "threads": 1},
        id="ip_rapid",
        family="patent",
        cadence="weekly",
        expected_volume={"min_per_run": 1, "max_per_run": 100},
    )


def catalogue(size: int, modified: str = "2026-10-12T00:33:45.663334"):
    resource = {"name": "IPRAPID.zip", "url": "https://files.test/iprapid.zip", "size": size, "last_modified": modified}
    return {"result": {"resources": [{"name": "dictionary.pdf"}, resource]}}


def client_for(http_cfg, zip_bytes: bytes, modified: str = "2026-10-12T00:33:45.663334", size: int | None = None):
    def handler(request):
        if request.url.host == "cat.test":
            return httpx.Response(200, json=catalogue(len(zip_bytes) if size is None else size, modified))
        return httpx.Response(200, content=zip_bytes)

    return make_client(http_cfg, handler)


def write(tmp_path, data: bytes, name: str = "release.zip"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def table(store, key: str) -> list[dict]:
    path = store.root / key
    con = duckdb.connect()
    cur = con.execute(f"SELECT * FROM read_parquet('{path}')")
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


def person_hash(name: str) -> str:
    normalised = " ".join(name.split()).lower()
    return "sha256:" + hashlib.sha256(f"{PERSON_HASH_LABEL}|{normalised}".encode()).hexdigest()


def test_first_release_is_a_base_with_individuals_names_hashed(http_cfg, store, tmp_path):
    data = make_zip()
    r = refresh(ipr_card(), store, client_for(http_cfg, data), zip_path=write(tmp_path, data))
    assert r.status == "passed", r.error
    assert r.records == sum(len(v) for v in ROWS.values())
    keys = store.list("lake/ip_rapid/")
    assert sorted(keys) == sorted(f"lake/ip_rapid/base=2026-10-12/{t}.parquet" for t in SCHEMA)

    parties = {p["party_id"]: p for p in table(store, "lake/ip_rapid/base=2026-10-12/party_activity.parquet")}
    assert parties["o1"]["party_name"] == 'placeholder "quoted" org' and parties["o1"]["post_code"] == "3000"
    assert parties["i2"]["party_name"] == person_hash("Placeholder  Person") and parties["i2"]["post_code"] is None
    assert parties["p3"]["party_name"] == person_hash("Untyped Party") and parties["p3"]["post_code"] is None
    assert parties["i2"]["state_code"] == "NSW"  # the state is kept; the postcode is not
    everything = json.dumps([table(store, k) for k in keys], default=str)
    assert "Placeholder  Person" not in everything and "Untyped Party" not in everything  # no person's name anywhere

    apps = {a["application_number"]: a for a in table(store, "lake/ip_rapid/base=2026-10-12/application.parquet")}
    assert (
        str(apps["2026000001"]["application_date"]) == "2026-01-05"
        and apps["2026000001"]["deemed_retired_date"] is None
    )
    events = table(store, "lake/ip_rapid/base=2026-10-12/application_events.parquet")
    assert sorted(e["is_standing"] for e in events) == [False, True]

    release = json.loads(store.get("raw/ip_rapid/2026-10-12/manifest.json"))
    assert release["mode"] == "base" and release["zip"]["sha256"] == hashlib.sha256(data).hexdigest()
    assert release["tables"]["party_activity"]["rows"] == 3
    manifest = json.loads(store.get(r.manifest_key))
    assert manifest["status"] == "passed" and manifest["counts"]["rows_party_activity"] == 3
    assert store.list("monitors/ingestion/source=ip_rapid/2026-10-12/")
    assert store.list("raw/") == ["raw/ip_rapid/2026-10-12/manifest.json"]  # the zip itself is never stored


def test_the_same_release_twice_does_nothing(http_cfg, store, tmp_path):
    data = make_zip()
    refresh(ipr_card(), store, client_for(http_cfg, data), zip_path=write(tmp_path, data))
    again = refresh(ipr_card(), store, client_for(http_cfg, data), zip_path=write(tmp_path, data))
    assert again.status == "passed" and again.records == 0 and "already ingested" in again.warnings[0]


def test_a_later_release_is_a_delta_against_the_base(http_cfg, store, tmp_path):
    first = make_zip()
    refresh(ipr_card(), store, client_for(http_cfg, first), zip_path=write(tmp_path, first))
    rows = {k: list(v) for k, v in ROWS.items()}
    rows["application"][0] = rows["application"][0].replace(",filed,", ",accepted,")  # a status changed
    rows["application_events"].append(f"2026000001,patent,accepted,accepted,2026-10-15{D},2026-10-15{D},1")
    second = make_zip(rows)
    r = refresh(
        ipr_card(),
        store,
        client_for(http_cfg, second, "2026-10-19T00:30:00"),
        zip_path=write(tmp_path, second, "b.zip"),
    )
    assert r.status == "passed", r.error
    release = json.loads(store.get("raw/ip_rapid/2026-10-19/manifest.json"))
    assert release["mode"] == "delta" and release["base_release"] == "2026-10-12"
    assert release["tables"]["application"]["added"] == 1 and release["tables"]["application"]["removed"] == 1
    assert release["tables"]["application_events"]["added"] == 1
    assert release["tables"]["application_events"]["removed"] == 0
    assert release["tables"]["party_activity"]["added"] == 0 and release["tables"]["party_activity"]["removed"] == 0
    delta = table(store, "lake/ip_rapid/delta=2026-10-19/application.parquet")
    assert sorted((d["_change"], d["status"]) for d in delta) == [("added", "accepted"), ("removed", "filed")]


def test_schema_changes_and_bad_values_fail_loudly(http_cfg, store, tmp_path):
    extra = make_zip(
        {**ROWS, "party_activity": [row + ",x" for row in ROWS["party_activity"]]},
        header_extra={"party_activity": ",name_raw"},
    )
    r = refresh(ipr_card(), store, client_for(http_cfg, extra), zip_path=write(tmp_path, extra))
    assert r.status == "failed" and "party_activity columns changed (unknown ['name_raw']" in r.error
    assert not store.list("lake/")  # nothing reached the lake

    bad = make_zip({**ROWS, "application_links": ["patent,2026000001,convention,XX123,2025-12-3x,us"]})
    r = refresh(ipr_card(), store, client_for(http_cfg, bad), zip_path=write(tmp_path, bad, "bad.zip"))
    assert r.status == "failed" and "application_links could not be converted" in r.error
    assert json.loads(store.get(r.manifest_key))["status"] == "failed"


def test_download_size_check_and_smoke_test(http_cfg, store, tmp_path):
    data = make_zip()
    r = refresh(ipr_card(), store, client_for(http_cfg, data, size=len(data) + 1))
    assert r.status == "failed" and "the catalogue's release 2026-10-12 has" in r.error

    smoke = refresh(ipr_card(), store, client_for(http_cfg, data), limit=2)
    assert smoke.status == "passed" and smoke.records == len(ROWS["application"]) + len(
        ROWS["application_classification"]
    )
    assert not store.list("lake/") and not store.exists("raw/ip_rapid/2026-10-12/manifest.json")

    full = refresh(ipr_card(), store, client_for(http_cfg, data))  # downloaded, not a local file
    assert full.status == "passed", full.error
    assert json.loads(store.get("raw/ip_rapid/2026-10-12/manifest.json"))["zip"]["origin"] == "download"


@pytest.mark.parametrize("name", ["party name", "Party", "party-name"])
def test_column_names_are_checked_before_they_reach_sql(name):
    from moria.collectors.base import CollectError
    from moria.ipr import column_sql

    with pytest.raises(CollectError):
        column_sql("application", name)
