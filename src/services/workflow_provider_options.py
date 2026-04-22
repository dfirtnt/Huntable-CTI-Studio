"""
Unified provider availability service for the workflow configuration UI.

Aggregates provider status from AppSettings (DB), the commercial model catalog,
and a live LM Studio health probe into a single server-owned response shape.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

from src.database.models import AppSettingsTable
from src.services.provider_model_catalog import load_catalog
from src.utils.lmstudio_url import get_lmstudio_base_url

logger = logging.getLogger(__name__)

_ENABLED_KEYS = {
    "lmstudio": "WORKFLOW_LMSTUDIO_ENABLED",
    "openai": "WORKFLOW_OPENAI_ENABLED",
    "anthropic": "WORKFLOW_ANTHROPIC_ENABLED",
}

_API_KEY_SETTINGS = {
    "openai": "WORKFLOW_OPENAI_API_KEY",
    "anthropic": "WORKFLOW_ANTHROPIC_API_KEY",
}

_ENV_KEY_FALLBACKS = {
    "openai": ("WORKFLOW_OPENAI_API_KEY", "OPENAI_API_KEY"),
    "anthropic": ("WORKFLOW_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
}

_PROVIDER_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-6",
    "lmstudio": "",
}

_EMBEDDING_HINTS = ("embedding", "embed", "e5-base", "bge-", "gte-")

LMSTUDIO_PROBE_TIMEOUT = 5.0


@dataclass
class ProviderStatus:
    enabled: bool
    configured: bool
    reachable: bool
    has_models: bool
    models: list[str] = field(default_factory=list)
    default_model: str = ""
    reason_unavailable: str | None = None

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "reachable": self.reachable,
            "has_models": self.has_models,
            "models": self.models,
            "default_model": self.default_model,
            "reason_unavailable": self.reason_unavailable,
        }


def _is_embedding_model(model_id: str) -> bool:
    low = model_id.lower()
    return any(h in low for h in _EMBEDDING_HINTS)


async def _probe_lmstudio() -> tuple[bool, list[str]]:
    """Probe LM Studio /models. Returns (reachable, chat_model_ids)."""
    base = get_lmstudio_base_url("http://host.docker.internal:1234/v1")
    candidates: list[str] = [base]

    if "localhost" in base.lower() or "127.0.0.1" in base:
        alt = base.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
        if alt not in candidates:
            candidates.append(alt)

    try:
        async with httpx.AsyncClient(timeout=LMSTUDIO_PROBE_TIMEOUT) as client:
            for url in candidates:
                try:
                    resp = await client.get(f"{url}/models")
                except httpx.HTTPError:
                    continue
                if resp.status_code == 200:
                    data = resp.json()
                    all_ids = [m["id"] for m in data.get("data", [])]
                    chat = [m for m in all_ids if not _is_embedding_model(m)]
                    return True, chat
    except Exception as exc:
        logger.debug("LM Studio probe failed: %s", exc)

    return False, []


def _read_settings(db_session) -> dict[str, str]:
    """Return relevant settings from DB, with env fallback for API keys."""
    wanted = set(_ENABLED_KEYS.values()) | set(_API_KEY_SETTINGS.values())
    rows = db_session.query(AppSettingsTable).filter(AppSettingsTable.key.in_(wanted)).all()
    settings: dict[str, str] = {r.key: (r.value or "") for r in rows}

    # Env fallback for API keys not in DB
    for provider, env_keys in _ENV_KEY_FALLBACKS.items():
        settings_key = _API_KEY_SETTINGS[provider]
        if not settings.get(settings_key):
            for env_key in env_keys:
                val = os.getenv(env_key, "")
                if val:
                    settings[settings_key] = val
                    break

    # Env fallback for enable flags not in DB
    for provider, settings_key in _ENABLED_KEYS.items():
        if settings_key not in settings:
            settings[settings_key] = os.getenv(settings_key, "false")

    return settings


def _is_enabled(settings: dict[str, str], provider: str) -> bool:
    key = _ENABLED_KEYS.get(provider, "")
    return settings.get(key, "false").lower() == "true"


async def get_provider_options(db_session) -> dict:
    """
    Build unified provider availability map.

    Reads settings from the DB session, loads the commercial model catalog from
    disk, and probes LM Studio if it is enabled. Returns:

        {
            "providers": {
                "lmstudio": { enabled, configured, reachable, has_models,
                              models, default_model, reason_unavailable },
                "openai":   { ... },
                "anthropic": { ... },
            },
            "default_provider": "<first enabled+usable provider or ''>",
        }
    """
    settings = _read_settings(db_session)
    catalog = load_catalog()

    # -- LM Studio --
    lm_enabled = _is_enabled(settings, "lmstudio")
    lm_reachable, lm_models = False, []
    if lm_enabled:
        lm_reachable, lm_models = await _probe_lmstudio()

    if not lm_enabled:
        lm_reason: str | None = "Provider is not enabled in settings"
    elif not lm_reachable:
        lm_reason = "LMStudio is not reachable"
    elif not lm_models:
        lm_reason = "No chat models loaded in LMStudio"
    else:
        lm_reason = None

    lmstudio = ProviderStatus(
        enabled=lm_enabled,
        configured=lm_enabled,
        reachable=lm_reachable,
        has_models=bool(lm_models),
        models=lm_models,
        default_model=lm_models[0] if lm_models else "",
        reason_unavailable=lm_reason,
    )

    # -- OpenAI --
    oa_enabled = _is_enabled(settings, "openai")
    oa_key = settings.get("WORKFLOW_OPENAI_API_KEY", "")
    oa_configured = bool(oa_key)
    oa_models = catalog.get("openai", [])

    if not oa_enabled:
        oa_reason: str | None = "Provider is not enabled in settings"
    elif not oa_configured:
        oa_reason = "API key is not configured"
    else:
        oa_reason = None

    openai = ProviderStatus(
        enabled=oa_enabled,
        configured=oa_configured,
        reachable=oa_configured,
        has_models=bool(oa_models),
        models=oa_models,
        default_model=_PROVIDER_DEFAULT_MODELS["openai"],
        reason_unavailable=oa_reason,
    )

    # -- Anthropic --
    an_enabled = _is_enabled(settings, "anthropic")
    an_key = settings.get("WORKFLOW_ANTHROPIC_API_KEY", "")
    an_configured = bool(an_key)
    an_models = catalog.get("anthropic", [])

    if not an_enabled:
        an_reason: str | None = "Provider is not enabled in settings"
    elif not an_configured:
        an_reason = "API key is not configured"
    else:
        an_reason = None

    anthropic = ProviderStatus(
        enabled=an_enabled,
        configured=an_configured,
        reachable=an_configured,
        has_models=bool(an_models),
        models=an_models,
        default_model=_PROVIDER_DEFAULT_MODELS["anthropic"],
        reason_unavailable=an_reason,
    )

    providers: dict[str, ProviderStatus] = {
        "lmstudio": lmstudio,
        "openai": openai,
        "anthropic": anthropic,
    }

    # First provider that is both enabled and has usable models
    default_provider = ""
    for name, status in providers.items():
        if status.enabled and status.has_models:
            default_provider = name
            break

    return {
        "providers": {name: s.to_dict() for name, s in providers.items()},
        "default_provider": default_provider,
    }
