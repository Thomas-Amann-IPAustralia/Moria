# How Moria's data mining works, in plain terms

For the owner, who asked how the process works (2026-10-09). The example output below is real: it was produced by
`scripts/demo_embed_cluster.py` from 28 made-up headlines, on this session's CPU. You can run the same script on a
laptop, on Kaggle or on Colab.

## The short version

1. **Collect** lots of short public texts (headlines, abstracts, patent titles, legislation, reports), each with its
   date and source.
2. **Embed** each text: turn it into a list of 384 numbers, so that texts about similar things get similar numbers.
3. **Cluster** the numbers into groups of similar texts. These are the themes.
4. **Watch the themes over time and across sources.** This is where the signals are: a theme growing unusually fast;
   a brand-new theme; a theme suddenly showing up in a new kind of source; two themes starting to overlap; items that
   fit no theme at all.
5. **Check, then show you the best candidates**, each with its evidence. You decide what is real and what matters.

Steps 2 and 3 are what you guessed: an embedding, then clustering with k-means or similar. The strategic value comes
from step 4, the change over time and across sources, and from step 5, your judgement.

## Step by step, with the demo

### 1. Embedding: text becomes numbers

The embedding model (`bge-small-en-v1.5`, free, from Hugging Face) reads each headline and outputs 384 numbers. You
never look at the numbers. What matters is that headlines with similar meaning end up close together, even when they
share no words. *"Counterfeit goods seized at the border"* and *"Online marketplaces remove infringing listings"*
land near each other.

> Step 1, embed: 28 headlines → a 28 × 384 table of numbers

### 2. Clustering: group the nearby points (k-means)

k-means needs you to choose *k*, the number of groups. So Moria tries several values and scores each one by how
cleanly the groups separate (the silhouette score):

> silhouette by k: k=3: 0.138, k=4: 0.148, **k=5: 0.167**, k=6: 0.148, k=7: 0.153 → k=5

### 3. Naming the clusters

Each cluster is labelled with the words that are common inside it but rare elsewhere. No AI writing is needed.

| Cluster | Its words | What landed in it |
|---|---|---|
| 1 | ai, trade, artists, applications | All 6 AI-and-IP headlines, **plus** "Quantum computer breaks a widely used encryption scheme" |
| 2 | counterfeit, businesses, small, agency | All 6 scam and counterfeit headlines: a clean cluster |
| 3 | aged, 85, age, ages | 5 of the 6 ageing headlines |
| 4 | costs, ion, delayed, battery | 4 of the 6 energy headlines |
| 0 | australia, approved, bred, coral | **A grab-bag:** 2 energy headlines, 1 ageing headline, and the 3 odd ones out (Moon mining rights, heat-tolerant coral, Indigenous fire knowledge) |

**What went right:** the four made-up themes mostly came back, with no help.

**What went wrong, and why it matters:** k-means forces every item into some cluster, so the odd ones out ended up in
a grab-bag with a meaningless label. The scores are also low, because 28 short headlines is tiny. Real collections
have hundreds of items per theme. Moria handles this in three ways:
- it runs HDBSCAN beside k-means, which may leave odd items *unclustered* instead of forcing them in;
- it keeps a cluster only if it reappears across several random restarts (stability);
- it treats "doesn't fit anywhere" as a signal in its own right (next step).

### 4. Novelty: what fits nowhere

Distance from the cluster's centre measures how badly an item fits its group. The five worst fits:

| Distance | Headline |
|---|---|
| 0.286 | Wearable sensors detect falls in elderly patients |
| 0.274 | UN members debate who can own resources mined on the Moon |
| 0.262 | Coral bred to tolerate hotter seas |
| 0.249 | Quantum computer breaks a widely used encryption scheme in a lab test |
| 0.230 | Indigenous rangers record traditional fire knowledge in a database |

**All four planted odd ones out are in the top five.** This is the raw material of weak signals. One weak fit is
noise. Several weak fits that resemble *each other*, or that keep appearing week after week, is a candidate.

### 5. Look-alikes: nearest neighbours

For any item, Moria can list its nearest neighbours. These are what fills each dossier with related evidence, finds
historical analogues, and spots duplicate stories.

> Look-alikes for "Fake trade mark renewal invoices target small businesses": "Scam losses reported by small
> businesses rise" (0.751), "Online marketplaces remove infringing listings" (0.661), "Customs warns of counterfeit
> medicines" (0.657)

## Where the signals come from: time and sources

Clustering one pile of text tells you *what is there*. Signals come from comparing piles: this quarter against last,
Australia against the world, news against research against legislation.

This table is made up, to show the shape:

| Theme | Share of items, a year ago | Share, last quarter | What Moria would flag |
|---|---|---|---|
| Scams targeting IP owners | 0.4% | 1.6% | A **surge from a low base** (four times as large) |
| AI and inventorship | 2.0% | 2.6% | A **trend**, if it holds over 2 of 3 windows |
| A theme seen only in research a year ago, now also in consultations and news | — | — | **Cross-source spread**: often the earliest sign that something is moving from labs to policy |
| Two separate themes whose items start mentioning each other | — | — | A **new combination** |

Some of the biggest signals need no text at all. For example: counts of patents in every technology class, research
papers in every topic, and ABS statistics, for Australia against the world. A class that is growing fast globally but
flat in Australia is a signal too.

Before any of this reaches you, Moria checks for false alarms:
- did one source just publish more of everything?
- did a collection job fail or double-count?
- is it one story repeated 200 times?
- is it a news flurry with no substance behind it?

## Why Kaggle (or Colab)

You **can** run the embedding model on Kaggle, and the plan does exactly that for the big one-off job:
- **The backfill:** embedding two or three years of items at once. A free Kaggle or Colab GPU does that much faster
  than a normal computer, and can also run larger, more accurate embedding models.
- **Weekly new items** are few enough to embed on the free GitHub Actions computer, which runs on a schedule by
  itself. That's the one thing Kaggle and Colab can't do: their free notebooks need someone to start them, with the
  browser open.

What can't run on the free Kaggle or Colab GPUs is **Matilda**: it is about 25 times larger than these embedding
models. The free TPUs can't be used either, because the tools we use don't support them.

## Why your 200 labels, and what they look like

The machine tags every item automatically: what it's about, which ring it's in, and which of your territories it
touches. Those tags drive the counts, so we need to know **how often the tags are right**. The only way to know is to
compare them against a person's answers on a sample. Your labels do two jobs:
1. **Teach:** about half train a simple classifier on top of the embeddings.
2. **Check:** the other half measure how often each free tagger agrees with you.

You get a short report, for example "theme tags right 80% of the time (between 72% and 87%)". You then choose which
tagger to keep.

### What you'd see

A spreadsheet (or, if you prefer, a phone-friendly page with one item per screen and tap-to-answer). Each row is one
real item from the collection: the source and date, the title, and the first couple of lines, with a link. The rows
below are made up, to show the format:

| # | Source · date | Item (title and first lines) | 1. Mainly about | 2. Ring | 3. Your territories | 4. Usable? |
|---|---|---|---|---|---|---|
| 17 | News title · 2026-08 | *Fake renewal invoices target trade mark owners* | Legal | IP system | (none, or T2…) | yes |
| 18 | Research abstract · 2026-07 | *A sodium-ion cell chemistry reaching 80% of lithium-ion energy density at a third of the cost…* | Technological | Adjacent | T4 | yes |
| 19 | ABS release · 2026-09 | *Population projections: the number of people aged 85+ is projected to…* | Social | Wider world | (none) | yes |
| 20 | News title · 2026-09 | *Click here to win a free cruise* | — | — | — | junk |

**The answers are menus, not writing:**
1. **Mainly about:** Political, Economic, Social, Technological, Legal or Environmental. Pick one, and optionally a
   second.
2. **Ring:** IP system; adjacent (economy, technology, international); or wider world.
3. **Your territories:** none, one or several of your five.
4. **Usable?** yes, or junk (broken text, an advert, a duplicate, not English).

### How the 200 are picked, and how long it takes

- **About 150 at random, spread across source types** (news, research, patents, government, reports), so every type
  is tested.
- **About 50 that the automatic tagger is least sure about.** These teach it the most.
- **About 10 repeats,** hidden in the set. Because you're the only labeller, there's no second person to compare
  with. Checking how consistently you answer the same item twice tells us how much any score can be trusted.
- **Time:** about 30 seconds an item, so about 1.5 to 2 hours in total. It can be split into four sittings of about
  25 minutes.
- **When:** after day 3 of the sprint, once real items are collected and embedded.

## What you review after that

Because it's just you, review has two stages, so your time goes where it matters:
1. **Triage:** up to 40 candidates, about 1 to 2 minutes each. You see a one-line summary, a small chart and three
   examples, and choose keep, park or reject.
2. **Deep review:** the 8 to 10 you kept, about 15 to 20 minutes each. You read the dossier, consider the
   alternative explanations, and record whether it's real and what pathway it has.

That is about 3 to 4 hours a round.
