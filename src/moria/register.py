"""The signal register (design §6.3, §6.4; day 5): an append-only event log, a spreadsheet round trip for the
reviewer, and the state view that folds the events.

- **`moria register sync --as-of D`** appends the machine's events for the scan's queue: `queued` (its place, view,
  type, ring, flags and dossier), `machine_pathways` (the decision model's suggestions, unconfirmed) and
  `machine_interpretation` (origin, horizon, stance, impact). Each event's id comes from its content, so a re-run
  appends nothing new.
- **`moria register export --as-of D`** writes the reviewer's spreadsheet (labelling by spreadsheet, D-006): the
  queue, then every signal already under review, with the machine's columns and the reviewer's columns (lists of the
  allowed values on each), the dossiers line by line, a sheet for missed signals, and the rules. It goes to the
  private bucket (`interpretation/register/exports/<run_id>.xlsx`) and, with `--out`, to the analyst's own disk.
- **`moria register import PATH`** reads a reviewed spreadsheet, validates every row (allowed values, the lifecycle's
  transitions, a reason for every rejection, a chain for every third-order pathway, a known trend for every
  'reinforces'), sweeps the reviewer's free text, and appends one `review` event per row that changed (and a `missed`
  event per missed signal). Any error rejects the whole file: nothing is appended, and the command exits 2 naming the
  first row and column. The file is kept in the bucket (`inbox/register/<run_id>.xlsx`).

Events live in `interpretation/register/events/<run_id>.parquet`, immutable (the store refuses to overwrite them),
each listed with its hash in its run's manifest. The state is a view: the latest status, the machine's latest
suggestions, the reviewer's latest review, and the whole history.

The register holds the owner's labels and the queue's labels: it lives only in the private bucket, never in the repo,
and no command logs its content.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import pyarrow as pa
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from .config import STATUSES, BaselineFile, ReviewConfig, TerritoriesFile
from .detect import _matching
from .dossier import COMMAND as DOSSIER
from .manifest import Manifest
from .queue import COMMAND as QUEUE
from .rank import failed, files_of, manifest_of
from .records import canonical_json, sha256_hex, utc_now
from .store import Store
from .sweep import sweep
from .tables import TS, cache_root, fetch_outputs, read_rows, upload, write_rows

log = logging.getLogger("moria.register")

SYNC, EXPORT, IMPORT = "register.sync", "register.export", "register.import"
EVENTS_PREFIX = "interpretation/register/events/"
EVENTS = pa.schema(
    [
        ("event_id", pa.string()),
        ("signal_id", pa.string()),
        ("at", TS),
        ("as_of", pa.date32()),  # the scan the event is about
        ("kind", pa.string()),  # queued, machine_pathways, machine_interpretation, review, missed
        ("origin", pa.string()),  # machine or analyst
        ("author", pa.string()),  # moria, model:<repo>@<revision>/<quant>, or analyst:<name>
        ("payload", pa.string()),  # canonical JSON
        ("run_id", pa.string()),
        ("export_id", pa.string()),  # the spreadsheet a review came from
    ]
)

REASONS = ("artefact", "news_cycle", "duplicate", "no_pathway", "insufficient_evidence")
RELEVANCE = ("high", "medium", "low", "none")
STANCE = ("opportunity", "threat", "both", "unclear")
LEVELS = ("low", "medium", "high")
HORIZONS = ("H1", "H2", "H3")
PESTLE = ("political", "economic", "social", "technological", "legal", "environmental")
ADDS = ("pace", "urgency", "arrival_australia", "arrival_ip_system")
QUESTIONS = ("Q1", "Q2", "Q3", "Q4", "S1", "S2", "S3", "S4", "S5", "S6", "S7")
DOMAINS = ("D0", "D1", "D2", "D3", "D4", "D5", "D6")
FOUND_BY = ("analyst", "conventional_scan", "later_events")
MISS_REASONS = ("source_gap", "detector_gap", "ranking_cut_off")

# the reviewer's columns, in order, with the allowed values of single and multiple choices
EDITABLE: list[tuple[str, str, tuple[str, ...] | None]] = [
    ("status", "single", STATUSES),
    ("rejection_reason", "single", REASONS),
    ("pathways", "multi", ("P1", "P2", "P3", "P4", "P5", "P6")),
    ("order", "single", ("1", "2", "3")),
    ("chain", "text", None),
    ("territories", "multi", None),  # the territory ids, from config
    ("baseline_relation", "single", ("novel", "reinforces")),
    ("known_trend", "single", None),  # a known trend's id, from config
    ("adds", "multi", ADDS),
    ("australian_relevance", "single", RELEVANCE),
    ("alternatives_considered", "text", None),
    ("questions", "multi", QUESTIONS),
    ("domains", "multi", DOMAINS),
    ("stance", "single", STANCE),
    ("impact", "single", LEVELS),
    ("horizon", "single", HORIZONS),
    ("uncertainty", "single", LEVELS),
    ("pestle", "multi", PESTLE),
    ("confidence", "single", LEVELS),
    ("rationale", "text", None),
    ("reviewer", "text", None),
    ("notes", "text", None),
]
TEXT_FIELDS = [name for name, kind, _ in EDITABLE if kind == "text"]
INFO = ["rank", "signal_id", "view", "type", "ring", "flags", "label", "summary", "chart", "example_1", "example_2",
        "example_3", "detectors", "sources", "corroboration", "machine_pathways", "machine_order", "machine_origin",
        "machine_horizon", "machine_stance", "machine_impact", "machine_known_trend", "territory_terms", "dossier",
        "current_status"]  # fmt: skip
MISSED = ["development", "noticed", "found_by", "reason", "evidence", "notes"]


# ------------------------------------------------------------------------------------------------- the event log


def event(signal_id: str, kind: str, origin: str, author: str, payload: dict, run_id: str, as_of: date | None,
          export_id: str | None = None, at: datetime | None = None) -> dict:  # fmt: skip
    """An event; its id is the hash of what it says (not when), so the same event is never appended twice."""
    body = canonical_json(payload)
    eid = sha256_hex(canonical_json([signal_id, kind, origin, author, body, as_of.isoformat() if as_of else None,
                                     export_id]))  # fmt: skip
    return {"event_id": eid, "signal_id": signal_id, "at": (at or utc_now()).replace(microsecond=0),
            "as_of": as_of, "kind": kind, "origin": origin, "author": author, "payload": body, "run_id": run_id,
            "export_id": export_id}  # fmt: skip


def events(store: Store) -> list[dict]:
    """Every event of every passed register run, checked against its manifest, oldest first."""
    out = []
    for command in (SYNC, IMPORT):
        for k in sorted(store.list(f"manifests/{command}/")):
            m = json.loads(store.get(k))
            if m["status"] != "passed":
                continue
            for p in fetch_outputs(store, m, EVENTS_PREFIX, cache_root()).values():
                out.extend(read_rows(p))
    out.sort(key=lambda e: (e["at"], e["event_id"]))
    return out


def state(evs: list[dict]) -> dict[str, dict]:
    """The register's current state, folded from its events: per signal, its status, the scans that queued it, the
    machine's latest suggestions, the reviewer's latest review, and its history."""
    out: dict[str, dict] = {}
    for e in evs:
        s = out.setdefault(e["signal_id"], {"signal_id": e["signal_id"], "status": "candidate", "queued": [],
                                            "machine": {}, "review": None, "reviews": 0, "history": []})  # fmt: skip
        p = json.loads(e["payload"])
        if e["kind"] == "queued":
            s["queued"].append(p)
        elif e["kind"] in ("machine_pathways", "machine_interpretation"):
            s["machine"][e["kind"]] = {"author": e["author"], **p}
        elif e["kind"] == "review":
            s["review"], s["reviews"] = {"author": e["author"], "at": e["at"].isoformat(), **p}, s["reviews"] + 1
            s["status"] = p.get("status") or s["status"]
        s["history"].append({"at": e["at"].isoformat(), "kind": e["kind"], "status": s["status"]})
    return out


def append(store: Store, manifest: Manifest, rows: list[dict]) -> int:
    known = {e["event_id"] for e in events(store)}
    new = [r for r in rows if r["event_id"] not in known]
    if new:
        with tempfile.TemporaryDirectory(prefix="moria-register-") as tmp:
            path = Path(tmp) / "events.parquet"
            write_rows(new, EVENTS, path, ("signal_id", "kind", "event_id"))
            upload(store, manifest, f"{EVENTS_PREFIX}{manifest.run_id}.parquet", path)
    return len(new)


# ---------------------------------------------------------------------------------------------------------- sync


def queue_rows(store: Store, as_of: date) -> tuple[dict, list[dict]]:
    qm = _matching(store, QUEUE, as_of)
    return qm, read_rows(files_of(store, qm, "review/")["queue.parquet"])


def sync(store: Store, cfg: ReviewConfig, as_of: date, config_hash: str | None = None) -> tuple[str, str, dict]:
    manifest = Manifest(command=SYNC, config_hash=config_hash)
    try:
        qm, rows = queue_rows(store, as_of)
        dm = manifest_of(store, DOSSIER, qm["params"]["dossier_run"])
        hashes = {o["key"]: o["sha256"] for o in dm["outputs"]}
        pm = manifest_of(store, "pathways", qm["params"]["pathways_run"])
        sug = {r["candidate_id"]: r for r in read_rows(files_of(store, pm, "interpretation/pathways/")
                                                       ["pathways.parquet"])}  # fmt: skip
        manifest.params = {"as_of": as_of.isoformat(), "queue_run": qm["run_id"], "pathways_run": pm["run_id"]}
        out = []
        for r in rows:
            sid = r["candidate_id"]
            out.append(event(sid, "queued", "machine", "moria", {
                "queue_rank": r["queue_rank"], "view": r["view"], "pass": r["pass"], "type": r["type"],
                "ring": r["ring"], "label": r["label"], "detectors": list(r["detectors"]), "flags": list(r["flags"]),
                "dossier": r["dossier_md"], "dossier_sha256": hashes.get(r["dossier_json"]),
                "queue_run": qm["run_id"]}, manifest.run_id, as_of))  # fmt: skip
            s = sug.get(sid) or {}
            if s.get("pathways"):
                out.append(event(sid, "machine_pathways", "machine", s["author"], {
                    "pathways": json.loads(s["pathways"]), "order": json.loads(s["order"]),
                    "suggested": {"pathway": s["pathway_top"], "order": s["order_top"], "chain": None},
                    "confirmed": False, "questions": s["questions"]}, manifest.run_id, as_of))  # fmt: skip
                out.append(event(sid, "machine_interpretation", "machine", s["author"], {
                    k: json.loads(s[k]) for k in ("origin", "horizon", "stance", "impact")}, manifest.run_id,
                    as_of))  # fmt: skip
        n = append(store, manifest, out)
        manifest.counts = {"events": len(out), "appended": n, "signals": len(rows)}
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        return failed(SYNC, store, manifest, e)


# -------------------------------------------------------------------------------------------------------- export


def _fmt_pathways(js: str | None) -> str:
    p = json.loads(js or "{}")
    top = sorted(p.items(), key=lambda kv: -kv[1])[:3]
    return ", ".join(f"{k} {v:.2f}" for k, v in top)


def export(store: Store, cfg: ReviewConfig, baseline: BaselineFile, territories: TerritoriesFile, as_of: date,
           out: Path | None = None, config_hash: str | None = None) -> tuple[str, str, dict]:  # fmt: skip
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    manifest = Manifest(command=EXPORT, config_hash=config_hash)
    try:
        qm, rows = queue_rows(store, as_of)
        dm = manifest_of(store, DOSSIER, qm["params"]["dossier_run"])
        dossiers = {}
        for k, p in fetch_outputs(store, dm, "interpretation/dossiers/", cache_root()).items():
            dossiers[k] = Path(p).read_text(encoding="utf-8")
        st = state(events(store))
        manifest.params = {"as_of": as_of.isoformat(), "queue_run": qm["run_id"], "dossier_run": dm["run_id"]}
        queued = {r["candidate_id"] for r in rows}
        active = [s for sid, s in sorted(st.items()) if sid not in queued and s["status"] not in ("candidate",)]
        wb = Workbook()
        ws = wb.active
        ws.title = "Queue"
        lists = wb.create_sheet("Lists")
        values = {name: list(allowed) for name, _, allowed in EDITABLE if allowed}
        values["territories"] = [t.id for t in territories.territories]
        values["known_trend"] = [t.id for t in baseline.trends]
        for j, (name, vals) in enumerate(sorted(values.items()), 1):
            lists.cell(row=1, column=j, value=name)
            for i, v in enumerate(vals, 2):
                lists.cell(row=i, column=j, value=v)
        headers = INFO + [n for n, _, _ in EDITABLE]
        grey, yellow = PatternFill("solid", fgColor="DDDDDD"), PatternFill("solid", fgColor="FFF2CC")
        for j, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=j, value=h)
            c.font, c.fill = Font(bold=True), grey if h in INFO else yellow
        ids = []
        for i, r in enumerate(rows, 2):
            d = json.loads(dossiers.get(r["dossier_json"], "{}"))
            ex = (d.get("examples") or []) + [{}, {}, {}]
            info = {"rank": r["queue_rank"], "signal_id": r["candidate_id"], "view": r["view"], "type": r["type"],
                    "ring": r["ring"], "flags": ", ".join(r["flags"]) or "none", "label": r["label"],
                    "summary": d.get("summary"), "chart": (d.get("chart") or {}).get("sparkline"),
                    **{f"example_{k + 1}": _example(ex[k]) for k in range(3)},
                    "detectors": ", ".join(r["detectors"]), "sources": ", ".join(d.get("sources") or []),
                    "corroboration": d.get("corroboration"), "machine_pathways": _fmt_pathways(r["pathways"]),
                    "machine_order": r["order_top"], "machine_origin": r["origin_top"],
                    "machine_horizon": r["horizon_top"], "machine_stance": r["stance_top"],
                    "machine_impact": r["impact_top"],
                    "machine_known_trend": f"{r['known_trend']} {r['known_trend_sim']:.2f}"
                    if r["known_trend"] else "", "territory_terms": ", ".join(r["term_territories"] or []),
                    "dossier": r["dossier_md"],
                    "current_status": st.get(r["candidate_id"], {}).get("status", "candidate")}  # fmt: skip
            _row(ws, i, headers, info, st.get(r["candidate_id"]))
            ids.append(r["candidate_id"])
        for i, s in enumerate(active, len(rows) + 2):
            last = (s["queued"] or [{}])[-1]
            info = {"rank": None, "signal_id": s["signal_id"], "view": last.get("view"), "type": last.get("type"),
                    "ring": last.get("ring"), "flags": ", ".join(last.get("flags") or []), "label": last.get("label"),
                    "dossier": last.get("dossier"), "current_status": s["status"]}  # fmt: skip
            _row(ws, i, headers, info, s)
            ids.append(s["signal_id"])
        n = len(ids) + 1
        for j, h in enumerate(headers, 1):
            if h in values:
                col = sorted(values).index(h) + 1
                letter = lists.cell(row=1, column=col).column_letter
                kind = next(k for name, k, _ in EDITABLE if name == h)
                if kind == "single":
                    dv = DataValidation(type="list", formula1=f"=Lists!${letter}$2:${letter}${len(values[h]) + 1}",
                                        allow_blank=True)  # fmt: skip
                    ws.add_data_validation(dv)
                    dv.add(f"{ws.cell(row=2, column=j).column_letter}2:{ws.cell(row=2, column=j).column_letter}{n}")
            width = 60 if h in ("label", "summary", "rationale", "alternatives_considered", "notes", "chain") else 18
            ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = width
        for row in ws.iter_rows(min_row=2, max_row=n):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "C2"
        ds = wb.create_sheet("Dossiers")
        ds.append(["signal_id", "line"])
        for sid in ids[: len(rows)]:
            for line in dossiers.get(next(r["dossier_md"] for r in rows if r["candidate_id"] == sid), "").split("\n"):
                ds.append([sid, line])
        ds.column_dimensions["A"].width, ds.column_dimensions["B"].width = 18, 160
        ms = wb.create_sheet("Missed")
        ms.append(MISSED)
        for name, allowed in (("found_by", FOUND_BY), ("reason", MISS_REASONS)):
            col = MISSED.index(name) + 1
            letter = ms.cell(row=1, column=col).column_letter
            dv = DataValidation(type="list", formula1='"' + ",".join(allowed) + '"', allow_blank=True)
            ms.add_data_validation(dv)
            dv.add(f"{letter}2:{letter}200")
        rules = wb.create_sheet("Read me", 0)
        for line in readme(cfg, as_of, manifest.run_id):
            rules.append([line])
        rules.column_dimensions["A"].width = 140
        meta = wb.create_sheet("_meta")
        meta.append(["export_id", manifest.run_id])
        meta.append(["as_of", as_of.isoformat()])
        meta.append(["queue_run", qm["run_id"]])
        meta.append(["signals", ",".join(ids)])
        meta.sheet_state = "hidden"
        lists.sheet_state = "hidden"
        with tempfile.TemporaryDirectory(prefix="moria-export-") as tmp:
            path = Path(tmp) / "register.xlsx"
            wb.save(path)
            key = f"interpretation/register/exports/{manifest.run_id}.xlsx"
            upload(store, manifest, key, path)
            if out is not None:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(path.read_bytes())
        manifest.counts = {"rows": len(ids), "queue": len(rows), "under_review": len(active)}
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        return failed(EXPORT, store, manifest, e)


def _example(e: dict) -> str:
    if not e:
        return ""
    if "title" in e:
        when = (e.get("observable_at") or e.get("filed") or "")[:10]
        return f"{when} {e.get('source') or e.get('right') or ''}: {e.get('title') or ''} {e.get('url') or ''}".strip()
    if "period" in e:
        return f"{e['period']}: {e['value']}"
    return canonical_json(e)


def _row(ws, i: int, headers: list[str], info: dict, s: dict | None) -> None:
    review = (s or {}).get("review") or {}
    for j, h in enumerate(headers, 1):
        if h in info:
            v = info[h]
        elif h == "pathways":
            v = ", ".join(p["pathway"] for p in review.get("pathways") or [])
        elif h == "order":
            v = next((str(p["order"]) for p in review.get("pathways") or []), None)
        elif h == "chain":
            v = next((p.get("chain") for p in review.get("pathways") or [] if p.get("chain")), None)
        elif h in ("stance", "impact", "horizon", "uncertainty", "pestle", "confidence", "rationale"):
            v = (review.get("interpretation") or {}).get(h)
        else:
            v = review.get(h)
        if isinstance(v, list):
            v = ", ".join(v)
        ws.cell(row=i, column=j, value=v)


def readme(cfg: ReviewConfig, as_of: date, export_id: str) -> list[str]:
    t = cfg.lifecycle.transitions
    return [
        f"Moria's review spreadsheet: the queue of the scan at {as_of.isoformat()} (export {export_id}).",
        "Grey columns are the machine's; yellow columns are yours. Fill in the rows you review; leave the others "
        "blank. Save, and import with `moria register import FILE`.",
        "",
        "Triage (design §2.5): keep = status investigating; park = status rejected with reason no_pathway (revisited "
        "if it grows); reject = status rejected with another reason.",
        "Statuses and the moves allowed from each: " + "; ".join(f"{k} -> {', '.join(v)}" for k, v in t.items()),
        "Every rejection needs a rejection_reason; a reason needs the status rejected.",
        "pathways: the pathways you confirm, e.g. 'P1, P3', with their order (1 direct, 2 through one change, 3 "
        "through a chain); an order of 3 needs its chain, named in words.",
        "Validated needs at least one pathway, australian_relevance and baseline_relation.",
        "baseline_relation: novel, or reinforces (then known_trend, the trend's id, and adds: what the signal adds: "
        "pace, urgency, arrival_australia, arrival_ip_system). A known trend never rejects a signal (D-014).",
        "Lists take several values separated by commas: pathways, territories, adds, questions, domains, pestle.",
        "Questions: Q1 to Q4 are the outside-in questions; S1 to S7 the system-specific ones (design §2.3).",
        "The machine's pathways, order, origin, horizon, stance, impact and known trend are suggestions from a free "
        "decision model or the tagger: uncalibrated, never thresholds (design §9.1).",
        "Missed sheet: developments Moria missed (design §6.3), with how they were found and why they were missed.",
        "This file holds the queue's labels and your review: keep it private; it belongs in the private bucket only.",
    ]


# -------------------------------------------------------------------------------------------------------- import


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _split(v) -> list[str]:
    if v is None:
        return []
    return [x.strip() for x in re.split(r"[,;]", str(v)) if x.strip()]


class ReviewRow(_Strict):
    status: Literal[STATUSES]  # type: ignore[valid-type]
    rejection_reason: Literal[REASONS] | None = None  # type: ignore[valid-type]
    pathways: list[Literal["P1", "P2", "P3", "P4", "P5", "P6"]] = []
    order: Literal["1", "2", "3"] | None = None
    chain: str | None = None
    territories: list[str] = []
    baseline_relation: Literal["novel", "reinforces"] | None = None
    known_trend: str | None = None
    adds: list[Literal[ADDS]] = []  # type: ignore[valid-type]
    australian_relevance: Literal[RELEVANCE] | None = None  # type: ignore[valid-type]
    alternatives_considered: str | None = None
    questions: list[Literal[QUESTIONS]] = []  # type: ignore[valid-type]
    domains: list[Literal[DOMAINS]] = []  # type: ignore[valid-type]
    stance: Literal[STANCE] | None = None  # type: ignore[valid-type]
    impact: Literal[LEVELS] | None = None  # type: ignore[valid-type]
    horizon: Literal[HORIZONS] | None = None  # type: ignore[valid-type]
    uncertainty: Literal[LEVELS] | None = None  # type: ignore[valid-type]
    pestle: list[Literal[PESTLE]] = []  # type: ignore[valid-type]
    confidence: Literal[LEVELS] | None = None  # type: ignore[valid-type]
    rationale: str | None = None
    reviewer: str | None = None
    notes: str | None = None

    @field_validator("order", mode="before")
    @classmethod
    def _order(cls, v):
        if v is None or v == "":
            return None
        return str(int(float(v))) if str(v).replace(".", "", 1).isdigit() else str(v)

    @model_validator(mode="after")
    def _rules(self) -> ReviewRow:
        if (self.status == "rejected") != (self.rejection_reason is not None):
            raise ValueError("a rejection needs a rejection_reason, and a rejection_reason needs the status rejected")
        if self.pathways and self.order is None:
            raise ValueError("confirmed pathways need their order (1, 2 or 3)")
        if self.order == "3" and not (self.chain or "").strip():
            raise ValueError("a third-order pathway needs its chain")
        if self.status == "validated" and not (self.pathways and self.australian_relevance and self.baseline_relation):
            raise ValueError("validated needs pathways, australian_relevance and baseline_relation")
        if self.baseline_relation == "reinforces" and not self.known_trend:
            raise ValueError("'reinforces' needs the known_trend it reinforces")
        if self.baseline_relation == "novel" and self.known_trend:
            raise ValueError("'novel' takes no known_trend")
        return self


class MissedRow(_Strict):
    development: str
    noticed: date
    found_by: Literal[FOUND_BY]  # type: ignore[valid-type]
    reason: Literal[MISS_REASONS]  # type: ignore[valid-type]
    evidence: str | None = None
    notes: str | None = None


class ReviewFileError(ValueError):
    pass


def _clean(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    return s or None


def read_review(path: Path, cfg: ReviewConfig, baseline: BaselineFile, territories: TerritoriesFile,
                current: dict[str, dict], export_ids: set[str]) -> tuple[dict, list, list[dict]]:  # fmt: skip
    """(meta, [(signal_id, review payload)], [missed payloads]); raises ReviewFileError naming the first bad cell."""
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True, read_only=True)
    if "_meta" not in wb.sheetnames or "Queue" not in wb.sheetnames:
        raise ReviewFileError("not a Moria review spreadsheet (no _meta or Queue sheet)")
    meta = {r[0]: r[1] for r in wb["_meta"].iter_rows(values_only=True) if r and r[0]}
    if meta.get("export_id") not in export_ids:
        raise ReviewFileError(f"export {meta.get('export_id')!r} is not a passed export in the store")
    allowed_ids = set(str(meta.get("signals") or "").split(","))
    terr, trends = {t.id for t in territories.territories}, {t.id for t in baseline.trends}
    rows = list(wb["Queue"].iter_rows(values_only=True))
    headers = [str(h) if h is not None else "" for h in rows[0]]
    editable = [n for n, _, _ in EDITABLE]
    missing = [h for h in ["signal_id", *editable] if h not in headers]
    if missing:
        raise ReviewFileError(f"Queue sheet: columns missing: {', '.join(missing)}")
    errors, reviews, seen = [], [], set()
    for i, row in enumerate(rows[1:], 2):
        cells = dict(zip(headers, row, strict=False))
        sid = _clean(cells.get("signal_id"))
        vals = {n: _clean(cells.get(n)) for n in editable}
        if not sid and not any(vals.values()):
            continue
        if sid not in allowed_ids:
            errors.append(f"Queue row {i}: signal_id {sid!r} is not in this export")
            continue
        if sid in seen:
            errors.append(f"Queue row {i}: {sid} appears twice")
            continue
        seen.add(sid)
        if not any(vals.values()):
            continue
        texts = sweep({n: vals[n] or "" for n in TEXT_FIELDS})
        if texts.severity == "high":
            errors.append(
                f"Queue row {i} ({sid}): free text has high-severity findings: {', '.join(texts.codes('high'))}"
            )
            continue
        for n in TEXT_FIELDS:
            vals[n] = texts.fields[n] or None
        data = {k: (_split(v) if kind == "multi" else v) for (k, kind, _), v in zip(EDITABLE, vals.values(),
                                                                                    strict=True)}  # fmt: skip
        if data["status"] is None:
            errors.append(f"Queue row {i} ({sid}): status is empty but other columns are filled")
            continue
        try:
            rr = ReviewRow.model_validate(data)
        except ValidationError as e:
            err = e.errors()[0]
            where = ".".join(str(x) for x in err["loc"])
            msg = err["msg"].removeprefix("Value error, ")
            errors.append(f"Queue row {i} ({sid}): {where + ': ' if where else ''}{msg}")
            continue
        bad = [t for t in rr.territories if t not in terr]
        if bad or (rr.known_trend and rr.known_trend not in trends):
            errors.append(
                f"Queue row {i} ({sid}): unknown territory or known trend: {', '.join(bad) or rr.known_trend}"
            )
            continue
        now = (current.get(sid) or {}).get("status", "candidate")
        if rr.status != now and rr.status not in cfg.lifecycle.transitions[now]:
            errors.append(f"Queue row {i} ({sid}): status cannot move from {now} to {rr.status}")
            continue
        payload = {"status": rr.status, "rejection_reason": rr.rejection_reason,
                   "pathways": [{"pathway": p, "order": int(rr.order), "chain": rr.chain if rr.order == "3" else None,
                                 "confirmed": True} for p in rr.pathways],
                   "territories": rr.territories, "outside_territories": not rr.territories,
                   "baseline_relation": rr.baseline_relation, "known_trend": rr.known_trend, "adds": rr.adds,
                   "australian_relevance": rr.australian_relevance,
                   "alternatives_considered": rr.alternatives_considered, "questions": rr.questions,
                   "domains": rr.domains, "notes": rr.notes,
                   "interpretation": {k: getattr(rr, k) for k in ("stance", "impact", "horizon", "uncertainty",
                                                                  "pestle", "confidence", "rationale")},
                   "reviewer": rr.reviewer or cfg.lifecycle.reviewer}  # fmt: skip
        reviews.append((sid, payload))
    missed = []
    if "Missed" in wb.sheetnames:
        mrows = list(wb["Missed"].iter_rows(values_only=True))
        mh = [str(h) if h is not None else "" for h in (mrows[0] if mrows else [])]
        for i, row in enumerate(mrows[1:], 2):
            cells = {k: _clean(v) for k, v in zip(mh, row, strict=False) if k in MISSED}
            if not any(cells.values()):
                continue
            texts = sweep({k: cells.get(k) or "" for k in ("development", "evidence", "notes")})
            if texts.severity == "high":
                errors.append(f"Missed row {i}: free text has high-severity findings")
                continue
            cells.update({k: texts.fields[k] or None for k in ("development", "evidence", "notes")})
            try:
                missed.append(MissedRow.model_validate(cells).model_dump(mode="json"))
            except ValidationError as e:
                err = e.errors()[0]
                errors.append(f"Missed row {i}: {'.'.join(str(x) for x in err['loc'])}: {err['msg']}")
    if errors:
        raise ReviewFileError("; ".join(errors[:20]) + (f"; and {len(errors) - 20} more" if len(errors) > 20 else ""))
    return meta, reviews, missed


def import_review(store: Store, cfg: ReviewConfig, baseline: BaselineFile, territories: TerritoriesFile,
                  path: Path, config_hash: str | None = None) -> tuple[str, str, dict]:  # fmt: skip
    manifest = Manifest(command=IMPORT, config_hash=config_hash)
    try:
        exports = {json.loads(store.get(k))["run_id"] for k in store.list(f"manifests/{EXPORT}/")
                   if json.loads(store.get(k))["status"] == "passed"}  # fmt: skip
        evs = events(store)
        current = state(evs)
        meta, reviews, missed = read_review(path, cfg, baseline, territories, current, exports)
        export_id = str(meta["export_id"])
        as_of = date.fromisoformat(str(meta["as_of"]))
        manifest.params = {"export_id": export_id, "as_of": as_of.isoformat()}
        data = path.read_bytes()
        key = f"inbox/register/{manifest.run_id}.xlsx"
        store.put(key, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        manifest.add_output(key, data)
        out, unchanged = [], 0
        now = datetime.now(UTC)
        for sid, payload in reviews:
            last = (current.get(sid) or {}).get("review") or {}
            if {k: v for k, v in last.items() if k not in ("author", "at")} == payload:
                unchanged += 1
                continue
            out.append(event(sid, "review", "analyst", f"analyst:{payload['reviewer']}", payload, manifest.run_id,
                             as_of, export_id, now))  # fmt: skip
        for m in missed:
            miss_id = f"miss-{sha256_hex(canonical_json(m))[:12]}"
            out.append(event(miss_id, "missed", "analyst", f"analyst:{cfg.lifecycle.reviewer}", m, manifest.run_id,
                             as_of, export_id, now))  # fmt: skip
        n = append(store, manifest, out)
        statuses: dict[str, int] = defaultdict(int)
        for _, p in reviews:
            statuses[f"status_{p['status']}"] += 1
        manifest.counts = {"reviews": len(reviews), "appended": n, "unchanged": unchanged, "missed": len(missed),
                           **dict(sorted(statuses.items()))}  # fmt: skip
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        return failed(IMPORT, store, manifest, e)
