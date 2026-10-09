"""A small, runnable picture of Moria's core mining step: embed texts, cluster them, find look-alikes and outliers.

The 28 headlines are made up for illustration (docs/mining-explained.md walks through the output). Runs on a laptop
CPU, a GitHub Actions runner, or a Kaggle/Colab notebook:

    pip install fastembed scikit-learn
    python scripts/demo_embed_cluster.py
"""

import numpy as np
from fastembed import TextEmbedding
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score

HEADLINES = [
    # four made-up themes of six headlines each ...
    "AI tools draft patent applications in minutes",
    "Court rules an AI system cannot be named as an inventor",
    "Artists sue AI developers over training on their work",
    "IP office trials machine learning to classify trade marks",
    "Generative AI floods prior-art databases with synthetic disclosures",
    "AI start-ups rely on trade secrets rather than patents",
    "Number of Australians aged over 85 set to double",
    "Aged care workforce shortage worsens in regional towns",
    "Wearable sensors detect falls in elderly patients",
    "Health spending climbs as the population ages",
    "Dementia research funding increases",
    "Debate over the retirement age returns",
    "Sodium-ion battery costs fall below lithium-ion",
    "Grid-scale storage projects approved in South Australia",
    "Green hydrogen export plans delayed by costs",
    "Rooftop solar output breaks a record",
    "Critical minerals processing plant opens in Western Australia",
    "Electric vehicle sales overtake hybrids",
    "Fake trade mark renewal invoices target small businesses",
    "Counterfeit goods seized at the border hit a record",
    "Online marketplaces remove infringing listings",
    "Phishing emails impersonate a government agency",
    "Customs warns of counterfeit medicines",
    "Scam losses reported by small businesses rise",
    # ... and four that fit none of them well
    "UN members debate who can own resources mined on the Moon",
    "Quantum computer breaks a widely used encryption scheme in a lab test",
    "Coral bred to tolerate hotter seas",
    "Indigenous rangers record traditional fire knowledge in a database",
]

model = TextEmbedding("BAAI/bge-small-en-v1.5")
vectors = np.array(list(model.embed(HEADLINES)))  # one row of 384 numbers per headline
vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
print(f"Step 1, embed: {len(HEADLINES)} headlines -> a {vectors.shape[0]} x {vectors.shape[1]} table of numbers\n")

# Step 2, cluster: try several k and keep the one whose groups are most clearly separated (highest silhouette).
scores = {}
for k in range(3, 8):
    labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(vectors)
    scores[k] = silhouette_score(vectors, labels, metric="cosine")
best_k = max(scores, key=scores.get)
print(
    "Step 2, cluster: silhouette by k (higher = better separated):",
    ", ".join(f"k={k}: {s:.3f}" for k, s in scores.items()),
    f"-> k={best_k}\n",
)
km = KMeans(n_clusters=best_k, n_init=10, random_state=0).fit(vectors)

# Step 3, name each cluster by the words that are common in it but rare elsewhere (class-based TF-IDF).
joined = [" ".join(h for h, c in zip(HEADLINES, km.labels_) if c == i) for i in range(best_k)]
tfidf = TfidfVectorizer(stop_words="english").fit(joined)
words = np.array(tfidf.get_feature_names_out())
weights = tfidf.transform(joined).toarray()
print("Step 3, name the clusters:")
for i in range(best_k):
    members = [h for h, c in zip(HEADLINES, km.labels_) if c == i]
    print(f"  cluster {i} [{', '.join(words[np.argsort(-weights[i])[:4]])}] ({len(members)} items)")
    for h in members:
        print(f"      - {h}")

# Step 4, novelty: how far each headline sits from its cluster's centre. The farthest are candidate weak signals.
centres = km.cluster_centers_ / np.linalg.norm(km.cluster_centers_, axis=1, keepdims=True)
distance = 1 - (vectors * centres[km.labels_]).sum(axis=1)
print("\nStep 4, novelty: the five headlines farthest from their cluster's centre")
for i in np.argsort(-distance)[:5]:
    print(f"  {distance[i]:.3f}  {HEADLINES[i]}")

# Step 5, look-alikes: the nearest neighbours of one headline (how dossiers find analogues and duplicates).
q = HEADLINES.index("Fake trade mark renewal invoices target small businesses")
sims = vectors @ vectors[q]
print(f"\nStep 5, look-alikes for: {HEADLINES[q]!r}")
for i in np.argsort(-sims)[1:4]:
    print(f"  {sims[i]:.3f}  {HEADLINES[i]}")
