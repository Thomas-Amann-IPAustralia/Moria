"""The `moria` command line. Every command writes a manifest; a failure exits with code 2 and a one-line cause."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import typer

from .collectors import ADAPTERS, Window, run_collection
from .collectors.gdelt import GdeltParams, build_groups
from .config import config_hash, load_config, load_sources, load_territories, load_themes
from .envcheck import run_checks
from .http import PoliteClient
from .store import open_store

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)


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


@app.command()
def terms() -> None:
    """Print the GDELT query groups built from the territories and the broad themes."""
    card = next(c for c in load_sources().values() if c.adapter == "gdelt")
    groups = build_groups(GdeltParams.model_validate(card.params))
    for g in groups:
        typer.echo(f"{g.group_id:<28} {g.expression}")
    typer.echo(f"{len(groups)} groups")


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


def _collect(source_ids: list[str], day: date, limit: int | None, store_backend: str | None) -> list:
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
            r = run_collection(cards[sid], store, client, window, limit=limit, config_hash=chash)
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
) -> None:
    """Collect one source for one UTC day into the raw store."""
    results = _collect([source], _parse_day(day), limit, store)
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


@app.command()
def adapters() -> None:
    """List the collector adapters."""
    for name in sorted(ADAPTERS):
        typer.echo(name)


if __name__ == "__main__":
    app()
