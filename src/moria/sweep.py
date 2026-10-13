"""The security sweep (SOP §16.2, §22; design §12), run inside `moria normalise` on every text field it keeps.

Every source's text is untrusted data that will later sit in dossiers and in the decision model's prompts. The sweep:
- removes hidden characters (zero-width, bidirectional controls, Unicode tag characters) and reports them;
- looks for AI-directed instructions, secrets and active content;
- counts personal data (e-mail addresses, phone numbers) without changing the text: judgments and notices name
  people, and their text stays in the private bucket (CLAUDE.md).

A high-severity finding quarantines the item: it is left out of lake/documents and listed, by id and finding code
only, in lake/quarantine/. Only the owner adds allowlist entries (config/sweep.yaml); Claude proposes them in chat.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .config import CONFIG_DIR, _load_yaml

SWEEP_VERSION = "sweep-v1"

Severity = Literal["low", "medium", "high"]

_ZERO_WIDTH = "\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\u2064\ufeff\u00ad"
_BIDI = "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
_HIDDEN = re.compile(f"[{_ZERO_WIDTH}{_BIDI}]")
_TAG_CHARS = re.compile("[\U000e0000-\U000e007f]")

# (code, severity, pattern). Instructions are matched as instructions addressed to a model, not as a topic: a paper
# about prompt injection may say "prompt injection" freely, but not "ignore all previous instructions".
_RULES: list[tuple[str, Severity, re.Pattern]] = [
    ("instruction_override", "high", re.compile(
        r"\b(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|above|earlier|"
        r"preceding)\s+(instructions?|prompts?|directions|rules|context)\b", re.I)),
    ("instruction_role", "high", re.compile(
        r"\b(you are now|from now on you are|act as|pretend to be)\s+(an?\s+)?(ai|assistant|chatgpt|claude|"
        r"language model|llm|dan)\b", re.I)),
    ("chat_markup", "high", re.compile(r"<\|(im_start|im_end|system|endoftext)\|>|\[/?INST\]|<<SYS>>", re.I)),
    ("addressed_to_model", "medium", re.compile(
        r"\b(note to (the )?(ai|llm|model|assistant)|if you are an? (ai|llm|language model|assistant))\b", re.I)),
    ("secret_aws_key", "high", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("secret_private_key", "high", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")),
    ("secret_token", "high", re.compile(
        r"\b(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}|sk-(ant-|proj-)?[A-Za-z0-9_-]{32,}|"
        r"xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})\b")),
    ("active_content", "medium", re.compile(r"<script\b|javascript:|<iframe\b|\bon(load|error|click)\s*=", re.I)),
    ("email_address", "low", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("phone_number", "low", re.compile(r"(?<!\d)(\+61\s?|0)[2-478](\s?\d){8}(?!\d)")),
]  # fmt: skip


class AllowEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str
    code: str
    approved_by: str
    approved_on: str
    reason: str


class SweepFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    allowlist: list[AllowEntry] = []


def load_sweep(config_dir: Path = CONFIG_DIR) -> SweepFile:
    return SweepFile.model_validate(_load_yaml(config_dir / "sweep.yaml"))


@dataclass
class SweepResult:
    fields: dict[str, str]  # the cleaned texts
    findings: dict[str, int] = field(default_factory=dict)  # code -> count
    severity: Severity | None = None

    def codes(self, at_least: Severity = "low") -> list[str]:
        order = {"low": 0, "medium": 1, "high": 2}
        return sorted(c for c in self.findings if order[SEVERITY[c]] >= order[at_least])


SEVERITY: dict[str, Severity] = {code: sev for code, sev, _ in _RULES}
SEVERITY.update({"hidden_characters": "medium", "unicode_tag_characters": "high"})


def sweep(texts: dict[str, str], allowed: set[str] = frozenset()) -> SweepResult:
    """Clean and scan an item's texts. `allowed` holds the finding codes the owner allowlisted for this item."""
    result = SweepResult(fields={})
    for name, text in texts.items():
        if not text:
            result.fields[name] = text
            continue
        if n := len(_TAG_CHARS.findall(text)):
            result.findings["unicode_tag_characters"] = result.findings.get("unicode_tag_characters", 0) + n
            text = _TAG_CHARS.sub("", text)
        if n := len(_HIDDEN.findall(text)):
            result.findings["hidden_characters"] = result.findings.get("hidden_characters", 0) + n
            text = _HIDDEN.sub("", text)
        text = unicodedata.normalize("NFC", text)
        for code, _sev, pattern in _RULES:
            if n := len(pattern.findall(text)):
                result.findings[code] = result.findings.get(code, 0) + n
        result.fields[name] = text
    order = {"low": 0, "medium": 1, "high": 2}
    live = [SEVERITY[c] for c in result.findings if c not in allowed]
    result.severity = max(live, key=order.__getitem__) if live else None
    return result
