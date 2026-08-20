"""
Reusable Jinja filter functions for the Huntable CTI Studio web UI.

Separated from the main application module to simplify imports and
keep template-specific helpers in a dedicated location.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.utils.keyword_resolution import (
    ResolvedKeywordMatch,
    render_highlighted_content,
    resolve_keyword_matches,
)


def highlight_keywords(content: str, metadata: dict[str, Any] | list[ResolvedKeywordMatch] | None) -> str:
    """
    Highlight discriminator keywords in article content.

    Args:
        content: Article content text.
        metadata: Article metadata containing keyword matches.

    Returns:
        HTML-escaped content with highlighted keywords.

    Security:
        Callers render this through Jinja's ``|safe``, so every return path must
        already be escaped. All escaping happens in ``render_highlighted_content``,
        which escapes each non-match segment and emits only its own generated
        markup. Never add an early return that hands back raw ``content``.
    """
    if not content:
        return ""

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
