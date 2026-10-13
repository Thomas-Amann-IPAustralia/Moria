"""The list-page and spreadsheet adapters, against hand-built replicas (placeholder labels and numbers)."""

from __future__ import annotations

import io
from datetime import date

import httpx
import openpyxl
import pytest

from moria.collectors import Window, run_collection
from moria.collectors.base import CollectContext, CollectError
from moria.collectors.listpage import ListPageCollector
from moria.collectors.xlsx import read_table
from moria.records import decode_bundle

from .conftest import card, make_client

DAY = date(2026, 10, 9)

# A WIPO Lex-like notification table
TABLE_PAGE = """<html><body><table><thead><tr><th>No</th><th>Title</th><th>Treaty</th><th>Date</th></tr></thead><tbody>
<tr><td data-sort="2"><div>2</div></td>
<td><div><a href="/notes/details/t_2">Accession by Placeholder&nbsp;Land</a></div></td>
<td><div>Placeholder Treaty</div></td><td data-sort="1"><div>October 5, 2026</div></td></tr>
<tr><td data-sort="1"><div>1</div></td>
<td><div><a href="/notes/details/t_1">Ratification by <b>Elsewhere</b></a></div></td>
<td><div>Placeholder Treaty</div></td><td data-sort="1"><div>March 1, 2001</div></td></tr>
</tbody></table></body></html>"""
TABLE_PATTERN = (
    r'<tr>\s*<td[^>]*><div>(?P<number>[^<]*)</div></td>\s*<td><div><a href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r"</div></td>\s*<td><div>[^<]*</div></td>\s*<td[^>]*><div>(?P<date>[A-Za-z]+ \d{1,2}, \d{4})</div></td>\s*</tr>"
)
# A news board whose items link through a script call
BOARD_PAGE = """<div class="board_list">
<p class="btit"><a href="#_" onclick="javascript:detail('12','news');">Placeholder headline</a></p>
<p class="bdate"><span class="cc_99">October 8, 2026</span></p><p class="bcon"><span>Placeholder summary</span></p>
</div>"""
BOARD_PATTERN = (
    r'<p class="btit">.*?detail\(\'(?P<id>\d+)\',\'news\'\);">(?P<title>.*?)</a></p>\s*<p class="bdate"><span[^>]*>'
    r'(?P<date>[A-Za-z]+ \d{1,2}, \d{4})</span></p><p class="bcon"><span>(?P<summary>.*?)</span></p>'
)


def page_handler(pages: dict[str, str]):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        body = pages.get(request.url.path)
        return httpx.Response(200, text=body) if body is not None else httpx.Response(404)

    return handler


def test_listpage_reads_a_notification_table_within_the_lookback(http_cfg):
    params = {
        "pages": [{"id": "t", "url": "https://lex.test/list", "label": "Placeholder Treaty"}],
        "item_pattern": TABLE_PATTERN,
        "date_format": "%B %d, %Y",
        "lookback_days": 30,
    }
    c = card("listpage", params)
    ctx = CollectContext(
        card=c, client=make_client(http_cfg, page_handler({"/list": TABLE_PAGE})), window=Window.for_day(DAY)
    )
    [rec] = ListPageCollector(c).collect(ctx)
    p = rec.payload
    assert p["title"] == "Accession by Placeholder Land" and p["number"] == "2" and p["date"] == "2026-10-05"
    assert p["link"] == "https://lex.test/notes/details/t_2" and rec.envelope.observable_at == "2026-10-05"
    assert "summary" not in p and p["page_label"] == "Placeholder Treaty"

    ctx.backfill = True
    recs = ListPageCollector(c).collect(ctx)
    assert sorted(r.payload["title"] for r in recs) == ["Accession by Placeholder Land", "Ratification by Elsewhere"]


def test_listpage_builds_links_from_ids_and_keeps_summaries_only_when_allowed(http_cfg):
    params = {
        "pages": [{"id": "news", "url": "https://board.test/list"}],
        "item_pattern": BOARD_PATTERN,
        "date_format": "%B %d, %Y",
        "link_template": "https://board.test/detail?seq={id}",
    }
    for keep in (False, True):
        c = card("listpage", {**params, "keep_summary": keep})
        client = make_client(http_cfg, page_handler({"/list": BOARD_PAGE}))
        [rec] = ListPageCollector(c).collect(CollectContext(card=c, client=client, window=Window.for_day(DAY)))
        assert rec.envelope.provider_record_id == "https://board.test/detail?seq=12"
        assert ("summary" in rec.payload) is keep


def test_listpage_fails_loudly_when_nothing_matches(http_cfg, store):
    params = {"pages": [{"id": "a", "url": "https://lex.test/list"}], "item_pattern": TABLE_PATTERN,
              "date_format": "%B %d, %Y"}  # fmt: skip
    c = card("listpage", params)
    r = run_collection(c, store, make_client(http_cfg, page_handler({"/list": "<p>changed</p>"})), Window.for_day(DAY))
    assert r.status == "failed" and "no page yielded any item" in r.error
    with pytest.raises(ValueError, match="named groups"):
        ListPageCollector(card("listpage", {**params, "item_pattern": "(?P<title>x)"}))


def workbook(released: str | None = "Released at 11:30am (Canberra time) 18 August 2026") -> bytes:
    wb = openpyxl.Workbook()
    contents = wb.active
    contents.title = "Contents"
    contents.append(["Placeholder publication"])
    if released:
        contents.append([released])
    t = wb.create_sheet("Table 1")
    t.append(["Table 1: Placeholder counts"])
    t.append([None, "Group A", None, "Group B"])
    t.append([None, "Opening", "Entries", "Opening"])
    t.append([None, "no.", "no.", "%"])
    t.append(["2024-25"])
    t.append(["Placeholder industry", 100, 7.0, "np"])
    t.append(["Other industry", 50, None, 1.5])
    t.append(["2025-26"])
    t.append(["Placeholder industry", 101, 8, 2.5])
    t.append([None, "(a) A placeholder footnote"])
    t.append(["© Placeholder"])
    wb.create_sheet("Further information").append(["Placeholder"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


RELEASE_PAGE = """<html><body><a href="/stats/pub/2026/1234DC01.xlsx">Data cube</a>
<a href="/stats/pub/2026/other.pdf">PDF</a></body></html>"""


def test_xlsx_reads_each_table_with_its_release_date(http_cfg, store):
    data = workbook()

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/stats/pub/latest":
            return httpx.Response(200, text=RELEASE_PAGE)
        if request.url.path.endswith(".xlsx"):
            return httpx.Response(200, content=data)
        return httpx.Response(404)

    params = {"sources": [{"id": "pub", "release_page": "https://abs.test/stats/pub/latest",
                           "link_pattern": r"/1234DC\d+\.xlsx$"}]}  # fmt: skip
    c = card("xlsx", params, id="cubes", family="statistics", cadence="weekly")
    r = run_collection(c, store, make_client(http_cfg, handler), Window.for_day(DAY))
    assert r.status == "passed", r.error
    [rec] = decode_bundle(store.get(r.bundle_key))
    p = rec.payload
    assert rec.envelope.kind == "observation" and rec.envelope.provider_record_id == "1234DC01|Table 1"
    assert rec.envelope.observable_at == "2026-08-18" and p["release_path"] == "2026"
    assert p["columns"] == ["Group A | Opening | no.", "Group A | Entries | no.", "Group B | Opening | %"]
    assert p["rows"] == [
        {"section": "2024-25", "label": "Placeholder industry", "values": [100, 7, "np"]},
        {"section": "2024-25", "label": "Other industry", "values": [50, None, 1.5]},
        {"section": "2025-26", "label": "Placeholder industry", "values": [101, 8, 2.5]},
    ]
    assert p["notes"] == ["© Placeholder", "(a) A placeholder footnote"] and p["n_values"] == 8

    # the same tables again keep their evidence ids, though the workbook's bytes differ
    again = run_collection(c, store, make_client(http_cfg, handler), Window.for_day(DAY))
    [rec2] = decode_bundle(store.get(again.bundle_key))
    assert rec2.envelope.evidence_id == rec.envelope.evidence_id


def test_xlsx_table_without_numbers_is_refused():
    with pytest.raises(CollectError):
        read_table([("Table 1",), (None, "A"), ("label", "text")])


def test_xlsx_without_a_matching_workbook_fails(http_cfg, store):
    def handler(request):
        return httpx.Response(404) if request.url.path == "/robots.txt" else httpx.Response(200, text="<p>none</p>")

    params = {"sources": [{"id": "pub", "release_page": "https://abs.test/latest", "link_pattern": r"\.xlsx$"}]}
    c = card("xlsx", params)
    r = run_collection(c, store, make_client(http_cfg, handler), Window.for_day(DAY))
    assert r.status == "failed" and "no workbook" in r.error


def zip_of_csvs(rows: str = "2021,AU,US,1,5\n2022,AU,AU,2,7\n") -> bytes:
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("indicator_by_class.csv", "year,office,origin,class_id,count\n" + rows)
        zf.writestr("names.xlsx", b"not converted")
    return buf.getvalue()


def test_zip_csv_goes_to_the_lake_and_skips_unchanged_files(http_cfg, store):
    import json

    from moria.bulk import refresh
    from moria.census import census_markdown

    data = {"v": zip_of_csvs()}

    def handler(request):
        return httpx.Response(200, content=data["v"], headers={"Last-Modified": "Mon, 15 Apr 2024 10:23:46 GMT"})

    c = card("zip_csv", {"files": [{"id": "marks", "url": "https://stats.test/marks.zip"}]}, id="stats",
             family="statistics", cadence="once", expected_volume={"min_per_run": 1, "max_per_run": 10})  # fmt: skip
    r = refresh(c, store, make_client(http_cfg, handler))
    assert r.status == "passed", r.error
    assert r.records == 2 and store.list("lake/") == ["lake/stats/release=2024-04-15/marks__indicator_by_class.parquet"]
    release = json.loads(store.get("raw/stats/2024-04-15/manifest.json"))
    table = release["tables"]["marks__indicator_by_class"]
    assert table["rows"] == 2 and [c for c, _ in table["columns"]] == ["year", "office", "origin", "class_id", "count"]
    assert release["files"]["marks"]["not_converted"] == ["names.xlsx"]
    text = census_markdown(store, c)
    assert "| marks__indicator_by_class | 2 | year, office, origin, class_id, count | 2021 to 2022 | 2 | 1 |" in text

    again = refresh(c, store, make_client(http_cfg, handler))
    assert again.status == "passed" and again.records == 0 and "unchanged" in again.warnings[0]

    data["v"] = zip_of_csvs("2023,AU,AU,2,9\n")  # changed content under the same Last-Modified date: a person looks
    changed = refresh(c, store, make_client(http_cfg, handler))
    assert changed.status == "failed" and "a person should look" in changed.error


def test_census_of_lists_and_tables_shows_no_titles(http_cfg, store):
    from moria.census import census_markdown

    params = {"pages": [{"id": "t", "url": "https://lex.test/list"}], "item_pattern": TABLE_PATTERN,
              "date_format": "%B %d, %Y"}  # fmt: skip
    c = card("listpage", params, id="notes")
    client = make_client(http_cfg, page_handler({"/list": TABLE_PAGE}))
    assert run_collection(c, store, client, Window.for_day(DAY), backfill=True).status == "passed"
    text = census_markdown(store, c)
    assert "| t | 2 | 2001-03-01 | 2026-10-05 |" in text and "Placeholder Land" not in text
