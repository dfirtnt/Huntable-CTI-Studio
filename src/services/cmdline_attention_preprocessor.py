"""
Command-line attention pre-processor for Windows command-line extraction.

HARD CONTRACT (CmdlineExtract):
    For CmdlineExtract, preprocessing MUST be byte-preserving with respect to
    newline boundaries. If a change violates this, it is a bug, not a tuning issue.

PURPOSE:
    Performs attention shaping for Windows command-line extraction by identifying
    high-likelihood text regions (via LOLBAS-aligned anchors) and surfacing them
    earlier in the LLM prompt. The LLM still receives the full article.

SCOPE:
    Covers execution/persistence (LOLBAS), credential access (T1003: LSASS dump
    tooling, mimikatz), and indirect execution (WSL/bash, at.exe). Scope was
    expanded beyond original LOLBAS-only coverage to close post-exploitation gaps.

NON-GOALS (strict):
    - Does NOT extract command lines
    - Does NOT validate syntax
    - Does NOT infer attacker behavior
    - Does NOT modify original text (full_article is always byte-identical to input)
    - Does NOT apply Sigma/EDR logic
    - Does NOT score or rank commands

CARET NORMALIZATION:
    cmd.exe silently strips ^ before execution (p^ow^er^sh^ell == powershell).
    _normalize_for_matching() strips carets from a COPY of the line for anchor
    matching only. The original line is ALWAYS used for snippet extraction and
    full_article passthrough. This is consistent with the HARD CONTRACT above.

EXTENDING ANCHORS:
    Add to STRING_ANCHORS for case-insensitive literal match, or REGEX_ANCHORS
    for pattern-based match. Keep anchors aligned with LOLBAS tradecraft.
    Pre-compile regexes at module load. Do not add scoring, weighting, or caps.
    Promote tokens to REGEX_ANCHORS (with structural guards) when the bare
    substring fires too broadly on prose (see "sc", "net", "expand", "tftp").
"""

import re
from typing import Any

# -----------------------------------------------------------------------------
# ANCHOR SET (LOLBAS-aligned, static)
# -----------------------------------------------------------------------------

# String anchors: case-insensitive `in` check. "cmd" uses boundary regex (see below).
# REMOVED (too broad / not cmdline-density indicators):
#   "C:\\" / "D:\\"  — path component in every Windows article; R5 (two-path rule) handles cmdlines
#   "system32"       — path component; near-universal FP across all Windows security content
#   "appdata" / "programdata" — directory names, not cmdline indicators
#   "ftp"            — 3-letter protocol name; fires on FTP protocol descriptions
#   "ipconfig"       — weakest LOLBin; single-token command, no surrounding cmdline density
#   "tasklist"       — no extractable argument structure; R1/R4 cover meaningful invocations
#   "dllhost"        — better served by proc_tree_attention_preprocessor
#   ".img"           — fires on HTML <img> refs and generic image descriptions
#   "tftp"           — promoted to REGEX_ANCHORS with word-boundary guard
STRING_ANCHORS = [
    # --- Execution / LOLBINs ---
    "powershell",
    "pwsh",
    "rundll32",
    "regsvr32",          # T1218.010 — AppLocker/SRP bypass via COM scriptlet (Squiblydoo)
    "msiexec",
    "wmic",
    "certutil",
    "bitsadmin",
    "schtasks",
    "netsh",
    "mshta",
    "cscript",
    "wscript",
    "forfiles",
    "findstr",
    "taskkill",
    "systeminfo",
    "diskshadow",
    "makecab",
    "esentutl",
    "msbuild",
    "msdt",
    "installutil",
    "regasm",
    "regsvcs",
    "regini",
    "odbcconf",
    "cmstp",
    "mavinject",         # T1055.001 — DLL injection via LOLBIN
    "xwizard",           # T1218 — proxy execution
    "presentationhost",  # T1218.008 — proxy execution
    "curl",
    "wget",
    # --- Windows paths / environment variables (cmdline-context specific) ---
    "%WINDIR%",
    "%TEMP%",
    "%TMP%",
    "\\temp\\",
    "\\pipe\\",    # Named pipe paths → lateral movement / C2 comms (SMB, Cobalt Strike)
    "syswow64",    # 32-bit on 64-bit OS; implies injection/evasion context
    "wbem",        # WMI namespace path → persistence/execution (T1047, T1546.003)
    "comspec",     # %COMSPEC% env var; only appears in cmdline invocation contexts
    # --- PowerShell tradecraft ---
    "FromBase64String",
    "DownloadString",
    "DownloadFile",      # .NET/PS download cradle (was missing)
    "DownloadData",
    "WebClient",         # [System.Net.WebClient] / New-Object Net.WebClient
    "Invoke-WebRequest",
    "Invoke-Expression",
    "IEX",
    "New-Object",
    "MemoryStream",
    "Add-MpPreference",  # T1562.001 — Defender exclusion add
    "Set-MpPreference",  # T1562.001 — Defender policy change
    # --- Container / disk artifacts (MOTW bypass: T1553.005) ---
    ".lnk",
    ".iso",
    ".vhd",
    ".vhdx",
    # --- Credential access (T1003) — scope expansion beyond original LOLBAS set ---
    "comsvcs",     # comsvcs.dll MiniDump → LSASS dump via rundll32
    "lsass",       # LSASS process — primary credential dump target
    "mimikatz",    # credential dumping toolkit; low FP (always attack-context)
    "sekurlsa",    # mimikatz module (sekurlsa::logonpasswords)
    "procdump",    # Sysinternals dump tool commonly used for LSASS
    # --- Contract LOLBins (named in CmdlineExtract Condition 2) ---
    "whoami",
    "vssadmin",
    "wevtutil",
    "nltest",
    "bcdedit",
    "adfind",
    "psexec",
    "nslookup",
    # --- PowerShell execution flags (appear without the "powershell" keyword) ---
    "-NoProfile",
    "-WindowStyle",
    "-ExecutionPolicy",
    "-NonInteractive",
]

REGEX_ANCHOR_PATTERNS = [
    # REMOVED: r"\b(hklm|hkcu|...)\b"  — fires on registry prose; redundant with reg regex below
    # REMOVED: r"(^|\s)(/c|/k)(?=\s|$)" — redundant with CMD_BOUNDARY_REGEX; fires on many tool flags
    r"\breg(\.exe)?\s+(add|delete|query|save|load)\b",
    r"-(encodedcommand|enc)\b",
    r"\brundll32(\.exe)?\s+[^,\s]+,\S+",
    r"\.(lnk|iso|vhd|vhdx)\b",   # .img removed: fires on HTML <img> and generic image refs
    # "sc" promoted from STRING_ANCHORS: plain substring fires on "Microsoft", "scan", etc.
    r"\bsc(\.exe)?\s+(start|stop|create|delete|config|query|description)\b",
    # "expand" promoted from STRING_ANCHORS: requires Windows path arg to avoid prose FP
    r"\bexpand(\.exe)?\s+[A-Za-z]:\\",
    # "net" promoted from STRING_ANCHORS: bare "net" fires on "network", "internet", etc.
    r"\bnet(\.exe)?\s+(user|group|use|share|view|localgroup|accounts|session|start|stop|computer)\b",
    # "tftp" promoted from STRING_ANCHORS: word-boundary guard prevents compound-token FP
    r"\btftp(\.exe)?\b",
    # T1218.001 — Compiled HTML Help: two-char name requires boundary + argument guard
    r"\bhh(\.exe)?\s+\S",
    # T1202 — Indirect Command Execution via Windows Subsystem for Linux
    r"\bwsl(\.exe)?\b",
    # T1202 — bash with explicit execution flag (bare "bash" fires on shell scripting prose)
    r"\bbash(\.exe)?\s+(-c|-i)\b",
    # T1053.002 — legacy at.exe scheduler: time argument required to avoid "at" substring noise
    r"\bat(\.exe)?\s+\d{1,2}:\d{2}\b",
]

# Pre-compiled regexes (case-insensitive)
REGEX_ANCHORS = [re.compile(p, re.IGNORECASE) for p in REGEX_ANCHOR_PATTERNS]

# cmd: boundary guard to avoid matching "command", "cmdlet", prose
CMD_BOUNDARY_REGEX = re.compile(r"\bcmd(\.exe)?\b", re.IGNORECASE)

# Sentence boundary for long-line splitting (used when extracting from >500 char lines).
# - Newline: always split
# - Period + whitespace: split only when period is NOT part of extension (e.g. .exe, .dll)
#   Use (?!\w) to avoid splitting "tool.exe and whoami" or "foo.dll,Export"
# - Comma: NOT used — comma+space can break commands ("echo hello, world")
# FORBIDDEN for CmdlineExtract (byte-preserving): use NEWLINE_ONLY instead.
#
# FOOTGUN: the two alternatives are NOT symmetric.
#   (?<=[\n])          -- zero-width lookbehind; m.end() points to the char AFTER \n
#   (?<=\.)(?!\w)\s+   -- non-zero-width; m.end() points past the consumed whitespace
# In _expand_to_boundary, boundary_after is set to end_off + m.end(), so the two cases
# land at different relative positions. Behavior is correct for current callers but
# would break silently if the function were extended to use m.start()/m.end() directly.
SENTENCE_SPLIT = re.compile(r"(?<=[\n])|(?<=\.)(?!\w)\s+")
NEWLINE_ONLY = re.compile(r"\n")

# Caret normalization: cmd.exe silently strips ^ before executing a command.
# e.g. p^ow^er^sh^ell -enc AAA  →  powershell -enc AAA
# _normalize_for_matching() strips carets from a COPY for anchor/structural
# matching only. The original line is ALWAYS used for snippet extraction.
# HARD CONTRACT: full_article is never touched by this function.
_CARET_STRIP_RE = re.compile(r"\^")


def _normalize_for_matching(line: str) -> str:
    """Strip cmd.exe caret escapes for anchor matching. Original preserved for extraction."""
    return _CARET_STRIP_RE.sub("", line)


# Line length threshold: use sentence logic only if line > N chars
LONG_LINE_THRESHOLD = 500

# Match-window: chars to each side of match when line exceeds threshold
MATCH_WINDOW_CHARS = 350

# Structural capture rules (beyond LOLBAS anchors)
# Rule 1: .exe path (quoted or unquoted) followed by invocation shape (arg indicator or verb)
# Exclude parenthetical/bracket content: "GT_NET.exe (Grixba)" is narrative, not a command
RE_EXE_PLUS_ARG = re.compile(
    r"(?:[^\s\"]+\.exe|\"[^\"]*\.exe\")\s+[^(\s\[\{]",
    re.IGNORECASE,
)
# Rule 2: Quoted string ending in .exe + whitespace + non-punctuation
RE_QUOTED_EXE_NONPUNCT = re.compile(
    r"\"[^\"]*\.exe\"\s+[A-Za-z0-9]",
    re.IGNORECASE,
)
# Rule 3: .exe + argument indicators → prefer full-line capture (checked in _extract_snippet)
ARG_INDICATORS = frozenset('-/"><|')
# Rule 4: .exe followed by bare word verb (e.g., tool.exe verb args)
# Exclude narrative-only words: "process", "application", "file" etc. (e.g. "MSBuild.exe process reached out")
RE_EXE_BARE_VERB = re.compile(
    r"\.exe\b\s+([A-Za-z]\w*)",
    re.IGNORECASE,
)
NARRATIVE_VERBS = frozenset(
    {
        "process",
        "application",
        "file",
        "version",
        "manager",
        "handler",
        "service",
        "component",
        "child",
        "parent",
        "reached",
        "observed",
        "started",
        "stopped",
        "created",
        "dropped",
        # Common prose verbs describing process execution in narrative text
        "ran",
        "executed",
        "invoked",
        "spawned",
        "launched",
        "terminated",
        "installed",
        "deployed",
        "triggered",
        # Prose connectors that follow .exe in narrative sentences but are not cmdline args.
        # Without these, "tool.exe using the AppDomain feature" fires R4.
        "using",
        "via",
        "hosting",
        "calling",
        "leveraging",
        "with",
        "within",
        "based",
        "found",
        "located",
        "attempting",
        "trying",
        "able",
        "known",
        "running",
    }
)
# Rule 5: Two or more Windows paths (C:\... or D:\...)
RE_WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^\s]*", re.IGNORECASE)


def _find_match_positions(line: str, line_lower: str) -> list[tuple[int, int]]:
    """
    Return all (start, end) match positions in line for anchors and structural rules.
    Used for match-window capture on long lines.
    """
    positions: list[tuple[int, int]] = []

    def add_matches(pattern: re.Pattern[str]) -> None:
        for m in pattern.finditer(line):
            positions.append((m.start(), m.end()))

    def add_string_anchor(anchor: str) -> None:
        start = 0
        a_lower = anchor.lower()
        while True:
            idx = line_lower.find(a_lower, start)
            if idx < 0:
                break
            positions.append((idx, idx + len(anchor)))
            start = idx + 1

    # Regex anchors
    add_matches(CMD_BOUNDARY_REGEX)
    for p in REGEX_ANCHORS:
        add_matches(p)
    for m in RE_EXE_PLUS_ARG.finditer(line):
        if _token_starting_at(line, m.end() - 1) not in NARRATIVE_VERBS:
            positions.append((m.start(), m.end()))
    add_matches(RE_QUOTED_EXE_NONPUNCT)
    for m in RE_EXE_BARE_VERB.finditer(line):
        if m.group(1).lower() not in NARRATIVE_VERBS:
            positions.append((m.start(), m.end()))

    # Structural: two or more Windows paths
    paths = list(RE_WINDOWS_PATH.finditer(line))
    if len(paths) >= 2:
        for m in paths:
            positions.append((m.start(), m.end()))

    # String anchors
    for anchor in STRING_ANCHORS:
        add_string_anchor(anchor)

    return positions


def _expand_to_boundary(full_line: str, start_off: int, end_off: int, *, newline_only: bool = False) -> str:
    """
    Expand the window [start_off, end_off] to nearest boundaries.
    newline_only=True: byte-preserving (CmdlineExtract) — only newline boundaries.
    newline_only=False: sentence boundaries (period + newline).
    Capped at ±MATCH_WINDOW_CHARS from match.
    """
    boundary_re = NEWLINE_ONLY if newline_only else SENTENCE_SPLIT
    win_start = max(0, start_off - MATCH_WINDOW_CHARS)
    win_end = min(len(full_line), end_off + MATCH_WINDOW_CHARS)

    before = full_line[win_start:start_off]
    boundary_before = win_start
    for m in boundary_re.finditer(before):
        boundary_before = win_start + m.end()
    after = full_line[end_off:win_end]
    boundary_after = win_end
    for m in boundary_re.finditer(after):
        boundary_after = end_off + m.end()
        break
    return full_line[boundary_before:boundary_after].strip()


def _line_matches_anchor(line: str, line_lower: str) -> bool:
    """Return True if line matches any string or regex anchor (case-insensitive)."""
    # cmd: boundary guard (precision fix)
    if CMD_BOUNDARY_REGEX.search(line):
        return True
    # String anchors
    for anchor in STRING_ANCHORS:
        if anchor.lower() in line_lower:
            return True
    # Regex anchors
    return any(pattern.search(line) for pattern in REGEX_ANCHORS)


def _token_starting_at(line: str, pos: int) -> str:
    """
    Extract the first token starting at or after pos (for narrative exclusion).
    Callers pass m.end() - 1, i.e. the index of the first non-space char captured
    by RE_EXE_PLUS_ARG, so lstrip() normalises any off-by-one from match shape.
    """
    rest = line[pos:].lstrip()
    if not rest:
        return ""
    token = rest.split()[0]
    if token.endswith((",", ".", ";", ":")):
        token = token[:-1]
    return token.lower()


def _line_matches_structural_rules(line: str) -> bool:
    """
    Return True if line matches any structural capture rule:
    1. .exe path (quoted or unquoted) + at least one argument token
    2. Quoted string ending in .exe + whitespace + non-punctuation
    4. .exe followed by bare word verb (e.g., tool.exe verb args)
    5. Two or more Windows paths (C:\\...)
    """
    if not line or not line.strip():
        return False
    # Rule 1: .exe path + argument (exclude narrative verbs)
    m = RE_EXE_PLUS_ARG.search(line)
    if m and _token_starting_at(line, m.end() - 1) not in NARRATIVE_VERBS:
        return True
    # Rule 2: quoted .exe + non-punctuation
    if RE_QUOTED_EXE_NONPUNCT.search(line):
        return True
    # Rule 4: .exe + bare verb (exclude narrative-only words)
    m = RE_EXE_BARE_VERB.search(line)
    if m and m.group(1).lower() not in NARRATIVE_VERBS:
        return True
    # Rule 5: two or more Windows paths
    paths = RE_WINDOWS_PATH.findall(line)
    return len(paths) >= 2


def _is_narrative_exe_only(line: str, line_lower: str) -> bool:
    """
    True when the ONLY reason the line matched is an exe+narrative-verb shape
    with no invocation context (/, -, etc.). Lines that also carry an independent
    LOLBAS anchor (e.g. 'powershell' in a line about 'MSBuild.exe process ...')
    are NOT suppressed -- the independent signal is real.
    """
    if ".exe" not in line_lower or any(c in line for c in ARG_INDICATORS):
        return False
    # Must have at least one exe + narrative verb to be a candidate for suppression
    if not any(m.group(1).lower() in NARRATIVE_VERBS for m in re.finditer(r"\.exe\s+(\w+)", line, re.IGNORECASE)):
        return False
    # Do not suppress if cmd boundary or any regex anchor fires independently
    if CMD_BOUNDARY_REGEX.search(line):
        return False
    if any(p.search(line) for p in REGEX_ANCHORS):
        return False
    # Do not suppress if a string anchor matches something other than the exe names
    # already present in the line (e.g. "powershell" in "MSBuild.exe process ... powershell")
    exe_names = {m.group(1).lower() for m in re.finditer(r"(\w+)\.exe\b", line, re.IGNORECASE)}
    for anchor in STRING_ANCHORS:
        a_lower = anchor.lower()
        if a_lower in line_lower and a_lower not in exe_names:
            return False
    return True


def _line_has_exe_arg_indicators(line: str) -> bool:
    """
    Rule 3: .exe + argument indicators (-, /, quotes, >, <, |).
    When True, prefer full-line capture over sentence splitting.
    """
    if ".exe" not in line.lower():
        return False
    return any(c in line for c in ARG_INDICATORS)


def _extract_snippet(
    line: str,
    lines: list[str],
    line_idx: int,
    prefer_full_line: bool = False,
    line_lower: str | None = None,
    *,
    byte_preserving: bool = False,
) -> str:
    """
    Extract matching line + ±1 surrounding sentence/line for context.
    byte_preserving: always use full-line capture (no sentence split, no " ".join).
    """
    use_full_line = (
        byte_preserving or prefer_full_line or len(line) <= LONG_LINE_THRESHOLD or _line_has_exe_arg_indicators(line)
    )
    if use_full_line:
        # Full-line capture: include ±1 surrounding lines
        start = max(0, line_idx - 1)
        end = min(len(lines), line_idx + 2)
        return "\n".join(lines[start:end]).strip()
    # Sentence logic for long lines (>500 chars, no .exe+arg indicators)
    # Split by SENTENCE_SPLIT, find matching part(s), include ±1 for context
    parts = SENTENCE_SPLIT.split(line)
    matching_indices: list[int] = []
    for i, part in enumerate(parts):
        part_stripped = part.strip()
        if not part_stripped:
            continue
        part_lower = part_stripped.lower()
        if _line_matches_anchor(part_stripped, part_lower) or _line_matches_structural_rules(part_stripped):
            matching_indices.append(i)
    if not matching_indices:
        # No part matched (shouldn't happen if line matched) — return full ±1 lines
        start = max(0, line_idx - 1)
        end = min(len(lines), line_idx + 2)
        return "\n".join(lines[start:end]).strip()
    # Include matching parts + ±1 adjacent for context
    min_i = max(0, min(matching_indices) - 1)
    max_i = min(len(parts) - 1, max(matching_indices) + 1)
    snippet = " ".join(p.strip() for p in parts[min_i : max_i + 1] if p.strip())
    # Prepend previous line, append next line for cross-line context
    prev_line = lines[line_idx - 1] if line_idx > 0 else ""
    next_line = lines[line_idx + 1] if line_idx + 1 < len(lines) else ""
    context_parts = [p for p in [prev_line, snippet, next_line] if p]
    return "\n".join(context_parts).strip()


def _extract_windowed_snippets(
    line: str, lines: list[str], line_idx: int, line_lower: str, *, byte_preserving: bool = False
) -> list[str]:
    """
    For long lines (>LONG_LINE_THRESHOLD): extract match-window snippets instead of full line.
    byte_preserving: use newline-only boundaries (no sentence/period split).

    Context policy: prev/next surrounding lines are attached to snippets[0] only.
    Attaching them to every window would duplicate the same neighboring lines once
    per anchor hit on the same long line. Short-line path (_extract_snippet) always
    attaches prev/next -- intentional asymmetry, documented here.

    Overlapping windows are merged before extraction to avoid emitting overlapping
    byte ranges as separate snippets (the exact-string dedup in process() only
    catches identical strings, not overlapping-but-different ones).
    """
    positions = _find_match_positions(line, line_lower)
    if not positions:
        return []

    # Compute raw windows, merge overlapping ranges (sort by start, linear merge pass)
    raw: list[tuple[int, int]] = sorted(
        (max(0, start - MATCH_WINDOW_CHARS), min(len(line), end + MATCH_WINDOW_CHARS)) for start, end in positions
    )
    merged: list[tuple[int, int]] = []
    for ws, we in raw:
        if merged and ws <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], we))
        else:
            merged.append((ws, we))

    snippets: list[str] = []
    for win_start, win_end in merged:
        window = _expand_to_boundary(line, win_start, win_end, newline_only=byte_preserving)
        if not window.strip():
            continue
        snippets.append(window)

    # Prepend previous line, append next line for cross-line context (first snippet only)
    prev_line = lines[line_idx - 1] if line_idx > 0 else ""
    next_line = lines[line_idx + 1] if line_idx + 1 < len(lines) else ""
    if (prev_line or next_line) and snippets:
        parts = [p for p in [prev_line, snippets[0], next_line] if p]
        snippets[0] = "\n".join(parts).strip()
    return snippets


def process(
    article_text: str,
    agent_name: str | None = None,
    max_snippets: int | None = None,
) -> dict[str, Any]:
    """
    Scan article for high-likelihood command-line regions and return structured payload.

    Args:
        article_text: Raw article content.
        agent_name: When "CmdlineExtract", enables byte-preserving mode (disables sentence
            split, period/comma reflow, and space-join). Required by HARD CONTRACT.
        max_snippets: Hard cap on returned snippets. Excess entries are dropped from the
            end (earliest/highest-signal snippets are preserved). None = no cap.

    Returns:
        {
            "high_likelihood_snippets": ["<verbatim snippet>", ...],
            "full_article": "<original article text>"
        }
    Snippets preserve original article order. Deduplicated by exact string.

    Note on byte-preservation: the HARD CONTRACT applies to full_article only.
    Snippets are derived/normalized (stripped, context-joined) and are not
    byte-identical to the source. Callers that validate newline count must use
    full_article, not snippets.

    Note on max_snippets: excess entries are dropped from the END, preserving
    the earliest (highest-signal) matches. This is intentional -- IOC-dense
    sections typically appear near the top of LOLBAS-style articles. Changing
    the drop strategy (e.g. sample-evenly) would break the article_2068 fix.
    """
    if not article_text or not article_text.strip():
        return {"high_likelihood_snippets": [], "full_article": article_text or ""}

    # CmdlineExtract: byte-preserving with respect to newline boundaries (HARD CONTRACT)
    byte_preserving = agent_name == "CmdlineExtract"

    lines = article_text.splitlines()
    seen: set[str] = set()
    snippets_ordered: list[str] = []

    for i, line in enumerate(lines):
        line_lower = line.lower()

        # Caret normalization: also match against the stripped copy so that
        # cmd.exe escape obfuscation (p^ow^er^sh^ell) fires the same anchors.
        # Snippet extraction ALWAYS uses the original `line` / `lines`.
        line_norm = _normalize_for_matching(line)
        line_norm_lower = line_norm.lower() if line_norm != line else line_lower

        anchor_match = _line_matches_anchor(line, line_lower) or (
            line_norm != line and _line_matches_anchor(line_norm, line_norm_lower)
        )
        structural_match = _line_matches_structural_rules(line) or (
            line_norm != line and _line_matches_structural_rules(line_norm)
        )
        if not anchor_match and not structural_match:
            continue
        if _is_narrative_exe_only(line, line_lower):
            continue

        # Long line: match-window capture.
        if len(line) > LONG_LINE_THRESHOLD:
            windowed = _extract_windowed_snippets(line, lines, i, line_lower, byte_preserving=byte_preserving)
            if not windowed and line_norm != line:
                # Caret obfuscation shifted positions; fall back to full ±1 line capture.
                windowed = [_extract_snippet(line, lines, i, prefer_full_line=True, line_lower=line_lower, byte_preserving=byte_preserving)]
            for snippet in windowed:
                if not snippet or snippet in seen:
                    continue
                seen.add(snippet)
                snippets_ordered.append(snippet)
            continue

        # Short line: full-line capture
        prefer_full = _line_has_exe_arg_indicators(line)
        snippet = _extract_snippet(
            line,
            lines,
            i,
            prefer_full_line=prefer_full,
            line_lower=line_lower,
            byte_preserving=byte_preserving,
        )
        if not snippet:
            continue
        if snippet in seen:
            continue
        seen.add(snippet)
        snippets_ordered.append(snippet)

    if max_snippets is not None and len(snippets_ordered) > max_snippets:
        snippets_ordered = snippets_ordered[:max_snippets]

    return {
        "high_likelihood_snippets": snippets_ordered,
        "full_article": article_text,
    }


# Example invocation
if __name__ == "__main__":
    example = """
    The attacker used powershell -enc to decode the payload.
    Then they ran cmd.exe /c whoami to check privileges.
    Registry modification: reg add HKLM\\Software\\Test.
    Caret-obfuscated: p^ow^er^sh^ell -enc JABjAG8AbQBtAGEAbgBk
    LSASS dump: rundll32 comsvcs.dll MiniDump 624 C:\\Temp\\lsass.dmp full
    """
    result = process(example)
    print("Snippets:", len(result["high_likelihood_snippets"]))
    for s in result["high_likelihood_snippets"]:
        print("  -", repr(s[:80] + "..." if len(s) > 80 else s))
