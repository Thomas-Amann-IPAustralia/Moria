"""The decision-model speed test on a free T4 GPU (design §4.2, §9.1, §13 day 3), for the owner to run in a Kaggle or
Colab notebook (free notebooks need a person to start them). Synthetic sentences only: no evidence leaves the bucket.

The question: can the free decision model (`chaoliangUNSW/Jev-Style-0.8B-Decision-v3-GGUF`, Apache-2.0, Q4_K_M)
tag every item on a free T4, or only signals? On this session's CPU it took about 5.1 s per short item with 7
questions, so per-item tags come from scikit-learn on embeddings unless this test shows otherwise.

The rule, fixed before the number exists (SOP §2, step 3):
- **fast enough for per-item tags** if the median short item (7 questions) takes <= 0.15 s, so the 122k items of
  day 3 take <= 5 h, inside one free Kaggle session (12 h) and a sixth of the weekly free GPU quota (30 h);
- **signals only** otherwise. Either way the result goes to the owner as a recommendation (design §9.1).

How to run (Kaggle: Settings > Accelerator > GPU T4; or Colab: Runtime > T4 GPU), in one cell:

    !git clone --depth 1 https://github.com/Thomas-Amann-IPAustralia/Moria && python Moria/scripts/t4_jevstyle_speed.py

It downloads the pinned model files (every SHA-256 checked), builds llama.cpp at the commit the model card names with
CUDA, builds the model's own scorer, and prints one JSON line of timings. Paste that line back to Claude.

The model repo's code was read on 2026-10-13 before this script was written: `jev_style_decision_gguf.py` launches
only the local `jev-score` binary (a subprocess, no network calls); `jev_score.cpp` is a llama.cpp client; the build
script runs CMake and a C++ compiler. Hashes of the files read are pinned below.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = "chaoliangUNSW/Jev-Style-0.8B-Decision-v3-GGUF"
REVISION = "edf37c26a1098f83cf4264b8adbe0dca2d2ebb0c"
LLAMA_CPP_COMMIT = "441df11f65ea0b6d0c72965aaf70c8241070ddcb"
FILES = {
    "Jev-Style-0.8B-Decision-v3-Q4_K_M.gguf": "0a19bc29bacc33e0d871146c8612b24dd14c2ed2e61cedeb7a928b0852628bac",
    "tokenizer/tokenizer.json": "06b9509352d2af50381ab2247e083b80d32d5c0aba91c272ca9ff729b6a0e523",
    "tokenizer/tokenizer_config.json": "66e427c470fe580fe8c7b5725d857af23d8417e37fae62667ec698306a19987b",
    "jev_style_decision_gguf.py": "e6b028f043d943b5e33d63368070405c5f038b6ee6f71a11b44e93caa562f5ed",
    "jev_score.cpp": "90d848a61546286c74e484f61126f572b79c6f77f835450d8fc970b8547ce603",
    "build_jev_score.sh": "5789a1585c51fbc4a03b423099a451e05cb66b9db49bc6c9361f326aca170fda",
    "manifest.json": "e370c55aa62c6b47154e72e56608bde79c691cc857c10b9adf1339306ece3473",
    "readout_config.json": "01de9bcce7effbfd1ae0a3fa13e52d7fa9aa4dd1cd1e47977d6bbdcd5e63054a",
    "release_config.json": "c2651284fec1e877a19641063e36d0f3c1f367ccdcfc7a325657dc7bedd01d8f",
    "LICENSE": "bbedc3fda3305820b977265f01b8619d87570a6739de3a5582c3464840f1e57a",
    "NOTICE": "5b20e266b5b9b9c12df4cb53db6801bc08fe8f1471355aaec15c1a9f9aa0b201",
}
THRESHOLD_S = 0.15

# The same questions as scripts/probe_jevstyle.py (the CPU measurement), so the two numbers compare.
PATHWAYS = [
    "This development could change how many, or what kinds of, patents, trade marks, designs or plant breeder's "
    "rights are sought in Australia.",
    "This development could make IP rights more or less valuable or useful to businesses and creators.",
    "This development could change how IP rights are examined, granted, administered or enforced.",
    "This development could affect public trust in, or the perceived fairness of, the IP system.",
    "This development could affect an IP office's workforce, technology, security or funding.",
]
QUESTIONS = [{"t": "noul", "ins": ins, "crit": None} for ins in PATHWAYS] + [
    {"t": "choice", "ins": "Where does this change mainly originate?",
     "crit": {"political": "government, geopolitics, security", "economic": "markets, trade, finance, industry",
              "social": "population, values, health, education, work", "technological": "science and technology",
              "legal": "laws, courts, regulation", "environmental": "climate, energy, resources, nature"}},
    {"t": "choice", "ins": "When could its main effects arrive?",
     "crit": {"h1": "within 2 years", "h2": "in 2 to 5 years", "h3": "in 5 to 10 years or later"}},
]  # fmt: skip
SAMPLES = [  # synthetic sentences, written for the probe; not evidence
    "A court held that an artificial intelligence system cannot be named as an inventor on a patent application.",
    "The population aged 85 and over is projected to more than double over the next 40 years.",
    "A cyclone forced the closure of three ports for a week, disrupting exports.",
    "Researchers report a sodium-ion battery chemistry at a third of the cost of lithium-ion.",
    "Scammers are sending fake renewal invoices to trade mark owners, imitating official branding.",
    "The central bank left the cash rate unchanged at its October meeting.",
]


def sh(*cmd: str, cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def fetch(work: Path) -> Path:
    model = work / "model"
    for name, sha in FILES.items():
        path = model / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            urllib.request.urlretrieve(f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}", path)
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != sha:
            sys.exit(f"{name}: SHA-256 {got} is not the pinned {sha}; stopping")
    return model


def build(work: Path, model: Path) -> Path:
    llama = work / "llama.cpp"
    if not llama.exists():
        sh("git", "clone", "https://github.com/ggml-org/llama.cpp", str(llama))
        sh("git", "checkout", LLAMA_CPP_COMMIT, cwd=llama)
    out = work / "jev-score"
    if not out.exists():
        env = {**os.environ, "OUT": str(out), "LLAMA_CMAKE_FLAGS": "-DGGML_CUDA=ON"}
        print("+ sh build_jev_score.sh llama.cpp (CUDA)", flush=True)
        subprocess.run(["sh", str(model / "build_jev_score.sh"), str(llama)], env=env, check=True)
    return out


def main() -> None:
    work = Path(os.environ.get("JEV_WORK", "/tmp/jev"))
    work.mkdir(parents=True, exist_ok=True)
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()  # fmt: skip
    model = fetch(work)
    scorer = build(work, model)
    sys.path.insert(0, str(model))  # the wrapper was read before this script was written (see the docstring)
    from jev_style_decision_gguf import JevStyleDecisionGGUF

    t0 = time.time()
    m = JevStyleDecisionGGUF(str(model), quant="Q4_K_M", binary=str(scorer), verify=True, many_mode="batched")
    load_s = time.time() - t0
    m.decide_many(SAMPLES[0], QUESTIONS)  # warm-up
    lat = []
    for i in range(60):
        t = time.time()
        m.decide_many(SAMPLES[i % len(SAMPLES)], QUESTIONS)
        lat.append(time.time() - t)
    long_state = " ".join(SAMPLES * 120)  # about 8k tokens, a dossier's size
    t = time.time()
    out_long = m.decide_many(long_state, QUESTIONS)
    long_s = time.time() - t
    m.close()
    median = sorted(lat)[len(lat) // 2]
    print(json.dumps({
        "gpu": gpu, "revision": REVISION, "llama_cpp": LLAMA_CPP_COMMIT, "load_s": round(load_s, 1),
        "short_items": len(lat), "short_item_s_median": round(median, 3), "short_item_s_p90": round(sorted(lat)[54], 3),
        "questions_per_item": len(QUESTIONS), "long_state_tokens": out_long[0].get("input_tokens"),
        "long_state_s": round(long_s, 2), "hours_for_122k_items": round(median * 122_000 / 3600, 1),
        "verdict": "per-item tags" if median <= THRESHOLD_S else "signals only", "threshold_s": THRESHOLD_S,
    }))  # fmt: skip


if __name__ == "__main__":
    main()
