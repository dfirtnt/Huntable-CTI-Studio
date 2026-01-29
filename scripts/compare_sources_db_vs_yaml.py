#!/usr/bin/env python3
"""Compare production DB source settings vs config/sources.yaml.

Usage:
  DATABASE_URL=postgresql+asyncpg://... python3 scripts/compare_sources_db_vs_yaml.py
  Or with default (postgres/cti_postgres): python3 scripts/compare_sources_db_vs_yaml.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.source_manager import SourceConfigLoader
from src.database.async_manager import AsyncDatabaseManager


def _source_row(db_source) -> dict:
    """Normalize DB source to comparable row (identifier, name, url, rss_url, check_frequency, lookback_days, active, config keys)."""
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
    """Normalize YAML SourceCreate to comparable row."""
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


async def main():
    config_path = Path(os.getenv("SOURCES_CONFIG", "config/sources.yaml"))
    if not config_path.is_absolute():
        config_path = Path(__file__).resolve().parent.parent / config_path
    if not config_path.exists():
        print(f"ERROR: Config not found: {config_path}")
        sys.exit(1)

    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://cti_user:cti_password@postgres:5432/cti_scraper")
    # Allow localhost for running from host (e.g. port 5432 forwarded)
    if "postgres:" in db_url and "localhost" not in db_url:
        alt = db_url.replace("postgres:", "localhost:")
        if os.getenv("DB_HOST") == "localhost":
            db_url = alt

    loader = SourceConfigLoader()
    yaml_configs = loader.load_from_file(str(config_path))
    yaml_by_id = {c.identifier: _yaml_row(c) for c in yaml_configs}

    db_manager = AsyncDatabaseManager(database_url=db_url)
    try:
        db_sources = await db_manager.list_sources()
    except Exception as e:
        print(f"ERROR: Cannot reach DB / list_sources failed: {e}")
        print("Tip: Use DATABASE_URL; from host use postgres host or localhost if port 5432 is forwarded.")
        await db_manager.close()
        sys.exit(1)

    db_by_id = {s.identifier: _source_row(s) for s in db_sources}

    only_yaml = set(yaml_by_id) - set(db_by_id)
    only_db = set(db_by_id) - set(yaml_by_id)
    common = set(yaml_by_id) & set(db_by_id)

    print("=== DB vs sources.yaml ===\n")
    print(f"YAML: {len(yaml_by_id)} sources  |  DB: {len(db_by_id)} sources\n")

    if only_yaml:
        print("--- Only in YAML (not in DB) ---")
        for sid in sorted(only_yaml):
            r = yaml_by_id[sid]
            print(f"  {sid}: active={r['active']} url={r['url'][:60]}...")
        print()

    if only_db:
        print("--- Only in DB (not in YAML) ---")
        for sid in sorted(only_db):
            r = db_by_id[sid]
            print(f"  {sid}: active={r['active']} url={r['url'][:60]}...")
        print()

    field_diffs = []
    for sid in sorted(common):
        diffs = _diff_fields(db_by_id[sid], yaml_by_id[sid])
        if diffs:
            field_diffs.append((sid, diffs))

    if field_diffs:
        print("--- Field differences (DB → YAML) ---")
        for sid, diffs in field_diffs:
            print(f"  {sid}:")
            for k, v_db, v_yaml in diffs:
                print(f"    {k}: DB={v_db!r}  YAML={v_yaml!r}")
        print()

    if not only_yaml and not only_db and not field_diffs:
        print("No differences: DB and YAML match (identifier set and compared fields).")
    else:
        print("Summary: run ./run_cli.sh sync-sources to overwrite DB with YAML (or --no-remove to keep DB-only sources).")

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
