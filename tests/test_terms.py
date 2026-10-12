"""The terms check, against hand-built GKG files (placeholder text, never real source text)."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

from moria.terms import check, sampled_days

from .conftest import card, make_client
from .test_gkg import gkg_zip, make_handler, row

TERRITORIES = SimpleNamespace(
    territories=[
        SimpleNamespace(
            id="T9",
            terms=SimpleNamespace(core=["widget licensing", "never seen phrase"], adjacent=["gizmo"], wider_world=[]),
        )
    ]
)
THEMES = SimpleNamespace(themes={"testing": ["net zero", "gizmo"]})


def gkg_card():
    return card("gdelt_gkg", {"base_url": "https://data.test/gdeltv2", "max_missing_files": 96})


DAY_1 = [
    row("https://news.test/a", "news.test", title="Placeholder story on Widget Licensing", date_="20261002000000"),
    row("https://paper.test.au/n", "paper.test.au", names="Gizmo Holdings,12", date_="20261002000000"),
]
DAY_2 = [
    row("https://news.test/b", "news.test", title="Widget licensing again", date_="20261009000000"),
    row("https://news.test/net-zero-plan", "news.test", date_="20261009000000"),
]


def test_sampled_days_run_weekly_back_from_the_end():
    assert sampled_days(date(2026, 10, 9), 3) == [date(2026, 9, 25), date(2026, 10, 2), date(2026, 10, 9)]


def test_terms_check_counts_each_term_and_keeps_samples_private(http_cfg, store, tmp_path):
    files = {"20261002000000": gkg_zip(DAY_1), "20261009000000": gkg_zip(DAY_2)}
    report = tmp_path / "terms-check.md"
    status, mkey, counts = check(
        gkg_card(),
        TERRITORIES,
        THEMES,
        store,
        make_client(http_cfg, make_handler(files)),
        end=date(2026, 10, 9),
        weeks=2,
        samples_per_term=1,
        report_path=report,
    )
    assert status == "passed", json.loads(store.get(mkey))["error"]
    assert counts["days_read"] == 2 and counts["documents"] == 4 and counts["terms"] == 4

    result = json.loads(store.get(next(k for k in store.list("reports/terms-check/") if k.endswith(".json"))))
    terms = result["terms"]
    wl = terms["widget licensing"]
    assert (wl["world"], wl["au"], wl["days_with_hits"], wl["by_field"]) == (2, 0, 2, {"title": 2})
    assert len(wl["samples"]) == 1 and wl["samples"][0]["title"].lower().startswith(("placeholder", "widget"))
    gizmo = terms["gizmo"]
    assert gizmo["sources"] == ["T9:adjacent", "theme:testing"]
    assert (gizmo["world"], gizmo["au"], gizmo["names_only"]) == (1, 1, 1)
    assert terms["net zero"]["by_field"] == {"url": 1}
    assert terms["never seen phrase"]["flags"] == ["silent"]

    public = report.read_text()
    assert "widget licensing" in public and "`silent`" in public
    for private in ("Placeholder story", "news.test/a", "paper.test.au"):
        assert private not in public, private  # the public summary carries counts, never titles or URLs


def test_terms_check_fails_loudly_when_nothing_can_be_read(http_cfg, store):
    status, mkey, _ = check(
        gkg_card(), TERRITORIES, THEMES, store, make_client(http_cfg, make_handler({})), end=date(2026, 10, 9), weeks=1
    )
    assert status == "failed" and "no sampled day could be read" in json.loads(store.get(mkey))["error"]
