"""Test environment helpers.

Handles .env loading, cloud-key stripping, and CI detection.
These functions mutate os.environ and must be called early in the
runner's startup sequence before any subprocess is spawned.
"""

from __future__ import annotations

import os
from pathlib import Path

# Project root is one level above this file's directory (tests_runner/).
_project_root = Path(__file__).parent.parent

# Keys from .env that must not be applied in test (guard: TEST_DATABASE_URL only).
# Cloud LLM keys are skipped so they are not loaded from .env into the test process.
_DOTENV_SKIP_IN_TEST = frozenset(
    {
        "DATABASE_URL",
        "REDIS_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "CHATGPT_API_KEY",
    }
)

_CLOUD_LLM_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CHATGPT_API_KEY")


def strip_cloud_llm_keys() -> None:
    """Remove cloud LLM keys from this process so tests never hit commercial APIs.

    Skipped if ALLOW_CLOUD_LLM_IN_TESTS=true.
    """
    if os.getenv("ALLOW_CLOUD_LLM_IN_TESTS", "").lower() in ("true", "1", "yes"):
        return
    for key in _CLOUD_LLM_KEYS:
        os.environ.pop(key, None)


def load_dotenv(project_root: Path | None = None) -> None:
    """Load .env from project root so POSTGRES_PASSWORD etc. match running Postgres.

    Does not override existing env vars. Skips DATABASE_URL so the test guard
    (TEST_DATABASE_URL only) continues to work correctly.
    """
    env_file = (project_root or _project_root) / ".env"
    if not env_file.is_file():
        return
    try:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key in _DOTENV_SKIP_IN_TEST:
                    continue
                value = value.strip().strip("'\"").strip()
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


def in_ci() -> bool:
    """Return True when running inside a CI environment (GitHub Actions or generic CI)."""
    return os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"
