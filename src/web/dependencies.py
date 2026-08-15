"""
Shared application-level dependencies for the Huntable CTI Studio web stack.

This module centralizes objects that need to be imported across many
routers such as the logger, environment configuration, template engine,
and expensive singletons like the content filter.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from starlette.requests import Request

from src.database.async_manager import async_db_manager
from src.database.manager import DatabaseManager
from src.utils.content_filter import ContentFilter
from src.web.security.csrf import issue_csrf_token
from src.web.utils.jinja_filters import highlight_keywords, strftime_filter


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a synchronous SQLAlchemy session.

    Route handlers take ``session: Session = Depends(get_db_session)`` instead of
    constructing ``DatabaseManager()`` by hand, so session lifecycle (rollback on
    error, close on completion) lives in one place rather than in every endpoint's
    try/finally. ``DatabaseManager`` caches engines per connection string, so
    per-request instantiation does not open a new pool.
    """
    session = DatabaseManager().get_session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def get_async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async SQLAlchemy session.

    Async counterpart to :func:`get_db_session`, backed by the ``async_db_manager``
    singleton whose context manager already handles rollback and close.
    """
    async with async_db_manager.get_session() as session:
        yield session


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Session context manager for work that outlives the request.

    Background tasks and thread-pool workers cannot use ``Depends(get_db_session)``:
    that session is closed as soon as the response is returned. They use this instead,
    so route modules still never import ``src.database`` directly.
    """
    session = DatabaseManager().get_session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Configure logging once for the web layer
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cti_scraper.web")

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEFAULT_SOURCE_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0"


def _csrf_context(request: Request) -> dict[str, str]:
    """Inject a per-request CSRF token into every rendered template.

    Empty string when CSRF is inactive (e.g. local AUTH_MODE=disabled), so the
    base template/fetch shim becomes a no-op without special-casing.
    """
    cfg = getattr(request.app.state, "security_config", None)
    if cfg is None or not cfg.csrf_active or not cfg.secret_key:
        return {"csrf_token": ""}
    identity = getattr(request.state, "identity", None)
    subject = identity.user_id if identity and getattr(identity, "user_id", None) else "anonymous"
    return {"csrf_token": issue_csrf_token(cfg.secret_key, subject)}


_STATIC_ROOT = Path("src/web/static")


def asset_url(path: str) -> str:
    """Return ``/static/<path>`` with a cache-busting token derived from file mtime.

    Templates previously hardcoded tokens like ``?v=20260729``. Those only invalidate a
    browser cache when a human remembers to edit the date, and static responses carry no
    Cache-Control header -- so a shipped JS fix kept being served from cache and looked
    like it had not worked at all. Deriving the token from mtime makes the URL change
    whenever the file does, and never otherwise.
    """
    relative = path.lstrip("/")
    if relative.startswith("static/"):
        relative = relative[len("static/") :]
    try:
        stamp = int((_STATIC_ROOT / relative).stat().st_mtime)
    except OSError:
        # A missing asset is the template's problem, not this helper's: emit the plain
        # URL so the 404 surfaces normally instead of being masked by an exception.
        return f"/static/{relative}"
    return f"/static/{relative}?v={stamp}"


# Template environment with custom filters
templates = Jinja2Templates(directory="src/web/templates", context_processors=[_csrf_context])
templates.env.filters["highlight_keywords"] = highlight_keywords
templates.env.filters["strftime"] = strftime_filter
templates.env.globals["asset_url"] = asset_url


@lru_cache(maxsize=1)
def get_content_filter() -> ContentFilter:
    """Return a lazily loaded singleton ContentFilter instance."""
    content_filter = ContentFilter()
    if not content_filter.model:
        content_filter.load_model()
    return content_filter


__all__ = [
    "ENVIRONMENT",
    "DEFAULT_SOURCE_USER_AGENT",
    "logger",
    "templates",
    "get_content_filter",
    "get_db_session",
    "get_async_db_session",
    "session_scope",
]
