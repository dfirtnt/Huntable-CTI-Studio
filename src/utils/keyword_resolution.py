from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from src.utils.content import ThreatHuntingScorer


@dataclass(frozen=True)
class KeywordCategoryMeta:
    key: str
    metadata_key: str
    display_name: str
    panel_title: str
    dimension: str
    precedence: int
    icon: str
    points_label: str
    card_classes: str
    heading_classes: str
    badge_classes: str
    chip_classes: str
    legend_classes: str
    highlight_classes: str
    print_background: str
    print_color: str
    print_border: str


@dataclass(frozen=True)
class RawKeywordMatch:
    start: int
    end: int
    keyword: str
    category: str


@dataclass(frozen=True)
class ResolvedKeywordMatch:
    text: str
    start: int
    end: int
    category: str
    source_categories: tuple[str, ...]
    occurrence_counts: dict[str, int]

    @property
    def title(self) -> str:
        winner = KEYWORD_CATEGORY_METADATA[self.category].display_name
        if len(self.source_categories) == 1:
            return f"Category: {winner}"
        contributors = ", ".join(KEYWORD_CATEGORY_METADATA[name].display_name for name in self.source_categories)
        return f"Category: {winner} | Highest-priority match among: {contributors}"


@dataclass(frozen=True)
class ResolvedKeywordPanelItem:
    text: str
    title: str
    category: str
    source_categories: tuple[str, ...]
    occurrence_counts: dict[str, int]


PARTIAL_MATCH_KEYWORDS = {
    "hunting",
    "detection",
    "monitor",
    "alert",
    "executable",
    "parent-child",
    "defender query",
    ".exe",
}
WILDCARD_KEYWORDS = {"spawn"}


KEYWORD_CATEGORIES: tuple[KeywordCategoryMeta, ...] = (
    KeywordCategoryMeta(
        key="perfect",
        metadata_key="perfect_keyword_matches",
        display_name="Perfect",
        panel_title="Perfect Discriminators",
        dimension="signal_strength",
        precedence=0,
        icon="✅",
        points_label="75 pts",
        card_classes="bg-green-100 dark:bg-green-800 border border-green-300 dark:border-green-600",
        heading_classes="text-green-800 dark:text-green-200",
        badge_classes="text-white bg-emerald-600 dark:bg-emerald-600",
        chip_classes="bg-green-100 dark:bg-green-800 text-green-800 dark:text-green-200 border border-green-200 dark:border-green-600",
        legend_classes="bg-green-100 dark:bg-green-900 border border-green-300 dark:border-green-700",
        highlight_classes="bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 border-green-300 dark:border-green-700",
        print_background="#dcfce7",
        print_color="#166534",
        print_border="#16a34a",
    ),
    KeywordCategoryMeta(
        key="good",
        metadata_key="good_keyword_matches",
        display_name="Good",
        panel_title="Good Discriminators",
        dimension="signal_strength",
        precedence=1,
        icon="🟣",
        points_label="5 pts",
        card_classes="bg-purple-100 dark:bg-purple-800 border border-purple-300 dark:border-purple-600",
        heading_classes="text-purple-800 dark:text-purple-200",
        badge_classes="text-white bg-purple-600 dark:bg-purple-600",
        chip_classes="bg-purple-100 dark:bg-purple-800 text-purple-800 dark:text-purple-200 border border-purple-200 dark:border-purple-600",
        legend_classes="bg-purple-100 dark:bg-purple-900 border border-purple-300 dark:border-purple-700",
        highlight_classes="bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 border-purple-300 dark:border-purple-700",
        print_background="#f3e8ff",
        print_color="#6b21a8",
        print_border="#9333ea",
    ),
    KeywordCategoryMeta(
        key="lolbas",
        metadata_key="lolbas_matches",
        display_name="LOLBAS",
        panel_title="LOLBAS Executables",
        dimension="technique",
        precedence=2,
        icon="🔧",
        points_label="10 pts",
        card_classes="bg-blue-100 dark:bg-blue-800 border border-blue-300 dark:border-blue-600",
        heading_classes="text-blue-800 dark:text-blue-200",
        badge_classes="text-white bg-blue-600 dark:bg-blue-600",
        chip_classes="bg-blue-100 dark:bg-blue-800 text-blue-800 dark:text-blue-200 border border-blue-200 dark:border-blue-600",
        legend_classes="bg-blue-100 dark:bg-blue-900 border border-blue-300 dark:border-blue-700",
        highlight_classes="bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 border-blue-300 dark:border-blue-700",
        print_background="#dbeafe",
        print_color="#1d4ed8",
        print_border="#2563eb",
    ),
    KeywordCategoryMeta(
        key="intelligence",
        metadata_key="intelligence_matches",
        display_name="Intelligence",
        panel_title="Intelligence Indicators",
        dimension="context",
        precedence=3,
        icon="🎯",
        points_label="10 pts",
        card_classes="bg-orange-100 dark:bg-orange-900 border border-orange-300 dark:border-orange-700",
        heading_classes="text-orange-800 dark:text-orange-200",
        badge_classes="text-white bg-orange-600 dark:bg-orange-600",
        chip_classes="bg-orange-200 dark:bg-orange-950 text-orange-900 dark:text-orange-300 border border-orange-400 dark:border-orange-800",
        legend_classes="bg-orange-200 dark:bg-orange-950 border border-orange-400 dark:border-orange-800",
        highlight_classes="bg-orange-200 dark:bg-orange-950 text-orange-900 dark:text-orange-300 border-orange-400 dark:border-orange-800",
        print_background="#fed7aa",
        print_color="#9a3412",
        print_border="#ea580c",
    ),
    KeywordCategoryMeta(
        key="negative",
        metadata_key="negative_matches",
        display_name="Negative",
        panel_title="Negative Indicators",
        dimension="polarity",
        precedence=4,
        icon="⚠️",
        points_label="-10 pts",
        card_classes="bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600",
        heading_classes="text-gray-800 dark:text-gray-200",
        badge_classes="text-white bg-gray-600 dark:bg-gray-600",
        chip_classes="bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-600",
        legend_classes="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600",
        highlight_classes="bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 border-gray-300 dark:border-gray-600",
        print_background="#f3f4f6",
        print_color="#374151",
        print_border="#9ca3af",
    ),
)

KEYWORD_CATEGORY_METADATA = {item.key: item for item in KEYWORD_CATEGORIES}
METADATA_KEY_TO_CATEGORY = {item.metadata_key: item.key for item in KEYWORD_CATEGORIES}


def _compile_keyword_pattern(keyword: str) -> re.Pattern[str] | None:
    try:
        normalized = keyword.lower()
        if normalized in PARTIAL_MATCH_KEYWORDS:
            return re.compile(re.escape(keyword), re.IGNORECASE)
        if normalized in WILDCARD_KEYWORDS:
            return re.compile(re.escape(keyword) + r"\w*", re.IGNORECASE)

        pattern_str = ThreatHuntingScorer._build_keyword_pattern(keyword)
        if pattern_str.startswith("\\b"):
            pattern_str = pattern_str.replace("\\b", r"(?<![a-zA-Z])", 1)
        if pattern_str.endswith("\\b"):
            pattern_str = pattern_str[:-2] + r"(?![a-zA-Z])"
        pattern_str = pattern_str.replace("\\b", r"(?![a-zA-Z])")
        return re.compile(pattern_str, re.IGNORECASE)
    except re.error:
        return None


def collect_raw_keyword_matches(content: str, metadata: dict[str, Any] | None) -> list[RawKeywordMatch]:
    if not content or not metadata:
        return []

    raw_matches: list[RawKeywordMatch] = []
    for category_meta in KEYWORD_CATEGORIES:
        for keyword in metadata.get(category_meta.metadata_key, []) or []:
            pattern = _compile_keyword_pattern(str(keyword))
            if not pattern:
                continue
            for match in pattern.finditer(content):
                raw_matches.append(
                    RawKeywordMatch(
                        start=match.start(),
                        end=match.end(),
                        keyword=str(keyword),
                        category=category_meta.key,
                    )
                )
    raw_matches.sort(key=lambda item: (item.start, item.end, item.keyword.lower(), item.category))
    return raw_matches


def _winner(match: RawKeywordMatch) -> tuple[int, int, int, str]:
    return (
        KEYWORD_CATEGORY_METADATA[match.category].precedence,
        -(match.end - match.start),
        match.start,
        match.keyword.lower(),
    )


def resolve_keyword_matches(content: str, metadata: dict[str, Any] | None) -> list[ResolvedKeywordMatch]:
    raw_matches = collect_raw_keyword_matches(content, metadata)
    if not raw_matches:
        return []

    resolved_matches: list[ResolvedKeywordMatch] = []
    cluster: list[RawKeywordMatch] = []
    cluster_end = -1

    def flush_cluster() -> None:
        nonlocal cluster
        if not cluster:
            return

        boundaries = sorted({match.start for match in cluster} | {match.end for match in cluster})
        segments: list[ResolvedKeywordMatch] = []

        for left, right in zip(boundaries, boundaries[1:]):
            active = [match for match in cluster if match.start < right and match.end > left]
            if not active:
                continue

            winning_match = min(active, key=_winner)
            category_counts = Counter(match.category for match in active)
            source_categories = tuple(
                sorted(category_counts.keys(), key=lambda name: KEYWORD_CATEGORY_METADATA[name].precedence)
            )
            segments.append(
                ResolvedKeywordMatch(
                    text=content[left:right],
                    start=left,
                    end=right,
                    category=winning_match.category,
                    source_categories=source_categories,
                    occurrence_counts=dict(sorted(category_counts.items())),
                )
            )

        for segment in segments:
            if (
                resolved_matches
                and resolved_matches[-1].end == segment.start
                and resolved_matches[-1].category == segment.category
            ):
                previous = resolved_matches[-1]
                merged_sources = tuple(
                    sorted(
                        set(previous.source_categories) | set(segment.source_categories),
                        key=lambda name: KEYWORD_CATEGORY_METADATA[name].precedence,
                    )
                )
                merged_counts = Counter(previous.occurrence_counts)
                merged_counts.update(segment.occurrence_counts)
                resolved_matches[-1] = ResolvedKeywordMatch(
                    text=previous.text + segment.text,
                    start=previous.start,
                    end=segment.end,
                    category=previous.category,
                    source_categories=merged_sources,
                    occurrence_counts=dict(sorted(merged_counts.items())),
                )
            else:
                resolved_matches.append(segment)

        cluster = []

    for raw_match in raw_matches:
        if not cluster:
            cluster = [raw_match]
            cluster_end = raw_match.end
            continue
        if raw_match.start < cluster_end:
            cluster.append(raw_match)
            cluster_end = max(cluster_end, raw_match.end)
            continue
        flush_cluster()
        cluster = [raw_match]
        cluster_end = raw_match.end

    flush_cluster()
    return resolved_matches


def render_highlighted_content(content: str, resolved_matches: list[ResolvedKeywordMatch]) -> str:
    if not content:
        return ""
    if not resolved_matches:
        return html.escape(content)

    rendered: list[str] = []
    cursor = 0
    for match in resolved_matches:
        rendered.append(html.escape(content[cursor : match.start]))
        category_meta = KEYWORD_CATEGORY_METADATA[match.category]
        rendered.append(
            '<span class="keyword-highlight keyword-highlight--{category} px-1 py-0.5 rounded text-xs '
            'font-medium border {classes}" data-keyword-category="{category}" '
            'data-source-categories="{sources}" title="{title}">{text}</span>'.format(
                category=category_meta.key,
                classes=category_meta.highlight_classes,
                sources=",".join(match.source_categories),
                title=html.escape(match.title, quote=True),
                text=html.escape(content[match.start : match.end]),
            )
        )
        cursor = match.end

    rendered.append(html.escape(content[cursor:]))
    return "".join(rendered)


def build_keyword_resolution_context(content: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
    resolved_matches = resolve_keyword_matches(content, metadata)

    panel_items_by_category: dict[str, list[ResolvedKeywordPanelItem]] = {meta.key: [] for meta in KEYWORD_CATEGORIES}
    panel_index: dict[tuple[str, str], int] = {}

    for match in resolved_matches:
        item_text = match.text.strip()
        if not item_text:
            continue
        dedupe_key = (match.category, item_text.lower())
        category_items = panel_items_by_category[match.category]
        if dedupe_key not in panel_index:
            panel_index[dedupe_key] = len(category_items)
            category_items.append(
                ResolvedKeywordPanelItem(
                    text=item_text,
                    title=match.title,
                    category=match.category,
                    source_categories=match.source_categories,
                    occurrence_counts=dict(match.occurrence_counts),
                )
            )
            continue

        index = panel_index[dedupe_key]
        existing = category_items[index]
        merged_sources = tuple(
            sorted(
                set(existing.source_categories) | set(match.source_categories),
                key=lambda name: KEYWORD_CATEGORY_METADATA[name].precedence,
            )
        )
        counts = Counter(existing.occurrence_counts)
        counts.update(match.occurrence_counts)
        category_items[index] = ResolvedKeywordPanelItem(
            text=existing.text,
            title=ResolvedKeywordMatch(
                text=existing.text,
                start=0,
                end=0,
                category=existing.category,
                source_categories=merged_sources,
                occurrence_counts=dict(sorted(counts.items())),
            ).title,
            category=existing.category,
            source_categories=merged_sources,
            occurrence_counts=dict(sorted(counts.items())),
        )

    panel_groups = [
        {
            "key": meta.key,
            "title": meta.panel_title,
            "display_name": meta.display_name,
            "dimension": meta.dimension,
            "icon": meta.icon,
            "points_label": meta.points_label,
            "card_classes": meta.card_classes,
            "heading_classes": meta.heading_classes,
            "badge_classes": meta.badge_classes,
            "chip_classes": meta.chip_classes,
            "items": panel_items_by_category[meta.key],
        }
        for meta in KEYWORD_CATEGORIES
    ]
    automatic_legends = [
        {
            "key": meta.key,
            "label": meta.display_name,
            "classes": meta.legend_classes,
            "title": f"Automatic keyword category: {meta.display_name}",
        }
        for meta in KEYWORD_CATEGORIES
    ]

    return {
        "matches": resolved_matches,
        "panel_groups": panel_groups,
        "automatic_legends": automatic_legends,
        "category_metadata": KEYWORD_CATEGORY_METADATA,
    }


__all__ = [
    "KEYWORD_CATEGORIES",
    "KEYWORD_CATEGORY_METADATA",
    "KeywordCategoryMeta",
    "ResolvedKeywordMatch",
    "ResolvedKeywordPanelItem",
    "build_keyword_resolution_context",
    "render_highlighted_content",
    "resolve_keyword_matches",
]
