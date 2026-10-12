"""`moria terms check` (design §2.4): how often each search term appears in the news, worldwide and in .au domains,
with a sample of its hits to read for noise.

GDELT's DOC API throttles shared cloud addresses (D-009), so the check reads GKG bulk files, as the daily collector
does (D-010). Three months of GKG is about 24 GB, so it samples days: by default one a week for 13 weeks, ending with
a given day. Every term is matched exactly as the daily collector matches it: whole words, regardless of case, in
each English web document's title, URL, quotations and named entities.

Outputs:
- the full result, with a seeded sample of hits per term (day, title, URL, domain, fields), in the private store at
  reports/terms-check/<run_id>.json. Titles are news titles, so the samples never go into the public repo;
- a summary for the owner, counts and flags only, as markdown (reports/terms-check.md by default).

The flags are triage, not verdicts: a person reads the samples of flagged terms before any term is narrowed or
dropped.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .collectors.base import CollectContext, CollectError, Window
from .collectors.gdelt import QueryGroup
from .collectors.gkg import GkgCollector, PhraseMatcher, file_stamps, phrase_hits, searchable_texts, web_documents
from .config import SourceCard, TerritoriesFile, ThemesFile
from .http import FetchError, PoliteClient
from .manifest import Manifest
from .records import canonical_json
from .store import Store

log = logging.getLogger("moria.terms")

FIELDS = ["title", "url", "quotations", "names"]
# Triage thresholds, per sampled day of worldwide English web news (about 50,000 to 65,000 documents a day)
RARE_PER_DAY = 0.2  # fewer than one hit in five sampled days
BROAD_PER_DAY = 500.0  # so common it is unlikely to pick out the territory
NAMES_HEAVY_SHARE = 0.6  # most hits only through GDELT's named entities, worth reading
NAMES_HEAVY_MIN_DOCS = 10


@dataclass
class TermStats:
    phrase: str
    sources: list[str]  # "T1:core", "theme:economy_finance", ...
    world: int = 0
    au: int = 0
    about: int = 0  # a match in the title or URL: the document is about the term
    days_with_hits: int = 0
    by_field: dict[str, int] = field(default_factory=dict)
    names_only: int = 0
    title_hits: int = 0
    samples: list[dict] = field(default_factory=list)
    seen_samples: int = 0

    def flags(self, days: int) -> list[str]:
        per_day = self.world / days if days else 0.0
        out = []
        if self.world == 0:
            out.append("silent")
        elif per_day < RARE_PER_DAY:
            out.append("rare")
        if per_day > BROAD_PER_DAY:
            out.append("broad")
        if self.world >= NAMES_HEAVY_MIN_DOCS and self.names_only / self.world > NAMES_HEAVY_SHARE:
            out.append("names-heavy")
        return out


def term_inventory(territories: TerritoriesFile, themes: ThemesFile) -> dict[str, TermStats]:
    """Every phrase, lower-cased, with every place it comes from."""
    terms: dict[str, TermStats] = {}

    def add(phrase: str, source: str) -> None:
        key = phrase.strip().lower()
        if key:
            terms.setdefault(key, TermStats(phrase=key, sources=[])).sources.append(source)

    for t in territories.territories:
        for ring in ("core", "adjacent", "wider_world"):
            for phrase in getattr(t.terms, ring):
                add(phrase, f"{t.id}:{ring}")
    for name, phrases in sorted(themes.themes.items()):
        for phrase in phrases:
            add(phrase, f"theme:{name}")
    return terms


def sampled_days(end: date, weeks: int) -> list[date]:
    return [end - timedelta(days=7 * i) for i in range(weeks)][::-1]


def _keep_sample(stats: TermStats, item: dict, k: int, rng: random.Random) -> None:
    # Reservoir sampling: every hit has the same chance of being kept, whatever its day
    stats.seen_samples += 1
    if len(stats.samples) < k:
        stats.samples.append(item)
    else:
        j = rng.randrange(stats.seen_samples)
        if j < k:
            stats.samples[j] = item


def run_check(
    gdelt_card: SourceCard,
    territories: TerritoriesFile,
    themes: ThemesFile,
    client: PoliteClient,
    days: list[date],
    samples_per_term: int = 12,
    files_per_day: int | None = None,
    seed: int = 20261012,
) -> tuple[dict[str, TermStats], dict]:
    """Match every term on the sampled days. Returns the per-term stats and the run totals."""
    collector = GkgCollector(gdelt_card)
    terms = term_inventory(territories, themes)
    matcher = PhraseMatcher([QueryGroup("terms", tuple(terms))])
    rngs = {p: random.Random(f"{seed}:{p}") for p in terms}
    totals: dict = {"days_read": 0, "days_skipped": [], "documents": 0, "au_documents": 0, "files_read": 0}
    for n, day in enumerate(days, start=1):
        ctx = CollectContext(card=gdelt_card, client=client, window=Window.for_day(day))
        stamps = file_stamps(ctx)[:files_per_day] if files_per_day else file_stamps(ctx)
        seen: set[str] = set()
        day_hits: dict[str, int] = {}
        missing = docs_today = 0
        started = time.monotonic()
        for stamp in stamps:
            try:
                text = collector.download_file(ctx, stamp)
            except FetchError as e:
                raise CollectError(f"terms: GKG file {stamp} could not be fetched: {e}") from e
            if text is None:
                missing += 1
                continue
            totals["files_read"] += 1
            docs, _ = web_documents(text, seen)
            for doc in docs:
                docs_today += 1
                totals["au_documents"] += doc.au
                texts = searchable_texts(doc)
                for phrase, fields in phrase_hits(matcher, texts, FIELDS).items():
                    s = terms[phrase]
                    s.world += 1
                    s.au += doc.au
                    day_hits[phrase] = day_hits.get(phrase, 0) + 1
                    for f in fields:
                        s.by_field[f] = s.by_field.get(f, 0) + 1
                    s.names_only += fields == {"names"}
                    s.about += bool(fields & {"title", "url"})
                    s.title_hits += "title" in fields
                    item = {
                        "day": day.isoformat(),
                        "title": texts["title"][:200],
                        "url": doc.url,
                        "domain": doc.domain,
                        "au": doc.au,
                        "fields": sorted(fields),
                    }
                    _keep_sample(s, item, samples_per_term, rngs[phrase])
        too_many = missing > collector.params.max_missing_files and not files_per_day
        if too_many or missing == len(stamps):
            totals["days_skipped"].append(day.isoformat())
            log.warning("terms [%d/%d] %s: %d of %d files missing; day left out", n, len(days), day, missing,
                        len(stamps))  # fmt: skip
            continue
        for phrase in day_hits:
            terms[phrase].days_with_hits += 1
        totals["days_read"] += 1
        totals["documents"] += docs_today
        log.info("terms [%d/%d] %s: %d documents, %d terms hit, %.0fs", n, len(days), day, docs_today, len(day_hits),
                 time.monotonic() - started)  # fmt: skip
    return terms, totals


def summary_markdown(terms: dict[str, TermStats], totals: dict, run_id: str, days: list[date]) -> str:
    """The public report: counts and flags per term, no titles or URLs."""
    d = max(totals["days_read"], 1)
    lines = [
        "# Terms check: how often each search term appears in the news",
        "",
        f"Run `{run_id}` (`moria terms check`). Generated; do not edit by hand.",
        "",
        f"**Sample:** {totals['days_read']} days of GDELT GKG files, one a week from {days[0]} to {days[-1]}"
        + (f" ({len(totals['days_skipped'])} left out for missing files)" if totals["days_skipped"] else "")
        + f": {totals['documents']:,} English web documents, {totals['au_documents']:,} from `.au` domains.",
        "",
        "**How to read it.** *World/day* is the average number of documents a sampled day that mention the term",
        "(whole words, in either spelling and with a plural last word, in the title, URL, quotations or named",
        "entities); *About/day* counts only matches in the title or URL, the documents about the term; *.au/day* is",
        "for `.au` domains. *Names only* is the share found only inside GDELT's named entities, which is often",
        f"incidental (D-012). Flags are triage: `silent` no hit at all; `rare` under {RARE_PER_DAY} a day;",
        f"`broad` over {BROAD_PER_DAY:.0f} a day; `names-heavy` over {NAMES_HEAVY_SHARE:.0%} names-only hits. The hit",
        "samples are in the private bucket; a person reads them before any term is narrowed or dropped.",
        "",
    ]
    groups: dict[str, list[TermStats]] = {}
    for s in terms.values():
        for src in s.sources:
            groups.setdefault(src.split(":")[0] if not src.startswith("theme:") else "themes", []).append(s)
    flagged = sum(1 for s in terms.values() if s.flags(d))
    lines += [f"**{len(terms)} distinct terms; {flagged} flagged.**", ""]
    for group in sorted(groups, key=lambda g: (g == "themes", g)):
        lines += [f"## {group if group != 'themes' else 'Broad themes'}", ""]
        lines += ["| Term | Ring or theme | World/day | About/day | .au/day | Days with hits | Names only | Flags |"]
        lines += ["|---|---|---:|---:|---:|---:|---:|---|"]
        for s in sorted(groups[group], key=lambda s: (-s.world, s.phrase)):
            prefix = "theme:" if group == "themes" else f"{group}:"
            src = ", ".join(x.split(":", 1)[1] for x in s.sources if x.startswith(prefix))
            names = f"{s.names_only / s.world:.0%}" if s.world else "-"
            flags = ", ".join(f"`{f}`" for f in s.flags(d))
            lines.append(
                f"| {s.phrase} | {src} | {s.world / d:.1f} | {s.about / d:.1f} | {s.au / d:.2f} | "
                f"{s.days_with_hits}/{totals['days_read']} | {names} | {flags} |"
            )
        lines.append("")
    return "\n".join(lines)


def check(
    gdelt_card: SourceCard,
    territories: TerritoriesFile,
    themes: ThemesFile,
    store: Store,
    client: PoliteClient,
    end: date,
    weeks: int = 13,
    samples_per_term: int = 12,
    files_per_day: int | None = None,
    report_path: Path | None = None,
    config_hash: str | None = None,
) -> tuple[str, str, dict]:
    """Run the check, write the private result and the manifest, and the public summary if asked. Returns (status,
    manifest key, counts)."""
    days = sampled_days(end, weeks)
    manifest = Manifest(
        command="terms.check",
        params={
            "end": end.isoformat(),
            "weeks": weeks,
            "samples_per_term": samples_per_term,
            "files_per_day": files_per_day,
        },
        config_hash=config_hash,
    )
    try:
        terms, totals = run_check(gdelt_card, territories, themes, client, days, samples_per_term, files_per_day)
        if totals["days_read"] == 0:
            raise CollectError("terms: no sampled day could be read")
        d = totals["days_read"]
        result = {
            "run_id": manifest.run_id,
            "days": [x.isoformat() for x in days],
            "totals": totals,
            "terms": {
                p: {
                    "sources": s.sources,
                    "world": s.world,
                    "au": s.au,
                    "world_per_day": round(s.world / d, 3),
                    "about": s.about,
                    "about_per_day": round(s.about / d, 3),
                    "au_per_day": round(s.au / d, 3),
                    "days_with_hits": s.days_with_hits,
                    "by_field": dict(sorted(s.by_field.items())),
                    "names_only": s.names_only,
                    "title_hits": s.title_hits,
                    "flags": s.flags(d),
                    "samples": sorted(s.samples, key=lambda x: (x["day"], x["url"])),
                }
                for p, s in sorted(terms.items())
            },
        }
        key = f"reports/terms-check/{manifest.run_id}.json"
        data = canonical_json(result).encode("utf-8")
        store.put(key, data, "application/json")
        manifest.add_output(key, data)
        markdown = summary_markdown(terms, totals, manifest.run_id, days)
        md_key = f"reports/terms-check/{manifest.run_id}.md"
        store.put(md_key, markdown.encode("utf-8"), "text/markdown")
        manifest.add_output(md_key, markdown.encode("utf-8"))
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(markdown + "\n", encoding="utf-8")
        flags: dict[str, int] = {}
        for s in terms.values():
            for f in s.flags(d):
                flags[f] = flags.get(f, 0) + 1
        manifest.counts = {"terms": len(terms), "days_read": d, "documents": totals["documents"],
                           **{f"flag_{k.replace('-', '_')}": v for k, v in sorted(flags.items())}}  # fmt: skip
        manifest.warnings = [f"terms: day {x} left out for missing files" for x in totals["days_skipped"]]
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        mkey = manifest.finish(store, "failed", f"terms.check: {type(e).__name__}: {first[:300]}")
        log.error("terms check failed: %s", first)
        return "failed", mkey, {}
