"""`moria ipr metrics`: monthly demand, outcome and timeliness series from IP RAPID (design §6.2 `ipr_metrics`, §7;
the territories' `ipr_indicators`, config/territories.yaml). Organisation, sector and country level only: no output
names or profiles a person (design §12).

Reads the latest IP RAPID release in the lake: its base, with the latest delta applied (a delta holds the rows added
since the base and the rows of the base no longer present). Writes, in the same shapes as `moria normalise`:
`lake/ipr_metrics/series.parquet` and `lake/ipr_metrics/observations.parquet`, so day 4's detectors read them with
every other series. Each release is a vintage: a value unchanged since the previous release adds nothing. The
release's own month is incomplete and is marked `status: incomplete`.

The series (`ip_rapid_metrics|<metric>|<right>[|<split>]`), monthly from 2000:
- demand, by application month: applications (by sub-type); by the founding applicants' origin (any Australian
  applicant, else overseas); filed without a founding agent (self-filed); first-time applicants (a founding
  applicant's first application of that right); Madrid applications designating Australia; patent applications in AI
  (IPC or CPC G06N, current classifications);
- outcomes, by event month: registrations or grants, acceptances, lapses, withdrawals, refusals, oppositions,
  non-use removal applications, ownership changes, renewals, examination requests (current events only; the
  `*_historical` categories are migrated records);
- timeliness: the median days from filing to registration or grant, by registration month (the application
  table's own date; the `accepted` event is not examination acceptance for every right).

A series whose last month is more than 12 months before the release is left out and counted as discontinued: some
event categories stopped when IP Australia's systems changed (trade mark renewals and examination requests end in
November 2018).
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from .config import SourceCard
from .manifest import Manifest
from .records import canonical_json
from .store import Store
from .tables import OBSERVATIONS, SERIES, cache_root, cached_get, latest_manifest, read_rows, upload, write_rows
from .text import period_start

log = logging.getLogger("moria.iprmetrics")

COMMAND = "ipr.metrics"
SOURCE = "ip_rapid_metrics"
START = "2000-01-01"

# (metric, rights, event categories): outcome counts by event month
OUTCOMES = [
    ("registered", ("trade_mark",), ("granted",)),
    ("registered", ("design",), ("registered",)),
    ("granted", ("patent", "pbr"), ("granted",)),
    ("accepted", ("patent", "trade_mark", "pbr"), ("accepted",)),
    ("lapsed", ("patent", "trade_mark", "design"), ("lapsed",)),
    ("withdrawn", ("patent", "trade_mark", "design", "pbr"), ("withdrawn",)),
    ("refused", ("patent", "trade_mark", "design", "pbr"), ("refused",)),
    ("oppositions", ("trade_mark",), ("opposition",)),
    ("oppositions", ("patent",), ("publish_opposition",)),
    ("non_use_removal", ("trade_mark",), ("publish_non_use",)),
    ("ownership_changes", ("patent", "trade_mark", "design"), ("publish_ownership",)),
    ("renewals", ("trade_mark", "design"), ("publish_renew",)),
    ("exam_requests", ("patent", "trade_mark", "design"), ("exam_request",)),
]
LABELS = {
    "applications": "Applications filed",
    "applications_au": "Applications with an Australian founding applicant",
    "applications_overseas": "Applications with only overseas founding applicants",
    "applications_self_filed": "Applications filed without a founding agent",
    "first_time_applicants": "Founding applicants filing their first application of this right",
    "madrid_designating_au": "Madrid international registrations designating Australia",
    "applications_ai_g06n": "Patent applications classified in G06N (AI)",
    "days_to_registration_median": "Median days from filing to registration or grant, by registration month",
}


def _q(path: Path) -> str:
    text = path.as_posix()
    if "'" in text:
        raise ValueError(f"a path with a quote can't go into SQL: {text!r}")
    return text


def current_tables(con: duckdb.DuckDBPyConnection, base: dict[str, Path], delta: dict[str, Path]) -> None:
    """A view per table: the base, with the latest delta's removed rows taken out and its added rows put in."""
    for table, path in sorted(base.items()):
        b = f"read_parquet('{_q(path)}')"
        if table in delta:
            d = f"read_parquet('{_q(delta[table])}')"
            con.execute(
                f"CREATE VIEW {table} AS (SELECT * FROM {b} EXCEPT ALL SELECT * EXCLUDE (_change) FROM {d} "
                f"WHERE _change = 'removed') UNION ALL SELECT * EXCLUDE (_change) FROM {d} WHERE _change = 'added'"
            )
        else:
            con.execute(f"CREATE VIEW {table} AS SELECT * FROM {b}")


def metric_rows(con: duckdb.DuckDBPyConnection, release: date) -> list[tuple[str, str, str, float]]:
    """(metric, right, split, period) -> value rows, as (series key, period, unit, value)."""
    end = release.isoformat()
    month = "strftime(date_trunc('month', {}), '%Y-%m')"
    window = f"BETWEEN DATE '{START}' AND DATE '{end}'"
    con.execute(
        f"CREATE TEMP TABLE apps AS SELECT application_number, ip_right_type AS r, ip_right_sub_type AS sub, "
        f"application_date AS filed, {month.format('application_date')} AS m FROM application "
        f"WHERE application_date {window}"
    )
    con.execute(
        "CREATE TEMP TABLE founders AS SELECT ip_right_type AS r, application_number, party_role_category AS cat, "
        "party_id, lower(country_code) AS country_code FROM party_activity "
        "WHERE is_founding AND party_role_category IN ('applicant', 'applicant_agent')"
    )
    queries = [
        ("applications|' || r || '|all", "SELECT m, r, count(*) FROM apps GROUP BY ALL"),
        ("applications|' || r || '|' || sub", "SELECT m, r, sub, count(*) FROM apps WHERE r IN ('patent', "
         "'trade_mark') GROUP BY ALL"),
        ("applications_au|' || r", "SELECT m, r, count(*) FROM apps a WHERE EXISTS (SELECT 1 FROM founders f WHERE "
         "f.application_number = a.application_number AND f.r = a.r AND f.cat = 'applicant' AND f.country_code = "
         "'au') GROUP BY ALL"),
        ("applications_overseas|' || r", "SELECT m, r, count(*) FROM apps a WHERE EXISTS (SELECT 1 FROM founders f "
         "WHERE f.application_number = a.application_number AND f.r = a.r AND f.cat = 'applicant') AND NOT EXISTS "
         "(SELECT 1 FROM founders f WHERE f.application_number = a.application_number AND f.r = a.r AND f.cat = "
         "'applicant' AND f.country_code = 'au') GROUP BY ALL"),
        # self-filed: no founding agent other than one of the founding applicants (a third of trade mark
        # applications name the applicant itself as its agent, its address for service)
        ("applications_self_filed|' || r",
         "SELECT m, r, count(*) FROM apps a WHERE NOT EXISTS (SELECT 1 FROM founders g WHERE "
         "g.application_number = a.application_number AND g.r = a.r AND g.cat = 'applicant_agent' AND NOT EXISTS "
         "(SELECT 1 FROM founders p WHERE p.application_number = a.application_number AND p.r = a.r AND "
         "p.cat = 'applicant' AND p.party_id = g.party_id)) GROUP BY ALL"),
        ("first_time_applicants|' || r",
         "SELECT m, r, count(*) FROM (SELECT f.r, f.party_id, min(a.application_date) AS first FROM founders f "
         "JOIN application a ON a.application_number = f.application_number AND a.ip_right_type = f.r "
         "WHERE f.cat = 'applicant' AND f.party_id IS NOT NULL GROUP BY ALL) x, LATERAL "
         f"(SELECT {month.format('first')} AS m) WHERE first {window} GROUP BY ALL"),
        ("madrid_designating_au|' || r", "SELECT m, r, count(DISTINCT a.application_number) FROM apps a JOIN "
         "application_links l ON l.application_number = a.application_number AND l.ip_right_type = a.r WHERE "
         "l.link_type = 'madrid_import' GROUP BY ALL"),
        ("applications_ai_g06n|' || r", "SELECT m, r, count(DISTINCT a.application_number) FROM apps a JOIN "
         "application_classification c ON c.application_number = a.application_number AND c.ip_right_type = a.r "
         "WHERE c.is_current AND c.classification_system IN ('ipc_mark', 'cpc_mark') AND c.classification LIKE "
         "'G06N%' GROUP BY ALL"),
    ]  # fmt: skip
    out: list[tuple[str, str, str, float]] = []
    for key, sql in queries:
        for row in con.execute(sql).fetchall():
            m, r, *rest, n = row
            series = key.split("|")[0] + "|" + r + ("|" + rest[0] if rest else ("|all" if "|all" in key else ""))
            out.append((series, m, "applications", float(n)))
    for metric, rights, cats in OUTCOMES:
        listed_r = ", ".join(f"'{r}'" for r in rights)
        listed_c = ", ".join(f"'{c}'" for c in cats)
        sql = (f"SELECT {month.format('event_effective_date')} AS m, ip_right_type, count(DISTINCT application_number) "
               f"FROM application_events WHERE ip_right_type IN ({listed_r}) AND event_category IN ({listed_c}) "
               f"AND event_effective_date {window} GROUP BY ALL")  # fmt: skip
        for m, r, n in con.execute(sql).fetchall():
            out.append((f"{metric}|{r}", m, "applications", float(n)))
    sql = (
        f"SELECT {month.format('gained_registration_status_date')} AS m, ip_right_type, "
        f"median(date_diff('day', application_date, gained_registration_status_date)) FROM application "
        f"WHERE gained_registration_status_date {window} AND gained_registration_status_date >= application_date "
        f"GROUP BY ALL"
    )
    for m, r, d in con.execute(sql).fetchall():
        out.append((f"days_to_registration_median|{r}", m, "days", float(d)))
    return sorted(out)


def drop_discontinued(rows: list[tuple[str, str, str, float]], release: date, months: int = 12):
    """Rows of series that are still published: a series whose last month is more than `months` before the
    release's month has stopped (a system change, not a trend) and is left out."""
    last: dict[str, str] = {}
    for key, period, _, _ in rows:
        last[key] = max(last.get(key, period), period)
    y, m = release.year, release.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    cutoff = f"{y:04d}-{m:02d}"
    stopped = sorted(k for k, p in last.items() if p < cutoff)
    return [r for r in rows if r[0] not in set(stopped)], stopped


def latest_release(store: Store) -> tuple[dict, dict | None]:
    """The latest release manifest of IP RAPID, and of its base when it is a delta."""
    found = []
    for key in store.list("raw/ip_rapid/"):
        if key.endswith("/manifest.json"):
            found.append(json.loads(store.get(key)))
    if not found:
        raise ValueError("no IP RAPID release in the store; run `moria ipr refresh` first")
    found.sort(key=lambda r: r["release_date"])
    latest = found[-1]
    if latest.get("mode") == "base":
        return latest, None
    base = next(r for r in found if r["release_date"] == latest["base_release"])
    return base, latest


def metrics(store: Store, card: SourceCard, config_hash: str | None = None, threads: int = 4,
            memory_limit: str = "3GB") -> tuple[str, str, dict]:  # fmt: skip
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        base, delta = latest_release(store)
        release = date.fromisoformat((delta or base)["release_date"])
        manifest.params = {"release": release.isoformat(), "base": base["release_date"], "delta": bool(delta)}
        base_paths = {t: cached_get(store, v["key"], v.get("sha256"), cache_root()) for t, v in base["tables"].items()}
        delta_paths = {}
        if delta:
            delta_paths = {
                t: cached_get(store, v["key"], v.get("sha256"), cache_root()) for t, v in delta["tables"].items()
            }
        con = duckdb.connect()
        con.execute(f"SET threads TO {int(threads)}; SET memory_limit = '{memory_limit}'")
        with tempfile.TemporaryDirectory(prefix="moria-iprm-") as tmp:
            con.execute(f"SET temp_directory = '{_q(Path(tmp))}'")
            current_tables(con, base_paths, delta_paths)
            rows = metric_rows(con, release)
            rows, discontinued = drop_discontinued(rows, release)
            vintage = datetime(release.year, release.month, release.day, tzinfo=UTC)
            obs, series = vintaged(store, rows, release, vintage, card)
            counts = {"series": write_rows(series, SERIES, Path(tmp) / "series.parquet", ("series_id",)),
                      "observations": write_rows(obs, OBSERVATIONS, Path(tmp) / "observations.parquet",
                                                 ("series_id", "period", "vintage_at"))}  # fmt: skip
            for name in ("observations", "series"):
                upload(store, manifest, f"lake/ipr_metrics/{name}.parquet", Path(tmp) / f"{name}.parquet")
        counts["discontinued_series"] = len(discontinued)
        manifest.params["discontinued"] = discontinued
        manifest.counts = counts
        return "passed", manifest.finish(store, "passed"), counts
    except Exception as e:
        first = (str(e).splitlines() or [type(e).__name__])[0]
        cause = f"{COMMAND}: {type(e).__name__}: {first[:300]}"
        log.error("%s", cause)
        return "failed", manifest.finish(store, "failed", cause), {"error": cause}


def vintaged(store: Store, rows: list[tuple[str, str, str, float]], release: date, vintage: datetime,
             card: SourceCard) -> tuple[list[dict], list[dict]]:  # fmt: skip
    """This release's values as a new vintage on top of the previous run's, adding only values that changed."""
    previous = latest_manifest(store, COMMAND)
    old: list[dict] = []
    if previous and previous["status"] == "passed":
        o = next((x for x in previous["outputs"] if x["key"].endswith("observations.parquet")), None)
        if o:
            old = [r for r in read_rows(cached_get(store, o["key"], o["sha256"], cache_root()))
                   if r["vintage_at"] < vintage]  # fmt: skip
    latest_old: dict[tuple[str, str], dict] = {}
    for r in sorted(old, key=lambda r: r["vintage_at"]):
        latest_old[(r["series_id"], r["period"])] = r
    incomplete = release.strftime("%Y-%m")
    new = []
    units = {}
    for key, period, unit, value in rows:
        sid = f"{SOURCE}|{key}"
        units[sid] = unit
        status = "incomplete" if period == incomplete else None
        prev = latest_old.get((sid, period))
        if prev and prev["value"] == value and prev["status"] == status:
            continue
        kind, start = period_start(period)
        new.append({"series_id": sid, "source": SOURCE, "period": period, "period_kind": kind, "period_start": start,
                    "value": value, "value_text": None, "status": status, "vintage_at": vintage})  # fmt: skip
    obs = old + new
    series = []
    by: dict[str, list[dict]] = {}
    for r in obs:
        by.setdefault(r["series_id"], []).append(r)
    for sid in sorted(by):
        rs = by[sid]
        periods = sorted({r["period"] for r in rs})
        _, metric, right, *split = sid.split("|")
        label = LABELS.get(metric, metric.replace("_", " ").capitalize())
        series.append({
            "series_id": sid, "source": SOURCE, "provider": "IP Australia (IP RAPID)", "source_collection": "ip_rapid",
            "label": f"{label}: {right.replace('_', ' ')}" + (f" ({split[0].replace('_', ' ')})" if split else ""),
            "measure": metric, "unit": units.get(sid, "applications"), "frequency": "M", "scope": "AUS",
            "dimensions": canonical_json({"metric": metric, "right": right, "split": split[0] if split else None}),
            "family": card.family, "rings": list(card.rings), "domains": list(card.domains), "licence": card.licence,
            "n_obs": len(periods), "first_period": periods[0], "last_period": periods[-1],
            "n_vintages": len({r["vintage_at"] for r in rs}), "first_seen_at": min(r["vintage_at"] for r in rs),
            "latest_vintage_at": max(r["vintage_at"] for r in rs),
            "raw_object_uri": f"raw/ip_rapid/{release}/manifest.json",
        })  # fmt: skip
    return obs, series
