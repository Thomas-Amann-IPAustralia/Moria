"""The Open Australian Legal Corpus stage, against a hand-built corpus file (placeholder text, never real documents)."""

from __future__ import annotations

import hashlib
import json

import duckdb
import httpx
import pytest

from moria.corpus import FIELDS, HfCorpusParams, refresh

from .conftest import card, make_client

COMMIT = "0" * 40


def doc(i: int, source: str, kind: str, date: str | None, text: str = "placeholder text") -> dict:
    return {
        "version_id": f"{source}:{i}",
        "type": kind,
        "jurisdiction": "commonwealth",
        "source": source,
        "mime": "text/html",
        "date": date,
        "citation": f"Placeholder citation {i}",
        "url": f"https://example.test/{i}",
        "when_scraped": "2025-03-10T09:00:00+11:00",
        "text": text,
    }


DOCS = [
    doc(1, "federal_register_of_legislation", "primary_legislation", "2020-01-02"),
    doc(2, "federal_court_of_australia", "decision", "2024-05-06", "a placeholder judgment's text"),
    doc(3, "high_court_of_australia", "decision", "2023-07-08"),
    doc(4, "nsw_caselaw", "decision", "2022-01-01"),  # not a default part: never written
    doc(5, "federal_court_of_australia", "decision", None),
]


def corpus_bytes(docs=DOCS) -> bytes:
    return ("\n".join(json.dumps(d) for d in docs) + "\n").encode()


def corpus_card(data: bytes, **params):
    sources = {
        "federal_register_of_legislation": {
            "provider": "FRL",
            "licence": "CC BY 4.0",
            "observable_from": "when_scraped",
        },
        "federal_court_of_australia": {"provider": "FCA", "licence": "FCA terms", "observable_from": "date"},
        "high_court_of_australia": {"provider": "HCA", "licence": "HCA terms", "observable_from": "date"},
    }
    p = {
        "repo": "owner/corpus",
        "revision": COMMIT,
        "sha256": hashlib.sha256(data).hexdigest(),
        "release": "7.1.0",
        "released": "2025-03-10",
        "sources": sources,
        "memory_limit": "512MB",
        "threads": 1,
        "max_object_bytes": 1024 * 1024,
        "base_url": "https://hub.test",
        **params,
    }
    return card("hf_corpus", p, id="oalc", family="legal", cadence="once",
                expected_volume={"min_per_run": 1, "max_per_run": 10})  # fmt: skip


def client_for(http_cfg, data: bytes, seen: list):
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=data)

    return make_client(http_cfg, handler)


def rows(store, key: str) -> list[dict]:
    con = duckdb.connect()
    cur = con.execute(
        f"SELECT * EXCLUDE (when_scraped, observable_at), strftime(observable_at AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M') "
        f"AS observable FROM read_parquet('{store.root / key}')"
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def test_the_corpus_goes_to_the_lake_in_parts_with_observable_dates(http_cfg, store):
    data, seen = corpus_bytes(), []
    r = refresh(corpus_card(data), store, client_for(http_cfg, data, seen))
    assert r.status == "passed", r.error
    assert seen == [f"https://hub.test/datasets/owner/corpus/resolve/{COMMIT}/corpus.jsonl"]  # pinned to the commit
    assert r.records == 4
    lake = sorted(store.list("lake/"))
    assert lake == [
        "lake/oalc/release=7.1.0/federal_court_of_australia.parquet",
        "lake/oalc/release=7.1.0/federal_register_of_legislation.parquet",
        "lake/oalc/release=7.1.0/high_court_of_australia.parquet",
    ]
    fca = {x["version_id"]: x for x in rows(store, lake[0])}
    assert fca["federal_court_of_australia:2"]["observable"] == "2024-05-06T00:00"  # judgments: the decision date
    # a judgment without a date is observable from its scrape: never earlier than Moria could know
    assert fca["federal_court_of_australia:5"]["observable"] == "2025-03-09T22:00"
    assert fca["federal_court_of_australia:5"]["date"] is None
    assert fca["federal_court_of_australia:2"]["licence"] == "FCA terms"
    text = "a placeholder judgment's text"
    assert fca["federal_court_of_australia:2"]["text_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    expected_id = hashlib.sha256(
        f"FCA|federal_court_of_australia:2|{hashlib.sha256(text.encode()).hexdigest()}".encode()
    )
    assert fca["federal_court_of_australia:2"]["evidence_id"] == expected_id.hexdigest()
    [frl] = rows(store, lake[1])
    assert frl["observable"] == "2025-03-09T22:00" and str(frl["event_at"]) == "2020-01-02"  # legislation: when scraped

    release = json.loads(store.get("raw/oalc/7.1.0/manifest.json"))
    assert release["revision"] == COMMIT and release["file"]["sha256"] == hashlib.sha256(data).hexdigest()
    assert release["tables"]["federal_court_of_australia"]["rows"] == 2
    assert release["tables"]["federal_court_of_australia"]["no_date"] == 1
    assert release["tables"]["high_court_of_australia"]["types"] == {"decision": 1}
    manifest = json.loads(store.get(r.manifest_key))
    assert manifest["status"] == "passed" and manifest["counts"]["rows_federal_court_of_australia"] == 2
    assert "nsw_caselaw" not in json.dumps(release["tables"])
    assert store.list("raw/") == ["raw/oalc/7.1.0/manifest.json"]  # the file itself is never stored

    again = refresh(corpus_card(data), store, client_for(http_cfg, data, []))
    assert again.status == "passed" and again.records == 0 and "already ingested" in again.warnings[0]


def test_a_file_that_does_not_match_the_pinned_hash_fails(http_cfg, store):
    data = corpus_bytes()
    r = refresh(corpus_card(data, sha256="f" * 64), store, client_for(http_cfg, data, []))
    assert r.status == "failed" and "SHA-256" in r.error
    assert store.list("lake/") == []
    assert json.loads(store.get(r.manifest_key))["status"] == "failed"


def test_changed_fields_fail_the_run(http_cfg, store):
    docs = [{**d, "extra": 1} for d in DOCS]
    data = corpus_bytes(docs)
    r = refresh(corpus_card(data), store, client_for(http_cfg, data, []))
    assert r.status == "failed" and "fields changed (unknown ['extra']" in r.error


def test_a_branch_is_never_a_revision():
    params = corpus_card(b"x").params
    with pytest.raises(ValueError, match="commit hash"):
        HfCorpusParams.model_validate({**params, "revision": "main"})
    assert len(FIELDS) == 10


def test_census_of_the_corpus_shows_counts_only(http_cfg, store):
    from moria.census import census_markdown

    data = corpus_bytes()
    c = corpus_card(data)
    assert refresh(c, store, client_for(http_cfg, data, [])).status == "passed"
    text = census_markdown(store, c)
    assert "| federal_court_of_australia | 2 | 1 | 0 |" in text and "| 2024 | 1 |" in text
    assert "Placeholder citation" not in text and "placeholder" not in text and "example.test" not in text
