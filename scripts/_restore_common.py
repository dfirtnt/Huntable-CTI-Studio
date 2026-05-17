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

Why deduplicate PRIMARY KEY constraints?
========================================
If a migration added an explicit ``ALTER TABLE ADD CONSTRAINT ... PRIMARY KEY``
to a table that already had one declared inline, the dump can contain two
``ADD CONSTRAINT ... PRIMARY KEY`` blocks for the same table.  PostgreSQL
rejects the second with "multiple primary keys are not allowed".  We track
constraint names and silently discard any duplicate PK definition together with
its preceding ``ALTER TABLE`` line.
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

# Matches a single-line "ADD CONSTRAINT <name> PRIMARY KEY ..." statement.
# Captures the constraint name so we can detect duplicates.
_PK_CONSTRAINT_RE = re.compile(
    r"^\s*ADD CONSTRAINT\s+(\S+)\s+PRIMARY KEY\b",
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
    deduplicate_pk_constraints: bool = True,
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
        deduplicate_pk_constraints: Suppress duplicate
            ``ALTER TABLE ... ADD CONSTRAINT ... PRIMARY KEY`` blocks.
            ``pg_dump`` can emit two such blocks for the same table when a
            migration added an explicit PK to a table that already had one
            defined inline; PostgreSQL rejects the second with "multiple
            primary keys are not allowed".
    """
    seen_pk_constraints: set[str] = set()
    # Buffer for the "ALTER TABLE [ONLY] …" line that immediately precedes an
    # "ADD CONSTRAINT" line.  We hold it back so we can discard it together
    # with a duplicate PK line without having already flushed it to the output.
    pending_alter_table: str | None = None

    def _flush_pending() -> Iterator[str]:
        nonlocal pending_alter_table
        if pending_alter_table is not None:
            line = rewrite_fk_to_not_valid(pending_alter_table) if rewrite_fk_constraints else pending_alter_table
            pending_alter_table = None
            yield line

    for line in lines:
        upper = line.upper()
        if skip_db_lifecycle and any(cmd in upper for cmd in _SKIP_DB_LIFECYCLE):
            yield from _flush_pending()
            continue
        if skip_unsupported_sets and any(s in line for s in _SKIP_UNSUPPORTED_SETS):
            yield from _flush_pending()
            continue

        if deduplicate_pk_constraints:
            # Buffer ALTER TABLE lines so we can drop them alongside a
            # duplicate PK ADD CONSTRAINT on the very next line.
            if line.startswith("ALTER TABLE"):
                yield from _flush_pending()
                pending_alter_table = line
                continue

            pk_match = _PK_CONSTRAINT_RE.match(line)
            if pk_match:
                constraint_name = pk_match.group(1)
                if constraint_name in seen_pk_constraints:
                    # Duplicate: discard the buffered ALTER TABLE and this line.
                    pending_alter_table = None
                    continue
                seen_pk_constraints.add(constraint_name)

        yield from _flush_pending()

        if rewrite_fk_constraints:
            line = rewrite_fk_to_not_valid(line)
        yield line

    yield from _flush_pending()
