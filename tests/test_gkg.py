"""The GKG bulk-file collector, against hand-built GKG 2.1 files (placeholder text, never real source text)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date

import httpx
import pytest

from moria.collectors import Window, run_collection
from moria.collectors import gdelt as gdelt_module
from moria.collectors.gdelt import QueryGroup
from moria.collectors.gkg import PhraseMatcher
from moria.records import decode_bundle

from .conftest import card, make_client, terms_config

DAY = date(2026, 10, 9)
QUOTE = "placeholder quoted words about widget licensing"


@pytest.fixture(autouse=True)
def fixed_terms(monkeypatch):
    territories, themes = terms_config(
        ["widget licensing", "gizmo"],
        themes={"testing": ["net zero"], "ip_test": ["sprocket"]},
        synonyms={"widget licensing": ["widget licence deal"]},
        rings={"ip_test": "core"},
    )
    monkeypatch.setattr(gdelt_module, "load_territories", lambda: territories)
    monkeypatch.setattr(gdelt_module, "load_themes", lambda: themes)


def row(url, domain, title="Placeholder title", quotes="", names="", collection="1", date_="20261009001500"):
    cols = [""] * 27
    cols[0] = f"{date_}-1"
    cols[1] = date_
    cols[2] = collection
    cols[3] = domain
    cols[4] = url
    cols[7] = "THEME_B;THEME_A;THEME_A;"
    cols[10] = "1#Placeland#AS#AS01##0#0#X#10;4#Elsewhere#US#US06##0#0#Y#20"
    cols[12] = "Private Person,30"
    cols[14] = "placeholder org,40;placeholder org,50"
    cols[15] = "1.5,3.0,1.5,4.5,20.0,0.0,321"
    cols[22] = quotes
    cols[23] = names
    cols[26] = (
        f"<PAGE_TITLE>{title}</PAGE_TITLE><PAGE_AUTHORS>Someone Named</PAGE_AUTHORS>"
        "<PAGE_PRECISEPUBTIMESTAMP>20261008230000</PAGE_PRECISEPUBTIMESTAMP>"
    )
    return "\t".join(cols)


def gkg_zip(rows: list[str], members: int = 1) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(members):
            zf.writestr(f"f{i}.gkg.csv", "\n".join(rows) + "\n")
    return buf.getvalue()


FILE_1 = [
    row("https://news.test/a", "news.test", title="Placeholder story on Widget Licensing"),
    row("https://news.test/net-zero-plan", "news.test"),  # matched in the URL only
    row("https://paper.test.au/q", "paper.test.au", quotes=f"10|40|said|{QUOTE}"),  # quotation only, .au
    row("https://news.test/n", "news.test", names="Gizmo Holdings,12;Other,40"),  # named entity only
    row("https://news.test/none", "news.test", title="Careful widgets with no match"),
    row("https://news.test/a", "news.test", title="Placeholder story on Widget Licensing"),  # duplicate URL
    row("https://tv.test/x", "tv.test", title="Widget licensing", collection="2"),  # not the open web
    "too\tfew\tcolumns",
]
FILE_2 = [row("https://other.test.au/b", "other.test.au", title="Net-zero placeholder", date_="20261009003000")]


def make_handler(files: dict[str, bytes], seen: list[str] | None = None):
    def handler(request):
        stamp = request.url.path.rsplit("/", 1)[-1].split(".")[0]
        if seen is not None:
            seen.append(stamp)
        return httpx.Response(200, content=files[stamp]) if stamp in files else httpx.Response(404)

    return handler


def gkg_card(**params):
    return card("gdelt_gkg", {"base_url": "https://data.test/gdeltv2", "max_missing_files": 96, **params})


def test_gkg_keeps_matching_documents_and_counts_volumes(http_cfg, store):
    files = {"20261009000000": gkg_zip(FILE_1), "20261009001500": gkg_zip(FILE_2)}
    r = run_collection(gkg_card(), store, make_client(http_cfg, make_handler(files)), Window.for_day(DAY))
    assert r.status == "passed", r.error
    recs = decode_bundle(store.get(r.bundle_key))
    docs = {x.payload["url"]: x for x in recs if x.envelope.kind == "document"}
    assert set(docs) == {
        "https://news.test/a",
        "https://news.test/net-zero-plan",
        "https://paper.test.au/q",
        "https://news.test/n",
        "https://other.test.au/b",
    }
    a = docs["https://news.test/a"]
    assert a.payload["matches"] == [{"group": "T9:core:0", "phrase": "widget licensing", "fields": ["title"]}]
    assert docs["https://news.test/net-zero-plan"].payload["matches"][0]["fields"] == ["url"]
    assert docs["https://paper.test.au/q"].payload["matches"][0]["fields"] == ["quotations"]
    assert docs["https://news.test/n"].payload["matches"][0]["phrase"] == "gizmo"
    assert a.payload["themes"] == ["THEME_A", "THEME_B"] and a.payload["organisations"] == ["placeholder org"]
    assert a.payload["location_countries"] == ["AS", "US"] and a.payload["tone"] == {"tone": 1.5, "word_count": 321}
    assert a.envelope.event_at.startswith("2026-10-08T23:00") and a.envelope.observable_at.startswith(
        "2026-10-09T00:15"
    )

    # Article text, person names and authors are never stored
    raw = store.get(r.bundle_key)
    bundle_text = json.dumps([x.model_dump() for x in recs])
    for private in (QUOTE, "Private Person", "Someone Named"):
        assert private not in bundle_text, private
    assert docs["https://paper.test.au/q"].payload["has_quotations"] is True and raw

    vols = {(x.payload["query_group"], x.payload["scope"]): x.payload for x in recs if x.envelope.kind == "observation"}
    assert vols[("T9:core:0", "world")]["matching_documents"] == 3  # a, the quotation, the name
    assert vols[("T9:core:0", "world")]["matches_by_field"] == {"names": 1, "quotations": 1, "title": 1}
    # about: in the title or URL; names-only: only inside a named entity (often incidental, D-012)
    assert vols[("T9:core:0", "world")]["about_documents"] == 1
    assert vols[("T9:core:0", "world")]["names_only_documents"] == 1
    assert vols[("theme:testing:0", "world")]["about_documents"] == 2
    assert vols[("T9:core:0", "au")]["matching_documents"] == 1
    assert vols[("theme:testing:0", "world")]["matching_documents"] == 2
    assert vols[("theme:testing:0", "world")]["total_documents"] == 6  # duplicates and non-web rows excluded
    assert vols[("theme:testing:0", "au")]["total_documents"] == 2
    assert (
        vols[("theme:testing:0", "world")]["files_read"] == 2
        and vols[("theme:testing:0", "world")]["files_expected"] == 96
    )

    warnings = " ".join(r.warnings)
    assert "94 of 96 files not published" in warnings and "1 rows skipped" in warnings
    assert (
        vols[("T9:core:0", "world")]["ring"] == "core" and vols[("theme:testing:0", "world")]["ring"] == "wider_world"
    )
    assert vols[("theme:ip_test:0", "world")]["ring"] == "core"  # a theme's ring from themes.yaml (D-014)


def test_a_synonym_counts_as_its_term_and_the_record_names_it(http_cfg, store):
    rows = [
        row("https://news.test/s", "news.test", title="Placeholder widget licence deals announced"),
        row("https://news.test/t", "news.test", title="Widget licensing and a widget licence deal"),
    ]
    files = {"20261009000000": gkg_zip(rows)}
    r = run_collection(gkg_card(), store, make_client(http_cfg, make_handler(files)), Window.for_day(DAY))
    assert r.status == "passed", r.error
    recs = decode_bundle(store.get(r.bundle_key))
    docs = {x.payload["url"]: x.payload for x in recs if x.envelope.kind == "document"}
    assert docs["https://news.test/s"]["matches"] == [
        {"group": "T9:core:0", "phrase": "widget licensing", "fields": ["title"], "synonyms": ["widget licence deal"]}
    ]
    assert docs["https://news.test/t"]["matches"][0]["synonyms"] == ["widget licence deal"]
    vols = {(x.payload["query_group"], x.payload["scope"]): x.payload for x in recs if x.envelope.kind == "observation"}
    assert vols[("T9:core:0", "world")]["matching_documents"] == 2


def test_matcher_reports_the_form_that_matched_and_the_group_expression_lists_synonyms():
    g = QueryGroup("g:0", ("patent waiver", "net zero"), (("patent waiver", ("trips waiver",)),))
    m = PhraseMatcher([g])
    assert m.forms_in("Members debate the TRIPS waivers") == {("patent waiver", "trips waiver")}
    assert m.phrases_in("A patent waiver and a TRIPS waiver") == {"patent waiver"}
    assert m.forms_in("A patent waiver and a TRIPS waiver") == {
        ("patent waiver", "patent waiver"),
        ("patent waiver", "trips waiver"),
    }
    assert g.expression == '("patent waiver" OR "trips waiver" OR "net zero")'


def test_gkg_fails_loudly_when_too_many_files_are_missing(http_cfg, store):
    files = {"20261009000000": gkg_zip(FILE_1)}
    c = gkg_card(max_missing_files=4)
    r = run_collection(c, store, make_client(http_cfg, make_handler(files)), Window.for_day(DAY))
    assert r.status == "failed" and "95 of 96 files missing (allowed 4)" in r.error
    assert json.loads(store.get(r.manifest_key))["status"] == "failed"


def test_gkg_limit_caps_the_files_and_rejects_a_bad_zip(http_cfg, store):
    seen: list[str] = []
    files = {"20261009000000": gkg_zip(FILE_1), "20261009001500": gkg_zip(FILE_2)}
    r = run_collection(
        gkg_card(), store, make_client(http_cfg, make_handler(files, seen)), Window.for_day(DAY), limit=1
    )
    assert r.status == "passed" and seen == ["20261009000000"]

    bad = {"20261009000000": b"not a zip"}
    r = run_collection(gkg_card(), store, make_client(http_cfg, make_handler(bad)), Window.for_day(DAY), limit=1)
    assert r.status == "failed" and "not a valid zip" in r.error
    two = {"20261009000000": gkg_zip(FILE_1, members=2)}
    r = run_collection(gkg_card(), store, make_client(http_cfg, make_handler(two)), Window.for_day(DAY), limit=1)
    assert r.status == "failed" and "holds 2 files" in r.error


def test_phrase_matching_uses_whole_words_and_treats_hyphens_as_spaces():
    m = PhraseMatcher([QueryGroup("g:0", ("aged care", "care", "net zero", "AI"))])
    assert m.phrases_in("Aged-care reform") == {"aged care", "care"}
    assert m.phrases_in("aged, careful") == set()  # words must be adjacent and whole
    assert m.phrases_in("careful wording") == set()
    assert m.phrases_in("https://x.test/net-zero_target") == {"net zero"}
    assert m.phrases_in("AI and air") == {"ai"}
    assert m.groups_by_phrase["care"] == ["g:0"]


def test_gkg_card_validates_match_fields():
    with pytest.raises(Exception, match="unknown match_fields"):
        from moria.collectors.gkg import GkgCollector

        GkgCollector(gkg_card(match_fields=["title", "body"]))


def test_phrases_match_in_both_spellings_and_with_a_plural_last_word():
    from moria.collectors.gkg import phrase_variants

    assert phrase_variants("organised crime") == {
        "organised crime",
        "organized crime",
        "organised crimes",
        "organized crimes",
    }
    assert "intellectual property commercialization" in phrase_variants("intellectual property commercialisation")
    assert "defense industries" in phrase_variants("defence industry")
    assert "trademark attorneys" in phrase_variants("trade mark attorney")
    assert phrase_variants("four corners") == {"four corners"}  # no false spellings ("four" is not "four" -> "for")
    assert phrase_variants("enterprise") == {"enterprise", "enterprises"}  # -ise only for known stems
    assert "deglobalization" in phrase_variants("deglobalisation")  # -isation always has an -ization spelling
    m = PhraseMatcher([QueryGroup("g:0", ("organised crime", "supply chain disruption", "population ageing"))])
    assert m.phrases_in("Organized-crime ring linked to supply chain disruptions") == {
        "organised crime",
        "supply chain disruption",
    }
    assert m.phrases_in("An ageing population") == set()  # word order is not varied
