"""The documents collector, against a hand-built one-page PDF and an HTML page (placeholder text)."""

from __future__ import annotations

from datetime import date

import httpx

from moria.collectors import Window, run_collection
from moria.records import decode_bundle

from .conftest import card, make_client

DAY = date(2026, 10, 11)


def tiny_pdf(text: str) -> bytes:
    """A minimal valid one-page PDF showing `text`, with a correct cross-reference table."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def doc(id_: str, url: str, store_text: bool) -> dict:
    return {
        "id": id_,
        "title": f"Placeholder {id_}",
        "publisher": "Placeholder publisher",
        "published": "2026-01-01",
        "url": url,
        "licence": "placeholder licence",
        "store_text": store_text,
    }


def docs_card(documents, **params):
    return card("documents", {"documents": documents, **params}, cadence="once")


def handler(request):
    if request.url.path == "/open.pdf":
        return httpx.Response(200, content=tiny_pdf("Placeholder megatrend text"))
    if request.url.path == "/reserved.html":
        return httpx.Response(200, text="<html><title>T</title><body><p>Reserved placeholder text</p></body></html>")
    return httpx.Response(403)


def test_documents_store_text_only_where_the_licence_allows(http_cfg, store):
    c = docs_card(
        [
            doc("open", "https://docs.test/open.pdf", True),
            doc("reserved", "https://docs.test/reserved.html", False),
            doc("blocked", "https://docs.test/blocked.pdf", True),
        ]
    )
    r = run_collection(c, store, make_client(http_cfg, handler), Window.for_day(DAY))
    assert r.status == "passed", r.error
    recs = {x.payload["id"]: x for x in decode_bundle(store.get(r.bundle_key))}
    assert set(recs) == {"open", "reserved"}
    opened = recs["open"].payload
    assert opened["format"] == "pdf" and opened["pages"] == 1
    assert "Placeholder megatrend text" in opened["page_texts"][0]
    reserved = recs["reserved"].payload
    assert reserved["format"] == "html" and "page_texts" not in reserved and len(reserved["sha256"]) == 64
    assert reserved["chars"] > 0 and reserved["text_stored"] is False
    assert (
        recs["open"].envelope.observable_at == "2026-01-01" and recs["open"].envelope.licence == "placeholder licence"
    )
    assert any("blocked not fetched" in w for w in r.warnings)


def test_documents_fail_loudly_when_nothing_is_read(http_cfg, store):
    c = docs_card([doc("blocked", "https://docs.test/blocked.pdf", True)])
    r = run_collection(c, store, make_client(http_cfg, handler), Window.for_day(DAY))
    assert r.status == "failed" and "every document failed" in r.error

    capped = docs_card([doc("open", "https://docs.test/open.pdf", True)], max_bytes=100)
    r = run_collection(capped, store, make_client(http_cfg, handler), Window.for_day(DAY))
    assert r.status == "failed" and "above the cap" in r.error
