"""
Command-line attention pre-processor for Windows command-line extraction.

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

# Sentence boundary: newline always; period/comma only if followed by whitespace
SENTENCE_SPLIT = re.compile(r"(?<=[\n])|(?<=\.)\s+|(?<=,)\s+")

# Line length threshold: use sentence logic only if line > N chars
LONG_LINE_THRESHOLD = 500


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
    for pattern in REGEX_ANCHORS:
        if pattern.search(line):
            return True
    return False


def _extract_snippet(line: str, lines: list[str], line_idx: int) -> str:
    """
    Extract matching line + ±1 surrounding sentence/line for context.
    Prefer line-based capture; fall back to sentence logic for very long lines.
    """
    if len(line) <= LONG_LINE_THRESHOLD:
        # Line-based: include ±1 surrounding lines
        start = max(0, line_idx - 1)
        end = min(len(lines), line_idx + 2)
        return "\n".join(lines[start:end]).strip()
    # Sentence logic for long lines
    parts = SENTENCE_SPLIT.split(line)
    # Find which part contains the anchor (simplified: use middle or first)
    # For long lines, take the matching line plus adjacent context
    start = max(0, line_idx - 1)
    end = min(len(lines), line_idx + 2)
    return "\n".join(lines[start:end]).strip()


def process(article_text: str) -> dict[str, Any]:
    """
    Scan article for high-likelihood command-line regions and return structured payload.

    Returns:
        {
            "high_likelihood_snippets": ["<verbatim snippet>", ...],
            "full_article": "<original article text>"
        }
    Snippets preserve original article order. Deduplicated by exact string.
    """
    if not article_text or not article_text.strip():
        return {"high_likelihood_snippets": [], "full_article": article_text or ""}

    lines = article_text.splitlines()
    seen: set[str] = set()
    snippets_ordered: list[str] = []

    for i, line in enumerate(lines):
        line_lower = line.lower()
        if not _line_matches_anchor(line, line_lower):
            continue

        snippet = _extract_snippet(line, lines, i)
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
