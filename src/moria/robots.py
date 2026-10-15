"""robots.txt as RFC 9309 reads it: the most specific rule wins, and `*` and `$` are wildcards.

Python's `urllib.robotparser` applies the first rule that matches, in file order, and reads `*` literally. Under it,
a file such as data.csiro.au's (`Disallow: /dap/` then `Allow: /dap/ws/v2/`) disallows the public API that the
second line allows, and `Disallow: /*.pdf` never matches anything.

Here, as in RFC 9309 §2.2: the group for Moria's product token is used if there is one (groups naming it are
merged), else the `*` group; the rule whose path pattern matches the most characters wins; an allow wins a tie; no
match means allowed; /robots.txt itself is always allowed.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

_LINE = re.compile(r"^\s*([A-Za-z-]+)\s*:\s*(.*?)\s*$")


def _product_token(user_agent: str) -> str:
    return re.split(r"[/\s]", user_agent.strip(), maxsplit=1)[0].lower()


def _pattern(path: str) -> re.Pattern:
    anchored = path.endswith("$")
    body = path[:-1] if anchored else path
    regex = ".*".join(re.escape(_normalise(part)) for part in body.split("*"))
    return re.compile(regex + ("$" if anchored else ""))


def _normalise(path: str) -> str:
    # compare decoded paths, so that %7E and ~ are the same (RFC 9309 §2.2.2), keeping an encoded slash distinct
    return unquote(path.replace("%2F", "%252F").replace("%2f", "%252F"))


class RobotsRules:
    def __init__(self, text: str, user_agent: str):
        token = _product_token(user_agent)
        groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
        agents: list[str] = []
        rules: list[tuple[bool, str]] = []
        in_rules = False
        for raw in text.splitlines():
            m = _LINE.match(raw.split("#", 1)[0])
            if not m:
                continue
            field, value = m.group(1).lower(), m.group(2)
            if field == "user-agent":
                if in_rules:  # a user-agent line after rules starts a new group
                    groups.append((agents, rules))
                    agents, rules, in_rules = [], [], False
                agents.append(value.lower())
            elif field in ("allow", "disallow"):
                in_rules = True
                if value:  # an empty disallow allows everything: no rule
                    rules.append((field == "allow", value))
        if agents:
            groups.append((agents, rules))
        mine = [r for a, r in groups if any(_product_token(ag) == token for ag in a if ag != "*")]
        chosen = mine or [r for a, r in groups if "*" in a]
        self.rules = [(allow, len(path), _pattern(path)) for group in chosen for allow, path in group]

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        path = parts.path or "/"
        if path == "/robots.txt":
            return True
        target = _normalise(path + (f"?{parts.query}" if parts.query else ""))
        best: tuple[int, bool] | None = None
        for allow, length, pattern in self.rules:
            if pattern.match(target) and (best is None or (length, allow) > best):
                best = (length, allow)
        return True if best is None else best[1]
