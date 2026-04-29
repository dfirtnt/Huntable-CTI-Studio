import json
from pathlib import Path

from fastapi import HTTPException

from src.utils.model_validation import (
    filter_anthropic_models_latest_only,
    filter_openai_models_latest_only,
    filter_openai_models_project_allowlist,
)

CATALOG_PATH = Path(__file__).resolve().parents[2] / "config" / "provider_model_catalog.json"
DEFAULT_CATALOG = {
    "openai": [
        "gpt-5",
        "gpt-5-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4.1-turbo",
        "gpt-4.1-realtime-preview",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4o-realtime-preview-2024-12-17",
        "gpt-4o-mini-tts",
        "gpt-4o-mini-transcribe",
        "o4",
        "o4-mini",
        "o3-mini",
        "o3-mini-high",
        "o3-mini-low",
        "o1",
        "o1-mini",
        "o1-preview",
        "o1-lite",
    ],
    "anthropic": [
        "claude-3.7-sonnet-latest",
        "claude-3.7-sonnet-20250219",
        "claude-3.7-haiku-latest",
        "claude-3.7-haiku-20250219",
        "claude-3.6-sonnet-20250108",
        "claude-3.6-haiku-20250108",
        "claude-3.5-sonnet-20241022",
        "claude-3.5-haiku-20241022",
        "claude-3.5-sonnet-latest",
        "claude-3.5-haiku-latest",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
        "claude-sonnet-4-6",
        "claude-2.1",
        "claude-2.0",
        "claude-instant-1.2",
    ],
}


MODEL_CONTEXT_TOKENS: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4.1": 1_047_576,
    "gpt-4.1-mini": 1_047_576,
    "gpt-4.1-nano": 1_047_576,
    "gpt-4.1-turbo": 1_047_576,
    "gpt-5": 128_000,
    "gpt-5-mini": 128_000,
    "o1": 128_000,
    "o1-mini": 128_000,
    "o1-preview": 128_000,
    "o1-lite": 128_000,
    "o3-mini": 200_000,
    "o3-mini-high": 200_000,
    "o3-mini-low": 200_000,
    "o4": 200_000,
    "o4-mini": 200_000,
    "claude-3-opus-20240229": 200_000,
    "claude-3-sonnet-20240229": 200_000,
    "claude-3-haiku-20240307": 200_000,
    "claude-3.5-sonnet-20241022": 200_000,
    "claude-3.5-haiku-20241022": 200_000,
    "claude-3.5-sonnet-latest": 200_000,
    "claude-3.5-haiku-latest": 200_000,
    "claude-3.6-sonnet-20250108": 200_000,
    "claude-3.6-haiku-20250108": 200_000,
    "claude-3.7-sonnet-20250219": 200_000,
    "claude-3.7-haiku-20250219": 200_000,
    "claude-3.7-sonnet-latest": 200_000,
    "claude-3.7-haiku-latest": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-2.1": 200_000,
    "claude-2.0": 100_000,
    "claude-instant-1.2": 100_000,
}


def get_model_context_tokens(model_name: str) -> int | None:
    return MODEL_CONTEXT_TOKENS.get(model_name)


def load_catalog() -> dict[str, list[str]]:
    if not CATALOG_PATH.exists():
        catalog = DEFAULT_CATALOG.copy()
    else:
        try:
            catalog = json.loads(CATALOG_PATH.read_text())
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"Invalid provider catalog: {exc}") from exc
    # Anthropic: show only latest per family (no datestamped variants)
    if "anthropic" in catalog and catalog["anthropic"]:
        catalog["anthropic"] = filter_anthropic_models_latest_only(catalog["anthropic"])
    # OpenAI: chat-only, latest only (no -YYYY-MM-DD dated variants), then narrow to
    # the project-workflow allowlist so dropdowns show only models the pipeline uses.
    if "openai" in catalog and catalog["openai"]:
        catalog["openai"] = filter_openai_models_project_allowlist(filter_openai_models_latest_only(catalog["openai"]))
    return catalog


def save_catalog(catalog: dict[str, list[str]]) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG_PATH, "w") as f:
        json.dump(catalog, f, indent=2, sort_keys=True)


def update_provider_models(provider: str, models: list[str]) -> dict[str, list[str]]:
    catalog = load_catalog()
    catalog[provider] = models
    save_catalog(catalog)
    return catalog
