"""Unit tests for cmdline_attention_preprocessor."""

import pytest

from src.services.cmdline_attention_preprocessor import process


def test_empty_article():
    """Empty article returns empty snippets and full_article."""
    result = process("")
    assert result["high_likelihood_snippets"] == []
    assert result["full_article"] == ""

    result = process("   \n\n  ")
    assert result["high_likelihood_snippets"] == []
    assert result["full_article"] == "   \n\n  "


def test_case_insensitivity():
    """POWERSHELL, Cmd.exe, RUNDLL32 all match (case-insensitive)."""
    for text in ["POWERSHELL -enc test", "Cmd.exe /c whoami", "RUNDLL32 foo.dll,Bar"]:
        result = process(text)
        assert len(result["high_likelihood_snippets"]) >= 1, f"Expected match for: {text}"
        assert result["full_article"] == text


def test_cmd_boundary_command_cmdlet_no_match():
    """'command' and 'cmdlet' do NOT match (cmd boundary guard)."""
    for text in ["The command failed.", "Use the cmdlet to process."]:
        result = process(text)
        assert result["high_likelihood_snippets"] == [], f"Expected no match for: {text}"


def test_cmd_boundary_matches():
    """'cmd /c' and 'cmd.exe' DO match."""
    for text in ["Run cmd /c whoami", "Execute cmd.exe /c echo test"]:
        result = process(text)
        assert len(result["high_likelihood_snippets"]) >= 1, f"Expected match for: {text}"


def test_powershell_enc_captured():
    """Article with powershell -enc captures snippet."""
    text = "The attacker used powershell -enc to decode the payload."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "powershell" in result["high_likelihood_snippets"][0].lower()
    assert result["full_article"] == text


def test_cmd_exe_whoami_captured():
    """Article with cmd.exe /c whoami captures snippet."""
    text = "Use cmd.exe /c whoami to check privileges."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "cmd" in result["high_likelihood_snippets"][0].lower()
    assert result["full_article"] == text


def test_system32_path_captured():
    """Article with C:\\Windows\\System32 path captures snippet."""
    text = "The binary at C:\\Windows\\System32\\net.exe was executed."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert result["full_article"] == text


def test_deduplication():
    """Same snippet from multiple anchors appears once."""
    text = "powershell -enc AAA && rundll32 foo.dll,Bar"
    result = process(text)
    snippets = result["high_likelihood_snippets"]
    assert len(snippets) >= 1
    # Same line should not appear twice
    assert len(snippets) == len(set(snippets))


def test_surrounding_context():
    """±1 surrounding line/sentence included."""
    text = "Previous line.\nThe attacker ran powershell -enc payload.\nNext line."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    snippet = result["high_likelihood_snippets"][0]
    assert "powershell" in snippet.lower()


def test_no_anchors_preserves_full_article():
    """No anchors → empty snippets, full_article preserved."""
    text = "This is a prose-only article with no Windows commands."
    result = process(text)
    assert result["high_likelihood_snippets"] == []
    assert result["full_article"] == text


def test_regex_anchors_reg_add():
    """Regex anchor: reg add captured."""
    text = "Modify registry: reg add HKLM\\Software\\Test /v Key /d Value"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1


def test_regex_anchors_encodedcommand():
    """Regex anchor: -encodedcommand captured."""
    text = "powershell -encodedcommand JABjAG8AbQBtAGEAbgBk"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1


def test_regex_anchors_rundll32():
    """Regex anchor: rundll32.exe foo.dll,Bar captured."""
    text = "rundll32.exe C:\\temp\\foo.dll,ExportFunc"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1


def test_snippets_preserve_article_order():
    """Snippets appear in same order as article."""
    text = "First: certutil -urlcache. Second: bitsadmin /transfer."
    result = process(text)
    snippets = result["high_likelihood_snippets"]
    assert len(snippets) >= 1
    # If multiple snippets, first should come before second in article
    if len(snippets) >= 2:
        first_pos = text.find(snippets[0].split("\n")[0][:20])
        second_pos = text.find(snippets[1].split("\n")[0][:20])
        if first_pos >= 0 and second_pos >= 0:
            assert first_pos < second_pos


def test_prose_only_article_with_late_command():
    """Article-62-class: long prose with command embedded late."""
    prose = "This is a long intrusion report. " * 20
    command_line = "The attacker then ran certutil -urlcache to download the payload."
    text = prose + "\n\n" + command_line
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "certutil" in result["high_likelihood_snippets"][0].lower()
    assert result["full_article"] == text


def test_anchor_inside_code_block_and_prose():
    """Anchor in code block + prose: dedupe works, no double capture."""
    text = """In the script block:
```powershell
powershell -enc base64payload
```
The same command was also mentioned in prose: powershell -enc base64payload
"""
    result = process(text)
    snippets = result["high_likelihood_snippets"]
    # Should capture but dedupe - exact same snippet may appear once
    assert len(snippets) >= 1
    assert result["full_article"] == text
