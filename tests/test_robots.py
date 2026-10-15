"""robots.txt read as RFC 9309 reads it: the most specific rule wins, with wildcards."""

from __future__ import annotations

from moria.robots import RobotsRules

UA = "Moria/0.1 (+https://example.test/moria)"

# The shape of data.csiro.au's file (2026-10-15): a disallowed tree with an allowed API inside it
NESTED = """# comment
User-agent: *
Disallow: /dap/
Allow: /dap/ws/v2/
Disallow: /dap/ws/v2/collections/*/data/
Disallow: /dap/ws/v2/collections/*downloadzip
Disallow: /dap/api/v2/
Allow: /dap/api/v2/collections/*/files/summary
"""


def test_the_most_specific_rule_wins_whatever_its_order():
    r = RobotsRules(NESTED, UA)
    assert r.allowed("https://s.test/dap/ws/v2/collections/searchbylocation?p=1&browseValue=X&atom=true")
    assert not r.allowed("https://s.test/dap/swagger-ui.html")
    assert not r.allowed("https://s.test/dap/ws/v2/collections/csiro:1/data/file.csv")
    assert not r.allowed("https://s.test/dap/ws/v2/collections/csiro:1/downloadzip")
    assert not r.allowed("https://s.test/dap/api/v2/collections/1/files")
    assert r.allowed("https://s.test/dap/api/v2/collections/1/files/summary")
    assert r.allowed("https://s.test/collection/csiro:1") and r.allowed("https://s.test/robots.txt")


def test_wildcards_end_anchors_ties_and_empty_rules():
    text = "User-agent: *\nDisallow: /*.pdf$\nDisallow: /x\nAllow: /x\nDisallow:\n"
    r = RobotsRules(text, UA)
    assert not r.allowed("https://s.test/docs/a.pdf")
    assert r.allowed("https://s.test/docs/a.pdf?download=1")  # $ anchors the end
    assert r.allowed("https://s.test/x/page")  # equal length: allow wins
    assert RobotsRules("User-agent: *\nDisallow:\n", UA).allowed("https://s.test/anything")


def test_a_group_naming_moria_replaces_the_star_group():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: OtherBot\nUser-agent: moria\nDisallow: /private/\n"
    r = RobotsRules(text, UA)
    assert r.allowed("https://s.test/public") and not r.allowed("https://s.test/private/a")
    assert not RobotsRules(text, "SomeoneElse/1.0").allowed("https://s.test/public")


def test_percent_encoding_is_compared_decoded():
    r = RobotsRules("User-agent: *\nDisallow: /~joe/\n", UA)
    assert not r.allowed("https://s.test/%7Ejoe/index.html")
