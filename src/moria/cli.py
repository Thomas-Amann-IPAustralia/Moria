"""The `moria` command line. Every command writes a manifest; a failure exits with code 2 and a one-line cause."""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer

from .census import census_markdown
from .collectors import ADAPTERS, Window, run_collection
from .collectors.gdelt import GdeltParams, build_groups
from .collectors.gkg import GkgParams
from .config import (
    config_hash,
    load_baseline,
    load_codebook,
    load_config,
    load_features,
    load_sources,
    load_territories,
    load_themes,
)
from .discover import discover as discover_urls
from .envcheck import run_checks
from .http import PoliteClient
from .ipr import refresh as ipr_refresh
from .stages import LAKE_STAGES
from .store import open_store
from .terms import check as terms_check

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)
ipr_app = typer.Typer(no_args_is_help=True, help="IP RAPID: the weekly bulk release, into the lake as Parquet")
app.add_typer(ipr_app, name="ipr")
features_app = typer.Typer(
    no_args_is_help=True, help="The feature stages: embeddings, de-duplication, keyphrases, BM25"
)
app.add_typer(features_app, name="features")
terms_app = typer.Typer(invoke_without_command=True, help="The news query groups, and the check of every search term")
app.add_typer(terms_app, name="terms")


@app.callback()
def main(quiet: bool = typer.Option(False, "--quiet", "-q", help="Log warnings and errors only, not each request")):
    """Progress goes to stderr as timestamped (UTC) log lines: one per HTTP attempt, per retry wait and per source."""
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%SZ")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    root = logging.getLogger("moria")
    root.handlers[:] = [handler]
    root.setLevel(logging.WARNING if quiet else logging.INFO)
    root.propagate = False


def _yesterday() -> date:
    return datetime.now(UTC).date() - timedelta(days=1)


def _parse_day(value: str | None) -> date:
    if not value:
        return _yesterday()
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise typer.BadParameter(f"--day must be YYYY-MM-DD, got {value!r}") from e


@app.command()
def sources() -> None:
    """List the source cards."""
    for card in load_sources().values():
        typer.echo(f"{card.id:<22} {card.adapter:<12} {card.cadence:<8} {','.join(card.rings):<28} {card.name}")


@terms_app.callback()
def terms(ctx: typer.Context) -> None:
    """Print the GDELT query groups built from the territories and the broad themes."""
    if ctx.invoked_subcommand:
        return
    card = next(c for c in load_sources().values() if c.adapter in ("gdelt", "gdelt_gkg"))
    groups = build_groups((GkgParams if card.adapter == "gdelt_gkg" else GdeltParams).model_validate(card.params))
    for g in groups:
        typer.echo(f"{g.group_id:<28} {g.expression}")
    typer.echo(f"{len(groups)} groups")


@terms_app.command("check")
def terms_check_command(
    end: str = typer.Option(None, help="Last day sampled (YYYY-MM-DD); default yesterday (UTC)"),
    weeks: int = typer.Option(13, help="Sample one day a week for this many weeks"),
    samples: int = typer.Option(12, help="Hits kept per term for reading (private store only)"),
    files_per_day: int = typer.Option(None, help="Smoke test: read only this many GKG files a day"),
    report: str = typer.Option("reports/terms-check.md", help="Where to write the public summary (counts only)"),
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
) -> None:
    """Check every territory term and theme phrase against sampled days of GDELT GKG files: volumes worldwide and in
    .au domains, and a private sample of hits to read for noise."""
    cfg, cards = load_config(), load_sources()
    card = next(c for c in cards.values() if c.adapter == "gdelt_gkg")
    territories, themes = load_territories(), load_themes()
    client = PoliteClient(cfg.http)
    try:
        status, mkey, counts = terms_check(
            card,
            territories,
            themes,
            open_store(cfg.store, store),
            client,
            end=_parse_day(end),
            weeks=weeks,
            samples_per_term=samples,
            files_per_day=files_per_day,
            report_path=Path(report) if report else None,
            config_hash=config_hash(cfg, territories, themes, card),
        )
    finally:
        client.close()
    typer.echo(f"{status:<7} terms check  {json.dumps(counts, sort_keys=True)}  manifest={mkey}")
    if status != "passed":
        raise typer.Exit(2)


@app.command("env-check")
def env_check(
    require: str = typer.Option("", help="Comma-separated checks that must pass, e.g. store:r2,api:openalex"),
) -> None:
    """Check which keys are present and make one cheap call to each service. Never prints a key."""
    cfg, cards = load_config(), load_sources()
    client = PoliteClient(cfg.http)
    try:
        checks = run_checks(cfg, cards, client)
    finally:
        client.close()
    for c in checks:
        typer.echo(f"{c.status:<8} {c.name:<28} {c.detail}")
    required = {r.strip() for r in require.split(",") if r.strip()}
    failed = [c.name for c in checks if c.name in required and c.status != "ok"]
    missing = required - {c.name for c in checks}
    if failed or missing:
        typer.echo(f"required checks not ok: {', '.join(sorted(set(failed) | missing))}", err=True)
        raise typer.Exit(2)


@app.command()
def discover(
    urls: Annotated[list[str], typer.Argument(help="Addresses to check, e.g. a news page, a feed or a robots.txt")],
    match: str = typer.Option(None, help="Also list a page's links matching this regular expression"),
) -> None:
    """Check what a new source's addresses answer from here: status, type and size; a feed's or sitemap's item count
    and dates; the feeds a page links. Addresses and counts only, never text. A refusal is an answer, not a failure."""
    # one try per address, and a shorter wait: a site that hangs is an answer too
    client = PoliteClient(load_config().http.model_copy(update={"timeout_s": 30.0, "max_retries": 0}))
    try:
        for line in discover_urls(client, urls, match):
            typer.echo(line)
    finally:
        client.close()


def _collect(
    source_ids: list[str], day: date, limit: int | None, store_backend: str | None, backfill: bool = False
) -> list:
    cfg, cards = load_config(), load_sources()
    unknown = [s for s in source_ids if s not in cards]
    if unknown:
        typer.echo(f"unknown source(s): {', '.join(unknown)}", err=True)
        raise typer.Exit(2)
    store = open_store(cfg.store, store_backend)
    client = PoliteClient(cfg.http)
    window = Window.for_day(day)
    chash = config_hash(cfg, load_territories(), load_themes(), *[cards[s] for s in source_ids])
    results = []
    try:
        for sid in source_ids:
            if cards[sid].adapter in LAKE_STAGES:  # bulk stages write the lake, not a raw bundle
                r = LAKE_STAGES[cards[sid].adapter](cards[sid], store, client, limit=limit, config_hash=chash)
            else:
                r = run_collection(cards[sid], store, client, window, limit=limit, config_hash=chash, backfill=backfill)
            results.append(r)
            line = (
                f"{r.status:<7} {sid:<22} records={r.records:<6} warnings={len(r.warnings):<3} "
                f"manifest={r.manifest_key}"
            )
            typer.echo(line if r.status == "passed" else f"{line}\n        cause: {r.error}")
    finally:
        client.close()
    return results


@app.command()
def collect(
    source: str = typer.Argument(..., help="A source id from `moria sources`"),
    day: str = typer.Option(None, help="UTC day to collect (YYYY-MM-DD); default yesterday"),
    limit: int = typer.Option(None, help="Smoke test: cap the work (query groups, pages or records)"),
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
    backfill: bool = typer.Option(False, help="A first snapshot: every feed item, or every page in a sitemap"),
) -> None:
    """Collect one source for one UTC day into the raw store."""
    results = _collect([source], _parse_day(day), limit, store, backfill)
    if any(r.status != "passed" for r in results):
        raise typer.Exit(2)


@app.command("collect-daily")
def collect_daily(
    day: str = typer.Option(None, help="UTC day to collect (YYYY-MM-DD); default yesterday"),
    limit: int = typer.Option(None, help="Smoke test: cap the work per source"),
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
) -> None:
    """Collect every daily source for one UTC day. Carries on past a failed source, then exits 2 if any failed."""
    daily = [c.id for c in load_sources().values() if c.cadence == "daily"]
    results = _collect(daily, _parse_day(day), limit, store)
    summary = {r.source: {"status": r.status, "records": r.records, "warnings": len(r.warnings)} for r in results}
    typer.echo(json.dumps(summary, sort_keys=True))
    if any(r.status != "passed" for r in results):
        raise typer.Exit(2)


@app.command("collect-weekly")
def collect_weekly(
    day: str = typer.Option(None, help="UTC day the snapshot is filed under (YYYY-MM-DD); default yesterday"),
    limit: int = typer.Option(None, help="Smoke test: cap the work per source"),
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
) -> None:
    """Collect every weekly source: whole-taxonomy counts, statistics and the IP RAPID release. Carries on past a
    failed source, then exits 2 if any failed."""
    weekly = [c.id for c in load_sources().values() if c.cadence == "weekly"]
    results = _collect(weekly, _parse_day(day), limit, store)
    summary = {r.source: {"status": r.status, "records": r.records, "warnings": len(r.warnings)} for r in results}
    typer.echo(json.dumps(summary, sort_keys=True))
    if any(r.status != "passed" for r in results):
        raise typer.Exit(2)


@ipr_app.command("refresh")
def ipr_refresh_command(
    zip_path: str = typer.Option(None, "--zip", help="Use this copy of the current release instead of downloading"),
    work_dir: str = typer.Option(None, help="Keep the converted Parquet here (default: a temporary directory)"),
    limit: int = typer.Option(None, help="Smoke test: convert only the first N tables, locally; uploads nothing"),
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
) -> None:
    """Ingest the current IP RAPID release into the lake (a base, or a delta against the latest base), with
    individuals' names hashed. Does nothing if the release is already in the store."""
    cfg, cards = load_config(), load_sources()
    card = next(c for c in cards.values() if c.adapter == "ip_rapid")
    client = PoliteClient(cfg.http)
    try:
        r = ipr_refresh(
            card,
            open_store(cfg.store, store),
            client,
            zip_path=Path(zip_path) if zip_path else None,
            work_dir=Path(work_dir) if work_dir else None,
            limit=limit,
            config_hash=config_hash(cfg, card),
        )
    finally:
        client.close()
    line = f"{r.status:<7} {card.id:<22} rows={r.records:<10} warnings={len(r.warnings):<3} manifest={r.manifest_key}"
    typer.echo(line if r.status == "passed" else f"{line}\n        cause: {r.error}")
    if r.status != "passed":
        raise typer.Exit(2)


@ipr_app.command("metrics")
def ipr_metrics_command(
    threads: int = typer.Option(4, help="DuckDB threads"),
    memory_limit: str = typer.Option("3GB", help="DuckDB memory limit"),
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
) -> None:
    """Monthly demand, outcome and timeliness series from the latest IP RAPID release, into lake/ipr_metrics (the
    same shapes as lake/series and lake/observations). Organisation, sector and country level only."""
    from .iprmetrics import COMMAND, metrics

    cfg, cards = load_config(), load_sources()
    card = next(c for c in cards.values() if c.adapter == "ip_rapid")
    status, mkey, counts = metrics(open_store(cfg.store, store), card, config_hash(card), threads, memory_limit)
    _stage_line(COMMAND, status, mkey, counts)


@app.command()
def census(
    source: str = typer.Argument(..., help="A source id from `moria sources`"),
    out: str = typer.Option(None, help="Where to write the report; default reports/census/<source>.md"),
    all_runs: bool = typer.Option(False, "--all-runs", help="Combine every collection in the store, not the latest"),
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
) -> None:
    """Profile a source's latest collection (aggregates only, safe for the public repo)."""
    cards = load_sources()
    if source not in cards:
        typer.echo(f"unknown source: {source}", err=True)
        raise typer.Exit(2)
    text = census_markdown(open_store(load_config().store, store), cards[source], all_runs=all_runs)
    path = Path(out or f"reports/census/{source}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    typer.echo(f"wrote {path}")


@app.command()
def baseline() -> None:
    """Print the known-trends baseline (config/baseline.yaml): each trend and the documents it comes from."""
    b = load_baseline()
    for t in b.trends:
        docs = sorted({s.doc + ("*" if s.status == "proposed" else "") for s in t.sources})
        mark = "proposed " if t.status == "proposed" else ""
        typer.echo(f"{t.id}  {mark}{t.name:<52} {','.join(t.pestle):<36} {', '.join(docs)}")
    read = sum(1 for d in b.documents.values() if d.read != "not_read")
    proposed = sum(1 for t in b.trends if t.status == "proposed")
    cites = sum(1 for t in b.trends for s in t.sources if s.status == "proposed" and t.status != "proposed")
    typer.echo(
        f"{len(b.trends)} trends ({b.status}; {proposed} proposed, and {cites} proposed citations of confirmed "
        f"trends, marked *); {read} of {len(b.documents)} documents read"
    )


@app.command()
def normalise(
    source: Annotated[list[str] | None, typer.Argument(help="Only these sources (default: every source)")] = None,
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
) -> None:
    """Normalise the raw store into lake/documents, lake/series and lake/observations, with dates read, first
    sightings, vintages and the security sweep. Sources whose inputs are unchanged are carried over."""
    from .normalise import run as normalise_run
    from .sweep import load_sweep

    cfg, cards, features = load_config(), load_sources(), load_features()
    unknown = [s for s in source or [] if s not in cards]
    if unknown:
        typer.echo(f"unknown source(s): {', '.join(unknown)}", err=True)
        raise typer.Exit(2)
    sweep_cfg = load_sweep()
    chash = config_hash(features, sweep_cfg, *cards.values())
    status, mkey, outcomes = normalise_run(open_store(cfg.store, store), cards, features, sweep_cfg, source, chash)
    for o in outcomes:
        shown = {
            k: v for k, v in sorted(o.counts.items()) if k in ("documents", "series", "observations", "quarantined")
        }
        line = f"{o.status:<9} {o.source:<26} {json.dumps(shown, sort_keys=True)}"
        typer.echo(line if o.status != "failed" else f"{line}\n          cause: {o.error}")
    typer.echo(f"{status:<9} normalise  manifest={mkey}")
    if status != "passed":
        raise typer.Exit(2)


def _stage_line(name: str, status: str, mkey: str, counts: dict) -> None:
    typer.echo(f"{status:<9} {name:<20} {json.dumps(counts, sort_keys=True)}  manifest={mkey}")
    if status != "passed":
        raise typer.Exit(2)


def _features_setup(store: str | None):
    cfg, features = load_config(), load_features()
    return cfg, features, open_store(cfg.store, store), config_hash(features)


def _encoder_factory(cfg, features):
    """The real encoder (bge-small, pinned and hashed); fetched from Hugging Face on first use."""

    def make():
        from .embed import Encoder

        client = PoliteClient(cfg.http.model_copy(update={"timeout_s": 300.0}))
        return Encoder(features.embed, client)

    return make


@features_app.command("embed")
def features_embed(
    source: Annotated[list[str] | None, typer.Argument(help="Only these sources (others are carried over)")] = None,
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
) -> None:
    """Embed every document (title, summary, opening text) with bge-small-en-v1.5; unchanged texts reuse their
    vectors. Needs the `models` extra (uv sync --extra models)."""
    from .features import EMBED, embed

    cfg, features, st, chash = _features_setup(store)
    status, mkey, counts = embed(st, features, _encoder_factory(cfg, features), chash, source)
    _stage_line(EMBED, status, mkey, counts)


@features_app.command("dedup")
def features_dedup(store: str = typer.Option(None, help="local or r2; default from config/moria.yaml")) -> None:
    """De-duplication groups: the same canonical URL, the same news title, or near-identical embeddings between
    outlets, within 30 days."""
    from .features import DEDUP, dedup

    _, features, st, chash = _features_setup(store)
    status, mkey, counts = dedup(st, features, chash)
    _stage_line(DEDUP, status, mkey, counts)


@features_app.command("keyphrases")
def features_keyphrases(store: str = typer.Option(None, help="local or r2; default from config/moria.yaml")) -> None:
    """n-gram keyphrases by TF-IDF per document, and the vocabulary with each phrase's first observable date."""
    from .features import KEYPHRASES, keyphrases

    _, features, st, chash = _features_setup(store)
    status, mkey, counts = keyphrases(st, features, chash)
    _stage_line(KEYPHRASES, status, mkey, counts)


@features_app.command("index")
def features_index(store: str = typer.Option(None, help="local or r2; default from config/moria.yaml")) -> None:
    """The BM25 full-text index (DuckDB fts) over every document."""
    from .features import INDEX, index

    _, features, st, chash = _features_setup(store)
    status, mkey, counts = index(st, features, chash)
    _stage_line(INDEX, status, mkey, counts)


@app.command()
def tag(
    backend: str = typer.Option("zeroshot", help="zeroshot (the only backend until the owner's labels exist)"),
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
) -> None:
    """Descriptive tags per item: ring, domain, PESTLE origin, rights, territories and the nearest known trend, by
    similarity to their descriptions; and the territory and theme terms matched in each item."""
    from .tags import COMMAND
    from .tags import tag as tag_run

    if backend != "zeroshot":
        typer.echo(f"backend {backend!r} is not built: the sklearn backend needs the owner's labels", err=True)
        raise typer.Exit(2)
    cfg, features, st, _ = _features_setup(store)
    codebook, territories, baseline, cards = load_codebook(), load_territories(), load_baseline(), load_sources()
    chash = config_hash(features, codebook, territories, baseline)
    status, mkey, counts = tag_run(st, features, codebook, territories, baseline, cards,
                                   _encoder_factory(cfg, features), chash)  # fmt: skip
    _stage_line(COMMAND, status, mkey, counts)


@app.command()
def search(
    query: str = typer.Argument(..., help="Words to search for (BM25, stemmed)"),
    limit: int = typer.Option(20, help="How many matches"),
    source: str = typer.Option(None, help="Only this source"),
    since: str = typer.Option(None, help="Only items observable from this day (YYYY-MM-DD)"),
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
) -> None:
    """Search every document (BM25) and print the matches' ids, sources, dates and titles. For the analyst's own
    terminal: titles are evidence, so never run this in a scheduled job, whose logs are public."""
    from .features import INDEX
    from .features import search as bm25
    from .tables import cache_root, fetch_outputs, upstream

    cfg = load_config()
    st = open_store(cfg.store, store)
    m = upstream(st, INDEX)
    (db,) = fetch_outputs(st, m, "features/index/", cache_root()).values()
    for score, item, src, day, title in bm25(db, query, limit, source, since):
        typer.echo(f"{score:>7} {day} {src:<24} {item[:12]} {title}")


@app.command()
def prepare(store: str = typer.Option(None, help="local or r2; default from config/moria.yaml")) -> None:
    """The evidence layer's whole chain: normalise, embed, dedup, keyphrases, tag, index and the IP RAPID metrics.
    Stops at the first stage that fails."""
    from .features import DEDUP, EMBED, INDEX, KEYPHRASES, dedup, embed, index, keyphrases
    from .normalise import run as normalise_run
    from .sweep import load_sweep
    from .tags import COMMAND
    from .tags import tag as tag_run

    cfg, cards, features = load_config(), load_sources(), load_features()
    st = open_store(cfg.store, store)
    sweep_cfg = load_sweep()
    status, mkey, outcomes = normalise_run(st, cards, features, sweep_cfg, None,
                                           config_hash(features, sweep_cfg, *cards.values()))  # fmt: skip
    totals = {f"sources_{o.status}": sum(1 for x in outcomes if x.status == o.status) for o in outcomes}
    _stage_line("normalise", status, mkey, totals)
    chash = config_hash(features)
    factory = _encoder_factory(cfg, features)
    _stage_line(EMBED, *embed(st, features, factory, chash))
    _stage_line(DEDUP, *dedup(st, features, chash))
    _stage_line(KEYPHRASES, *keyphrases(st, features, chash))
    codebook, territories, baseline = load_codebook(), load_territories(), load_baseline()
    tag_hash = config_hash(features, codebook, territories, baseline)
    _stage_line(COMMAND, *tag_run(st, features, codebook, territories, baseline, cards, factory, tag_hash))
    _stage_line(INDEX, *index(st, features, chash))
    from .iprmetrics import COMMAND as IPRM
    from .iprmetrics import metrics as ipr_metrics

    ipr_card = next(c for c in cards.values() if c.adapter == "ip_rapid")
    _stage_line(IPRM, *ipr_metrics(st, ipr_card, config_hash(ipr_card)))


@app.command("evidence-report")
def evidence_report_command(
    out: str = typer.Option("reports/evidence-layer.md", help="Where to write the report (aggregates only)"),
    store: str = typer.Option(None, help="local or r2; default from config/moria.yaml"),
) -> None:
    """Profile the evidence layer after `moria prepare`: counts by source, date basis, sweep finding, dedup rule and
    tag. Safe for the public repo: no titles, text, URLs or keyphrases."""
    from .evidence_report import evidence_report

    text = evidence_report(open_store(load_config().store, store))
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    typer.echo(f"wrote {path}")


@app.command()
def adapters() -> None:
    """List the collector adapters."""
    for name in sorted([*ADAPTERS, *LAKE_STAGES]):
        typer.echo(name)


if __name__ == "__main__":
    app()
