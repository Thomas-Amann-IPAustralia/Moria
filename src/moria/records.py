"""Evidence envelopes, canonical JSON, and raw bundles (design §6.1, §4.3).

A raw bundle is one zstd-compressed JSON-lines object per source per run, never one object per response, so R2's
operation counts stay small. Each line is {"envelope": {...}, "payload": ...}.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, date, datetime
from typing import Any, Literal

import zstandard
from pydantic import BaseModel, ConfigDict

Kind = Literal["document", "observation", "ipr_record"]


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(data: bytes | str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    provider: str
    source_collection: str
    provider_record_id: str
    kind: Kind
    family: str
    rings: list[str]
    domains: list[str]
    event_at: str | None
    observable_at: str | None
    provider_updated_at: str | None = None
    retrieved_at: str
    retrieval_method: str
    request_hash: str
    tool_identity: str
    content_hash: str
    licence: str
    parser_version: str


def make_envelope(
    *,
    provider: str,
    source_collection: str,
    provider_record_id: str,
    kind: Kind,
    family: str,
    rings: list[str],
    domains: list[str],
    payload: Any,
    request: dict[str, Any],
    retrieval_method: str,
    tool_identity: str,
    licence: str,
    parser_version: str,
    event_at: str | None,
    observable_at: str | None,
    provider_updated_at: str | None = None,
    retrieved_at: str | None = None,
) -> Envelope:
    content_hash = sha256_hex(canonical_json(payload))
    return Envelope(
        evidence_id=sha256_hex(f"{provider}|{provider_record_id}|{content_hash}"),
        provider=provider,
        source_collection=source_collection,
        provider_record_id=provider_record_id,
        kind=kind,
        family=family,
        rings=rings,
        domains=domains,
        event_at=event_at,
        observable_at=observable_at,
        provider_updated_at=provider_updated_at,
        retrieved_at=retrieved_at or utc_now().isoformat(timespec="seconds"),
        retrieval_method=retrieval_method,
        request_hash=sha256_hex(canonical_json(request)),
        tool_identity=tool_identity,
        content_hash=content_hash,
        licence=licence,
        parser_version=parser_version,
    )


class RawRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope: Envelope
    payload: Any


def encode_bundle(records: list[RawRecord]) -> bytes:
    """Lines sorted by evidence_id, so the same records always give the same bytes."""
    lines = sorted(canonical_json(r.model_dump(mode="json")) for r in records)
    raw = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    return zstandard.ZstdCompressor(level=10, write_checksum=True).compress(raw)


def decode_bundle(data: bytes) -> list[RawRecord]:
    with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data)) as reader:
        text = reader.read().decode("utf-8")
    return [RawRecord.model_validate(json.loads(line)) for line in text.splitlines() if line]


def bundle_key(source_id: str, day: date, run_id: str) -> str:
    return f"raw/{source_id}/{day:%Y/%m/%d}/{run_id}.jsonl.zst"
