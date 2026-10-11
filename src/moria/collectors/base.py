"""The collector contract and the run that wraps every collection (SOP §16.1 stage contract).

A collector turns one source card and one UTC window into RawRecords. The run writes them as one immutable raw bundle,
records an ingestion-monitor entry (actual against expected volume), and writes a manifest, failed runs included.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol

from ..config import SourceCard
from ..http import PoliteClient
from ..records import RawRecord, canonical_json


@dataclass(frozen=True)
class Window:
    """A half-open UTC window [start, end). Daily collection uses one whole UTC day."""

    start: datetime
    end: datetime

    @classmethod
    def for_day(cls, day: date) -> Window:
        start = datetime.combine(day, time.min, tzinfo=UTC)
        return cls(start, start + timedelta(days=1))

    @property
    def day(self) -> date:
        return self.start.date()

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


@dataclass
class CollectContext:
    card: SourceCard
    client: PoliteClient
    window: Window
    limit: int | None = None
    warnings: list[str] = field(default_factory=list)


class Collector(Protocol):
    parser_version: str

    def collect(self, ctx: CollectContext) -> list[RawRecord]: ...


class CollectError(RuntimeError):
    """A collection that cannot complete. The message is one line naming the source and the cause."""


def monitor_entry(card: SourceCard, window: Window, n_records: int, run_id: str, status: str) -> bytes:
    band = card.expected_volume
    flag = "ok"
    if n_records < band.min_per_run:
        flag = "below_expected"
    elif n_records > band.max_per_run:
        flag = "above_expected"
    return canonical_json(
        {
            "source": card.id,
            "day": window.day.isoformat(),
            "run_id": run_id,
            "status": status,
            "records": n_records,
            "expected": band.model_dump(),
            "flag": flag,
        }
    ).encode("utf-8")
