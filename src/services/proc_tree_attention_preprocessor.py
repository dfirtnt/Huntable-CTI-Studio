"""
Process-tree attention pre-processor for process lineage extraction.

HARD CONTRACT (ProcTreeExtract):
    For ProcTreeExtract, preprocessing MUST be byte-preserving with respect to
    newline boundaries. If a change violates this, it is a bug, not a tuning issue.
    This applies to full_article only; snippets are derived/normalized.

PURPOSE:
    Performs attention shaping for process lineage extraction by identifying
    high-likelihood text regions (parent->child spawn patterns, tree renderings,
    Sysmon fields) and surfacing them earlier in the LLM prompt. The LLM still
    receives the full article.

NON-GOALS (strict):
    - Does NOT assemble parent->child tuples (that's the LLM's job)
    - Does NOT infer PIDs, scores, or confidence
    - Does NOT modify full_article bytes
    - Does NOT change the cmdline preprocessor or ProcTreeExtract prompts
    - Does NOT touch other extractors' prompts

EXTENDING ANCHORS:
    Add to STRING_ANCHORS_EXACT for case-insensitive literal match (only
    high-specificity tokens like Sysmon field names or tree glyphs).
    Add to PROC_TREE_REGEX_PATTERNS for pattern-based match with \\b guards.
    Bare verbs like "spawn", "child", "parent" go in regex with \\b, NOT in
    STRING_ANCHORS_EXACT -- that's the substring-anchor trap.
    Pre-compile regexes at module load. Do not add scoring or weighting.

max_snippets heuristic: excess entries are dropped from the END, preserving
    the earliest (highest-signal) matches. IOC-dense sections typically appear
    near the top of lineage-focused articles.
"""

import re
from typing import Any

# -----------------------------------------------------------------------------
# ANCHOR SETS (static, frozen at module load)
# -----------------------------------------------------------------------------

# String anchors: case-insensitive substring match -- ONLY high-specificity tokens
STRING_ANCHORS_EXACT = [
    "Process Create",
    "ProcessCreate",
    "ProcessCreated",
    "EventID 1",
    "Event ID 1",
    "ParentImage",
    "ParentCommandLine",
    "ParentProcessName",
    "ParentProcessId",
    "ParentProcessGuid",
    # Arrow renderings
    "\u2192",  # right arrow
    "->",
    "-->",
    # Tree-drawing glyphs
    "\u2514\u2500",  # corner + horizontal
    "\u251c\u2500",  # tee + horizontal
    "\u2514\u2500\u2500",  # corner + double horizontal
    "\u251c\u2500\u2500",  # tee + double horizontal
    "\u2514>",  # corner + gt
]

# Regex patterns for process lineage (compiled once, case-insensitive)
PROC_TREE_REGEX_PATTERNS = [
    # P1: lineage verbs binding two tokens
    r"\b[\w\-.]+(?:\.exe)?\s+"
    r"(?:spawn(?:s|ed|ing)?|launch(?:es|ed|ing)?|execut(?:e|es|ed|ing)|"
    r"invok(?:e|es|ed|ing)|start(?:s|ed|ing)?|creat(?:e|es|ed|ing)|"
    r"r(?:an|uns|unning)|call(?:s|ed|ing)?|load(?:s|ed|ing)?)\s+"
    r"[\w\-.]+(?:\.exe)?\b",
    # P2: reverse direction "X was spawned by Y"
    r"\b[\w\-.]+(?:\.exe)?\s+(?:was\s+)?"
    r"(?:spawned|launched|executed|created|invoked|started|loaded)\s+by\s+"
    r"[\w\-.]+(?:\.exe)?\b",
    # P3: parent/child label (must be qualified)
    r"\b(?:parent|child)\s+(?:process|pid|image|id|command\s*line)\b",
    r"\b(?:parent|child)\s*[:=]\s*\S",
    # P6: child of / running under / in the context of
    r"\bchild\s+of\s+[\w\-.]+(?:\.exe)?",
    r"\brunning\s+under\s+[\w\-.]+(?:\.exe)?",
    r"\b(?:in|with)\s+the\s+context\s+of\s+[\w\-.]+(?:\.exe)?",
    # P7: explicit arrow rendering between .exe tokens
    r"[\w\-.]+\.exe\s*(?:-+>|\u2192|=+>)\s*[\w\-.]+\.exe",
    # P8: tree-drawing glyph + .exe on same line
    r"^\s*(?:[\u2502|]\s*)*(?:[\u2514\u251c]\u2500{1,3}|\\->|\|-)\s*\S*\.exe",
]

# Pre-compiled regexes (case-insensitive)
REGEX_ANCHORS = [re.compile(p, re.IGNORECASE) for p in PROC_TREE_REGEX_PATTERNS]

# Indices into REGEX_ANCHORS for classification (strong vs weak)
# P1=0, P2=1, P3=2-3, P6=4-6, P7=7, P8=8
_STRONG_REGEX_INDICES = frozenset({2, 3, 7, 8})  # P3, P7, P8
_WEAK_REGEX_INDICES = frozenset({0, 1, 4, 5, 6})  # P1, P2, P6

# Executable-shape heuristic for T3 (matches any exe/dll/scr/com/bat/cmd/ps1 token)
_EXE_SHAPE_RE = re.compile(
    r"\b[a-zA-Z0-9_\-]+\.(exe|dll|scr|com|bat|cmd|ps1)\b",
    re.IGNORECASE,
)

# Path indicators for T3 (Windows drive roots, UNC paths, quoted executables,
# backslash-prefixed executable names)
_PATH_INDICATOR_RE = re.compile(
    r"[A-Za-z]:\\"
    r"|\\\\[\w\-]+"
    r'|"[^"]*\.(exe|dll|scr|com|bat|cmd|ps1)"'
    r"|(?<![A-Za-z0-9])\\[A-Za-z0-9_\-]{2,}\.(exe|dll|scr|com|bat|cmd|ps1)",
    re.IGNORECASE,
)

# Lineage keywords for T3 proximity check
_LINEAGE_KEYWORDS_RE = re.compile(
    r"\b(?:parent|child|spawn(?:s|ed|ing)?|inject(?:s|ed|ing)?|"
    r"launch(?:es|ed|ing)?|execut(?:e|es|ed|ing)|creat(?:e|es|ed|ing)|"
    r"lineage|tree|ancestor|descendant)\b",
    re.IGNORECASE,
)

# Arrow / tree glyph tokens for narrative suppression check
_ARROW_TREE_GLYPHS = frozenset(
    {
        "\u2192",
        "->",
        "-->",
        "==>",
        "\u2514\u2500",
        "\u251c\u2500",
        "\u2514\u2500\u2500",
        "\u251c\u2500\u2500",
        "\u2514>",
        "\\->",
        "|-",
    }
)

# Boundary patterns (reuse same logic as cmdline preprocessor)
NEWLINE_ONLY = re.compile(r"\n")
SENTENCE_SPLIT = re.compile(r"(?<=[\n])|(?<=\.)(?!\w)\s+")

# Line length threshold: use windowed logic for lines > N chars
LONG_LINE_THRESHOLD = 500

# Match-window: chars to each side of match when line exceeds threshold
MATCH_WINDOW_CHARS = 400

# Adjacent context lines
ADJACENT_LINES_DEFAULT = 1
ADJACENT_LINES_TREE_GLYPH = 2  # T2 matches: include +/-2 lines

# Regex for finding .exe tokens on a line
_EXE_TOKEN_RE = re.compile(r"\b([\w\-.]+\.exe)\b", re.IGNORECASE)

# Regex for T4: Sysmon field block detection
_SYSMON_PARENT_IMAGE_RE = re.compile(r"\bParentImage\b", re.IGNORECASE)
_SYSMON_IMAGE_RE = re.compile(r"\bImage\b", re.IGNORECASE)
_SYSMON_PARENT_CMDLINE_RE = re.compile(r"\bParentCommandLine\b", re.IGNORECASE)
_SYSMON_CMDLINE_RE = re.compile(r"\bCommandLine\b", re.IGNORECASE)

# PID/PPID pattern for T5 (pair detection -- requires two matches on same line)
_PID_RE = re.compile(r"\b(?:p?pid|process\s*id|parent\s*pid)\s*[:=]?\s*\d{2,}", re.IGNORECASE)


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------


def _find_match_positions(line: str, line_lower: str) -> list[tuple[int, int]]:
    """
    Return all (start, end) match positions in line for anchors and structural rules.
    Used for match-window capture on long lines.
    """
    positions: list[tuple[int, int]] = []

    # String anchors
    for anchor in STRING_ANCHORS_EXACT:
        a_lower = anchor.lower()
        start = 0
        while True:
            idx = line_lower.find(a_lower, start)
            if idx < 0:
                break
            positions.append((idx, idx + len(anchor)))
            start = idx + 1

    # Regex anchors
    for pattern in REGEX_ANCHORS:
        for m in pattern.finditer(line):
            positions.append((m.start(), m.end()))

    # T3a: two executable-shape tokens + lineage keyword within +/-60 chars
    shape_matches = list(_EXE_SHAPE_RE.finditer(line))
    if len(shape_matches) >= 2:
        for i, m1 in enumerate(shape_matches):
            for m2 in shape_matches[i + 1 :]:
                region_start = max(0, min(m1.start(), m2.start()) - 60)
                region_end = min(len(line), max(m1.end(), m2.end()) + 60)
                if _LINEAGE_KEYWORDS_RE.search(line[region_start:region_end]):
                    positions.append((m1.start(), m1.end()))
                    positions.append((m2.start(), m2.end()))

    # T3b: path indicator + lineage keyword
    if _PATH_INDICATOR_RE.search(line) and _LINEAGE_KEYWORDS_RE.search(line):
        positions.append((0, len(line)))

    # T4: Sysmon field block
    if (_SYSMON_PARENT_IMAGE_RE.search(line) and _SYSMON_IMAGE_RE.search(line)) or (
        _SYSMON_PARENT_CMDLINE_RE.search(line) and _SYSMON_CMDLINE_RE.search(line)
    ):
        positions.append((0, len(line)))

    # T5: PID and PPID on same line (two distinct PID matches)
    pid_matches = list(_PID_RE.finditer(line))
    if len(pid_matches) >= 2:
        for m in pid_matches:
            positions.append((m.start(), m.end()))

    return positions


def _expand_to_boundary(full_line: str, start_off: int, end_off: int, *, newline_only: bool = False) -> str:
    """
    Expand the window [start_off, end_off] to nearest boundaries.
    newline_only=True: byte-preserving (ProcTreeExtract) -- only newline boundaries.
    newline_only=False: sentence boundaries (period + newline).
    Capped at +/-MATCH_WINDOW_CHARS from match.
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
    # String anchors
    for anchor in STRING_ANCHORS_EXACT:
        if anchor.lower() in line_lower:
            return True
    # Regex anchors
    return any(pattern.search(line) for pattern in REGEX_ANCHORS)


def _line_matches_structural_rules(line: str) -> bool:
    """
    Return True if line matches any structural capture rule:
    T3a: Two executable-shape tokens + lineage keyword within +/-60 chars
    T3b: Path indicator + lineage keyword on same line
    T4: Sysmon field block (ParentImage AND Image, or ParentCommandLine AND CommandLine)
    T5: PID and PPID pair on same line
    (T1/T2 are covered by P7/P8 regex anchors)
    """
    if not line or not line.strip():
        return False

    # T3a: two executable-shape tokens + lineage keyword within +/-60 chars
    shape_matches = list(_EXE_SHAPE_RE.finditer(line))
    if len(shape_matches) >= 2:
        for i, m1 in enumerate(shape_matches):
            for m2 in shape_matches[i + 1 :]:
                region_start = max(0, min(m1.start(), m2.start()) - 60)
                region_end = min(len(line), max(m1.end(), m2.end()) + 60)
                if _LINEAGE_KEYWORDS_RE.search(line[region_start:region_end]):
                    return True

    # T3b: path indicator + lineage keyword
    if _PATH_INDICATOR_RE.search(line) and _LINEAGE_KEYWORDS_RE.search(line):
        return True

    # T4: Sysmon field block
    if (_SYSMON_PARENT_IMAGE_RE.search(line) and _SYSMON_IMAGE_RE.search(line)) or (
        _SYSMON_PARENT_CMDLINE_RE.search(line) and _SYSMON_CMDLINE_RE.search(line)
    ):
        return True

    # T5: PID and PPID on same line
    pid_matches = list(_PID_RE.finditer(line))
    if len(pid_matches) >= 2:
        return True

    return False


def _has_strong_anchor(line: str, line_lower: str) -> bool:
    """
    Return True if the line matched a strong anchor:
    - Any STRING_ANCHORS_EXACT hit (Sysmon fields, arrows, tree glyphs)
    - Strong regex: P3, P4, P5, P7, P8
    - Structural: T3, T4, T5
    """
    # String anchors are all strong
    for anchor in STRING_ANCHORS_EXACT:
        if anchor.lower() in line_lower:
            return True

    # Strong regex indices
    for idx in _STRONG_REGEX_INDICES:
        if REGEX_ANCHORS[idx].search(line):
            return True

    # Structural rules are all strong
    if _line_matches_structural_rules(line):
        return True

    return False


def _is_narrative_only(line: str, matched_strong_anchor: bool) -> bool:
    """
    True when the ONLY reason the line matched is a weak verb-based anchor (P1, P2, P6)
    with no process-specific context. If matched_strong_anchor=True, never suppress.

    A weak match is suppressed iff:
    - No strong anchor fired
    - No .exe token from KNOWN_PROCESS_TOKENS appears on the line
    - No arrow/tree glyph on the line
    """
    if matched_strong_anchor:
        return False

    # Check for executable-shape tokens
    if _EXE_SHAPE_RE.search(line):
        return False

    # Check for path indicators
    if _PATH_INDICATOR_RE.search(line):
        return False

    # Check for arrow/tree glyphs
    return all(glyph not in line for glyph in _ARROW_TREE_GLYPHS)


def _is_tree_glyph_line(line: str) -> bool:
    """Return True if line starts with a tree-drawing prefix or matched P8."""
    stripped = line.lstrip()
    # Check tree glyphs at start of stripped line
    tree_prefixes = ("\u2514", "\u251c", "\\->", "|-", "\u2502")
    if any(stripped.startswith(p) for p in tree_prefixes):
        return True
    # P8 regex match
    return bool(REGEX_ANCHORS[8].search(line))  # P8 is now index 8


def _extract_snippet(
    line: str,
    lines: list[str],
    line_idx: int,
    *,
    byte_preserving: bool = False,
    adjacent: int = ADJACENT_LINES_DEFAULT,
) -> str:
    """
    Extract matching line + surrounding context lines.
    byte_preserving: always use full-line capture (no sentence split).
    adjacent: number of context lines above and below.
    """
    start = max(0, line_idx - adjacent)
    end = min(len(lines), line_idx + adjacent + 1)
    return "\n".join(lines[start:end]).strip()


def _extract_windowed_snippets(
    line: str,
    lines: list[str],
    line_idx: int,
    line_lower: str,
    *,
    byte_preserving: bool = False,
    adjacent: int = ADJACENT_LINES_DEFAULT,
) -> list[str]:
    """
    For long lines (>LONG_LINE_THRESHOLD): extract match-window snippets.
    byte_preserving: use newline-only boundaries (no sentence/period split).

    Overlapping windows are merged before extraction to avoid emitting
    overlapping byte ranges as separate snippets.
    """
    positions = _find_match_positions(line, line_lower)
    if not positions:
        return []

    # Compute raw windows, merge overlapping/adjacent ranges
    raw: list[tuple[int, int]] = sorted(
        (max(0, start - MATCH_WINDOW_CHARS), min(len(line), end + MATCH_WINDOW_CHARS)) for start, end in positions
    )
    merged: list[tuple[int, int]] = []
    for ws, we in raw:
        if merged and ws <= merged[-1][1] + 1:  # overlap or within 1 char
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
    prev_lines = lines[max(0, line_idx - adjacent) : line_idx]
    next_lines = lines[line_idx + 1 : min(len(lines), line_idx + adjacent + 1)]
    if (prev_lines or next_lines) and snippets:
        parts = [*prev_lines, snippets[0], *next_lines]
        parts = [p for p in parts if p]
        snippets[0] = "\n".join(parts).strip()
    return snippets


def process(
    article_text: str,
    agent_name: str | None = None,
    max_snippets: int | None = None,
) -> dict[str, Any]:
    """
    Scan article for high-likelihood process lineage regions and return structured payload.

    Args:
        article_text: Raw article content.
        agent_name: When "ProcTreeExtract", enables byte-preserving mode (disables sentence
            split). Required by HARD CONTRACT.
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
    byte-identical to the source.

    Note on max_snippets: excess entries are dropped from the END, preserving
    the earliest (highest-signal) matches. This is intentional -- process
    lineage sections typically appear early in structured reports.
    """
    if not article_text or not article_text.strip():
        return {"high_likelihood_snippets": [], "full_article": article_text or ""}

    # ProcTreeExtract: byte-preserving with respect to newline boundaries (HARD CONTRACT)
    byte_preserving = agent_name == "ProcTreeExtract"

    lines = article_text.splitlines()
    seen: set[str] = set()
    snippets_ordered: list[str] = []

    for i, line in enumerate(lines):
        line_lower = line.lower()
        anchor_match = _line_matches_anchor(line, line_lower)
        structural_match = _line_matches_structural_rules(line)

        if not anchor_match and not structural_match:
            continue

        # Determine strong anchor status and check narrative suppression
        strong = _has_strong_anchor(line, line_lower)
        if _is_narrative_only(line, strong):
            continue

        # Determine adjacent context lines
        adjacent = ADJACENT_LINES_TREE_GLYPH if _is_tree_glyph_line(line) else ADJACENT_LINES_DEFAULT

        # Long line: match-window capture
        if len(line) > LONG_LINE_THRESHOLD:
            windowed = _extract_windowed_snippets(
                line,
                lines,
                i,
                line_lower,
                byte_preserving=byte_preserving,
                adjacent=adjacent,
            )
            for snippet in windowed:
                if not snippet or snippet in seen:
                    continue
                seen.add(snippet)
                snippets_ordered.append(snippet)
            continue

        # Short line: full-line capture
        snippet = _extract_snippet(
            line,
            lines,
            i,
            byte_preserving=byte_preserving,
            adjacent=adjacent,
        )
        if not snippet or snippet in seen:
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
    winword.exe spawned powershell.exe with encoded command.
    ParentImage: C:\\Windows\\System32\\services.exe
    Image: C:\\Windows\\System32\\svchost.exe
    PID: 1234, PPID: 5678
    """
    result = process(example)
    print("Snippets:", len(result["high_likelihood_snippets"]))
    for s in result["high_likelihood_snippets"]:
        print("  -", repr(s[:80] + "..." if len(s) > 80 else s))
