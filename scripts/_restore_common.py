"""Shared helpers for the database restore scripts.

Centralises filtering logic so that fixes (e.g. the ``NOT VALID`` rewrite for
foreign key constraints) only need to be applied in one place.

Why ``NOT VALID``?
==================
``pg_dump`` drops constraints up front, ``COPY``s data, then re-adds the
constraints with ``ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY ...``. That
``ADD CONSTRAINT`` synchronously validates every existing row. If the source
database has any dangling references (e.g. a ``sigma_rule_queue`` row pointing
at a pruned ``agentic_workflow_executions`` id) the restore aborts.

Appending ``NOT VALID`` makes Postgres install the constraint without
revalidating existing rows. Subsequent INSERT/UPDATE statements are still
checked, so the schema invariant is preserved going forward; only legacy bad
rows are grandfathered in. They can be cleaned up later with ``DELETE`` plus
``ALTER TABLE ... VALIDATE CONSTRAINT ...``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

# Matches a single-line "ADD CONSTRAINT <name> FOREIGN KEY ..." statement
# anywhere in the file. ``pg_dump`` always emits these on one line, so a
# line-oriented regex is sufficient and keeps the filter streamable.
_FK_CONSTRAINT_RE = re.compile(
    r"^(\s*ADD CONSTRAINT\s+\S+\s+FOREIGN KEY\b.*?)(;\s*)$",
    re.IGNORECASE,
)

# Matches a COPY header line: COPY [schema.]table (col, ...) FROM stdin;
_COPY_START_RE = re.compile(
    r"^COPY\s+(?:\w+\.)?(\w+)\s+\(([^)]+)\)\s+FROM\s+stdin;\s*$",
    re.IGNORECASE,
)

# Matches the end-of-COPY sentinel.
_COPY_END = "\\.\n"

# Matches the "ALTER TABLE [ONLY] [schema.]table" header line emitted by pg_dump
# for multi-line constraint additions.
_ALTER_TABLE_RE = re.compile(
    r"^ALTER TABLE\s+(?:ONLY\s+)?(?:\w+\.)?(\w+)\s*$",
    re.IGNORECASE,
)

# Matches the continuation line "    ADD CONSTRAINT <name> PRIMARY KEY ..."
_ADD_PK_RE = re.compile(
    r"^\s+ADD CONSTRAINT\s+\S+\s+PRIMARY KEY\b",
    re.IGNORECASE,
)

# Statements that must be skipped because the restore harness handles
# DROP/CREATE database itself before the dump is replayed.
_SKIP_DB_LIFECYCLE = ("DROP DATABASE", "CREATE DATABASE", "\\connect", "\\c ")

# Settings emitted by recent pg_dump versions that older psql clients reject.
_SKIP_UNSUPPORTED_SETS = (
    "SET transaction_timeout",
    "SET idle_in_transaction_session_timeout",
)


def rewrite_fk_to_not_valid(line: str) -> str:
    """Append ``NOT VALID`` to single-line FK constraint additions.

    Idempotent: a line that already contains ``NOT VALID`` is returned unchanged.
    Non-matching lines are returned unchanged.
    """
    if "NOT VALID" in line.upper():
        return line
    m = _FK_CONSTRAINT_RE.match(line)
    if not m:
        return line
    return f"{m.group(1)} NOT VALID{m.group(2)}"


def filter_dump_lines(
    lines: Iterable[str],
    *,
    skip_db_lifecycle: bool = False,
    skip_unsupported_sets: bool = False,
    rewrite_fk_constraints: bool = True,
    dedup_primary_keys: bool = True,
    dedup_copy_rows: bool = True,
) -> Iterator[str]:
    """Yield filtered SQL dump lines.

    Args:
        lines: Iterator over raw dump lines (already decompressed).
        skip_db_lifecycle: Drop ``DROP DATABASE`` / ``CREATE DATABASE`` /
            ``\\connect`` / ``\\c`` lines. Set when the harness manages the
            target database itself.
        skip_unsupported_sets: Drop ``SET transaction_timeout`` and friends
            that older psql clients do not understand.
        rewrite_fk_constraints: Append ``NOT VALID`` to FK constraint
            additions so dangling references do not abort the restore.
        dedup_primary_keys: Skip duplicate ``ALTER TABLE ... ADD CONSTRAINT
            ... PRIMARY KEY`` blocks for tables that already had one emitted.
            Prevents "multiple primary keys for table" errors when a backup was
            taken from a DB where a migration accidentally defined the PK twice.
        dedup_copy_rows: Within each COPY block, drop rows whose ``id`` column
            value has already been emitted for that table.  Prevents
            ``could not create unique index`` errors when the source DB had
            duplicate PK values (e.g. because the PK constraint was temporarily
            absent during a migration).  Keeps the first occurrence of each id.
    """
    # State for primary-key deduplication.  pg_dump always emits the ALTER TABLE
    # header and ADD CONSTRAINT body on adjacent lines with no blank line between
    # them, so a two-line look-ahead is sufficient.
    tables_with_pk: set[str] = set()
    pending_alter_table: str | None = None   # table name being buffered
    pending_alter_line: str | None = None    # the actual ALTER TABLE line text

    # State for COPY-row deduplication.
    in_copy: bool = False
    copy_id_col: int | None = None          # 0-based index of the "id" column
    copy_seen_ids: set[str] = set()         # id values emitted so far for this COPY block

    for line in lines:
        # --- primary-key dedup state machine ---
        if dedup_primary_keys:
            alter_m = _ALTER_TABLE_RE.match(line)
            if alter_m:
                # Flush any previously buffered ALTER TABLE that was NOT followed
                # by an ADD CONSTRAINT PRIMARY KEY (i.e. it's for a different
                # kind of constraint — emit it now).
                if pending_alter_line is not None:
                    pending_alter_line = _apply_line_filters(
                        pending_alter_line,
                        skip_db_lifecycle,
                        skip_unsupported_sets,
                        rewrite_fk_constraints,
                    )
                    if pending_alter_line is not None:
                        yield pending_alter_line
                pending_alter_table = alter_m.group(1).lower()
                pending_alter_line = line
                continue  # hold this line until we see what follows

            if pending_alter_table is not None:
                if _ADD_PK_RE.match(line):
                    table = pending_alter_table
                    saved_alter_line = pending_alter_line
                    pending_alter_table = None
                    pending_alter_line = None
                    if table in tables_with_pk:
                        # Drop both the ALTER TABLE header and this ADD CONSTRAINT line.
                        continue
                    tables_with_pk.add(table)
                    # Emit the buffered ALTER TABLE line, then fall through to emit this line.
                    yield saved_alter_line  # type: ignore[arg-type]
                    # Fall through to emit the current ADD CONSTRAINT line below.
                else:
                    # Not a PRIMARY KEY constraint -- flush the buffer and continue normally.
                    buffered = pending_alter_line
                    pending_alter_table = None
                    pending_alter_line = None
                    buffered = _apply_line_filters(
                        buffered,  # type: ignore[arg-type]
                        skip_db_lifecycle,
                        skip_unsupported_sets,
                        rewrite_fk_constraints,
                    )
                    if buffered is not None:
                        yield buffered
                    # Fall through to process the current line normally.

        # --- COPY-row dedup state machine ---
        if dedup_copy_rows:
            if not in_copy:
                copy_m = _COPY_START_RE.match(line)
                if copy_m:
                    in_copy = True
                    cols = [c.strip() for c in copy_m.group(2).split(",")]
                    copy_id_col = cols.index("id") if "id" in cols else None
                    copy_seen_ids = set()
                    yield line
                    continue
            else:
                # Inside a COPY block.
                if line == _COPY_END or line.rstrip("\n") == "\\.":
                    in_copy = False
                    copy_id_col = None
                    copy_seen_ids = set()
                    yield line
                    continue
                if copy_id_col is not None:
                    fields = line.split("\t")
                    if len(fields) > copy_id_col:
                        row_id = fields[copy_id_col]
                        if row_id in copy_seen_ids:
                            continue  # duplicate row -- drop it
                        copy_seen_ids.add(row_id)
                yield line
                continue

        # --- standard filters ---
        filtered = _apply_line_filters(line, skip_db_lifecycle, skip_unsupported_sets, rewrite_fk_constraints)
        if filtered is not None:
            yield filtered

    # Flush any trailing buffered ALTER TABLE line (edge case: last statement in dump).
    if dedup_primary_keys and pending_alter_line is not None:
        filtered = _apply_line_filters(
            pending_alter_line,
            skip_db_lifecycle,
            skip_unsupported_sets,
            rewrite_fk_constraints,
        )
        if filtered is not None:
            yield filtered


def _apply_line_filters(
    line: str,
    skip_db_lifecycle: bool,
    skip_unsupported_sets: bool,
    rewrite_fk_constraints: bool,
) -> str | None:
    """Apply the standard per-line filters; return None if the line should be dropped."""
    upper = line.upper()
    if skip_db_lifecycle and any(cmd in upper for cmd in _SKIP_DB_LIFECYCLE):
        return None
    if skip_unsupported_sets and any(s in line for s in _SKIP_UNSUPPORTED_SETS):
        return None
    if rewrite_fk_constraints:
        line = rewrite_fk_to_not_valid(line)
    return line
