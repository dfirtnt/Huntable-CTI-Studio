"""
Shared application-level dependencies for the Huntable CTI Studio web stack.

This module centralizes objects that need to be imported across many
routers such as the logger, environment configuration, template engine,
and expensive singletons like the content filter.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from src.utils.content_filter import ContentFilter
from src.web.security.csrf import issue_csrf_token
from src.web.utils.jinja_filters import highlight_keywords, strftime_filter

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


# Template environment with custom filters
templates = Jinja2Templates(directory="src/web/templates", context_processors=[_csrf_context])
templates.env.filters["highlight_keywords"] = highlight_keywords
templates.env.filters["strftime"] = strftime_filter


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
]
