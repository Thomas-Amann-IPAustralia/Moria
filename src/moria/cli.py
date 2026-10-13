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
from .config import config_hash, load_baseline, load_config, load_sources, load_territories, load_themes
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
        docs = sorted({s.doc for s in t.sources})
        typer.echo(f"{t.id}  {t.name:<52} {','.join(t.pestle):<36} {', '.join(docs)}")
    read = sum(1 for d in b.documents.values() if d.read != "not_read")
    typer.echo(f"{len(b.trends)} trends ({b.status}); {read} of {len(b.documents)} documents read")


@app.command()
def adapters() -> None:
    """List the collector adapters."""
    for name in sorted([*ADAPTERS, *LAKE_STAGES]):
        typer.echo(name)


if __name__ == "__main__":
    app()
