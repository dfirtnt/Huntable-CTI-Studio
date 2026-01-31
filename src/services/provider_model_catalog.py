import json
from pathlib import Path

from fastapi import HTTPException

CATALOG_PATH = Path(__file__).resolve().parents[2] / "config" / "provider_model_catalog.json"
DEFAULT_CATALOG = {
    "openai": [
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
        "claude-2.1",
        "claude-2.0",
        "claude-instant-1.2",
    ],
    "gemini": [
        "gemini-2.0-pro-exp",
        "gemini-1.5-pro-latest",
        "gemini-1.5-pro",
        "gemini-1.5-pro-002",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash-002",
        "gemini-1.5-flash-8b",
        "gemini-1.5-flash-8b-latest",
        "gemini-1.0-pro",
        "gemini-1.0-pro-latest",
    ],
}


def load_catalog() -> dict[str, list[str]]:
    if not CATALOG_PATH.exists():
        return DEFAULT_CATALOG.copy()
    try:
        return json.loads(CATALOG_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid provider catalog: {exc}") from exc


def save_catalog(catalog: dict[str, list[str]]) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG_PATH, "w") as f:
        json.dump(catalog, f, indent=2, sort_keys=True)


def update_provider_models(provider: str, models: list[str]) -> dict[str, list[str]]:
    catalog = load_catalog()
    catalog[provider] = models
    save_catalog(catalog)
    return catalog
