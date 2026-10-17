"""`moria rank --as-of D`: every candidate of a scan scored for the two views, and the shortlist that dossiers and
pathway suggestions are built for (design §1, §2.5, §8.2, §8.5; day 5).

Wide and shallow, then narrow and deep (§2.5): every candidate is scored here; the shortlist (`rank.shortlist`,
about 100) is chosen under the same ring quotas as the queue; `moria queue` then ranks the shortlist again with the
decision model's pathway suggestions and picks the review queue of about 40.

**One ring per candidate** (for the quotas; the handover's flag 7): a one-ring card gives its ring; a label that
matches the IP-system terms (the core-ring query groups) is core; a statistics series takes its query's ring
(`rank.rings.by_query`), a GDELT volume its query group's ring, an OpenAlex field, subfield or domain its field's
ring; anything else takes its label's zero-shot ring (the codebook's ring prototypes) among its card's rings. A
document candidate takes the ring most of its window items carry (one item per de-duplication group).
`ring_basis` records which rule applied.

**Components**, each in (0, 1]:
- strength: the detector's effect as a percentile within its type and subject kind (strengths of different types
  are not comparable; the handover's flag 2);
- breadth: independent lines of evidence (`corroboration`, D-025), families beyond the first, and detectors that
  agree, as a percentile over all candidates; a redundancy group counts once (only one of a group is picked);
- lead time: the most anticipatory detector that fired (`rank.lead`);
- novelty: the most novel detector (`rank.novelty`), lowered when the nearest known trend matches (a tag, never a
  reason to reject: D-014);
- pathway and impact: added by `moria queue` from the pathway suggestions.

A view's score is the weighted geometric mean of its components times the candidate's factors: its type (band
anomalies rank lower, D-025), its flags (shown, never hidden: §8.3), the scope's Australian relevance and, if set,
'explained by its context' (D-028). The early-warning view takes candidates whose views include it, and likewise the
strategic view. A document weak signal whose evidence would not make a weak signal from sources with
`rank.cold_start_days` of history before the window is **held** (D-032): scored for neither view, so it is shown in the
ranking and the dashboard but neither shortlisted nor queued, until its sources have a baseline.

**Selection** (`select`, shared with `moria queue`): picks alternate between the two views' rankings by their
shares; each ring is capped at its quota, each source at `queue.source_max`, third-order pathways at
`queue.third_order_max`, and one candidate per redundancy group. When a ring runs out, its unused places pass to
the others (pass 2), then the source cap is relaxed (pass 3); each pick records its pass.

Writes `review/as_of=<D>/ranked.parquet`: one row per candidate with its ring, components, factors, scores and
shortlist place.
"""

from __future__ import annotations

import json
import logging
import math
import tempfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import yaml

from .artefacts import COMMAND as ARTEFACTS
from .concepts import COMMAND as DOCS
from .concepts import is_core_group
from .config import (
    BaselineFile,
    CodebookFile,
    QueueConfig,
    ReviewConfig,
    SourceCard,
    TerritoriesFile,
)
from .detect import COMMAND as DETECT
from .detect import _matching
from .manifest import Manifest
from .measures import COMMAND as SERIES
from .records import canonical_json
from .store import Store
from .tables import STRS, cache_root, fetch_outputs, read_rows, upload, write_rows

log = logging.getLogger("moria.rank")

COMMAND = "rank"
RINGS = ("core", "adjacent", "wider_world")
VIEWS = ("early_warning", "strategic")
COMPONENTS = {"early_warning": ("strength", "novelty", "lead", "pathway"),
              "strategic": ("strength", "breadth", "impact", "pathway")}  # fmt: skip

RANKED = pa.schema(
    [
        ("candidate_id", pa.string()),
        ("as_of", pa.date32()),
        ("type", pa.string()),
        ("subject_kind", pa.string()),
        ("subject", pa.string()),
        ("label", pa.string()),
        ("views", STRS),
        ("source", pa.string()),  # the primary source (the first of its sources)
        ("sources", STRS),
        ("families", STRS),
        ("detectors", STRS),
        ("flags", STRS),
        ("ring", pa.string()),
        ("ring_basis", pa.string()),  # card, core_terms, map, items, zeroshot, default
        ("redundancy_group", pa.string()),
        ("strength", pa.float64()),
        ("strength_pct", pa.float64()),
        ("breadth", pa.float64()),
        ("lead", pa.float64()),
        ("novelty", pa.float64()),
        ("known_trend", pa.string()),
        ("known_trend_sim", pa.float64()),
        ("known_trend_match", pa.bool_()),
        ("territory_top", pa.string()),
        ("territory_sim", pa.float64()),
        ("term_territories", STRS),
        ("scope_factor", pa.float64()),
        ("type_factor", pa.float64()),
        ("flag_factor", pa.float64()),
        ("context_factor", pa.float64()),
        ("held", pa.bool_()),  # a document weak signal whose sources have no baseline yet: not shortlisted (D-032)
        ("score_early_warning", pa.float64()),  # before the pathway suggestions; null when not in the view
        ("score_strategic", pa.float64()),
        ("shortlisted", pa.bool_()),
        ("shortlist_rank", pa.int32()),
        ("shortlist_view", pa.string()),
        ("shortlist_pass", pa.int8()),
    ]
)


# ------------------------------------------------------------------------------------------------------- helpers


def files_of(store: Store, m: dict, prefix: str) -> dict[str, Path]:
    """A manifest's outputs under a prefix, by file name, checked against their hashes."""
    return {k.rsplit("/", 1)[1]: p for k, p in fetch_outputs(store, m, prefix, cache_root()).items()}


def manifest_of(store: Store, command: str, run_id: str) -> dict:
    """A named run's manifest, which must have passed (an upstream run a later stage was built on)."""
    m = json.loads(store.get(f"manifests/{command}/{run_id}.json"))
    if m["status"] != "passed":
        raise ValueError(f"{command} run {run_id} {m['status']}")
    return m


def failed(command: str, store: Store, manifest: Manifest, e: Exception) -> tuple[str, str, dict]:
    first = (str(e).splitlines() or [type(e).__name__])[0]
    cause = f"{command}: {type(e).__name__}: {first[:300]}"
    log.error("%s", cause)
    return "failed", manifest.finish(store, "failed", cause), {"error": cause}


def percentiles(values: list[float | None]) -> list[float]:
    """Mid-rank percentiles in (0, 1): ties share their average rank; a missing value counts as the lowest."""
    n = len(values)
    if n == 0:
        return []
    keyed = sorted(range(n), key=lambda i: -math.inf if values[i] is None else values[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        vi = values[keyed[i]]
        while j + 1 < n and values[keyed[j + 1]] == vi:
            j += 1
        mid = (i + j) / 2
        for k in range(i, j + 1):
            out[keyed[k]] = (mid + 0.5) / n
        i = j + 1
    return out


def geomean(parts: dict[str, float], weights: dict[str, float], floor: float) -> float:
    """The weighted geometric mean of the components present (a component absent from `parts` is left out)."""
    used = {k: w for k, w in weights.items() if k in parts and w > 0}
    if not used:
        return floor
    total = sum(used.values())
    return math.exp(sum(w * math.log(max(parts[k], floor)) for k, w in used.items()) / total)


def largest_remainder(size: int, shares: dict[str, float]) -> dict[str, int]:
    raw = {k: size * v for k, v in shares.items()}
    caps = {k: math.floor(v) for k, v in raw.items()}
    left = size - sum(caps.values())
    for k in sorted(raw, key=lambda k: (-(raw[k] - caps[k]), k))[:left]:
        caps[k] += 1
    return caps


def select(rows: list[dict], size: int, qc: QueueConfig, score: dict[str, str],
           third_order: bool = False) -> list[dict]:  # fmt: skip
    """Picks under the quotas (see the module's docstring). `score` names each view's score field; a row is in a
    view when its score there is not None. Returns the picks in order, each {candidate_id, rank, view, pass}."""
    ring_cap = largest_remainder(size, qc.rings)
    source_cap = max(1, math.floor(size * qc.source_max))
    third_cap = math.floor(size * qc.third_order_max)
    rankings = {v: sorted((r for r in rows if r.get(score[v]) is not None),
                          key=lambda r: (-r[score[v]], r["candidate_id"])) for v in VIEWS}  # fmt: skip
    picks: list[dict] = []
    used: set[str] = set()
    groups: set[str] = set()
    rings: Counter = Counter()
    sources: Counter = Counter()
    thirds = 0
    for stage in (1, 2, 3):
        pos = dict.fromkeys(VIEWS, 0)
        done = {v for v in VIEWS if not rankings[v] or qc.views.get(v, 0) <= 0}
        while len(picks) < size and len(done) < len(VIEWS):
            taken = Counter(p["view"] for p in picks)
            view = min((v for v in VIEWS if v not in done),
                       key=lambda v: ((taken[v] + 1) / qc.views[v], VIEWS.index(v)))  # fmt: skip
            ranking = rankings[view]
            chosen = None
            while pos[view] < len(ranking):
                r = ranking[pos[view]]
                pos[view] += 1
                if r["candidate_id"] in used or (r.get("redundancy_group") and r["redundancy_group"] in groups):
                    continue
                if stage == 1 and rings[r["ring"]] >= ring_cap.get(r["ring"], 0):
                    continue
                if stage < 3 and sources[r["source"]] >= source_cap:
                    continue
                if third_order and r.get("order") == "3" and thirds >= third_cap:
                    continue
                chosen = r
                break
            if chosen is None:
                done.add(view)
                continue
            used.add(chosen["candidate_id"])
            if chosen.get("redundancy_group"):
                groups.add(chosen["redundancy_group"])
            rings[chosen["ring"]] += 1
            sources[chosen["source"]] += 1
            thirds += third_order and chosen.get("order") == "3"
            picks.append({"candidate_id": chosen["candidate_id"], "rank": len(picks) + 1, "view": view,
                          "pass": stage})  # fmt: skip
        if len(picks) >= size:
            break
    return picks


# --------------------------------------------------------------------------------------------------------- rings


def series_ring(label: str, rings: list[str], meta: dict | None, core_label: bool, zeroshot: dict | None,
                cfg: ReviewConfig) -> tuple[str, str]:  # fmt: skip
    """(ring, basis) of a series candidate."""
    rings = [r for r in RINGS if r in (rings or [])] or ["adjacent"]
    if len(rings) == 1:
        return rings[0], "card"
    if core_label:
        return "core", "core_terms"
    maps = cfg.rank.rings
    if meta:
        source = meta.get("source")
        dims = meta.get("dims") or {}
        q = dims.get("query_id")
        if source in maps.by_query and q in maps.by_query[source]:
            return maps.by_query[source][q], "map"
        if source == "gdelt_news" and dims.get("ring") in RINGS:
            return dims["ring"], "map"
        if source == "openalex_counts":
            level, oid = dims.get("level"), str(dims.get("id") or "").rsplit("/", 1)[-1]
            if level == "field" and oid in maps.openalex_fields:
                return maps.openalex_fields[oid], "map"
            if level == "subfield" and oid[:2] in maps.openalex_fields:
                return maps.openalex_fields[oid[:2]], "map"
            if level == "domain" and oid in maps.openalex_domains:
                return maps.openalex_domains[oid], "map"
    others = [r for r in rings if r != "core"] or rings
    if zeroshot:
        best = max(others, key=lambda r: (zeroshot.get(r, -1.0), -RINGS.index(r)))
        return best, "zeroshot"
    return others[0], "default"


def items_ring(items: list[dict]) -> tuple[str, str] | None:
    """The ring most of a document candidate's items carry, one item per de-duplication group (the earliest)."""
    first: dict[str, dict] = {}
    for e in items:
        g = e["dedup_group"] or e["ref"]
        at = e["observable_at"].timestamp() if e["observable_at"] else 0.0
        if g not in first or (at, e["ref"]) < first[g]["_k"]:
            first[g] = {**e, "_k": (at, e["ref"])}
    counts = Counter(e["ring"] for e in first.values() if e["ring"] in RINGS)
    if not counts:
        return None
    ring = max(RINGS, key=lambda r: (counts[r], -RINGS.index(r)))
    return ring, "items"


# ---------------------------------------------------------------------------------------------- label semantics


class LabelSemantics:
    """Similarities of short labels (series names) to the ring, known-trend and territory prototypes, by the same
    encoder and prototype texts as the item tags (`moria tag`). Only vectors and similarities are derived."""

    def __init__(self, encoder, codebook: CodebookFile, territories: TerritoriesFile, baseline: BaselineFile,
                 context: dict | None):  # fmt: skip
        from .tags import prototype_texts, prototypes

        texts = prototype_texts(codebook, territories, baseline, context)
        keep = {k: v for k, v in texts.items() if k in ("ring", "territory", "known_trend")}
        self.encoder = encoder
        self.protos = prototypes(encoder, keep)

    def score(self, labels: list[str]) -> list[dict]:
        if not labels:
            return []
        vecs = self.encoder.encode(labels)
        out = [dict() for _ in labels]
        for name, (keys, mat) in self.protos.items():
            sims = vecs @ mat.T
            for i in range(len(labels)):
                if name == "ring":
                    out[i]["ring"] = {k: float(sims[i, j]) for j, k in enumerate(keys)}
                else:
                    j = int(np.argmax(sims[i]))
                    out[i][name] = (keys[j], float(sims[i, j]))
        return out


def item_semantics(items: list[dict], tags: dict[str, dict]) -> dict:
    """The nearest known trend and territory of a document candidate, from its items' tags: the trend nearest most
    of its items (by summed similarity), and its mean similarity over them; the territories its items' terms match."""
    kt: dict[str, list[float]] = defaultdict(list)
    terr: dict[str, list[float]] = defaultdict(list)
    terms: Counter = Counter()
    for e in items:
        t = tags.get(e["ref"])
        if not t:
            continue
        if t.get("known_trend_top"):
            kt[t["known_trend_top"]].append(float(t.get("known_trend_sim") or 0))
        if t.get("territory_top"):
            terr[t["territory_top"]].append(float(t.get(f"territory_sim_{t['territory_top']}") or 0))
        terms.update(t.get("term_territories") or [])
    out: dict = {"term_territories": sorted(terms)}
    if kt:
        best = max(kt, key=lambda k: (sum(kt[k]), k))
        out["known_trend"] = (best, float(np.mean(kt[best])))
    if terr:
        best = max(terr, key=lambda k: (sum(terr[k]), k))
        out["territory"] = (best, float(np.mean(terr[best])))
    return out


# ---------------------------------------------------------------------------------------------------- the stage


def series_meta(store: Store, series_run: dict) -> dict[str, dict]:
    """Labels and dimensions of every series the scan read, from the normalise and IP RAPID metrics runs that its
    series measures were built on."""
    out: dict[str, dict] = {}
    paths = []
    nrun = series_run["params"].get("normalise_run")
    if nrun:
        nm = manifest_of(store, "normalise", nrun)
        paths += [p for k, p in fetch_outputs(store, nm, "lake/series/", cache_root()).items()]
    irun = series_run["params"].get("ipr_metrics_run")
    if irun:
        im = manifest_of(store, "ipr.metrics", irun)
        paths += [p for k, p in fetch_outputs(store, im, "lake/ipr_metrics/series", cache_root()).items()]
    for p in paths:
        for r in read_rows(p, ["series_id", "source", "label", "dimensions", "scope"]):
            try:
                dims = json.loads(r["dimensions"] or "{}")
            except ValueError:
                dims = {}
            out[r["series_id"]] = {"source": r["source"], "label": r["label"], "dims": dims, "scope": r["scope"]}
    return out


def load_tags(store: Store, docs_run: dict) -> dict[str, dict]:
    trun = docs_run["params"].get("tags_run")
    if not trun:
        return {}
    tm = manifest_of(store, "tag", trun)
    out = {}
    for p in fetch_outputs(store, tm, "features/tags/", cache_root()).values():
        import pyarrow.parquet as pq

        names = pq.read_schema(p).names
        cols = [c for c in names if c in ("item_id", "known_trend_top", "known_trend_sim", "territory_top",
                                          "term_territories") or c.startswith("territory_sim_")]  # fmt: skip
        for r in read_rows(p, cols):
            out[r["item_id"]] = r
    return out


def inputs(store: Store, as_of: date) -> tuple[dict, dict]:
    dm = _matching(store, DETECT, as_of)
    am = _matching(store, ARTEFACTS, as_of)
    if am["params"].get("detect_run") != dm["run_id"]:
        raise ValueError(f"the artefact checks of {as_of} are for an older detect run; run `moria artefacts`")
    sm = manifest_of(store, SERIES, dm["params"]["series_run"])
    docm = manifest_of(store, DOCS, dm["params"]["documents_run"])
    runs = {"detect_run": dm["run_id"], "artefacts_run": am["run_id"], "series_run": sm["run_id"],
            "documents_run": docm["run_id"]}  # fmt: skip
    files = {**files_of(store, dm, "candidates/"), **files_of(store, am, "candidates/")}
    return runs, {"files": files, "series_run": sm, "documents_run": docm}


def score_candidates(cands: list[dict], evidence: list[dict], flags: dict[str, list[str]], meta: dict[str, dict],
                     tags: dict[str, dict], semantics: LabelSemantics | None, matcher, cards: dict[str, SourceCard],
                     cfg: ReviewConfig, as_of: date, history: dict[str, float] | None = None,
                     min_items: int = 3, min_sources: int = 2) -> list[dict]:  # fmt: skip
    """The ranked rows (before selection). `history` is each document source's days of history before the window
    (`baseline_days`); with `rank.cold_start_days`, a document weak signal is held unless its window items from
    sources with that much history still make a weak signal (min_items groups from min_sources sources)."""
    from .tags import term_tags

    rc = cfg.rank
    items: dict[str, list[dict]] = defaultdict(list)
    subject_series: dict[str, str] = {}
    for e in evidence:
        if e["kind"] == "item":
            items[e["candidate_id"]].append(e)
        elif e["role"] == "subject":
            subject_series[e["candidate_id"]] = e["ref"]
    # series labels: the subject's own label (an AU/world pair: its Australian series)
    series_labels: dict[str, str] = {}
    for c in cands:
        if c["subject_kind"] in ("series", "pair"):
            sid = subject_series.get(c["candidate_id"], c["subject"])
            series_labels[c["candidate_id"]] = (meta.get(sid) or {}).get("label") or c["label"] or c["subject"]
    order = sorted(series_labels)
    sem = dict(zip(order, semantics.score([series_labels[k] for k in order]), strict=True)) if semantics else {}
    rows = []
    for c in cands:
        cid = c["candidate_id"]
        row = {k: c[k] for k in ("candidate_id", "type", "subject_kind", "subject", "label", "views", "sources",
                                 "families", "detectors", "redundancy_group", "strength")}  # fmt: skip
        row.update(as_of=as_of, source=(c["sources"] or ["unknown"])[0], flags=flags.get(cid, []))
        s = sem.get(cid) or {}
        if c["subject_kind"] in ("series", "pair"):
            sid = subject_series.get(cid, c["subject"])
            m = meta.get(sid)
            groups, territories, _ = term_tags(matcher, {"title": series_labels[cid]}) if matcher else ([], [], 0)
            core = any(is_core_group(g) for g in groups)
            card = cards.get(row["source"])
            rings = c["rings"] or (list(card.rings) if card else ["core"] if row["source"] == "ip_rapid_metrics"
                                   else [])  # fmt: skip
            row["ring"], row["ring_basis"] = series_ring(series_labels[cid], rings, m, core, s.get("ring"), cfg)
            row["term_territories"] = territories
            kt, terr = s.get("known_trend"), s.get("territory")
        else:
            got = items_ring(items.get(cid, [])) if c["sources"] != ["ip_rapid"] else None
            row["ring"], row["ring_basis"] = got or (next((r for r in RINGS if r in (c["rings"] or [])), "core"),
                                                     "card")  # fmt: skip
            si = item_semantics(items.get(cid, []), tags)
            row["term_territories"] = si["term_territories"]
            kt, terr = si.get("known_trend"), si.get("territory")
        row["known_trend"], row["known_trend_sim"] = kt if kt else (None, None)
        row["territory_top"], row["territory_sim"] = terr if terr else (None, None)
        row["known_trend_match"] = bool(kt and kt[1] >= rc.known_trend_sim)
        dets = [d for d in c["detectors"] if d in rc.lead]
        row["lead"] = max((rc.lead[d] for d in dets), default=rc.floor)
        nov = max((rc.novelty[d] for d in dets), default=rc.floor)
        row["novelty"] = nov * (rc.known_trend_factor if row["known_trend_match"] else 1.0)
        row["_breadth_raw"] = ((c.get("corroboration") or 1) + max(len(c["families"] or []) - 1, 0)
                               + 0.5 * (len(set(c["detectors"])) - 1))  # fmt: skip
        row["scope_factor"] = rc.scope.factor(c.get("scope"))
        row["type_factor"] = rc.type_weight[c["type"]]
        row["flag_factor"] = math.prod(rc.flag_penalty[f] for f in row["flags"] if f in rc.flag_penalty)
        explained = "context_explains" in json.loads(c["numbers"] or "{}")
        row["context_factor"] = rc.context_explained if explained else 1.0
        row["held"] = bool(rc.cold_start_days and history is not None and c["subject_kind"] not in ("series", "pair")
                           and c["sources"] != ["ip_rapid"]
                           and not established(items.get(cid, []), history, rc.cold_start_days, min_items,
                                               min_sources))  # fmt: skip
        rows.append(row)
    # percentiles: strength within type and subject kind; breadth over all
    by: dict[tuple, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by[(r["type"], r["subject_kind"])].append(i)
    for idx in by.values():
        for i, p in zip(idx, percentiles([rows[i]["strength"] for i in idx]), strict=True):
            rows[i]["strength_pct"] = p
    for r, p in zip(rows, percentiles([r.pop("_breadth_raw") for r in rows]), strict=True):
        r["breadth"] = p
    for r in rows:
        view_scores(r, cfg)
    return rows


def established(items: list[dict], history: dict[str, float], days: int, min_items: int, min_sources: int) -> bool:
    """Would a document candidate still be a weak signal on the window items of sources with `days` of history?"""
    kept = [i for i in items if i.get("role") == "window" and (history.get(i["source"]) or 0) >= days]
    return len({i["dedup_group"] for i in kept}) >= min_items and len({i["source"] for i in kept}) >= min_sources


def baseline_days(volumes: list[dict], as_of: date, window_days: int, baseline_days_: int) -> dict[str, float]:
    """Each document source's days of dated history before the window (in the baseline, at most its length)."""
    from .measures import as_of_end

    w_start = as_of_end(as_of) - timedelta(days=window_days)
    b_start = w_start - timedelta(days=baseline_days_)
    out = {}
    for v in volumes:
        start = v.get("coverage_start")
        out[v["source"]] = max((w_start - max(start, b_start)).total_seconds() / 86400, 0.0) if start else 0.0
    return out


def factors(r: dict) -> float:
    return r["scope_factor"] * r["type_factor"] * r["flag_factor"] * r["context_factor"]


def view_scores(r: dict, cfg: ReviewConfig, weights: dict[str, dict[str, float]] | None = None,
                extra: dict[str, float] | None = None) -> None:  # fmt: skip
    """Each view's score: the weighted geometric mean of its components times the factors. `extra` adds the pathway
    and impact components (from `moria queue`)."""
    weights = weights or cfg.rank.weights
    parts = {"strength": r["strength_pct"], "novelty": r["novelty"], "lead": r["lead"], "breadth": r["breadth"],
             **(extra or {})}  # fmt: skip
    for view in VIEWS:
        key = f"score_{view}"
        if view not in (r["views"] or []) or r.get("held"):
            r[key] = None
            continue
        comps = {k: parts[k] for k in COMPONENTS[view] if k in parts}
        r[key] = geomean(comps, weights[view], cfg.rank.floor) * factors(r)


def rank(store: Store, cfg: ReviewConfig, cards: dict[str, SourceCard], codebook: CodebookFile,
         territories: TerritoriesFile, baseline: BaselineFile, encoder_factory, as_of: date,
         config_hash: str | None = None) -> tuple[str, str, dict]:  # fmt: skip
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        runs, got = inputs(store, as_of)
        manifest.params = {"as_of": as_of.isoformat(), **runs}
        f = got["files"]
        cands = read_rows(f["candidates.parquet"])
        evidence = read_rows(f["evidence.parquet"])
        flags = {r["candidate_id"]: r["flags"] for r in read_rows(f["artefacts.parquet"], ["candidate_id", "flags"])}
        meta = series_meta(store, got["series_run"])
        tags = load_tags(store, got["documents_run"])
        semantics = None
        if encoder_factory is not None:
            from .tags import CONTEXT_KEY

            context = yaml.safe_load(store.get(CONTEXT_KEY)) if store.exists(CONTEXT_KEY) else None
            encoder = encoder_factory()
            semantics = LabelSemantics(encoder, codebook, territories, baseline, context)
            manifest.params["encoder"] = encoder.identity
            manifest.params["territory_context"] = context is not None
        from .config import load_detect
        from .tags import term_matcher

        dc = load_detect().documents
        history = None
        if cfg.rank.cold_start_days:
            vols = read_rows(files_of(store, got["documents_run"], "measures/documents/")["volumes.parquet"])
            history = baseline_days(vols, as_of, dc.window_days, dc.baseline_days)
            manifest.params["cold_start_days"] = cfg.rank.cold_start_days
        rows = score_candidates(cands, evidence, flags, meta, tags, semantics, term_matcher(cards), cards, cfg, as_of,
                                history, dc.min_items, dc.min_sources)  # fmt: skip
        picks = select(rows, cfg.rank.shortlist, cfg.queue, {v: f"score_{v}" for v in VIEWS})
        place = {p["candidate_id"]: p for p in picks}
        for r in rows:
            p = place.get(r["candidate_id"])
            r.update(shortlisted=p is not None, shortlist_rank=p and p["rank"], shortlist_view=p and p["view"],
                     shortlist_pass=p and p["pass"])  # fmt: skip
        with tempfile.TemporaryDirectory(prefix="moria-rank-") as tmp:
            path = Path(tmp) / "ranked.parquet"
            write_rows(rows, RANKED, path, ("candidate_id",))
            upload(store, manifest, f"review/as_of={as_of.isoformat()}/ranked.parquet", path)
        manifest.counts = counts_of(rows, picks)
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        return failed(COMMAND, store, manifest, e)


def counts_of(rows: list[dict], picks: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    counts["candidates"] = len(rows)
    counts["shortlisted"] = len(picks)
    shortlisted = {p["candidate_id"] for p in picks}
    for r in rows:
        counts[f"ring_{r['ring']}"] += 1
        counts[f"ring_basis_{r['ring_basis']}"] += 1
        if r["candidate_id"] in shortlisted:
            counts[f"shortlist_ring_{r['ring']}"] += 1
            counts[f"shortlist_type_{r['type']}"] += 1
            counts["shortlist_flagged"] += bool(r["flags"])
        counts["known_trend_match"] += bool(r["known_trend_match"])
        counts["held"] += bool(r.get("held"))
    for p in picks:
        counts[f"shortlist_pass_{p['pass']}"] += 1
        counts[f"shortlist_view_{p['view']}"] += 1
    return dict(sorted(counts.items()))


def ranked_summary(rows: list[dict]) -> str:
    """Canonical JSON of the shortlist's ids in order (for tests and manifests)."""
    return canonical_json(sorted((r["shortlist_rank"], r["candidate_id"]) for r in rows if r["shortlisted"]))
