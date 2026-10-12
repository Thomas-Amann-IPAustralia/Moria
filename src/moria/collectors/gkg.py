"""GDELT Global Knowledge Graph (GKG 2.1) bulk files: the news scan without the rate-limited DOC API (D-009, D-010).

GDELT publishes one GKG file every 15 minutes at data.gdeltproject.org. A UTC day is the 96 files stamped inside it.
Every English web document in them is matched against the query groups (`moria terms`) in its title, URL, quotations
and named entities. Matching documents are kept; the rest only count towards the day's totals.

What is stored (design §12: news is titles, URLs and metadata, never article text):
- per matching document: URL, domain, title, GDELT's timestamps, which groups and phrases matched and in which fields,
  and GDELT's own metadata, which it derives from the full text: themes, organisations, location countries and tone;
- per group and scope (worldwide English, `.au` domains): matching documents and all documents that day.

Quotations are article text, so they are searched in memory and never stored. Person names and page authors are not
stored either.
"""

from __future__ import annotations

import html
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from pydantic import Field

from ..http import FetchError
from ..records import RawRecord, make_envelope
from .base import CollectContext, CollectError
from .gdelt import QueryGroupParams, build_groups

PARSER_VERSION = "gdelt-gkg-v1"
FILE_INTERVAL = timedelta(minutes=15)
MATCH_FIELDS = ("title", "url", "quotations", "names")

log = logging.getLogger("moria.collect.gkg")

# GKG 2.1 columns (tab-separated, 27 per row)
C_DATE, C_COLLECTION, C_DOMAIN, C_URL = 1, 2, 3, 4
C_THEMES, C_LOCATIONS, C_ORGS, C_TONE, C_QUOTES, C_NAMES, C_EXTRAS = 7, 10, 14, 15, 22, 23, 26
N_COLUMNS = 27
WEB = "1"  # source collection 1 is the open web


class GkgParams(QueryGroupParams):
    base_url: str = "https://data.gdeltproject.org/gdeltv2"
    match_fields: list[str] = Field(default_factory=lambda: list(MATCH_FIELDS))
    max_missing_files: int = 4  # GDELT occasionally skips a 15-minute file; more than this fails the run
    max_title_chars: int = 500


_SEPARATORS = re.compile(r"[\W_]+")


def _words(text: str) -> str:
    # Lower case, with every run of non-letters and non-digits (spaces, punctuation, hyphens, underscores in URL slugs)
    # turned into one space, padded so " phrase " matches whole words only.
    return f" {_SEPARATORS.sub(' ', text.lower()).strip()} "


class PhraseMatcher:
    """Whole-word, case-insensitive phrase matching. Candidates are looked up by first word, then checked as
    substrings of the normalised text: fast enough for a day's 65k documents in pure Python."""

    def __init__(self, groups):
        self.groups_by_phrase: dict[str, list[str]] = {}
        for g in groups:
            for p in g.phrases:
                self.groups_by_phrase.setdefault(p.lower(), []).append(g.group_id)
        self._by_first_word: dict[str, list[tuple[str, str]]] = {}  # first word -> [(normalised, phrase)]
        for phrase in self.groups_by_phrase:
            normalised = _words(phrase)
            if normalised.strip():
                self._by_first_word.setdefault(normalised.split()[0], []).append((normalised, phrase))

    def phrases_in(self, text: str) -> set[str]:
        if not text:
            return set()
        normalised = _words(text)
        found = set()
        for word in set(normalised.split()) & self._by_first_word.keys():
            found.update(phrase for n, phrase in self._by_first_word[word] if n in normalised)
        return found


@dataclass
class GroupCounts:
    world: int = 0
    au: int = 0
    by_field: dict[str, int] = field(default_factory=dict)


def _gkg_time(value: str) -> str | None:
    try:
        return datetime.strptime(value.strip(), "%Y%m%d%H%M%S").replace(tzinfo=UTC).isoformat()
    except ValueError:
        return None


def _extra(extras: str, tag: str) -> str:
    m = re.search(f"<{tag}>(.*?)</{tag}>", extras, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def _names(value: str) -> list[str]:
    # "name,offset;name,offset": a name may itself contain commas, so split on the last one
    return [e.rsplit(",", 1)[0] for e in value.split(";") if e]


def _quotes(value: str) -> list[str]:
    # "offset|length|verb|quote#offset|length|verb|quote"
    return [e.split("|", 3)[3] for e in value.split("#") if e.count("|") >= 3]


def _countries(value: str) -> list[str]:
    # "type#name#country#adm1#adm2#lat#lon#feature#offset;..." -> GDELT's FIPS country codes
    out = set()
    for e in value.split(";"):
        parts = e.split("#")
        if len(parts) >= 3 and parts[2]:
            out.add(parts[2])
    return sorted(out)


def _tone(value: str) -> dict[str, float | int] | None:
    parts = value.split(",")
    try:
        return {"tone": round(float(parts[0]), 3), "word_count": int(float(parts[6]))}
    except (IndexError, ValueError):
        return None


def file_stamps(ctx: CollectContext) -> list[str]:
    stamps, moment = [], ctx.window.start
    while moment < ctx.window.end:
        stamps.append(moment.strftime("%Y%m%d%H%M%S"))
        moment += FILE_INTERVAL
    return stamps


class GkgCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = GkgParams.model_validate(card.params)
        unknown = set(self.params.match_fields) - set(MATCH_FIELDS)
        if unknown:
            raise CollectError(f"gkg: unknown match_fields {sorted(unknown)}; allowed: {list(MATCH_FIELDS)}")

    def _download(self, ctx: CollectContext, stamp: str) -> str | None:
        """The file's text, or None when GDELT never published it (404)."""
        url = f"{self.params.base_url}/{stamp}.gkg.csv.zip"
        resp = ctx.client.get(url, ok_statuses=(200, 404))
        if resp.status_code == 404:
            return None
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                members = zf.namelist()
                if len(members) != 1:
                    raise CollectError(f"gkg: {stamp} holds {len(members)} files, expected 1")
                return zf.read(members[0]).decode("utf-8", errors="replace")  # zipfile checks the CRC
        except zipfile.BadZipFile as e:
            raise CollectError(f"gkg: {stamp} is not a valid zip: {e}") from e

    def collect(self, ctx: CollectContext) -> list[RawRecord]:
        groups = build_groups(self.params)
        matcher = PhraseMatcher(groups)
        fields = self.params.match_fields
        stamps = file_stamps(ctx)
        if ctx.limit:
            stamps = stamps[: ctx.limit]
        counts = {g.group_id: GroupCounts() for g in groups}
        totals = {"world": 0, "au": 0}
        seen: set[str] = set()
        docs: list[RawRecord] = []
        missing: list[str] = []
        malformed = 0
        log.info("gkg: %d files, %d query groups, matching in %s", len(stamps), len(groups), ", ".join(fields))
        for i, stamp in enumerate(stamps, start=1):
            try:
                text = self._download(ctx, stamp)
            except FetchError as e:
                raise CollectError(f"gkg: file {stamp} could not be fetched: {e}") from e
            if text is None:
                missing.append(stamp)
                log.warning("gkg [%d/%d] %s: not published by GDELT (404)", i, len(stamps), stamp)
                continue
            n_docs = n_matches = 0
            for line in text.split("\n"):
                if not line.strip():
                    continue
                row = line.rstrip("\r").split("\t")
                if len(row) != N_COLUMNS:
                    malformed += 1
                    continue
                url = row[C_URL].strip()
                if row[C_COLLECTION] != WEB or not url or url in seen:
                    continue
                seen.add(url)
                domain = row[C_DOMAIN].strip().lower()
                au = domain.endswith(".au")
                totals["world"] += 1
                totals["au"] += au
                n_docs += 1
                record = self._match(ctx, row, url, domain, au, matcher, fields, counts)
                if record is not None and self.params.articles:
                    docs.append(record)
                    n_matches += 1
            log.info("gkg [%d/%d] %s: %d documents, %d matched", i, len(stamps), stamp, n_docs, n_matches)

        if missing:
            ctx.warnings.append(f"gkg: {len(missing)} of {len(stamps)} files not published: {', '.join(missing)}")
        if malformed:
            ctx.warnings.append(f"gkg: {malformed} rows skipped without {N_COLUMNS} columns")
        if len(missing) > self.params.max_missing_files or len(missing) == len(stamps):
            raise CollectError(
                f"gkg: {len(missing)} of {len(stamps)} files missing (allowed {self.params.max_missing_files})"
            )
        log.info(
            "gkg: %d documents (%d from .au domains), %d matched at least one group",
            totals["world"],
            totals["au"],
            len(docs),
        )
        return docs + self._volumes(ctx, groups, counts, totals, len(stamps) - len(missing), len(stamps))

    def _match(self, ctx, row, url, domain, au, matcher, fields, counts) -> RawRecord | None:
        extras = row[C_EXTRAS]
        title = _extra(extras, "PAGE_TITLE")
        texts = {
            "title": title,
            "url": url,
            "quotations": " \n ".join(_quotes(row[C_QUOTES])),
            "names": " ; ".join(_names(row[C_NAMES])),
        }
        hits: dict[str, set[str]] = {}  # phrase -> fields
        for f in fields:
            for phrase in matcher.phrases_in(texts[f]):
                hits.setdefault(phrase, set()).add(f)
        if not hits:
            return None
        matches = sorted(
            (
                {"group": gid, "phrase": phrase, "fields": sorted(fs)}
                for phrase, fs in hits.items()
                for gid in matcher.groups_by_phrase[phrase]
            ),
            key=lambda m: (m["group"], m["phrase"]),
        )
        for gid in sorted({m["group"] for m in matches}):
            c = counts[gid]
            c.world += 1
            c.au += au
            for f in sorted({f for m in matches if m["group"] == gid for f in m["fields"]}):
                c.by_field[f] = c.by_field.get(f, 0) + 1
        payload = {
            "url": url,
            "domain": domain,
            "au_domain": au,
            "title": title[: self.params.max_title_chars],
            "gkg_date": _gkg_time(row[C_DATE]),
            "published_at": _gkg_time(_extra(extras, "PAGE_PRECISEPUBTIMESTAMP")),
            "query_groups": sorted({m["group"] for m in matches}),
            "matches": matches,
            "themes": sorted({t for t in row[C_THEMES].split(";") if t}),
            "organisations": sorted(set(_names(row[C_ORGS]))),
            "location_countries": _countries(row[C_LOCATIONS]),
            "tone": _tone(row[C_TONE]),
            "has_quotations": bool(texts["quotations"]),
        }
        return RawRecord(
            envelope=make_envelope(
                provider=domain or "unknown",
                source_collection="gdelt_gkg_v2",
                provider_record_id=url,
                kind="document",
                family=self.card.family,
                rings=self.card.rings,
                domains=self.card.domains,
                payload=payload,
                request={"file": row[C_DATE].strip(), "base_url": self.params.base_url},
                retrieval_method="bulk:gdelt_gkg_v2",
                tool_identity=f"moria:{PARSER_VERSION}",
                licence=self.card.licence,
                parser_version=PARSER_VERSION,
                event_at=payload["published_at"],
                observable_at=payload["gkg_date"],
            ),
            payload=payload,
        )

    def _volumes(self, ctx, groups, counts, totals, files_read, files_expected) -> list[RawRecord]:
        records = []
        for g in groups:
            c = counts[g.group_id]
            for scope in self.params.volume_scopes:
                payload = {
                    "query_group": g.group_id,
                    "scope": scope,
                    "matching_documents": c.world if scope == "world" else c.au,
                    "total_documents": totals[scope],
                    "matches_by_field": dict(sorted(c.by_field.items())) if scope == "world" else None,
                    "files_read": files_read,
                    "files_expected": files_expected,
                }
                records.append(
                    RawRecord(
                        envelope=make_envelope(
                            provider="The GDELT Project",
                            source_collection="gdelt_gkg_v2_volume",
                            provider_record_id=f"{g.group_id}|{scope}|{ctx.window.day.isoformat()}",
                            kind="observation",
                            family=self.card.family,
                            rings=self.card.rings,
                            domains=self.card.domains,
                            payload=payload,
                            request={"day": ctx.window.day.isoformat(), "base_url": self.params.base_url},
                            retrieval_method="bulk:gdelt_gkg_v2",
                            tool_identity=f"moria:{PARSER_VERSION}",
                            licence=self.card.licence,
                            parser_version=PARSER_VERSION,
                            event_at=ctx.window.start.isoformat(),
                            observable_at=ctx.window.end.isoformat(),
                        ),
                        payload=payload,
                    )
                )
        return records
