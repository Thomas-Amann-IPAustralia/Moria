"""Collectors and the run that wraps each collection."""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass

from ..config import SourceCard
from ..http import FetchError, PoliteClient
from ..manifest import Manifest
from ..records import bundle_key, encode_bundle
from ..store import Store
from .base import CollectContext, CollectError, Window, monitor_entry
from .feed import FeedCollector
from .gdelt import GdeltCollector
from .legislation import LegislationCollector
from .sitemap import SitemapCollector

ADAPTERS = {
    "gdelt": GdeltCollector,
    "feed": FeedCollector,
    "sitemap": SitemapCollector,
    "legislation": LegislationCollector,
}

__all__ = ["ADAPTERS", "CollectError", "CollectResult", "Window", "run_collection"]


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
    ctx = CollectContext(card=card, client=client, window=window, limit=limit)
    requests_before = client.requests
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
        manifest.counts = {"records": len(records), "requests": client.requests - requests_before, **kinds}
        monitor = monitor_entry(card, window, len(records), manifest.run_id, "passed")
        monitor_key = f"monitors/ingestion/source={card.id}/{window.day.isoformat()}/{manifest.run_id}.json"
        store.put(monitor_key, monitor, "application/json")
        manifest.add_output(monitor_key, monitor)
        if b'"flag":"ok"' not in monitor:
            ctx.warnings.append(f"ingestion monitor: {len(records)} records is outside the expected band")
        manifest.warnings = ctx.warnings
        mkey = manifest.finish(store, "passed")
        return CollectResult(card.id, "passed", len(records), mkey, key, ctx.warnings)
    except Exception as e:
        if not isinstance(e, CollectError | FetchError):
            traceback.print_exc(file=sys.stderr)
        first_line = (str(e).splitlines() or [type(e).__name__])[0]
        cause = f"{card.id}: {type(e).__name__}: {first_line[:300]}"
        manifest.warnings = ctx.warnings
        manifest.counts = {"requests": client.requests - requests_before}
        mkey = manifest.finish(store, "failed", cause)
        return CollectResult(card.id, "failed", 0, mkey, None, ctx.warnings, cause)
