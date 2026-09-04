import json
import logging
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from src.utils.model_validation import (
    filter_anthropic_models_latest_only,
    filter_openai_models_latest_only,
    filter_openai_models_project_allowlist,
    heuristic_supports_variable_temperature,
)

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).resolve().parents[2] / "config" / "provider_model_catalog.json"
CAPABILITIES_PATH = Path(__file__).resolve().parents[2] / "config" / "model_capabilities.json"
DEFAULT_CATALOG = {
    "openai": [
        "gpt-5",
        "gpt-5-mini",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.5",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4.1-realtime-preview",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4o-realtime-preview-2024-12-17",
        "gpt-4o-mini-tts",
        "gpt-4o-mini-transcribe",
        "o4",
        "o4-mini",
        "o3",
        "o3-mini",
        "o3-mini-high",
        "o3-mini-low",
        "o1",
        "o1-mini",
        "o1-preview",
        "o1-lite",
    ],
    "anthropic": [
        "claude-fable-5",
        "claude-haiku-4-5-20251001",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-opus-4-5",
        "claude-3.7-sonnet-latest",
        "claude-3.7-sonnet-20250219",
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


# Default context windows by model id. Values are the default total context
# accepted by the API.
# Anthropic: Fable 5, Opus 4.6+, Sonnet 4.6+, and Opus 4.7 have 1M context by default
# (no beta header needed). Older 3.7/4.x models cap at 200K by default but can
# be extended to 1M with the `context-1m-2025-08-07` beta header; if you rely
# on that, branch on the header in the caller.
MODEL_CONTEXT_TOKENS: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4.1": 1_047_576,
    "gpt-4.1-mini": 1_047_576,
    "gpt-4.1-nano": 1_047_576,
    "gpt-5": 400_000,
    "gpt-5-mini": 400_000,
    "gpt-5-nano": 400_000,
    "gpt-5-pro": 400_000,
    "gpt-5-chat-latest": 128_000,
    "gpt-5.1": 400_000,
    "gpt-5.1-chat-latest": 128_000,
    "gpt-5.2": 400_000,
    "gpt-5.2-chat-latest": 128_000,
    "gpt-5.2-pro": 400_000,
    "gpt-5.3-chat-latest": 128_000,
    "gpt-5.4": 1_050_000,
    "gpt-5.4-mini": 400_000,
    "gpt-5.4-nano": 400_000,
    "gpt-5.4-pro": 1_050_000,
    "gpt-5.5": 1_050_000,
    "gpt-5.5-pro": 1_050_000,
    "gpt-5.6-luna": 1_050_000,
    "gpt-5.6-sol": 1_050_000,
    "gpt-5.6-terra": 1_050_000,
    "o1": 200_000,
    "o1-pro": 200_000,
    "o1-mini": 128_000,
    "o1-preview": 128_000,
    "o1-lite": 128_000,
    "o3": 200_000,
    "o3-pro": 200_000,
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
    "claude-3.7-sonnet-20250219": 200_000,
    "claude-3.7-sonnet-latest": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-sonnet-5": 1_000_000,
    "claude-opus-4-20250514": 200_000,
    "claude-opus-4-1-20250805": 200_000,
    "claude-opus-4-5": 200_000,
    "claude-opus-4-5-20251101": 200_000,
    "claude-opus-4-6": 1_000_000,
    "claude-opus-4-7": 1_000_000,
    "claude-opus-4-8": 1_000_000,
    "claude-opus-5": 1_000_000,
    "claude-fable-5": 1_000_000,
    "claude-fable-5-1": 1_000_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-sonnet-4-5-20250929": 200_000,
    "claude-2.1": 200_000,
    "claude-2.0": 100_000,
    "claude-instant-1.2": 100_000,
}


def get_model_context_tokens(model_name: str) -> int | None:
    return MODEL_CONTEXT_TOKENS.get(model_name)


# Providers whose model parameters are never sent by this app. The Codex adapter
# only forwards `effort`; its tiers come from model/list at request time, so the
# static file deliberately has no codex entries.
_LIVE_CAPABILITY_PROVIDERS = frozenset({"codex"})


@dataclass(frozen=True)
class ModelCapabilities:
    """What request parameters a (provider, model) pair accepts.

    `source` records where the answer came from: "catalog" for an entry in
    config/model_capabilities.json, "fallback" for the name-prefix heuristics that
    cover models the file does not know yet, and "live" for providers whose tiers
    are discovered at request time (Codex).
    """

    supports_temperature: bool
    supports_top_p: bool
    effort_levels: tuple[str, ...]
    default_effort: str | None
    source: str

    def to_dict(self) -> dict:
        return {
            "supports_temperature": self.supports_temperature,
            "supports_top_p": self.supports_top_p,
            "effort_levels": list(self.effort_levels),
            "default_effort": self.default_effort,
            "source": self.source,
        }


_capabilities_cache: tuple[float, dict[str, dict]] | None = None


def load_model_capabilities() -> dict[str, dict]:
    """Return the raw model-id -> capability mapping from config/model_capabilities.json.

    Cached on file mtime so the resolver stays cheap on the per-request paths that
    call it (every LLM call, every provider-options fetch) while still picking up a
    hand edit without a restart. An unreadable file degrades to {} -- every model
    then takes the fallback path -- rather than failing an unrelated request.
    """
    global _capabilities_cache
    try:
        mtime = CAPABILITIES_PATH.stat().st_mtime
    except OSError:
        return {}
    if _capabilities_cache and _capabilities_cache[0] == mtime:
        return _capabilities_cache[1]
    try:
        raw = json.loads(CAPABILITIES_PATH.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        logger.warning("Could not read %s: %s", CAPABILITIES_PATH.name, exc)
        return {}
    models = raw.get("models") if isinstance(raw, dict) else None
    models = models if isinstance(models, dict) else {}
    _capabilities_cache = (mtime, models)
    return models


def _fallback_capabilities(provider: str, model: str) -> ModelCapabilities:
    # The prefix heuristics only ever knew OpenAI reasoning families; for every
    # other provider an unknown model is assumed to take sampling parameters and no
    # effort tier, which is the only combination that cannot produce a 400.
    if provider in ("openai", "codex", ""):
        supports_sampling = heuristic_supports_variable_temperature(model)
    else:
        supports_sampling = True
    return ModelCapabilities(
        supports_temperature=supports_sampling,
        supports_top_p=supports_sampling,
        effort_levels=(),
        default_effort=None,
        source="fallback",
    )


def get_model_capabilities(provider: str | None, model: str | None) -> ModelCapabilities:
    """Resolve the parameter capabilities of a model.

    Catalog entries win. Unknown models fall back to the legacy name heuristics so
    a newly released model degrades to "no effort control, sampling as before"
    instead of raising. Codex is always `source="live"`: the adapter never sends
    temperature/top_p, and its effort tiers come from `model/list`.
    """
    provider = (provider or "").strip().lower()
    model = (model or "").strip()
    if provider in _LIVE_CAPABILITY_PROVIDERS:
        return ModelCapabilities(
            supports_temperature=False,
            supports_top_p=False,
            effort_levels=(),
            default_effort=None,
            source="live",
        )
    entry = load_model_capabilities().get(model) if model else None
    if not isinstance(entry, dict):
        return _fallback_capabilities(provider, model)
    levels = entry.get("effort_levels") or []
    default = entry.get("default_effort")
    return ModelCapabilities(
        supports_temperature=bool(entry.get("supports_temperature", True)),
        supports_top_p=bool(entry.get("supports_top_p", entry.get("supports_temperature", True))),
        effort_levels=tuple(str(level) for level in levels if isinstance(level, str)),
        default_effort=str(default) if isinstance(default, str) else None,
        source="catalog",
    )


def find_unclassified_models(catalog: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return provider -> model ids present in `catalog` but absent from the capabilities file.

    The provider model-list APIs return ids only, so tier values cannot be fetched;
    this is the gap detector the daily refresh job runs so a new id is noticed the
    day it appears. Live-capability providers (Codex) are excluded.
    """
    known = load_model_capabilities()
    gaps: dict[str, list[str]] = {}
    for provider, models in catalog.items():
        if provider in _LIVE_CAPABILITY_PROVIDERS or not isinstance(models, list):
            continue
        missing = sorted(m for m in models if isinstance(m, str) and m and m not in known)
        if missing:
            gaps[provider] = missing
    return gaps


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


# Providers that serve the same model namespace. The Codex subscription serves the
# OpenAI model family, so "codex" + "gpt-5.6-sol" is a correct pair even though the
# catalog files that model under "openai" (the catalog has no codex key -- codex
# models are enumerated from a live endpoint).
_PROVIDER_MODEL_NAMESPACES: tuple[frozenset[str], ...] = (frozenset({"openai", "codex"}),)


def _namespace_for(provider: str) -> frozenset[str]:
    """Providers whose models are interchangeable with `provider`."""
    for group in _PROVIDER_MODEL_NAMESPACES:
        if provider in group:
            return group
    return frozenset({provider})


def load_ownership_catalog() -> dict[str, list[str]]:
    """Raw provider -> models mapping, for answering "who owns this model?".

    Deliberately NOT load_catalog(): that applies the Workflow/Settings *display*
    filters (latest-only, project allowlist), which drop real models -- notably
    claude-sonnet-4-5, this project's own Anthropic default. Judging provenance
    through a dropdown-cosmetics filter makes the answer depend on presentation
    policy, so ownership reads the file as written.
    """
    if not CATALOG_PATH.exists():
        return {k: list(v) for k, v in DEFAULT_CATALOG.items()}
    try:
        raw = json.loads(CATALOG_PATH.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        # A daily refresh writes this file; a torn or unreadable read must not
        # become an error on an unrelated code path.
        return {}
    return raw if isinstance(raw, dict) else {}


def find_provider_model_mismatch(provider: str | None, model: str | None) -> str | None:
    """Return an explanation when `model` demonstrably belongs to a different provider.

    Conservative by construction -- it reports a mismatch only when the catalog
    positively attributes the model to some other provider namespace. Anything the
    catalog does not know (LMStudio local models, newly released models, blank values)
    is allowed through, so this can only reject pairs that are provably wrong.
    """
    provider = (provider or "").strip().lower()
    model = (model or "").strip()
    if not provider or not model:
        return None

    catalog = load_ownership_catalog()

    owners = {prov for prov, models in catalog.items() if isinstance(models, list) and model in models}
    if not owners:
        return None  # Unknown to the catalog -- not evidence of a mismatch.
    if owners & _namespace_for(provider):
        return None

    return (
        f"model '{model}' belongs to {'/'.join(sorted(owners))}, not '{provider}'. "
        f"Pairing a provider with another provider's model makes the run fail at call time "
        f"with a confusing 'model not found' error from '{provider}'."
    )
