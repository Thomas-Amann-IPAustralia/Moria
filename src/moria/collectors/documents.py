"""Documents read once (design §5.2): foresight syntheses and national strategies, fetched as PDF or HTML.

Each document in the card has its own licence. Its text is stored, page by page, only where `store_text` says the
licence allows it; otherwise the record keeps the title, publisher, URL, the file's SHA-256 and size, and its page
count (CLAUDE.md: a source whose licence is unclear is not stored as text). A document that can't be fetched is a
warning, so one blocked site doesn't lose the others; the run fails only when every document fails.

Owner uploads (D-014): some sites refuse cloud addresses, so the owner downloads those documents and puts them in the
private bucket at `inbox/documents/<document id>.pdf` (or `.html`). A document with an upload is read from it instead
of its URL; the record says so.

The licence check: every document's first and last pages are searched, in memory, for licence statements (Creative
Commons, the Open Government Licence, "all rights reserved", no reproduction, public domain). The statements found
and the verdict go in the record and the manifest. A document whose card allows its text but which itself reserves
all rights, with no open licence, is not stored as text, and the run warns.

PDFs are untrusted input: their size and page count are capped before any text is extracted.
"""

from __future__ import annotations

import io
import logging
import re
from typing import Literal

from pydantic import Field

from ..config import Strict
from ..http import FetchError
from ..records import RawRecord, make_envelope, sha256_hex
from .base import CollectContext, CollectError
from .sitemap import extract_page

PARSER_VERSION = "documents-v2"
INBOX = "inbox/documents/"
LICENCE_PAGES = (6, 4)  # the first and last pages searched for licence statements

log = logging.getLogger("moria.collect.documents")


class DocumentSpec(Strict):
    id: str
    title: str
    publisher: str
    published: str | None = None  # ISO date of publication, when known
    url: str
    licence: str
    # true, false, or if_open_licence: store the text only when the document itself states an open licence (for a
    # licence known so far only from search results or a site's general terms)
    store_text: bool | Literal["if_open_licence"]
    note: str = ""


class DocumentsParams(Strict):
    documents: list[DocumentSpec]
    max_bytes: int = 60_000_000
    max_pages: int = 1500
    max_text_chars: int = Field(default=3_000_000, description="Per document, after extraction")


_CC = re.compile(
    r"creativecommons\.org/licen[cs]es/(by(?:-nc)?(?:-nd)?(?:-sa)?)/(\d\.\d)"
    r"|creative\s+commons\s+attribution((?:[\s-]+(?:non-?commercial|no-?\s?derivatives|no-?\s?derivs|share-?\s?alike))*)"
    r"(?:[\s-]+(\d\.\d))?"
    r"|\bcc[\s-]by((?:[\s-](?:nc|nd|sa))*)(?:[\s-](\d\.\d))?",
    re.IGNORECASE,
)
_ANY_CC = re.compile(r"creative\s+commons", re.IGNORECASE)
_STATEMENTS = {
    "Open Government Licence": re.compile(r"open\s+government\s+licen[cs]e", re.IGNORECASE),
    "public domain": re.compile(r"\bpublic\s+domain\b", re.IGNORECASE),
    # the EU institutions' and agencies' standard notice (Commission Decision 2011/833/EU and its kin)
    "reuse authorised with acknowledgement": re.compile(
        r"(?:reproduction|reuse|re-use)\s+is\s+authori[sz]ed[,]?\s+provided\s+the\s+source\s+is\s+acknowledged",
        re.IGNORECASE,
    ),
    "all rights reserved": re.compile(r"\ball\s+rights\s+reserved\b", re.IGNORECASE),
    "no reproduction without permission": re.compile(
        r"(?:may\s+not|must\s+not|cannot)\s+be\s+(?:reproduced|copied)|no\s+part\s+of\s+this\s+"
        r"(?:publication|document|report|work)\s+may\s+be\s+(?:reproduced|copied)",
        re.IGNORECASE,
    ),
}
OPEN = ("CC BY", "Open Government Licence", "public domain", "reuse authorised with acknowledgement")
RESERVED = ("all rights reserved", "no reproduction without permission")


def _cc_name(m: re.Match) -> str:
    if m.group(1):  # a licence URL: creativecommons.org/licenses/by-nc/4.0
        return f"CC {m.group(1).upper()} {m.group(2)}"
    if m.group(0).lower().startswith("creative"):  # Creative Commons Attribution-NonCommercial 4.0
        mods, version = (m.group(3) or "").lower(), m.group(4)
    else:  # CC BY-NC 4.0
        mods, version = (m.group(5) or "").lower(), m.group(6)
    kinds = [k for k, rx in (("NC", r"nc\b|commercial"), ("ND", r"nd\b|deriv"), ("SA", r"sa\b|alike"))
             if re.search(rx, mods)]  # fmt: skip
    return "CC " + "-".join(["BY", *kinds]) + (f" {version}" if version else "")


def licence_statements(pages: list[str]) -> list[str]:
    """Licence statements in a document's first and last pages: Creative Commons licences by name and version, and
    the other statements above. Pattern names only, never the document's text."""
    head, tail = LICENCE_PAGES
    picked = pages if len(pages) <= head + tail else pages[:head] + pages[-tail:]
    text = " ".join(picked)
    found = {_cc_name(m) for m in _CC.finditer(text)}
    if not found and _ANY_CC.search(text):
        found.add("Creative Commons (unspecified)")
    found |= {name for name, rx in _STATEMENTS.items() if rx.search(text)}
    if any(f.startswith(("CC BY ", "CC BY-")) for f in found):
        found.discard("CC BY")  # a bare "CC BY" adds nothing beside a named version
    return sorted(found)


def licence_verdict(statements: list[str]) -> str:
    """open_licence: the document states an open licence (third-party exceptions are common, so it wins);
    rights_reserved: only restrictive statements; none_found: nothing either way."""
    if any(s.startswith(OPEN) for s in statements):
        return "open_licence"
    if any(s in RESERVED for s in statements):
        return "rights_reserved"
    return "none_found"


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
        self.counts: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1

    def _uploads(self, ctx: CollectContext) -> dict[str, str]:
        """document id -> its upload's key in the inbox"""
        if ctx.store is None:
            return {}
        out: dict[str, str] = {}
        for key in ctx.store.list(INBOX):
            name = key[len(INBOX) :]
            stem, _, ext = name.rpartition(".")
            if "/" not in name and ext.lower() in ("pdf", "html", "htm"):
                out[stem] = key
        return out

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
                request={"url": doc.url, "inbox_key": payload.get("inbox_key")},
                retrieval_method="upload:document" if payload.get("inbox_key") else "http:document",
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
        uploads = self._uploads(ctx)
        records, failed = [], 0
        for i, doc in enumerate(docs, start=1):
            inbox_key = uploads.get(doc.id)
            if inbox_key:
                data, final_url = ctx.store.get(inbox_key), None
                self._count("uploads_read")
            else:
                try:
                    resp = ctx.client.get(doc.url, retries=1)
                except FetchError as e:
                    failed += 1
                    ctx.warnings.append(f"documents: {doc.id} not fetched: {e}")
                    log.warning("documents [%d/%d] %s: not fetched (%s)", i, len(docs), doc.id, e)
                    continue
                data, final_url = resp.content, str(resp.url)
            if len(data) > self.params.max_bytes:
                failed += 1
                ctx.warnings.append(f"documents: {doc.id} is {len(data)} bytes, above the cap")
                continue
            is_pdf = data[:5] == b"%PDF-"
            try:
                if is_pdf:
                    pages = pdf_pages(data, self.params.max_pages)
                else:
                    pages = [extract_page(data.decode("utf-8", errors="replace"))["text"]]
            except Exception as e:  # a malformed or hostile file: skip it, loudly
                failed += 1
                ctx.warnings.append(f"documents: {doc.id} could not be read: {type(e).__name__}")
                continue
            statements = licence_statements(pages)
            verdict = licence_verdict(statements)
            self._count(f"licence_{verdict}")
            open_found = ", ".join(s for s in statements if s.startswith(OPEN))
            if doc.store_text == "if_open_licence":
                store_text = verdict == "open_licence"
                if not store_text:
                    ctx.warnings.append(f"documents: {doc.id} states no open licence ({verdict}); text not stored")
            else:
                store_text = doc.store_text
            if store_text and verdict == "rights_reserved":
                store_text = False
                ctx.warnings.append(
                    f"documents: {doc.id} states {', '.join(statements)} and no open licence, although its card "
                    "allows its text; text not stored until the licence is confirmed"
                )
            elif doc.store_text is False and verdict == "open_licence":
                ctx.warnings.append(
                    f"documents: {doc.id} states {open_found}; its card keeps metadata only, so the card may be "
                    "updated to store its text"
                )
            if inbox_key and not store_text:
                ctx.warnings.append(f"documents: {doc.id} was uploaded but its text is not stored; the upload stays in "
                                    f"{INBOX} until the licence is settled")  # fmt: skip
            chars = sum(len(p) for p in pages)
            payload = {
                "id": doc.id,
                "title": doc.title,
                "publisher": doc.publisher,
                "published": doc.published,
                "url": doc.url,
                "final_url": final_url,
                "obtained": "owner_upload" if inbox_key else "fetched",
                "inbox_key": inbox_key,
                "format": "pdf" if is_pdf else "html",
                "sha256": sha256_hex(data),
                "bytes": len(data),
                "pages": len(pages),
                "chars": chars,
                "licence_statements": statements,
                "licence_check": verdict,
                "text_stored": store_text,
                "note": doc.note,
            }
            if store_text:
                if chars > self.params.max_text_chars:
                    ctx.warnings.append(f"documents: {doc.id} text cut at {self.params.max_text_chars} characters")
                payload["page_texts"] = _cap(pages, self.params.max_text_chars)
            records.append(self._record(doc, payload))
            log.info("documents [%d/%d] %s: %s %s, %d pages, %d characters, licence %s, text %s", i, len(docs),
                     doc.id, payload["obtained"], payload["format"], len(pages), chars, verdict,
                     "stored" if store_text else "not stored")  # fmt: skip
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
