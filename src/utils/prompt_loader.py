"""
Prompt loader utility for CTIScraper AI endpoints.

This module provides a centralized way to load and format prompts from text files,
making it easier to maintain and update AI prompts without modifying code.
"""

import logging
import re
from pathlib import Path
from typing import Any

# Matches any Python str.format-style placeholder: {identifier} or {identifier!r} etc.
# Used to distinguish user-message templates (have placeholders) from system personas (don't).
_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*[^{]*?\}")

logger = logging.getLogger(__name__)


class PromptLoader:
    """Loads and formats prompts from text files."""

    def __init__(self, prompts_dir: str = "src/prompts"):
        """
        Initialize the prompt loader.

        Args:
            prompts_dir: Directory containing prompt files
        """
        self.prompts_dir = Path(prompts_dir)
        self._prompt_cache: dict[str, str] = {}

        # Ensure prompts directory exists
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory {self.prompts_dir} does not exist")

    def load_prompt(self, prompt_name: str) -> str:
        """
        Load a prompt from a text file (synchronous).

        Args:
            prompt_name: Name of the prompt file (without .txt extension)

        Returns:
            The prompt content as a string

        Raises:
            FileNotFoundError: If the prompt file doesn't exist
        """
        if prompt_name in self._prompt_cache:
            return self._prompt_cache[prompt_name]

        prompt_file = self.prompts_dir / f"{prompt_name}.txt"

        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file {prompt_file} not found")

        try:
            with open(prompt_file, encoding="utf-8") as f:
                content = f.read().strip()
                self._prompt_cache[prompt_name] = content
                return content
        except Exception as e:
            logger.error(f"Error loading prompt {prompt_name}: {e}")
            raise

    async def load_prompt_async(self, prompt_name: str) -> str:
        """
        Load a prompt from a text file (async, non-blocking).

        Args:
            prompt_name: Name of the prompt file (without .txt extension)

        Returns:
            The prompt content as a string

        Raises:
            FileNotFoundError: If the prompt file doesn't exist
        """
        if prompt_name in self._prompt_cache:
            return self._prompt_cache[prompt_name]

        prompt_file = self.prompts_dir / f"{prompt_name}.txt"

        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file {prompt_file} not found")

        try:
            import asyncio

            def _read_file():
                with open(prompt_file, encoding="utf-8") as f:
                    return f.read().strip()

            content = await asyncio.to_thread(_read_file)
            self._prompt_cache[prompt_name] = content
            return content
        except Exception as e:
            logger.error(f"Error loading prompt {prompt_name}: {e}")
            raise

    def format_prompt(self, prompt_name: str, **kwargs: Any) -> str:
        """
        Load and format a prompt with the given parameters (synchronous).

        Args:
            prompt_name: Name of the prompt file (without .txt extension)
            **kwargs: Parameters to format into the prompt

        Returns:
            The formatted prompt string
        """
        prompt_template = self.load_prompt(prompt_name)

        try:
            return prompt_template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing parameter {e} for prompt {prompt_name}")
            raise
        except Exception as e:
            logger.error(f"Error formatting prompt {prompt_name}: {e}")
            raise

    async def format_prompt_async(self, prompt_name: str, **kwargs: Any) -> str:
        """
        Load and format a prompt with the given parameters (async, non-blocking).

        Args:
            prompt_name: Name of the prompt file (without .txt extension)
            **kwargs: Parameters to format into the prompt

        Returns:
            The formatted prompt string
        """
        prompt_template = await self.load_prompt_async(prompt_name)

        try:
            return prompt_template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing parameter {e} for prompt {prompt_name}")
            raise
        except Exception as e:
            logger.error(f"Error formatting prompt {prompt_name}: {e}")
            raise

    def get_available_prompts(self) -> list[str]:
        """
        Get a list of available prompt files.

        Returns:
            List of prompt names (without .txt extension)
        """
        if not self.prompts_dir.exists():
            return []

        return [f.stem for f in self.prompts_dir.glob("*.txt")]

    def clear_cache(self):
        """Clear the prompt cache."""
        self._prompt_cache.clear()


# Global prompt loader instance
prompt_loader = PromptLoader()


# Convenience functions
def load_prompt(prompt_name: str) -> str:
    """Load a prompt by name (synchronous)."""
    return prompt_loader.load_prompt(prompt_name)


def format_prompt(prompt_name: str, **kwargs: Any) -> str:
    """Load and format a prompt with parameters (synchronous)."""
    return prompt_loader.format_prompt(prompt_name, **kwargs)


async def load_prompt_async(prompt_name: str) -> str:
    """Load a prompt by name (async, non-blocking)."""
    return await prompt_loader.load_prompt_async(prompt_name)


async def format_prompt_async(prompt_name: str, **kwargs: Any) -> str:
    """Load and format a prompt with parameters (async, non-blocking)."""
    return await prompt_loader.format_prompt_async(prompt_name, **kwargs)


def get_available_prompts() -> list[str]:
    """Get list of available prompts."""
    return prompt_loader.get_available_prompts()


def parse_sigma_agent_prompt_data(sigma_prompt_data: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Extract (user_template, system_prompt) from a SigmaAgent DB record.

    Canonical shape (post-migration):
      {"system": "<persona>", "user": "<template or null>", "instructions"?: ...}

    Legacy shapes still tolerated for unmigrated records:
      * Locked scaffold JSON:   {"prompt": "{\"role\":...,\"user_template\":...}", ...}
      * Extraction-agent JSON:  {"prompt": "{\"role\":...,\"task\":...,\"json_example\":...,\"instructions\":...}", ...}
      * Legacy simple JSON:     {"prompt": "{\"system\":...,\"user\":...}", ...}
      * Legacy raw text:        {"prompt": "<persona or template>", ...}
      * Sibling system_prompt:  {"prompt": "<template>", "system_prompt": "<persona>"}

    Returns a tuple (template, system). Either value may be None if not resolvable.
    """
    import json

    if not sigma_prompt_data:
        return (None, None)

    # Canonical shape: {system, user} at outer level. Detected by either key present
    # AND no nested 'prompt' key (legacy records always have 'prompt').
    if "prompt" not in sigma_prompt_data and ("system" in sigma_prompt_data or "user" in sigma_prompt_data):
        template = sigma_prompt_data.get("user") or None
        system = sigma_prompt_data.get("system") or None
        return (template, system)

    raw_prompt = sigma_prompt_data.get("prompt", "")
    template: str | None = None
    system: str | None = None

    if isinstance(raw_prompt, str) and raw_prompt:
        try:
            parsed = json.loads(raw_prompt)
        except (ValueError, json.JSONDecodeError):
            parsed = None

        if isinstance(parsed, dict) and parsed.get("user_template"):
            # Locked scaffold format
            template = parsed["user_template"]
            system = parsed.get("role") or parsed.get("system") or None
        elif isinstance(parsed, dict) and (parsed.get("user") or parsed.get("system")):
            # Legacy {system, user} format
            template = parsed.get("user") or raw_prompt
            system = parsed.get("system") or None
        elif isinstance(parsed, dict) and ("task" in parsed or "json_example" in parsed):
            # Extraction-agent save format: legacy records written when SigmaAgent was
            # mistakenly included in LOCKED_EXTRACTOR_AGENTS on the frontend and the save
            # path wrapped prompts as {"role": <system>, "task": "", "json_example": "{}",
            # "instructions": ""}. The UI no longer generates this shape for SigmaAgent.
            # No user template recoverable from this shape; treat role as system only.
            # Detect by key presence, not by role value, to handle empty role strings.
            system = parsed.get("role") or None
        elif parsed is None and (
            sigma_prompt_data.get("model") or not _TEMPLATE_PLACEHOLDER_RE.search(raw_prompt)
        ):
            # Auto-persist shape OR persona-only text: either saved alongside a
            # sibling "model" key, or the text has zero Python format placeholders
            # ({identifier}) and therefore cannot function as a user message
            # template.  In both cases treat as system persona; no user template present.
            system = raw_prompt or None
        else:
            # Legacy raw-text template (bootstrap default) — has at least one
            # {identifier} placeholder; treat as user message template verbatim.
            template = raw_prompt

    # Legacy sibling key still honored when the parsed JSON didn't carry a system.
    if not system and isinstance(sigma_prompt_data.get("system_prompt"), str):
        system = sigma_prompt_data["system_prompt"]

    return (template, system)


def parse_rank_agent_prompt_data(rank_prompt_data: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Extract (user_template, system_prompt) from a RankAgent DB record.

    Mirrors parse_sigma_agent_prompt_data but routes through _parse_rank_prompt
    for legacy JSON-encoded prompts (which support a different set of keys than
    SigmaAgent's locked-scaffold format).

    Canonical shape (post-migration):
      {"system": "<persona>", "user": "<template or null>", "instructions"?: ...}

    Legacy shapes:
      * Any of {role, user_template} / {system, user} / {prompt} JSON in the
        outer dict's 'prompt' key (handled by _parse_rank_prompt).
      * Raw text in 'prompt' (handled by _parse_rank_prompt's fallback).

    Returns a tuple (template, system). Either value may be None if not resolvable.
    """
    if not rank_prompt_data:
        return (None, None)

    # Canonical shape: {system, user} at outer level
    if "prompt" not in rank_prompt_data and ("system" in rank_prompt_data or "user" in rank_prompt_data):
        template = rank_prompt_data.get("user") or None
        system = rank_prompt_data.get("system") or None
        return (template, system)

    # Legacy: prompt field contains the (possibly JSON-encoded) string
    raw_prompt = rank_prompt_data.get("prompt", "")
    if not isinstance(raw_prompt, str) or not raw_prompt:
        return (None, None)

    # Reuse the existing JSON-shape parser; catches PreprocessInvariantError
    # only for legitimately malformed JSON-prompts (returns the raw string +
    # None system in those cases, so the caller can decide).
    try:
        from src.services.llm_service import PreprocessInvariantError, _parse_rank_prompt

        template, system = _parse_rank_prompt(raw_prompt)
    except PreprocessInvariantError:
        # JSON shape with empty system override -- preserve the prompt as
        # template, leave system unresolved so caller can fall back.
        return (raw_prompt, None)

    # If _parse_rank_prompt returned the raw text as both template and system,
    # disambiguate: text without {identifier} placeholders is a persona, not
    # a template.
    if template == raw_prompt and system is None and not _TEMPLATE_PLACEHOLDER_RE.search(raw_prompt):
        return (None, raw_prompt)

    return (template, system)


def parse_sigma_repair_prompt_data(repair_prompt_data: dict[str, Any] | None) -> str | None:
    """Extract the repair template string from a SigmaRepair DB record.

    The template must contain both {validation_errors} and {original_rule}
    placeholders so the caller can inject repair context.  If either is missing
    the saved value is a bare persona string (not a usable template) and this
    function returns None so the caller falls back to the file-based default.

    Returns the prompt string if valid, or None.
    """
    if not repair_prompt_data:
        return None

    raw_prompt = repair_prompt_data.get("prompt", "")
    if not isinstance(raw_prompt, str) or not raw_prompt:
        return None

    required = ("{validation_errors}", "{original_rule}")
    if not all(ph in raw_prompt for ph in required):
        logger.warning(
            "SigmaRepair prompt from DB is missing required placeholders "
            "({validation_errors} and/or {original_rule}); ignoring and using file-based default"
        )
        return None

    return raw_prompt
