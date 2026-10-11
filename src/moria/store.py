"""The system of record: a private R2 bucket, or a local directory with the same layout for tests and dry runs.

Keys are POSIX-style paths ("raw/gdelt/2026/10/09/<run_id>.jsonl.zst"). Raw objects are immutable: writing an existing
key under raw/ fails loudly.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Protocol

from .config import REPO_ROOT, StoreConfig

IMMUTABLE_PREFIXES = ("raw/", "manifests/")


class StoreError(RuntimeError):
    pass


class Store(Protocol):
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def list(self, prefix: str) -> list[str]: ...


def _check_key(key: str) -> None:
    if key.startswith("/") or ".." in key.split("/") or not key:
        raise StoreError(f"invalid store key: {key!r}")


class LocalStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        _check_key(key)
        return self.root / key

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        path = self._path(key)
        if key.startswith(IMMUTABLE_PREFIXES) and path.exists():
            raise StoreError(f"refusing to overwrite immutable object: {key}")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)  # atomic on POSIX
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def list(self, prefix: str) -> list[str]:
        base = self.root
        if not base.exists():
            return []
        keys = [
            p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file() and not p.name.startswith(".tmp-")
        ]
        return sorted(k for k in keys if k.startswith(prefix))


class R2Store:
    """Cloudflare R2 through its S3-compatible API. Credentials come only from the environment (names in config)."""

    def __init__(self, cfg: StoreConfig):
        import boto3  # imported here so tests and local runs need no AWS stack configured

        missing = [
            n for n in (cfg.account_id_env, cfg.access_key_id_env, cfg.secret_access_key_env) if not os.environ.get(n)
        ]
        if missing:
            raise StoreError(f"R2 credentials missing from the environment: {', '.join(missing)}")
        self.bucket = cfg.bucket
        self._s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ[cfg.account_id_env]}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ[cfg.access_key_id_env],
            aws_secret_access_key=os.environ[cfg.secret_access_key_env],
            region_name="auto",
        )

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        _check_key(key)
        if key.startswith(IMMUTABLE_PREFIXES) and self.exists(key):
            raise StoreError(f"refusing to overwrite immutable object: {key}")
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        _check_key(key)
        return self._s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def list(self, prefix: str) -> list[str]:
        keys: list[str] = []
        for page in self._s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return sorted(keys)


def open_store(cfg: StoreConfig, backend: str | None = None) -> Store:
    chosen = backend or cfg.backend
    if chosen == "local":
        return LocalStore(REPO_ROOT / cfg.local_root)
    if chosen == "r2":
        return R2Store(cfg)
    raise StoreError(f"unknown store backend: {chosen!r}")
