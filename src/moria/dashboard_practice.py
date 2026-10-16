"""The dashboard's practice data (D-030): invented candidates, series, documents and dossiers in the private
bundle's shape, so that anyone can see what the private views do without seeing anything private.

Every signal here is invented, with Middle-earth labels that can't be mistaken for findings. They are not made up
wholesale, though: the invented series go through the real detectors (`measures._run`, `detect.series_candidates`),
every candidate through the real ranking and selection (`rank.score_candidates`, `rank.select`, `queue.rescore`,
`queue.sensitivity`), and the bundle through the same builders as a real one (`dashboard.private_bundle`), so the
practice queue behaves as a real queue would and the dashboard's what-if can be checked against it. What is about
Moria itself (its sources, settings, evaluations, document volumes and collection days) is kept from the public
bundle, and the dashboard says so.

Deterministic: the same public bundle and seed give the same bytes. Reads no store; writes
`dashboard/data/practice.json`.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from . import detect as det
from .artefacts import CHECKS
from .config import DetectConfig, ReviewConfig
from .dashboard import SCHEMA, private_bundle, queue_part, ranking_part, scan_part
from .dossier import summary_line
from .measures import Series, _run, period_index
from .queue import choose, rescore, sensitivity
from .rank import VIEWS, score_candidates, select, view_scores
from .records import canonical_json

PRACTICE_PATH = "dashboard/data/practice.json"
SEED = 20261015
AUTHOR = "practice: invented (no model was asked)"

# practice sources: (family, ring, frequency, first year)
SERIES_SOURCES = {
    "practice_ip_filings": ("ipa_internal", "core", "M", 2014),
    "practice_research": ("research", "adjacent", "A", 2000),
    "practice_trade": ("statistics", "adjacent", "Q", 2006),
    "practice_world": ("statistics", "wider_world", "M", 2014),
}
LABELS = {
    "practice_ip_filings": [
        "Trade marks filed for lantern oils",
        "Patents for mithril alloys",
        "Designs registered for carved doors",
        "Plant breeder's rights for pipe-weed varieties",
        "Patents for mine ventilation",
        "Trade marks for ale and mead",
        "Patents for ring-forging methods",
        "First-time applicants from the Shire",
        "Applications from Erebor",
        "Designs for beacon towers",
        "Patents for eagle-borne logistics",
        "Trade marks for elven cloaks",
        "Patents for stone-cutting saws",
        "Applications from Dale",
        "Patents for map-making instruments",
        "Trade marks for second breakfasts",
        "Patents for everlasting torches",
        "Designs for hobbit-hole doors",
        "Patents for rope that never frays",
        "Applications from the Iron Hills",
        "Trade marks for lembas bread",
        "Patents for seeing-stone optics",
        "Designs for mithril mail",
        "Patents for dragon-proof vaults",
    ],
    "practice_research": [
        "Research on deep-rock acoustics",
        "Research on mithril metallurgy",
        "Studies of ent ecology",
        "Research on lantern photonics",
        "Studies of rune cryptography",
        "Research on tunnel engineering",
        "Studies of dragon-fire chemistry",
        "Research on underground hydrology",
        "Studies of moth-borne messaging",
        "Research on palantír optics",
        "Studies of hobbit nutrition",
        "Research on cave-lichen biology",
        "Studies of beacon networks",
        "Research on dwarven automata",
        "Studies of river-barrel logistics",
        "Research on forge emissions",
        "Studies of elvish linguistics",
        "Research on avalanche prediction",
        "Studies of mushroom farming",
        "Research on gemstone synthesis",
    ],
    "practice_trade": [
        "Exports of worked silver",
        "Imports of iron ore from the Iron Hills",
        "Charges for the use of IP: Rohan",
        "Royalties received from Gondor",
        "Exports of pipe-weed",
        "Imports of elven wine",
        "Exports of lanterns",
        "Charges for the use of IP: Dale",
        "Royalties paid to Erebor",
        "Exports of rope",
        "Imports of dragon-scale",
        "Exports of maps",
        "Charges for the use of IP: the Shire",
        "Imports of mithril",
        "Exports of ale",
        "Royalties received from Lake-town",
    ],
    "practice_world": [
        "Population of the Shire",
        "Price of pipe-weed",
        "Days of rain in Rivendell",
        "Ships leaving the Grey Havens",
        "Orc sightings near the Misty Mountains",
        "Harvest yields in the Westfarthing",
        "Wages of hobbit gardeners",
        "Travellers on the East Road",
        "Price of a pony in Bree",
        "Beacons lit in Gondor",
        "Mail carried by eagles",
        "Ale brewed in the Green Dragon",
        "Firework orders for birthday parties",
        "Ferries at Bucklebury",
        "Fish caught in the Long Lake",
        "Wood cut in the Old Forest",
    ],
}
REGIONS = ("the Shire", "Erebor", "all of Middle-earth")
# the patterns the series are drawn from, in the order the labels take them
PATTERNS = ["rise", "accelerate", "spike", "fall", "flat", "rise", "accelerate", "shift", "spike", "flat", "fall",
            "rise"]  # fmt: skip

DOC_SOURCES = {"practice_news": ("news", "wider_world"), "practice_policy": ("policy", "adjacent"),
               "practice_legal": ("legal", "core")}  # fmt: skip
CONCEPTS = [
    ("lantern-fuel patents", ["new_term"]),
    ("eagle delivery; trade marks", ["new_combination"]),
    ("mithril recycling", ["new_term", "cross_family"]),
    ("ent forestry; carbon credits", ["new_combination"]),
    ("seeing-stones; data privacy", ["new_combination", "cross_ring"]),
    ("ring registry", ["new_term"]),
    ("dragon insurance", ["low_base_surge"]),
    ("beacon network standards", ["cross_family"]),
    ("Shire food labelling", ["new_term"]),
    ("dwarf-made automata; inventorship", ["new_combination", "cross_ring"]),
    ("elven rope designs", ["low_base_surge"]),
    ("palantír licensing", ["new_term", "cross_family"]),
    ("hobbit-hole architecture", ["cross_family"]),
    ("moth messaging networks", ["new_term"]),
    ("Gondor seal registry review", ["new_term", "cross_ring"]),
    ("counterfeit lembas", ["low_base_surge"]),
    ("mushroom farming rights", ["new_combination"]),
    ("forge emissions; green metals", ["new_combination"]),
    ("wizard fireworks safety", ["new_term"]),
    ("river-barrel shipping; insurance", ["new_combination"]),
    ("rune-based passwords", ["new_term", "cross_ring"]),
    ("pony rental platforms", ["low_base_surge"]),
    ("Bree innkeepers' trade names", ["cross_family"]),
    ("dwarven apprenticeships", ["new_term"]),
    ("Rohan horse breeding rights", ["new_combination"]),
    ("lighthouse beacons; open standards", ["cross_family"]),
    ("lake-town fishing quotas", ["low_base_surge"]),
    ("mithril supply chains", ["new_term", "cross_family"]),
    ("hobbit cooperative brands", ["new_combination"]),
    ("Grey Havens shipping data", ["new_term"]),
]
HEADLINES = {
    "practice_news": [
        "Dwarves of the Iron Hills report record finds",
        "Hobbit start-ups rush to protect their blends",
        "Eagles to carry parcels across the Misty Mountains",
        "Bree innkeeper wins naming dispute",
        "Lake-town merchants back a new trading guild",
        "Rivendell opens its library to scholars",
        "A wizard's fireworks spark a copycat trade",
        "Rohan horse-breeders register a new line",
    ],
    "practice_policy": [
        "Council of Elrond opens consultation on ring safety",
        "Gondor reviews its seal registry",
        "Shire mayor proposes labelling rules for second breakfasts",
        "Dale consults on lantern standards",
        "Erebor sets out a plan for mithril recycling",
        "The Grey Havens publish a shipping strategy",
    ],
    "practice_legal": [
        "Court rules a dragon cannot be named as an inventor",
        "Erebor Mining Co v Smaug: who owns the hoard",
        "Tribunal hears dispute over a counterfeit elven brooch",
        "Appeal decided on palantír licensing terms",
    ],
}
APPLICANTS = ["The Lonely Mountain Trading Company", "Gamgee Gardens", "Iron Hills Smelting", "Dale Lantern Works",
              "Took and Sons", "Lake-town Shipwrights", "Rivendell Scriptorium", "Brandybuck Ferries"]  # fmt: skip
PATHWAYS = ("P1", "P2", "P3", "P4", "P5", "P6")


class _NoStore:
    """The practice data reads nothing: a store with no manifests."""

    def list(self, prefix: str) -> list[str]:
        return []

    def get(self, key: str) -> bytes:
        raise KeyError(key)


def _shape(pattern: str, n: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n, dtype=float)
    base = rng.uniform(80, 400)
    noise = rng.normal(0, base * 0.025, n)
    if pattern == "rise":
        y = base * np.exp(t * rng.uniform(0.012, 0.03))
    elif pattern == "fall":
        y = base * np.exp(-t * rng.uniform(0.01, 0.022))
    elif pattern == "accelerate":
        k = int(n * 0.7)
        y = base * np.exp(np.where(t < k, t * 0.004, k * 0.004 + (t - k) * rng.uniform(0.05, 0.08)))
    elif pattern == "spike":
        y = base * np.exp(t * 0.003)
        y[-1] *= rng.uniform(1.6, 2.2)
    elif pattern == "shift":
        y = base * np.where(t >= n - 6, rng.uniform(1.4, 1.7), 1.0)
    else:
        y = np.full(n, base)
    return np.maximum(y + noise, 1.0)


def invent_series(rng: np.random.Generator, as_of: date) -> dict[str, Series]:
    out: dict[str, Series] = {}
    for source, (family, ring, kind, start) in SERIES_SOURCES.items():
        first = period_index(kind, date(start, 1, 1))
        last = period_index(kind, as_of) - 1
        n = last - first + 1
        for k, label in enumerate(LABELS[source]):
            for j, region in enumerate(REGIONS):
                values = _shape(PATTERNS[(3 * k + j) % len(PATTERNS)], n, rng)
                scope = "world" if j == 2 and source != "practice_ip_filings" else "au"
                sid = f"{source}|all|{k:02d}{j}|{scope}"  # one test family per source, as a dataflow is
                meta = {"label": f"{label} ({region})", "unit": "number", "scope": scope, "dimensions": "{}",
                        "family": family, "rings": [ring]}  # fmt: skip
                out[sid] = Series(
                    sid, source, kind, meta, {first + i: round(float(v), 3) for i, v in enumerate(values)}
                )
    return out


def invent_documents(rng: np.random.Generator, as_of: date, cfg: DetectConfig) -> tuple[list[dict], dict[str, dict]]:
    """Weak signals from invented documents, and class pairings from invented IP filings."""
    end = datetime(as_of.year, as_of.month, as_of.day, tzinfo=UTC)
    cands, docs = [], {}
    n_item = 0
    for c, (label, fired) in enumerate(CONCEPTS):
        k = int(rng.integers(3, 11))
        srcs = list(DOC_SOURCES) if c % 3 else ["practice_news", "practice_policy"]
        items = []
        for i in range(k):
            src = srcs[i % len(srcs)]
            family, ring = DOC_SOURCES[src]
            n_item += 1
            iid = f"practice-item-{n_item:04d}"
            at = end - timedelta(days=int(rng.integers(1, cfg.documents.window_days)), hours=int(rng.integers(0, 23)))
            title = HEADLINES[src][int(rng.integers(0, len(HEADLINES[src])))]
            items.append({"item_id": iid, "source": src, "family": family, "ring": ring, "observable_at": at,
                          "dedup_group": iid, "role": "window"})  # fmt: skip
            docs[iid] = {"source": src, "family": family, "doc_type": "practice", "title": f"{title} (practice)",
                         "url": None, "outlet": src, "event_at": at.date().isoformat()}  # fmt: skip
        groups = len(items)
        numbers: dict = {}
        for d in fired:
            if d == "new_term":
                numbers[d] = {"window": groups, "baseline": 0, "sources": len({e["source"] for e in items})}
            elif d == "new_combination":
                numbers[d] = {"a_baseline": int(rng.integers(3, 30)), "b_baseline": int(rng.integers(3, 30)),
                              "baseline": 0, "window": groups, "new": True, "rising": False, "scheme": "kp",
                              "lift_ratio": None, "p_holm": None}  # fmt: skip
            elif d == "cross_family":
                numbers[d] = {
                    "baseline_families": ["research"],
                    "window_families": sorted({e["family"] for e in items}),
                }
            elif d == "cross_ring":
                numbers[d] = {"baseline_rings": ["wider_world"], "window_rings": sorted({e["ring"] for e in items})}
            elif d == "low_base_surge":
                exp = round(float(rng.uniform(0.3, 1.5)), 2)
                numbers[d] = {"practice_news": {"window": groups, "expected": exp, "ratio": round(groups / exp, 2),
                                                "p_holm": round(float(rng.uniform(1e-5, 0.01)), 6)}}  # fmt: skip
        key = f"kp:{label}" if len(fired) == 1 and fired[0] != "new_combination" else f"nc:kp:{label}"
        kind = "combination" if "new_combination" in fired else "concept"
        cands.append(det._doc_candidate(kind, key, label, fired, numbers, items, cfg, as_of))
    # pairings of classes in invented IP filings (no items: the applications sit in the dossier, as for IP RAPID)
    for k, (a, b) in enumerate([("M1TH", "R1NG"), ("L4MP", "0IL5"), ("D00R", "ST0N"), ("ALE5", "MEAD"),
                                ("E4GL", "P0ST"), ("R0PE", "ELF5")]):  # fmt: skip
        window, baseline = int(rng.integers(6, 20)), int(rng.integers(0, 4))
        scheme = "ipc_country" if k % 2 else "ipc"
        name = "jurisdiction_shift" if scheme == "ipc_country" else "new_combination"
        nums = {name: {"a_baseline": int(rng.integers(40, 900)), "b_baseline": int(rng.integers(20, 300)),
                       "baseline": baseline, "window": window, "new": baseline == 0, "rising": baseline > 0,
                       "lift_ratio": round(float(rng.uniform(3, 9)), 3), "scheme": scheme,
                       "p_holm": round(float(rng.uniform(1e-6, 0.004)), 8)}}  # fmt: skip
        cands.append({"subject_kind": "combination", "subject": f"nc:{scheme}:{a}+{b}",
                      "label": f"Class {a} + Class {b} (practice)", "type": "weak_signal", "detectors": [name],
                      "numbers": nums, "strength": float(window), "direction": 1, "sources": ["practice_ip_filings"],
                      "families": ["ipa_internal"], "rings": ["core"], "scope": "AUS", "n_items": window,
                      "n_sources": 1, "window_start": None, "window_end": as_of.isoformat(), "_evidence": [],
                      "_items": []})  # fmt: skip
    return cands, docs


def _artefacts(c: dict, rng: np.random.Generator) -> dict:
    """Plausible artefact outcomes: documents from sources too new for a baseline are flagged, as in a real scan."""
    out = dict.fromkeys(CHECKS, "n/a")
    out["ingestion"] = "pass"
    if c["subject_kind"] == "series":
        out["source_break"] = "pass"
        out["coverage"] = "flag" if rng.random() < 0.08 else "pass"
    elif c["sources"] != ["practice_ip_filings"]:
        out["source_break"] = "flag" if rng.random() < 0.55 else "pass"
        out["coverage"] = "flag" if rng.random() < 0.4 else "pass"
        out["duplicate"] = "pass"
        out["news_cycle"] = "flag" if rng.random() < 0.08 else "pass"
    out["flags"] = [k for k in CHECKS if out[k] == "flag"]
    out["clean"] = not out["flags"]
    out["details"] = "{}"
    return out


def _suggestion(cid: str, rng: np.random.Generator) -> dict:
    p = {pid: round(float(rng.uniform(0.25, 0.75)), 4) for pid in PATHWAYS}
    top = max(p, key=lambda k: (p[k], k))
    choice = lambda opts: {o: round(float(v), 4) for o, v in zip(opts, rng.dirichlet(np.ones(len(opts))), strict=True)}  # noqa: E731
    out = {"candidate_id": cid, "author": AUTHOR, "pathways": canonical_json(p), "pathway_top": top,
           "pathway_p": p[top],
           "pathway_strength": p[top], "error": None}  # fmt: skip
    for name, opts in (("order", ("1", "2", "3")), ("origin", ("political", "economic", "social", "technological",
                       "legal", "environmental")), ("horizon", ("h1", "h2", "h3")),
                       ("stance", ("opportunity", "threat", "both")),
                       ("impact", ("low", "medium", "high"))):  # fmt: skip
        d = choice(opts)
        out[name] = canonical_json(d)
        out[f"{name}_top"] = max(d, key=lambda k: (d[k], k))
    out["impact_value"] = {"low": 0.2, "medium": 0.5, "high": 0.9}[out["impact_top"]]
    return out


def _dossier(c: dict, r: dict, art: dict, items: list[dict], docs: dict, rng: np.random.Generator,
             as_of: date, baseline_trends: dict) -> dict:  # fmt: skip
    from .dossier import checklist

    nums = json.loads(c["numbers"])
    extra = [{"check": "administrative", "outcome": "pass", "detail": "no recorded administrative cause"}]
    if r.get("known_trend"):
        extra.append({"check": "known_trend", "outcome": "flag" if r["known_trend_match"] else "pass",
                      "detail": f"nearest {r['known_trend']} (practice), "
                                f"similarity {r['known_trend_sim']:.2f}"})  # fmt: skip
    d = {"dossier_version": "practice", "candidate_id": c["candidate_id"], "as_of": as_of.isoformat(),
         "label": c["label"], "subject": c["subject"], "subject_kind": c["subject_kind"], "type": c["type"],
         "direction": c["direction"], "views": list(c["views"]), "ring": r["ring"], "ring_basis": r["ring_basis"],
         "scope": c["scope"], "sources": c["sources"], "families": c["families"], "corroboration": c["corroboration"],
         "window": {"start": c["window_start"], "end": c["window_end"]}, "detectors": nums,
         "summary": summary_line(c, nums), "related": [], "counter_evidence": [], "examples": [],
         "flags": list(r["flags"]), "notes": [], "runs": {"practice": "invented data, no runs"},
         "limits": ["practice data: invented, to show what a dossier holds"]}  # fmt: skip
    if items:
        rows = [{**{k: i[k] for k in ("item_id", "source", "family", "role")}, "title": docs[i["item_id"]]["title"],
                 "url": None, "outlet": i["source"], "doc_type": "practice", "event_at": None,
                 "observable_at": i["observable_at"].isoformat(timespec="seconds"), "copies": 1}
                for i in items]  # fmt: skip
        d["evidence"] = {"items": rows[:10], "groups": len(rows), "items_total": len(rows)}
        months = []
        y, m = as_of.year, as_of.month
        for _ in range(27):
            months.append(f"{y:04d}-{m:02d}")
            y, m = (y, m - 1) if m > 1 else (y - 1, 12)
        months.reverse()
        counts = Counter(i["observable_at"].strftime("%Y-%m") for i in items)
        vals = [float(counts.get(p, 0)) + (float(rng.integers(0, 2)) if k < 24 and rng.random() < 0.15 else 0.0)
                for k, p in enumerate(months)]  # fmt: skip
        d["chart"] = {"frequency": "M", "shown": "de-duplicated items holding the concept", "periods": months,
                      "values": vals, "baseline_groups": int(sum(vals[:-3]))}  # fmt: skip
    elif c["subject_kind"] == "combination":
        n = int(c["n_items"])
        d["evidence"] = {"applications": {"status": "ok", "applications": n, "applicants": int(rng.integers(3, 8)),
                                          "filed_before_period": int(rng.integers(0, 2)), "period": "the window",
                                          "release": as_of.isoformat(), "sample": [
            {"application_number": f"PRACTICE-{k:04d}", "right": "patent", "title": t, "filed": as_of.isoformat(),
             "applicants": [APPLICANTS[int(rng.integers(0, len(APPLICANTS)))]], "classes_observable": None}
            for k, t in enumerate(["LANTERN WITH EVERLASTING FLAME", "ROPE THAT UNTIES ON COMMAND",
                                   "VAULT DOOR PROOF AGAINST DRAGONS"], 1)]}}  # fmt: skip
    else:
        d["evidence"] = {"series": [{"series_id": c["subject"], "role": "subject", "source": c["sources"][0],
                                     "last_period": c["window_end"], "last_value": None}]}  # fmt: skip
    kt = r.get("known_trend")
    d["known_trend"] = ({"id": kt, "name": baseline_trends.get(kt, "?"), "similarity": r["known_trend_sim"],
                         "match": r["known_trend_match"], "status": "confirmed"} if kt else None)  # fmt: skip
    d["territories"] = {"top": r.get("territory_top"), "similarity": r.get("territory_sim"), "terms": []}
    d["checklist"] = checklist(c, art, nums, extra)
    d["history"] = [{"as_of": (as_of - timedelta(days=7 * k)).isoformat(), "present": bool(rng.random() < 0.7),
                     "type": c["type"], "strength": round(c["strength"] * float(rng.uniform(0.6, 1.0)), 4),
                     "detectors": list(c["detectors"])} for k in (1, 2, 3)]  # fmt: skip
    d["rank"] = {k: r.get(k) for k in ("shortlist_rank", "shortlist_view", "shortlist_pass", "strength_pct",
                                       "breadth", "lead", "novelty", "scope_factor", "type_factor", "flag_factor",
                                       "context_factor", "score_early_warning", "score_strategic")}  # fmt: skip
    return d


def practice_bundle(public: dict, review: ReviewConfig, detect_cfg: DetectConfig, seed: int = SEED) -> dict:
    as_of = date.fromisoformat(public["as_of"])
    rng = np.random.default_rng(seed)
    series = invent_series(rng, as_of)
    # the real detectors on the invented series
    rows, div, scounts, hrows, crows, _ = _run(dict(series), detect_cfg, as_of)
    found = det.series_candidates(rows, div, detect_cfg, hrows, crows)
    docs_c, docs = invent_documents(rng, as_of, detect_cfg)
    cands, evidence = [], []
    for c in found + docs_c:
        cid = det.candidate_id(c["subject"])
        c["corroboration"] = det.corroboration(c)
        for kind, ref, source, family, role in c.pop("_evidence"):
            evidence.append({"candidate_id": cid, "kind": kind, "ref": ref, "source": source, "family": family,
                             "ring": None, "dedup_group": None, "observable_at": None, "role": role})  # fmt: skip
        for e in c.pop("_items", []) or []:
            evidence.append({"candidate_id": cid, "kind": "item", "ref": e["item_id"], "source": e["source"],
                             "family": e["family"], "ring": e["ring"], "dedup_group": e["dedup_group"],
                             "observable_at": e["observable_at"], "role": "window"})  # fmt: skip
        c.setdefault("n_sources", len(c["sources"]))
        c.update(candidate_id=cid, as_of=as_of, numbers=canonical_json(c["numbers"]), views=det.VIEWS[c["type"]])
        c.setdefault("redundancy_group", None)
        cands.append(c)
    sizes = Counter(c["redundancy_group"] for c in cands if c["redundancy_group"])
    for c in cands:
        c["redundancy_size"] = sizes[c["redundancy_group"]] if c["redundancy_group"] else 1
    arts = {c["candidate_id"]: {"candidate_id": c["candidate_id"], **_artefacts(c, rng)} for c in cands}
    flags = {cid: a["flags"] for cid, a in arts.items()}
    meta = {sid: {"source": s.source, "label": s.meta["label"], "dims": {}, "scope": s.meta["scope"]}
            for sid, s in series.items()}  # fmt: skip
    # the real ranking: components, factors, scores; invented known trends and territories, applied as rank does
    ranked = score_candidates(cands, evidence, flags, meta, {}, None, None, {}, review, as_of)
    trends = [t["id"] for t in public["config"]["known_trends"]]
    territories = [t["id"] for t in public["config"]["territories"]]
    rc = review.rank
    for r in sorted(ranked, key=lambda r: r["candidate_id"]):
        r["known_trend"] = trends[int(rng.integers(0, len(trends)))]
        r["known_trend_sim"] = round(float(rng.uniform(0.5, 0.74)), 4)
        r["known_trend_match"] = r["known_trend_sim"] >= rc.known_trend_sim
        if r["known_trend_match"]:
            r["novelty"] *= rc.known_trend_factor
        r["territory_top"] = territories[int(rng.integers(0, len(territories)))]
        r["territory_sim"] = round(float(rng.uniform(0.5, 0.7)), 4)
        view_scores(r, review)
    picks = select(ranked, rc.shortlist, review.queue, {v: f"score_{v}" for v in VIEWS})
    place = {p["candidate_id"]: p for p in picks}
    for r in ranked:
        p = place.get(r["candidate_id"])
        r.update(shortlisted=p is not None, shortlist_rank=p and p["rank"], shortlist_view=p and p["view"],
                 shortlist_pass=p and p["pass"])  # fmt: skip
    # the queue and its sensitivity, as `moria queue` picks them
    short = [dict(r) for r in ranked if r["shortlisted"]]
    sug = {
        r["candidate_id"]: _suggestion(r["candidate_id"], rng) for r in sorted(short, key=lambda r: r["candidate_id"])
    }
    rescore(short, sug, review, confirmed={})
    qpicks = choose(short, review)
    sens = sensitivity(short, sug, review, {p["candidate_id"] for p in qpicks}, {})
    by = {r["candidate_id"]: r for r in ranked}
    queue = [{"candidate_id": p["candidate_id"], "queue_rank": p["rank"], "view": p["view"], "pass": p["pass"],
              **{k: by[p["candidate_id"]][k] for k in ("type", "ring", "source", "flags")}}
             for p in qpicks]  # fmt: skip
    # the register: the queue, and a few invented reviews to show how statuses look
    reviews = {2: ("investigating", "Practice note: worth a closer look at the filings behind it."),
               5: ("validated", "Practice note: a real shift, with a clear pathway (P1)."),
               9: ("parked", "Practice note: no evident pathway to the IP system yet."),
               14: ("rejected", "Practice note: an artefact of a new source.")}  # fmt: skip
    register = {}
    events = []
    for q in queue:
        st = {"signal_id": q["candidate_id"], "status": "candidate", "queued": [{}], "machine": {}, "review": None,
              "reviews": 0, "history": []}  # fmt: skip
        events += [{"kind": "queued"}, {"kind": "machine_pathways"}, {"kind": "machine_interpretation"}]
        if q["queue_rank"] in reviews:
            status, note = reviews[q["queue_rank"]]
            st.update(status=status, reviews=1, review={"author": "practice reviewer", "at": as_of.isoformat(),
                                                        "status": status, "notes": note, "pathways": []})  # fmt: skip
            events.append({"kind": "review"})
        register[q["candidate_id"]] = st
    # dossiers for the shortlist
    items_by: dict[str, list[dict]] = defaultdict(list)
    for e in evidence:
        if e["kind"] == "item":
            items_by[e["candidate_id"]].append({**e, "item_id": e["ref"]})
    cand_by = {c["candidate_id"]: c for c in cands}
    trend_names = {t["id"]: t["name"] for t in public["config"]["known_trends"]}
    dossiers = {r["candidate_id"]: _dossier(cand_by[r["candidate_id"]], r, arts[r["candidate_id"]],
                                            items_by.get(r["candidate_id"], []), docs, rng, as_of, trend_names)
                for r in sorted(ranked, key=lambda r: r["candidate_id"]) if r["shortlisted"]}  # fmt: skip
    checks = Counter(ck["check"] for d in dossiers.values() for ck in d["checklist"] if ck["outcome"] == "flag")
    inp = SimpleNamespace(
        store=_NoStore(), as_of=as_of, ranked=ranked, queue=queue, sensitivity=sens, suggestions=list(sug.values()),
        candidates=cand_by, evidence=_group(evidence), artefacts=arts, measures=rows,
        series_m={"counts": scounts}, docs_m={"counts": {}},
        detect_m={"counts": {"redundancy_groups": len(sizes),
                             "redundant_candidates": sum(n - 1 for n in sizes.values())}},
        dossier_m={"counts": {f"check_{k}": v for k, v in checks.items()}},
        pathways_m={"params": {"author": AUTHOR, "questions": "practice"}}, events=events, register=register,
    )  # fmt: skip
    pub = dict(public)
    pub["runs"] = {"practice": {"run_id": f"practice-{seed}", "commit": "", "dirty": False}}
    pub["scan"] = scan_part(inp, detect_cfg)
    pub["ranking"] = ranking_part(inp)
    q = queue_part(inp, review)
    q["pathways"]["evaluation"] = public["queue"]["pathways"].get("evaluation")  # the real model's real check
    pub["queue"] = q
    regs = list(register.values())
    pub["funnel"] = {"sources": len(SERIES_SOURCES) + len(DOC_SOURCES), "documents": len(docs),
                     "series": len(rows), "candidates": len(ranked),
                     "clean": sum(1 for a in arts.values() if a["clean"]), "shortlist": len(picks),
                     "queue": len(queue), "reviewed": sum(1 for s in regs if s["review"])}  # fmt: skip
    pub["history"] = [{"as_of": (as_of - timedelta(days=7 * k)).isoformat(),
                       "candidates": int(len(ranked) * (1 - 0.06 * k)),
                       "types": {t: int(pub["scan"]["types"][t]["candidates"] * (1 - 0.06 * k)) for t in det.TYPES},
                       "clean": int(pub["funnel"]["clean"] * (1 - 0.06 * k)), "shortlist": len(picks),
                       "queue": len(queue)} for k in (5, 4, 3, 2, 1, 0)]  # fmt: skip
    bundle, _ = private_bundle(inp, pub, detect_cfg, loaded=series, docs=docs, dossiers=dossiers, kind="practice")
    bundle["schema"] = SCHEMA
    bundle["practice"] = {"seed": seed, "note": "Every signal, number and title in the candidates, series, items, "
                          "dossiers, suggestions and register is invented. The sources, settings, evaluations, "
                          "document volumes and collection days are the real scan's."}  # fmt: skip
    return bundle


def _group(evidence: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for e in evidence:
        out[e["candidate_id"]].append(e)
    return out


def encode(bundle: dict) -> bytes:
    return (json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str) + "\n").encode()


def floor_check(bundle: dict) -> None:
    """The practice bundle holds no real candidate: every label is from the invented lists."""
    allowed = {f"{lab} ({r})" for labs in LABELS.values() for lab in labs for r in REGIONS} | {c for c, _ in CONCEPTS}
    for c in bundle["candidates"]:
        if c["label"] not in allowed and not c["label"].endswith("(practice)"):
            raise ValueError(f"practice bundle: an unexpected label for {c['id']}")
    if not all(math.isfinite(c["strength_pct"]) for c in bundle["candidates"]):
        raise ValueError("practice bundle: a non-finite component")


def write_practice(public_path: Path, out_path: Path, review: ReviewConfig, detect_cfg: DetectConfig) -> dict:
    """The practice bundle from the public bundle on disk (the repo's), written beside it."""
    bundle = practice_bundle(json.loads(public_path.read_text(encoding="utf-8")), review, detect_cfg)
    floor_check(bundle)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = encode(bundle)
    out_path.write_bytes(data)
    return {"candidates": len(bundle["candidates"]), "series": len(bundle["series"]), "bytes": len(data)}
