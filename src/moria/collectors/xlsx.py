"""Spreadsheet data cubes found on a release page: the ABS's business entries and exits (CABEE) and business R&D
(BERD), which the ABS Data API does not carry.

For each workbook source in the card, the adapter reads its "latest release" page (robots.txt honoured), finds the
workbook links matching the card's pattern, downloads each (size-capped), and reads every sheet whose name matches
`sheet_pattern` (by default the tables, not the contents or notes). Each table becomes one observation record,
kept faithfully rather than interpreted:
- `header_rows`: the column headings (spanned headings carried across the columns they cover), units last;
- `columns`: each value column's headings joined by " | ";
- `rows`: each data row's section (the latest label-only row above it, such as a year or "Employment size"), label
  and values. Numbers stay numbers; the ABS's symbols ("np", "-", "..") stay as text;
- `notes`: footnotes and the copyright line below the table.
The release date printed in the workbook ("Released at 11:30am (Canberra time) 18 August 2026") is the record's
`observable_at`. The record id is the workbook's name without its release suffix plus the sheet's name, so a table
re-published unchanged keeps its evidence id, and a new release is a new vintage (as for the ABS headline series).

Workbooks are untrusted input: their size, rows and columns are capped, and openpyxl parses their XML through
defusedxml.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from ..config import Strict
from ..discover import page_links
from ..http import FetchError
from ..records import RawRecord, make_envelope, sha256_hex, utc_now
from .base import CollectContext, CollectError

PARSER_VERSION = "xlsx-v1"
RELEASED = re.compile(r"Released at .*?(\d{1,2} [A-Z][a-z]+ \d{4})")

log = logging.getLogger("moria.collect.xlsx")


class XlsxSource(Strict):
    id: str  # Moria's name for the publication, e.g. "cabee"
    release_page: str  # the page that links the current workbooks, e.g. ABS's ".../latest-release"
    link_pattern: str  # a regular expression matched against each link's path
    sheet_pattern: str = r"^Table"


class XlsxParams(Strict):
    sources: list[XlsxSource]
    max_bytes: int = 20_000_000
    max_rows: int = 5000
    max_cols: int = 60


def _cell(value):
    if isinstance(value, str):
        value = " ".join(value.split())
        return value or None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value


def _release_date(text: str) -> str | None:
    for fmt in ("%d %B %Y", "%d %b %Y"):  # "18 August 2026", "22 Aug 2025"
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _is_number(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def read_table(rows: list[tuple]) -> dict:
    """One sheet's rows (values only) into header rows, columns, data rows and notes."""
    grid = [[_cell(v) for v in r] for r in rows]
    width = max((max((j for j, v in enumerate(r) if v is not None), default=-1) for r in grid), default=-1) + 1
    grid = [r[:width] + [None] * (width - len(r[:width])) for r in grid]
    first_data = next((i for i, r in enumerate(grid) if any(_is_number(v) for v in r[1:])), None)
    if first_data is None:
        raise CollectError("xlsx: a table without any numeric value")
    title = next((r[0] for r in grid[:first_data] if isinstance(r[0], str) and r[0].startswith("Table")), None)
    released = None
    for r in grid[:6]:
        for v in r:
            m = RELEASED.search(v) if isinstance(v, str) else None
            if m:
                released = _release_date(m.group(1))
    # header rows: above the first data row, with something in the value columns
    header_rows = [r[1:] for r in grid[:first_data] if any(v is not None for v in r[1:])]
    header_rows = [r for r in header_rows if not (r[0] and isinstance(r[0], str) and RELEASED.search(r[0]))]
    filled = []
    for depth, r in enumerate(header_rows):
        out, carry = [], None
        for v in r:
            if v is not None:
                carry = v
            # spanned headings carry right; the last header row (units, or the lowest heading) does not
            out.append(v if depth == len(header_rows) - 1 else (v if v is not None else carry))
        filled.append(out)
    columns = [" | ".join(str(r[j]) for r in filled if r[j] is not None) for j in range(width - 1)]
    section, data, notes, last_data = None, [], [], first_data
    # label-only rows between the header and the first data row are sections too
    start = max((i for i, r in enumerate(grid[:first_data]) if any(v is not None for v in r[1:])), default=-1) + 1
    for i in range(start, len(grid)):
        r = grid[i]
        values = r[1:]
        if any(v is not None for v in values) and r[0] is not None and any(_is_number(v) for v in values):
            data.append({"section": section, "label": r[0], "values": values})
            last_data = i
        elif r[0] is not None and all(v is None for v in values):
            section = r[0]
        elif any(v is not None for v in r):
            notes.append(" ".join(str(v) for v in r if v is not None))
    # label-only rows after the last data row are notes, not sections
    trailing = [r[0] for r in grid[last_data + 1 :] if r[0] is not None and all(v is None for v in r[1:])]
    notes = trailing + [n for n in notes if n not in trailing]
    return {
        "title": title,
        "released": released,
        "header_rows": header_rows,
        "columns": columns,
        "rows": data,
        "notes": notes,
        "n_rows": len(data),
        "n_values": sum(1 for d in data for v in d["values"] if v is not None),
    }


def _cube_id(url: str) -> str:
    # 81040DO005_202324.xlsx -> 81040DO005; 8165DC01.xlsx -> 8165DC01
    stem = urlsplit(url).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return re.sub(r"_\d{4,8}$", "", stem)


class XlsxCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = XlsxParams.model_validate(card.params)
        self.counts: dict[str, int] = {}

    def _workbook(self, ctx: CollectContext, source: XlsxSource, url: str) -> list[RawRecord]:
        import openpyxl  # imported here: only this adapter needs it

        resp = ctx.client.get(url, check_robots=True)
        data = resp.content
        if len(data) > self.params.max_bytes:
            raise CollectError(f"xlsx: {url.rsplit('/', 1)[-1]} is {len(data)} bytes, above the cap")
        retrieved_at = utc_now().isoformat(timespec="seconds")
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        pattern = re.compile(source.sheet_pattern)
        records = []
        try:
            # the workbook's release date, wherever it is printed (CABEE: only on its Contents sheet)
            released = None
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True, max_row=6, max_col=4):
                    for v in row:
                        m = RELEASED.search(v) if isinstance(v, str) else None
                        released = released or (_release_date(m.group(1)) if m else None)
            for ws in wb.worksheets:
                if not pattern.search(ws.title):
                    continue
                rows = list(ws.iter_rows(values_only=True, max_row=self.params.max_rows, max_col=self.params.max_cols))
                table = read_table(rows)
                table["released"] = table["released"] or released
                cube = _cube_id(url)
                payload = {
                    "source": source.id,
                    "workbook": url.rsplit("/", 1)[-1],
                    "url": url,
                    "release_path": urlsplit(url).path.rsplit("/", 2)[-2],
                    "workbook_sha256": sha256_hex(data),
                    "sheet": ws.title,
                    **table,
                }
                records.append(
                    RawRecord(
                        envelope=make_envelope(
                            provider=self.card.name,
                            source_collection=f"{self.card.id}_{source.id}",
                            provider_record_id=f"{cube}|{ws.title}",
                            kind="observation",
                            family=self.card.family,
                            rings=self.card.rings,
                            domains=self.card.domains,
                            # the workbook's hash is left out of the content: an unchanged table keeps its id
                            payload={k: v for k, v in payload.items() if k != "workbook_sha256"},
                            request={"url": url},
                            retrieval_method="http:xlsx",
                            tool_identity=f"moria:{PARSER_VERSION}",
                            licence=self.card.licence,
                            parser_version=PARSER_VERSION,
                            event_at=None,
                            observable_at=table["released"] or retrieved_at,
                            retrieved_at=retrieved_at,
                        ),
                        payload=payload,
                    )
                )
        finally:
            wb.close()
        return records

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        sources = self.params.sources[: ctx.limit] if ctx.limit else self.params.sources
        records: list[RawRecord] = []
        failed = 0
        for source in sources:
            try:
                page = ctx.client.get(source.release_page, check_robots=True)
            except FetchError as e:
                failed += 1
                ctx.warnings.append(f"xlsx: {source.id}'s release page not fetched: {e}")
                continue
            pattern = re.compile(source.link_pattern)
            links = sorted({urljoin(str(page.url), h) for h in page_links(page.text)
                            if pattern.search(urlsplit(urljoin(str(page.url), h)).path)})  # fmt: skip
            if not links:
                failed += 1
                ctx.warnings.append(f"xlsx: no workbook on {source.id}'s release page matches its pattern")
                continue
            got = 0
            for url in links:
                try:
                    found = self._workbook(ctx, source, url)
                except (FetchError, CollectError) as e:
                    ctx.warnings.append(f"xlsx: {url.rsplit('/', 1)[-1]} not read: {e}")
                    continue
                except Exception as e:  # a malformed or hostile workbook: skip it, loudly
                    ctx.warnings.append(f"xlsx: {url.rsplit('/', 1)[-1]} could not be read: {type(e).__name__}")
                    continue
                records.extend(found)
                got += 1
                self.counts[f"tables_{source.id}"] = self.counts.get(f"tables_{source.id}", 0) + len(found)
            self.counts[f"workbooks_{source.id}"] = got
            log.info("xlsx %s: %d of %d workbooks read", source.id, got, len(links))
            if not got:
                failed += 1
        if sources and failed == len(sources):
            raise CollectError(f"xlsx: every source failed ({failed}); first: {ctx.warnings[0]}")
        return records
