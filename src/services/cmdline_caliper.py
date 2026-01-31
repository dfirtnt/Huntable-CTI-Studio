"""
Command-line extraction service powered by the CMDCaliper sentence transformer.

Uses sentence embeddings to detect command-line-like statements in article content.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

try:
    from sentence_transformers import SentenceTransformer, util
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment]
    util = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "CyCraftAI/CmdCaliper-small"
COMMAND_CONTEXT_WINDOW = 80
MAX_LINE_LENGTH = 800
MIN_LINE_LENGTH = 10
MAX_CANDIDATES = 200

# Example command prototypes used to calibrate similarity scores
PROTOTYPE_COMMANDS = [
    "cmd.exe /c whoami",
    "powershell -NoProfile -Command Get-Process",
    "bash -c ls -la /etc",
    "sudo systemctl restart sshd",
    "curl -X POST https://example.com/api -H 'Content-Type: application/json'",
    "git clone https://github.com/example/repo.git",
    "az login --identity",
    "python -m pip install -r requirements.txt",
]

# Command-like regex used for fallback extraction (wrap in a capture group for reuse)
COMMAND_REGEX = re.compile(r"""(?xi)
(?:
    # PowerShell one-liners
    \biex\s*\([^\r\n]{5,}\)
    |
    # PowerShell with interpreter
    \b(?:powershell|pwsh)(?:\.exe)?\s+[^\r\n]+
    |
    # cmd.exe execution
    \bcmd(?:\.exe)?\s+/[ck]\s+[^\r\n]+
    |
    # Full Windows paths with arguments
    \b[a-zA-Z]:\\[^\r\n<>":|?*]+\.exe\s+[^\r\n]+
    |
    # Quoted executables WITH arguments
    ["'][^"'\r\n]+\.exe["']\s+[^\r\n]+
    |
    # Native utilities
    \b(?:nltest|net|reg|wmic|tasklist|whoami|ipconfig|systeminfo|
        ping|nslookup|bcdedit|vssadmin|schtasks|netstat|query\s+user
    )\s+[^\r\n]+
    |
    # LOLBins
    \b(?:rundll32|regsvr32|mshta|wscript|cscript|certutil|bitsadmin|
        sc|sqlcmd|rclone|ntdsutil|msiexec|forfiles|pcalua
    )(?:\.exe)?\s+[^\r\n]+
    |
    # Bare executables with arguments only
    \b[a-zA-Z0-9_.-]+\.exe\s+[^\r\n]{1,500}
)
""")


class CommandLineCaliperExtractor:
    """Wraps the CMDCaliper sentence-transformer model for command detection."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        device: str | None = None,
        hf_token_env: list[str] | None = None,
    ):
        self.model_name = model_name
        self.device = device
        self.hf_token_env = hf_token_env or [
            "HUGGINGFACE_API_TOKEN",
            "HF_API_TOKEN",
            "HUGGINGFACE_HUB_TOKEN",
        ]
        self._model: SentenceTransformer | None = None
        self._prototype_embeddings = None
        self._override_token: str | None = None

    @property
    def auth_token(self) -> str | None:
        if self._override_token:
            return self._override_token
        for env_var in self.hf_token_env:
            token = os.getenv(env_var)
            if token:
                return token
        return None

    def set_auth_token(self, token: str | None) -> None:
        """Allow callers to provide a token (e.g., from AppSettings) without mutating env."""
        self._override_token = token or None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        if SentenceTransformer is None or util is None:
            raise RuntimeError(
                "sentence-transformers is required for CMDCaliper extraction. "
                "Install it with `pip install sentence-transformers`."
            )
        kwargs: dict[str, Any] = {}
        if self.device:
            kwargs["device"] = self.device
        token = self.auth_token
        if token:
            # Use modern HF hub token parameter; avoid passing both to prevent conflicts
            kwargs["token"] = token
        try:
            self._model = SentenceTransformer(self.model_name, **kwargs)
            # Pre-compute prototype embeddings (normalized)
            self._prototype_embeddings = self._model.encode(
                PROTOTYPE_COMMANDS,
                convert_to_tensor=True,
                normalize_embeddings=True,
            )
        except Exception as exc:
            logger.error("Failed to load CMDCaliper model %s: %s", self.model_name, exc)
            raise

    def _extract_candidate_lines(self, content: str, max_candidates: int = MAX_CANDIDATES) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        min_words = 2

        # Primary segmentation: newlines
        segments = content.splitlines()

        # Fallback segmentation: break long, single-line content on common delimiters
        if len(segments) <= 1:
            segments = re.split(r"(?<=[;|])\s+|(?<=\.)\s+|(?<=,)\s+", content)

        offset = 0
        for segment in segments:
            if not segment:
                offset += 1
                continue

            trimmed = segment.strip()
            if not trimmed or len(trimmed) < MIN_LINE_LENGTH or len(trimmed) > MAX_LINE_LENGTH:
                offset += len(segment) + 1
                continue
            if len(trimmed.split()) < min_words and not re.search(r"[\\/=]", trimmed):
                offset += len(segment) + 1
                continue
            if not re.search(r"(\\\\|/|\\.exe\\b|powershell|cmd\\.exe|bash\\s+-c|--)", trimmed, re.IGNORECASE):
                offset += len(segment) + 1
                continue

            start = content.find(trimmed, offset)
            if start == -1:
                start = offset
            end = start + len(trimmed)
            context = self._extract_context(content, start, end)
            candidates.append(
                {
                    "text": trimmed,
                    "start": start,
                    "end": end,
                    "context": context,
                }
            )
            if len(candidates) >= max_candidates:
                break
            offset = end + 1

        # Extract embedded command-like substrings from existing segments to tighten noisy lines
        command_pattern = COMMAND_REGEX
        if candidates:
            expanded: list[dict[str, Any]] = []
            for candidate in candidates:
                # Targeted subcommand extraction around .exe tokens
                for sub in re.finditer(
                    r"\"[^\"]*?\.exe[^\"]*\"|\b\S*?\.exe\S*(?:\s+\S+){0,6}",
                    candidate["text"],
                    re.IGNORECASE,
                ):
                    text = sub.group(0).strip()
                    if len(text) < MIN_LINE_LENGTH or len(text) > MAX_LINE_LENGTH:
                        continue
                    start = candidate["start"] + sub.start(0)
                    end = start + len(text)
                    expanded.append(
                        {
                            "text": text,
                            "start": start,
                            "end": end,
                            "context": self._extract_context(content, start, end),
                        }
                    )

                for match in command_pattern.finditer(candidate["text"]):
                    text = match.group(0).strip()
                    if len(text) < MIN_LINE_LENGTH or len(text) > MAX_LINE_LENGTH:
                        continue
                    start = candidate["start"] + match.start(0)
                    end = start + len(text)
                    expanded.append(
                        {
                            "text": text,
                            "start": start,
                            "end": end,
                            "context": self._extract_context(content, start, end),
                        }
                    )
            candidates.extend(expanded)

        # Secondary fallback: extract command-like spans directly from the content
        if len(candidates) < max_candidates:
            for match in command_pattern.finditer(content):
                text = match.group(0).strip()
                if len(text) < MIN_LINE_LENGTH or len(text) > MAX_LINE_LENGTH:
                    continue
                start = match.start(0)
                end = match.end(0)
                context = self._extract_context(content, start, end)
                candidates.append(
                    {
                        "text": text,
                        "start": start,
                        "end": end,
                        "context": context,
                    }
                )
                if len(candidates) >= max_candidates:
                    break

        return candidates

    def _extract_context(self, content: str, start: int, end: int, window: int = COMMAND_CONTEXT_WINDOW) -> str:
        left = max(0, start - window)
        right = min(len(content), end + window)
        snippet = content[left:right]
        return snippet.replace("\n", " ").replace("\r", " ").strip()

    def extract(
        self,
        content: str,
        similarity_threshold: float = 0.7,
        max_results: int = 20,
        max_candidates: int = 200,
    ) -> list[dict[str, Any]]:
        """
        Extract command-line-like sentences using CMDCaliper embeddings.

        Args:
            content: Text content to scan for commands.
            similarity_threshold: Minimum cosine similarity to accept a candidate.
            max_results: Number of commands to return.
            max_candidates: Number of candidate lines to score.

        Returns:
            Sorted list of command line dicts with `text`, `start`, `end`, `context`, and `score`.
        """
        if not content or len(content.strip()) == 0:
            return []

        self._ensure_model()
        if self._model is None or self._prototype_embeddings is None:
            return []

        candidates = self._extract_candidate_lines(content, max_candidates=max_candidates)
        if not candidates:
            return []

        texts = [cand["text"] for cand in candidates]
        embeddings = self._model.encode(texts, convert_to_tensor=True, normalize_embeddings=True)
        similarity_matrix = util.cos_sim(embeddings, self._prototype_embeddings)

        def _dedupe(entries):
            seen = set()
            unique = []
            for entry in entries:
                key = entry["text"]
                if key in seen:
                    continue
                seen.add(key)
                unique.append(entry)
            return unique

        def _has_arguments(text: str) -> bool:
            return bool(re.search(r"\.exe\b\s+\S", text, re.IGNORECASE))

        results = []
        for idx, candidate in enumerate(candidates):
            scores = similarity_matrix[idx]
            if scores.numel() == 0:
                continue
            max_score = float(scores.max().item())
            if max_score < similarity_threshold:
                continue
            if not _has_arguments(candidate["text"]):
                continue
            entry = {
                "text": candidate["text"],
                "start": candidate["start"],
                "end": candidate["end"],
                "context": candidate["context"],
                "score": max_score,
            }
            results.append(entry)
        results.sort(key=lambda value: value["score"], reverse=True)
        if results:
            return _dedupe(results)[:max_results]

        # Relaxed pass with lower threshold to avoid missing noisy but valid commands
        relaxed_threshold = 0.05
        relaxed_results = []
        for idx, candidate in enumerate(candidates):
            scores = similarity_matrix[idx]
            if scores.numel() == 0:
                continue
            max_score = float(scores.max().item())
            if max_score < relaxed_threshold:
                continue
            if not _has_arguments(candidate["text"]):
                continue
            relaxed_results.append(
                {
                    "text": candidate["text"],
                    "start": candidate["start"],
                    "end": candidate["end"],
                    "context": candidate["context"],
                    "score": max_score,
                }
            )
        if relaxed_results:
            relaxed_results.sort(key=lambda value: value["score"], reverse=True)
            return _dedupe(relaxed_results)[:max_results]

        # Heuristic fallback: emit regex-detected command-like strings when embeddings are too strict
        regex_hits = []
        seen = set()
        for match in COMMAND_REGEX.finditer(content):
            text = match.group(0).strip()
            if len(text) < MIN_LINE_LENGTH or len(text) > MAX_LINE_LENGTH:
                continue
            if text in seen:
                continue
            seen.add(text)
            regex_hits.append(
                {
                    "text": text,
                    "start": match.start(0),
                    "end": match.end(0),
                    "context": self._extract_context(content, match.start(0), match.end(0)),
                    "score": 0.0,
                }
            )
            if len(regex_hits) >= max_results:
                break
        return _dedupe(regex_hits)[:max_results]


command_line_caliper_extractor = CommandLineCaliperExtractor()
