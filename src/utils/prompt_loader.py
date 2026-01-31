"""
Prompt loader utility for CTIScraper AI endpoints.

This module provides a centralized way to load and format prompts from text files,
making it easier to maintain and update AI prompts without modifying code.
"""

import logging
from pathlib import Path
from typing import Any

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
