"""
Read-only database loader for exporting raw CTI text into Workshop/data/raw.

- Reuses project DB configuration via src.cli.context.CLIContext (DATABASE_URL).
- Forces read-only connections (PostgreSQL: default_transaction_read_only=on).
- Never creates tables or writes back to the database.
- Outputs one JSON file per record: Workshop/data/raw/<id>.json
"""

import json
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Reuse existing config source
 # --- ensure project root is on PYTHONPATH ---
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]   # CTIScraper project root
sys.path.insert(0, str(ROOT))
# --------------------------------------------

from src.cli.context import CLIContext

WORKSHOP_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = WORKSHOP_ROOT / "data" / "raw"


def _coerce_sync_url(database_url: str) -> str:
    """Convert asyncpg URLs to sync driver for SQLAlchemy."""
    return database_url.replace("+asyncpg", "")


def _read_only_args(database_url: str):
    """Add read-only options when supported (PostgreSQL)."""
    if database_url.startswith("postgresql"):
        return {"options": "-c default_transaction_read_only=on"}
    return {}


def get_database_url() -> str:
    """Get database URL using existing CLI context defaults."""
    ctx = CLIContext()
    return ctx.database_url


def build_engine(database_url: Optional[str] = None, echo: bool = False) -> Engine:
    """Create a read-only SQLAlchemy engine without creating tables."""
    url = _coerce_sync_url(database_url or get_database_url())
    connect_args = _read_only_args(url)
    return create_engine(url, future=True, echo=echo, connect_args=connect_args)


def export_raw(
    table_name: str,
    text_field: str = "content",
    id_field: str = "id",
    ref_field: Optional[str] = None,
    limit: Optional[int] = None,
    chunk_size: int = 500,
    database_url: Optional[str] = None,
) -> int:
    """
    Export text rows to JSON files in RAW_DIR.

    Args:
        table_name: Source table or view.
        text_field: Column containing text content.
        id_field: Primary identifier column.
        ref_field: Optional article_id/chunk_id column to preserve.
        limit: Optional row cap.
        chunk_size: Fetch size for streaming.
        database_url: Override DB URL (defaults to CLIContext).
    Returns:
        Number of records exported.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    engine = build_engine(database_url, echo=False)
    columns = [id_field, text_field] + ([ref_field] if ref_field else [])
    select_clause = ", ".join(columns)
    limit_clause = " LIMIT :limit" if limit else ""
    stmt = text(f"SELECT {select_clause} FROM {table_name}{limit_clause}")

    exported = 0
    with engine.connect().execution_options(stream_results=True) as conn:
        params = {"limit": limit} if limit else {}
        result = conn.execution_options(yield_per=chunk_size).execute(stmt, params)
        for row in result:
            m = row._mapping
            row_id = m[id_field]
            data = {
                "id": row_id,
                "text": m[text_field],
            }
            if ref_field and ref_field in m:
                data[ref_field] = m[ref_field]

            out_path = RAW_DIR / f"{row_id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            exported += 1
    return exported


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Export raw text rows from the CTIScraper database into Workshop/data/raw (read-only)."
    )
    parser.add_argument("--table", required=True, help="Table or view to read from")
    parser.add_argument("--text-field", default="content", help="Column containing text/content")
    parser.add_argument("--id-field", default="id", help="Primary ID column")
    parser.add_argument(
        "--ref-field",
        default=None,
        help="Optional article_id or chunk_id column to include in output",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL (defaults to src.cli.context.CLIContext)",
    )

    args = parser.parse_args()
    count = export_raw(
        table_name=args.table,
        text_field=args.text_field,
        id_field=args.id_field,
        ref_field=args.ref_field,
        limit=args.limit,
        database_url=args.database_url,
    )
    print(f"Exported {count} records to {RAW_DIR}")


if __name__ == "__main__":
    main()
