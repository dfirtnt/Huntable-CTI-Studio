"""CLI command to compare DB source settings vs sources.yaml."""

import asyncio
import os
from pathlib import Path

import click

from src.core.source_manager import SourceConfigLoader
from src.database.async_manager import AsyncDatabaseManager

from ..context import CLIContext


def _source_row(db_source) -> dict:
    cfg = db_source.config if isinstance(db_source.config, dict) else {}
    return {
        "identifier": db_source.identifier,
        "name": db_source.name,
        "url": db_source.url,
        "rss_url": db_source.rss_url or None,
        "check_frequency": db_source.check_frequency,
        "lookback_days": getattr(db_source, "lookback_days", 180),
        "active": db_source.active,
        "min_content_length": cfg.get("min_content_length"),
        "rss_only": cfg.get("rss_only"),
    }


def _yaml_row(cfg) -> dict:
    c = getattr(cfg, "config", None)
    inner = getattr(c, "config", None) if c is not None else {}
    if not isinstance(inner, dict):
        inner = {}
    return {
        "identifier": cfg.identifier,
        "name": cfg.name,
        "url": cfg.url,
        "rss_url": cfg.rss_url or None,
        "check_frequency": getattr(c, "check_frequency", 3600) if c is not None else 3600,
        "lookback_days": getattr(c, "lookback_days", 180) if c is not None else 180,
        "active": cfg.active,
        "min_content_length": inner.get("min_content_length") if isinstance(inner, dict) else None,
        "rss_only": inner.get("rss_only") if isinstance(inner, dict) else None,
    }


def _diff_fields(db_row: dict, yaml_row: dict) -> list:
    diffs = []
    for k in ["name", "url", "rss_url", "check_frequency", "lookback_days", "active", "min_content_length", "rss_only"]:
        if k not in yaml_row:
            continue
        v_db, v_yaml = db_row.get(k), yaml_row.get(k)
        if v_db != v_yaml:
            diffs.append((k, v_db, v_yaml))
    return diffs


pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.command("compare-sources")
@click.option(
    "--config-path", default=None, help="Path to sources YAML (default: SOURCES_CONFIG or config/sources.yaml)"
)
@pass_context
def compare_sources(ctx: CLIContext, config_path: str):
    """Compare production DB source settings vs sources.yaml."""

    async def _run():
        path = config_path or os.getenv("SOURCES_CONFIG", "config/sources.yaml")
        path = Path(path)
        if not path.is_absolute():
            base = Path(__file__).resolve().parent.parent.parent.parent
            path = base / path
        if not path.exists():
            path = Path.cwd() / "config" / "sources.yaml"
        if not path.exists():
            click.echo(f"ERROR: Config not found: {path}", err=True)
            raise SystemExit(1)

        loader = SourceConfigLoader()
        yaml_configs = loader.load_from_file(str(path))
        yaml_by_id = {c.identifier: _yaml_row(c) for c in yaml_configs}

        db_manager = AsyncDatabaseManager(database_url=ctx.database_url)
        try:
            db_sources = await db_manager.list_sources()
        except Exception as e:
            click.echo(f"ERROR: Cannot reach DB: {e}", err=True)
            await db_manager.close()
            raise SystemExit(1) from e

        db_by_id = {s.identifier: _source_row(s) for s in db_sources}

        only_yaml = set(yaml_by_id) - set(db_by_id)
        only_db = set(db_by_id) - set(yaml_by_id)
        common = set(yaml_by_id) & set(db_by_id)

        click.echo("=== DB vs sources.yaml ===\n")
        click.echo(f"YAML: {len(yaml_by_id)} sources  |  DB: {len(db_by_id)} sources\n")

        if only_yaml:
            click.echo("--- Only in YAML (not in DB) ---")
            for sid in sorted(only_yaml):
                r = yaml_by_id[sid]
                url_preview = (r["url"] or "")[:60]
                click.echo(f"  {sid}: active={r['active']} url={url_preview}...")
            click.echo("")

        if only_db:
            click.echo("--- Only in DB (not in YAML) ---")
            for sid in sorted(only_db):
                r = db_by_id[sid]
                url_preview = (r["url"] or "")[:60]
                click.echo(f"  {sid}: active={r['active']} url={url_preview}...")
            click.echo("")

        field_diffs = []
        for sid in sorted(common):
            diffs = _diff_fields(db_by_id[sid], yaml_by_id[sid])
            if diffs:
                field_diffs.append((sid, diffs))

        if field_diffs:
            click.echo("--- Field differences (DB → YAML) ---")
            for sid, diffs in field_diffs:
                click.echo(f"  {sid}:")
                for k, v_db, v_yaml in diffs:
                    click.echo(f"    {k}: DB={v_db!r}  YAML={v_yaml!r}")
            click.echo("")

        if not only_yaml and not only_db and not field_diffs:
            click.echo("No differences: DB and YAML match (identifier set and compared fields).")
        else:
            click.echo(
                "Tip: ./run_cli.sh sync-sources to overwrite DB with YAML (or --no-remove to keep DB-only sources)."
            )

        await db_manager.close()

    asyncio.run(_run())
