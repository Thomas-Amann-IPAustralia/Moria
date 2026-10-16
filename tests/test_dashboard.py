"""The dashboard's data (D-030): the public bundle holds aggregates only; the private bundle holds the scan in full,
with fits recomputed exactly; the practice bundle is invented, deterministic and run through the real machinery; and
the dashboard's what-if ranking (JavaScript) reproduces Moria's own shortlist and queue. On the hand-built layer of
day 4's and day 5's tests: numbers are synthetic and text is placeholder."""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from moria.config import REPO_ROOT, load_baseline, load_detect, load_review, load_sources, load_territories
from moria.dashboard import PUBLIC_PATH, check_out_path, dashboard, private_key
from moria.dashboard_practice import PRACTICE_PATH, encode, floor_check, practice_bundle

from .detect_fixtures import AS_OF, minimal_layer
from .test_review import REVIEW, _review_chain

RANKING_JS = REPO_ROOT / "dashboard" / "assets" / "js" / "ranking.js"


@pytest.fixture
def reviewed(store):
    from moria.cli import run_scan
    from moria.register import sync

    minimal_layer(store)
    run_scan(store, load_detect(), load_sources(), AS_OF)
    _review_chain(store)
    sync(store, REVIEW, AS_OF)
    return store


def _run(store, tmp_path, **kw):
    return dashboard(store, REVIEW, load_detect(), load_sources(), load_territories(), load_baseline(), AS_OF,
                     public_out=tmp_path / "public.json", **kw)  # fmt: skip


def test_the_public_bundle_holds_aggregates_only(reviewed, tmp_path):
    status, _, counts = _run(reviewed, tmp_path)
    assert status == "passed", counts
    public = json.loads((tmp_path / "public.json").read_text())
    private = json.loads(gzip.decompress(reviewed.get(private_key(AS_OF))))
    assert public["kind"] == "public" and public["schema"] == 1 and "candidates" not in public
    body = json.dumps({k: v for k, v in public.items() if k != "config"})  # the config is the repo's own, public
    assert "sig-" not in body and "http" not in body and "placeholder" not in body.lower() and "Topic T" not in body
    for c in private["candidates"]:
        assert c["id"] not in body
    for items in private["items"].values():
        for i in items:
            assert not i.get("title") or i["title"] not in body
    # the funnel and the queue agree with the private bundle
    assert public["funnel"]["candidates"] == len(private["candidates"])
    assert public["funnel"]["queue"] == sum(1 for c in private["candidates"] if c["queue"])


def test_the_private_bundle_holds_the_scan_with_its_fits(reviewed, tmp_path):
    status, mkey, counts = _run(reviewed, tmp_path, out=tmp_path / "mine" / "dashboard.json.gz")
    assert status == "passed", counts
    assert not counts.get("fit_mismatch") and not counts.get("anomaly_mismatch")
    b = json.loads(gzip.decompress((tmp_path / "mine" / "dashboard.json.gz").read_bytes()))
    assert b["kind"] == "private" and b["candidates"]
    queued = [c for c in b["candidates"] if c["queue"]]
    assert queued and all(c["id"] in b["dossiers"] for c in queued)
    series = [c for c in b["candidates"] if c["subject_kind"] == "series"]
    assert series and all(any(s["id"] in b["series"] for s in c["series"]) for c in series)
    for s in b["series"].values():
        assert len(s["periods"]) == len(s["values"]) == len(s["y"])
        for f in s["fits"]:
            assert f["lo"] <= f["slope"] <= f["hi"]
    m = json.loads(reviewed.get(mkey))
    assert m["outputs"][0]["key"] == private_key(AS_OF) and m["params"]["public"]["path"] == PUBLIC_PATH


def test_the_private_bundle_never_goes_in_the_repo(tmp_path):
    with pytest.raises(ValueError, match="never goes in the repo"):
        check_out_path(REPO_ROOT / "dashboard" / "data" / "dashboard.json.gz")
    check_out_path(REPO_ROOT / "data" / "dashboard.json.gz")  # git-ignored
    check_out_path(tmp_path / "dashboard.json.gz")
    for path in ("dashboard/data/dashboard.json.gz", "dashboard/data/mine.json"):
        assert subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO_ROOT).returncode == 0, path


def test_the_practice_bundle_is_invented_and_deterministic():
    public = json.loads((REPO_ROOT / PUBLIC_PATH).read_text())
    review, detect_cfg = load_review(), load_detect()
    a = practice_bundle(public, review, detect_cfg)
    b = practice_bundle(public, review, detect_cfg)
    assert encode(a) == encode(b)
    floor_check(a)
    assert a["kind"] == "practice" and "practice" in a
    assert sum(1 for c in a["candidates"] if c["queue"]) == review.queue.size
    assert {c["type"] for c in a["candidates"]} >= {"trend", "acceleration", "weak_signal"}
    assert all("(practice)" in i["title"] for v in a["items"].values() for i in v)


def test_the_committed_practice_bundle_is_current():
    """`moria dashboard` regenerates it; this says when the committed copy is stale."""
    public = json.loads((REPO_ROOT / PUBLIC_PATH).read_text())
    fresh = practice_bundle(public, load_review(), load_detect())
    committed = json.loads((REPO_ROOT / PRACTICE_PATH).read_text())
    key = lambda b: sorted((c["id"], (c["queue"] or {}).get("rank")) for c in b["candidates"])  # noqa: E731
    assert key(committed) == key(fresh), "run `uv run moria dashboard --practice-only`"


def _node_check(bundle: dict, tmp_path: Path) -> dict:
    """Run the dashboard's ranking port on a bundle with Moria's own settings (Node, ES module)."""
    shutil.copy(RANKING_JS, tmp_path / "ranking.mjs")
    (tmp_path / "bundle.json").write_text(json.dumps(bundle))
    (tmp_path / "check.mjs").write_text(
        'import { readFileSync } from "fs";\n'
        'import { settingsFrom, whatIf } from "./ranking.mjs";\n'
        'const b = JSON.parse(readFileSync(new URL("./bundle.json", import.meta.url)));\n'
        "const r = whatIf(b.candidates, settingsFrom(b.config), b.register);\n"
        "console.log(JSON.stringify({ shortlist: r.shortlist.map((p) => p.id), queue: r.queue.map((p) => p.id) }));\n"
    )
    out = subprocess.run(["node", str(tmp_path / "check.mjs")], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_the_dashboards_what_if_reproduces_the_queue(reviewed, tmp_path):
    out = tmp_path / "mine" / "dashboard.json.gz"
    assert _run(reviewed, tmp_path, out=out)[0] == "passed"
    public = json.loads((REPO_ROOT / PUBLIC_PATH).read_text())
    for bundle in (
        json.loads(gzip.decompress(out.read_bytes())),
        practice_bundle(public, load_review(), load_detect()),
    ):
        cands = bundle["candidates"]
        want_short = [
            c["id"] for c in sorted((c for c in cands if c["shortlist"]), key=lambda c: c["shortlist"]["rank"])
        ]
        want_queue = [c["id"] for c in sorted((c for c in cands if c["queue"]), key=lambda c: c["queue"]["rank"])]
        got = _node_check(bundle, tmp_path)
        assert got["shortlist"] == want_short and got["queue"] == want_queue
