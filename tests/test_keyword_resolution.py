from __future__ import annotations

import pytest

from src.utils.keyword_resolution import (
    KEYWORD_CATEGORY_METADATA,
    build_keyword_resolution_context,
    render_highlighted_content,
    resolve_keyword_matches,
)

pytestmark = pytest.mark.unit


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


def test_compound_lolbas_executable_is_not_fragmented_by_exe_good_match() -> None:
    content = "The actor launched cmd.exe from AppData."
    metadata = {
        "perfect_keyword_matches": [],
        "good_keyword_matches": [".exe"],
        "lolbas_matches": ["cmd.exe"],
        "intelligence_matches": [],
        "negative_matches": [],
    }

    context = build_keyword_resolution_context(content, metadata)
    resolved = context["matches"]
    panel_groups = {group["key"]: group["items"] for group in context["panel_groups"]}

    assert [(match.text, match.category) for match in resolved] == [("cmd.exe", "lolbas")]
    assert [item.text for item in panel_groups["lolbas"]] == ["cmd.exe"]
    assert panel_groups["good"] == []
    assert "More-specific match among: Good, LOLBAS" in panel_groups["lolbas"][0].title


def test_perfect_discriminator_supersedes_overlapping_keyword_matches() -> None:
    content = "The actor launched cmd.exe from AppData."
    metadata = {
        "perfect_keyword_matches": ["cmd.exe"],
        "good_keyword_matches": [".exe"],
        "lolbas_matches": ["cmd.exe"],
        "intelligence_matches": [],
        "negative_matches": [],
    }

    resolved = resolve_keyword_matches(content, metadata)

    assert [(match.text, match.category) for match in resolved] == [("cmd.exe", "perfect")]
    assert resolved[0].source_categories == ("perfect", "good", "lolbas")
    assert "Highest-priority match among: Perfect, Good, LOLBAS" in resolved[0].title


def _only_highlight_spans(rendered: str) -> list[str]:
    """Extract just the highlighted text runs, in document order."""
    import re

    return re.findall(r'<span class="keyword-highlight[^"]*"[^>]*>([^<]*)</span>', rendered)


def test_partial_keyword_highlight_covers_the_whole_word_not_a_mid_word_fragment() -> None:
    """Regression for the "detection"/"detections" split: a PARTIAL_MATCH_KEYWORDS
    entry matches a substring by design (for scoring), but the *rendered* highlight
    must cover the whole surrounding word so the highlight never begins or ends
    inside an alphanumeric run."""
    content = "We observed detections of malware on the host."
    metadata = {
        "perfect_keyword_matches": [],
        "good_keyword_matches": ["detection"],
        "lolbas_matches": [],
        "intelligence_matches": [],
        "negative_matches": [],
    }

    resolved = resolve_keyword_matches(content, metadata)
    # The underlying match -- what the Keyword Matches panel counts and displays --
    # is unchanged: the narrow "detection" substring, not the whole word.
    assert [match.text for match in resolved] == ["detection"]

    rendered = render_highlighted_content(content, resolved)
    assert _only_highlight_spans(rendered) == ["detections"]
    assert rendered.count("<span") == 1


def test_defanged_ip_highlight_stays_one_continuous_token() -> None:
    """Regression for `45.153.34[.]132` rendering as three fragments when only
    the `[.]` defang marker matched."""
    content = "Traffic to 45.153.34[.]132 was logged by the sensor."
    metadata = {
        "perfect_keyword_matches": [],
        "good_keyword_matches": ["[.]"],
        "lolbas_matches": [],
        "intelligence_matches": [],
        "negative_matches": [],
    }

    resolved = resolve_keyword_matches(content, metadata)
    assert [match.text for match in resolved] == ["[.]"]

    rendered = render_highlighted_content(content, resolved)
    assert _only_highlight_spans(rendered) == ["45.153.34[.]132"]


def test_two_distinct_matches_in_one_hyphenated_token_render_as_a_single_span() -> None:
    """Regression for "command-and-con" / "trol"-style splits: two *separate*
    keyword matches ("command" and "control") landing in the same hyphenated
    compound must not each independently truncate at their own raw boundary --
    they merge into one combined highlight covering the whole compound."""
    content = "Observed command-and-control traffic on the network."
    metadata = {
        "perfect_keyword_matches": [],
        "good_keyword_matches": ["command", "control"],
        "lolbas_matches": [],
        "intelligence_matches": [],
        "negative_matches": [],
    }

    resolved = resolve_keyword_matches(content, metadata)
    # Panel data still shows two distinct matches -- merging is a render-only concern.
    assert [match.text for match in resolved] == ["command", "control"]

    rendered = render_highlighted_content(content, resolved)
    assert _only_highlight_spans(rendered) == ["command-and-control"]


def test_highlight_span_does_not_swallow_unrelated_punctuation_past_the_word() -> None:
    """Expansion must stop at real token boundaries (quotes, angle brackets,
    "="), not run through arbitrary non-whitespace text."""
    content = '<b class="x">already</b> wrapped'
    metadata = {
        "perfect_keyword_matches": [],
        "good_keyword_matches": ["already"],
        "lolbas_matches": [],
        "intelligence_matches": [],
        "negative_matches": [],
    }

    resolved = resolve_keyword_matches(content, metadata)
    rendered = render_highlighted_content(content, resolved)
    assert _only_highlight_spans(rendered) == ["already"]
