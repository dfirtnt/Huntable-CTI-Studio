from __future__ import annotations

from src.utils.keyword_resolution import (
    KEYWORD_CATEGORY_METADATA,
    build_keyword_resolution_context,
    render_highlighted_content,
    resolve_keyword_matches,
)


def test_overlap_resolves_to_higher_priority_category() -> None:
    content = "powershell.exe launched from temp."
    metadata = {
        "perfect_keyword_matches": ["powershell.exe"],
        "good_keyword_matches": [],
        "lolbas_matches": ["powershell.exe"],
        "intelligence_matches": [],
        "negative_matches": [],
    }

    resolved = resolve_keyword_matches(content, metadata)

    assert len(resolved) == 1
    assert resolved[0].text == "powershell.exe"
    assert resolved[0].category == "perfect"
    assert resolved[0].source_categories == ("perfect", "lolbas")
    assert resolved[0].occurrence_counts == {"lolbas": 1, "perfect": 1}


def test_intelligence_uses_canonical_orange_styles() -> None:
    meta = KEYWORD_CATEGORY_METADATA["intelligence"]

    assert "bg-orange-200" in meta.chip_classes
    assert "bg-orange-200" in meta.highlight_classes
    assert meta.dimension == "context"


def test_adjacent_and_nested_matches_resolve_without_overlap() -> None:
    content = "rundll32.exe javascript:"
    metadata = {
        "perfect_keyword_matches": ["rundll32.exe javascript:"],
        "good_keyword_matches": [],
        "lolbas_matches": ["rundll32.exe"],
        "intelligence_matches": [],
        "negative_matches": [],
    }

    resolved = resolve_keyword_matches(content, metadata)

    assert len(resolved) == 1
    assert resolved[0].text == "rundll32.exe javascript:"
    assert resolved[0].category == "perfect"
    assert resolved[0].source_categories == ("perfect", "lolbas")

    rendered = render_highlighted_content(content, resolved)
    assert rendered.count('<span class="keyword-highlight') == 1
    assert "rundll32.exe javascript:" in rendered


def test_partial_and_wildcard_matching_still_resolve() -> None:
    content = "The actor spawns child processes for threat hunting detection."
    metadata = {
        "perfect_keyword_matches": [],
        "good_keyword_matches": ["spawn", "hunting", "detection"],
        "lolbas_matches": [],
        "intelligence_matches": [],
        "negative_matches": [],
    }

    resolved = resolve_keyword_matches(content, metadata)
    texts = [match.text.lower() for match in resolved]

    assert "spawns" in texts
    assert "hunting" in texts
    assert "detection" in texts


def test_panel_context_dedupes_lower_priority_duplicates() -> None:
    content = "powershell.exe uses cmd.exe while an incident unfolds."
    metadata = {
        "perfect_keyword_matches": ["powershell.exe"],
        "good_keyword_matches": [],
        "lolbas_matches": ["powershell.exe", "cmd.exe"],
        "intelligence_matches": ["incident"],
        "negative_matches": [],
    }

    context = build_keyword_resolution_context(content, metadata)
    panel_groups = {group["key"]: group["items"] for group in context["panel_groups"]}

    assert [item.text for item in panel_groups["perfect"]] == ["powershell.exe"]
    assert [item.text for item in panel_groups["lolbas"]] == ["cmd.exe"]
    assert [item.text for item in panel_groups["intelligence"]] == ["incident"]
    assert "Highest-priority match among: Perfect, LOLBAS" in panel_groups["perfect"][0].title
