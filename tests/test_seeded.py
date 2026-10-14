"""Day 4 end to end: the seeded artefacts on a minimal evidence layer. Every stage runs (monitor, the series and
document measures, detect, artefacts) on a copy with synthetic seeds; each seed must be caught by its check and each
control detected without that flag (design §11.2)."""

from __future__ import annotations

import json

from moria.config import load_detect, load_features, load_sources
from moria.seeded import evaluate, report

from .detect_fixtures import AS_OF, minimal_layer


def test_every_seeded_artefact_is_flagged_and_every_control_is_not(store):
    minimal_layer(store)
    status, mkey, counts, result = evaluate(store, load_detect(), load_features(), load_sources(), AS_OF)
    assert status == "passed", counts
    missed = [r for r in result if not (r["caught"] and r["control_ok"])]
    assert not missed, json.dumps(missed, indent=1, default=str)
    assert counts == {"seeds": 6, "caught": 6, "controls_ok": 6, "all_flagged": 1}
    text = report(result, mkey, AS_OF)
    assert "6 of 6 seeds caught" in text and "seedphrase" not in text  # the report names seeds, not their phrases
    # the copy is gone; the real store holds only the eval's manifest
    assert not store.list("candidates/") and store.list("manifests/eval.artefacts/")


def test_scan_report_holds_counts_only(store):
    from moria.cli import run_scan
    from moria.scan_report import scan_report

    minimal_layer(store)
    cfg, cards = load_detect(), load_sources()
    run_scan(store, cfg, cards, AS_OF)
    text = scan_report(store, cfg, AS_OF)
    assert f"# Scan of {AS_OF}" in text and "## Candidates by type and artefact check" in text
    assert "Topic T1" not in text and "placeholder phrase" not in text  # labels and keyphrases stay in the bucket
