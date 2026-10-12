"""Collectors and the run that wraps each collection."""

from __future__ import annotations

import logging
import sys
import time
import traceback
from dataclasses import dataclass

from ..config import SourceCard
from ..http import FetchError, PoliteClient
from ..manifest import Manifest
from ..records import bundle_key, encode_bundle
from ..store import Store
from .abs import AbsSdmxCollector
from .base import CollectContext, CollectError, Window, monitor_entry
from .bigquery import BigQueryCpcCollector
from .documents import DocumentsCollector
from .feed import FeedCollector
from .gdelt import GdeltCollector
from .gkg import GkgCollector
from .legislation import LegislationCollector
from .openalex import OpenAlexCountsCollector
from .sitemap import SitemapCollector

ADAPTERS = {
    "abs_sdmx": AbsSdmxCollector,
    "bigquery_cpc": BigQueryCpcCollector,
    "documents": DocumentsCollector,
    "gdelt": GdeltCollector,
    "gdelt_gkg": GkgCollector,
    "feed": FeedCollector,
    "sitemap": SitemapCollector,
    "legislation": LegislationCollector,
    "openalex_counts": OpenAlexCountsCollector,
}

__all__ = ["ADAPTERS", "CollectError", "CollectResult", "Window", "run_collection"]

log = logging.getLogger("moria.collect")


@dataclass
class CollectResult:
    source: str
    status: str
    records: int
    manifest_key: str
    bundle_key: str | None
    warnings: list[str]
    error: str | None = None


def run_collection(
    card: SourceCard,
    store: Store,
    client: PoliteClient,
    window: Window,
    limit: int | None = None,
    config_hash: str | None = None,
) -> CollectResult:
    manifest = Manifest(
        command=f"collect.{card.id}",
        params={"window_start": window.start.isoformat(), "window_end": window.end.isoformat(), "limit": limit},
        config_hash=config_hash,
    )
    ctx = CollectContext(card=card, client=client, window=window, limit=limit, store=store)
    requests_before = client.requests
    outcomes_before = dict(client.outcomes)
    started = time.monotonic()
    log.info("%s: collecting %s (run %s)", card.id, window.day.isoformat(), manifest.run_id)

    def request_counts() -> dict[str, int]:
        # Requests made by this run, and their outcomes ("http_200", "http_429", "error_ReadTimeout", ...)
        counts = {"requests": client.requests - requests_before}
        for outcome, n in client.outcomes.items():
            if n - outcomes_before.get(outcome, 0):
                counts[f"requests_{outcome}"] = n - outcomes_before.get(outcome, 0)
        return counts

    collector = None
    try:
        collector = ADAPTERS[card.adapter](card)
        records = collector.collect(ctx)
        data = encode_bundle(records)
        key = bundle_key(card.id, window.day, manifest.run_id)
        store.put(key, data, "application/zstd")
        manifest.add_output(key, data)
        kinds: dict[str, int] = {}
        for r in records:
            kinds[r.envelope.kind] = kinds.get(r.envelope.kind, 0) + 1
        manifest.counts = {"records": len(records), **request_counts(), **kinds, **_collector_counts(collector)}
        monitor = monitor_entry(card, window, len(records), manifest.run_id, "passed")
        monitor_key = f"monitors/ingestion/source={card.id}/{window.day.isoformat()}/{manifest.run_id}.json"
        store.put(monitor_key, monitor, "application/json")
        manifest.add_output(monitor_key, monitor)
        if b'"flag":"ok"' not in monitor:
            ctx.warnings.append(f"ingestion monitor: {len(records)} records is outside the expected band")
        manifest.warnings = ctx.warnings
        mkey = manifest.finish(store, "passed")
        log.info(
            "%s: passed in %s, %d records, %d warnings, requests %s",
            card.id,
            _took(started),
            len(records),
            len(ctx.warnings),
            _summary(request_counts()),
        )
        return CollectResult(card.id, "passed", len(records), mkey, key, ctx.warnings)
    except Exception as e:
        if not isinstance(e, CollectError | FetchError):
            traceback.print_exc(file=sys.stderr)
        first_line = (str(e).splitlines() or [type(e).__name__])[0]
        cause = f"{card.id}: {type(e).__name__}: {first_line[:300]}"
        manifest.warnings = ctx.warnings
        manifest.counts = {**request_counts(), **_collector_counts(collector)}
        mkey = manifest.finish(store, "failed", cause)
        log.error(
            "%s: failed in %s, requests %s; cause: %s", card.id, _took(started), _summary(request_counts()), cause
        )
        return CollectResult(card.id, "failed", 0, mkey, None, ctx.warnings, cause)


def _collector_counts(collector) -> dict[str, int]:
    # A collector may report its own counts for the manifest, such as API credits used
    return dict(getattr(collector, "counts", None) or {})


def _took(started: float) -> str:
    seconds = int(time.monotonic() - started)
    return f"{seconds // 60}m{seconds % 60:02d}s"


def _summary(counts: dict[str, int]) -> str:
    detail = ", ".join(f"{k.removeprefix('requests_')}={v}" for k, v in sorted(counts.items()) if k != "requests")
    return f"{counts['requests']}" + (f" ({detail})" if detail else "")
