"""Documents read once (design §5.2): foresight syntheses and national strategies, fetched as PDF or HTML.

Each document in the card has its own licence. Its text is stored, page by page, only where `store_text` says the
licence allows it; otherwise the record keeps the title, publisher, URL, the file's SHA-256 and size, and its page
count (CLAUDE.md: a source whose licence is unclear is not stored as text). A document that can't be fetched is a
warning, so one blocked site doesn't lose the others; the run fails only when every document fails.

PDFs are untrusted input: their size and page count are capped before any text is extracted.
"""

from __future__ import annotations

import io
import logging

from pydantic import Field

from ..config import Strict
from ..http import FetchError
from ..records import RawRecord, make_envelope, sha256_hex
from .base import CollectContext, CollectError
from .sitemap import extract_page

PARSER_VERSION = "documents-v1"

log = logging.getLogger("moria.collect.documents")


class DocumentSpec(Strict):
    id: str
    title: str
    publisher: str
    published: str | None = None  # ISO date of publication, when known
    url: str
    licence: str
    store_text: bool
    note: str = ""


class DocumentsParams(Strict):
    documents: list[DocumentSpec]
    max_bytes: int = 60_000_000
    max_pages: int = 1500
    max_text_chars: int = Field(default=3_000_000, description="Per document, after extraction")


def pdf_pages(data: bytes, max_pages: int) -> list[str]:
    from pypdf import PdfReader  # imported here: only this adapter needs it

    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) > max_pages:
        raise CollectError(f"documents: {len(reader.pages)} pages, above the cap of {max_pages}")
    return [" ".join((page.extract_text() or "").split()) for page in reader.pages]


class DocumentsCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = DocumentsParams.model_validate(card.params)
        ids = [d.id for d in self.params.documents]
        if len(set(ids)) != len(ids):
            raise CollectError("documents: document ids must be unique")

    def _record(self, doc: DocumentSpec, payload: dict) -> RawRecord:
        return RawRecord(
            envelope=make_envelope(
                provider=doc.publisher,
                source_collection=self.card.id,
                provider_record_id=doc.id,
                kind="document",
                family=self.card.family,
                rings=self.card.rings,
                domains=self.card.domains,
                payload=payload,
                request={"url": doc.url},
                retrieval_method="http:document",
                tool_identity=f"moria:{PARSER_VERSION}",
                licence=doc.licence,
                parser_version=PARSER_VERSION,
                event_at=doc.published,
                observable_at=doc.published,
            ),
            payload=payload,
        )

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        docs = self.params.documents[: ctx.limit] if ctx.limit else self.params.documents
        records, failed = [], 0
        for i, doc in enumerate(docs, start=1):
            try:
                resp = ctx.client.get(doc.url, retries=1)
            except FetchError as e:
                failed += 1
                ctx.warnings.append(f"documents: {doc.id} not fetched: {e}")
                log.warning("documents [%d/%d] %s: not fetched (%s)", i, len(docs), doc.id, e)
                continue
            data = resp.content
            if len(data) > self.params.max_bytes:
                failed += 1
                ctx.warnings.append(f"documents: {doc.id} is {len(data)} bytes, above the cap")
                continue
            is_pdf = data[:5] == b"%PDF-"
            try:
                pages = pdf_pages(data, self.params.max_pages) if is_pdf else [extract_page(resp.text)["text"]]
            except Exception as e:  # a malformed or hostile file: skip it, loudly
                failed += 1
                ctx.warnings.append(f"documents: {doc.id} could not be read: {type(e).__name__}")
                continue
            chars = sum(len(p) for p in pages)
            payload = {
                "id": doc.id,
                "title": doc.title,
                "publisher": doc.publisher,
                "published": doc.published,
                "url": doc.url,
                "final_url": str(resp.url),
                "format": "pdf" if is_pdf else "html",
                "sha256": sha256_hex(data),
                "bytes": len(data),
                "pages": len(pages),
                "chars": chars,
                "text_stored": doc.store_text,
                "note": doc.note,
            }
            if doc.store_text:
                if chars > self.params.max_text_chars:
                    ctx.warnings.append(f"documents: {doc.id} text cut at {self.params.max_text_chars} characters")
                payload["page_texts"] = _cap(pages, self.params.max_text_chars)
            records.append(self._record(doc, payload))
            log.info("documents [%d/%d] %s: %s, %d pages, %d characters, text %s", i, len(docs), doc.id,
                     payload["format"], len(pages), chars, "stored" if doc.store_text else "not stored")  # fmt: skip
        if docs and failed == len(docs):
            raise CollectError(f"documents: every document failed ({failed}); first: {ctx.warnings[0]}")
        return records


def _cap(pages: list[str], limit: int) -> list[str]:
    out, used = [], 0
    for p in pages:
        if used >= limit:
            break
        out.append(p[: limit - used])
        used += len(out[-1])
    return out
