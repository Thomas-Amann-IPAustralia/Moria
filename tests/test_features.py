"""The feature stages on fixture documents (placeholder text) with a stub encoder: embed (and reuse), dedup's three
rules, keyphrases, the zero-shot tags with territory terms, and the BM25 index. The stub is test-only: the CLI
always builds the real, pinned encoder."""

from __future__ import annotations

import json
import zlib

import duckdb
import numpy as np
import pyarrow.parquet as pq
import pytest

from moria import features as F
from moria import tags as T
from moria.config import load_baseline, load_codebook, load_features, load_sources, load_territories
from moria.normalise import run as normalise

from .conftest import card
from .test_normalise import SWEEP, feed_item, put_run, rec

CFG = load_features()


class StubEncoder:
    """Bag of words hashed into the model's dimensions: identical texts give identical vectors."""

    identity = f"{CFG.embed.model}@{CFG.embed.revision}"

    def __init__(self):
        self.calls = 0

    def encode(self, texts):
        self.calls += len(texts)
        out = np.zeros((len(texts), CFG.embed.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in t.lower().split():
                out[i, zlib.crc32(w.encode()) % CFG.embed.dim] += 1.0
            out[i] /= max(np.linalg.norm(out[i]), 1e-9)
        return out


def news(url, title, at, domain):
    return {"au_domain": False, "domain": domain, "gkg_date": at, "has_quotations": False, "location_countries": [],
            "matches": [], "organisations": [], "published_at": None, "query_groups": [], "themes": [],
            "title": title, "tone": {"tone": 0.0, "word_count": 1}, "url": url}  # fmt: skip


def corpus(store):
    gk = card("gdelt_gkg", {}, family="news", id="gdelt_news", rings=["wider_world"])
    fd = card("feed", {}, id="policy_feed")
    t = "2026-10-12T08:00:00+00:00"
    put_run(store, gk, [
        rec(gk, "u1", news("https://a.example.com/s1", "Placeholder council approves new harbour bridge plan", t,
                           "a.example.com"), observable_at=t),
        rec(gk, "u2", news("https://b.example.net/x", "Placeholder council approves new harbour bridge plan", t,
                           "b.example.net"), observable_at=t),
        rec(gk, "u3", news("https://c.example.org/y", "Short title here", t, "c.example.org"), observable_at=t),
        rec(gk, "u4", news("https://d.example.info/z", "Short title here", t, "d.example.info"), observable_at=t),
        rec(gk, "u5", news("http://www.a.example.com/s1/", "Another headline entirely", t, "a.example.com"),
            observable_at=t),
    ], "20261013T040000Z-00000001")  # fmt: skip
    shared = "https://example.gov/committee"
    items = [
        {**feed_item("Inquiry into counterfeit goods opened", "Counterfeit goods and trade mark infringement.",
                     "2026-10-01"), "link": shared},
        {**feed_item("Report on counterfeit goods tabled", "Counterfeit goods report.", "2026-10-02"), "link": shared},
        feed_item("Patent office modernises patent examination", "Patent examination and patent office systems.",
                  "2026-10-03"),
    ]  # fmt: skip
    put_run(store, fd, [rec(fd, it["title"], it, observable_at=it["published"]) for it in items],
            "20261013T040000Z-00000002")  # fmt: skip
    cards = {gk.id: gk, fd.id: fd}
    assert normalise(store, cards, CFG, SWEEP)[0] == "passed"
    return cards


def test_embed_reuses_unchanged_texts(store):
    corpus(store)
    stub = StubEncoder()
    status, _, counts = F.embed(store, CFG, lambda: stub)
    assert status == "passed" and counts["documents"] == 8 and stub.calls == 6  # two pairs of news texts are identical
    rows = pq.read_table(store.root / "features/embeddings/source=policy_feed/embeddings.parquet").to_pylist()
    assert len(rows) == 3 and len(rows[0]["vector"]) == CFG.embed.dim * 2  # float16
    status, _, counts = F.embed(store, CFG, lambda: stub)
    assert status == "passed" and counts["sources_unchanged"] == 2 and stub.calls == 6


def test_dedup_rules(store):
    corpus(store)
    F.embed(store, CFG, StubEncoder)
    status, _, counts = F.dedup(store, CFG)
    assert status == "passed", counts
    groups = pq.read_table(store.root / "features/dedup/groups.parquet").to_pylist()
    docs = {d["item_id"]: d for p in (store.root / "lake/documents").glob("*/documents.parquet")
            for d in pq.read_table(p).to_pylist()}  # fmt: skip
    by_title = {}
    for g in groups:
        by_title.setdefault(docs[g["item_id"]]["provider_record_id"], g)
    assert by_title["u1"]["dedup_group"] == by_title["u2"]["dedup_group"]  # the same 7-word title
    assert counts["joined_title"] == 1  # an item keeps the first rule that joined it, so count the joins
    assert by_title["u3"]["dedup_group"] == by_title["u4"]["dedup_group"]  # too short for the title rule: cosine
    assert "cosine" in {by_title["u3"]["rule"], by_title["u4"]["rule"]}
    assert by_title["u5"]["dedup_group"] == by_title["u1"]["dedup_group"]  # the same canonical URL in news
    inquiry = by_title["Inquiry into counterfeit goods opened"]
    report = by_title["Report on counterfeit goods tabled"]
    assert inquiry["dedup_group"] != report["dedup_group"]  # a shared committee link is not the same item
    assert counts["joined_url"] == 1 and counts["groups"] == 5


def test_dedup_refuses_embeddings_from_an_older_normalise_run(store):
    cards = corpus(store)
    F.embed(store, CFG, StubEncoder)
    fd = cards["policy_feed"]
    put_run(store, fd, [rec(fd, "new", feed_item("New item", "", "2026-10-04"), observable_at="2026-10-04")],
            "20261014T040000Z-00000003")  # fmt: skip
    normalise(store, cards, CFG, SWEEP)
    status, _, counts = F.dedup(store, CFG)
    assert status == "failed" and "run `moria features embed` first" in counts["error"]


def test_keyphrase_candidates_and_tables():
    stop = F._stopwords()
    got = F.candidates("The patent office: new AI patent rules (draft).", 3, stop)
    assert got["patent office"] == 1 and got["ai patent rules"] == 1 and "the" not in got and "office new" not in got
    docs = [F._Doc(f"i{n}", "s1" if n < 2 else "s2", "policy", n, f"Counterfeit goods seizure report {n}. Patent.")
            for n in range(4)]  # fmt: skip
    cfg = CFG.model_copy(update={"keyphrases": CFG.keyphrases.model_copy(update={"min_df": 2, "max_df": 1.0})})
    per_source, vocab, counts = F.keyphrase_tables(docs, cfg)
    v = {r["phrase"]: r for r in vocab}
    assert v["counterfeit goods seizure"]["df"] == 4 and v["counterfeit goods seizure"]["n_sources"] == 2
    assert v["counterfeit goods seizure"]["first_item_id"] == "i0"
    kept = [r["phrase"] for r in per_source["s1"] if r["item_id"] == "i0"]
    assert "counterfeit goods seizure" in kept and "counterfeit goods" not in kept  # held by a longer phrase
    assert counts["documents_with_keyphrases"] == 4


def test_tags_zero_shot_and_territory_terms(store):
    cards = corpus(store)
    cards["gdelt_news"] = load_sources()["gdelt_news"]  # the real query groups: territory terms and themes
    F.embed(store, CFG, StubEncoder)
    status, mkey, counts = T.tag(store, CFG, load_codebook(), load_territories(), load_baseline(), cards, StubEncoder)
    assert status == "passed", counts
    rows = {r["item_id"]: r for p in (store.root / "features/tags").glob("*/tags.parquet")
            for r in pq.read_table(p).to_pylist()}  # fmt: skip
    assert counts["items"] == 8 == len(rows)
    r = next(iter(rows.values()))
    assert r["ring_top"] in {"core", "adjacent", "wider_world"}
    assert abs(r["ring_p_core"] + r["ring_p_adjacent"] + r["ring_p_wider_world"] - 1) < 1e-5
    assert {f"territory_sim_T{i}" for i in range(1, 6)} <= set(r) and r["known_trend_top"].startswith("KT")
    docs = {d["item_id"]: d for d in pq.read_table(store.root / "lake/documents/source=policy_feed/documents.parquet")
            .to_pylist()}  # fmt: skip
    inquiry = next(rows[i] for i, d in docs.items() if d["title"].startswith("Inquiry"))
    assert "T1" in inquiry["term_territories"]  # "counterfeit goods" and "trade mark infringement" are T1 terms
    m = json.loads(store.get(mkey))
    assert m["params"]["tagger"].startswith(CFG.tags.version) and m["params"]["territory_context"] is False


def _fts_installed() -> bool:
    con = duckdb.connect()
    return bool(con.execute("SELECT installed FROM duckdb_extensions() WHERE extension_name = 'fts'").fetchone()[0])


@pytest.mark.skipif(not _fts_installed(), reason="DuckDB's fts extension is not installed (tests make no downloads)")
def test_bm25_index_and_search(store, tmp_path):
    corpus(store)
    _, paths = F.documents_in(store)
    db = tmp_path / "bm25.duckdb"
    assert F.build_index(db, paths, 1000) == 8
    hits = F.search(db, "patent examination")
    assert hits and hits[0][4] == "Patent office modernises patent examination"
    assert F.search(db, "patent examination", source="gdelt_news") == []
