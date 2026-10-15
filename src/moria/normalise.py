"""`moria normalise`: the raw store into the evidence layer's tables (design §6.2, §7; day 3).

Reads every raw bundle whose collection passed, checked against its run manifest's SHA-256, and the latest release
of each bulk source in the lake. Writes, per source:
- `lake/documents/source=<id>/documents.parquet`: one row per item (its latest version), with its first sight;
- `lake/series/source=<id>/series.parquet` and `lake/observations/source=<id>/observations.parquet`: counts and
  statistics in long form, one row per series, period and vintage;
- `lake/quarantine/source=<id>/quarantine.parquet`: items the sweep held back (ids and finding codes only).

Dates (design §6.1): `observable_at` is the source's own publication or release time, read from any of the
sources' formats; an item without one is observable from Moria's first sight of it, and a source date later than
first sight is replaced by first sight (`observable_basis` says which). Point-in-time logic uses `observable_at`.

Vintages: a snapshot source (ABS, the OECD, OpenAlex, the CPC counts, spreadsheets) gives every series anew each
run; a run whose values match the series' previous vintage adds nothing. An append source (GDELT's daily volumes)
gives each period once. Either way, the value at `as_of` is the latest vintage at or before it.

A source whose inputs are unchanged since the last passed run is not rebuilt: its outputs are carried into this
run's manifest, so the next stage can still check them.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from .config import FeaturesConfig, SourceCard
from .lake import releases
from .manifest import Manifest
from .records import canonical_json, decode_bundle, sha256_hex
from .store import Store
from .sweep import SWEEP_VERSION, SweepFile, sweep
from .tables import (
    DOCUMENTS,
    OBSERVATIONS,
    QUARANTINE,
    SERIES,
    cache_root,
    cached_get,
    upload,
    write_rows,
)
from .text import canonical_url, cut, parse_moment, period_start, plain_text, title_key

NORMALISE_VERSION = "normalise-v1"
COMMAND = "normalise"

log = logging.getLogger("moria.normalise")

# Adapters whose records are documents, observations, or bulk releases in the lake
DOC_ADAPTERS = {"feed", "sitemap", "gdelt", "gdelt_gkg", "legislation", "documents", "listpage", "json_list"}
OBS_ADAPTERS = {"abs_sdmx", "oecd_sdmx", "openalex_counts", "bigquery_cpc", "xlsx"}
LAKE_DOCS = {"hf_corpus", "delimited_csv"}
LAKE_OBS = {"zip_csv"}
SKIPPED = {"ip_rapid": "IP RAPID is read by `moria ipr metrics`, not normalised into documents"}

_CPC = re.compile(r"^[A-HY]\d\d[A-Z]$")


class NormaliseError(RuntimeError):
    pass


@dataclass
class SourceOutcome:
    source: str
    status: str  # built, unchanged, failed, skipped
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    digest: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------------------------------------- inputs


def bundle_inputs(store: Store, card: SourceCard, warnings: list[str]) -> list[tuple[str, str]]:
    """(bundle key, SHA-256) of every raw bundle whose collection run passed, checked against its manifest."""
    out = []
    for key in sorted(k for k in store.list(f"raw/{card.id}/") if k.endswith(".jsonl.zst")):
        run_id = key.rsplit("/", 1)[1].removesuffix(".jsonl.zst")
        mkey = f"manifests/collect.{card.id}/{run_id}.json"
        if not store.exists(mkey):
            warnings.append(f"{key}: no run manifest; left out")
            continue
        m = json.loads(store.get(mkey))
        sha = next((o["sha256"] for o in m["outputs"] if o["key"] == key), None)
        if m["status"] != "passed" or sha is None:
            warnings.append(f"{key}: its run {m['status']} or did not list it; left out")
            continue
        out.append((key, sha))
    return out


def release_inputs(store: Store, card: SourceCard) -> tuple[dict, list[tuple[str, str]]] | None:
    """The latest release manifest of a bulk source and its tables (key, SHA-256)."""
    rels = releases(store, card.id)
    if not rels:
        return None
    rel = rels[-1]
    return rel, sorted((t["key"], t["sha256"]) for t in rel["tables"].values())


def digest(card: SourceCard, cfg: FeaturesConfig, inputs: list[tuple[str, str]]) -> str:
    return sha256_hex(
        canonical_json(
            {
                "version": NORMALISE_VERSION,
                "sweep": SWEEP_VERSION,
                "card": card.model_dump(mode="json"),
                "normalise": cfg.normalise.model_dump(mode="json"),
                "inputs": inputs,
            }
        )
    )


def run_time(run_id: str) -> datetime:
    return datetime.strptime(run_id[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


# ------------------------------------------------------------------------------------------------------- documents


def _doc_fields(card: SourceCard, payload: dict) -> dict:
    """The document's fields from its payload, by adapter. An unknown payload shape is an error, not a guess."""
    a = card.adapter
    if a == "feed":
        # categories as the feed gives them; topics, the feeds of a multi-topic source it was found in (csiro_dap)
        extra = {k: payload[k] for k in ("categories", "topics") if payload.get(k)}
        return {
            "doc_type": "feed_item",
            "title": payload.get("title"),
            "summary": payload.get("summary"),
            "url": payload.get("link"),
            "extra": extra,
        }
    if a == "sitemap":
        return {
            "doc_type": "web_page",
            "title": payload.get("title"),
            "summary": payload.get("description"),
            "text": payload.get("text"),
            "text_stored": payload.get("text") is not None,
            "url": payload["url"],
            "extra": {"lastmod": payload.get("lastmod"), "html_bytes": payload.get("html_bytes")},
        }
    if a in ("gdelt", "gdelt_gkg") and "article" in payload:  # the DOC API's early runs (D-009): titles only
        art = payload["article"]
        return {
            "doc_type": "news_title",
            "title": art.get("title"),
            "url": art.get("url"),
            "outlet": art.get("domain"),
            "country": "AU" if art.get("sourcecountry") == "Australia" else None,
            "extra": {"query_groups": [payload.get("query_group")], "sourcecountry": art.get("sourcecountry"),
                      "api": "doc"},
        }  # fmt: skip
    if a == "gdelt_gkg":
        return {
            "doc_type": "news_title",
            "title": payload.get("title"),
            "url": payload["url"],
            "outlet": payload.get("domain"),
            "country": "AU" if payload.get("au_domain") else None,
            "extra": {
                "au_domain": payload.get("au_domain"),
                "query_groups": payload.get("query_groups"),
                "matches": payload.get("matches"),
                "themes": (payload.get("themes") or [])[:60],
                "organisations": (payload.get("organisations") or [])[:30],
                "location_countries": payload.get("location_countries"),
                "tone": payload.get("tone"),
            },
        }
    if a == "legislation":
        lid = payload.get("registerId") or payload.get("id")
        keys = ("entity", "status", "registerId", "titleId", "id", "compilationNumber", "collection", "isPrincipal",
                "isInForce", "isCurrent", "isLatest", "start", "end", "makingDate")  # fmt: skip
        return {
            "doc_type": "legislation_version" if payload.get("entity") == "Versions" else "legislation_title",
            "title": payload.get("name"),
            "url": f"https://www.legislation.gov.au/{lid}" if lid else None,
            "extra": {k: payload[k] for k in keys if payload.get(k) is not None},
        }
    if a == "documents":
        pages = payload.get("page_texts") or []
        stored = bool(payload.get("text_stored")) and bool(pages)
        keys = ("publisher", "format", "pages", "licence_check", "obtained", "id")
        return {
            "doc_type": "report",
            "title": payload.get("title"),
            "text": "\n".join(pages) if stored else None,
            "text_chars": payload.get("chars") or 0,
            "text_stored": stored,
            "url": payload.get("final_url") or payload.get("url"),
            "extra": {k: payload[k] for k in keys if payload.get(k) is not None},
        }
    if a == "listpage":
        label = payload.get("page_label")
        title = payload.get("title") or ""
        return {
            "doc_type": "list_item",
            "title": f"{label}: {title}" if label else title,
            "url": payload.get("link"),
            "extra": {k: payload[k] for k in ("number", "page", "date_text") if payload.get(k)},
        }
    if a == "json_list":
        title = payload.get("title") or ""
        if payload.get("reportingPeriodLabel"):
            title = f"{title} ({payload['reportingPeriodLabel']})"
        return {
            "doc_type": "list_item",
            "title": title,
            "url": payload.get("link"),
            "country": payload.get("country"),
            "extra": {k: v for k, v in sorted(payload.items()) if k not in ("title", "link") and v is not None},
        }
    raise NormaliseError(f"{card.id}: no document mapping for adapter {a!r}")


def make_document(card: SourceCard, cfg: FeaturesConfig, base: dict, fields: dict, sweep_cfg: SweepFile,
                  counts: dict[str, int]) -> tuple[dict | None, dict | None]:  # fmt: skip
    """The document row, or a quarantine row when the sweep finds something of high severity."""
    n = cfg.normalise
    text_raw = fields.get("text")
    texts = {
        "title": plain_text(fields.get("title")),
        "summary": cut(plain_text(fields.get("summary")), n.summary_chars),
        "text": cut(plain_text(text_raw), n.text_chars) if text_raw else "",
    }
    allowed = {e.code for e in sweep_cfg.allowlist if e.item_id == base["item_id"]}
    swept = sweep(texts, allowed)
    for code, k in swept.findings.items():
        counts[f"sweep_{code}"] = counts.get(f"sweep_{code}", 0) + k
    if swept.severity == "high":
        counts["quarantined"] = counts.get("quarantined", 0) + 1
        return None, {
            "item_id": base["item_id"],
            "source": card.id,
            "evidence_id": base["evidence_id"],
            "codes": swept.codes("high"),
            "raw_object_uri": base["raw_object_uri"],
        }
    url = fields.get("url")
    title = swept.fields["title"]
    row = {
        **base,
        "doc_type": fields["doc_type"],
        "family": card.family,
        "rings": list(card.rings),
        "domains": list(card.domains),
        "title": title,
        "summary": swept.fields["summary"],
        "text": swept.fields["text"],
        "text_chars": int(fields.get("text_chars") or (len(plain_text(text_raw)) if text_raw else 0)),
        "text_stored": bool(fields.get("text_stored", text_raw is not None)) and bool(text_raw),
        "url": url,
        "url_canonical": canonical_url(url),
        "outlet": fields.get("outlet") or card.id,
        "country": fields.get("country"),
        "extra": canonical_json(fields.get("extra") or {}),
        "sweep_codes": swept.codes("low"),
        "title_key": title_key(title, cfg.dedup.title_min_words) if card.family == "news" else None,
    }
    return row, None


def observable(source_value: object, first_seen: datetime, cfg: FeaturesConfig, counts: dict) -> tuple:
    """(observable_at, basis): the source's date, unless missing or later than first sight."""
    moment = parse_moment(source_value)
    if moment is None:
        counts["observable_first_sight"] = counts.get("observable_first_sight", 0) + 1
        return first_seen, "first_sight"
    if moment > first_seen + timedelta(days=cfg.normalise.near_future_days):
        counts["observable_clamped"] = counts.get("observable_clamped", 0) + 1
        return first_seen, "clamped"
    return moment, "source"


def documents_from_bundles(card: SourceCard, cfg: FeaturesConfig, bundles: list[tuple[str, list]],
                           sweep_cfg: SweepFile, counts: dict[str, int]) -> tuple[list[dict], list[dict]]:  # fmt: skip
    """One row per item: its latest version, its first sight across every run, and the number of versions seen."""
    versions: dict[str, list[tuple[datetime, str, object, str]]] = defaultdict(list)
    for key, records in bundles:
        for r in records:
            e = r.envelope
            if e.kind != "document":
                continue  # observations are read by observations_from_bundles
            versions[e.provider_record_id].append((parse_moment(e.retrieved_at), e.evidence_id, r, key))
    docs, quarantined = [], []
    for record_id in sorted(versions):
        vs = sorted(versions[record_id], key=lambda v: (v[0], v[1]))
        retrieved, _, latest, key = vs[-1]
        e = latest.envelope
        first_seen = vs[0][0]
        obs_at, basis = observable(e.observable_at, first_seen, cfg, counts)
        base = {
            "item_id": sha256_hex(f"{card.id}|{record_id}"),
            "source": card.id,
            "evidence_id": e.evidence_id,
            "n_versions": len({v[1] for v in vs}),
            "provider": e.provider,
            "source_collection": e.source_collection,
            "provider_record_id": record_id,
            "licence": e.licence,
            "event_at": parse_moment(e.event_at),
            "observable_at": obs_at,
            "observable_basis": basis,
            "first_seen_at": first_seen,
            "retrieved_at": retrieved,
            "raw_object_uri": key,
            "parser_version": e.parser_version,
        }
        row, q = make_document(card, cfg, base, _doc_fields(card, latest.payload), sweep_cfg, counts)
        (docs.append(row) if row else quarantined.append(q))
    return docs, quarantined


def documents_from_lake(card: SourceCard, cfg: FeaturesConfig, rel: dict, paths: dict[str, Path],
                        sweep_cfg: SweepFile, counts: dict[str, int]) -> tuple[list[dict], list[dict]]:  # fmt: skip
    first_seen = run_time(rel["run_id"])
    con = duckdb.connect()
    con.execute("SET threads TO 4")
    docs, quarantined = [], []
    if card.adapter == "hf_corpus":
        files = ", ".join(f"'{p.as_posix()}'" for p in paths.values())
        n = cfg.normalise.text_chars + 2000  # cut again after whitespace is collapsed
        cur = con.execute(
            f"SELECT version_id, type, jurisdiction, source, mime, date, citation, url, text_chars, event_at, "
            f"epoch(observable_at), licence, provider, evidence_id, left(text, {n}) FROM read_parquet([{files}]) "
            f"ORDER BY version_id"
        )
        for row in iter(lambda: cur.fetchmany(5000), []):
            for (vid, typ, jur, src, mime, day, citation, url, chars, event_at, obs_at, licence, provider, eid,
                 text) in row:  # fmt: skip
                obs_at = datetime.fromtimestamp(obs_at, UTC) if obs_at is not None else None
                obs, basis = observable(obs_at, first_seen, cfg, counts)
                base = {
                    "item_id": sha256_hex(f"{card.id}|{vid}"),
                    "source": card.id,
                    "evidence_id": eid,
                    "n_versions": 1,
                    "provider": provider,
                    "source_collection": src,
                    "provider_record_id": vid,
                    "licence": licence,
                    "event_at": parse_moment(event_at),
                    "observable_at": obs,
                    "observable_basis": basis,
                    "first_seen_at": first_seen,
                    "retrieved_at": first_seen,
                    "raw_object_uri": next(k for k in paths if f"/{src}.parquet" in k),
                    "parser_version": rel["parser_version"],
                }
                fields = {
                    "doc_type": typ,
                    "title": citation,
                    "text": text,
                    "text_chars": chars,
                    "text_stored": True,
                    "url": url,
                    "country": "AU",
                    "extra": {"jurisdiction": jur, "corpus_source": src, "mime": mime, "date": str(day)},
                }
                d, q = make_document(card, cfg, base, fields, sweep_cfg, counts)
                (docs.append(d) if d else quarantined.append(q))
        return docs, quarantined
    if card.adapter == "delimited_csv" and card.id == "stip_compass":
        (key, path), = paths.items()  # fmt: skip
        objectives = " || ' ' || ".join(f"coalesce(Objectives{i}, '')" for i in range(1, 7))
        cur = con.execute(
            f"SELECT InitiativeID, any_value(NameEnglish), any_value(CountryCode), any_value(ShortDescription), "
            f"any_value({objectives}), any_value(Background), any_value(Tags), any_value(Acronym), "
            f"any_value(NameResponsibleOrganisation), any_value(StartDateYear), any_value(EndDateYear), "
            f"any_value(YearlyBudgetRange), any_value(CreatedInSurvey), any_value(LastModifiedInSurvey), "
            f"any_value(InternetLinks1), list(DISTINCT InstrumentTypeLabel ORDER BY InstrumentTypeLabel), "
            f"string_agg(coalesce(InstrumentName, '') || ': ' || coalesce(InstrumentDescription, ''), ' ' "
            f"ORDER BY InstrumentID), count(*) FROM read_parquet('{path.as_posix()}') GROUP BY InitiativeID "
            f"ORDER BY InitiativeID"
        )
        for (iid, name, country, short, objectives_text, background, tags, acronym, org, start, end, budget, created,
             modified, link, types, instruments, n_instruments) in cur.fetchall():  # fmt: skip
            obs, basis = observable(created, first_seen, cfg, counts)
            text = " ".join(t for t in (objectives_text, background, instruments) if t and t.strip())
            evidence = sha256_hex(f"{card.id}|{iid}|{modified}")
            base = {
                "item_id": sha256_hex(f"{card.id}|{iid}"),
                "source": card.id,
                "evidence_id": evidence,
                "n_versions": 1,
                "provider": "EC-OECD STIP Compass",
                "source_collection": card.id,
                "provider_record_id": str(iid),
                "licence": rel["licence"],
                "event_at": parse_moment(start) if start and str(start).isdigit() else None,
                "observable_at": obs,
                "observable_basis": basis,
                "first_seen_at": first_seen,
                "retrieved_at": first_seen,
                "raw_object_uri": key,
                "parser_version": rel["parser_version"],
            }
            fields = {
                "doc_type": "policy_initiative",
                "title": name,
                "summary": short,
                "text": text,
                "text_stored": True,
                "url": link,
                "country": country,
                "extra": {
                    "tags": [t for t in (tags or "").split("¬") if t],
                    "acronym": acronym,
                    "responsible_organisation": org,
                    "start_year": start,
                    "end_year": end,
                    "budget_range": budget,
                    "instrument_types": types,
                    "instruments": n_instruments,
                    "last_modified": modified,
                },
            }
            d, q = make_document(card, cfg, base, fields, sweep_cfg, counts)
            (docs.append(d) if d else quarantined.append(q))
        return docs, quarantined
    raise NormaliseError(f"{card.id}: no lake document mapping for adapter {card.adapter!r}")


# ---------------------------------------------------------------------------------------------------- observations


@dataclass
class SeriesPiece:
    series_id: str
    meta: dict  # label, measure, unit, frequency, scope, dimensions
    obs: list[tuple[str, float | None, str | None, str | None]]  # (period, value, value_text, status)


def _number(value: object) -> tuple[float | None, str | None]:
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        return float(value), None
    if isinstance(value, int | float):
        return float(value), None
    try:
        return float(str(value).replace(",", "")), None
    except ValueError:
        return None, str(value)


def series_pieces(card: SourceCard, payload: dict, counts: dict[str, int]) -> list[SeriesPiece]:
    a, sid = card.adapter, card.id
    if a in ("abs_sdmx", "oecd_sdmx"):
        dims = payload.get("dimensions") or {}
        attrs = payload.get("attributes") or {}
        label = " · ".join(
            v["label"] for k, v in dims.items() if k != "FREQ" and v.get("label") and v.get("code") != "_Z"
        )
        unit = (attrs.get("UNIT_MEASURE") or dims.get("UNIT_MEASURE") or {}).get("label")
        mult = (attrs.get("UNIT_MULT") or {}).get("label")
        scope = (dims.get("REF_AREA") or dims.get("REGION") or {}).get("code") or "AUS"
        obs = []
        for o in payload["observations"]:
            value, text = _number(o[1])
            obs.append((str(o[0]), value, text, o[2] if len(o) > 2 else None))
        meta = {
            "label": label,
            "measure": (dims.get("MEASURE") or dims.get("DATA_ITEM") or {}).get("label"),
            "unit": f"{unit} ({mult})" if unit and mult and mult != "Units" else unit,
            "frequency": (dims.get("FREQ") or {}).get("code"),
            "scope": scope,
            "dimensions": {"dataflow": payload.get("dataflow"), "query_id": payload.get("query_id"),
                           **{k: v.get("code") for k, v in dims.items()}},
        }  # fmt: skip
        key = payload.get("series_key")
        dataflow = (payload.get("dataflow") or "").split("(")[0]  # the version is not part of a series' id (D-020)
        return [SeriesPiece(f"{sid}|{dataflow}|{key}", meta, obs)]
    if a == "openalex_counts":
        level, scope, period, kind = payload["level"], payload["scope"], payload["period"], payload["period_kind"]
        freq = "A" if kind == "year" else "M"
        pieces = [
            SeriesPiece(
                f"{sid}|total|{scope}|{kind}",
                {"label": "All works (research output types)", "measure": "works", "unit": "works",
                 "frequency": freq, "scope": scope, "dimensions": {"level": "total"}},
                [(period, float(payload["total_works"]), None, None)],
            )
        ]  # fmt: skip
        for g in payload.get("groups") or []:
            gid = str(g["id"]).rsplit("/", 1)[-1]
            pieces.append(
                SeriesPiece(
                    f"{sid}|{level}|{gid}|{scope}|{kind}",
                    {"label": g.get("name") or gid, "measure": f"works by primary {level}", "unit": "works",
                     "frequency": freq, "scope": scope, "dimensions": {"level": level, "id": g["id"]}},
                    [(period, float(g["count"]), None, None)],
                )
            )  # fmt: skip
        return pieces
    if a == "bigquery_cpc":
        code = payload["cpc_subclass"]
        if not _CPC.match(code):
            counts["skipped_malformed_cpc"] = counts.get("skipped_malformed_cpc", 0) + 1
            return []
        years = payload["years"]
        dims = {"cpc_subclass": code, "table": payload.get("table")}
        return [
            SeriesPiece(f"{sid}|{code}|world", {"label": f"CPC {code}", "measure": "patent families by priority year",
                        "unit": "families", "frequency": "A", "scope": "world", "dimensions": dims},
                        [(str(y), float(w), None, None) for y, w, _ in years]),
            SeriesPiece(f"{sid}|{code}|au", {"label": f"CPC {code}", "measure":
                        "patent families with an Australian member, by priority year", "unit": "families",
                        "frequency": "A", "scope": "au", "dimensions": dims},
                        [(str(y), float(au), None, None) for y, _, au in years]),
        ]  # fmt: skip
    if a == "xlsx":
        pieces = []
        period = payload.get("release_path") or payload.get("released")
        for row in payload["rows"]:
            for column, value in zip(payload["columns"], row["values"], strict=False):
                v, text = _number(value)
                parts = [p.strip() for p in column.split("|")]
                unit = parts[-1] if len(parts) > 1 else None
                named = parts[:-1] if len(parts) > 1 else parts
                label = " · ".join(x for x in (row.get("section"), row.get("label"), *named) if x)
                where = f"{payload['source']}|{payload['sheet']}|{row.get('section')}|{row.get('label')}"
                series = f"{sid}|{where}|{column}"
                pieces.append(
                    SeriesPiece(series, {"label": f"{payload.get('title')}: {label}", "measure": column, "unit": unit,
                                         "frequency": None, "scope": "AUS",
                                         "dimensions": {"workbook": payload.get("workbook"), "sheet": payload["sheet"],
                                                        "section": row.get("section"), "row": row.get("label"),
                                                        "column": column}},
                                [(period, v, text, None)])
                )  # fmt: skip
        return pieces
    raise NormaliseError(f"{card.id}: no series mapping for adapter {a!r}")


def gdelt_volume_pieces(payload: dict, day: str, counts: dict[str, int]) -> list[SeriesPiece]:
    """GKG daily volumes per query group (D-010, D-012); the DOC API's timelines (D-009) are left out."""
    if "timeline" in payload:
        counts["skipped_doc_api_volumes"] = counts.get("skipped_doc_api_volumes", 0) + 1
        return []
    group, scope = payload["query_group"], payload["scope"]
    pieces = [SeriesPiece(f"gdelt_news|total|{scope}", {"label": "All English web documents", "measure": "documents",
              "unit": "documents", "frequency": "D", "scope": scope, "dimensions": {"query_group": None}},
              [(day, float(payload["total_documents"]), None, None)])]  # fmt: skip
    for measure in ("matching_documents", "about_documents", "names_only_documents"):
        if payload.get(measure) is None:
            continue
        pieces.append(
            SeriesPiece(f"gdelt_news|{group}|{scope}|{measure}", {"label": group, "measure": measure,
                        "unit": "documents", "frequency": "D", "scope": scope,
                        "dimensions": {"query_group": group, "ring": payload.get("ring")}},
                        [(day, float(payload[measure]), None, None)])
        )  # fmt: skip
    return pieces


def observations_from_bundles(card: SourceCard, bundles: list[tuple[str, list]],
                              counts: dict[str, int]) -> tuple[list[dict], list[dict]]:  # fmt: skip
    append = card.adapter in ("gdelt", "gdelt_gkg")
    # series -> vintage key -> (vintage_at, meta, {period: obs}, raw key, provider, collection, licence)
    vintages: dict[str, dict[str, list]] = defaultdict(dict)
    for key, records in bundles:
        run_id = key.rsplit("/", 1)[1].removesuffix(".jsonl.zst")
        for r in records:
            e = r.envelope
            if e.kind != "observation":
                continue
            if append:
                day = (parse_moment(e.event_at) or parse_moment(e.observable_at)).date().isoformat()
                pieces = gdelt_volume_pieces(r.payload, day, counts)
            else:
                pieces = series_pieces(card, r.payload, counts)
            at = parse_moment(e.observable_at) or parse_moment(e.retrieved_at)
            for p in pieces:
                vkey = run_id if not append else p.obs[0][0]  # a snapshot is a run; an append source a period
                slot = vintages[p.series_id].get(vkey)
                if slot is None:
                    slot = vintages[p.series_id][vkey] = [at, p.meta, {}, key, e.provider, e.source_collection,
                                                          e.licence]  # fmt: skip
                slot[0] = min(slot[0], at) if not append else max(slot[0], at)
                for o in p.obs:
                    slot[2][o[0]] = o
    obs_rows, series_rows = [], []
    for series_id in sorted(vintages):
        kept: list[list] = []
        previous = None
        for _, slot in sorted(vintages[series_id].items(), key=lambda kv: (kv[1][0], kv[0])):
            content = sorted(slot[2].values())
            if not append and content == previous:
                continue  # unchanged since the last vintage: no new information
            previous = content
            kept.append(slot)
        for slot in kept:
            for period, value, text, status in sorted(slot[2].values()):
                kind, start = period_start(period)
                obs_rows.append({"series_id": series_id, "source": card.id, "period": period, "period_kind": kind,
                                 "period_start": start, "value": value, "value_text": text, "status": status,
                                 "vintage_at": slot[0]})  # fmt: skip
        last = kept[-1]
        periods = sorted(last[2]) if not append else sorted({p for s in kept for p in s[2]})
        series_rows.append(
            {
                "series_id": series_id, "source": card.id, "provider": last[4], "source_collection": last[5],
                "label": last[1]["label"], "measure": last[1]["measure"], "unit": last[1]["unit"],
                "frequency": last[1]["frequency"], "scope": last[1]["scope"],
                "dimensions": canonical_json(last[1]["dimensions"]), "family": card.family,
                "rings": list(card.rings), "domains": list(card.domains), "licence": last[6],
                "n_obs": len(periods), "first_period": periods[0], "last_period": periods[-1],
                "n_vintages": len(kept), "first_seen_at": kept[0][0], "latest_vintage_at": last[0],
                "raw_object_uri": last[3],
            }
        )  # fmt: skip
    return obs_rows, series_rows


def observations_from_lake(card: SourceCard, rel: dict, paths: dict[str, Path], work: Path) -> tuple[Path, Path]:
    """WIPO's bulk indicators (`zip_csv`): each table's (office, origin, class) a series of yearly counts. Built in
    DuckDB, straight to Parquet."""
    if card.adapter != "zip_csv":
        raise NormaliseError(f"{card.id}: no lake series mapping for adapter {card.adapter!r}")
    con = duckdb.connect()
    vintage = run_time(rel["run_id"]).isoformat()
    selects = []
    for name, t in sorted(rel["tables"].items()):
        cols = [c for c, _ in t["columns"]]
        klass = next((c for c in cols if c not in ("year", "office", "origin", "count")), None)
        if klass is None or not {"year", "office", "origin", "count"} <= set(cols):
            raise NormaliseError(f"{card.id}: table {name} has unexpected columns {cols}")
        path = paths[t["key"]].as_posix()
        selects.append(
            f"SELECT '{card.id}|{name}|' || office || '|' || origin || '|' || CAST({klass} AS VARCHAR) AS series_id, "
            f"'{name}' AS tbl, '{klass}' AS klass_col, CAST({klass} AS VARCHAR) AS klass, office, origin, "
            f"CAST(year AS VARCHAR) AS period, CAST(count AS DOUBLE) AS value, '{t['key']}' AS raw_key "
            f"FROM read_parquet('{path}')"
        )
    con.execute(f"CREATE TABLE w AS {' UNION ALL '.join(selects)}")
    obs_path, series_path = work / "observations.parquet", work / "series.parquet"
    con.execute(
        f"COPY (SELECT series_id, '{card.id}' AS source, period, 'year' AS period_kind, "
        f"make_date(CAST(period AS INTEGER), 1, 1) AS period_start, value, NULL::VARCHAR AS value_text, "
        f"NULL::VARCHAR AS status, TIMESTAMPTZ '{vintage}' AS vintage_at FROM w ORDER BY series_id, period) "
        f"TO '{obs_path.as_posix()}' (FORMAT parquet, COMPRESSION zstd)"
    )
    licence = rel["licence"].replace("'", "''")
    con.execute(
        f"COPY (SELECT series_id, '{card.id}' AS source, 'WIPO' AS provider, '{card.id}' AS source_collection, "
        f"tbl || ': office ' || office || ', origin ' || origin || ', ' || klass_col || ' ' || klass AS label, "
        f"tbl AS measure, 'count' AS unit, 'A' AS frequency, office AS scope, "
        f"to_json({{'table': tbl, 'office': office, 'origin': origin, 'class': klass}})::VARCHAR AS dimensions, "
        f"'{card.family}' AS family, {list(card.rings)}::VARCHAR[] AS rings, {list(card.domains)}::VARCHAR[] AS "
        f"domains, '{licence}' AS licence, CAST(count(*) AS INTEGER) AS n_obs, min(period) AS first_period, "
        f"max(period) AS last_period, 1 AS n_vintages, TIMESTAMPTZ '{vintage}' AS first_seen_at, "
        f"TIMESTAMPTZ '{vintage}' AS latest_vintage_at, any_value(raw_key) AS raw_object_uri FROM w "
        f"GROUP BY series_id, tbl, klass_col, klass, office, origin ORDER BY series_id) "
        f"TO '{series_path.as_posix()}' (FORMAT parquet, COMPRESSION zstd)"
    )
    return obs_path, series_path


# ------------------------------------------------------------------------------------------------------------- run


def normalise_source(store: Store, card: SourceCard, cfg: FeaturesConfig, sweep_cfg: SweepFile, manifest: Manifest,
                     previous: dict | None, work: Path) -> SourceOutcome:  # fmt: skip
    out = SourceOutcome(card.id, "built")
    if card.adapter in SKIPPED:
        out.status = "skipped"
        out.warnings.append(SKIPPED[card.adapter])
        return out
    lake = card.adapter in LAKE_DOCS | LAKE_OBS
    rel = None
    if lake:
        found = release_inputs(store, card)
        if found is None:
            out.status = "skipped"
            out.warnings.append("no release in the store")
            return out
        rel, inputs = found
    else:
        inputs = bundle_inputs(store, card, out.warnings)
    out.digest = digest(card, cfg, inputs)
    prev = ((previous or {}).get("params", {}).get("sources") or {}).get(card.id) or {}
    prev_outputs = [o for o in (previous or {}).get("outputs", []) if f"/source={card.id}/" in o["key"]]
    if prev.get("digest") == out.digest and prev_outputs and all(store.exists(o["key"]) for o in prev_outputs):
        out.status, out.outputs, out.counts = "unchanged", prev_outputs, dict(prev.get("counts") or {})
        return out
    sdir = work / card.id
    sdir.mkdir(parents=True, exist_ok=True)
    counts = out.counts
    docs: list[dict] = []
    quarantined: list[dict] = []
    files: dict[str, Path] = {}
    if lake:
        paths = {k: cached_get(store, k, sha, cache_root()) for k, sha in inputs}
        if card.adapter in LAKE_DOCS:
            docs, quarantined = documents_from_lake(card, cfg, rel, paths, sweep_cfg, counts)
        else:
            obs_path, series_path = observations_from_lake(card, rel, paths, sdir)
            files["observations"], files["series"] = obs_path, series_path
            con = duckdb.connect()
            counts["series"] = con.execute(f"SELECT count(*) FROM '{series_path.as_posix()}'").fetchone()[0]
            counts["observations"] = con.execute(f"SELECT count(*) FROM '{obs_path.as_posix()}'").fetchone()[0]
    else:
        bundles = []
        for key, sha in inputs:
            data = store.get(key)
            if sha256_hex(data) != sha:
                raise NormaliseError(f"{key}: SHA-256 does not match its run manifest")
            bundles.append((key, decode_bundle(data)))
        counts["bundles"] = len(bundles)
        counts["records"] = sum(len(r) for _, r in bundles)
        if card.adapter in DOC_ADAPTERS:
            docs, quarantined = documents_from_bundles(card, cfg, bundles, sweep_cfg, counts)
        if card.adapter in OBS_ADAPTERS or card.adapter in ("gdelt", "gdelt_gkg"):
            obs_rows, series_rows = observations_from_bundles(card, bundles, counts)
            if obs_rows or card.adapter in OBS_ADAPTERS:
                counts["series"] = write_rows(series_rows, SERIES, sdir / "series.parquet", ("series_id",))
                counts["observations"] = write_rows(obs_rows, OBSERVATIONS, sdir / "observations.parquet",
                                                    ("series_id", "period", "vintage_at"))  # fmt: skip
                files["series"], files["observations"] = sdir / "series.parquet", sdir / "observations.parquet"
        if card.adapter not in DOC_ADAPTERS | OBS_ADAPTERS:
            raise NormaliseError(f"{card.id}: adapter {card.adapter!r} has no normalisation")
    if card.adapter in DOC_ADAPTERS | LAKE_DOCS:
        counts["documents"] = write_rows(docs, DOCUMENTS, sdir / "documents.parquet", ("item_id",))
        files["documents"] = sdir / "documents.parquet"
        write_rows(quarantined, QUARANTINE, sdir / "quarantine.parquet", ("item_id",))
        files["quarantine"] = sdir / "quarantine.parquet"
    for table, path in sorted(files.items()):
        out.outputs.append(upload(store, manifest, f"lake/{table}/source={card.id}/{table}.parquet", path))
    return out


def run(
    store: Store,
    cards: dict[str, SourceCard],
    cfg: FeaturesConfig,
    sweep_cfg: SweepFile,
    only: list[str] | None = None,
    config_hash: str | None = None,
) -> tuple[str, str, list[SourceOutcome]]:
    """Normalise every source (or `only` these). Carries on past a failed source; the run then fails."""
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    previous = latest_passed(store)
    outcomes: list[SourceOutcome] = []
    with tempfile.TemporaryDirectory(prefix="moria-normalise-") as tmp:
        for sid in sorted(cards):
            card = cards[sid]
            if only and sid not in only:
                # carried over untouched from the previous passed run
                prev = ((previous or {}).get("params", {}).get("sources") or {}).get(sid)
                outs = [o for o in (previous or {}).get("outputs", []) if f"/source={sid}/" in o["key"]]
                if prev:
                    outcomes.append(SourceOutcome(sid, "unchanged", dict(prev.get("counts") or {}), [], outs,
                                                  prev.get("digest")))  # fmt: skip
                continue
            try:
                o = normalise_source(store, card, cfg, sweep_cfg, manifest, previous, Path(tmp))
            except Exception as e:  # one line naming the source; the run carries on and then fails
                first = (str(e).splitlines() or [type(e).__name__])[0]
                o = SourceOutcome(sid, "failed", error=f"{sid}: {type(e).__name__}: {first[:300]}")
                log.error("%s: failed: %s", sid, o.error)
            else:
                log.info("%s: %s %s", sid, o.status, json.dumps(o.counts, sort_keys=True))
            outcomes.append(o)
    for o in outcomes:
        if o.status == "unchanged":
            manifest.outputs.extend(o.outputs)
        manifest.warnings.extend(f"{o.source}: {w}" for w in o.warnings)
    manifest.params = {
        "only": only,
        "version": NORMALISE_VERSION,
        "sources": {o.source: {"status": o.status, "digest": o.digest, "counts": o.counts, "error": o.error}
                    for o in outcomes},
    }  # fmt: skip
    totals: dict[str, int] = defaultdict(int)
    for o in outcomes:
        totals[f"sources_{o.status}"] += 1
        for k in ("documents", "series", "observations", "quarantined"):
            totals[k] += o.counts.get(k, 0)
    manifest.counts = dict(sorted(totals.items()))
    failed = [o for o in outcomes if o.status == "failed"]
    status = "failed" if failed else "passed"
    error = "; ".join(o.error for o in failed)[:1000] if failed else None
    return status, manifest.finish(store, status, error), outcomes


def latest_passed(store: Store) -> dict | None:
    """The newest normalise run that passed."""
    runs = [json.loads(store.get(k)) for k in store.list(f"manifests/{COMMAND}/") if k.endswith(".json")]
    passed = [m for m in runs if m["status"] == "passed"]
    return max(passed, key=lambda m: (m["run_id"][:16], m.get("started_ns") or 0, m["run_id"])) if passed else None
