"""`moria dossier --as-of D`: an evidence dossier for each shortlisted candidate (design §8.4; day 5).

Explanations start from the evidence, never from a score. Each dossier holds:
- **the detectors' numbers,** with their windows and the runs they came from;
- **the original evidence:** for documents, the window items, one per de-duplication group, with links, event and
  observable dates and the number of copies; for series, the series behind it (subject, denominator, reference,
  peers) and a small chart of the latest periods;
- **the alternative-explanations checklist:** each artefact check's outcome (coverage, ingestion, duplicate, news
  cycle, source break, label drift), a seasonal pattern (monthly and quarterly series), known administrative or
  recording causes (`dossier.administrative_events`) with the primary sources in the window that mention the
  subject, 'explained by its context' (D-028), the nearest known trend, and the redundancy group;
- **counter-evidence:** BM25 hits for the subject's words that use words of the opposite direction (hits to read,
  not established contradiction);
- **the nearest historical analogues:** for documents, the earlier items nearest the candidate's own (embeddings),
  with what became of them in the register; for series, the series' own similar past moves and whether they lasted;
- **sample works** (OpenAlex surges and anomalies; the handover's flag 3): the works behind the count, by venue,
  so a surge that is one book or one journal issue shows as concentrated;
- the candidate's **history** in earlier scans, and the ranking's components.

Writes `interpretation/dossiers/<candidate_id>/<as_of>.json` and `.md` (one version per scan), in the private
bucket only: dossiers hold titles and links, so nothing of them is logged. The decision model reads the JSON
(`moria pathways`); people read the Markdown, or the register's spreadsheet.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np

from .concepts import COMMAND as DOCS
from .concepts import load_items
from .config import BaselineFile, DetectConfig, ReviewConfig, SourceCard
from .detect import COMMAND as DETECT
from .detect import _matching
from .features import DEDUP, EMBED, INDEX, KEYPHRASES, load_vectors
from .manifest import Manifest
from .measures import COMMAND as SERIES
from .measures import Series, as_of_end, index_label, load_series, period_index_of_label, synthetic_totals
from .rank import COMMAND as RANK
from .rank import failed, files_of, manifest_of
from .records import canonical_json
from .store import Store
from .tables import cache_root, fetch_outputs, latest_manifest, read_rows

log = logging.getLogger("moria.dossier")

COMMAND = "dossier"
SPARK = "".join(chr(c) for c in range(0x2581, 0x2589))  # the eight block heights
_WORD = re.compile(r"[a-z][a-z\-]{2,}")
_URL = re.compile(r"^https?://[^\s()<>\[\]]+$")
# words of statistical labels that say nothing about the subject (search terms are what is left)
_GENERIC_WORDS = (
    "original seasonally adjusted trend current prices chain volume measures measure index percentage change changes "
    "total all activities persons australia australian dollars usd ppp converted constant units unit number "
    "annual quarterly monthly per cent rate ratio share world oecd value values level levels sector sectors "
    "calendar neither nor expenditure amplitude harmonised from to of the and or in on for by with cpc ipc nice "
    "subclass class classes founding applications applicants filed"
)
GENERIC = frozenset(_GENERIC_WORDS.split())


def key_of(cid: str, as_of: date, ext: str) -> str:
    return f"interpretation/dossiers/{cid}/{as_of.isoformat()}.{ext}"


def _iso(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.astimezone(UTC).isoformat(timespec="seconds")
    return v.isoformat() if isinstance(v, date) else str(v)


def _r(v, n=4):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), n)


def sparkline(values: list[float | None]) -> str:
    vals = [v for v in values if v is not None and math.isfinite(v)]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    out = []
    for v in values:
        if v is None or not math.isfinite(v):
            out.append(" ")
        elif hi == lo:
            out.append(SPARK[3])
        else:
            out.append(SPARK[min(7, int((v - lo) / (hi - lo) * 7.999))])
    return "".join(out)


def md_text(s: str | None, limit: int = 200) -> str:
    """Untrusted text made inert in Markdown: one line, cut, and every character that could make a link, an image,
    markup or a table cell escaped."""
    s = " ".join((s or "").split())[:limit]
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_\[\]|])", r"\\\1", s)


def md_link(url: str | None) -> str:
    return f"<{url}>" if url and _URL.match(url) else ""


def query_terms(label: str | None, limit: int = 8) -> list[str]:
    """Search words from a label: its first two parts (statistics labels are 'indicator · breakdown · area · unit'),
    without stopwords or words that say nothing about the subject. Class codes give none."""
    from .features import _stopwords

    stop = _stopwords()
    parts = (label or "").replace(";", " · ").split(" · ")[:2]
    out: list[str] = []
    for w in _WORD.findall(" ".join(parts).lower()):
        if w not in stop and w not in GENERIC and w not in out:
            out.append(w)
    return out[:limit]


# ------------------------------------------------------------------------------------------------- series parts


def series_chart(s: Series | None, denom: Series | None, transform: str | None, n: int) -> dict | None:
    if s is None or not s.points:
        return None
    if transform == "log_share" and denom is not None and denom.points:
        # a count absent from a period its source covered is a zero (D-022)
        idx = [i for i in sorted(denom.points) if i >= min(s.points)][-n:]
        vals = [s.points.get(i, 0.0) / denom.points[i] if denom.points.get(i) else None for i in idx]
        shown = "share of the source's volume"
    else:
        idx = sorted(s.points)[-n:]
        vals = [s.points[i] for i in idx]
        shown = "value"
    return {"series_id": s.series_id, "frequency": s.kind, "shown": shown,
            "periods": [index_label(s.kind, i) for i in idx], "values": [_r(v, 8) for v in vals],
            "sparkline": sparkline(vals)}  # fmt: skip


def seasonal_check(s: Series | None, period: str | None, direction: int) -> dict:
    """Whether the anomaly's calendar month or quarter was also unusual, the same way, in the previous three years:
    each year's value against that year's mean."""
    if s is None or s.kind not in ("M", "Q") or not period:
        return {"check": "seasonal", "outcome": "n/a", "detail": "not a monthly or quarterly anomaly"}
    i = period_index_of_label(s.kind, period)
    per_year = 12 if s.kind == "M" else 4
    if i is None:
        return {"check": "seasonal", "outcome": "n/a", "detail": "no period"}
    ratios = []
    for k in (1, 2, 3):
        j = i - k * per_year
        year = [s.points.get(j - (j % per_year) + m) for m in range(per_year)]
        year = [v for v in year if v is not None]
        if s.points.get(j) is None or len(year) < per_year - 1 or not np.mean(year):
            continue
        ratios.append(s.points[j] / float(np.mean(year)) - 1)
    if len(ratios) < 2:
        return {"check": "seasonal", "outcome": "n/a", "detail": "fewer than 2 earlier years"}
    same = sum(1 for r in ratios if r * direction > 0.10)
    outcome = "flag" if same >= 2 else "pass"
    detail = (f"the same {'month' if s.kind == 'M' else 'quarter'} was {', '.join(f'{r:+.0%}' for r in ratios)} "
              f"against its year's mean in the previous {len(ratios)} years")  # fmt: skip
    return {"check": "seasonal", "outcome": outcome, "detail": detail}


def jump_analogues(s: Series, direction: int, follow: int, k: int) -> list[dict]:
    """Earlier moves of the series like its latest one (the same direction, at least 70% of its size against the
    median of the 12 periods before), and whether each lasted: the level `follow` periods later still at least half
    the jump above (below) the median before it."""
    idx = sorted(s.points)
    vals = np.array([s.points[i] for i in idx], dtype=float)
    if len(vals) < 30:
        return []

    def dev(t):
        base = np.median(vals[max(0, t - 12) : t])
        scale = abs(base) or 1.0
        return (vals[t] - base) / scale, base

    cur, _ = dev(len(vals) - 1)
    if cur * direction <= 0:
        return []
    out, t = [], len(vals) - 1 - follow
    while t >= 12 and len(out) < k:
        d, base = dev(t)
        if d * direction > 0 and abs(d) >= 0.7 * abs(cur):
            later = vals[min(t + follow, len(vals) - 1)]
            lasted = (later - base) * direction >= 0.5 * abs(vals[t] - base)
            out.append({"period": index_label(s.kind, idx[t]), "move": _r(d), "after": _r((later - base) / (abs(base)
                        or 1.0)), "lasted": bool(lasted), "follow_periods": follow})  # fmt: skip
            t -= follow
        else:
            t -= 1
    return out


def trend_analogues(s: Series, window: int, follow: int) -> dict | None:
    """How unusual the latest window's growth is in the series' own history: its rank among every earlier window of
    the same length, and how often the earlier windows that grew as fast kept growing over the next periods."""
    idx = sorted(s.points)
    vals = np.array([s.points[i] for i in idx], dtype=float)
    if len(vals) < window * 2:
        return None
    # growth on a log scale where every value is positive; else in units of the mean absolute level
    logs = np.log(vals) if np.all(vals > 0) else vals / max(float(np.mean(np.abs(vals))), 1e-12)
    growth = np.array([logs[t] - logs[t - window] for t in range(window, len(vals))])
    cur = growth[-1]
    earlier = growth[:-window] if len(growth) > window else growth[:0]
    if not len(earlier):
        return None
    faster = [t for t in range(len(earlier)) if earlier[t] * np.sign(cur) >= abs(cur)]
    kept = [t for t in faster if t + window + follow < len(vals)
            and (logs[t + window + follow] - logs[t + window]) * np.sign(cur) > 0]  # fmt: skip
    return {"window_periods": window, "growth": _r(cur), "percentile": _r(float(np.mean(earlier * np.sign(cur)
            < abs(cur)))), "earlier_as_fast": len(faster), "kept_going": len(kept)}  # fmt: skip


# --------------------------------------------------------------------------------------------- the layer it reads


class Layer:
    """The scan's evidence, read once for every dossier."""

    def __init__(self, store: Store, detect_cfg: DetectConfig, cards: dict[str, SourceCard], as_of: date,
                 dim: int = 384):  # fmt: skip
        self.store, self.cfg, self.cards, self.as_of, self.dim = store, detect_cfg, cards, as_of, dim
        rm = _matching(store, RANK, as_of)
        p = rm["params"]
        self.runs = {"rank_run": rm["run_id"], **{k: p[k] for k in ("detect_run", "artefacts_run", "series_run",
                                                                     "documents_run")}}  # fmt: skip
        self.ranked = read_rows(files_of(store, rm, "review/")["ranked.parquet"])
        dm, am = manifest_of(store, DETECT, p["detect_run"]), manifest_of(store, "artefacts", p["artefacts_run"])
        self.sm, self.docm = manifest_of(store, SERIES, p["series_run"]), manifest_of(store, DOCS, p["documents_run"])
        cf = {**files_of(store, dm, "candidates/"), **files_of(store, am, "candidates/")}
        self.cands = {c["candidate_id"]: c for c in read_rows(cf["candidates.parquet"])}
        self.evidence: dict[str, list[dict]] = defaultdict(list)
        for e in read_rows(cf["evidence.parquet"]):
            self.evidence[e["candidate_id"]].append(e)
        self.artefacts = {a["candidate_id"]: a for a in read_rows(cf["artefacts.parquet"])}
        sf = files_of(store, self.sm, "measures/series/")
        self.measures = {r["series_id"]: r for r in read_rows(sf["measures.parquet"], ["series_id", "frequency",
                         "transform", "denominator", "last_period", "trend_w3_periods"])}  # fmt: skip
        self.doc_files = files_of(store, self.docm, "measures/documents/")
        self._docs = self._series = self._vectors = self._kp = self._items = None
        self.index_db, self.index_run = self._index()
        self.ipr = IprSampler(store)
        self.history = self._history()

    # documents and their features (the runs the document measures were built on)
    def _run(self, command: str, key: str) -> dict:
        return manifest_of(self.store, command, self.docm["params"][key])

    def documents(self) -> dict[str, dict]:
        if self._docs is None:
            nm = manifest_of(self.store, "normalise", self.docm["params"]["normalise_run"])
            self._docs = {}
            cols = ["item_id", "source", "family", "doc_type", "title", "url", "outlet", "event_at", "observable_at",
                    "first_seen_at"]  # fmt: skip
            for p in fetch_outputs(self.store, nm, "lake/documents/", cache_root()).values():
                for r in read_rows(p, cols):
                    self._docs[r["item_id"]] = r
            groups = fetch_outputs(self.store, self._run(DEDUP, "dedup_run"), "features/dedup/", cache_root())
            for r in read_rows(next(iter(groups.values())), ["item_id", "dedup_group", "group_size"]):
                d = self._docs.get(r["item_id"])
                if d is not None:
                    d["dedup_group"], d["group_size"] = r["dedup_group"], r["group_size"]
        return self._docs

    def visible_items(self) -> dict[str, dict]:
        """Items in the scan's window and baseline, as the document measures saw them."""
        if self._items is None:
            nm = manifest_of(self.store, "normalise", self.docm["params"]["normalise_run"])
            files = {"documents": {k.split("/source=")[1].split("/")[0]: p for k, p in
                                   fetch_outputs(self.store, nm, "lake/documents/", cache_root()).items()},
                     "dedup": fetch_outputs(self.store, self._run(DEDUP, "dedup_run"), "features/dedup/",
                                            cache_root()),
                     "tags": fetch_outputs(self.store, self._run("tag", "tags_run"), "features/tags/",
                                           cache_root())}  # fmt: skip
            items, _ = load_items(files, self.cards, self.as_of, self.cfg)
            self._items = {i["item_id"]: i for i in items}
        return self._items

    def keyphrases(self) -> dict[str, set[str]]:
        """phrase -> the items it was kept for."""
        if self._kp is None:
            self._kp = defaultdict(set)
            for k, p in fetch_outputs(self.store, self._run(KEYPHRASES, "kp_run"), "features/keyphrases/",
                                      cache_root()).items():  # fmt: skip
                if "/source=" in k:
                    for r in read_rows(p, ["item_id", "phrase"]):
                        self._kp[r["phrase"]].add(r["item_id"])
        return self._kp

    def vectors(self) -> tuple[list[str], np.ndarray]:
        if self._vectors is None:
            em = self._run(EMBED, "emb_run")
            paths = {k.split("/source=")[1].split("/")[0]: p for k, p in
                     fetch_outputs(self.store, em, "features/embeddings/", cache_root()).items()}  # fmt: skip
            self._vectors = load_vectors(paths, self.dim)
        return self._vectors

    def series(self, wanted: set[str]) -> dict[str, Series]:
        if self._series is None:
            self._series = {}
        need = wanted - set(self._series)
        if need:
            pairs = []
            nm = manifest_of(self.store, "normalise", self.sm["params"]["normalise_run"])
            files = fetch_outputs(self.store, nm, "lake/", cache_root())
            for src in sorted(set(self.cfg.series.sources) - {"ip_rapid_metrics"}):
                s = f"lake/series/source={src}/series.parquet"
                o = f"lake/observations/source={src}/observations.parquet"
                if s in files and o in files:
                    pairs.append((files[s], files[o]))
            if self.sm["params"].get("ipr_metrics_run"):
                im = manifest_of(self.store, "ipr.metrics", self.sm["params"]["ipr_metrics_run"])
                f = fetch_outputs(self.store, im, "lake/ipr_metrics/", cache_root())
                pairs.append((f["lake/ipr_metrics/series.parquet"], f["lake/ipr_metrics/observations.parquet"]))
            only = {w for w in need if "|*|" not in w}
            for w in need:  # a synthetic total (all CPC subclasses) needs every series of its source
                if "|*|" in w:
                    only |= {m for m in self.measures if m.startswith(w.split("|*|")[0] + "|")}
            got = load_series(pairs, self.cfg, self.as_of, only=only)
            synthetic_totals(got)
            self._series.update(got)
            for w in need:
                self._series.setdefault(w, None)
        return {w: self._series.get(w) for w in wanted}

    def _index(self) -> tuple[Path | None, str | None]:
        m = latest_manifest(self.store, INDEX)
        if not m or m["status"] != "passed":
            return None, None
        (db,) = fetch_outputs(self.store, m, "features/index/", cache_root()).values()
        return db, m["run_id"]

    def _history(self) -> list[tuple[str, dict[str, dict]]]:
        """The candidates of earlier scans: (as_of, {candidate_id: candidate}), newest first."""
        by_day: dict[str, dict] = {}
        for k in sorted(self.store.list(f"manifests/{DETECT}/")):
            m = json.loads(self.store.get(k))
            day = m["params"].get("as_of")
            newer = day not in by_day or (m.get("started_ns") or 0) > (by_day[day].get("started_ns") or 0)
            if m["status"] == "passed" and day and day < self.as_of.isoformat() and newer:
                by_day[day] = m
        return [(d, by_day[d]) for d in sorted(by_day, reverse=True)]

    def history_of(self, cid: str, n: int) -> list[dict]:
        out = []
        for day, m in self.history[:n]:
            if "_cands" not in m:
                f = files_of(self.store, m, "candidates/")
                m["_cands"] = {c["candidate_id"]: c for c in read_rows(f["candidates.parquet"], ["candidate_id",
                               "type", "strength", "detectors"])}  # fmt: skip
            c = m["_cands"].get(cid)
            out.append({"as_of": day, "present": c is not None, "type": c and c["type"],
                        "strength": c and _r(c["strength"]), "detectors": c and list(c["detectors"])})  # fmt: skip
        return out


# --------------------------------------------------------------------------------------------------------- search


def covered(terms: list[str], text: str) -> int:
    """How many search words a hit's title and summary hold (a word's first five letters, so plurals count): BM25
    ranks any one word, and a hit on one common word of several says little."""
    low = text.lower()
    return sum(1 for t in terms if t[:5] in low)


def bm25_hits(db: Path | None, terms: list[str], since: datetime, until: datetime, families: list[str] | None,
              limit: int) -> list[dict]:  # fmt: skip
    if db is None or not terms:
        return []
    con = duckdb.connect(str(db), read_only=True)
    try:
        con.execute("INSTALL fts; LOAD fts")  # a runner installs the extension on first use
        where = [
            "score IS NOT NULL",
            "observable_at >= CAST(? AS TIMESTAMPTZ)",
            "observable_at < CAST(? AS TIMESTAMPTZ)",
        ]
        args: list = [" ".join(terms), since.isoformat(), until.isoformat()]
        if families:
            where.append("family IN (SELECT unnest(?))")
            args.append(families)
        args.append(max(limit * 20, 100))  # the word-coverage filter below keeps fewer
        rows = con.execute(
            f"SELECT item_id, source, family, strftime(observable_at, '%Y-%m-%dT%H:%M:%SZ'), title, summary, url, "
            f"round(score, 3) FROM ("
            f"SELECT *, fts_main_docs.match_bm25(item_id, ?) AS score FROM docs) WHERE {' AND '.join(where)} "
            f"ORDER BY score DESC, item_id LIMIT ?",
            args,
        ).fetchall()
    finally:
        con.close()
    need = len(terms) if len(terms) <= 2 else math.ceil(len(terms) / 2)
    rows = [r for r in rows if covered(terms, f"{r[4] or ''} {r[5] or ''}") >= need][:limit]
    return [{"item_id": r[0], "source": r[1], "family": r[2], "observable_at": r[3], "title": r[4],
             "summary": r[5], "url": r[6], "score": r[7]} for r in rows]  # fmt: skip


# ----------------------------------------------------------------------------------------------- OpenAlex samples


class OpenAlexSampler:
    """The works behind an OpenAlex count, by venue (exact, one group_by call) and as a seeded random sample to read
    (one call): 1 credit each of the key's free daily budget, checked first; a key with a prepaid balance is refused,
    as the collector refuses it."""

    def __init__(self, client, card: SourceCard, cfg: ReviewConfig):
        from .collectors.openalex import OpenAlexCountsParams

        self.client, self.cfg = client, cfg.dossier.openalex_samples
        self.params = OpenAlexCountsParams.model_validate(card.params)
        self.calls = 0
        self.ready: bool | None = None
        self.note = ""

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {os.environ.get(self.params.api_key_env, '')}"}

    def _check(self) -> bool:
        if self.ready is None:
            if not os.environ.get(self.params.api_key_env):
                self.ready, self.note = False, f"{self.params.api_key_env} is not set"
                return False
            limits = self.client.get(f"{self.params.base_url}/rate-limit", headers=self._headers()).json()
            limits = limits.get("rate_limit", {})
            if limits.get("prepaid_remaining_usd"):
                self.ready, self.note = False, "the key has a prepaid balance; samples refused"
            elif int(limits.get("credits_remaining", 0)) - self.cfg.max_calls < self.params.reserve_credits:
                self.ready, self.note = False, "too few free credits left today"
            else:
                self.ready = True
        return bool(self.ready)

    def sample(self, series_id: str, dims: dict, scope: str | None, period: str, kind: str) -> dict:
        from .collectors.openalex import LEVELS, SCOPES

        level, oid = dims.get("level"), str(dims.get("id") or "")
        if level not in LEVELS:
            return {"status": "n/a", "note": f"level {level!r} has no works filter"}
        if self.calls + 2 > self.cfg.max_calls or not self._check():
            return {"status": "skipped", "note": self.note or "the run's call cap is reached"}
        if kind == "year":
            when = f"publication_year:{period[:4]}"
        else:
            first, last = [*period.split("/"), period][:2]
            y, m = int(last[:4]), int(last[5:7])
            end = (date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)).isoformat()
            when = f"from_publication_date:{first[:7]}-01,to_publication_date:{end}"
        filt = ",".join(x for x in (f"{LEVELS[level]}:{oid}", when, SCOPES.get(scope or "world"),
                                    self.params.extra_filter) if x)  # fmt: skip
        base = f"{self.params.base_url}/works"
        venues = self.client.get(base, params={"filter": filt, "group_by": "primary_location.source.id",
                                               "per_page": "200"}, headers=self._headers()).json()  # fmt: skip
        works = self.client.get(base, params={"filter": filt, "sample": str(self.cfg.sample), "seed": "20261016",
                                              "per_page": str(self.cfg.sample),
                                              "select": "id,display_name,publication_date,type,primary_location"},
                                headers=self._headers()).json()  # fmt: skip
        self.calls += 2
        groups = [(g.get("key_display_name") or "unknown venue", int(g.get("count") or 0))
                  for g in venues.get("group_by") or []]  # fmt: skip
        total = int((venues.get("meta") or {}).get("count") or sum(n for _, n in groups))
        top = max(groups, key=lambda g: g[1]) if groups else ("none", 0)
        share = top[1] / total if total else None
        listed = []
        for w in works.get("results") or []:
            loc = (w.get("primary_location") or {}).get("source") or {}
            listed.append({"id": str(w.get("id", "")).rsplit("/", 1)[-1], "title": w.get("display_name"),
                           "date": w.get("publication_date"), "type": w.get("type"),
                           "venue": loc.get("display_name")})  # fmt: skip
        return {"status": "ok", "filter_period": period, "works": total, "venues": len(groups),
                "top_venue": top[0], "top_venue_share": _r(share), "concentrated": bool(share is not None and
                share >= self.cfg.concentrated), "sample": listed}  # fmt: skip


# ---------------------------------------------------------------------------------------------- IP RAPID samples


IPR_SCHEMES = {"ipc": ("ipc_mark", "left(c.classification, 4)"), "nice": ("nice", "c.classification")}


class IprSampler:
    """The applications behind an IP RAPID class pair or applicant country by class: up to `n`, newest first, with
    their titles (a patent's or design's description, a trade mark's words) and founding applicants. Organisations
    are named; an individual is shown only as 'an individual' (their names are hashed at ingest, D-011). Read from
    the latest IP RAPID release in the lake, by the month the application's classes became observable, as the
    detector counts them."""

    def __init__(self, store: Store, n: int = 10):
        self.store, self.n = store, n
        self.con = None
        self.release = None

    def _open(self) -> None:
        from .iprmetrics import current_tables, latest_release
        from .tables import cached_get

        base, delta = latest_release(self.store)
        need = ("application", "application_classification", "application_description", "party_activity")
        bp = {t: cached_get(self.store, v["key"], v.get("sha256"), cache_root()) for t, v in base["tables"].items()
              if t in need}  # fmt: skip
        dp = {t: cached_get(self.store, v["key"], v.get("sha256"), cache_root())
              for t, v in ((delta or {}).get("tables") or {}).items() if t in need}  # fmt: skip
        self.release = (delta or base)["release_date"]
        self.con = duckdb.connect()
        self.con.execute("SET memory_limit = '3GB'")
        current_tables(self.con, bp, dp)

    def sample(self, subject: str, as_of: date, window_months: int, baseline_months: int, fading: bool) -> dict:
        from .iprmetrics import MAX_PAIR_CLASSES

        parts = subject.split(":", 2)
        if len(parts) != 3 or "+" not in parts[2]:
            return {"status": "n/a", "note": "not a class pair"}
        scheme, (a, b) = parts[1], parts[2].split("+", 1)
        country = scheme.endswith("_country")
        system, code = IPR_SCHEMES[scheme.removesuffix("_country")]
        if self.con is None:
            self._open()
        last = date(as_of.year, as_of.month, 1) - timedelta(days=1)

        def back(k):  # the first day of the month k months before `last`'s month
            y, m = last.year, last.month - k
            while m < 1:
                y, m = y - 1, m + 12
            return date(y, m, 1)

        lo, hi = back(window_months - 1), date(last.year, last.month, 1) + timedelta(days=31)
        if fading:  # a fading pair: the baseline held it
            lo, hi = back(window_months + baseline_months - 1), back(window_months - 1)
        hi = date(hi.year, hi.month, 1)
        want = (f"EXISTS (SELECT 1 FROM ctry f WHERE f.n = x.n AND f.r = x.r AND f.c = '{_sql(a.lower())}') AND "
                f"list_contains(x.ks, '{_sql(b)}')" if country else
                f"list_contains(x.ks, '{_sql(a)}') AND list_contains(x.ks, '{_sql(b)}')")  # fmt: skip
        sql = f"""
            WITH cls AS (SELECT c.ip_right_type AS r, c.application_number AS n, {code} AS k,
                           coalesce(c.classification_date, a.application_date) AS d
                         FROM application_classification c JOIN application a
                           ON a.application_number = c.application_number AND a.ip_right_type = c.ip_right_type
                         WHERE c.is_current AND c.classification_system = '{system}'),
                 ctry AS (SELECT DISTINCT application_number AS n, ip_right_type AS r, lower(country_code) AS c
                          FROM party_activity WHERE is_founding AND party_role_category = 'applicant'),
                 x AS (SELECT r, n, list(DISTINCT k) AS ks, max(d) AS d FROM cls GROUP BY ALL
                       HAVING count(DISTINCT k) <= {MAX_PAIR_CLASSES})
            SELECT x.r, x.n, x.d, a.application_date FROM x JOIN application a
              ON a.application_number = x.n AND a.ip_right_type = x.r
            WHERE x.d >= DATE '{lo.isoformat()}' AND x.d < DATE '{hi.isoformat()}' AND {want}
            ORDER BY x.d DESC, x.n"""
        apps = self.con.execute(sql).fetchall()
        shown = apps[: self.n]
        nums = [n for _, n, _, _ in shown]
        titles, parties = {}, defaultdict(list)
        if nums:
            for n, r, t, v in self.con.execute(
                "SELECT application_number, ip_right_type, description_type, description_value FROM "
                "application_description WHERE application_number IN (SELECT unnest(?)) ORDER BY 1, 3",
                [nums],
            ).fetchall():
                rank = ("description", "trade_mark_word", "trade_mark_word_mark_phrase", "variety")
                pos = rank.index(t) if t in rank else len(rank)
                if (n, r) not in titles or pos < titles[(n, r)][0]:
                    titles[(n, r)] = (pos, v)
        everyone = set()
        for n, r, kind, name in self.con.execute(
            "SELECT application_number, ip_right_type, party_type, party_name FROM party_activity WHERE is_founding "
            "AND party_role_category = 'applicant' AND application_number IN (SELECT unnest(?)) ORDER BY 1, 4",
            [[n for _, n, _, _ in apps]],
        ).fetchall():
            everyone.add(name)
            if n in nums:
                parties[(n, r)].append(name if kind == "organisation" else "an individual")
        listed = [{"application_number": n, "right": r, "filed": _iso(f), "classes_observable": _iso(d),
                   "title": (titles.get((n, r)) or (0, None))[1], "applicants": sorted(set(parties.get((n, r), [])))}
                  for r, n, d, f in shown]  # fmt: skip
        before = sum(1 for _, _, _, f in apps if f is not None and f < lo)
        return {"status": "ok", "release": self.release, "period": f"{lo.isoformat()}/{hi.isoformat()}",
                "applications": len(apps), "applicants": len(everyone), "filed_before_period": before,
                "sample": listed}  # fmt: skip


def _sql(text: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9 ]{1,8}", text):
        raise ValueError(f"not a class or country code: {text!r}")
    return text


# ------------------------------------------------------------------------------------------------------ one dossier


def summary_line(c: dict, nums: dict) -> str:
    label = c["label"] or c["subject"]
    t = c["type"]
    up = "rising" if (c["direction"] or 1) > 0 else "falling"
    if "divergence" in nums:
        d = nums["divergence"]
        return f"{label}: Australia against the {d.get('reference')}, {d.get('growth_per_year') or 0:+.1%} a year"
    if t == "acceleration" and "acceleration" in nums:
        a = nums["acceleration"]
        g = (nums.get("trend") or {}).get("growth_per_year")
        extra = f"; trend {g:+.1%} a year" if g is not None else ""
        cp = f", a change point at {a['change_point']}" if a.get("change_point") else ""
        return f"{label}: {up}, and faster recently (slope {a.get('early')} to {a.get('recent')}{cp}{extra})"
    if t == "trend" and "trend" in nums:
        g = nums["trend"].get("growth_per_year")
        return f"{label}: a {up} trend, about {g or 0:+.1%} a year"
    if "low_base_surge" in nums and c["subject_kind"] == "series":
        s = nums["low_base_surge"]
        return (f"{label}: {s.get('count'):.0f} in {s.get('window')} against {s.get('expected') or 0:.1f} expected "
                f"(ratio {s.get('ratio') or 0:.1f}) from a low base")  # fmt: skip
    if t == "anomaly" and "anomaly" in nums:
        a = nums["anomaly"]
        v, e = a.get("value"), a.get("expected")
        rel = f"{(v - e) / abs(e):+.0%}" if v is not None and e else f"{a.get('change') or 0:+.0%}"
        return f"{label}: {a.get('period')} was {rel} off its expected value"
    for name in ("new_combination", "jurisdiction_shift", "fading_combination"):
        if name in nums:
            n = nums[name]
            what = "new" if n.get("new") else "rising" if n.get("rising") else "fading"
            return f"{label}: {what}; {n.get('window')} in the window against {n.get('baseline')} in the baseline" + (
                f" ({n.get('expected_window'):.0f} expected)" if n.get("expected_window") else ""
            )
    dets = ", ".join(c["detectors"])
    return (f"'{label}': {c['n_items']} items (de-duplicated) from {c['n_sources']} sources in the window to "
            f"{c['window_end']} ({dets})")  # fmt: skip


def checklist(c: dict, art: dict | None, nums: dict, extra: list[dict]) -> list[dict]:
    from .artefacts import CHECKS

    details = json.loads((art or {}).get("details") or "{}")
    out = []
    for check in CHECKS:
        outcome = (art or {}).get(check) or "n/a"
        d = details.get(check)
        out.append({"check": check, "outcome": outcome, "detail": canonical_json(d) if d is not None else ""})
    ce = nums.get("context_explains")
    if ce:
        detail = (
            f"its peers and counterpart predict {ce.get('share') or 0:.0%} of the move (expected "
            f"{ce.get('expected')} against {ce.get('observed')}; R2 {ce.get('r2')})"
        )
        out.append({"check": "explained_by_context", "outcome": "flag", "detail": detail})
    return out + extra


def build_dossier(layer: Layer, row: dict, cfg: ReviewConfig, baseline: BaselineFile,
                  sampler: OpenAlexSampler | None) -> dict:  # fmt: skip
    dc = cfg.dossier
    cid = row["candidate_id"]
    c = layer.cands[cid]
    nums = json.loads(c["numbers"] or "{}")
    ev = layer.evidence.get(cid, [])
    end = as_of_end(layer.as_of)
    trends = {t.id: t for t in baseline.trends}
    out: dict = {
        "dossier_version": dc.version, "candidate_id": cid, "as_of": layer.as_of.isoformat(), "label": c["label"],
        "subject": c["subject"], "subject_kind": c["subject_kind"], "type": c["type"], "direction": c["direction"],
        "views": list(c["views"]), "ring": row["ring"], "ring_basis": row["ring_basis"], "scope": c["scope"],
        "sources": list(c["sources"]), "families": list(c["families"]), "corroboration": c["corroboration"],
        "window": {"start": c["window_start"], "end": c["window_end"]}, "detectors": nums,
        "runs": {**layer.runs, "index_run": layer.index_run}, "summary": summary_line(c, nums),
    }  # fmt: skip
    extra_checks: list[dict] = []
    limits: list[str] = []
    notes: list[str] = []
    examples: list[dict] = []
    # ------------------------------------------------------------ evidence
    items = [e for e in ev if e["kind"] == "item"]
    series_ev = [e for e in ev if e["kind"] == "series"]
    if items:
        docs = layer.documents()
        first: dict[str, dict] = {}
        for e in sorted(items, key=lambda e: (e["observable_at"] or end, e["ref"])):
            g = e["dedup_group"] or e["ref"]
            first.setdefault(g, e)
        rows = []
        for e in first.values():
            d = docs.get(e["ref"]) or {}
            rows.append({"item_id": e["ref"], "title": d.get("title"), "url": d.get("url"), "source": e["source"],
                         "family": e["family"], "outlet": d.get("outlet"), "doc_type": d.get("doc_type"),
                         "event_at": _iso(d.get("event_at")), "observable_at": _iso(e["observable_at"]),
                         "role": e["role"], "copies": int(d.get("group_size") or 1)})  # fmt: skip
        primary = set(layer.cfg.artefacts.primary_families)
        rows.sort(key=lambda r: (r["role"] != "window", r["family"] not in primary, r["observable_at"] or "",
                                 r["item_id"]), reverse=False)  # fmt: skip
        out["evidence"] = {"items": rows[: dc.evidence_items], "groups": len(first), "items_total": len(items)}
        examples = rows[: dc.examples]
        out["chart"] = concept_chart(layer, c, set(first), dc)
        out["analogues"] = document_analogues(layer, [e["ref"] for e in items], c, dc.analogues)
    elif c["subject_kind"] in ("series", "pair"):
        wanted = {e["ref"] for e in series_ev}
        subj = next((e["ref"] for e in series_ev if e["role"] == "subject"), c["subject"])
        m = layer.measures.get(subj) or {}
        if m.get("denominator"):
            wanted.add(m["denominator"])
        got = layer.series(wanted | {subj})
        s = got.get(subj)
        chart = series_chart(s, got.get(m.get("denominator")), m.get("transform"), dc.chart_points)
        out["chart"] = chart
        out["evidence"] = {"series": [{"series_id": e["ref"], "role": e["role"], "source": e["source"],
                                       "last_period": index_label(got[e["ref"]].kind, max(got[e["ref"]].points))
                                       if got.get(e["ref"]) else None,
                                       "last_value": _r(got[e["ref"]].points[max(got[e["ref"]].points)], 6)
                                       if got.get(e["ref"]) else None} for e in series_ev]}  # fmt: skip
        if chart:
            tail = zip(chart["periods"][-dc.examples :], chart["values"][-dc.examples :], strict=True)
            examples = [{"period": p, "value": v} for p, v in tail]
        if s is not None and s.points and max(s.points.values()) < 0:
            notes.append("every value is negative (debits, as published): a fall in value is a rise in size")
        period = (nums.get("anomaly") or {}).get("period")
        if c["type"] == "anomaly" or "anomaly" in nums:
            extra_checks.append(seasonal_check(s, period, c["direction"] or 1))
        if s is not None:
            if c["type"] in ("trend", "acceleration") and s.kind in ("M", "Q", "A"):
                w = int(m.get("trend_w3_periods") or {"M": 36, "Q": 24, "A": 16}[s.kind])
                out["analogues"] = {"trend": trend_analogues(s, w, dc.analogue_follow),
                                    "note": f"the series has {len(s.points)} periods; earlier windows of {w} periods "
                                            f"need at least {2 * w}"}  # fmt: skip
            else:
                out["analogues"] = {"moves": jump_analogues(s, c["direction"] or 1, dc.analogue_follow,
                                                            dc.analogues)}  # fmt: skip
        if c["sources"] == ["openalex_counts"] and sampler is not None and {"low_base_surge", "anomaly"} & set(
                c["detectors"]):  # fmt: skip
            meta = series_dims(layer, subj)
            sp = (nums.get("low_base_surge") or {}).get("window") or period
            kind = "year" if subj.endswith("|year") else "month"
            if sp:
                try:
                    out["samples"] = {"openalex": sampler.sample(subj, meta, c["scope"], sp, kind)}
                except Exception as e:  # a supplement: a failed fetch is recorded, never fatal
                    out["samples"] = {"openalex": {"status": "failed", "note": f"{type(e).__name__}"}}
            samp = (out.get("samples") or {}).get("openalex") or {}
            if samp.get("status") == "ok":
                extra_checks.append({"check": "concentrated_works",
                                     "outcome": "flag" if samp["concentrated"] else "pass",
                                     "detail": f"{samp['works']} works in {samp['venues']} venues; the largest holds "
                                               f"{samp['top_venue_share'] or 0:.0%}"})  # fmt: skip
    else:  # IP RAPID class pairs: the applications are in the IP RAPID lake, not the documents
        fading = "fading_combination" in nums or bool((nums.get("jurisdiction_shift") or {}).get("fading"))
        dcfg = layer.cfg.documents
        try:
            got = layer.ipr.sample(c["subject"], layer.as_of, dcfg.ipr_window_months, dcfg.ipr_baseline_months,
                                   fading)  # fmt: skip
        except Exception as e:  # a supplement: recorded, never fatal
            got = {"status": "failed", "note": type(e).__name__}
        out["evidence"] = {"applications": got}
        if got.get("status") == "ok":
            examples = got["sample"][: dc.examples]
            if got["applications"]:
                share = got["filed_before_period"] / got["applications"]
                extra_checks.append({"check": "reclassified", "outcome": "flag" if share >= 0.5 else "pass",
                                     "detail": f"{got['filed_before_period']} of {got['applications']} applications "
                                               "were filed before the period: their classes were assigned or changed "
                                               "in it (a reclassification, not new filings)"})  # fmt: skip
            if got["applicants"] < 3:
                extra_checks.append({"check": "few_applicants", "outcome": "flag",
                                     "detail": f"{got['applications']} applications from {got['applicants']} "
                                               "founding applicants"})  # fmt: skip
    out["examples"] = examples
    # ------------------------------------------------------------ administrative causes and primary sources
    admin = []
    ws = _window_date(c["window_start"]) or (layer.as_of - timedelta(days=365))
    for ev_ in dc.administrative_events:
        if set(ev_.sources) & set(c["sources"]) and re.search(ev_.pattern, c["subject"]):
            when = date.fromisoformat(ev_.date)
            if ws - timedelta(days=366) <= when <= layer.as_of:
                admin.append(ev_.note)
    terms = query_terms(c["label"] if c["subject_kind"] != "concept" else (c["label"] or "").split(";")[0])
    since = datetime.combine(ws, datetime.min.time(), tzinfo=UTC) - timedelta(days=365)
    related = bm25_hits(layer.index_db, terms, since, end, ["legal", "policy"], dc.related_items)
    extra_checks.append({"check": "administrative", "outcome": "flag" if admin else "pass" if terms else "n/a",
                         "detail": "; ".join(admin) or ("no recorded administrative cause" if terms else
                                                        "no search words in the label")})  # fmt: skip
    out["related"] = [_hit(h) for h in related]
    # ------------------------------------------------------------ counter-evidence
    words = dc.falling_words if (c["direction"] or 1) > 0 else dc.rising_words
    cue = re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b", re.I)
    hits = bm25_hits(layer.index_db, terms, since, end, None, 200)
    out["counter_evidence"] = [_hit(h) for h in hits if cue.search(f"{h['title'] or ''} {h['summary'] or ''}")][
        : dc.counter_items
    ]
    out["searched"] = {"terms": terms, "since": since.date().isoformat(), "index": layer.index_db is not None}
    if layer.index_db is None:
        limits.append("no BM25 index: related and counter-evidence searches were not run")
    # ------------------------------------------------------------ known trend, territories, redundancy, history
    kt = row.get("known_trend")
    out["known_trend"] = {"id": kt, "name": trends[kt].name if kt in trends else None,
                          "similarity": _r(row.get("known_trend_sim")), "match": bool(row.get("known_trend_match")),
                          "status": trends[kt].status if kt in trends else None} if kt else None  # fmt: skip
    if kt:
        detail = (
            f"nearest {kt} ({trends[kt].name if kt in trends else '?'}), similarity "
            f"{row.get('known_trend_sim') or 0:.2f} (machine; reinforcement counts, D-014)"
        )
        extra_checks.append({"check": "known_trend", "outcome": "flag" if row.get("known_trend_match") else "pass",
                             "detail": detail})  # fmt: skip
    out["territories"] = {"top": row.get("territory_top"), "similarity": _r(row.get("territory_sim")),
                          "terms": list(row.get("term_territories") or [])}  # fmt: skip
    group = c.get("redundancy_group")
    if group:
        others = [o for o in layer.cands.values() if o.get("redundancy_group") == group and o["candidate_id"] != cid]
        out["redundancy"] = {"group": group, "size": c.get("redundancy_size") or 1 + len(others),
                             "others": [{"candidate_id": o["candidate_id"], "label": o["label"], "type": o["type"]}
                                        for o in sorted(others, key=lambda o: o["candidate_id"])[:10]]}  # fmt: skip
        if others:
            extra_checks.append(
                {
                    "check": "redundancy",
                    "outcome": "flag",
                    "detail": f"moves with {len(others)} other candidates: one line of evidence",
                }
            )
    out["checklist"] = checklist(c, layer.artefacts.get(cid), nums, extra_checks)
    out["history"] = layer.history_of(cid, dc.history_scans)
    out["rank"] = {k: _r(row.get(k)) if isinstance(row.get(k), float) else row.get(k) for k in
                   ("shortlist_rank", "shortlist_view", "shortlist_pass", "strength_pct", "breadth", "lead",
                    "novelty", "scope_factor", "type_factor", "flag_factor", "context_factor",
                    "score_early_warning", "score_strategic")}  # fmt: skip
    out["flags"] = list(row.get("flags") or [])
    limits += [
        "backfilled history has no true first sighting",
        "non-English sources are absent",
        "customers (D4) are low coverage on public data",
    ]
    out["limits"] = limits
    out["notes"] = notes
    return out


def series_dims(layer: Layer, sid: str) -> dict:
    from .rank import series_meta

    if not hasattr(layer, "_meta"):
        layer._meta = series_meta(layer.store, layer.sm)
    return (layer._meta.get(sid) or {}).get("dims") or {}


def _window_date(label: str | None) -> date | None:
    if not label:
        return None
    try:
        if len(label) == 4:
            return date(int(label), 1, 1)
        if "-Q" in label:
            y, q = label.split("-Q")
            return date(int(y), 3 * int(q) - 2, 1)
        if len(label) == 7:
            return date(int(label[:4]), int(label[5:7]), 1)
        return date.fromisoformat(label[:10])
    except ValueError:
        return None


def _hit(h: dict) -> dict:
    return {k: h[k] for k in ("item_id", "source", "family", "observable_at", "title", "url", "score")}


def concept_items(layer: Layer, c: dict) -> set[str]:
    """Every visible item (window and baseline) that holds the candidate's concept, where the concept is a
    keyphrase, a pair of them, a term group or a cluster; else none (micro-clusters are window-only)."""
    key = c["subject"]
    kp = layer.keyphrases
    if key.startswith("kp:"):
        return set(kp().get(key[3:], set()))
    if key.startswith("nc:kp:"):
        a, b = key[6:].split("+", 1)
        return set(kp().get(a, set())) & set(kp().get(b, set()))
    if key.startswith("tg:"):
        return {i for i, it in layer.visible_items().items() if key[3:] in (it.get("term_groups") or [])}
    if key.startswith("cl:") and "assignments.parquet" in layer.doc_files:
        return {r["item_id"] for r in read_rows(layer.doc_files["assignments.parquet"]) if r["cluster"] == key}
    return set()


def concept_chart(layer: Layer, c: dict, window_groups: set[str], dc) -> dict | None:
    """Groups holding the concept per month over the baseline and window: the low base, shown."""
    ids = concept_items(layer, c)
    vis = layer.visible_items()
    months: dict[str, set] = defaultdict(set)
    for i in ids:
        it = vis.get(i)
        if it:
            months[it["observable_at"].strftime("%Y-%m")].add(it["grp"])
    if not months:
        return None
    end = layer.as_of
    labels = []
    y, m = end.year, end.month
    for _ in range(27):
        labels.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    labels.reverse()
    vals = [float(len(months.get(p, ()))) for p in labels]
    return {"frequency": "M", "shown": "de-duplicated items holding the concept", "periods": labels,
            "values": vals, "sparkline": sparkline(vals), "baseline_groups": int(sum(vals[:-3]))}  # fmt: skip


def document_analogues(layer: Layer, item_ids: list[str], c: dict, k: int) -> list[dict]:
    """The earlier items nearest the candidate's own: cosine to the mean of its items' vectors, among items
    observable before its window, one per de-duplication group."""
    ids, vecs = layer.vectors()
    pos = {i: n for n, i in enumerate(ids)}
    mine = [pos[i] for i in item_ids if i in pos]
    if not mine:
        return []
    centre = vecs[mine].mean(axis=0)
    centre /= max(float(np.linalg.norm(centre)), 1e-12)
    start = _window_date(c["window_start"]) or layer.as_of
    cutoff = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    docs = layer.documents()
    sims = vecs @ centre
    order = np.argsort(-sims, kind="stable")
    out, groups, own = [], set(), set(item_ids)
    for n in order[:5000]:
        iid = ids[n]
        d = docs.get(iid)
        if not d or iid in own or d["observable_at"] is None or d["observable_at"] >= cutoff:
            continue
        g = d.get("dedup_group") or iid
        if g in groups:
            continue
        groups.add(g)
        out.append({"item_id": iid, "title": d.get("title"), "url": d.get("url"), "source": d["source"],
                    "family": d["family"], "observable_at": _iso(d["observable_at"]),
                    "similarity": _r(float(sims[n])), "became": "no register history yet"})  # fmt: skip
        if len(out) >= k:
            break
    return out


# ------------------------------------------------------------------------------------------------------- Markdown


def render(d: dict) -> str:
    """The dossier as Markdown, deterministic from its JSON; untrusted text is escaped."""
    lines = [f"# {md_text(d['label'] or d['subject'], 160)}", "", md_text(d["summary"], 400), ""]
    lines += [f"Note: {md_text(n, 300)}" for n in d.get("notes") or []] + ([""] if d.get("notes") else [])
    flags = ", ".join(d["flags"]) or "none"
    lines += ["| | |", "|---|---|", f"| Candidate | `{d['candidate_id']}` (scan of {d['as_of']}) |",
              f"| Type | {d['type']} ({', '.join(d['views'])}) |", f"| Ring | {d['ring']} ({d['ring_basis']}) |",
              f"| Sources | {', '.join(d['sources'])} ({', '.join(d['families']) or 'statistics'}) |",
              f"| Independent lines of evidence | {d['corroboration']} |", f"| Artefact flags | {flags} |",
              f"| Window | {d['window']['start']} to {d['window']['end']} |", ""]  # fmt: skip
    ch = d.get("chart")
    if ch:
        lines += ["## Small chart", "", f"`{ch['sparkline']}`  {ch['periods'][0]} to {ch['periods'][-1]} "
                  f"({ch['shown']}; {ch['frequency']})", ""]  # fmt: skip
    lines += ["## The detectors' numbers", ""]
    for name, n in sorted(d["detectors"].items()):
        lines.append(f"- **{name}**: `{md_text(canonical_json(n), 600)}`")
    runs = ", ".join(f"{k} {v}" for k, v in sorted(d["runs"].items()) if v)
    lines += ["", f"Runs: {runs}.", ""]
    ev = d.get("evidence") or {}
    lines += ["## Original evidence", ""]
    if ev.get("items"):
        lines += [
            f"{ev['groups']} de-duplicated items ({ev['items_total']} in all); the first "
            f"{len(ev['items'])}, primary sources first:",
            "",
            "| Observable | Event | Source | Family | Copies | Title | Link |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in ev["items"]:
            lines.append(
                f"| {(r['observable_at'] or '')[:10]} | {(r['event_at'] or '')[:10]} | {r['source']} | "
                f"{r['family']} | {r['copies']} | {md_text(r['title'], 140)} | {md_link(r['url'])} |"
            )
    elif ev.get("series"):
        lines += ["| Series | Role | Last period | Last value |", "|---|---|---|---|"]
        for s in ev["series"]:
            lines.append(f"| `{md_text(s['series_id'], 120)}` | {s['role']} | {s['last_period']} | {s['last_value']} |")
    elif ev.get("applications"):
        ap = ev["applications"]
        if ap.get("status") == "ok":
            lines += [f"{ap['applications']} applications from {ap['applicants']} founding applicants, by the month "
                      f"their classes became observable ({ap['period']}; IP RAPID release {ap['release']}); the "
                      f"newest {len(ap['sample'])}:", "", "| Application | Right | Filed | Title | Applicants |",
                      "|---|---|---|---|---|"]  # fmt: skip
            for a in ap["sample"]:
                lines.append(
                    f"| {a['application_number']} | {a['right']} | {(a['filed'] or '')[:10]} | "
                    f"{md_text(a['title'], 120)} | {md_text('; '.join(a['applicants']), 120)} |"
                )
        else:
            lines.append(f"{ap.get('status')}: {md_text(ap.get('note'))}")
    lines += ["", "## Alternative explanations", "", "| Check | Outcome | Detail |", "|---|---|---|"]
    for ck in d["checklist"]:
        lines.append(f"| {ck['check']} | {ck['outcome']} | {md_text(ck['detail'], 300)} |")
    kt = d.get("known_trend")
    lines += ["", "## Known trend and territories (machine tags)", ""]
    if kt:
        status = " (proposed)" if kt.get("status") == "proposed" else ""
        lines.append(
            f"- Nearest known trend: {kt['id']} {md_text(kt['name'])}{status}, similarity "
            f"{kt['similarity']}{' (a match)' if kt['match'] else ''}"
        )
    t = d.get("territories") or {}
    lines.append(
        f"- Nearest territory: {t.get('top')} ({t.get('similarity')}); terms matched: "
        f"{', '.join(t.get('terms') or []) or 'none'}"
    )
    for title, key in (("Counter-evidence (to read: hits that use words of the opposite direction)",
                        "counter_evidence"), ("Primary sources that mention the subject", "related")):  # fmt: skip
        lines += ["", f"## {title}", ""]
        hits = d.get(key) or []
        if not hits:
            lines.append(f"None found (search words: {', '.join(d['searched']['terms']) or 'none'}).")
        for h in hits:
            lines.append(
                f"- {(h['observable_at'] or '')[:10]} {h['source']}: {md_text(h['title'], 140)} {md_link(h['url'])}"
            )
    an = d.get("analogues")
    lines += ["", "## Analogues", ""]
    if isinstance(an, list):
        for a in an or []:
            lines.append(
                f"- {(a['observable_at'] or '')[:10]} {a['source']}: {md_text(a['title'], 140)} "
                f"(similarity {a['similarity']}; {a['became']}) {md_link(a['url'])}"
            )
        if not an:
            lines.append("No earlier items near these.")
    elif isinstance(an, dict) and an.get("moves") is not None:
        for a in an["moves"]:
            lines.append(
                f"- {a['period']}: a move of {a['move']:+.0%}; {a['follow_periods']} periods later "
                f"{a['after']:+.0%} ({'it lasted' if a['lasted'] else 'it did not last'})"
            )
        if not an["moves"]:
            lines.append("No earlier move of this size in the series.")
    elif isinstance(an, dict) and "trend" in an and not an["trend"]:
        lines.append(f"None: {md_text(an.get('note'))}.")
    elif isinstance(an, dict) and an.get("trend"):
        tr = an["trend"]
        lines.append(
            f"- Growth over the last {tr['window_periods']} periods: {tr['growth']:+.2f} (log); faster than "
            f"{tr['percentile']:.0%} of earlier windows; {tr['earlier_as_fast']} earlier windows grew as "
            f"fast, and {tr['kept_going']} of them kept growing"
        )
    else:
        lines.append("None computed.")
    samp = (d.get("samples") or {}).get("openalex")
    if samp:
        lines += ["", "## Sample works (OpenAlex)", ""]
        if samp.get("status") == "ok":
            lines.append(
                f"{samp['works']} works in {samp['venues']} venues; the largest, "
                f"{md_text(samp['top_venue'])}, holds {samp['top_venue_share'] or 0:.0%}"
                f"{' (concentrated)' if samp['concentrated'] else ''}. A random sample:"
            )
            for w in samp["sample"]:
                lines.append(f"- {w['date']} {w['type']}: {md_text(w['title'], 140)} ({md_text(w['venue'], 80)})")
        else:
            lines.append(f"{samp.get('status')}: {md_text(samp.get('note'))}")
    red = d.get("redundancy")
    if red and red["others"]:
        lines += ["", "## Moves with (one line of evidence)", ""]
        for o in red["others"]:
            lines.append(f"- `{o['candidate_id']}` {o['type']}: {md_text(o['label'], 120)}")
    lines += ["", "## Earlier scans", ""]
    hist = d.get("history") or []
    if not hist:
        lines.append("No earlier scan.")
    for h in hist:
        lines.append(f"- {h['as_of']}: " + (f"{h['type']}, strength {h['strength']} ({', '.join(h['detectors'])})"
                                             if h["present"] else "not a candidate"))  # fmt: skip
    r = d["rank"]
    lines += ["", "## Ranking (machine)", "",
              f"Shortlist place {r['shortlist_rank']} ({r['shortlist_view']}, pass {r['shortlist_pass']}). "
              f"Components: strength {r['strength_pct']}, breadth {r['breadth']}, lead time {r['lead']}, novelty "
              f"{r['novelty']}; factors: scope {r['scope_factor']}, type {r['type_factor']}, flags "
              f"{r['flag_factor']}, context {r['context_factor']}.", "",
              "## Limits", ""] + [f"- {x}" for x in d["limits"]]  # fmt: skip
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------------------------------- the stage


def dossier(store: Store, cfg: ReviewConfig, detect_cfg: DetectConfig, cards: dict[str, SourceCard],
            baseline: BaselineFile, client, as_of: date, dim: int = 384, config_hash: str | None = None,
            only: list[str] | None = None) -> tuple[str, str, dict]:  # fmt: skip
    manifest = Manifest(command=COMMAND, config_hash=config_hash)
    try:
        layer = Layer(store, detect_cfg, cards, as_of, dim)
        manifest.params = {"as_of": as_of.isoformat(), **layer.runs, "index_run": layer.index_run}
        shortlist = sorted((r for r in layer.ranked if r["shortlisted"]), key=lambda r: r["shortlist_rank"])
        if only:
            shortlist = [r for r in shortlist if r["candidate_id"] in set(only)]
        sampler = None
        if client is not None and cfg.dossier.openalex_samples.enabled and "openalex_counts" in cards:
            sampler = OpenAlexSampler(client, cards["openalex_counts"], cfg)
        counts: dict[str, int] = defaultdict(int)
        for n, row in enumerate(shortlist, 1):
            d = build_dossier(layer, row, cfg, baseline, sampler)
            js = canonical_json(d).encode("utf-8")
            md = render(d).encode("utf-8")
            for ext, data, ctype in (("json", js, "application/json"), ("md", md, "text/markdown")):
                key = key_of(row["candidate_id"], as_of, ext)
                store.put(key, data, ctype)
                manifest.add_output(key, data)
            counts["dossiers"] += 1
            counts[f"type_{d['type']}"] += 1
            counts["with_counter_evidence"] += bool(d.get("counter_evidence"))
            counts["with_related"] += bool(d.get("related"))
            counts["with_chart"] += bool(d.get("chart"))
            samp = (d.get("samples") or {}).get("openalex") or {}
            if samp:
                counts[f"openalex_samples_{samp.get('status')}"] += 1
                counts["openalex_concentrated"] += bool(samp.get("concentrated"))
            for ck in d["checklist"]:
                if ck["outcome"] == "flag":
                    counts[f"check_{ck['check']}"] += 1
            if n % 20 == 0:
                log.info("dossier: %d of %d", n, len(shortlist))
        if sampler is not None:
            counts["openalex_calls"] = sampler.calls
            if sampler.note:
                manifest.warnings.append(f"OpenAlex samples: {sampler.note}")
        if layer.index_db is None:
            manifest.warnings.append("no passed BM25 index: counter-evidence was not searched")
        manifest.counts = dict(sorted(counts.items()))
        return "passed", manifest.finish(store, "passed"), manifest.counts
    except Exception as e:
        return failed(COMMAND, store, manifest, e)


def load_dossiers(store: Store, manifest: dict) -> dict[str, dict]:
    """The JSON dossiers of a dossier run, checked against its manifest: {candidate_id: dossier}."""
    out = {}
    for k, p in fetch_outputs(store, manifest, "interpretation/dossiers/", cache_root()).items():
        if k.endswith(".json"):
            d = json.loads(Path(p).read_text(encoding="utf-8"))
            out[d["candidate_id"]] = d
    return out


def counts_by(items, key) -> Counter:
    return Counter(key(i) for i in items)
