"""LangGraph checkpoint persistence for the agentic workflow.

The workflow is executed by Celery workers, which means an in-memory saver is
useless: the state has to survive process death so a crashed run can resume and
so a run can be inspected step by step after the fact. This module owns the
Postgres-backed saver and the thread-id convention.

Design notes
------------
* Off by default. Checkpointing writes every step's state to Postgres, which is
  a meaningful write amplification for a pipeline that already checkpoints its
  own progress in ``agentic_workflow_executions``. Operators turn it on with
  ``LANGGRAPH_CHECKPOINT_ENABLED=1``.
* Fail-open at the call site. If the saver cannot be built (package missing,
  database unreachable) the workflow still runs without persistence rather than
  refusing to process an article. Degrading observability must never stop
  detection work.
* ``thread_id`` is derived from the execution row, so the same execution always
  maps to the same checkpoint thread. That is what makes resume and time-travel
  inspection land on the right history.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)

_CHECKPOINT_ENV = "LANGGRAPH_CHECKPOINT_ENABLED"
_TRUTHY = {"1", "true", "yes", "on", "enabled"}


def checkpoint_thread_id(execution_id: int | str) -> str:
    """Return the LangGraph ``thread_id`` for a workflow execution."""
    return f"workflow_exec_{execution_id}"


def checkpointing_enabled() -> bool:
    """Return True when Postgres checkpointing has been switched on."""
    return os.getenv(_CHECKPOINT_ENV, "").strip().lower() in _TRUTHY


def psycopg_dsn(raw: str | None = None) -> str | None:
    """Convert the application's SQLAlchemy URL into a psycopg v3 DSN.

    ``DATABASE_URL`` carries the SQLAlchemy dialect prefix
    (``postgresql+asyncpg://`` or ``postgresql+psycopg2://``), which psycopg
    cannot parse. LangGraph's Postgres saver needs a plain libpq DSN.
    """
    url = (raw if raw is not None else os.getenv("DATABASE_URL", "")).strip()
    if not url:
        return None
    url = re.sub(r"^postgresql\+[a-z0-9_]+://", "postgresql://", url)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[Any | None]:
    """Yield an ``AsyncPostgresSaver``, or ``None`` when checkpointing is off.

    The saver's schema is created on first use (``setup()`` is idempotent), so a
    fresh database needs no manual migration step.
    """
    if not checkpointing_enabled():
        yield None
        return

    dsn = psycopg_dsn()
    if not dsn:
        logger.warning(
            "LangGraph checkpointing is enabled but DATABASE_URL is not set; running without checkpoints."
        )
        yield None
        return

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError as exc:  # pragma: no cover - dependency guard
        logger.warning(
            "LangGraph checkpointing is enabled but langgraph-checkpoint-postgres/psycopg "
            "are not installed (%s); running without checkpoints.",
            exc,
        )
        yield None
        return

    try:
        async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
            await saver.setup()
            logger.info("LangGraph checkpointing active (Postgres).")
            yield saver
    except Exception as exc:  # pragma: no cover - infrastructure guard
        logger.warning("Could not initialise the LangGraph checkpointer (%s); running without checkpoints.", exc)
        yield None
