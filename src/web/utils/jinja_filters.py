"""
Reusable Jinja filter functions for the CTI Scraper web UI.

Separated from the main application module to simplify imports and
keep template-specific helpers in a dedicated location.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def highlight_keywords(content: str, metadata: Dict[str, Any]) -> str:
    """
    Highlight discriminator keywords in article content.

    Args:
        content: Article content text.
        metadata: Article metadata containing keyword matches.

    Returns:
        HTML content with highlighted keywords.
    """
    if not content or not metadata:
        return content

    # Get all keyword matches
    all_keywords: List[Tuple[str, str, str]] = []
    keyword_types: Dict[str, Tuple[str, str]] = {
        "perfect_keyword_matches": (
            "perfect",
            "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 border-green-300 dark:border-green-700",
        ),
        "good_keyword_matches": (
            "good",
            "bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 border-purple-300 dark:border-purple-700",
        ),
        "lolbas_matches": (
            "lolbas",
            "bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 border-blue-300 dark:border-blue-700",
        ),
        "intelligence_matches": (
            "intelligence",
            "bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200 border-orange-300 dark:border-orange-700",
        ),
        "negative_matches": (
            "negative",
            "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 border-gray-300 dark:border-gray-600",
        ),
    }

    for key, (type_name, css_classes) in keyword_types.items():
        keywords = metadata.get(key, [])
        for keyword in keywords:
            all_keywords.append((keyword, type_name, css_classes))

    if not all_keywords:
        return content

    # Sort keywords by length (longest first) to avoid partial replacements
    all_keywords.sort(key=lambda x: len(x[0]), reverse=True)

    # Check if content is already highlighted (contains HTML spans)
    if "<span class=" in content:
        logger.warning(
            "Content already contains HTML spans, skipping keyword highlighting to avoid nested spans"
        )
        return content

    matches = []
    for keyword, type_name, css_classes in all_keywords:
        escaped_keyword = re.escape(keyword)

        # For certain keywords, allow partial matches (e.g., "hunting" in "threat hunting")
        partial_match_keywords = [
            "hunting",
            "detection",
            "monitor",
            "alert",
            "executable",
            "parent-child",
            "defender query",
            ".exe",
        ]

        # For wildcard keywords, use prefix matching
        wildcard_keywords = ["spawn"]

        try:
            if keyword.lower() in partial_match_keywords:
                pattern = re.compile(escaped_keyword, re.IGNORECASE)
            elif keyword.lower() in wildcard_keywords:
                pattern = re.compile(escaped_keyword + r"\\w*", re.IGNORECASE)
            else:
                pattern = re.compile(r"(?<![a-zA-Z])" + escaped_keyword + r"(?![a-zA-Z])", re.IGNORECASE)

            for match in pattern.finditer(content):
                matches.append(
                    {
                        "start": match.start(),
                        "end": match.end(),
                        "keyword": keyword,
                        "type_name": type_name,
                        "css_classes": css_classes,
                    }
                )
        except re.error as exc:
            logger.warning("Regex error for keyword '%s': %s", keyword, exc)
            continue

    # Sort matches by start position
    matches.sort(key=lambda x: x["start"])

    # Remove overlapping matches (keep the longest one)
    non_overlapping = []
    for match in matches:
        overlaps = False
        for existing in list(non_overlapping):
            if match["start"] < existing["end"] and match["end"] > existing["start"]:
                # Overlap detected - keep the longer match
                if len(match["keyword"]) > len(existing["keyword"]):
                    non_overlapping.remove(existing)
                    non_overlapping.append(match)
                overlaps = True
                break

        if not overlaps:
            non_overlapping.append(match)

    # Sort again by start position
    non_overlapping.sort(key=lambda x: x["start"])

    highlighted_content = content
    for match in reversed(non_overlapping):
        # Use the actual matched text from content, not the keyword from metadata
        matched_text = content[match["start"]:match["end"]]
        highlight_span = (
            '<span class="px-1 py-0.5 rounded text-xs font-medium border '
            f'{match["css_classes"]}" title="{match["type_name"].title()} discriminator: {match["keyword"]}">'
            f'{matched_text}</span>'
        )
        highlighted_content = (
            highlighted_content[: match["start"]]
            + highlight_span
            + highlighted_content[match["end"] :]
        )

    return highlighted_content


def strftime_filter(value: Optional[datetime], format_string: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a datetime object using strftime."""
    if value is None:
        return "N/A"
    try:
        return value.strftime(format_string)
    except (AttributeError, ValueError):
        return str(value)

