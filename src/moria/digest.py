"""`moria digest --as-of D`: the weekly early-warning digest for IPAVentures (design §0, §1, §4.4; day 5).

The early-warning view of the register: weak signals, low-base surges, novel items and new combinations, shown as soon
as they pass the artefact checks, validated or not, clearly marked. In order:
- the scan in brief, and what is new since the previous scan;
- the top early-warning candidates with no artefact flag, by the early-warning score, each with its one-line
  summary, detectors, ring, sources, the register's status, the machine's pathway suggestion (labelled as such) and
  its dossier;
- high-ranking candidates that carry flags, with their flags (a flag is shown, never hidden);
- candidates that strengthened or weakened since the previous scan;
- coverage: the Growth Territories the queue's items match by their terms, and territories with none (possible blind
  spots, design §2.4);
- the limits every output discloses (design §11.3).

Writes `interpretation/digests/as_of=<D>/digest.md` in the private bucket: it holds labels and links, so it is never
logged and never goes in the repo.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date

from .config import ReviewConfig, TerritoriesFile
from .detect import COMMAND as DETECT
from .detect import _matching
from .dossier import md_text, summary_line
from .manifest import Manifest
from .queue import COMMAND as QUEUE
from .rank import COMMAND as RANK
from .rank import failed, files_of, manifest_of
from .register import events, state
from .store import Store
from .tables import read_rows

log = logging.getLogger("moria.digest")

COMMAND = "digest"


def previous_scan(store: Store, as_of: date) -> tuple[str, dict[str, dict]] | None:
    """The latest passed detect run before as_of: (its as_of, {candidate_id: candidate})."""
    best = None
    for k in sorted(store.list(f"manifests/{DETECT}/")):
        m = json.loads(store.get(k))
        day = m["params"].get("as_of")
        if m["status"] != "passed" or not day or day >= as_of.isoformat():
            continue
        if best is None or (day, m.get("started_ns") or 0) > (best["params"]["as_of"], best.get("started_ns") or 0):
            best = m
    if best is None:
        return None
    rows = read_rows(files_of(store, best, "candidates/")["candidates.parquet"], ["candidate_id", "type", "strength"])
    return best["params"]["as_of"], {r["candidate_id"]: r for r in rows}


def capped(rows: list[dict], n: int, per_source: int) -> list[dict]:
    """The first n rows, at most per_source from any one source."""
    out, seen = [], Counter()
    for r in rows:
        if seen[r["source"]] < per_source:
            out.append(r)
            seen[r["source"]] += 1
        if len(out) == n:
            break
    return out


def _status(st: dict, cid: str) -> str:
    s = st.get(cid)
    return s["status"] if s else "candidate (not reviewed)"


def digest(store: Store, cfg: ReviewConfig, territories: TerritoriesFile, as_of: date,
           config_hash: str | None = None) -> tuple[str, str, dict]:  # fmt: skip
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        rm, qm = _matching(store, RANK, as_of), _matching(store, QUEUE, as_of)
        if qm["params"].get("rank_run") != rm["run_id"]:
            raise ValueError(f"the queue of {as_of} is for an older ranking; run `moria queue --as-of {as_of}`")
        dm = manifest_of(store, DETECT, rm["params"]["detect_run"])
        cands = {c["candidate_id"]: c for c in read_rows(files_of(store, dm, "candidates/")["candidates.parquet"])}
        ranked = read_rows(files_of(store, rm, "review/")["ranked.parquet"])
        queue = read_rows(files_of(store, qm, "review/")["queue.parquet"])
        st = state(events(store))
        prev = previous_scan(store, as_of)
        manifest.params = {"as_of": as_of.isoformat(), "rank_run": rm["run_id"], "queue_run": qm["run_id"],
                           "previous_scan": prev[0] if prev else None}  # fmt: skip
        dg = cfg.digest
        ew = sorted((r for r in ranked if r["score_early_warning"] is not None),
                    key=lambda r: (-r["score_early_warning"], r["candidate_id"]))  # fmt: skip
        clean = [r for r in ew if not r["flags"]]
        flagged = [r for r in ew if r["flags"]]
        cap = max(1, int(dg.top * cfg.queue.source_max))  # breadth across sources, as in the queue
        queued = {q["candidate_id"]: q for q in queue}
        new = [r for r in ew if prev and r["candidate_id"] not in prev[1]]
        lines = [f"# Moria early-warning digest: the scan of {as_of.isoformat()}", "",
                 "Private: this digest holds labels and links. The machine's pathway suggestions are a free decision "
                 "model's, uncalibrated and unconfirmed; statuses come from the register.", "",
                 "## In brief", "",
                 f"- {len(ranked)} candidates in the scan; {len(ew)} in the early-warning view, {len(clean)} of them "
                 "with no artefact flag.",
                 f"- The review queue holds {len(queue)} dossiers, "
                 f"{sum(1 for q in queue if q['view'] == 'early_warning')} picked by the early-warning view.",
                 (f"- New since the scan of {prev[0]}: {len(new)} early-warning candidates."
                  if prev else "- No earlier scan to compare with."), ""]  # fmt: skip
        lines += [
            "## Early-warning signals past the artefact checks",
            "",
            f"The {dg.top} highest by the early-warning score, at most {cap} from one source.",
            "",
        ]
        for n, r in enumerate(capped(clean, dg.top, cap), 1):
            lines += _entry(n, r, cands.get(r["candidate_id"]), queued.get(r["candidate_id"]), st, prev)
        lines += ["", "## High-ranking candidates with artefact flags (shown, never hidden)", ""]
        for n, r in enumerate(capped(flagged, dg.flagged, cap), 1):
            lines += _entry(n, r, cands.get(r["candidate_id"]), queued.get(r["candidate_id"]), st, prev)
        lines += ["", "## Changed since the previous scan", "",
                  "Early-warning candidates with no artefact flag whose strength moved most since the previous scan.",
                  ""]  # fmt: skip
        if prev:
            moved = []
            for r in clean:  # flagged candidates move with their sources' onboarding, not with the world
                p = prev[1].get(r["candidate_id"])
                if p and p["strength"] and r["strength"] is not None and abs(r["strength"] / p["strength"] - 1) >= 0.1:
                    moved.append({**r, "_change": r["strength"] / p["strength"] - 1})
            moved.sort(key=lambda m: (-abs(m["_change"]), m["candidate_id"]))
            for r in capped(moved, dg.changes, cap):
                word = "strengthened" if r["_change"] > 0 else "weakened"
                lines.append(f"- {word} {r['_change']:+.0%}: {md_text(r['label'] or r['subject'], 120)} "
                             f"(`{r['candidate_id']}`, {r['type']})")  # fmt: skip
            if not moved:
                lines.append("None moved by 10% or more.")
        else:
            lines.append("No earlier scan.")
        terms = Counter(t for q in queue for t in q["term_territories"] or [])
        lines += ["", "## Coverage of the Growth Territories (term matches in the queue)", "",
                  "| Territory | Queue items matching its terms |", "|---|---:|"]  # fmt: skip
        for t in territories.territories:
            lines.append(f"| {t.id} {md_text(t.name)} | {terms.get(t.id, 0)} |")
        blind = [t.id for t in territories.territories if not terms.get(t.id)]
        lines += ["", f"Territories with no match in the queue (possible blind spots): {', '.join(blind) or 'none'}.",
                  "", "## Limits", "", "- Backfilled history has no true first sighting.",
                  "- Weak signals from documents carry onboarding flags until the daily feeds have a baseline (D-022).",
                  "- Customers (D4) are low coverage on public data; non-English sources are absent.",
                  "- The machine's pathway suggestions did not pass `moria eval pathways` on this scan, so they are "
                  "shown, not ranked (D-029)." if not cfg.pathways.use_in_ranking else
                  "- The pathway suggestions are uncalibrated (design §9.1)."]  # fmt: skip
        data = ("\n".join(lines) + "\n").encode("utf-8")
        key = f"interpretation/digests/as_of={as_of.isoformat()}/digest.md"
        store.put(key, data, "text/markdown")
        manifest.add_output(key, data)
        manifest.counts = {"early_warning": len(ew), "clean": len(clean), "listed": min(len(clean), dg.top),
                           "flagged_listed": min(len(flagged), dg.flagged), "new": len(new),
                           "blind_spots": len(blind)}  # fmt: skip
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        return failed(COMMAND, store, manifest, e)


def _entry(n: int, r: dict, c: dict | None, q: dict | None, st: dict, prev) -> list[str]:
    nums = json.loads((c or {}).get("numbers") or "{}")
    summary = summary_line(c, nums) if c else r["label"]
    new = " **new**" if prev and r["candidate_id"] not in prev[1] else ""
    status = _status(st, r["candidate_id"])
    mark = "**validated**" if status == "validated" else status
    lines = [f"{n}. **{md_text(r['label'] or r['subject'], 120)}**{new} (`{r['candidate_id']}`)",
             f"   - {md_text(summary, 300)}",
             f"   - {r['type']}; {', '.join(r['detectors'])}; ring {r['ring']}; sources {', '.join(r['sources'])}; "
             f"flags {', '.join(r['flags']) or 'none'}; status {mark}"]  # fmt: skip
    if q:
        pw = json.loads(q.get("pathways") or "{}")
        top = ", ".join(f"{k} {v:.2f}" for k, v in sorted(pw.items(), key=lambda kv: -kv[1])[:2])
        lines.append(
            f"   - In the review queue at place {q['queue_rank']}; machine pathways (unconfirmed): {top or 'none'}; "
            f"dossier `{q['dossier_md']}`"
        )
    return lines
