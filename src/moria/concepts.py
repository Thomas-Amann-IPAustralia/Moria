"""`moria measure documents --as-of D`: the five weak-signal indicators over documents (design §8.2, §8.5; day 4).

Reads the latest passed `normalise`, `features.dedup`, `features.keyphrases`, `features.embed` and `tag` runs (all
of the same normalise run) and the latest `ipr.metrics` run. At `as_of`, an item is visible when it was observable by
then and Moria had seen it by then; an item observable before its source's onboarding (Moria's first collection of
that source) is backfill, bound by its observable date alone (design §6.3). An item dated only by Moria's first sight
in its source's first collection (an undated backlog) carries no date at all and is left out of every window.

The weak-signal window is the `window_days` before as_of; the baseline the `baseline_days` before that. Counts are of
de-duplication groups (one per syndicated story), never raw items.

**Concepts:** keyphrases (`kp:`), the 47 territory and theme term groups (`tg:`), and clusters of the embeddings
fitted at as_of (`cl:`, MiniBatchKMeans, named by their top keyphrases).

**Indicators:**
1. `new_term`: a keyphrase first observable inside the window (over every document), in at least k window groups from
   at least 2 sources, at least one of them in a credible family (research, patent, legal, policy);
2. `new_combination`: two keyphrases, IPC subclasses or Nice classes together for the first time in the window
   (each already seen apart), or whose lift at least doubled (exact test, Holm); and, for the SignalBoost proposal
   (D-025), `fading`: an established pair whose co-occurrence fell well below what its baseline lift predicts from
   each side's activity in the window (exact Poisson test, Holm), and the same three tests on an applicant country
   and a class (IP RAPID, schemes `ipc_country` and `nice_country`): jurisdictions entering, rising in or leaving
   a technology or a class of goods and services;
3. `cross_family`: a concept in at least 3 families in the window and at most 1 before; and `cross_ring` (§8.5): a
   concept rising in wider-world items (exact test, Holm) that appears in core-ring items for the first time;
4. `low_base_surge`: a concept's rate per family volume against a low baseline (exact Poisson test, Holm);
5. `novel_items`: window items far from the baseline of their family (LocalOutlierFactor on embeddings), grouped
   into micro-clusters of at least 3.

An item's ring: its source card's ring when the card has one; else core when it matches a core-ring term group (a
territory's core terms or the `ip_system` theme, D-021's flag); else the zero-shot ring among the card's other rings.

Writes `measures/documents/as_of=<D>/`: `volumes`, `concepts`, `surges`, `combinations`, `novelty`, `clusters`,
`assignments`, `group_items` (window items per term group and source, for the checks on news volumes) and `evidence`
(the window items behind each concept that fired), all in the private bucket: keyphrases are evidence.
"""

from __future__ import annotations

import logging
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa

from . import stats
from .config import DetectConfig, SourceCard
from .embed import from_blobs
from .features import DEDUP, EMBED, KEYPHRASES
from .iprmetrics import COMMAND as IPRM
from .manifest import Manifest
from .measures import as_of_end
from .normalise import COMMAND as NORMALISE
from .store import Store
from .tables import STRS, TS, cache_root, fetch_outputs, read_rows, upload, upstream, write_rows
from .tags import COMMAND as TAG

log = logging.getLogger("moria.concepts")

COMMAND = "measure.documents"
F64 = pa.float64()

VOLUMES = pa.schema(
    [
        ("source", pa.string()),
        ("family", pa.string()),
        ("onboarded_at", TS),  # Moria's first sight of the source
        ("coverage_start", TS),  # its earliest dated item: before this the source says nothing
        ("backlog_items", pa.int32()),  # undated items from its first collection, left out of every window
        ("window_items", pa.int32()),
        ("window_groups", pa.int32()),
        ("baseline_items", pa.int32()),
        ("baseline_groups", pa.int32()),
        ("window_per_day", F64),
        ("baseline_per_day", F64),  # over the days of the baseline the source covers
        ("change", F64),  # window per day over baseline per day, minus 1 (the coverage check, design §8.3)
    ]
)
CONCEPTS = pa.schema(
    [
        ("concept", pa.string()),  # kp:<phrase>, tg:<group>, cl:<cluster>
        ("kind", pa.string()),
        ("label", pa.string()),
        ("window_groups", pa.int32()),
        ("baseline_groups", pa.int32()),
        ("window_sources", pa.int16()),
        ("window_families", STRS),
        ("baseline_families", STRS),
        ("window_rings", STRS),
        ("core_window", pa.int32()),
        ("core_baseline", pa.int32()),
        ("wider_window", pa.int32()),
        ("wider_baseline", pa.int32()),
        ("first_observable_at", TS),  # keyphrases: the first document holding the phrase, over every document
        ("new_term", pa.bool_()),
        ("cross_family", pa.bool_()),
        ("cross_ring_ratio", F64),
        ("cross_ring_p", F64),
        ("cross_ring_p_holm", F64),
        ("cross_ring", pa.bool_()),
    ]
)
SURGES = pa.schema(
    [
        ("concept", pa.string()),
        ("kind", pa.string()),
        ("family", pa.string()),
        ("window_groups", pa.int32()),
        ("baseline_groups", pa.int32()),
        ("window_exposure", pa.int32()),  # the family's groups in the window
        ("baseline_exposure", pa.int32()),
        ("window_sources", pa.int16()),
        ("expected", F64),
        ("ratio", F64),
        ("p", F64),
        ("p_holm", F64),
        ("surge", pa.bool_()),
    ]
)
COMBINATIONS = pa.schema(
    [
        ("combination", pa.string()),  # nc:<scheme>:<a>+<b>
        ("scheme", pa.string()),  # kp, ipc, nice
        ("a", pa.string()),
        ("b", pa.string()),
        ("window", pa.int32()),  # groups (keyphrases) or applications (classes) holding both
        ("baseline", pa.int32()),
        ("a_baseline", pa.int32()),
        ("b_baseline", pa.int32()),
        ("window_sources", pa.int16()),  # keyphrases: sources; classes: 2 when at least two applicants
        ("baseline_sources", pa.int16()),  # the same, in the baseline
        ("a_window", pa.int32()),
        ("b_window", pa.int32()),
        ("lift_window", F64),
        ("lift_baseline", F64),
        ("window_exposure", pa.int32()),  # groups (keyphrases) or classified applications in the window
        ("baseline_exposure", pa.int32()),
        ("exposure_change", F64),  # per day (or month), window against baseline, minus 1: the coverage check
        ("classes_since", pa.string()),  # classes: the later of the two classes' first months
        ("new_class", pa.bool_()),  # classes: one of them first seen inside the baseline (new to the scheme)
        ("ratio", F64),
        ("p", F64),
        ("p_holm", F64),
        ("new", pa.bool_()),
        ("rising", pa.bool_()),
        ("expected_window", F64),  # at the baseline's lift, from each side's activity in the window (D-025)
        ("p_fade", F64),
        ("p_fade_holm", F64),
        ("fading", pa.bool_()),  # an established pair that broke down
    ]
)
NOVELTY = pa.schema(
    [
        ("micro", pa.string()),  # nv:<family>:<n>
        ("family", pa.string()),
        ("items", pa.int32()),
        ("groups", pa.int32()),
        ("sources", STRS),
        ("label", pa.string()),  # its members' top keyphrases
        ("mean_score", F64),  # LocalOutlierFactor's score_samples (lower is more novel)
        ("baseline_size", pa.int32()),
    ]
)
GROUP_ITEMS = pa.schema(
    [
        ("group", pa.string()),  # a territory or theme term group
        ("source", pa.string()),
        ("family", pa.string()),
        ("items", pa.int32()),  # window items matching the group
        ("groups", pa.int32()),  # their de-duplication groups
    ]
)
CLUSTERS = pa.schema(
    [("cluster", pa.string()), ("size", pa.int32()), ("label", pa.string()), ("families", STRS)]
)  # fmt: skip
ASSIGNMENTS = pa.schema([("item_id", pa.string()), ("cluster", pa.string())])
EVIDENCE = pa.schema(
    [
        ("key", pa.string()),  # a concept, combination or micro-cluster
        ("item_id", pa.string()),
        ("source", pa.string()),
        ("family", pa.string()),
        ("ring", pa.string()),
        ("dedup_group", pa.string()),
        ("observable_at", TS),
        ("first_seen_at", TS),
        ("role", pa.string()),  # window, or baseline for the items a surge is compared with (not stored)
    ]
)

CORE_GROUP = ("theme:ip_system:",)


def is_core_group(g: str) -> bool:
    return g.startswith(CORE_GROUP) or (g.startswith("T") and ":core:" in g)


def item_ring(card: SourceCard | None, groups: list[str], probs: dict[str, float]) -> str:
    rings = list(card.rings) if card else ["wider_world"]
    if len(rings) == 1:
        return rings[0]
    if "core" in rings and any(is_core_group(g) for g in groups or []):
        return "core"
    others = [r for r in rings if r != "core"] or ["core"]
    if len(others) == 1:
        return others[0]
    return max(others, key=lambda r: probs.get(r) or 0.0)


# -------------------------------------------------------------------------------------------------------- inputs


def _same_run(m: dict, normalise_run: str, command: str) -> None:
    if m["params"].get("normalise_run") != normalise_run:
        raise ValueError(f"{command} is from normalise run {m['params'].get('normalise_run')}, not the latest "
                         f"({normalise_run}); run `moria prepare` first")  # fmt: skip


def inputs(store: Store) -> tuple[dict, dict]:
    nm = upstream(store, NORMALISE)
    runs = {"normalise_run": nm["run_id"]}
    files = {"documents": {k.split("/source=")[1].split("/")[0]: p
                           for k, p in fetch_outputs(store, nm, "lake/documents/", cache_root()).items()}}  # fmt: skip
    for command, prefix, name in ((DEDUP, "features/dedup/", "dedup"), (KEYPHRASES, "features/keyphrases/", "kp"),
                                  (EMBED, "features/embeddings/", "emb"), (TAG, "features/tags/", "tags")):  # fmt: skip
        m = upstream(store, command)
        _same_run(m, nm["run_id"], command)
        runs[f"{name}_run"] = m["run_id"]
        files[name] = fetch_outputs(store, m, prefix, cache_root())
    im = upstream(store, IPRM)
    runs["ipr_metrics_run"] = im["run_id"]
    files["ipr"] = {**fetch_outputs(store, im, "lake/ipr_metrics/class_", cache_root()),
                    **fetch_outputs(store, im, "lake/ipr_metrics/country_", cache_root())}  # fmt: skip
    return runs, files


def _by_source(files: dict[str, Path]) -> dict[str, Path]:
    return {k.split("/source=")[1].split("/")[0]: p for k, p in files.items() if "/source=" in k}


# ----------------------------------------------------------------------------------------------------- the items


def load_items(files: dict, cards: dict[str, SourceCard], as_of: date, cfg: DetectConfig) -> tuple[list[dict], dict]:
    """Visible, dated items at as_of with their window (w or b), group, ring; and per-source volumes."""
    dc = cfg.documents
    end = as_of_end(as_of)
    w_start = end - timedelta(days=dc.window_days)
    b_start = w_start - timedelta(days=dc.baseline_days)
    groups = {r["item_id"]: r["dedup_group"] for r in read_rows(next(iter(files["dedup"].values())),
                                                                  ["item_id", "dedup_group"])}  # fmt: skip
    tags = {}
    for p in _by_source(files["tags"]).values():
        for r in read_rows(p, ["item_id", "term_groups", "ring_p_core", "ring_p_adjacent", "ring_p_wider_world",
                               "tagger"]):  # fmt: skip
            tags[r["item_id"]] = r
    items, volumes = [], {}
    for source, path in sorted(files["documents"].items()):
        rows = read_rows(path, ["item_id", "source", "family", "observable_at", "observable_basis", "first_seen_at"])
        if not rows:
            continue
        onboarded = min(r["first_seen_at"] for r in rows)
        backlog = [r for r in rows if r["observable_basis"] == "first_sight"
                   and r["first_seen_at"].date() == onboarded.date()]  # fmt: skip
        bset = {r["item_id"] for r in backlog}
        dated = [r for r in rows if r["item_id"] not in bset]
        coverage = min((r["observable_at"] for r in dated), default=None)
        card = cards.get(source)
        vol = {"source": source, "family": rows[0]["family"], "onboarded_at": onboarded, "coverage_start": coverage,
               "backlog_items": len(bset), "window_items": 0, "baseline_items": 0, "_wg": set(),
               "_bg": set()}  # fmt: skip
        for r in dated:
            at = r["observable_at"]
            visible = at <= end and (r["first_seen_at"] <= end or at < onboarded)
            if not visible or at <= b_start:
                continue
            period = "w" if at > w_start else "b"
            t = tags.get(r["item_id"]) or {}
            probs = {k: t.get(f"ring_p_{k}") for k in ("core", "adjacent", "wider_world")}
            ring = item_ring(card, t.get("term_groups") or [], probs)
            grp = groups.get(r["item_id"], r["item_id"])
            items.append({"item_id": r["item_id"], "source": source, "family": r["family"], "ring": ring,
                          "grp": grp, "period": period, "observable_at": at, "first_seen_at": r["first_seen_at"],
                          "term_groups": t.get("term_groups") or [], "tagger": t.get("tagger")})  # fmt: skip
            vol["window_items" if period == "w" else "baseline_items"] += 1
            vol["_wg" if period == "w" else "_bg"].add(grp)
        span_start = max(b_start, coverage) if coverage else w_start
        base_days = max((w_start - span_start).total_seconds() / 86400, 0)
        vol["window_groups"], vol["baseline_groups"] = len(vol.pop("_wg")), len(vol.pop("_bg"))
        vol["window_per_day"] = vol["window_groups"] / dc.window_days
        vol["baseline_per_day"] = vol["baseline_groups"] / base_days if base_days >= 1 else None
        bpd = vol["baseline_per_day"]
        vol["change"] = vol["window_per_day"] / bpd - 1 if bpd else None
        volumes[source] = vol
    return items, volumes


# -------------------------------------------------------------------------------------------------------- clusters


def fit_clusters(
    items: list[dict], emb_paths: dict[str, Path], cfg: DetectConfig, dim: int, kp_rows: dict[str, list[str]]
) -> tuple[dict[str, str], list[dict], dict[str, np.ndarray]]:
    """MiniBatchKMeans on the visible items' embeddings (fitted at as_of only: no future items), each cluster named by
    its keyphrases' class-based TF-IDF. Returns (item -> cluster, cluster rows, item -> vector)."""
    from sklearn.cluster import MiniBatchKMeans

    cc = cfg.documents.clusters
    wanted = {i["item_id"] for i in items}
    ids, blobs = [], []
    for source in sorted(emb_paths):
        for r in read_rows(emb_paths[source], ["item_id", "vector"]):
            if r["item_id"] in wanted:
                ids.append(r["item_id"])
                blobs.append(r["vector"])
    if not ids:
        return {}, [], {}
    vec = from_blobs(blobs, dim).astype(np.float32)
    k = min(cc.k, max(1, len(ids) // 5))
    rng = np.random.default_rng(cc.seed)
    sample = rng.choice(len(ids), min(len(ids), cc.sample), replace=False) if len(ids) > cc.sample else None
    km = MiniBatchKMeans(n_clusters=k, random_state=cc.seed, batch_size=cc.batch, n_init=3)
    km.fit(vec[np.sort(sample)] if sample is not None else vec)
    labels = km.predict(vec)
    assign = {i: f"cl:{int(c):03d}" for i, c in zip(ids, labels, strict=True)}
    fam = {i["item_id"]: i["family"] for i in items}
    terms: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    members: dict[str, set] = defaultdict(set)
    for i, c in assign.items():
        members[c].add(fam.get(i))
        for p in kp_rows.get(i, []):
            terms[c][p] += 1
    rows = []
    df: dict[str, int] = defaultdict(int)
    for c in terms:
        for p in terms[c]:
            df[p] += 1
    n = max(len(terms), 1)
    sizes = defaultdict(int)
    for c in assign.values():
        sizes[c] += 1
    for c in sorted(sizes):
        scored = sorted(((cnt * np.log(1 + n / df[p]), p) for p, cnt in terms[c].items()), reverse=True)
        rows.append({"cluster": c, "size": sizes[c], "label": "; ".join(p for _, p in scored[: cc.name_terms]),
                     "families": sorted(f for f in members[c] if f)})  # fmt: skip
    vectors = dict(zip(ids, vec, strict=True))
    return assign, rows, vectors


# -------------------------------------------------------------------------------------------------- the indicators


def concept_table(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Per concept: groups and families in the window and the baseline, core and wider-world groups."""
    return con.execute(
        """SELECT o.concept, count(DISTINCT i.grp) FILTER (i.period = 'w') AS wg,
                  count(DISTINCT i.grp) FILTER (i.period = 'b') AS bg,
                  count(DISTINCT i.source) FILTER (i.period = 'w') AS ws,
                  list(DISTINCT i.family) FILTER (i.period = 'w') AS wf,
                  list(DISTINCT i.family) FILTER (i.period = 'b') AS bf,
                  list(DISTINCT i.ring) FILTER (i.period = 'w') AS wr,
                  count(DISTINCT i.grp) FILTER (i.period = 'w' AND i.ring = 'core') AS cw,
                  count(DISTINCT i.grp) FILTER (i.period = 'b' AND i.ring = 'core') AS cb,
                  count(DISTINCT i.grp) FILTER (i.period = 'w' AND i.ring = 'wider_world') AS ww,
                  count(DISTINCT i.grp) FILTER (i.period = 'b' AND i.ring = 'wider_world') AS wb
           FROM occ o JOIN items i USING (item_id) GROUP BY o.concept
           HAVING count(DISTINCT i.grp) FILTER (i.period = 'w') > 0 ORDER BY o.concept"""
    ).fetchall()


def indicators(
    items: list[dict],
    occ: list[tuple[str, str]],
    labels: dict[str, str],
    vocab: dict[str, dict],
    backlog_ids: set[str],
    w_start: datetime,
    cfg: DetectConfig,
) -> tuple[list[dict], list[dict]]:
    """new_term, cross_family and cross_ring per concept; low-base surges per concept and family."""
    dc = cfg.documents
    con = duckdb.connect()
    con.register("items", pa.Table.from_pylist([{k: i[k] for k in ("item_id", "source", "family", "ring", "grp",
                                                                   "period")} for i in items]))  # fmt: skip
    occ_schema = pa.schema([("item_id", pa.string()), ("concept", pa.string())])
    con.register("occ", pa.Table.from_pylist([{"item_id": a, "concept": b} for a, b in occ], schema=occ_schema))
    exposure = {r[0]: r[1:] for r in con.execute(
        "SELECT ring, count(DISTINCT grp) FILTER (period = 'w'), count(DISTINCT grp) FILTER (period = 'b') "
        "FROM items GROUP BY ring").fetchall()}  # fmt: skip
    ww_e1, ww_e0 = exposure.get("wider_world", (0, 0))
    rows = []
    for c, wg, bg, ws, wf, bf, wr, cw, cb, ww, wb in concept_table(con):
        kind = c.split(":", 1)[0]
        v = vocab.get(c[3:]) if kind == "kp" else None
        first = v["first_observable_at"] if v else None
        new_term = bool(v and first is not None and first > w_start and v["first_item_id"] not in backlog_ids
                        and wg >= dc.new_term_min_df and ws >= dc.min_sources
                        and set(wf or []) & set(dc.credible_families))  # fmt: skip
        cross_family = len(wf or []) >= dc.cross_family_min and len(bf or []) <= dc.cross_family_max_before
        rows.append({"concept": c, "kind": kind, "label": labels.get(c, c.split(":", 1)[1]), "window_groups": wg,
                     "baseline_groups": bg, "window_sources": ws, "window_families": sorted(wf or []),
                     "baseline_families": sorted(bf or []), "window_rings": sorted(wr or []), "core_window": cw,
                     "core_baseline": cb, "wider_window": ww, "wider_baseline": wb, "first_observable_at": first,
                     "new_term": new_term, "cross_family": bool(cross_family)})  # fmt: skip
    # cross-ring: rising in wider-world items, and in core items for the first time
    p, ratio = stats.poisson_rate_test([r["wider_window"] for r in rows], [ww_e1] * len(rows),
                                       [r["wider_baseline"] for r in rows], [ww_e0] * len(rows))  # fmt: skip
    p = np.where(np.array([r["wider_window"] >= dc.min_items and r["core_window"] > 0 and r["core_baseline"] == 0
                           for r in rows], dtype=bool), p, np.nan)  # fmt: skip
    h = stats.holm(p, [r["kind"] for r in rows])
    for r, pv, rv, hv in zip(rows, p, ratio, h, strict=True):
        r["cross_ring_p"], r["cross_ring_ratio"], r["cross_ring_p_holm"] = _f(pv), _f(rv), _f(hv)
        r["cross_ring"] = bool(np.isfinite(hv) and hv < dc.alpha and rv >= dc.surge_min_ratio)
    # low-base surges per concept and family
    fam_e = {r[0]: r[1:] for r in con.execute(
        "SELECT family, count(DISTINCT grp) FILTER (period = 'w'), count(DISTINCT grp) FILTER (period = 'b') "
        "FROM items GROUP BY family").fetchall()}  # fmt: skip
    srows = []
    for c, fam, wg, bg, ws in con.execute(
        "SELECT o.concept, i.family, count(DISTINCT i.grp) FILTER (i.period = 'w'), "
        "count(DISTINCT i.grp) FILTER (i.period = 'b'), count(DISTINCT i.source) FILTER (i.period = 'w') "
        "FROM occ o JOIN items i USING (item_id) GROUP BY ALL HAVING count(DISTINCT i.grp) FILTER (i.period = 'w') "
        f">= {int(dc.min_items)} ORDER BY 1, 2"
    ).fetchall():  # fmt: skip
        e1, e0 = fam_e.get(fam, (0, 0))
        expected = bg * e1 / e0 if e0 else None
        srows.append({"concept": c, "kind": c.split(":", 1)[0], "family": fam, "window_groups": wg,
                      "baseline_groups": bg, "window_exposure": e1, "baseline_exposure": e0, "window_sources": ws,
                      "expected": expected})  # fmt: skip
    if srows:
        p, ratio = stats.poisson_rate_test([s["window_groups"] for s in srows], [s["window_exposure"] for s in srows],
                                           [s["baseline_groups"] for s in srows],
                                           [s["baseline_exposure"] for s in srows])  # fmt: skip
        ok = np.array([s["baseline_exposure"] >= dc.surge_min_baseline_items and s["expected"] is not None
                       and s["expected"] <= dc.surge_max_expected for s in srows], dtype=bool)  # fmt: skip
        p = np.where(ok, p, np.nan)
        h = stats.holm(p, [f"{s['kind']}|{s['family']}" for s in srows])
        for s, pv, rv, hv in zip(srows, p, ratio, h, strict=True):
            s["p"], s["ratio"], s["p_holm"] = _f(pv), _f(rv), _f(hv)
            s["surge"] = bool(np.isfinite(hv) and hv < dc.alpha and rv >= dc.surge_min_ratio)
    return rows, srows


def _f(v) -> float | None:
    return float(v) if v is not None and np.isfinite(v) else None


def keyphrase_pairs(items: list[dict], kp_rows: dict[str, list[str]], cfg: DetectConfig) -> list[dict]:
    """Two keyphrases of one document: together for the first time in the window, each already seen in the baseline,
    or with their lift at least doubled. Counts are groups."""
    dc = cfg.documents
    con = duckdb.connect()
    con.register("items", pa.Table.from_pylist([{k: i[k] for k in ("item_id", "source", "grp", "period")}
                                                for i in items]))  # fmt: skip
    occ = [{"item_id": i, "p": p} for i, ps in kp_rows.items() for p in ps]
    con.register("kp", pa.Table.from_pylist(occ, schema=pa.schema([("item_id", pa.string()), ("p", pa.string())])))
    con.execute("CREATE TEMP TABLE o AS SELECT i.*, kp.p FROM kp JOIN items i USING (item_id)")
    n = {r[0]: r[1] for r in con.execute("SELECT period, count(DISTINCT grp) FROM items GROUP BY 1").fetchall()}
    single = {(r[0], r[1]): r[2] for r in con.execute(
        "SELECT p, period, count(DISTINCT grp) FROM o GROUP BY ALL").fetchall()}  # fmt: skip
    # pairs in enough window groups (new and rising), or established in the baseline (fading, D-025)
    rows = con.execute(
        """WITH pairs AS (SELECT x.p AS a, y.p AS b, x.period, x.grp, x.source FROM o x JOIN o y
                          ON x.item_id = y.item_id AND x.p < y.p)
           SELECT * FROM (SELECT a, b, count(DISTINCT grp) FILTER (period = 'w') AS wg,
                                 count(DISTINCT source) FILTER (period = 'w') AS ws,
                                 count(DISTINCT grp) FILTER (period = 'b') AS bg,
                                 count(DISTINCT source) FILTER (period = 'b') AS bs FROM pairs GROUP BY ALL)
           WHERE wg >= ? OR bg >= ? ORDER BY 1, 2""",
        [int(dc.combination_min_items), int(cfg.relationships.fade_min_baseline)],
    ).fetchall()
    out = []
    for a, b, wg, ws, bg, bs in rows:
        s = single.get
        r = _combination("kp", a, b, wg, bg, s((a, "w"), 0), s((b, "w"), 0), s((a, "b"), 0), s((b, "b"), 0),
                         n.get("w", 0), n.get("b", 0), ws)  # fmt: skip
        r["baseline_sources"] = bs
        out.append(r)
    return out


def _combination(scheme, a, b, wg, bg, aw, bw, ab, bb, nw, nb, sources) -> dict:
    with np.errstate(all="ignore"):
        lift_w = wg * nw / (aw * bw) if aw and bw else None
        lift_b = bg * nb / (ab * bb) if ab and bb and bg else None
    return {"combination": f"nc:{scheme}:{a}+{b}", "scheme": scheme, "a": a, "b": b, "window": wg, "baseline": bg,
            "a_baseline": ab, "b_baseline": bb, "a_window": aw, "b_window": bw, "window_sources": sources,
            "lift_window": lift_w, "lift_baseline": lift_b, "_exposure": (nw, nb)}  # fmt: skip


def _lengths(rows: list[dict], w_len: float, b_len: float) -> list[dict]:
    for r in rows:
        r["_exposure"] = (*r["_exposure"], w_len, b_len)
    return rows


def class_pairs(files: dict, as_of: date, cfg: DetectConfig) -> list[dict]:
    """IPC subclass and Nice class pairs on IP RAPID applications, by the month the classes became observable: the
    window is the last complete months before as_of."""
    dc = cfg.documents
    paths = {k.rsplit("/", 1)[1]: p for k, p in files["ipr"].items()}
    if "class_pairs.parquet" not in paths:
        return []
    last = date(as_of.year, as_of.month, 1) - timedelta(days=1)
    w_end = f"{last.year:04d}-{last.month:02d}"

    def shift(y: int, m: int, k: int) -> str:
        t = y * 12 + m - 1 - k
        return f"{t // 12:04d}-{t % 12 + 1:02d}"

    w_start = shift(last.year, last.month, dc.ipr_window_months - 1)
    b_start = shift(last.year, last.month, dc.ipr_window_months + dc.ipr_baseline_months - 1)
    con = duckdb.connect()
    pp, cp = paths["class_pairs.parquet"].as_posix(), paths["class_counts.parquet"].as_posix()
    per = f"CASE WHEN period BETWEEN '{w_start}' AND '{w_end}' THEN 'w' WHEN period >= '{b_start}' AND period < " \
          f"'{w_start}' THEN 'b' END"  # fmt: skip
    counts = {(r[0], r[1], r[2], r[3]): r[4] for r in con.execute(
        f"SELECT scheme, \"right\", \"class\", {per} AS q, sum(applications) FROM read_parquet('{cp}') "
        f"WHERE {per} IS NOT NULL GROUP BY ALL").fetchall()}  # fmt: skip
    rows = con.execute(
        f"""SELECT scheme, "right", class_a, class_b, coalesce(sum(applications) FILTER ({per} = 'w'), 0) AS w,
                   coalesce(sum(applications) FILTER ({per} = 'b'), 0) AS b,
                   coalesce(min(applicant_min) FILTER ({per} = 'w') <> max(applicant_max) FILTER ({per} = 'w'),
                            false) AS two,
                   coalesce(min(applicant_min) FILTER ({per} = 'b') <> max(applicant_max) FILTER ({per} = 'b'),
                            false) AS two_b
            FROM read_parquet('{pp}') WHERE {per} IS NOT NULL GROUP BY ALL
            HAVING w >= {int(dc.combination_min_items)} OR b >= {int(cfg.relationships.fade_min_baseline)}
            ORDER BY 1, 2, 3, 4"""
    ).fetchall()
    # a class's first month: one first seen inside the baseline is new to the scheme (IPC adds subclasses, such as
    # H10D, H10F and H10H in 2025), and a pair with it is a change of classification, not of practice
    sql = f'SELECT scheme, "right", "class", min(period) FROM read_parquet(\'{cp}\') GROUP BY ALL'
    first = {(r[0], r[1], r[2]): r[3] for r in con.execute(sql).fetchall()}
    out = []
    for scheme, right, a, b, w, bg, two, two_b in rows:
        g = {(k, q): counts.get((scheme, right, k, q), 0) for k in (a, b, "*") for q in ("w", "b")}
        r = _combination(scheme, a, b, int(w), int(bg), g[(a, "w")], g[(b, "w")], g[(a, "b")], g[(b, "b")],
                         g[("*", "w")], g[("*", "b")], 2 if two else 1)  # fmt: skip
        r["baseline_sources"] = 2 if two_b else 1
        r["_right"] = right
        r["classes_since"] = max(first.get((scheme, right, a), ""), first.get((scheme, right, b), ""))
        r["new_class"] = r["classes_since"] > b_start
        out.append(r)
    return out


def country_pairs(files: dict, as_of: date, cfg: DetectConfig) -> list[dict]:
    """An applicant country and an IPC subclass or Nice class (IP RAPID; D-025), as a pair: the country's
    applications in the class against its applications and the class's, by the month the classes were observable.
    Schemes `ipc_country` and `nice_country`; a is the country (upper case), b the class."""
    dc, rc = cfg.documents, cfg.relationships
    paths = {k.rsplit("/", 1)[1]: p for k, p in files["ipr"].items()}
    if not rc.jurisdictions or "country_classes.parquet" not in paths:
        return []
    last = date(as_of.year, as_of.month, 1) - timedelta(days=1)

    def shift(k: int) -> str:
        t = last.year * 12 + last.month - 1 - k
        return f"{t // 12:04d}-{t % 12 + 1:02d}"

    w_end, w_start = shift(0), shift(dc.ipr_window_months - 1)
    b_start = shift(dc.ipr_window_months + dc.ipr_baseline_months - 1)
    per = f"CASE WHEN period BETWEEN '{w_start}' AND '{w_end}' THEN 'w' WHEN period >= '{b_start}' AND period < " \
          f"'{w_start}' THEN 'b' END"  # fmt: skip
    path = paths["country_classes.parquet"].as_posix()
    con = duckdb.connect()
    totals = {(r[0], r[1], r[2], r[3], r[4]): r[5] for r in con.execute(
        f"SELECT scheme, \"right\", country, \"class\", {per} AS q, sum(applications) FROM read_parquet('{path}') "
        f"WHERE {per} IS NOT NULL AND (country = '*' OR \"class\" = '*') GROUP BY ALL").fetchall()}  # fmt: skip
    first = {(r[0], r[1], r[2]): r[3] for r in con.execute(
        f"SELECT scheme, \"right\", \"class\", min(period) FROM read_parquet('{path}') WHERE country = '*' "
        "GROUP BY ALL").fetchall()}  # fmt: skip
    rows = con.execute(
        f"""SELECT scheme, "right", country, "class", coalesce(sum(applications) FILTER ({per} = 'w'), 0) AS w,
                   coalesce(sum(applications) FILTER ({per} = 'b'), 0) AS b,
                   coalesce(min(applicant_min) FILTER ({per} = 'w') <> max(applicant_max) FILTER ({per} = 'w'),
                            false),
                   coalesce(min(applicant_min) FILTER ({per} = 'b') <> max(applicant_max) FILTER ({per} = 'b'),
                            false)
            FROM read_parquet('{path}') WHERE {per} IS NOT NULL AND country <> '*' AND "class" <> '*' GROUP BY ALL
            HAVING w >= {int(dc.combination_min_items)} OR b >= {int(rc.fade_min_baseline)} ORDER BY 1, 2, 3, 4"""
    ).fetchall()
    out = []
    for scheme, right, c, k, w, bg, two, two_b in rows:

        def t(cc, kk, q, scheme=scheme, right=right):
            return totals.get((scheme, right, cc, kk, q), 0)

        r = _combination(f"{scheme}_country", c.upper(), k, int(w), int(bg), t(c, "*", "w"), t("*", k, "w"),
                         t(c, "*", "b"), t("*", k, "b"), t("*", "*", "w"), t("*", "*", "b"),
                         2 if two else 1)  # fmt: skip
        r["baseline_sources"] = 2 if two_b else 1
        r["_right"] = right
        r["classes_since"] = first.get((scheme, right, k), "")
        r["new_class"] = r["classes_since"] > b_start
        out.append(r)
    return out


def decide_combinations(rows: list[dict], cfg: DetectConfig) -> None:
    dc, rc = cfg.documents, cfg.relationships
    p = np.full(len(rows), np.nan)
    pf = np.full(len(rows), np.nan)
    ratio = np.full(len(rows), np.nan)
    for n, r in enumerate(rows):
        nw, nb, w_len, b_len = r["_lengths"] = r.pop("_exposure")
        r.pop("_right", None)
        lw, lb = r["lift_window"], r["lift_baseline"]
        if lw is not None and lb:
            ratio[n] = lw / lb
        if r["baseline"] > 0 and nw and nb and r["window"] >= dc.combination_min_items:
            # the pair's rate per group (or application), window against baseline
            p[n] = stats.poisson_rate_test([r["window"]], [nw], [r["baseline"]], [nb])[0][0]
        r["expected_window"] = None
        if lb and nw and r["baseline"] >= rc.fade_min_baseline:
            # fading (D-025): the window's count against the baseline's lift applied to each side's window activity
            r["expected_window"] = lb * (r["a_window"] or 0) * (r["b_window"] or 0) / nw
            pf[n] = stats.poisson_lower([r["window"]], [r["expected_window"]])[0]
    h = stats.holm(p, [r["scheme"] for r in rows])
    hf = stats.holm(pf, [f"{r['scheme']}|fade" for r in rows])
    min_sources = cfg.documents.min_sources
    for r, pv, hv, rv in zip(rows, p, h, ratio, strict=True):
        r["p"], r["p_holm"], r["ratio"] = _f(pv), _f(hv), _f(rv)
        nw, nb, w_len, b_len = r.pop("_lengths")
        r["window_exposure"], r["baseline_exposure"] = nw, nb
        r["exposure_change"] = (nw / w_len) / (nb / b_len) - 1 if nb and w_len and b_len else None
        enough = r["window"] >= dc.combination_min_items and r["window_sources"] >= min_sources
        r["new"] = bool(enough and r["baseline"] == 0 and min(r["a_baseline"], r["b_baseline"])
                        >= dc.combination_min_each_before)  # fmt: skip
        r["rising"] = bool(enough and np.isfinite(hv) and hv < dc.alpha and np.isfinite(rv)
                           and rv >= dc.combination_lift_ratio)  # fmt: skip
    for r, pv, hv, rv in zip(rows, pf, hf, ratio, strict=True):
        r["p_fade"], r["p_fade_holm"] = _f(pv), _f(hv)
        r["fading"] = bool(np.isfinite(hv) and hv < dc.alpha and (r.get("baseline_sources") or 0) >= dc.min_sources
                           and min(r["a_window"] or 0, r["b_window"] or 0) >= rc.fade_min_each_window
                           and (r["expected_window"] or 0) >= rc.fade_min_expected
                           and (not np.isfinite(rv) or rv <= rc.fade_ratio))  # fmt: skip


def novel_items(items: list[dict], vectors: dict[str, np.ndarray], kp_rows: dict[str, list[str]],
                cfg: DetectConfig) -> tuple[list[dict], dict[str, list[str]]]:  # fmt: skip
    """Per family with enough baseline: LocalOutlierFactor fitted on the baseline (one item per group), window items
    scored against it; the novel ones grouped into micro-clusters (cosine, average linkage)."""
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.neighbors import LocalOutlierFactor

    nc = cfg.documents.novelty
    dc = cfg.documents
    out, members = [], {}
    by_family: dict[str, dict[str, list[dict]]] = defaultdict(lambda: {"w": [], "b": []})
    seen = set()
    for i in sorted(items, key=lambda i: (i["observable_at"], i["item_id"])):
        if i["item_id"] in vectors and (i["grp"], i["period"]) not in seen:
            seen.add((i["grp"], i["period"]))
            by_family[i["family"]][i["period"]].append(i)
    rng = np.random.default_rng(dc.clusters.seed)
    for fam in sorted(by_family):
        base, win = by_family[fam]["b"], by_family[fam]["w"]
        if len(base) < nc.min_baseline or not win:
            continue
        if len(base) > nc.baseline_sample:
            base = [base[k] for k in np.sort(rng.choice(len(base), nc.baseline_sample, replace=False))]
        xb = np.vstack([vectors[i["item_id"]] for i in base])
        xw = np.vstack([vectors[i["item_id"]] for i in win])
        lof = LocalOutlierFactor(n_neighbors=min(nc.neighbours, len(base) - 1), novelty=True, metric="cosine")
        lof.fit(xb)
        score = lof.score_samples(xw)
        novel = [(i, s) for i, s in zip(win, score, strict=True) if s < nc.threshold]
        if len(novel) < dc.min_items:
            continue
        xn = np.vstack([vectors[i["item_id"]] for i, _ in novel])
        ac = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average",
                                     distance_threshold=nc.micro_distance)  # fmt: skip
        labels = ac.fit_predict(xn) if len(novel) > 1 else np.zeros(1, dtype=int)
        clusters: dict[int, list] = defaultdict(list)
        for (i, s), lab in zip(novel, labels, strict=True):
            clusters[int(lab)].append((i, s))
        n = 0
        for lab in sorted(clusters, key=lambda k: (-len(clusters[k]), k)):
            ms = clusters[lab]
            srcs = sorted({i["source"] for i, _ in ms})
            grps = {i["grp"] for i, _ in ms}
            if len(grps) < dc.min_items:
                continue
            key = f"nv:{fam}:{n:03d}"
            n += 1
            terms: dict[str, int] = defaultdict(int)
            for i, _ in ms:
                for p in kp_rows.get(i["item_id"], []):
                    terms[p] += 1
            top = sorted(terms.items(), key=lambda t: (-t[1], t[0]))[: dc.clusters.name_terms]
            label = "; ".join(p for p, _ in top)
            out.append({"micro": key, "family": fam, "items": len(ms), "groups": len(grps), "sources": srcs,
                        "label": label, "mean_score": float(np.mean([s for _, s in ms])),
                        "baseline_size": len(base)})  # fmt: skip
            members[key] = [i["item_id"] for i, _ in ms]
    return out, members


# ------------------------------------------------------------------------------------------------------------ run


def measure(store: Store, cfg: DetectConfig, cards: dict[str, SourceCard], dim: int, as_of: date,
            config_hash: str | None = None) -> tuple[str, str, dict]:  # fmt: skip
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        runs, files = inputs(store)
        manifest.params = {"as_of": as_of.isoformat(), **runs}
        tables, counts = build(files, cards, cfg, dim, as_of)
        manifest.params["taggers"] = counts.pop("_taggers")
        prefix = f"measures/documents/as_of={as_of.isoformat()}/"
        with tempfile.TemporaryDirectory(prefix="moria-docs-") as tmp:
            for name, (rows, schema, sort) in sorted(tables.items()):
                write_rows(rows, schema, Path(tmp) / f"{name}.parquet", sort)
                upload(store, manifest, f"{prefix}{name}.parquet", Path(tmp) / f"{name}.parquet")
        manifest.counts = counts
        return "passed", manifest.finish(store, "passed"), counts
    except Exception as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        cause = f"{COMMAND}: {type(e).__name__}: {first[:300]}"
        log.error("%s", cause)
        return "failed", manifest.finish(store, "failed", cause), {"error": cause}


def build(files: dict, cards: dict[str, SourceCard], cfg: DetectConfig, dim: int, as_of: date) -> tuple[dict, dict]:
    dc = cfg.documents
    w_start = as_of_end(as_of) - timedelta(days=dc.window_days)
    items, volumes = load_items(files, cards, as_of, cfg)
    log.info("documents: %d items in the window and baseline", len(items))
    backlog_ids: set[str] = set()
    for source, path in files["documents"].items():
        v = volumes.get(source)
        if v and v["backlog_items"]:
            for r in read_rows(path, ["item_id", "observable_basis", "first_seen_at"]):
                if r["observable_basis"] == "first_sight" and r["first_seen_at"].date() == v["onboarded_at"].date():
                    backlog_ids.add(r["item_id"])
    wanted = {i["item_id"] for i in items}
    kp_rows: dict[str, list[str]] = defaultdict(list)
    for p in _by_source(files["kp"]).values():
        for r in read_rows(p, ["item_id", "phrase"]):
            if r["item_id"] in wanted:
                kp_rows[r["item_id"]].append(r["phrase"])
    vocab_path = next(p for k, p in files["kp"].items() if k.endswith("vocabulary.parquet"))
    vocab = {r["phrase"]: r for r in read_rows(vocab_path, ["phrase", "first_observable_at", "first_item_id"])}
    if files.get("emb") is None:  # term-only (a hindsight run, design §11.3): no embeddings, no clusters
        assign, cluster_rows, vectors = {}, [], {}
    else:
        assign, cluster_rows, vectors = fit_clusters(items, _by_source(files["emb"]), cfg, dim, kp_rows)
    log.info("documents: %d clusters", len(cluster_rows))
    labels = {r["cluster"]: r["label"] for r in cluster_rows}
    occ: list[tuple[str, str]] = []
    for i in items:
        iid = i["item_id"]
        occ += [(iid, f"kp:{p}") for p in kp_rows.get(iid, [])]
        occ += [(iid, f"tg:{g}") for g in i["term_groups"]]
        if iid in assign:
            occ.append((iid, assign[iid]))
    concepts, surges = indicators(items, occ, labels, vocab, backlog_ids, w_start, cfg)
    log.info("documents: %d concepts, %d surge tests", len(concepts), len(surges))
    combos = _lengths(keyphrase_pairs(items, kp_rows, cfg), dc.window_days, dc.baseline_days)
    combos += _lengths(class_pairs(files, as_of, cfg), dc.ipr_window_months, dc.ipr_baseline_months)
    combos += _lengths(country_pairs(files, as_of, cfg), dc.ipr_window_months, dc.ipr_baseline_months)
    decide_combinations(combos, cfg)
    novelty, members = novel_items(items, vectors, kp_rows, cfg) if vectors else ([], {})
    # evidence: the window items behind each concept, combination or micro-cluster that fired
    fired = {c["concept"] for c in concepts if c["new_term"] or c["cross_family"] or c["cross_ring"]}
    fired |= {s["concept"] for s in surges if s.get("surge")}
    pair_keys, fade_keys = {}, {}
    for c in combos:
        if (c["new"] or c["rising"]) and c["scheme"] == "kp":
            pair_keys[c["combination"]] = (c["a"], c["b"])
        if c["fading"] and c["scheme"] == "kp":
            fade_keys[c["combination"]] = (c["a"], c["b"])
    by_item = {i["item_id"]: i for i in items}
    evidence = []
    concept_items: dict[str, set] = defaultdict(set)
    for iid, c in occ:
        if c in fired and by_item[iid]["period"] == "w":
            concept_items[c].add(iid)
    for key, (a, b) in pair_keys.items():
        for iid, ps in kp_rows.items():
            if a in ps and b in ps and by_item[iid]["period"] == "w":
                concept_items[key].add(iid)
    for key, ids in members.items():
        concept_items[key] |= set(ids)
    # a fading pair's evidence: the items that held it, in the baseline and in the window (D-025)
    fade_items: dict[str, set] = defaultdict(set)
    for key, (a, b) in fade_keys.items():
        for iid, ps in kp_rows.items():
            if a in ps and b in ps:
                fade_items[key].add(iid)
    for key in sorted(set(concept_items) | set(fade_items)):
        for iid in sorted(concept_items.get(key, set()) | fade_items.get(key, set())):
            i = by_item[iid]
            evidence.append({"key": key, "item_id": iid, "source": i["source"], "family": i["family"],
                             "ring": i["ring"], "dedup_group": i["grp"], "observable_at": i["observable_at"],
                             "first_seen_at": i["first_seen_at"],
                             "role": "window" if i["period"] == "w" else "baseline"})  # fmt: skip
    vols = [v for _, v in sorted(volumes.items())]
    gi: dict[tuple, list] = defaultdict(lambda: [0, set()])
    for i in items:
        if i["period"] == "w":
            for g in i["term_groups"]:
                slot = gi[(g, i["source"], i["family"])]
                slot[0] += 1
                slot[1].add(i["grp"])
    group_items = [{"group": g, "source": s, "family": f, "items": n, "groups": len(gs)}
                   for (g, s, f), (n, gs) in sorted(gi.items())]  # fmt: skip
    tables = {
        "volumes": (vols, VOLUMES, ("source",)),
        "concepts": (concepts, CONCEPTS, ("concept",)),
        "surges": (surges, SURGES, ("concept", "family")),
        "combinations": (combos, COMBINATIONS, ("combination",)),
        "novelty": (novelty, NOVELTY, ("micro",)),
        "clusters": (cluster_rows, CLUSTERS, ("cluster",)),
        "group_items": (group_items, GROUP_ITEMS, ("group", "source")),
        "assignments": ([{"item_id": i, "cluster": c} for i, c in assign.items()], ASSIGNMENTS, ("item_id",)),
        "evidence": (evidence, EVIDENCE, ("key", "item_id")),
    }
    counts = {
        "items_window": sum(1 for i in items if i["period"] == "w"),
        "items_baseline": sum(1 for i in items if i["period"] == "b"),
        "backlog_items": len(backlog_ids),
        "concepts": len(concepts),
        "new_term": sum(c["new_term"] for c in concepts),
        "cross_family": sum(c["cross_family"] for c in concepts),
        "cross_ring": sum(c["cross_ring"] for c in concepts),
        "low_base_surge": sum(bool(s.get("surge")) for s in surges),
        "combinations_new": sum(c["new"] for c in combos),
        "combinations_rising": sum(c["rising"] for c in combos),
        "combinations_fading": sum(c["fading"] for c in combos),
        "jurisdiction_new": sum(c["new"] for c in combos if c["scheme"].endswith("_country")),
        "jurisdiction_rising": sum(c["rising"] for c in combos if c["scheme"].endswith("_country")),
        "jurisdiction_fading": sum(c["fading"] for c in combos if c["scheme"].endswith("_country")),
        "novel_micro_clusters": len(novelty),
        "clusters": len(cluster_rows),
        "evidence_rows": len(evidence),
        "_taggers": sorted({i["tagger"] for i in items if i["tagger"]}),
    }
    return tables, counts
