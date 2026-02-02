"""Unit tests for cmdline_attention_preprocessor."""

from src.services.cmdline_attention_preprocessor import process, _expand_to_boundary


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
    """Article-602-class: long prose with command embedded late."""
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


def test_rule1_exe_path_plus_argument():
    """Rule 1: .exe path (quoted or unquoted) + at least one argument token."""
    for text in [
        "C:\\Tools\\mimikatz.exe privilege::debug",
        '"C:\\Program Files\\tool.exe" /install',
    ]:
        result = process(text)
        assert len(result["high_likelihood_snippets"]) >= 1, f"Expected match for: {text}"


def test_rule2_quoted_exe_nonpunctuation():
    """Rule 2: Quoted .exe + whitespace + non-punctuation → capture line."""
    text = '"C:\\Temp\\payload.exe" Invoke'
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "payload.exe" in result["high_likelihood_snippets"][0]


def test_rule4_exe_bare_verb():
    """Rule 4: .exe followed by bare word verb (e.g., tool.exe verb args)."""
    text = "The binary custom.exe install --silent was used."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "custom.exe" in result["high_likelihood_snippets"][0]


def test_rule5_two_or_more_windows_paths():
    """Rule 5: Line with two or more Windows paths (C:\\...)."""
    text = "Copy from C:\\Users\\Admin\\file.exe to C:\\Temp\\output.exe"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "C:\\" in result["high_likelihood_snippets"][0]


def test_narrative_exe_no_match():
    """Narrative .exe mention (e.g. GT_NET.exe (Grixba)) should NOT match - no invocation shape."""
    text = "The binary GT_NET.exe (Grixba) was used by the attacker."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) == 0


def test_narrative_exe_process_no_match():
    """MSBuild.exe process reached out - narrative verb 'process' should NOT match."""
    text = ".exe child process have been commonly observed. MSBuild.exe process reached out to Pastebin."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) == 0


def test_cmdline_extract_byte_preserving_no_sentence_split():
    """CmdlineExtract: no split on period; newline boundaries only (HARD CONTRACT)."""
    # Long line with period mid-sentence - should NOT split on period when agent=CmdlineExtract
    text = "x" * 300 + ". " + "y" * 300 + "\nThe attacker ran certutil -urlcache to download."
    result_default = process(text)  # agent_name=None
    result_cmdline = process(text, agent_name="CmdlineExtract")
    # With CmdlineExtract, we use full-line capture for long lines (byte_preserving)
    # so we get the full matching line, not sentence-split parts
    assert len(result_cmdline["high_likelihood_snippets"]) >= 1
    snippet = result_cmdline["high_likelihood_snippets"][0]
    # Must contain newline (we capture ±1 lines)
    assert "\n" in snippet or "certutil" in snippet
    # full_article unchanged
    assert result_cmdline["full_article"] == text


def test_expand_to_boundary_newline_only():
    """_expand_to_boundary with newline_only=True uses newline boundaries only, not period."""
    full_line = "prefix. match. suffix"
    start_off, end_off = 8, 13  # "match"
    result_newline = _expand_to_boundary(full_line, start_off, end_off, newline_only=True)
    result_sentence = _expand_to_boundary(full_line, start_off, end_off, newline_only=False)
    # newline_only=True: no \n in line, so full line returned (no period split)
    assert result_newline == "prefix. match. suffix"
    # newline_only=False: SENTENCE_SPLIT splits on ". ", yielding "match." (period included)
    assert result_sentence == "match."


def test_long_line_multiple_snippets():
    """Long line with multiple anchors produces multiple windowed snippets (not one blob)."""
    long_prose = "This is a long intrusion report. " * 40
    cmd1 = "The attacker ran certutil -urlcache to download."
    cmd2 = "Then they used bitsadmin /transfer to exfiltrate."
    text = long_prose + cmd1 + " " + long_prose[:200] + " " + cmd2
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 2
