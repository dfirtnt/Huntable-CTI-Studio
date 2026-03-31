"""
Reusable Jinja filter functions for the Huntable CTI Studio web UI.

Separated from the main application module to simplify imports and
keep template-specific helpers in a dedicated location.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.utils.keyword_resolution import (
    ResolvedKeywordMatch,
    render_highlighted_content,
    resolve_keyword_matches,
)

logger = logging.getLogger(__name__)


def highlight_keywords(content: str, metadata: dict[str, Any] | list[ResolvedKeywordMatch] | None) -> str:
    """
    Highlight discriminator keywords in article content.

    Args:
        content: Article content text.
        metadata: Article metadata containing keyword matches.

    Returns:
        HTML content with highlighted keywords.
    """
    if not content:
        return content

    if metadata is None:
        return content

    # Sort keywords by length (longest first) to avoid partial replacements
    # Check if content is already highlighted (contains HTML spans)
    if "<span class=" in content:
        logger.warning("Content already contains HTML spans, skipping keyword highlighting to avoid nested spans")
        return content

    resolved_matches = metadata if isinstance(metadata, list) else resolve_keyword_matches(content, metadata)
    return render_highlighted_content(content, resolved_matches)


def strftime_filter(value: datetime | None, format_string: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a datetime object using strftime."""
    if value is None:
        return "N/A"
    try:
        return value.strftime(format_string)
    except (AttributeError, ValueError):
        return str(value)
