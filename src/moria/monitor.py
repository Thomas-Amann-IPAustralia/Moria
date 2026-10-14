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
    try:
        return date(int(m["run_id"][:4]), int(m["run_id"][4:6]), int(m["run_id"][6:8]))
    except ValueError:
        return None


def _band_flag(records: int, card: SourceCard | None, recorded: str | None) -> str:
    """A run's volume against the card's current band (a band revised after a run applies to it too)."""
    if card is None:
        return recorded or "ok"
    band = card.expected_volume
    return "below_expected" if records < band.min_per_run else "above_expected" if records > band.max_per_run else "ok"


def summarise(entries: list[dict], manifests: list[dict], cards: dict[str, SourceCard],
              as_of: date) -> tuple[list[dict], list[dict]]:  # fmt: skip
    """One row per source and day, judged by the day's best passed run (the most records: a dry run or a failure
    followed by a good run the same day is not an incident); its incident if that run is outside the card's band
    (daily and weekly collections only: a monthly or one-off source has no volume per day), or if every run failed.
    A snapshot is above the daily band by design: a source's first day, and a `--backfill` run. A daily source's
    day with no run is a gap, from its first day to two days before as_of (day D is collected early on D + 1).
    A run's monitor entry gives its day (a bulk release is filed under its release date) and records."""
    days: dict[tuple[str, date], dict] = defaultdict(lambda: {"passed": {}, "failed": {}})
    with_entry = set()
    for e in entries:
        with_entry.add(e["run_id"])
        d = date.fromisoformat(e["day"])
        if d <= as_of and e.get("status") == "passed":
            days[(e["source"], d)]["passed"][e["run_id"]] = int(e.get("records") or 0)
    backfills = {m["run_id"] for m in manifests if (m.get("params") or {}).get("backfill")}
    for m in manifests:
        if m["status"] == "passed" and m["run_id"] in with_entry:
            continue  # its monitor entry gives its day and records
        source, d = m["command"].removeprefix("collect."), _day(m)
        if d is None or d > as_of:
            continue
        if m["status"] != "passed":
            days[(source, d)]["failed"][m["run_id"]] = (m.get("error") or m["status"])[:200]
        else:
            counts = m.get("counts") or {}
            days[(source, d)]["passed"].setdefault(m["run_id"], int(counts.get("records", counts.get("rows")) or 0))
    first = {}
    for (source, d), slot in days.items():
        if slot["passed"]:
            first[source] = min(first.get(source, d), d)
    rows, incidents = [], []
    for (source, d), slot in sorted(days.items()):
        card = cards.get(source)
        if slot["passed"]:
            run, records = max(slot["passed"].items(), key=lambda kv: (kv[1], kv[0]))
            flag = _band_flag(records, card, None) if card is None or card.cadence in ("daily", "weekly") else "ok"
            if flag == "above_expected" and (d == first.get(source) or run in backfills):
                flag = "ok"  # a snapshot
            if flag != "ok":
                band = card.expected_volume.model_dump() if card else None
                incidents.append({"source": source, "day": d, "kind": flag, "run_id": run,
                                  "detail": f"{records} records; expected {band}"})  # fmt: skip
        else:
            run, error = sorted(slot["failed"].items())[-1]
            records, flag = 0, "failed"
            incidents.append({"source": source, "day": d, "kind": "failed_run", "run_id": run, "detail": error})
        rows.append({"source": source, "day": d, "cadence": card.cadence if card else None,
                     "runs": len(slot["passed"]) + len(slot["failed"]), "failed": len(slot["failed"]),
                     "records": records, "flag": flag})  # fmt: skip
    for source, start in sorted(first.items()):
        card = cards.get(source)
        if not card or card.cadence != "daily":
            continue
        d = start
        while d < as_of - timedelta(days=1):
            if (source, d) not in days:
                rows.append({"source": source, "day": d, "cadence": "daily", "runs": 0, "failed": 0, "records": 0,
                             "flag": "gap"})  # fmt: skip
                incidents.append({"source": source, "day": d, "kind": "gap", "run_id": None,
                                  "detail": "no collection for this day"})  # fmt: skip
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
