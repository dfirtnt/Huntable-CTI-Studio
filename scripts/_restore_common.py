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
    """
    for line in lines:
        upper = line.upper()
        if skip_db_lifecycle and any(cmd in upper for cmd in _SKIP_DB_LIFECYCLE):
            continue
        if skip_unsupported_sets and any(s in line for s in _SKIP_UNSUPPORTED_SETS):
            continue
        if rewrite_fk_constraints:
            line = rewrite_fk_to_not_valid(line)
        yield line
