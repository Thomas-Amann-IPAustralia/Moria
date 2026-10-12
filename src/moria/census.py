"""`moria census <source>` (design §3, phase 2: data understanding): a profile of what a source's latest collection
holds, for the owner and for the sessions that build normalisation on it.

Aggregates only, so a report may be committed to the public repo: record counts by kind and collection, how often
each envelope date and payload field is present, date ranges, and a section per kind of source (series and periods
for statistics, levels and totals for OpenAlex, tables, types and sentinel dates for IP RAPID). Never titles, text,
URLs or names.
"""

from __future__ import annotations

import json
import statistics
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from .config import SourceCard
from .records import RawRecord, decode_bundle
from .store import Store

SENTINEL_DATES = ("1800-01-01", "1901-01-01")


def latest_bundle(store: Store, source: str) -> str | None:
    keys = [k for k in store.list(f"raw/{source}/") if k.endswith(".jsonl.zst")]
    # raw/<source>/<yyyy>/<mm>/<dd>/<run_id>.jsonl.zst: the run id starts with its UTC start time, so the last key in
    # (day, run id) order is the newest collection of the newest day
    return sorted(keys)[-1] if keys else None


def _when(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=None)


def _date_range(values: list[str | None]) -> str:
    parsed = [m for m in (_when(v) for v in values) if m is not None]
    if not parsed:
        return "none"
    naive = sorted(m.replace(tzinfo=None) for m in parsed)
    return f"{naive[0]:%Y-%m-%d} to {naive[-1]:%Y-%m-%d} ({len(parsed)} of {len(values)} present)"


def _type_name(value) -> str:
    return "null" if value is None else type(value).__name__


def generic_profile(records: list[RawRecord]) -> list[str]:
    lines = [f"**Records:** {len(records):,}", ""]
    kinds = Counter(r.envelope.kind for r in records)
    collections = Counter(r.envelope.source_collection for r in records)
    lines += ["| Kind | Records |", "|---|---:|", *[f"| {k} | {v:,} |" for k, v in sorted(kinds.items())], ""]
    lines += ["| Collection | Records |", "|---|---:|"]
    lines += [f"| {k} | {v:,} |" for k, v in sorted(collections.items())] + [""]
    lines += [
        f"**event_at:** {_date_range([r.envelope.event_at for r in records])}  ",
        f"**observable_at:** {_date_range([r.envelope.observable_at for r in records])}",
        "",
    ]
    fields: dict[str, Counter] = {}
    lengths: dict[str, list[int]] = {}
    for r in records:
        if not isinstance(r.payload, dict):
            continue
        for k, v in r.payload.items():
            fields.setdefault(k, Counter())[_type_name(v)] += 1
            if isinstance(v, str | list | dict):
                lengths.setdefault(k, []).append(len(v))
    lines += ["| Payload field | Present | Types | Median length |", "|---|---:|---|---:|"]
    for k in sorted(fields):
        present = sum(n for t, n in fields[k].items() if t != "null")
        types = ", ".join(f"{t} {n:,}" for t, n in fields[k].most_common())
        med = statistics.median(lengths[k]) if lengths.get(k) else ""
        lines.append(f"| {k} | {present / len(records):.0%} | {types} | {med} |")
    return [*lines, ""]


def openalex_section(records: list[RawRecord]) -> list[str]:
    p = {r.envelope.provider_record_id: r.payload for r in records}
    levels = sorted({x["level"] for x in p.values()})
    lines = [
        "## OpenAlex counts",
        "",
        "| Level | Scope | Periods | Median groups | Pages |",
        "|---|---|---:|---:|---:|",
    ]
    for level in levels:
        for scope in ("world", "au"):
            rows = [x for x in p.values() if x["level"] == level and x["scope"] == scope]
            if rows:
                med = statistics.median(len(x["groups"]) for x in rows)
                lines.append(f"| {level} | {scope} | {len(rows)} | {med:.0f} | {sum(x['pages'] for x in rows):,} |")
    years = sorted(x["period"] for x in p.values() if x["period_kind"] == "year" and x["level"] == levels[0])
    years = sorted(set(years))
    if years:
        lines += ["", "Works matched by the filter, by publication year:", ""]
        lines += ["| Year | World | Australia | AU share |", "|---|---:|---:|---:|"]
        for y in years:
            w = p.get(f"{levels[0]}|world|{y}", {}).get("total_works", 0)
            a = p.get(f"{levels[0]}|au|{y}", {}).get("total_works", 0)
            lines.append(f"| {y} | {w:,} | {a:,} | {a / w:.2%} |" if w else f"| {y} | {w:,} | {a:,} | - |")
    any_filter = next(iter(p.values()))["filter"]
    return [*lines, "", f"Filter of one query, for reference: `{any_filter}`", ""]


def abs_section(records: list[RawRecord]) -> list[str]:
    by_query: dict[str, list[dict]] = {}
    for r in records:
        by_query.setdefault(r.payload["query_id"], []).append(r.payload)
    lines = ["## ABS queries", "", "| Query | Series | Observations | First period | Last period |"]
    lines += ["|---|---:|---:|---|---|"]
    for q, series in sorted(by_query.items()):
        firsts = sorted(s["first_period"] for s in series)
        lasts = sorted(s["last_period"] for s in series)
        lines.append(f"| {q} | {len(series)} | {sum(s['n_obs'] for s in series):,} | {firsts[0]} | {lasts[-1]} |")
    missing = sum(1 for s in (r.payload for r in records) for o in s["observations"] if o[1] is None)
    return [*lines, "", f"Observations with no value: {missing:,}", ""]


def documents_section(records: list[RawRecord]) -> list[str]:
    lines = [
        "## Documents",
        "",
        "| Document | Obtained | Format | Pages | Characters | Licence stated | Check | Text stored |",
        "|---|---|---|---:|---:|---|---|---|",
    ]
    for r in sorted(records, key=lambda r: r.payload["id"]):
        x = r.payload
        stated = ", ".join(x.get("licence_statements") or []) or "-"
        lines.append(
            f"| {x['id']} | {x.get('obtained', 'fetched')} | {x['format']} | {x['pages']} | {x['chars']:,} | "
            f"{stated} | {x.get('licence_check', 'not run')} | {x['text_stored']} |"
        )
    return [*lines, ""]


def ipr_section(store: Store) -> list[str]:
    """IP RAPID from its newest release manifest and that release's base in the lake (aggregates only)."""
    import duckdb

    manifests = sorted(k for k in store.list("raw/ip_rapid/") if k.endswith("/manifest.json"))
    if not manifests:
        return ["No IP RAPID release has been ingested yet.", ""]
    release = json.loads(store.get(manifests[-1]))
    lines = [
        f"**Release** {release['release_date']} ({release['mode']}; zip {release['zip']['bytes'] / 1e9:.2f} GB, "
        f"SHA-256 `{release['zip']['sha256'][:16]}…`)",
        "",
        "| Table | Rows | Parquet MB |",
        "|---|---:|---:|",
    ]
    for t, e in release["tables"].items():
        lines.append(f"| {t} | {e['rows']:,} | {e['bytes'] / 1e6:.1f} |")
    if release["mode"] != "base":
        return [*lines, "", "This release is a delta; profile its base instead.", ""]
    con = duckdb.connect()
    with tempfile.TemporaryDirectory(prefix="moria-census-") as tmp:

        def table(name: str) -> str:
            path = Path(tmp) / f"{name}.parquet"
            if not path.exists():
                store.get_file(release["tables"][name]["key"], path)
            return f"read_parquet('{path}')"

        app = table("application")
        rows = con.execute(
            f"SELECT ip_right_type, count(*), count(*) FILTER (WHERE year(application_date) >= 2015) FROM {app} "
            "GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        lines += ["", "**Applications by right** (all time; since 2015):", ""]
        lines += ["| Right | Applications | Since 2015 |", "|---|---:|---:|"]
        lines += [f"| {r} | {n:,} | {m:,} |" for r, n, m in rows]
        yearly = con.execute(
            f"SELECT year(application_date) AS y, ip_right_type, count(*) FROM {app} WHERE application_date "
            ">= DATE '2015-01-01' GROUP BY 1, 2 ORDER BY 1, 2"
        ).fetchall()
        rights = sorted({r for _, r, _ in yearly})
        lines += ["", "**Applications by year of application_date:**", ""]
        lines += ["| Year | " + " | ".join(rights) + " |", "|---|" + "---:|" * len(rights)]
        for y in sorted({y for y, _, _ in yearly}):
            cells = {r: n for yy, r, n in yearly if yy == y}
            lines.append(f"| {y} | " + " | ".join(f"{cells.get(r, 0):,}" for r in rights) + " |")
        party = table("party_activity")
        types = con.execute(
            f"SELECT coalesce(party_type, '(none)'), count(*), count(*) FILTER (WHERE party_name LIKE 'sha256:%'), "
            f"count(post_code) FROM {party} GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        lines += ["", "**Parties** (individuals' names hashed and postcodes dropped at ingest):", ""]
        lines += ["| Party type | Rows | Names hashed | With postcode |", "|---|---:|---:|---:|"]
        lines += [f"| {t} | {n:,} | {h:,} | {p:,} |" for t, n, h, p in types]
        lines += ["", "**Sentinel dates** (placeholders for unknown dates):", ""]
        lines += ["| Table | Column | 1800-01-01 | 1901-01-01 |", "|---|---|---:|---:|"]
        for name in release["tables"]:
            src = table(name)
            cols = [d[0] for d in con.execute(f"SELECT * FROM {src} LIMIT 0").description if d[0].endswith("_date")]
            for c in cols:
                a, b = con.execute(
                    f"SELECT count(*) FILTER (WHERE {c} = DATE '{SENTINEL_DATES[0]}'), "
                    f"count(*) FILTER (WHERE {c} = DATE '{SENTINEL_DATES[1]}') FROM {src}"
                ).fetchone()
                if a or b:
                    lines.append(f"| {name} | {c} | {a:,} | {b:,} |")
    return [*lines, ""]


def corpus_section(store: Store, card: SourceCard) -> list[str]:
    """The legal corpus from its newest release manifest and that release's parts (counts by source, type and year
    only: never citations, names or text)."""
    import duckdb

    manifests = sorted(k for k in store.list(f"raw/{card.id}/") if k.endswith("/manifest.json"))
    if not manifests:
        return ["No release has been ingested yet.", ""]
    release = json.loads(store.get(manifests[-1]))
    lines = [
        f"**Release** {release['release']} (dataset commit `{release['revision'][:12]}`; file "
        f"{release['file']['bytes'] / 1e9:.2f} GB, SHA-256 `{release['file']['sha256'][:16]}…`)",
        "",
        "| Part | Documents | No date | No text | Parquet MB | Observable from |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name, t in sorted(release["tables"].items()):
        lines.append(f"| {name} | {t['rows']:,} | {t['no_date']:,} | {t['no_text']:,} | {t['bytes'] / 1e6:.1f} | "
                     f"{t['observable_from']} |")  # fmt: skip
    con = duckdb.connect()
    with tempfile.TemporaryDirectory(prefix="moria-census-") as tmp:
        for name, t in sorted(release["tables"].items()):
            path = Path(tmp) / f"{name}.parquet"
            store.get_file(t["key"], path)
            src = f"read_parquet('{path}')"
            kinds = con.execute(
                f"SELECT coalesce(type, '(none)'), count(*), median(text_chars) FROM {src} GROUP BY 1 ORDER BY 1"
            ).fetchall()
            lines += ["", f"**{name}**", "", "| Type | Documents | Median characters |", "|---|---:|---:|"]
            lines += [f"| {k} | {n:,} | {m:,.0f} |" for k, n, m in kinds]
            years = con.execute(
                f"SELECT year(date) AS y, count(*) FROM {src} WHERE date IS NOT NULL GROUP BY 1 ORDER BY 1"
            ).fetchall()
            recent = [(y, n) for y, n in years if y >= 2000]
            earlier = sum(n for y, n in years if y < 2000)
            lines += ["", "| Year of the document's date | Documents |", "|---|---:|"]
            if earlier:
                lines.append(f"| before 2000 (from {years[0][0]}) | {earlier:,} |")
            lines += [f"| {y} | {n:,} |" for y, n in recent]
    return [*lines, ""]


def census_markdown(store: Store, card: SourceCard, all_runs: bool = False) -> str:
    head = [f"# Census: {card.id}", "", f"{card.name}. Generated by `moria census {card.id}`; aggregates only.", ""]
    if card.adapter == "ip_rapid":
        return "\n".join(head + ipr_section(store))
    if card.adapter == "hf_corpus":
        return "\n".join(head + corpus_section(store, card))
    key = latest_bundle(store, card.id)
    if key is None:
        return "\n".join([*head, "No collection in the store yet.", ""])
    if all_runs:
        # by run id (it starts with the run's UTC time), not by path, whose date is the collection window's day
        keys = sorted((k for k in store.list(f"raw/{card.id}/") if k.endswith(".jsonl.zst")),
                      key=lambda k: k.rsplit("/", 1)[-1])  # fmt: skip
        unique = {r.envelope.evidence_id: r for k in keys for r in decode_bundle(store.get(k))}
        records = list(unique.values())
        lines = [*head, f"Every collection in the store: {len(keys)} runs, de-duplicated by evidence id.", ""]
    else:
        records = decode_bundle(store.get(key))
        run = key.rsplit("/", 1)[-1].removesuffix(".jsonl.zst")
        lines = [*head, f"Latest collection: `{key.split('/', 2)[2]}` (run `{run}`).", ""]
    if not records:
        return "\n".join([*lines, "The latest collection holds no records.", ""])
    if all_runs and card.adapter == "documents":
        # a document read again gets a new record; keep the newest record of each (keys are in run order)
        records = list({r.payload["id"]: r for r in records}.values())
        lines += ["Documents: the newest record of each.", ""]
    lines += generic_profile(records)
    if card.adapter == "openalex_counts":
        lines += openalex_section(records)
    elif card.adapter == "abs_sdmx":
        lines += abs_section(records)
    elif card.adapter == "documents":
        lines += documents_section(records)
    return "\n".join(lines)
