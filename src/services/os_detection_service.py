"""OS Detection Service for CTI Scraper

``detect_os`` is entity-driven: the keyword registry (``project_platform``) decides,
with a Windows keyword safety net for low-signal content and LLM adjudication for the
Unknown tail (``platform_adjudicator``). Scoring-time verdicts (``precomputed``,
Phase 3) are consumed as-is, skipping redundant re-scans for articles that have
already been classified at ingest time.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Windows OS keyword indicators (for fast keyword-based detection)
WINDOWS_OS_KEYWORDS = [
    # Windows executables
    "powershell.exe",
    "cmd.exe",
    "wmic.exe",
    "reg.exe",
    "rundll32.exe",
    "msiexec.exe",
    "svchost.exe",
    "lsass.exe",
    "winlogon.exe",
    "conhost.exe",
    "wscript.exe",
    "services.exe",
    "findstr.exe",
    "comspec",
    # Windows paths & environment
    "C:\\",
    "D:\\",
    "%WINDIR%",
    "%wintmp%",
    "%APPDATA%",
    "%TEMP%",
    "\\temp\\",
    "\\pipe\\",
    "system32",
    "programdata",
    "appdata",
    # Windows registry
    "hklm",
    "hkcu",
    "HKEY",
    # Windows file extensions
    ".exe",
    ".dll",
    ".bat",
    ".ps1",
    ".lnk",
    # Windows-specific patterns
    "Event ID",
    "EventCode",
    "Sysmon",
    "Windows Event Logs",
    "WMI",
    "schtasks",
    "scheduled tasks",
    # Windows commands
    "icacls",
    "attrib",
    "tasklist",
    "systeminfo",
]


class OSDetectionService:
    """OS detection: entity-driven keyword registry with Windows safety net.

    Detection order:
    1. Precomputed verdict from article_metadata["os_classification"] (Phase 3).
    2. Fresh registry scan via project_platform() when no precomputed verdict.
    3. Windows keyword safety net for thin-evidence (low-confidence) content.
    4. Unknown — LLM adjudication (platform_adjudicator) handles this tail externally.

    All detection is stateless; no model loading occurs on construction.
    """

    def _check_windows_keywords(self, content: str, min_matches: int = 3) -> dict[str, Any] | None:
        """Check for Windows OS keywords in content.

        Returns a Windows verdict dict if >= min_matches, None otherwise.
        """
        if not content:
            return None

        content_lower = content.lower()
        matches = []

        for keyword in WINDOWS_OS_KEYWORDS:
            keyword_lower = keyword.lower()
            if keyword_lower in content_lower:
                matches.append(keyword)

        match_count = len(matches)

        if match_count >= min_matches:
            logger.info(f"Windows OS detected via keywords: {match_count} matches (threshold: {min_matches})")
            return {
                "operating_system": "Windows",
                "method": "keyword_match",
                "confidence": "high",
                "keyword_matches": match_count,
                "matched_keywords": matches[:10],
            }

        logger.debug(f"Windows keyword check: {match_count} matches (threshold: {min_matches}), returning Unknown")
        return None

    async def detect_os(
        self,
        content: str,
        min_windows_keywords: int = 3,
        precomputed: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Detect OS from content.

        Detection order (entity-driven; embedding paths retired):
        1. Deterministic verdict — the ingest-time verdict (``precomputed``, Phase 3) when
           supplied, else a fresh scan against the keyword registry (``project_platform``).
        2. Windows keyword safety net for low-evidence content (deterministic).
        3. Otherwise Unknown (Phase B adjudicates this tail with an LLM externally).

        ``precomputed`` is ``article_metadata["os_classification"]`` computed at scoring time
        (Phase 2); consuming it avoids re-scanning the same content. Articles ingested before
        Phase 2 have no stored verdict and fall back to the fresh scan (go-forward).

        Args:
            content: Article content.
            min_windows_keywords: Keyword match count for the deterministic Windows safety net.
            precomputed: Verdict computed at scoring time; returned as-is when not low-confidence.

        Returns:
            Dict with operating_system, method, and confidence.
        """
        # Step 1: deterministic verdict — reuse the scoring-time verdict, else scan fresh against
        # the keyword registry (the single platform-vocabulary source of truth).
        if precomputed is not None:
            verdict = precomputed
            confidence = precomputed.get("confidence")
            source = "precomputed"
        else:
            from src.utils.keyword_registry import project_platform

            kb = project_platform(content)
            verdict = kb.as_os_result()
            confidence = kb.confidence
            source = "registry scan"

        if confidence != "low":
            logger.info(f"Platform verdict ({source}): {verdict.get('platforms_detected')} (confidence={confidence})")
            return verdict

        # Step 2: deterministic Windows keyword safety net for thin evidence.
        keyword_result = self._check_windows_keywords(content, min_matches=min_windows_keywords)
        if keyword_result:
            return keyword_result

        # Step 3: genuinely insufficient signal -> Unknown (no embedding guesswork).
        logger.info(f"Platform classification inconclusive ({source}, confidence=low); returning Unknown")
        return verdict
