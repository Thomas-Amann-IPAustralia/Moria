"""`moria artefacts --as-of D`: the artefact checks on every candidate (design §8.3; day 4). A failed check is shown to
the analyst; it never hides the candidate.

Weak signals from documents. Several checks ask whether the candidate would still meet the weak-signal minimum
(design §8.2: 3 items, one per de-duplication group, from 2 sources; a cross-family candidate also its 3 families)
without the evidence the check casts doubt on:
- coverage: without the sources whose volume moved more than ±25% between the baseline and the window, or that have
  no baseline;
- source_break: without the sources whose history doesn't cover the baseline (onboarded inside it);
- ingestion: a source of its evidence had an incident in the window (a failed run, a volume outside the band, a gap);
- duplicate: its raw items are at least twice its de-duplication groups;
- news_cycle: only news, so no primary source, inside 14 days;
- label_drift: it rests on tags (term groups, rings) and the window's items carry more than one tagger version.

Series and AU/world pairs:
- coverage: the source's volume (the denominator) moved more than ±25% over the detector's window;
- ingestion: the source's latest collection had an incident, or a daily source had one in the window;
- source_break: a dated break on the source's card falls inside the detector's window, or a reclassification of
  the series' own classes does (`artefacts.series_breaks`, D-032);
- duplicate (GDELT volumes): the group's window items are at least twice their de-duplication groups;
- news_cycle (GDELT bursts: surges and anomalies): no item from a primary family matches the group in the window.

IP RAPID class pairs: coverage (the classified applications, window against baseline), ingestion, and source_break
when one of the classes is new to the scheme (first seen inside the baseline).

Writes `candidates/as_of=<D>/artefacts.parquet`: one row per candidate, each check's outcome (flag, pass or n/a),
the flags, and the numbers behind them (canonical JSON).
"""

from __future__ import annotations

import logging
import re
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa

from .concepts import COMMAND as DOCS
from .config import DetectConfig, SourceCard
from .detect import COMMAND as DETECT
from .detect import _matching
from .manifest import Manifest
from .measures import COMMAND as SERIES
from .measures import as_of_end, period_index_of_label
from .monitor import COMMAND as MONITOR
from .records import canonical_json
from .store import Store
from .tables import STRS, cache_root, fetch_outputs, read_rows, upload, write_rows
from .text import period_start

log = logging.getLogger("moria.artefacts")

COMMAND = "artefacts"
CHECKS = ("coverage", "ingestion", "duplicate", "news_cycle", "source_break", "label_drift")
ARTEFACTS = pa.schema(
    [
        ("candidate_id", pa.string()),
        ("flags", STRS),
        ("clean", pa.bool_()),  # no check flagged it
        *[(c, pa.string()) for c in CHECKS],  # flag, pass or n/a
        ("details", pa.string()),
    ]
)
# the collection behind a source's series, where they differ
COLLECTED_AS = {"ip_rapid_metrics": "ip_rapid"}
_DATE = re.compile(r"^(\d{4}-\d{2}(?:-\d{2})?)\b")


def card_breaks(cards: dict[str, SourceCard]) -> dict[str, list[date]]:
    """A card's breaks that start with a date apply to the whole source (`2026-10-12: parser ...`); others are notes
    about some of its series and are not applied by machine."""
    out: dict[str, list[date]] = {}
    for cid, card in cards.items():
        ds = []
        for b in card.breaks:
            m = _DATE.match(b.strip())
            if m:
                s = m.group(1)
                ds.append(date.fromisoformat(s if len(s) == 10 else f"{s}-01"))
        if ds:
            out[cid] = sorted(ds)
    return out


def _period_bounds(freq: str, start: str | None, end: str | None) -> tuple[date | None, date | None]:
    """The first day of the window's first period and the last day of its last."""
    if not start or not end or period_index_of_label(freq, start) is None:
        return None, None
    _, s = period_start(start)
    _, e = period_start(end)
    if s is None or e is None:
        return None, None
    nxt = {"A": lambda d: date(d.year + 1, 1, 1), "Q": lambda d: date(d.year + (d.month + 2) // 12,
           (d.month + 2) % 12 + 1, 1), "M": lambda d: date(d.year + d.month // 12, d.month % 12 + 1, 1),
           "D": lambda d: d + timedelta(days=1)}[freq]  # fmt: skip
    return s, nxt(e) - timedelta(days=1)


class Checker:
    def __init__(self, cfg: DetectConfig, cards: dict[str, SourceCard], as_of: date, volumes: list[dict],
                 incidents: list[dict], days: list[dict], series: dict[str, dict], combos: dict[str, dict],
                 group_items: list[dict], taggers: list[str]):  # fmt: skip
        self.cfg, self.cards, self.as_of = cfg, cards, as_of
        dc = cfg.documents
        self.w_start = as_of_end(as_of) - timedelta(days=dc.window_days)
        self.b_start = self.w_start - timedelta(days=dc.baseline_days)
        self.volumes = {v["source"]: v for v in volumes}
        self.uncovered = {s for s, v in self.volumes.items()
                          if v["coverage_start"] is None or v["coverage_start"] > self.b_start}  # fmt: skip
        lim = cfg.artefacts.coverage_change
        self.moved = {s: v["change"] for s, v in self.volumes.items() if v["change"] is None or abs(v["change"]) > lim}
        self.incidents: dict[str, list[dict]] = defaultdict(list)
        for i in incidents:
            self.incidents[i["source"]].append(i)
        self.latest_day: dict[str, dict] = {}
        for d in sorted(days, key=lambda d: d["day"]):
            if d["flag"] != "gap":
                self.latest_day[d["source"]] = d
        self.series, self.combos = series, combos
        self.breaks = card_breaks(cards)
        self.group_items: dict[str, list[dict]] = defaultdict(list)
        for g in group_items:
            self.group_items[g["group"]].append(g)
        self.taggers = taggers

    # ---------------------------------------------------------------------------------------------- documents

    def _survives(self, c: dict, ev: list[dict], keep) -> bool:
        dc = self.cfg.documents
        kept = [e for e in ev if keep(e["source"])]
        groups = {e["dedup_group"] for e in kept}
        sources = {e["source"] for e in kept}
        ok = len(groups) >= dc.min_items and len(sources) >= dc.min_sources
        if c["detectors"] == ["cross_family"]:
            ok = ok and len({e["family"] for e in kept}) >= dc.cross_family_min
        return ok

    def documents(self, c: dict, ev: list[dict]) -> tuple[dict, dict]:
        out, details = {}, {}
        ac = self.cfg.artefacts
        srcs = sorted({e["source"] for e in ev})
        groups = {e["dedup_group"] for e in ev}
        moved = {s: self.moved[s] for s in srcs if s in self.moved}
        out["coverage"] = "flag" if moved and not self._survives(c, ev, lambda s: s not in moved) else "pass"
        details["coverage"] = {s: (None if v is None else round(v, 3)) for s, v in moved.items()}
        onboarded = sorted(set(srcs) & self.uncovered)
        alone = self._survives(c, ev, lambda s: s not in onboarded)
        out["source_break"] = "flag" if onboarded and not alone else "pass"
        details["source_break"] = {s: self.volumes[s]["coverage_start"].date().isoformat()
                                   if self.volumes[s]["coverage_start"] else None for s in onboarded}  # fmt: skip
        ratio = len(ev) / max(len(groups), 1)
        out["duplicate"] = "flag" if ratio >= ac.duplicate_ratio else "pass"
        details["duplicate"] = {"items": len(ev), "groups": len(groups)}
        fams = {e["family"] for e in ev}
        dates = [e["observable_at"] for e in ev if e["observable_at"]]
        span = (max(dates) - min(dates)).days if dates else 0
        news_only = fams == {"news"}
        out["news_cycle"] = "flag" if news_only and span <= ac.news_cycle_days else "pass"
        details["news_cycle"] = {"families": sorted(fams), "span_days": span}
        hit = self._incidents(srcs, self.w_start.date(), self.as_of)
        out["ingestion"] = "flag" if hit else "pass"
        details["ingestion"] = hit
        tagged = c["subject"].startswith("tg:") or "cross_ring" in c["detectors"]
        out["label_drift"] = ("flag" if len(self.taggers) > 1 else "pass") if tagged else "n/a"
        details["label_drift"] = {"taggers": len(self.taggers)}
        return out, details

    def _incidents(self, sources: list[str], start: date, end: date) -> dict[str, list[str]]:
        hit: dict[str, list[str]] = {}
        for s in sources:
            found = self.incidents.get(COLLECTED_AS.get(s, s), [])
            kinds = sorted({i["kind"] for i in found if start <= i["day"] <= end})
            if kinds:
                hit[s] = kinds
        return hit

    # ------------------------------------------------------------------------------------------------- series

    def series_check(self, c: dict) -> tuple[dict, dict]:
        out = {k: "n/a" for k in CHECKS}
        details: dict = {}
        ac = self.cfg.artefacts
        source = c["sources"][0]
        collected = COLLECTED_AS.get(source, source)
        r = self.series.get(c["subject"]) if c["subject_kind"] == "series" else None
        primary = c["type"]
        # coverage: the source's volume over the detector's window
        if r and r["denominator"]:
            change = r["surge_volume_change"] if primary == "weak_signal" else r["volume_change"]
            if change is not None:
                out["coverage"] = "flag" if abs(change) > ac.coverage_change else "pass"
                details["coverage"] = round(change, 3)
        # ingestion: the latest collection, and a daily source's days in the window
        latest = self.latest_day.get(collected)
        hit = []
        if latest and latest["flag"] != "ok":
            hit.append(f"latest {latest['day']}: {latest['flag']}")
        freq = (r or {}).get("frequency")
        if freq == "D" and c["window_start"]:
            for kinds in self._incidents([source], date.fromisoformat(c["window_start"]), self.as_of).values():
                hit += kinds
        out["ingestion"] = "flag" if hit else "pass"
        details["ingestion"] = hit
        # source break: a dated break on the card inside the window
        start, end = _period_bounds(freq, c["window_start"], c["window_end"]) if freq else (None, None)
        if start and end:
            crossed = [d.isoformat() for d in self.breaks.get(collected, []) if start < d <= end]
            subject = c["subject"] if c["subject_kind"] == "series" else ""
            crossed += [f"{b.date}: {b.note}" for b in self.cfg.artefacts.series_breaks
                        if start < date.fromisoformat(b.date) <= end and re.search(b.pattern, subject)]  # fmt: skip
            out["source_break"] = "flag" if crossed else "pass"
            details["source_break"] = crossed
        # GDELT volumes: syndicated copies, and news bursts without a primary source
        if source == "gdelt_news" and r:
            group = c["subject"].split("|")[1]
            rows = self.group_items.get(group, [])
            news = [g for g in rows if g["source"] == "gdelt_news"]
            items, groups = sum(g["items"] for g in news), sum(g["groups"] for g in news)
            if groups:
                out["duplicate"] = "flag" if items / groups >= ac.duplicate_ratio else "pass"
                details["duplicate"] = {"items": items, "groups": groups}
            if set(c["detectors"]) <= {"low_base_surge", "anomaly"}:
                primary_items = [g for g in rows if g["family"] in ac.primary_families]
                out["news_cycle"] = "pass" if primary_items else "flag"
                details["news_cycle"] = {"primary_items": sum(g["items"] for g in primary_items)}
        return out, details

    def class_pair(self, c: dict) -> tuple[dict, dict]:
        out = {k: "n/a" for k in CHECKS}
        details = {}
        r = self.combos.get(c["subject"]) or {}
        change = r.get("exposure_change")
        if change is not None:
            out["coverage"] = "flag" if abs(change) > self.cfg.artefacts.coverage_change else "pass"
            details["coverage"] = round(change, 3)
        latest = self.latest_day.get("ip_rapid")
        out["ingestion"] = "flag" if latest and latest["flag"] != "ok" else "pass"
        if r.get("new_class") is not None:
            out["source_break"] = "flag" if r["new_class"] else "pass"
            details["source_break"] = {"classes_since": r.get("classes_since")}
        return out, details


def check_all(checker: Checker, cands: list[dict], evidence: list[dict]) -> list[dict]:
    ev: dict[str, list[dict]] = defaultdict(list)
    for e in evidence:
        if e["kind"] == "item":
            ev[e["candidate_id"]].append(e)
    rows = []
    for c in cands:
        if c["subject_kind"] in ("series", "pair"):
            out, details = checker.series_check(c)
        elif c["subject_kind"] == "combination" and c["sources"] == ["ip_rapid"]:
            out, details = checker.class_pair(c)
        else:
            out, details = checker.documents(c, ev.get(c["candidate_id"], []))
        flags = [k for k in CHECKS if out.get(k) == "flag"]
        rows.append({"candidate_id": c["candidate_id"], "flags": flags, "clean": not flags, **out,
                     "details": canonical_json(details)})  # fmt: skip
    return rows


def artefacts(store: Store, cfg: DetectConfig, cards: dict[str, SourceCard], as_of: date,
              config_hash: str | None = None) -> tuple[str, str, dict]:  # fmt: skip
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        dm = _matching(store, DETECT, as_of)
        sm, docm, mm = (_matching(store, c, as_of) for c in (SERIES, DOCS, MONITOR))
        if dm["params"]["series_run"] != sm["run_id"] or dm["params"]["documents_run"] != docm["run_id"]:
            raise ValueError(f"the candidates of {as_of} are from older measures; run `moria detect --as-of {as_of}`")
        manifest.params = {"as_of": as_of.isoformat(), "detect_run": dm["run_id"], "monitor_run": mm["run_id"]}

        def files(m, prefix):
            return {k.rsplit("/", 1)[1]: p for k, p in fetch_outputs(store, m, prefix, cache_root()).items()}

        cf, sf, df, mf = (files(dm, "candidates/"), files(sm, "measures/series/"), files(docm, "measures/documents/"),
                          files(mm, "monitors/summary/"))  # fmt: skip
        series = {r["series_id"]: r for r in read_rows(sf["measures.parquet"], ["series_id", "denominator",
                  "volume_change", "surge_volume_change", "frequency"])}  # fmt: skip
        combos = {r["combination"]: r for r in read_rows(df["combinations.parquet"],
                                                          ["combination", "exposure_change", "classes_since",
                                                           "new_class"])}  # fmt: skip
        checker = Checker(cfg, cards, as_of, read_rows(df["volumes.parquet"]), read_rows(mf["incidents.parquet"]),
                          read_rows(mf["days.parquet"]), series, combos, read_rows(df["group_items.parquet"]),
                          docm["params"].get("taggers") or [])  # fmt: skip
        rows = check_all(checker, read_rows(cf["candidates.parquet"]), read_rows(cf["evidence.parquet"]))
        with tempfile.TemporaryDirectory(prefix="moria-artefacts-") as tmp:
            write_rows(rows, ARTEFACTS, Path(tmp) / "artefacts.parquet", ("candidate_id",))
            upload(store, manifest, f"candidates/as_of={as_of.isoformat()}/artefacts.parquet",
                   Path(tmp) / "artefacts.parquet")  # fmt: skip
        counts: dict[str, int] = defaultdict(int)
        counts["candidates"] = len(rows)
        counts["clean"] = sum(r["clean"] for r in rows)
        for r in rows:
            for f in r["flags"]:
                counts[f"flag_{f}"] += 1
        manifest.counts = dict(sorted(counts.items()))
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        cause = f"{COMMAND}: {type(e).__name__}: {first[:300]}"
        log.error("%s", cause)
        return "failed", manifest.finish(store, "failed", cause), {"error": cause}
