"""The documents collector, against a hand-built one-page PDF and an HTML page (placeholder text)."""

from __future__ import annotations

import json
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


def test_an_owner_upload_is_read_instead_of_the_url_and_its_licence_is_checked(http_cfg, store):
    store.put("inbox/documents/blocked.pdf", tiny_pdf("Placeholder text. Licensed under CC BY 4.0"), "application/pdf")
    seen: list[str] = []

    def recording(request):
        seen.append(request.url.path)
        return handler(request)

    c = docs_card(
        [doc("blocked", "https://docs.test/blocked.pdf", True), doc("open", "https://docs.test/open.pdf", True)]
    )
    r = run_collection(c, store, make_client(http_cfg, recording), Window.for_day(DAY))
    assert r.status == "passed", r.error
    assert seen == ["/open.pdf"]  # the upload replaced the refused fetch
    recs = {x.payload["id"]: x for x in decode_bundle(store.get(r.bundle_key))}
    up = recs["blocked"]
    assert up.payload["obtained"] == "owner_upload" and up.payload["inbox_key"] == "inbox/documents/blocked.pdf"
    assert up.payload["licence_statements"] == ["CC BY 4.0"] and up.payload["licence_check"] == "open_licence"
    assert up.payload["text_stored"] is True and up.envelope.retrieval_method == "upload:document"
    assert recs["open"].payload["obtained"] == "fetched" and recs["open"].payload["licence_check"] == "none_found"
    counts = json.loads(store.get(r.manifest_key))["counts"]
    assert counts["uploads_read"] == 1 and counts["licence_open_licence"] == 1 and counts["licence_none_found"] == 1


def test_a_document_that_reserves_its_rights_is_not_stored_as_text_whatever_its_card_says(http_cfg, store):
    store.put("inbox/documents/a.pdf", tiny_pdf("Copyright 2026 Placeholder. All rights reserved."), "application/pdf")
    store.put(
        "inbox/documents/b.pdf", tiny_pdf("Placeholder under the Open Government Licence v3.0"), "application/pdf"
    )
    store.put("inbox/documents/c.pdf", tiny_pdf("Placeholder under CC BY 4.0"), "application/pdf")
    store.put("inbox/documents/d.pdf", tiny_pdf("Placeholder with no statement"), "application/pdf")
    c = docs_card(
        [
            doc("a", "https://docs.test/a.pdf", True),
            doc("b", "https://docs.test/b.pdf", False),
            doc("c", "https://docs.test/c.pdf", "if_open_licence"),
            doc("d", "https://docs.test/d.pdf", "if_open_licence"),
        ]
    )
    r = run_collection(c, store, make_client(http_cfg, handler), Window.for_day(DAY))
    assert r.status == "passed", r.error
    recs = {x.payload["id"]: x.payload for x in decode_bundle(store.get(r.bundle_key))}
    assert recs["a"]["licence_check"] == "rights_reserved" and recs["a"]["text_stored"] is False
    assert "page_texts" not in recs["a"]
    assert recs["b"]["licence_statements"] == ["Open Government Licence"] and "page_texts" not in recs["b"]
    warnings = " ".join(r.warnings)
    assert "a states all rights reserved and no open licence" in warnings
    assert "b states Open Government Licence; its card keeps metadata only" in warnings
    assert "b was uploaded but its text is not stored" in warnings
    # if_open_licence: the document's own statement decides
    assert recs["c"]["text_stored"] is True and "page_texts" in recs["c"]
    assert recs["d"]["text_stored"] is False and "d states no open licence (none_found)" in warnings


def test_licence_statements_name_the_licence_and_never_quote_the_text():
    from moria.collectors.documents import licence_statements, licence_verdict

    cases = {
        "Licensed under a Creative Commons Attribution 4.0 International licence": ["CC BY 4.0"],
        "see creativecommons.org/licenses/by-nc-nd/4.0 for the terms": ["CC BY-NC-ND 4.0"],
        "Reproduction is authorised provided the source is acknowledged.": ["reuse authorised with acknowledgement"],
        "Placeholder. All rights reserved. No part of this publication may be reproduced": [
            "all rights reserved",
            "no reproduction without permission",
        ],
        "Nothing about licences": [],
    }
    for text, expected in cases.items():
        assert licence_statements([text]) == expected, text
    assert licence_verdict(["CC BY 4.0", "all rights reserved"]) == "open_licence"  # third-party exceptions are common
    pages = ["Licensed under CC BY 4.0"] + ["filler"] * 20 + ["All rights reserved"]
    assert licence_statements(pages) == ["CC BY 4.0", "all rights reserved"]  # first and last pages only
    assert licence_statements(["filler"] * 7 + ["CC BY 4.0"] + ["filler"] * 7) == []


def tiny_docx(paragraphs: list[str]) -> bytes:
    """A minimal Word file: only word/document.xml matters to the reader."""
    import io
    import zipfile

    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p[:5]}</w:t></w:r><w:r><w:t>{p[5:]}</w:t></w:r></w:p>" for p in paragraphs)
    field = '<w:p><w:r><w:instrText>TOC \\o "1-1"</w:instrText></w:r></w:p>'
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{w}"><w:body>{field}{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_an_upload_under_its_own_name_and_a_word_file_are_read(http_cfg, store):
    store.put("inbox/documents/Owner's Report.docx", tiny_docx(["Placeholder title", "Licensed under CC BY 4.0"]))
    store.put("inbox/documents/scan.pdf", tiny_pdf("No part may be reproduced by any process"))
    word = dict(doc("word_doc", "https://site.test/word", "if_open_licence"), upload="Owner's Report.docx")
    reserved = dict(doc("reserved_pdf", "https://site.test/scan", True), upload="scan.pdf")
    missing = dict(doc("missing", "https://site.test/open.pdf", False), upload="not there.pdf")
    r = run_collection(docs_card([word, reserved, missing]), store, make_client(http_cfg, handler), Window.for_day(DAY))
    assert r.status == "passed", r.error
    recs = {x.payload["id"]: x.payload for x in decode_bundle(store.get(r.bundle_key))}
    w = recs["word_doc"]
    assert (w["format"], w["obtained"], w["inbox_key"]) == (
        "docx",
        "owner_upload",
        "inbox/documents/Owner's Report.docx",
    )
    assert w["page_texts"] == ["Placeholder title Licensed under CC BY 4.0"]  # field codes are not text
    assert w["licence_statements"] == ["CC BY 4.0"] and w["text_stored"] is True
    p = recs["reserved_pdf"]
    assert p["licence_check"] == "rights_reserved" and p["text_stored"] is False and "page_texts" not in p
    assert recs["missing"]["obtained"] == "fetched"  # the named upload isn't there, so the URL is read
    assert any("'not there.pdf' is not in inbox/documents/" in w for w in r.warnings)


def test_licence_check_reads_the_reserved_and_permissive_wordings_of_government_publishers():
    from moria.collectors.documents import licence_statements, licence_verdict

    aic = ("no part of this publication may in any form or by any means (electronic, mechanical, photocopying) be "
           "reproduced, stored in a retrieval system")  # fmt: skip
    canada = ("the information in this publication may be reproduced, in part or in whole and by any means, without "
              "charge or further permission from the Department")  # fmt: skip
    assert licence_verdict(licence_statements([aic])) == "rights_reserved"
    assert licence_statements([canada]) == ["reproduction permitted without charge"]
    assert licence_verdict(licence_statements([canada])) == "open_licence"
