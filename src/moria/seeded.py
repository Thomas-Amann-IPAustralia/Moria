"""`moria eval artefacts --as-of D`: the artefact checks against seeded artefacts (design §11.2: all seeded artefacts
flagged; day 4).

The evidence layer's latest outputs are copied into a temporary local store, synthetic artefacts are planted in the
copy, and day 4's whole chain runs on it (monitor, measures, detect, artefacts). Each seed has a positive control: a
genuine change of the same size, without the artefact, which must also become a candidate but without that flag. So a
seed counts as caught only when the detectors would have reported it and the check is what marked it.

Seeds, each with the flag it must get and its control:
- volume spike (series): a research scope whose total jumps 60% while one topic's share rises (coverage); control:
  the same topic in a scope whose total is flat;
- volume spike (documents): a policy source publishing 8 times more in the window, 3 of its items with a new phrase
  (coverage); control: a new phrase in steady sources;
- duplicated syndication: a new phrase in 4 stories, each syndicated 4 times (duplicate); control: 4 distinct stories;
- source onboarding: a feed onboarded 2 days ago with 60 days of backfill, 3 of its items with a new phrase
  (source_break); control: a new phrase in sources whose history covers the baseline;
- ingestion failure: a failed collection in the window of a source holding a new phrase (ingestion); control:
  sources without incidents;
- news cycle: a news query group bursting from a low base with no primary source (news_cycle); control: the same
  burst with a policy item on the group.

Seeds live in synthetic sources and scopes (`seed_*`, scope `zz`), so the real data stay as they are; they share the
real families, so the tests run among the real volumes and Holm families. The copy is deleted afterwards. Writes
`manifests/eval.artefacts/<run_id>.json` in the real store, with each seed's outcome, and returns the outcomes for
`reports/eval/artefacts.md`. Everything planted is placeholder text.
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .artefacts import COMMAND as ART
from .artefacts import artefacts
from .concepts import COMMAND as DOCS
from .concepts import measure as measure_docs
from .config import DetectConfig, FeaturesConfig, SourceCard
from .detect import COMMAND as DET
from .detect import candidate_id, detect
from .embed import to_blob
from .features import DEDUP, EMBED, EMBEDDINGS, GROUPS, KEYPHRASE_ROWS, KEYPHRASES, VOCABULARY
from .iprmetrics import COMMAND as IPRM
from .manifest import Manifest
from .measures import COMMAND as SER
from .measures import as_of_end
from .measures import measure as measure_ser
from .monitor import COMMAND as MON
from .monitor import monitor
from .normalise import COMMAND as NORMALISE
from .records import canonical_json, sha256_hex
from .store import LocalStore, Store
from .tables import DOCUMENTS, OBSERVATIONS, SERIES, cache_root, fetch_outputs, latest_manifest, read_rows, upstream
from .tags import COMMAND as TAG
from .text import period_start

log = logging.getLogger("moria.seeded")

COMMAND = "eval.artefacts"
SEEDS = [  # name, the flag expected, the seed's subject, its control's subject
    ("volume_spike_series", "coverage", "openalex_counts|topic|SEED1|zz|month", "openalex_counts|topic|SEED1|zy|month"),
    ("volume_spike_documents", "coverage", "kp:seedphrase spike", "kp:seedphrase covered"),
    ("duplicated_syndication", "duplicate", "kp:seedphrase syndicated", "kp:seedphrase distinct"),
    ("source_onboarding", "source_break", "kp:seedphrase onboarded", "kp:seedphrase covered"),
    ("ingestion_failure", "ingestion", "kp:seedphrase incident", "kp:seedphrase distinct"),
    ("news_cycle", "news_cycle", "gdelt_news|seedburst|zz|about_documents", "gdelt_news|seedcited|zz|about_documents"),
]
COMMON = [f"seed common {c}" for c in "abcdefghij"]
SEED_SOURCES = {"seed_policy_a": 1, "seed_policy_b": 1, "seed_policy_c": 1, "seed_policy_spike": 4}  # days per item


def seed_card(source: str) -> SourceCard:
    return SourceCard.model_validate({
        "id": source, "name": f"Seeded source {source}", "adapter": "feed", "rings": ["adjacent"], "domains": ["D3"],
        "family": "policy", "cadence": "weekly", "publication_lag": "none", "coverage": "synthetic",
        "history_start": None, "stable_since": None, "known_biases": [], "revision_policy": "none",
        "licence": "synthetic", "snapshot_rights": "synthetic",
        "expected_volume": {"min_per_run": 0, "max_per_run": 10**6},
    })  # fmt: skip


# --------------------------------------------------------------------------------------------- copying the layer


def _copy_stage(real: Store, tmp: LocalStore, command: str, prefix: str) -> dict[str, Path]:
    """The latest passed run's outputs, copied to the temporary store; returns key -> local path in the copy."""
    m = upstream(real, command)
    files = fetch_outputs(real, m, prefix, cache_root())
    out = {}
    for key, path in files.items():
        tmp.put_file(key, path)
        out[key] = tmp.root / key
    return out


def _finish(tmp: LocalStore, command: str, params: dict) -> str:
    """A passed manifest in the copy over every file now under the command's prefixes."""
    m = Manifest(command=command)
    m.params = params
    prefixes = {NORMALISE: ("lake/documents/", "lake/series/", "lake/observations/"), EMBED: ("features/embeddings/",),
                DEDUP: ("features/dedup/",), KEYPHRASES: ("features/keyphrases/",), TAG: ("features/tags/",),
                IPRM: ("lake/ipr_metrics/",)}[command]  # fmt: skip
    from .lake import file_sha256

    for pre in prefixes:
        for key in tmp.list(pre):
            path = tmp.root / key
            m.add_output_file(key, file_sha256(path), path.stat().st_size)
    m.finish(tmp, "passed")
    return m.run_id


def _append(path: Path, rows: list[dict], schema: pa.Schema | None = None) -> None:
    old = pq.read_table(path)
    new = pa.Table.from_pylist(rows, schema=schema or old.schema)
    pq.write_table(pa.concat_tables([old, new.select(old.schema.names).cast(old.schema)]), path, compression="zstd")


def _write(path: Path, rows: list[dict], schema: pa.Schema) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, compression="zstd")


# ----------------------------------------------------------------------------------------------------- the seeds


class Planter:
    """Synthetic items: documents, their groups, keyphrases, vectors and tags."""

    def __init__(self, as_of: date, cfg: DetectConfig, dim: int, tagger: str, seed: int = 20261014):
        self.end = as_of_end(as_of)
        self.w_start = self.end - timedelta(days=cfg.documents.window_days)
        self.b_start = self.w_start - timedelta(days=cfg.documents.baseline_days)
        self.rng = np.random.default_rng(seed)
        self.dim, self.tagger = dim, tagger
        self.centre = self._unit(self.rng.normal(size=dim))
        self.docs: dict[str, list[dict]] = {}
        self.groups, self.kp, self.vec, self.tags = [], {}, {}, []
        self.first: dict[str, tuple[datetime, str]] = {}
        self.df: dict[str, set] = {}
        self.n = 0

    def _unit(self, v):
        return v / np.linalg.norm(v)

    def item(self, source: str, family: str, at: datetime, phrases: list[str], first_seen: datetime | None = None,
             group: str | None = None, term_groups: list[str] | None = None) -> str:  # fmt: skip
        self.n += 1
        iid = sha256_hex(f"seed|{source}|{self.n}")
        seen = first_seen or at
        self.docs.setdefault(source, []).append({
            "item_id": iid, "source": source, "evidence_id": iid, "n_versions": 1, "provider": "seed",
            "source_collection": source, "provider_record_id": str(self.n), "doc_type": "item", "family": family,
            "rings": ["adjacent"], "domains": ["D3"], "licence": "synthetic", "title": f"Placeholder {self.n}",
            "summary": "", "text": "", "text_chars": 0, "text_stored": False, "url": None, "url_canonical": None,
            "outlet": source, "country": None, "event_at": at, "observable_at": at, "observable_basis": "source",
            "first_seen_at": seen, "retrieved_at": seen, "raw_object_uri": "seed", "parser_version": "seed",
            "extra": "{}", "sweep_codes": [], "title_key": None,
        })  # fmt: skip
        self.groups.append({"item_id": iid, "source": source, "dedup_group": group or iid, "group_size": 1,
                            "rule": "self" if not group else "title", "max_cosine": 0.0})  # fmt: skip
        self.kp.setdefault(source, []).extend(
            {"item_id": iid, "phrase": p, "score": 1.0, "rank": k + 1} for k, p in enumerate(phrases))  # fmt: skip
        for p in phrases:
            if p not in self.first or at < self.first[p][0]:
                self.first[p] = (at, iid)
            self.df.setdefault(p, set()).add((iid, source, family))
        noise = self._unit(self.rng.normal(size=self.dim))
        self.vec.setdefault(source, []).append((iid, self._unit(self.centre + 0.3 * noise)))
        self.tags.append({"item_id": iid, "tagger": self.tagger, "term_groups": term_groups or [],
                          "term_territories": [], "term_phrases": 0, "ring_top": "adjacent",
                          "ring_p_adjacent": 1.0, "ring_p_core": 0.0, "ring_p_wider_world": 0.0,
                          "_source": source})  # fmt: skip
        return iid

    def background(self) -> None:
        """Steady sources over the baseline and the window; the spike source publishes 8 times more in the window."""
        for source, every in SEED_SOURCES.items():
            at = self.b_start - timedelta(days=20)  # their history covers the whole baseline
            while at < self.end - timedelta(days=1):
                step = 0.5 if source == "seed_policy_spike" and at > self.w_start else every
                self.item(source, "policy", at, list(self.rng.choice(COMMON, 3, replace=False)))
                at += timedelta(days=step)

    def seeds(self) -> None:
        day = lambda k: self.end - timedelta(days=k, hours=12)  # noqa: E731
        com = COMMON[:2]
        for k, s in enumerate(("seed_policy_a", "seed_policy_a", "seed_policy_b", "seed_policy_b")):
            self.item(s, "policy", day(20 + k), ["seedphrase distinct", *com])
            self.item(s, "policy", day(30 + k), ["seedphrase covered", *com])
            first = self.item(s, "policy", day(40 + k), ["seedphrase syndicated", *com])
            for _ in range(3):  # syndicated copies of the same story, in the same de-duplication group
                self.item(s, "policy", day(40 + k), ["seedphrase syndicated", *com], group=first)
        for k, s in enumerate(("seed_policy_spike",) * 3 + ("seed_policy_a",)):
            self.item(s, "policy", day(10 + k), ["seedphrase spike", *com])
        for k, s in enumerate(("seed_policy_c", "seed_policy_c", "seed_policy_a", "seed_policy_a")):
            self.item(s, "policy", day(50 + k), ["seedphrase incident", *com])
        onboarded = self.end - timedelta(days=2)
        for k in range(20):  # a feed onboarded two days ago, with 60 days of backfill
            phrases = ["seedphrase onboarded", *com] if k < 3 else list(self.rng.choice(COMMON, 3, replace=False))
            self.item("seed_new_feed", "policy", day(5 + 3 * k), phrases, first_seen=onboarded)
        self.item("seed_policy_a", "policy", day(15), ["seedphrase onboarded", *com])
        self.item("seed_policy_b", "policy", day(3), list(com), term_groups=["seedcited"])  # a primary source

    def vocabulary(self) -> list[dict]:
        out = []
        for p, (at, iid) in sorted(self.first.items()):
            hits = self.df[p]
            first_at = self.b_start - timedelta(days=30) if p in COMMON else at
            out.append({"phrase": p, "words": len(p.split()), "df": len(hits),
                        "n_sources": len({s for _, s, _ in hits}), "sources": sorted({s for _, s, _ in hits}),
                        "families": sorted({f for _, _, f in hits}), "first_observable_at": first_at,
                        "first_item_id": iid})  # fmt: skip
        return out


def seeded_series(as_of: date) -> tuple[list[dict], list[dict]]:
    """OpenAlex scopes zz (total jumps 60% in the last 12 months) and zy (flat), with a rising topic in each; GDELT
    scope zz with two query groups bursting from a low base in the last 7 days."""
    rng = np.random.default_rng(7)
    vintage = datetime(as_of.year, as_of.month, as_of.day, tzinfo=UTC) - timedelta(days=1)
    series, obs = [], []

    def add(sid, source, label, scope, family, freq, values):
        series.append({"series_id": sid, "source": source, "provider": "seed", "source_collection": source,
                       "label": label, "measure": "seed", "unit": "count", "frequency": freq, "scope": scope,
                       "dimensions": "{}", "family": family, "rings": ["adjacent"], "domains": ["D3"],
                       "licence": "synthetic", "n_obs": len(values), "first_period": min(values),
                       "last_period": max(values), "n_vintages": 1, "first_seen_at": vintage,
                       "latest_vintage_at": vintage, "raw_object_uri": "seed"})  # fmt: skip
        for period, v in sorted(values.items()):
            kind, start = period_start(period)
            obs.append({"series_id": sid, "source": source, "period": period, "period_kind": kind,
                        "period_start": start, "value": float(v), "value_text": None, "status": None,
                        "vintage_at": vintage})  # fmt: skip

    last = date(as_of.year, as_of.month, 1)
    months = []
    y, m = last.year, last.month
    for _ in range(36):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    months = months[::-1]
    for scope, jump in (("zz", 1.6), ("zy", 1.0)):
        total = {p: 20000.0 * (jump if i >= len(months) - 13 else 1.0) for i, p in enumerate(months)}
        add(f"openalex_counts|total|{scope}|month", "openalex_counts", "Seeded total", scope, "research", "M", total)
        topic = {p: float(rng.poisson(total[p] * 0.01 * np.exp(0.04 * i))) for i, p in enumerate(months)}
        add(f"openalex_counts|topic|SEED1|{scope}|month", "openalex_counts", "Seeded topic", scope, "research", "M",
            topic)  # fmt: skip
    days = [(as_of - timedelta(days=k)).isoformat() for k in range(120, -1, -1)]
    add("gdelt_news|total|zz", "gdelt_news", "Seeded total", "zz", "news", "D", {d: 10000.0 for d in days})
    for group in ("seedburst", "seedcited"):
        vals = {d: float(rng.poisson(0.05 if k < len(days) - 8 else 4.0)) for k, d in enumerate(days)}
        add(f"gdelt_news|{group}|zz|about_documents", "gdelt_news", group, "zz", "news", "D", vals)
    return series, obs


# ----------------------------------------------------------------------------------------------------------- run


def build_copy(real: Store, tmp: LocalStore, cfg: DetectConfig, features: FeaturesConfig, as_of: date) -> list[str]:
    """Copy the layer, plant the seeds, write the copy's manifests; returns the seed sources."""
    _copy_stage(real, tmp, NORMALISE, "lake/")
    stages = (
        (EMBED, "features/embeddings/"),
        (DEDUP, "features/dedup/"),
        (KEYPHRASES, "features/keyphrases/"),
        (TAG, "features/tags/"),
        (IPRM, "lake/ipr_metrics/"),
    )
    for command, prefix in stages:
        _copy_stage(real, tmp, command, prefix)
    for key in real.list("monitors/ingestion/source=") + real.list("manifests/collect."):
        if key.endswith(".json"):
            tmp.put(key, real.get(key))
    tags_paths = sorted((tmp.root / "features/tags").glob("source=*/tags.parquet"))
    tag_schema = pq.read_schema(tags_paths[0])
    taggers = {t for path in tags_paths for t in pq.read_table(path, columns=["tagger"]).column(0).to_pylist()}
    if len(taggers) != 1:
        raise ValueError(f"the copy's tags carry {len(taggers)} tagger versions; the seeds need one")
    (tagger,) = taggers  # a source with no items has an empty tags file
    p = Planter(as_of, cfg, features.embed.dim, tagger)
    p.background()
    p.seeds()
    for source, rows in p.docs.items():
        _write(tmp.root / f"lake/documents/source={source}/documents.parquet", rows, DOCUMENTS)
        _write(tmp.root / f"features/keyphrases/source={source}/keyphrases.parquet", p.kp.get(source, []),
               KEYPHRASE_ROWS)  # fmt: skip
        ids, vecs = zip(*p.vec[source], strict=True)
        _write(tmp.root / f"features/embeddings/source={source}/embeddings.parquet",
               [{"item_id": i, "text_sha256": i, "vector": b} for i, b in zip(ids, to_blob(np.vstack(vecs)),
                                                                              strict=True)], EMBEDDINGS)  # fmt: skip
        trows = [{k: v for k, v in t.items() if k != "_source"} for t in p.tags if t["_source"] == source]
        _write(tmp.root / f"features/tags/source={source}/tags.parquet", trows, tag_schema)
    _append(tmp.root / "features/dedup/groups.parquet", p.groups, GROUPS)
    _append(tmp.root / "features/keyphrases/vocabulary.parquet", p.vocabulary(), VOCABULARY)
    series, obs = seeded_series(as_of)
    for source in ("openalex_counts", "gdelt_news"):
        spath = tmp.root / f"lake/series/source={source}/series.parquet"
        opath = tmp.root / f"lake/observations/source={source}/observations.parquet"
        srows = [s for s in series if s["source"] == source]
        orows = [o for o in obs if o["source"] == source]
        if spath.exists():
            _append(spath, srows, SERIES)
            _append(opath, orows, OBSERVATIONS)
        else:
            _write(spath, srows, SERIES)
            _write(opath, orows, OBSERVATIONS)
    failed = Manifest(command="collect.seed_policy_c")
    failed.params = {"window_start": f"{(as_of - timedelta(days=10)).isoformat()}T00:00:00+00:00"}
    failed.finish(tmp, "failed", "seed_policy_c: seeded failure")
    nrun = _finish(tmp, NORMALISE, {"seeded": True})
    erun = _finish(tmp, EMBED, {"normalise_run": nrun, "model": f"{features.embed.model}@{features.embed.revision}"})
    _finish(tmp, DEDUP, {"normalise_run": nrun, "embed_run": erun})
    _finish(tmp, KEYPHRASES, {"normalise_run": nrun})
    _finish(tmp, TAG, {"normalise_run": nrun, "embed_run": erun, "tagger": tagger})
    _finish(tmp, IPRM, {"seeded": True})
    return sorted({*p.docs})


def outcomes(tmp: LocalStore, as_of: date) -> list[dict]:
    """Each seed's and control's candidate and flags, from the copy's artefact run."""
    am, dm = latest_manifest(tmp, ART), latest_manifest(tmp, DET)
    if not am or am["status"] != "passed" or not dm or dm["status"] != "passed":
        raise RuntimeError("the seeded scan did not pass")
    prefix = tmp.root / f"candidates/as_of={as_of.isoformat()}"
    flags = {r["candidate_id"]: r["flags"] for r in read_rows(prefix / "artefacts.parquet")}
    cands = {r["candidate_id"]: r for r in read_rows(prefix / "candidates.parquet")}
    out = []
    for name, flag, seed, control in SEEDS:
        s, c = candidate_id(seed), candidate_id(control)
        caught = s in cands and flag in flags.get(s, [])
        control_ok = c in cands and flag not in flags.get(c, [])
        out.append({"seed": name, "flag": flag, "seed_detected": s in cands, "seed_flags": flags.get(s, []),
                    "caught": caught, "control_detected": c in cands, "control_flags": flags.get(c, []),
                    "control_ok": control_ok,
                    "seed_detectors": (cands.get(s) or {}).get("detectors", []),
                    "control_detectors": (cands.get(c) or {}).get("detectors", [])})  # fmt: skip
    return out


def evaluate(real: Store, cfg: DetectConfig, features: FeaturesConfig, cards: dict[str, SourceCard], as_of: date,
             config_hash: str | None = None) -> tuple[str, str, dict, list[dict]]:  # fmt: skip
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        with tempfile.TemporaryDirectory(prefix="moria-seeded-") as d:
            tmp = LocalStore(Path(d) / "store")
            seeded = build_copy(real, tmp, cfg, features, as_of)
            all_cards = {**cards, **{s: seed_card(s) for s in seeded}}
            steps = [
                (MON, lambda: monitor(tmp, all_cards, as_of)),
                (SER, lambda: measure_ser(tmp, cfg, as_of)),
                (DOCS, lambda: measure_docs(tmp, cfg, all_cards, features.embed.dim, as_of)),
                (DET, lambda: detect(tmp, cfg, as_of)),
                (ART, lambda: artefacts(tmp, cfg, all_cards, as_of)),
            ]
            runs = {}
            for name, step in steps:
                status, _, counts = step()
                runs[name] = {"status": status, "counts": counts}
                if status != "passed":
                    raise RuntimeError(f"the seeded {name} run failed: {counts.get('error')}")
            result = outcomes(tmp, as_of)
        manifest.params = {"as_of": as_of.isoformat(), "seeds": result, "runs": json.loads(canonical_json(runs))}
        manifest.counts = {"seeds": len(result), "caught": sum(r["caught"] for r in result),
                           "controls_ok": sum(r["control_ok"] for r in result)}  # fmt: skip
        ok = all(r["caught"] and r["control_ok"] for r in result)
        manifest.counts["all_flagged"] = int(ok)
        return "passed", manifest.finish(real, "passed"), manifest.counts, result
    except Exception as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        cause = f"{COMMAND}: {type(e).__name__}: {first[:300]}"
        log.error("%s", cause)
        return "failed", manifest.finish(real, "failed", cause), {"error": cause}, []


def report(result: list[dict], mkey: str, as_of: date) -> str:
    lines = [
        "# Artefact checks against seeded artefacts",
        "",
        f"Generated by `moria eval artefacts --as-of {as_of}` (`{mkey}`); synthetic seeds only, planted on a copy of "
        "the evidence layer (design §11.2: all seeded artefacts flagged).",
        "",
        "A seed is caught when it became a candidate and its check flagged it; its control, a genuine change of the "
        "same size without the artefact, must also become a candidate without that flag.",
        "",
        "| Seed | Check | Seed detected by | Caught | Control detected by | Control without the flag |",
        "|---|---|---|---|---|---|",
    ]
    for r in result:
        lines.append(f"| {r['seed'].replace('_', ' ')} | {r['flag']} | {', '.join(r['seed_detectors']) or '-'} | "
                     f"{'yes' if r['caught'] else 'no'} | {', '.join(r['control_detectors']) or '-'} | "
                     f"{'yes' if r['control_ok'] else 'no'} |")  # fmt: skip
    caught = sum(r["caught"] for r in result)
    controls = sum(r["control_ok"] for r in result)
    lines += ["", f"**{caught} of {len(result)} seeds caught; {controls} of {len(result)} controls clean on their "
              "check.**", ""]  # fmt: skip
    return "\n".join(lines)
