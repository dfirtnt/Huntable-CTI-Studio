"""Unit tests for proc_tree_attention_preprocessor."""

import pytest

from src.services.proc_tree_attention_preprocessor import process

pytestmark = pytest.mark.unit


def test_empty_article():
    """Empty article returns empty snippets and full_article."""
    result = process("")
    assert result["high_likelihood_snippets"] == []
    assert result["full_article"] == ""

    result = process("   \n\n  ")
    assert result["high_likelihood_snippets"] == []
    assert result["full_article"] == "   \n\n  "


def test_arrow_rendering_unicode_and_ascii():
    """winword.exe -> powershell.exe and unicode arrow both match."""
    for text in [
        "winword.exe \u2192 powershell.exe",
        "winword.exe -> powershell.exe",
    ]:
        result = process(text)
        assert len(result["high_likelihood_snippets"]) >= 1, f"Expected match for: {text}"
        assert result["full_article"] == text


def test_tree_glyph_match_with_indent():
    """Tree glyph with indent matches with +/-2 lines context."""
    lines = [
        "Process tree:",
        "  services.exe",
        "    \u2514\u2500\u2500 powershell.exe -enc x",
        "      some child detail",
        "end of tree",
    ]
    text = "\n".join(lines)
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    snippet = result["high_likelihood_snippets"][0]
    # Should include +/-2 lines context (tree glyph rule)
    assert "powershell.exe" in snippet


def test_lineage_verb_two_tokens():
    """P1: lineage verb binding two tokens matches."""
    text = "WINWORD.EXE spawned powershell.exe"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1, "P1 lineage verb should match"


def test_reverse_lineage_spawned_by():
    """P2: reverse direction 'X was spawned by Y' matches."""
    text = "powershell.exe was spawned by winword.exe"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1, "P2 reverse lineage should match"


def test_parent_child_label_qualified():
    """P3: 'parent process' matches; 'the parent company' does NOT."""
    result_match = process("parent process: services.exe")
    assert len(result_match["high_likelihood_snippets"]) >= 1, "Qualified parent/child should match"

    result_no_match = process("the parent company reported a data breach")
    assert result_no_match["high_likelihood_snippets"] == [], "Unqualified 'parent' should not match"


def test_parent_node_graph_theory_no_match():
    """P3 qualifier guard: 'parent node' and 'child node' do NOT match."""
    for text in [
        "the parent node in the graph has three edges",
        "each child node inherits properties from its parent node",
    ]:
        result = process(text)
        assert result["high_likelihood_snippets"] == [], f"Graph theory term should not match: {text}"


def test_overlap_merge_long_line():
    """Two arrow matches within 2*MATCH_WINDOW_CHARS produce a single merged snippet."""
    # Build a line > 500 chars with two arrow matches close together
    prefix = "X" * 200
    gap = "Y" * 80
    suffix = "Z" * 200
    line = prefix + "winword.exe -> powershell.exe" + gap + "cmd.exe --> explorer.exe" + suffix
    assert len(line) > 500  # must trigger windowed path

    result = process(line)
    snippets = result["high_likelihood_snippets"]
    # Both matches within one merged window -- should be exactly 1 snippet
    assert len(snippets) == 1, f"Expected 1 merged snippet, got {len(snippets)}"


def test_pid_ppid_pair_same_line():
    """T5: PID and PPID pair on same line matches."""
    text = "PID 1234, PPID 5678"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1, "PID/PPID pair should match"


def test_sysmon_parent_image_block():
    """T4: line with both ParentImage and Image matches."""
    text = "ParentImage: services.exe | Image: svchost.exe"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1, "Sysmon ParentImage+Image should match"


def test_injection_into_process_no_match():
    """P5 removed: injection/hollowing patterns no longer anchor on their own."""
    text = "The attacker injected code into lsass.exe"
    result = process(text)
    assert result["high_likelihood_snippets"] == [], "Injection-only line should not match after P5 removal"


def test_inventory_line_no_lineage_keyword_no_match():
    """T3 keyword-proximity guard: inventory without lineage keyword does NOT match."""
    text = "the toolkit dropped lsass.exe, cmd.exe, and rundll32.exe to disk"
    result = process(text)
    assert result["high_likelihood_snippets"] == [], "Inventory line without lineage keyword should not match"


def test_narrative_verb_only_no_process_token_no_match():
    """Weak verb-only match without known process token should NOT match."""
    text = "the campaign executed in Q3"
    result = process(text)
    assert result["high_likelihood_snippets"] == [], "Narrative-only verb should not match"


def test_narrative_verb_with_strong_anchor_still_matches():
    """Strong-anchor override of narrative suppression -- pins finding #5 fix."""
    text = "winword.exe \u2192 powershell.exe (this was executed)"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1, "Strong anchor should override narrative suppression"


def test_long_line_threshold_boundary():
    """499-char vs 501-char lines with identical anchor produce expected shapes."""
    anchor = "winword.exe -> powershell.exe "
    # 499-char line: full-line path
    filler = "A" * (499 - len(anchor))
    short_line = anchor + filler
    assert len(short_line) == 499
    result_short = process(short_line)
    assert len(result_short["high_likelihood_snippets"]) >= 1, "499-char line should produce a snippet"

    # 501-char line: windowed path
    filler = "A" * (501 - len(anchor))
    long_line = anchor + filler
    assert len(long_line) == 501
    result_long = process(long_line)
    assert len(result_long["high_likelihood_snippets"]) >= 1, "501-char line should produce a snippet"


def test_byte_preserving_newline_count():
    """For any input, full_article has identical newline count to input."""
    text = "line1\nwinword.exe -> powershell.exe\nline3\n\nline5"
    result = process(text, agent_name="ProcTreeExtract")
    assert result["full_article"].count("\n") == text.count("\n")


def test_byte_preserving_full_article_identity():
    """full_article == article_text (exact equality)."""
    text = "ParentImage: services.exe\nImage: svchost.exe\nPID: 1234"
    result = process(text, agent_name="ProcTreeExtract")
    assert result["full_article"] == text


def test_max_snippets_cap_applied():
    """max_snippets trims excess snippets from the end; first snippet preserved."""
    lines = [f"winword.exe -> powershell{i:03d}.exe" for i in range(50)]
    article = "\n".join(lines)
    result = process(article, agent_name="ProcTreeExtract", max_snippets=5)
    snippets = result["high_likelihood_snippets"]
    assert len(snippets) <= 5
    # First snippet is preserved (high-signal early content kept)
    assert "powershell000" in snippets[0]


def test_max_snippets_zero_returns_empty():
    """max_snippets=0 returns no snippets (edge case)."""
    text = "winword.exe -> powershell.exe"
    result = process(text, max_snippets=0)
    assert result["high_likelihood_snippets"] == []


def test_snippets_preserve_article_order():
    """Multiple matches emit in document order."""
    text = "First: winword.exe -> powershell.exe\nSome prose here with no matches.\nSecond: cmd.exe --> explorer.exe"
    result = process(text)
    snippets = result["high_likelihood_snippets"]
    assert len(snippets) >= 2
    # First snippet should reference powershell, second should reference explorer
    all_text = "\n".join(snippets)
    first_ps = all_text.find("powershell")
    first_exp = all_text.find("explorer")
    assert first_ps < first_exp, "Snippets should preserve article order"


def test_deduplication():
    """Identical snippet from two anchors appears once."""
    # This line matches both STRING_ANCHORS_EXACT ("->") and P7 regex
    text = "winword.exe -> powershell.exe"
    result = process(text)
    snippets = result["high_likelihood_snippets"]
    assert len(snippets) == len(set(snippets)), "No duplicate snippets allowed"


def test_no_match_returns_empty_with_full_article():
    """Prose-only article returns [] + verbatim full_article."""
    text = "This is a regular article about cybersecurity trends in 2024."
    result = process(text)
    assert result["high_likelihood_snippets"] == []
    assert result["full_article"] == text
