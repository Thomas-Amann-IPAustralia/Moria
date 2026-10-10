"""Run manifests (SOP §13): one per run, failed runs included, never overwritten.

A manifest records the status, the outputs and their SHA-256, counts and warnings, the config hash, the git commit
and dirty flag, and the package versions. Stored at manifests/<command>/<run_id>.json.
"""

from __future__ import annotations

import os
import platform
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from importlib import metadata
from typing import Any

from . import __version__
from .config import REPO_ROOT
from .records import canonical_json, sha256_hex, utc_now
from .store import Store

TRACKED_PACKAGES = ("moria", "httpx", "pydantic", "boto3", "zstandard", "defusedxml", "pyyaml", "typer")


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def git_identity() -> dict[str, Any]:
    commit = os.environ.get("GITHUB_SHA") or _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--", ".", ":(exclude)data")
    return {"commit": commit, "dirty": bool(status) if status is not None else None}


def package_versions() -> dict[str, str]:
    out = {"python": platform.python_version()}
    for name in TRACKED_PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "not installed"
    return out


def new_run_id() -> str:
    return f"{utc_now():%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"


@dataclass
class Manifest:
    command: str
    run_id: str = field(default_factory=new_run_id)
    started_at: str = field(default_factory=lambda: utc_now().isoformat(timespec="seconds"))
    finished_at: str | None = None
    status: str = "running"
    error: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    config_hash: str | None = None
    outputs: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    git: dict[str, Any] = field(default_factory=git_identity)
    versions: dict[str, str] = field(default_factory=package_versions)
    moria_version: str = __version__

    def add_output(self, key: str, data: bytes) -> None:
        self.outputs.append({"key": key, "sha256": sha256_hex(data), "bytes": len(data)})

    @property
    def key(self) -> str:
        return f"manifests/{self.command}/{self.run_id}.json"

    def finish(self, store: Store, status: str, error: str | None = None) -> str:
        self.status, self.error = status, error
        self.finished_at = utc_now().isoformat(timespec="seconds")
        store.put(self.key, canonical_json(asdict(self)).encode("utf-8"), "application/json")
        return self.key
