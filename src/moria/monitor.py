"""`moria monitor ingestion --as-of D`: the ingestion monitor (design §6.2 `ingestion_monitor`, §7, §8.3).

Reads every collection's monitor entry (`monitors/ingestion/source=<id>/<day>/<run_id>.json`: records against the
card's expected band) and every collection manifest (`manifests/collect.<id>/`), and writes, as of D:
- `monitors/summary/as_of=<D>/days.parquet`: per source and day, the runs, failures, records and the worst flag;
- `monitors/summary/as_of=<D>/incidents.parquet`: failed runs, volumes outside the expected band, and gaps (a day
  since a daily source's onboarding with no passed collection).

The artefact checks hold candidates whose sources had an incident in their window (design §8.3). Counts and ids
only.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa

from .config import SourceCard
from .manifest import Manifest
from .store import Store
from .tables import upload, write_rows

log = logging.getLogger("moria.monitor")

COMMAND = "monitor.ingestion"
DAYS = pa.schema(
    [
        ("source", pa.string()),
        ("day", pa.date32()),
        ("cadence", pa.string()),
        ("runs", pa.int16()),
        ("failed", pa.int16()),
        ("records", pa.int64()),  # the largest passed run's
        ("flag", pa.string()),  # ok, below_expected, above_expected, failed (no passed run), or gap
    ]
)
INCIDENTS = pa.schema(
    [
        ("source", pa.string()),
        ("day", pa.date32()),
        ("kind", pa.string()),  # failed_run, below_expected, above_expected, gap
        ("run_id", pa.string()),
        ("detail", pa.string()),
    ]
)


def _day(m: dict) -> date | None:
    start = (m.get("params") or {}).get("window_start")
    if start:
        return date.fromisoformat(start[:10])
    return date(int(m["run_id"][:4]), int(m["run_id"][4:6]), int(m["run_id"][6:8]))


def summarise(entries: list[dict], manifests: list[dict], cards: dict[str, SourceCard],
              as_of: date) -> tuple[list[dict], list[dict]]:  # fmt: skip
    days: dict[tuple[str, date], dict] = {}
    incidents: list[dict] = []
    for e in entries:
        d = date.fromisoformat(e["day"])
        if d > as_of:
            continue
        slot = days.setdefault((e["source"], d), {"runs": set(), "failed": set(), "records": 0, "flags": set()})
        slot["runs"].add(e["run_id"])
        if e.get("status") == "passed":
            slot["records"] = max(slot["records"], int(e.get("records") or 0))
            slot["flags"].add(e.get("flag") or "ok")
            if e.get("flag") in ("below_expected", "above_expected"):
                incidents.append({"source": e["source"], "day": d, "kind": e["flag"], "run_id": e["run_id"],
                                  "detail": f"{e.get('records')} records; expected {e.get('expected')}"})  # fmt: skip
    for m in manifests:
        source = m["command"].removeprefix("collect.")
        d = _day(m)
        if d is None or d > as_of:
            continue
        slot = days.setdefault((source, d), {"runs": set(), "failed": set(), "records": 0, "flags": set()})
        slot["runs"].add(m["run_id"])
        if m["status"] != "passed":
            slot["failed"].add(m["run_id"])
            incidents.append({"source": source, "day": d, "kind": "failed_run", "run_id": m["run_id"],
                              "detail": (m.get("error") or m["status"])[:200]})  # fmt: skip
    rows = []
    passed_days: dict[str, set[date]] = defaultdict(set)
    for (source, d), slot in days.items():
        ok = len(slot["runs"]) > len(slot["failed"])
        if ok:
            passed_days[source].add(d)
        flags = slot["flags"]
        flag = ("failed" if not ok else "below_expected" if "below_expected" in flags
                else "above_expected" if "above_expected" in flags else "ok")  # fmt: skip
        card = cards.get(source)
        rows.append({"source": source, "day": d, "cadence": card.cadence if card else None, "runs": len(slot["runs"]),
                     "failed": len(slot["failed"]), "records": slot["records"], "flag": flag})  # fmt: skip
    # gaps: days since a daily source's first passed collection with no run at all (a day whose runs failed is an
    # incident already); as_of's own day is not over
    for source, ds in sorted(passed_days.items()):
        card = cards.get(source)
        if not card or card.cadence != "daily":
            continue
        d = min(ds)
        while d < as_of:
            if (source, d) not in days:
                rows.append({"source": source, "day": d, "cadence": "daily", "runs": 0, "failed": 0, "records": 0,
                             "flag": "gap"})  # fmt: skip
                incidents.append({"source": source, "day": d, "kind": "gap", "run_id": None,
                                  "detail": "no passed collection for this day"})  # fmt: skip
            d += timedelta(days=1)
    return rows, incidents


def monitor(store: Store, cards: dict[str, SourceCard], as_of: date, config_hash: str | None = None):
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        entries = [json.loads(store.get(k)) for k in store.list("monitors/ingestion/source=") if k.endswith(".json")]
        manifests = [json.loads(store.get(k)) for k in store.list("manifests/collect.") if k.endswith(".json")]
        rows, incidents = summarise(entries, manifests, cards, as_of)
        manifest.params = {"as_of": as_of.isoformat(), "monitor_entries": len(entries),
                           "collect_manifests": len(manifests)}  # fmt: skip
        prefix = f"monitors/summary/as_of={as_of.isoformat()}/"
        with tempfile.TemporaryDirectory(prefix="moria-monitor-") as tmp:
            write_rows(rows, DAYS, Path(tmp) / "days.parquet", ("source", "day"))
            write_rows(incidents, INCIDENTS, Path(tmp) / "incidents.parquet", ("source", "day", "kind", "run_id"))
            for name in ("days", "incidents"):
                upload(store, manifest, f"{prefix}{name}.parquet", Path(tmp) / f"{name}.parquet")
        counts: dict[str, int] = defaultdict(int)
        counts["source_days"] = len(rows)
        for i in incidents:
            counts[f"incidents_{i['kind']}"] += 1
        manifest.counts = dict(sorted(counts.items()))
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        cause = f"{COMMAND}: {type(e).__name__}: {first[:300]}"
        log.error("%s", cause)
        return "failed", manifest.finish(store, "failed", cause), {"error": cause}
