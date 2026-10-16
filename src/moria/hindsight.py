"""`moria eval hindsight`: the term-only hindsight smoke run (design §11.1, §11.3; day 5).

Each development in `config/hindsight.yaml` is scanned at its dates, as the scan would have run then, with the
leakage rules of §11.3:
1. **Observable dates only:** series take each period's latest vintage observable by the date (else the earliest:
   backfilled history has no true first sighting); documents are visible when observable by the date and seen by
   Moria by then, or observable before their source's onboarding.
2. **Fit at the date:** the keyphrase vocabulary (and each phrase's first observable date) is fitted again at each
   date on the documents visible then; de-duplication uses its URL and title rules (which only join items within 30
   days of each other, so a later item never renames an earlier group).
3. **Term-only:** no pretrained model. No embeddings, clusters, micro-clusters or zero-shot tags; the territory and
   theme terms are matched in each item's text (deterministic); OpenAlex is left out (its topics come from a model
   trained in 2024) and so is GDELT (collected from October 2026). Rings come from the cards and maps, never from
   the zero-shot ring; there are no artefact checks (no collection history exists at past dates).
4. The developments are defined from contemporaneous evidence by analysts blind to Moria's output: **the set in the
   repo is Claude's draft (proposed)**, so this is a smoke run of the machinery, not the sprint's hindsight result.

At each date the candidates are ranked term-only and a queue of the configured size is chosen under the quotas. A
development is raised at a date when a candidate matches it (a series, a class pair or a term in a document
candidate's label, in its direction, through a detector of change: `match_detectors`); it is recovered when first
raised by its mainstream month; its lead is the months from the first date it was raised to the mainstream month. A
miss is classified: a ranking cut-off when it was raised but never queued, else a detector or source gap.

Writes the manifest (`manifests/eval.hindsight/`) with every number, and `reports/eval/hindsight.md` (aggregates:
development ids and names from the config, counts, detector types and leads; no labels, titles or keyphrases).
"""

from __future__ import annotations

import json
import logging
import re
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pyarrow as pa

from . import concepts, detect, measures
from .config import DetectConfig, FeaturesConfig, HindsightFile, ReviewConfig, SourceCard
from .context import CONTEXT
from .features import KEYPHRASE_ROWS, VOCABULARY, _Doc, dedup_groups, embed_text, keyphrase_tables
from .horizons import HORIZONS
from .manifest import Manifest
from .measures import as_of_end
from .rank import VIEWS, failed, score_candidates, select
from .store import Store
from .tables import STRS, cache_root, fetch_outputs, read_rows, upstream, write_rows

log = logging.getLogger("moria.hindsight")

COMMAND = "eval.hindsight"
TAGS = pa.schema([("item_id", pa.string()), ("tagger", pa.string()), ("term_groups", STRS),
                  ("ring_p_core", pa.float32()), ("ring_p_adjacent", pa.float32()),
                  ("ring_p_wider_world", pa.float32())])  # fmt: skip
GROUPS = pa.schema([("item_id", pa.string()), ("source", pa.string()), ("dedup_group", pa.string()),
                    ("group_size", pa.int32()), ("rule", pa.string()), ("max_cosine", pa.float32())])  # fmt: skip


def months(label: str) -> int:
    return int(label[:4]) * 12 + int(label[5:7]) - 1


class TermLayer:
    """The evidence layer, read once: documents, their term groups, term-only de-duplication groups, series files,
    IP RAPID's class tables and the series' labels."""

    def __init__(self, store: Store, cfg: DetectConfig, features: FeaturesConfig, tmp: Path):
        nm = upstream(store, "normalise")
        docs = fetch_outputs(store, nm, "lake/documents/", cache_root())
        self.docs = {k.split("/source=")[1].split("/")[0]: p for k, p in docs.items()}
        self.runs = {"normalise_run": nm["run_id"]}
        tm = upstream(store, "tag")
        self.runs["tags_run"] = tm["run_id"]
        terms = {}
        for p in fetch_outputs(store, tm, "features/tags/", cache_root()).values():
            for r in read_rows(p, ["item_id", "term_groups"]):
                terms[r["item_id"]] = r["term_groups"]
        rows, self.texts = [], {}
        for _, p in sorted(self.docs.items()):
            cols = [
                "item_id",
                "source",
                "family",
                "outlet",
                "observable_at",
                "observable_basis",
                "first_seen_at",
                "url_canonical",
                "title_key",
                "title",
                "summary",
                "text",
            ]
            for r in read_rows(p, cols):
                rows.append(r)
                self.texts[r["item_id"]] = embed_text(r.pop("title"), r.pop("summary"), r.pop("text"),
                                                      features.keyphrases.text_chars)  # fmt: skip
        self.rows = rows
        keys = ("item_id", "source", "family", "outlet", "observable_at", "url_canonical", "title_key")
        groups, _ = dedup_groups([{k: r[k] for k in keys} for r in rows], {}, features)
        self.groups_path = tmp / "dedup" / "groups.parquet"
        write_rows(groups, GROUPS, self.groups_path, ("item_id",))
        self.tags_files = {}
        by_source: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_source[r["source"]].append({"item_id": r["item_id"], "tagger": "term-only",
                                           "term_groups": terms.get(r["item_id"]) or []})  # fmt: skip
        for source, trs in by_source.items():
            path = tmp / "tags" / f"source={source}" / "tags.parquet"
            write_rows(trs, TAGS, path, ("item_id",))
            self.tags_files[f"features/tags/source={source}/tags.parquet"] = path
        im = upstream(store, "ipr.metrics")
        self.runs["ipr_metrics_run"] = im["run_id"]
        self.ipr = {**fetch_outputs(store, im, "lake/ipr_metrics/class_", cache_root()),
                    **fetch_outputs(store, im, "lake/ipr_metrics/country_", cache_root())}  # fmt: skip
        _, self.pairs = measures.inputs(store, cfg)
        self.meta = {}
        for sp, _ in self.pairs:
            for r in read_rows(sp, ["series_id", "source", "label", "dimensions", "scope"]):
                try:
                    dims = json.loads(r["dimensions"] or "{}")
                except ValueError:
                    dims = {}
                self.meta[r["series_id"]] = {"source": r["source"], "label": r["label"], "dims": dims}
        onboard: dict[str, object] = {}
        for r in rows:
            if r["source"] not in onboard or r["first_seen_at"] < onboard[r["source"]]:
                onboard[r["source"]] = r["first_seen_at"]
        self.onboarded = onboard

    def visible(self, day: date) -> list[dict]:
        """Documents a scan at `day` could see, dated (not a source's undated first collection)."""
        end = as_of_end(day)
        out = []
        for r in self.rows:
            at, first, on = r["observable_at"], r["first_seen_at"], self.onboarded[r["source"]]
            if r["observable_basis"] == "first_sight" and first.date() == on.date():
                continue
            if at <= end and (first <= end or at < on):
                out.append(r)
        return out


def scan_at(layer: TermLayer, cfg: DetectConfig, features: FeaturesConfig, review: ReviewConfig,
            cards: dict[str, SourceCard], day: date, matcher) -> tuple[list[dict], dict]:  # fmt: skip
    """The term-only scan at `day`: its candidates, ranked, with the queue's picks marked."""
    with tempfile.TemporaryDirectory(prefix="moria-hindsight-") as tmp:
        tmp = Path(tmp)
        series = measures.load_series(layer.pairs, cfg, day)
        rows, div, _, hrows, crows, red = measures._run(series, cfg, day)
        sp = {}
        for name, data, schema, sort in (("measures", rows, measures.MEASURES, ("series_id",)),
                                         ("divergence", div, measures.DIVERGENCE, ("pair_id",)),
                                         ("horizons", hrows, HORIZONS, ("series_id", "horizon_months")),
                                         ("context", crows, CONTEXT, ("series_id",)),
                                         ("redundancy", red, measures.REDUNDANCY, ("series_id",))):  # fmt: skip
            sp[f"{name}.parquet"] = tmp / "series" / f"{name}.parquet"
            write_rows(data, schema, sp[f"{name}.parquet"], sort)
        visible = layer.visible(day)
        docs = [_Doc(r["item_id"], r["source"], r["family"], r["observable_at"], layer.texts[r["item_id"]])
                for r in visible]  # fmt: skip
        per_source, vocab, _ = keyphrase_tables(docs, features)
        kp = {}
        for source in sorted({r["source"] for r in visible}):
            path = tmp / "kp" / f"source={source}" / "keyphrases.parquet"
            write_rows(per_source.get(source, []), KEYPHRASE_ROWS, path, ("item_id", "rank"))
            kp[f"features/keyphrases/source={source}/keyphrases.parquet"] = path
        vpath = tmp / "kp" / "vocabulary.parquet"
        write_rows(vocab, VOCABULARY, vpath, ("phrase",))
        kp["features/keyphrases/vocabulary.parquet"] = vpath
        files = {"documents": layer.docs, "dedup": {"features/dedup/groups.parquet": layer.groups_path},
                 "tags": layer.tags_files, "kp": kp, "emb": None, "ipr": layer.ipr}  # fmt: skip
        tables, _ = concepts.build(files, cards, cfg, features.embed.dim, day)
        dp = {}
        for name, (trows, schema, sort) in tables.items():
            dp[f"{name}.parquet"] = tmp / "docs" / f"{name}.parquet"
            write_rows(trows, schema, dp[f"{name}.parquet"], sort)
        cands, evidence, _ = detect.build(sp, dp, cfg, day)
    ranked = score_candidates(cands, evidence, {}, layer.meta, {}, None, matcher, cards, review, day)
    picks = select(ranked, review.queue.size, review.queue, {v: f"score_{v}" for v in VIEWS})
    queued = {p["candidate_id"]: p["rank"] for p in picks}
    for c in cands:
        c["queue_rank"] = queued.get(c["candidate_id"])
    counts = {"series": len(rows), "documents_visible": len(visible), "vocabulary": len(vocab),
              "candidates": len(cands), "queued": len(picks)}  # fmt: skip
    return cands, counts


def matches(dev, c: dict, detectors: list[str] | None = None) -> bool:
    if detectors and not set(c["detectors"]) & set(detectors):
        return False
    if c["subject_kind"] == "series" and any(re.search(p, c["subject"]) for p in dev.series):
        return (c["direction"] or 1) == dev.direction
    if c["subject_kind"] == "combination" and any(re.search(p, c["subject"]) for p in dev.combinations):
        return (c["direction"] or 1) == dev.direction
    if c["subject_kind"] in ("concept", "combination", "micro") and dev.terms:
        label = (c["label"] or "").lower()
        return any(re.search(rf"\b{re.escape(t.lower())}\b", label) for t in dev.terms)
    return False


def evaluate(store: Store, cfg: DetectConfig, features: FeaturesConfig, review: ReviewConfig,
             hindsight: HindsightFile, cards: dict[str, SourceCard], only: list[str] | None = None,
             config_hash: str | None = None) -> tuple[str, str, dict, dict | None]:  # fmt: skip
    from .tags import term_matcher

    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        tcfg = cfg.model_copy(update={"series": cfg.series.model_copy(update={"sources": [
            s for s in cfg.series.sources if s not in hindsight.exclude_sources]})})  # fmt: skip
        devs = [d for d in hindsight.developments if not only or d.id in only]
        with tempfile.TemporaryDirectory(prefix="moria-hindsight-layer-") as tmp:
            layer = TermLayer(store, tcfg, features, Path(tmp))
            manifest.params = {**layer.runs, "variant": hindsight.variant, "status": hindsight.status,
                               "exclude_sources": hindsight.exclude_sources,
                               "developments": [d.id for d in devs]}  # fmt: skip
            matcher = term_matcher(cards)
            scans: dict[str, dict] = {}
            for day_s in sorted({d for dev in devs for d in dev.dates}):
                t0 = time.time()
                cands, counts = scan_at(layer, tcfg, features, review, cards, date.fromisoformat(day_s), matcher)
                counts["seconds"] = round(time.time() - t0)
                scans[day_s] = {"counts": counts, "cands": cands}
                log.info("hindsight %s: %d candidates in %ds", day_s, counts["candidates"], counts["seconds"])
        result = {"status": hindsight.status, "developments": [], "scans": {d: s["counts"] for d, s in
                                                                            scans.items()}}  # fmt: skip
        for dev in devs:
            per_date = []
            for day_s in sorted(dev.dates):
                hit = [c for c in scans[day_s]["cands"] if matches(dev, c, hindsight.match_detectors)]
                per_date.append({"as_of": day_s, "matched": len(hit),
                                 "types": dict(sorted(Counter(c["type"] for c in hit).items())),
                                 "detectors": dict(sorted(Counter(d for c in hit for d in c["detectors"]).items())),
                                 "queued": sum(1 for c in hit if c["queue_rank"]),
                                 "best_queue_rank": min((c["queue_rank"] for c in hit if c["queue_rank"]),
                                                        default=None)})  # fmt: skip
            raised = [p["as_of"] for p in per_date if p["matched"]]
            first = raised[0] if raised else None
            lead = months(dev.mainstream) - months(first) if first else None
            queued = any(p["queued"] for p in per_date)
            miss = None if first else "detector_or_source_gap"
            if first and not queued:
                miss = "ranking_cut_off"
            result["developments"].append({"id": dev.id, "name": dev.name, "mainstream": dev.mainstream,
                                           "first_raised": first, "lead_months": lead,
                                           "recovered": bool(first and months(first) <= months(dev.mainstream)),
                                           "queued": queued, "miss": miss, "dates": per_date})  # fmt: skip
        recs = [d for d in result["developments"] if d["recovered"]]
        leads = [d["lead_months"] for d in recs if d["lead_months"] is not None]
        result["recovery"] = round(len(recs) / len(devs), 3) if devs else None
        result["median_lead_months"] = statistics.median(leads) if leads else None
        result["queued_share"] = (
            round(sum(d["queued"] for d in result["developments"]) / len(devs), 3) if devs else None
        )
        manifest.params["result"] = result
        manifest.counts = {"developments": len(devs), "recovered": len(recs), "scans": len(scans)}
        return "passed", manifest.finish(store, "passed"), manifest.counts, result
    except Exception as e:
        status, mkey, counts = failed(COMMAND, store, manifest, e)
        return status, mkey, counts, None


def report(result: dict, mkey: str) -> str:
    r = result
    lines = [
        "# Hindsight smoke run (term-only)", "",
        f"Run `{mkey.rsplit('/', 1)[1].removesuffix('.json')}`. Generated by `moria eval hindsight`; aggregates only.",
        "", f"**The hindsight set is {r['status']}:** Claude's draft from design §11.3, not a set chosen blind to "
        "Moria's output, and with no non-events yet. This run exercises the term-only machinery at past dates "
        "(D-029); it is not the sprint's hindsight result.", "",
        "## Headline", "",
        f"- Recovered by the mainstream month: {sum(d['recovered'] for d in r['developments'])} of "
        f"{len(r['developments'])} (rule, design §11.1: at least 50%).",
        f"- Median lead time of those recovered: {r['median_lead_months']} months (rule: at least 6).",
        f"- Raised and picked for a term-only queue at some date: {sum(d['queued'] for d in r['developments'])} of "
        f"{len(r['developments'])}.", "",
        "| Development | Mainstream | First raised | Lead (months) | Queued | Miss |", "|---|---|---|---:|---|---|",
    ]  # fmt: skip
    for d in r["developments"]:
        lines.append(f"| {d['id']} {d['name']} | {d['mainstream']} | {d['first_raised'] or '-'} | "
                     f"{d['lead_months'] if d['lead_months'] is not None else '-'} | {'yes' if d['queued'] else 'no'} "
                     f"| {d['miss'] or '-'} |")  # fmt: skip
    lines += ["", "## By date", "", "| Development | As of | Matching candidates | Types | Detectors | In the queue |",
              "|---|---|---:|---|---|---:|"]  # fmt: skip
    for d in r["developments"]:
        for p in d["dates"]:
            types = ", ".join(f"{k} {v}" for k, v in p["types"].items()) or "-"
            dets = ", ".join(f"{k} {v}" for k, v in p["detectors"].items()) or "-"
            lines.append(f"| {d['id']} | {p['as_of']} | {p['matched']} | {types} | {dets} | {p['queued']} |")
    lines += ["", "## The scans", "", "| As of | Series tested | Documents visible | Vocabulary | Candidates | Queue | "
              "Seconds |", "|---|---:|---:|---:|---:|---:|---:|"]  # fmt: skip
    for day, c in sorted(r["scans"].items()):
        lines.append(
            f"| {day} | {c['series']} | {c['documents_visible']} | {c['vocabulary']} | {c['candidates']} | "
            f"{c['queued']} | {c['seconds']} |"
        )
    lines += ["", "## Leakage and limits (design §11.3)", "",
              "- Fitted at each date: the keyphrase vocabulary and its first-seen dates. De-duplication by URL and "
              "title only. No embeddings, clusters, micro-clusters, zero-shot tags or decision model (term-only).",
              "- OpenAlex is left out (its topic classifier was trained in 2024); GDELT has no history before October "
              "2026.",
              "- Statistics take each period's latest vintage at the date, else the earliest one Moria holds (2026): "
              "revised values leak where no earlier vintage exists.",
              "- IP RAPID is the 2026 release read at past dates: applications amended or reclassified later appear "
              "as they are now, classes by the date they were assigned where dated.",
              "- No artefact checks: no collection history exists at past dates.",
              "- Backfilled history has no true first sighting; non-English sources are absent."]  # fmt: skip
    return "\n".join(lines) + "\n"
