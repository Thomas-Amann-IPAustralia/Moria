"""The text encoder (design §9.1): `BAAI/bge-small-en-v1.5` (MIT), its own ONNX export, run by onnxruntime on CPU.

The model's files are fetched at the revision pinned in `config/features.yaml` and each is checked against its
SHA-256 before it is loaded (CLAUDE.md: third-party model files are pinned and hashed). No model code is run: the
ONNX graph is data to onnxruntime, and the tokenizer is the `tokenizers` library reading `tokenizer.json`.

Pooling is the [CLS] token, L2-normalised, as the model's `1_Pooling/config.json` says; no query instruction is
added, because items are compared with items and with label descriptions, not queries with passages.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

from .config import REPO_ROOT, EmbedConfig
from .http import PoliteClient
from .lake import file_sha256

log = logging.getLogger("moria.embed")


class ModelFileError(RuntimeError):
    pass


def model_dir(cfg: EmbedConfig) -> Path:
    return REPO_ROOT / cfg.cache_dir / cfg.model.replace("/", "__") / cfg.revision


def ensure_files(cfg: EmbedConfig, client: PoliteClient | None) -> Path:
    """The pinned model files in the local cache, downloaded if missing; every file's SHA-256 checked."""
    root = model_dir(cfg)
    for name, sha in sorted(cfg.files.items()):
        path = root / name
        if not path.exists() or file_sha256(path) != sha:
            if client is None:
                raise ModelFileError(f"{cfg.model}: {name} is not in {root} and downloads are off")
            path.parent.mkdir(parents=True, exist_ok=True)
            url = f"https://huggingface.co/{cfg.model}/resolve/{cfg.revision}/{name}"
            got, size = client.download(url, path.with_name(path.name + ".part"))
            if got != sha:
                path.with_name(path.name + ".part").unlink(missing_ok=True)
                raise ModelFileError(f"{cfg.model}: {name} has SHA-256 {got[:12]}…, not the pinned {sha[:12]}…")
            path.with_name(path.name + ".part").replace(path)
            log.info("embed: fetched %s (%d bytes, SHA-256 checked)", name, size)
    return root


class Encoder:
    """Texts to unit vectors. Batches are formed from texts of similar length, so padding stays short."""

    def __init__(self, cfg: EmbedConfig, client: PoliteClient | None = None, threads: int | None = None):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        root = ensure_files(cfg, client)
        self.cfg = cfg
        self.identity = f"{cfg.model}@{cfg.revision}"
        tok = Tokenizer.from_file(str(root / "tokenizer.json"))
        tok.enable_truncation(max_length=cfg.max_tokens)
        tok.enable_padding(pad_id=0, pad_token="[PAD]")
        self.tokenizer = tok
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads or os.cpu_count() or 1
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(root / "onnx/model.onnx"), opts, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}

    def encode(self, texts: list[str], progress_every: int = 0) -> np.ndarray:
        out = np.zeros((len(texts), self.cfg.dim), dtype=np.float32)
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        bs = self.cfg.batch_size
        for start in range(0, len(order), bs):
            idx = order[start : start + bs]
            enc = self.tokenizer.encode_batch([texts[i] or " " for i in idx])
            feed = {
                "input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
                "token_type_ids": np.array([e.type_ids for e in enc], dtype=np.int64),
            }
            hidden = self.session.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0]
            cls = hidden[:, 0, :]
            out[idx] = cls / np.maximum(np.linalg.norm(cls, axis=1, keepdims=True), 1e-12)
            if progress_every and (start // bs) % progress_every == 0:
                log.info("embed: %d of %d texts", start + len(idx), len(texts))
        return out


def to_blob(vectors: np.ndarray) -> list[bytes]:
    """Vectors stored as little-endian float16: 768 bytes for 384 dimensions."""
    half = vectors.astype("<f2")
    return [row.tobytes() for row in half]


def from_blobs(blobs: list[bytes], dim: int) -> np.ndarray:
    if not blobs:
        return np.zeros((0, dim), dtype=np.float32)
    return np.frombuffer(b"".join(blobs), dtype="<f2").reshape(len(blobs), dim).astype(np.float32)
