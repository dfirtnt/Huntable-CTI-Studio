"""
Command-line attention pre-processor for Windows command-line extraction.

HARD CONTRACT (CmdlineExtract):
    For CmdlineExtract, preprocessing MUST be byte-preserving with respect to
    newline boundaries. If a change violates this, it is a bug, not a tuning issue.

PURPOSE:
    Performs attention shaping for Windows command-line extraction by identifying
    high-likelihood text regions (via LOLBAS-aligned anchors) and surfacing them
    earlier in the LLM prompt. The LLM still receives the full article.

NON-GOALS (strict):
    - Does NOT extract command lines
    - Does NOT validate syntax
    - Does NOT infer attacker behavior
    - Does NOT modify original text
    - Does NOT apply Sigma/EDR logic
    - Does NOT score or rank commands

EXTENDING ANCHORS:
    Add to STRING_ANCHORS for case-insensitive literal match, or REGEX_ANCHORS
    for pattern-based match. Keep anchors aligned with LOLBAS tradecraft.
    Pre-compile regexes at module load. Do not add scoring, weighting, or caps.
"""

import re
from typing import Any

# -----------------------------------------------------------------------------
# ANCHOR SET (LOLBAS-aligned, static)
# -----------------------------------------------------------------------------

# String anchors: case-insensitive `in` check. "cmd" uses boundary regex (see below).
STRING_ANCHORS = [
    "powershell",
    "pwsh",
    "rundll32",
    "msiexec",
    "wmic",
    "certutil",
    "bitsadmin",
    "schtasks",
    "netsh",
    "sc",
    "mshta",
    "cscript",
    "wscript",
    "forfiles",
    "findstr",
    "taskkill",
    "tasklist",
    "ipconfig",
    "systeminfo",
    "diskshadow",
    "makecab",
    "expand",
    "esentutl",
    "msbuild",
    "msdt",
    "installutil",
    "regasm",
    "regsvcs",
    "regini",
    "odbcconf",
    "cmstp",
    "dllhost",
    "ftp",
    "tftp",
    "curl",
    "wget",
    "C:\\",
    "D:\\",
    "%WINDIR%",
    "%TEMP%",
    "%TMP%",
    "\\temp\\",
    "\\pipe\\",
    "appdata",
    "programdata",
    "system32",
    "syswow64",
    "wbem",
    "comspec",
    "FromBase64String",
    "DownloadString",
    "Invoke-WebRequest",
    "Invoke-Expression",
    "IEX",
    "New-Object",
    "MemoryStream",
    "Add-MpPreference",
    "Set-MpPreference",
    ".lnk",
    ".iso",
    ".img",
    ".vhd",
    ".vhdx",
]

REGEX_ANCHOR_PATTERNS = [
    r"\b(hklm|hkcu|hkey_local_machine|hkey_current_user)\b",
    r"\breg(\.exe)?\s+(add|delete|query|save|load)\b",
    r"(^|\s)(/c|/k|/\?)\b",
    r"-(encodedcommand|enc)\b",
    r"\brundll32(\.exe)?\s+[^,\s]+,\S+",
    r"\.(lnk|iso|img|vhd|vhdx)\b",
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
SENTENCE_SPLIT = re.compile(r"(?<=[\n])|(?<=\.)(?!\w)\s+")
NEWLINE_ONLY = re.compile(r"\n")

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
        if _token_after_exe_match(line, m.end() - 1) not in NARRATIVE_VERBS:
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


def _expand_to_boundary(
    full_line: str, start_off: int, end_off: int, *, newline_only: bool = False
) -> str:
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


def _token_after_exe_match(line: str, match_end: int) -> str:
    """Extract the token immediately after .exe match (for narrative exclusion)."""
    rest = line[match_end:].lstrip()
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
    if m and _token_after_exe_match(line, m.end() - 1) not in NARRATIVE_VERBS:
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


def _is_narrative_exe_only(line: str) -> bool:
    """
    True when line has .exe + narrative verb but no invocation context (/, -, etc.).
    E.g. 'MSBuild.exe process reached out' matches via 'msbuild' anchor but is narrative.
    """
    if ".exe" not in line.lower() or any(c in line for c in ARG_INDICATORS):
        return False
    return any(m.group(1).lower() in NARRATIVE_VERBS for m in re.finditer(r"\.exe\s+(\w+)", line, re.IGNORECASE))


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
        byte_preserving
        or prefer_full_line
        or len(line) <= LONG_LINE_THRESHOLD
        or _line_has_exe_arg_indicators(line)
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
    """
    positions = _find_match_positions(line, line_lower)
    if not positions:
        return []

    snippets: list[str] = []
    for start, end in positions:
        # Window around match: ±MATCH_WINDOW_CHARS
        win_start = max(0, start - MATCH_WINDOW_CHARS)
        win_end = min(len(line), end + MATCH_WINDOW_CHARS)
        window = _expand_to_boundary(line, win_start, win_end, newline_only=byte_preserving)
        if not window.strip():
            continue
        snippets.append(window)

    # Prepend previous line, append next line for cross-line context (once per set)
    prev_line = lines[line_idx - 1] if line_idx > 0 else ""
    next_line = lines[line_idx + 1] if line_idx + 1 < len(lines) else ""
    if (prev_line or next_line) and snippets:
        # Add context to first snippet only (avoid duplicating for each window)
        parts = [p for p in [prev_line, snippets[0], next_line] if p]
        snippets[0] = "\n".join(parts).strip()
    return snippets


def process(article_text: str, agent_name: str | None = None) -> dict[str, Any]:
    """
    Scan article for high-likelihood command-line regions and return structured payload.

    Args:
        article_text: Raw article content.
        agent_name: When "CmdlineExtract", enables byte-preserving mode (disables sentence
            split, period/comma reflow, and space-join). Required by HARD CONTRACT.

    Returns:
        {
            "high_likelihood_snippets": ["<verbatim snippet>", ...],
            "full_article": "<original article text>"
        }
    Snippets preserve original article order. Deduplicated by exact string.
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
        if not _line_matches_anchor(line, line_lower) and not _line_matches_structural_rules(line):
            continue
        if _is_narrative_exe_only(line):
            continue

        # Long line: match-window capture (eval fix A)
        if len(line) > LONG_LINE_THRESHOLD:
            windowed = _extract_windowed_snippets(
                line, lines, i, line_lower, byte_preserving=byte_preserving
            )
            for snippet in windowed:
                if not snippet or snippet in seen:
                    continue
                seen.add(snippet)
                snippets_ordered.append(snippet)
            continue

        # Short line: full-line capture
        prefer_full = _line_has_exe_arg_indicators(line)
        snippet = _extract_snippet(
            line, lines, i,
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
    """
    result = process(example)
    print("Snippets:", len(result["high_likelihood_snippets"]))
    for s in result["high_likelihood_snippets"]:
        print("  -", repr(s[:80] + "..." if len(s) > 80 else s))
