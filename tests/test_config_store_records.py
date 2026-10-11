from __future__ import annotations

import pytest
from pydantic import ValidationError

from moria.collectors import ADAPTERS
from moria.config import MoriaConfig, load_config, load_sources, load_territories, load_themes
from moria.records import RawRecord, decode_bundle, encode_bundle, make_envelope
from moria.store import StoreError


def test_repo_config_files_validate():
    cfg = load_config()
    assert cfg.store.bucket == "moria"
    cards = load_sources()
    assert {"gdelt_news", "legislation_frl", "ipaustralia_site", "wipo_press", "ukipo_news"} <= set(cards)
    for c in cards.values():
        ADAPTERS[c.adapter](c)  # each adapter validates its card's params
    territories = load_territories().territories
    assert [t.id for t in territories] == ["T1", "T2", "T3", "T4", "T5"]
    assert all(t.terms.core and t.terms.adjacent and t.terms.wider_world for t in territories)
    assert load_themes().themes


def test_unknown_config_keys_are_errors():
    raw = load_config().model_dump()
    raw["stray"] = 1
    with pytest.raises(ValidationError):
        MoriaConfig.model_validate(raw)


def test_local_store_atomic_and_raw_immutable(store):
    store.put("raw/x/2026/10/09/run.jsonl.zst", b"a")
    assert store.get("raw/x/2026/10/09/run.jsonl.zst") == b"a"
    with pytest.raises(StoreError):
        store.put("raw/x/2026/10/09/run.jsonl.zst", b"b")
    store.put("monitors/m.json", b"1")
    store.put("monitors/m.json", b"2")  # not immutable
    assert store.list("monitors/") == ["monitors/m.json"]
    with pytest.raises(StoreError):
        store.put("../escape", b"x")


def _env(payload, rid="r1"):
    return make_envelope(
        provider="p",
        source_collection="c",
        provider_record_id=rid,
        kind="document",
        family="news",
        rings=["core"],
        domains=["D1"],
        payload=payload,
        request={"q": 1},
        retrieval_method="test",
        tool_identity="t",
        licence="l",
        parser_version="v",
        event_at=None,
        observable_at=None,
        retrieved_at="2026-10-10T00:00:00+00:00",
    )


def test_evidence_id_is_stable_and_content_sensitive():
    assert _env({"a": 1}).evidence_id == _env({"a": 1}).evidence_id
    assert _env({"a": 1}).evidence_id != _env({"a": 2}).evidence_id


def test_bundle_round_trip_is_deterministic():
    recs = [RawRecord(envelope=_env({"n": i}, f"r{i}"), payload={"n": i}) for i in (3, 1, 2)]
    data = encode_bundle(recs)
    assert data == encode_bundle(list(reversed(recs)))
    back = decode_bundle(data)
    assert sorted(r.payload["n"] for r in back) == [1, 2, 3]
    assert decode_bundle(encode_bundle([])) == []
