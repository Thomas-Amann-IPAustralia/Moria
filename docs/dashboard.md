# The dashboard

A web page for exploring what Moria found: the review queue, every candidate, the series behind them over time, how
the ranking works, the statistics explained, and the sources and limits. It is in `dashboard/` and is published by
GitHub Pages. Built at the owner's request (D-030).

## Opening it

Once GitHub Pages is switched on (below), the dashboard is at
**https://thomas-amann-ipaustralia.github.io/Moria/dashboard/**, and Moria's visual index (the repository's front
page) links to it. It is designed for a desktop or laptop browser.

To run it on your own computer instead, from the repository: `python3 -m http.server 8000`, then open
http://localhost:8000/dashboard/. (Opening `dashboard/index.html` straight from disk doesn't work: browsers block a
page from reading its own data files that way.)

### Switching on GitHub Pages (once)

1. On GitHub, open the repository, then **Settings**, then **Pages** (under "Code and automation").
2. Under **Build and deployment**, set **Source** to **Deploy from a branch**.
3. Choose the branch **main** and the folder **/ (root)**, and **Save**.
4. After a minute or two the page above answers. The `.nojekyll` file at the root tells GitHub to serve the files
   as they are.

Until this branch is merged into `main`, you can preview it by choosing this branch instead of `main` in step 3.

## Three ways to look

| Mode | What you see | Where its data comes from |
|---|---|---|
| **Public** (the default) | Counts only: how many candidates of each kind, where they came from, their flags, the queue's make-up, score distributions, the evaluations, the sources and settings | `dashboard/data/public.json` in the repo: aggregates only, like `reports/` |
| **Private** ("Open the Doors") | Everything: each candidate's name, chart, numbers, evidence (titles and links), dossier and the decision model's suggestions | Your private file, read by your browser only |
| **Practice** | Everything, but invented: Middle-earth signals that show how the private views work | `dashboard/data/practice.json` in the repo |

### Opening the Doors (your private file)

The private file holds labels, titles and links, so it lives only in the private bucket, never in the repo.

1. Sign in to Cloudflare and open **R2**, then the bucket **moria**.
2. Open `interpretation/dashboard/`, then the newest `as_of=…` folder, and download `dashboard.json.gz`.
3. On the dashboard, press **Open the Doors** (or drop the file on the page, or type *mellon*).

Or, from a terminal: `uv run moria dashboard --out ~/moria-dashboard.json.gz --store r2` (the command refuses a path
inside the repository, except under the git-ignored `data/`).

**What happens to it.** The file is read by the browser tab and nothing else. The page cannot send it anywhere: its
content security policy allows no connections except to the dashboard's own site, and it loads no third-party
scripts, fonts or trackers (everything it uses is in `dashboard/assets/`). The file is not saved in the browser;
closing the tab forgets it. Text from sources (titles, labels) is shown as text, never run as code, and links open
only if they are plain web addresses.

## The levels

Each level starts simple and lets you go deeper; every dotted term or small "?" explains itself, and hovering a
number (a p-value, a percentile, a z-score) explains what that particular value means.

1. **Start here** (the West-gate): what Moria is, the journey of a signal from 44 sources down to the queue, the four
   kinds of candidate, the three rings, the scans so far, and the Doors.
2. **The review queue** (mithril): the 40 for review; with the Doors open, a card each, and a drawer with everything
   about it: the evidence drawn, the detectors' numbers, the alternative explanations checked, the documents, why it
   ranked where it did, the decision model's suggestions and its history.
3. **All candidates** (the deep delvings): where every candidate came from and went, the flags by type, the detectors,
   the score distributions; with the Doors open, a map of every candidate and a searchable table.
4. **Change over time** (the Mirrormere): overlay up to eight series; switch on the trend lines and their uncertainty,
   the expected band, accelerations, change points and surge windows; view them as published, indexed to 100, or as
   Moria tested them.
5. **How ranking works** (the forge): how a score is built; with the Doors open (or practice data), a what-if that
   re-runs Moria's ranking in your browser under your own settings and shows which candidates come and go. It first
   checks itself: at Moria's settings it must pick exactly Moria's shortlist and queue, in order.
6. **Statistics explained** (lore of the delvers): playgrounds with made-up data that run Moria's own tests: a trend
   playground, why testing thousands of series wakes false alarms (Holm against Benjamini-Hochberg, with the real
   scan's p-values), and when a small count is a surge.
7. **Sources and limits** (the Chamber of Mazarbul): what to keep in mind, the sources, why so many weak signals are
   flagged, collection day by day, how Moria has been tested, and the audit trail.
8. **Glossary** (runes decoded).

## How the data is made

`uv run moria dashboard [--as-of D] [--out PATH] --store r2` (`src/moria/dashboard.py`) reads the scan's and the
review's outputs once and writes:

- the **private bundle** to `interpretation/dashboard/as_of=<D>/dashboard.json.gz` in the bucket (and to `--out`);
- the **public bundle** to `dashboard/data/public.json`: aggregates only, the same rule as `reports/` (a test checks
  it holds no candidate ids, labels, titles or links);
- the **practice bundle** to `dashboard/data/practice.json` (`src/moria/dashboard_practice.py`): invented series run
  through the real detectors, and every invented candidate through the real ranking and selection.

`uv run moria dashboard --practice-only` rebuilds the practice bundle from the public one, with no store.

The dashboard never changes anything Moria computed. Values are copied from the stages' outputs. Two things the
outputs don't store are recomputed with the detectors' own code and checked against the stored numbers: each trend
line's intercept (so its line can be drawn) and each anomaly's expected band. On the scan of 15 October 2026 all
6,980 trend lines matched. The forge's what-if is a line-for-line port of `rank.select` and the scoring; the tests run
it (with Node) and require it to reproduce the queue exactly.

The weekly `prepare` workflow runs `moria dashboard` after the review, so a fresh private bundle is in the bucket each
week. The public page's counts change when a build session commits `dashboard/data/` (as it commits `reports/`).

## What the dashboard can't tell you

- It shows Moria's candidates; it doesn't make them findings. No person has reviewed them yet.
- The decision model's suggestions are shown, but they failed their check and don't affect the ranking.
- Series charts show what Moria tested: counts as shares of their source's volume, statistics as published. Nothing
  is forecast; every line stays inside the data.
- The public page's counts are as fresh as the last commit of `dashboard/data/`.
