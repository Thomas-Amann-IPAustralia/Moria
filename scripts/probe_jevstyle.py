"""Probe a free Jev-class decision model on CPU: peak memory, speed, and a sanity look (docs/design.md §4.2, §9).

Model: chaoliangUNSW/Jev-Style-0.8B-Decision-v3-GGUF (Apache-2.0), Q4_K_M, run by its bundled llama.cpp scorer.
Read the model repo's scripts before running them (they launch only the local scorer; no network calls).

    hf download chaoliangUNSW/Jev-Style-0.8B-Decision-v3-GGUF --local-dir MODEL_DIR \
        --include "*Q4_K_M.gguf" "tokenizer/*" "*.py" "*.cpp" "*.sh" "*.json" requirements.txt LICENSE NOTICE
    git -C llama.cpp checkout 441df11f65ea0b6d0c72965aaf70c8241070ddcb   # the commit the model card names
    (cd MODEL_DIR && OUT=/path/to/jev-score sh build_jev_score.sh /path/to/llama.cpp)
    python scripts/probe_jevstyle.py MODEL_DIR /path/to/jev-score THREADS

The six sample sentences are a smoke test of behaviour, not a measure of accuracy (that needs labelled items).
"""

import json
import resource
import sys
import time

model_dir, scorer, threads = sys.argv[1], sys.argv[2], int(sys.argv[3])
sys.path.insert(0, model_dir)  # the wrapper was read before running; it only launches the local scorer
from jev_style_decision_gguf import JevStyleDecisionGGUF

PATHWAYS = {
    "p1_demand": "This development could change how many, or what kinds of, patents, trade marks, designs or "
    "plant breeder's rights are sought in Australia.",
    "p2_value": "This development could make IP rights more or less valuable or useful to businesses and creators.",
    "p3_administer": "This development could change how IP rights are examined, granted, administered or enforced.",
    "p4_legitimacy": "This development could affect public trust in, or the perceived fairness of, the IP system.",
    "p5_operations": "This development could affect an IP office's workforce, technology, security or funding.",
}
QUESTIONS = [{"t": "noul", "ins": ins, "crit": None} for ins in PATHWAYS.values()] + [
    {
        "t": "choice",
        "ins": "Where does this change mainly originate?",
        "crit": {
            "political": "government, geopolitics, security",
            "economic": "markets, trade, finance, industry",
            "social": "population, values, health, education, work",
            "technological": "science and technology",
            "legal": "laws, courts, regulation",
            "environmental": "climate, energy, resources, nature",
        },
    },
    {
        "t": "choice",
        "ins": "When could its main effects arrive?",
        "crit": {"h1": "within 2 years", "h2": "in 2 to 5 years", "h3": "in 5 to 10 years or later"},
    },
]

SAMPLES = [
    (
        "The Full Federal Court held that an artificial intelligence system cannot be named as an inventor on an "
        "Australian patent application."
    ),
    (
        "Australia's population aged 85 and over is projected to more than double over the next 40 years, increasing "
        "demand for health and aged care workers."
    ),
    "A cyclone forced the closure of three Queensland ports for a week, disrupting exports of coal and beef.",
    (
        "Researchers report a room-temperature sodium-ion battery chemistry that reaches 80% of lithium-ion energy "
        "density at a third of the cost."
    ),
    "Scammers are sending fake renewal invoices to trade mark owners, imitating official IP office branding.",
    "The Reserve Bank left the cash rate unchanged at its October meeting.",
]


def child_hwm_mb(pid):
    with open(f"/proc/{pid}/status") as f:
        for line in f:
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) / 1024
    return None


t0 = time.time()
m = JevStyleDecisionGGUF(model_dir, quant="Q4_K_M", binary=scorer, threads=threads, verify=True, many_mode="batched")
load_s = time.time() - t0

results, lat = [], []
for s in SAMPLES:
    t = time.time()
    out = m.decide_many(s, QUESTIONS)
    lat.append(time.time() - t)
    row = {
        k: round(o["probabilities"]["true"] if "true" in o["probabilities"] else o["top_probability"], 2)
        for k, o in zip(list(PATHWAYS) + ["origin", "horizon"], out)
    }
    row["origin"] = out[5]["answer"]
    row["horizon"] = out[6]["answer"]
    results.append({"state": s[:70], **row})

# a dossier-sized state: about 4k tokens
long_state = " ".join(SAMPLES * 60)
t = time.time()
out_long = m.decide_many(long_state, QUESTIONS)
long_s = time.time() - t
long_tokens = out_long[0]["input_tokens"]

hwm = child_hwm_mb(m.proc.pid)
m.close()
print(
    json.dumps(
        {
            "threads": threads,
            "load_s": round(load_s, 1),
            "short_item_s_median": round(sorted(lat)[len(lat) // 2], 2),
            "questions_per_item": len(QUESTIONS),
            "long_state_tokens": long_tokens,
            "long_state_s": round(long_s, 1),
            "scorer_peak_rss_mb": round(hwm) if hwm else None,
            "python_peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
        }
    )
)
for r in results:
    print(json.dumps(r))
