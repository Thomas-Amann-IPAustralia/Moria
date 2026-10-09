"""Peak-memory probe for Moria's planned workloads (docs/design.md §3.2).

Each workload runs in its own process, so each peak is independent. The data is synthetic, at the planned scale.
Run it on the target VM to confirm the free tier (1 GB RAM) holds them, one job at a time:

    uv run --with scikit-learn --with pandas --with pyarrow --with duckdb [--with fastembed] python scripts/memprobe.py

Prints one JSON line per workload. The `embed` workload needs fastembed and downloads bge-small-en-v1.5 (about 130 MB).
"""

import json
import os
import resource
import subprocess
import sys
import tempfile
import time

WORKLOADS = [
    "imports",
    "text_sgd",
    "kmeans_iforest",
    "nmf_vocab20k",
    "nmf_hashed",
    "duckdb_agg",
    "hdbscan",
    "embed",
]


def synthetic_docs(n, rng, vocab=50_000, length=150):
    return [" ".join(f"w{w}" for w in row) for row in rng.integers(0, vocab, size=(n, length))]


def run(name):
    # Each workload imports what its real job would: numpy and pyarrow (every job reads Parquet), plus its own tools.
    import numpy as np
    import pyarrow  # noqa: F401

    rng = np.random.default_rng(0)
    out = {}
    if name == "imports":  # the whole analytics stack at once
        import duckdb
        import pandas  # noqa: F401
        import sklearn  # noqa: F401
    elif name == "text_sgd":
        from sklearn.feature_extraction.text import HashingVectorizer
        from sklearn.linear_model import SGDClassifier

        hv = HashingVectorizer(n_features=2**20, alternate_sign=False, norm="l2")
        clf = SGDClassifier(loss="log_loss")
        for _ in range(40):  # 40 batches of 5k = 200k documents, streamed
            batch = synthetic_docs(5_000, rng)
            clf.partial_fit(hv.transform(batch), rng.integers(0, 6, size=len(batch)), classes=list(range(6)))
        out["docs"] = 200_000
    elif name == "kmeans_iforest":
        from sklearn.cluster import MiniBatchKMeans
        from sklearn.ensemble import IsolationForest

        km = MiniBatchKMeans(n_clusters=200, batch_size=4096, random_state=0, n_init=1)
        for _ in range(20):  # 20 batches of 10k = 200k vectors of 384 dims, streamed
            km.partial_fit(rng.standard_normal((10_000, 384), dtype=np.float32))
        IsolationForest(n_estimators=200, random_state=0).fit(rng.standard_normal((50_000, 384), dtype=np.float32))
        out["vectors"] = 200_000
    elif name == "nmf_vocab20k":
        from sklearn.decomposition import MiniBatchNMF
        from sklearn.feature_extraction.text import TfidfVectorizer

        tv = TfidfVectorizer(max_features=20_000, dtype=np.float32).fit(synthetic_docs(20_000, rng))
        nmf = MiniBatchNMF(n_components=50, batch_size=2048, random_state=0)
        for _ in range(20):  # 100k documents
            nmf.partial_fit(tv.transform(synthetic_docs(5_000, rng)))
        out["docs"] = 100_000
    elif name == "nmf_hashed":  # the known over-budget setting: a dense model over a hashed feature space
        from sklearn.decomposition import MiniBatchNMF
        from sklearn.feature_extraction.text import HashingVectorizer

        hv = HashingVectorizer(n_features=2**18, alternate_sign=False, norm="l2")
        nmf = MiniBatchNMF(n_components=50, batch_size=2048, random_state=0)
        for _ in range(20):
            nmf.partial_fit(hv.transform(synthetic_docs(5_000, rng)))
        out["docs"] = 100_000
    elif name == "duckdb_agg":
        import duckdb

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "events.parquet")
            con = duckdb.connect()
            con.execute("SET memory_limit='300MB'; SET threads=2;")
            con.execute(
                f"""COPY (SELECT i AS application_number, (i % 4)::INT AS ip_right_type,
                         1990 + (i % 36) AS year, (hash(i) % 35)::INT AS tech_field,
                         (hash(i * 7) % 900)::INT AS days_to_event
                         FROM range(20000000) t(i)) TO '{path}' (FORMAT parquet, COMPRESSION zstd)"""
            )
            rows = con.execute(
                f"""SELECT ip_right_type, year, tech_field, count(*) n, median(days_to_event) med
                    FROM '{path}' GROUP BY ALL"""
            ).fetchall()
            out.update(rows_in=20_000_000, groups=len(rows), parquet_mb=round(os.path.getsize(path) / 1e6, 1))
    elif name == "hdbscan":
        from sklearn.cluster import HDBSCAN
        from sklearn.decomposition import PCA

        x = PCA(n_components=20, random_state=0).fit_transform(rng.standard_normal((20_000, 384), dtype=np.float32))
        HDBSCAN(min_cluster_size=25, copy=True).fit(x)
        out["points"] = 20_000
    elif name == "embed":
        try:
            from fastembed import TextEmbedding
        except ImportError:
            return {"skipped": "fastembed not installed"}
        words = [
            "patent",
            "trade",
            "mark",
            "innovation",
            "policy",
            "artificial",
            "intelligence",
            "examination",
            "filing",
            "design",
            "technology",
            "market",
            "australia",
            "research",
            "law",
            "court",
            "climate",
            "energy",
            "economy",
            "digital",
        ]
        texts = [" ".join(rng.choice(words, size=60)) for _ in range(2_000)]  # about 80 tokens each
        model = TextEmbedding("BAAI/bge-small-en-v1.5", threads=1)
        t0 = time.time()
        vecs = list(model.embed(texts, batch_size=64))
        out.update(texts=len(vecs), dims=len(vecs[0]), texts_per_s=round(len(vecs) / (time.time() - t0), 1))
    return out


if __name__ == "__main__":
    if len(sys.argv) == 2:
        t0 = time.time()
        extra = run(sys.argv[1])
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KiB on Linux
        print(
            json.dumps(
                {"workload": sys.argv[1], "peak_rss_mb": round(peak_mb), "seconds": round(time.time() - t0, 1), **extra}
            ),
            flush=True,
        )
    else:
        env = {**os.environ, "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "MKL_NUM_THREADS": "2"}
        for workload in WORKLOADS:
            subprocess.run([sys.executable, __file__, workload], env=env, check=False)
