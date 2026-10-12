"""GDELT Global Knowledge Graph (GKG 2.1) bulk files: the news scan without the rate-limited DOC API (D-009, D-010).

GDELT publishes one GKG file every 15 minutes at data.gdeltproject.org. A UTC day is the 96 files stamped inside it.
Every English web document in them is matched against the query groups (`moria terms`) in its title, URL, quotations
and named entities. Matching documents are kept; the rest only count towards the day's totals.

What is stored (design §12: news is titles, URLs and metadata, never article text):
- per matching document: URL, domain, title, GDELT's timestamps, which groups and phrases matched and in which fields,
  and GDELT's own metadata, which it derives from the full text: themes, organisations, location countries and tone;
- per group and scope (worldwide English, `.au` domains): matching documents, the documents *about* the group (a
  phrase in the title or URL), the documents that match only through GDELT's named entities, and all documents
  that day. A names-only match means the phrase appears inside some proper name in the article, which is often
  incidental (D-012), so `about_documents` is the cleaner series.

Phrases match in Australian and US spelling and with a plural last word (`phrase_variants`), so "commercialisation"
also finds "commercialization" and "supply chain disruption" finds "supply chain disruptions" (D-012). A term's
synonyms (the `synonyms` maps in config/territories.yaml and config/themes.yaml) are other wordings of it, the way news
writes it: a match on a synonym counts as the term, and the record names the synonyms that matched (D-014).

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

PARSER_VERSION = "gdelt-gkg-v3"
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


# Word-level spelling pairs (Australian/UK -> US), from explicit lists so that words like "enterprise" or "four" are
# never touched. The territories' search rule asks for both spellings (config/territories.yaml).
_SPELLING = {
    "ageing": "aging",
    "analyse": "analyze",
    "behaviour": "behavior",
    "catalogue": "catalog",
    "centre": "center",
    "colour": "color",
    "defence": "defense",
    "enrol": "enroll",
    "favour": "favor",
    "fibre": "fiber",
    "fulfil": "fulfill",
    "harbour": "harbor",
    "honour": "honor",
    "judgement": "judgment",
    "labour": "labor",
    "licence": "license",
    "modelling": "modeling",
    "neighbour": "neighbor",
    "offence": "offense",
    "programme": "program",
    "travelling": "traveling",
}
_SPELLING_US = {us: au for au, us in _SPELLING.items()}
# Stems that take -ise/-ize: "commercial" + "isation" <-> "commercial" + "ization"
_ISE_STEMS = frozenset(
    [
        "author", "capital", "categor", "central", "colon", "commercial", "critic", "decentral", "democrat", "digit",
        "emphas", "final", "global", "harmon", "industrial", "legal", "local", "maxim", "minim", "mobil", "modern",
        "monet", "national", "neutral", "optim", "organ", "personal", "priorit", "privat", "real", "recogn",
        "revital", "special", "stabil", "standard", "subsid", "summar", "symbol", "urban", "util", "visual",
    ]
)  # fmt: skip
_ISE_ENDINGS = {
    "ise": "ize",
    "ised": "ized",
    "ises": "izes",
    "ising": "izing",
    "isation": "ization",
    "isations": "izations",
}
_IZE_ENDINGS = {us: au for au, us in _ISE_ENDINGS.items()}


def _spellings(word: str) -> set[str]:
    out = {word}
    if word in _SPELLING:
        out.add(_SPELLING[word])
    if word in _SPELLING_US:
        out.add(_SPELLING_US[word])
    for endings in (_ISE_ENDINGS, _IZE_ENDINGS):
        for ending, other in endings.items():
            if not word.endswith(ending):
                continue
            stem = word[: -len(ending)]
            # -isation and -ization are always spellings of each other; the shorter -ise forms only for known stems,
            # because "enterprise" or "franchise" have no -ize form
            if ending.startswith(("isation", "ization")) or stem in _ISE_STEMS:
                out.add(stem + other)
    return out


def _plurals(word: str) -> set[str]:
    if len(word) < 3 or word.endswith("s"):
        return set()
    if word.endswith(("x", "z", "ch", "sh")):
        return {word + "es"}
    if word.endswith("y") and word[-2] not in "aeiou":
        return {word[:-1] + "ies"}
    return {word + "s"}


def phrase_variants(phrase: str) -> set[str]:
    """The normalised phrase in Australian and US spelling, with its last word also in the plural; "trade mark" and
    "trademark" stand for each other."""
    words = _words(phrase).split()
    if not words:
        return set()
    forms = [_spellings(w) for w in words]
    forms[-1] = forms[-1] | {p for w in forms[-1] for p in _plurals(w)}
    variants = {""}
    for options in forms:
        variants = {f"{v} {o}".strip() for v in variants for o in options}
    for v in list(variants):
        if " trade mark" in f" {v} ":
            variants.add(f" {v} ".replace(" trade mark", " trademark").strip())
        if " trademark" in f" {v} ":
            variants.add(f" {v} ".replace(" trademark", " trade mark").strip())
    return variants


class PhraseMatcher:
    """Whole-word, case-insensitive phrase matching, in both spellings and with a plural last word, for each term and
    its synonyms. Candidates are looked up by first word, then checked as substrings of the normalised text: fast
    enough for a day's 65k documents in pure Python. Matches are reported by the term as written in the config (lower
    case), with the form that matched: the term itself or one of its synonyms."""

    def __init__(self, groups):
        self.groups_by_phrase: dict[str, list[str]] = {}
        forms: dict[str, set[str]] = {}
        for g in groups:
            synonyms = dict(g.synonyms)
            for p in g.phrases:
                key = p.lower()
                self.groups_by_phrase.setdefault(key, []).append(g.group_id)
                forms.setdefault(key, {key}).update(synonyms.get(key, ()))
        # first word -> {(normalised variant, term, form)}
        self._by_first_word: dict[str, set[tuple[str, str, str]]] = {}
        for phrase, phrase_forms in forms.items():
            for form in phrase_forms:
                for variant in phrase_variants(form):
                    self._by_first_word.setdefault(variant.split()[0], set()).add((f" {variant} ", phrase, form))

    def forms_in(self, text: str) -> set[tuple[str, str]]:
        """(term, form) for every term found, by the form that matched (the term itself or a synonym)."""
        if not text:
            return set()
        normalised = _words(text)
        found = set()
        for word in set(normalised.split()) & self._by_first_word.keys():
            found.update((phrase, form) for n, phrase, form in self._by_first_word[word] if n in normalised)
        return found

    def phrases_in(self, text: str) -> set[str]:
        return {phrase for phrase, _ in self.forms_in(text)}


@dataclass
class GroupCounts:
    world: int = 0
    au: int = 0
    about_world: int = 0  # a phrase in the title or URL
    about_au: int = 0
    names_only_world: int = 0  # matched only inside GDELT's named entities
    names_only_au: int = 0
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


@dataclass
class GkgDocument:
    url: str
    domain: str
    au: bool
    row: list[str]


def web_documents(text: str, seen: set[str]) -> tuple[list[GkgDocument], int]:
    """One file's open-web documents whose URL hasn't been seen yet (adding them to `seen`), and the number of rows
    skipped for not having 27 columns."""
    docs, malformed = [], 0
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
        docs.append(GkgDocument(url, domain, domain.endswith(".au"), row))
    return docs, malformed


def searchable_texts(doc: GkgDocument) -> dict[str, str]:
    """The texts phrases are matched in. Quotations are article text: searched here in memory, never stored."""
    return {
        "title": _extra(doc.row[C_EXTRAS], "PAGE_TITLE"),
        "url": doc.url,
        "quotations": " \n ".join(_quotes(doc.row[C_QUOTES])),
        "names": " ; ".join(_names(doc.row[C_NAMES])),
    }


@dataclass
class PhraseHit:
    fields: set[str] = field(default_factory=set)  # where the term matched
    forms: set[str] = field(default_factory=set)  # the term itself and/or the synonyms that matched

    def synonyms(self, phrase: str) -> list[str]:
        return sorted(self.forms - {phrase})


def phrase_hits(matcher: PhraseMatcher, texts: dict[str, str], fields: list[str]) -> dict[str, PhraseHit]:
    """term -> the fields it matched in and the forms that matched"""
    hits: dict[str, PhraseHit] = {}
    for f in fields:
        for phrase, form in matcher.forms_in(texts[f]):
            hit = hits.setdefault(phrase, PhraseHit())
            hit.fields.add(f)
            hit.forms.add(form)
    return hits


class GkgCollector:
    parser_version = PARSER_VERSION

    def __init__(self, card):
        self.card = card
        self.params = GkgParams.model_validate(card.params)
        unknown = set(self.params.match_fields) - set(MATCH_FIELDS)
        if unknown:
            raise CollectError(f"gkg: unknown match_fields {sorted(unknown)}; allowed: {list(MATCH_FIELDS)}")

    def download_file(self, ctx: CollectContext, stamp: str) -> str | None:
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
                text = self.download_file(ctx, stamp)
            except FetchError as e:
                raise CollectError(f"gkg: file {stamp} could not be fetched: {e}") from e
            if text is None:
                missing.append(stamp)
                log.warning("gkg [%d/%d] %s: not published by GDELT (404)", i, len(stamps), stamp)
                continue
            file_docs, bad_rows = web_documents(text, seen)
            malformed += bad_rows
            n_matches = 0
            for doc in file_docs:
                totals["world"] += 1
                totals["au"] += doc.au
                record = self._match(ctx, doc, matcher, fields, counts)
                if record is not None and self.params.articles:
                    docs.append(record)
                    n_matches += 1
            n_docs = len(file_docs)
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

    def _match(self, ctx, doc: GkgDocument, matcher, fields, counts) -> RawRecord | None:
        row, url, domain, au = doc.row, doc.url, doc.domain, doc.au
        extras = row[C_EXTRAS]
        texts = searchable_texts(doc)
        title = texts["title"]
        hits = phrase_hits(matcher, texts, fields)
        if not hits:
            return None
        matches = sorted(
            (
                {"group": gid, "phrase": phrase, "fields": sorted(hit.fields)}
                | ({"synonyms": hit.synonyms(phrase)} if hit.synonyms(phrase) else {})
                for phrase, hit in hits.items()
                for gid in matcher.groups_by_phrase[phrase]
            ),
            key=lambda m: (m["group"], m["phrase"]),
        )
        for gid in sorted({m["group"] for m in matches}):
            c = counts[gid]
            group_fields = {f for m in matches if m["group"] == gid for f in m["fields"]}
            c.world += 1
            c.au += au
            if group_fields & {"title", "url"}:
                c.about_world += 1
                c.about_au += au
            if group_fields == {"names"}:
                c.names_only_world += 1
                c.names_only_au += au
            for f in sorted(group_fields):
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
                world = scope == "world"
                payload = {
                    "query_group": g.group_id,
                    "ring": g.ring,
                    "scope": scope,
                    "matching_documents": c.world if world else c.au,
                    "about_documents": c.about_world if world else c.about_au,
                    "names_only_documents": c.names_only_world if world else c.names_only_au,
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
