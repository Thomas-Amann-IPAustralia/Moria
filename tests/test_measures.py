"""`moria measure series` on hand-built series: rates per source volume, a trend, a surge from a low base, an
anomaly, a change in level, a world/AU divergence, and nothing on noise."""

from __future__ import annotations

import pyarrow.parquet as pq

from moria.config import load_detect
from moria.measures import measure

from .detect_fixtures import AS_OF, abs_series, openalex_series, put_normalise

CFG = load_detect()


def cfg(sources=("openalex_counts", "abs_headline")):
    return CFG.model_copy(update={"series": CFG.series.model_copy(update={"sources": list(sources)})})


def run(store, c=None):
    s1, o1 = openalex_series()
    s2, o2 = abs_series()
    put_normalise(store, series=s1 + s2, obs=o1 + o2)
    status, _, counts = measure(store, c or cfg(), AS_OF)
    assert status == "passed", counts
    prefix = store.root / f"measures/series/as_of={AS_OF}"
    rows = {r["series_id"]: r for r in pq.read_table(prefix / "measures.parquet").to_pylist()}
    div = {r["pair_id"]: r for r in pq.read_table(prefix / "divergence.parquet").to_pylist()}
    return rows, div, counts


def test_series_detectors(store):
    rows, div, counts = run(store)
    t1 = rows["openalex_counts|topic|T1|au|month"]
    assert t1["transform"] == "log_share" and t1["denominator"] == "openalex_counts|total|au|month"
    assert t1["last_period"] == "2026-09"  # October is not over at as_of
    assert t1["trend_dir"] == 1 and t1["trend_sig"] >= 2 and 0.3 < t1["trend_growth"] < 0.7  # about 0.04 a month
    t2 = rows["openalex_counts|topic|T2|au|month"]
    assert t2["trend_dir"] == 0 and not t2["anomaly"] and not t2["surge"] and not t2["accel"]
    t3 = rows["openalex_counts|topic|T3|au|month"]
    assert t3["surge"] and t3["surge_count"] >= 5 and t3["surge_ratio"] > 10  # a low base: zeros filled in
    t4 = rows["openalex_counts|topic|T4|au|month"]
    assert t4["anomaly"] and t4["anom_period"] == "2026-09" and t4["anom_z"] > 0
    l1, l2 = rows["abs_headline|ABS:TEST|L1"], rows["abs_headline|ABS:TEST|L2"]
    assert l1["transform"] == "level" and (l1["anomaly"] or l1["cp_level_recent"])
    assert not l2["anomaly"] and not l2["cp_level_recent"] and l2["trend_dir"] == 0
    d5 = div["openalex_counts|topic|T5|month"]
    assert d5["direction"] == -1 and d5["au_trend_dir"] == 0 and d5["ref_trend_dir"] == 1
    assert div["openalex_counts|topic|T1|month"]["direction"] == 0  # both rising alike
    assert counts["series"] == len(rows) and counts["divergences"] >= 1


def test_january_is_left_out_of_openalex_months(store):
    rows, _, _ = run(store)
    t1 = rows["openalex_counts|topic|T1|au|month"]
    assert t1["trend_w1_n"] == 11  # 12 months, one of them a January


def test_point_in_time_drops_periods_after_as_of(store):
    from datetime import date

    s1, o1 = openalex_series()
    put_normalise(store, series=s1, obs=o1)
    status, _, _ = measure(store, cfg(("openalex_counts",)), date(2026, 3, 20))
    assert status == "passed"
    rows = pq.read_table(store.root / "measures/series/as_of=2026-03-20/measures.parquet").to_pylist()
    assert {r["last_period"] for r in rows} == {"2026-02"}


def test_missing_upstream_fails_loudly(store):
    status, _, counts = measure(store, cfg(), AS_OF)
    assert status == "failed" and "run `moria normalise` first" in counts["error"]
