"""Repo hygiene (SOP §15.3): no secrets in tracked files; secrets, local data and private context are ignored."""

from __future__ import annotations

import re
import subprocess

from moria.config import REPO_ROOT

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS-style access key ids
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),  # OpenAI-style keys
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),  # Google API keys
    re.compile(r"\bghp_[A-Za-z0-9]{30,}"),  # GitHub tokens
    re.compile(r"(?i)(secret_access_key|api_key)\s*[:=]\s*['\"]?[A-Za-z0-9/+]{24,}"),
]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


def test_no_secrets_in_tracked_files():
    offenders = []
    for path in _git("ls-files").splitlines():
        full = REPO_ROOT / path
        if not full.is_file() or full.suffix in {".png", ".pdf", ".zst", ".lock"}:
            continue
        text = full.read_text(encoding="utf-8", errors="ignore")
        offenders += [f"{path}: {p.pattern}" for p in SECRET_PATTERNS if p.search(text)]
    assert not offenders, offenders


def test_private_and_local_paths_are_ignored():
    for path in (".env", "data/store/raw/x", "config/territories.context.yaml", ".venv/x"):
        assert subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO_ROOT).returncode == 0, path
    assert "config/territories.context.yaml" not in _git("ls-files").splitlines()
