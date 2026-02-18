"""
Model validation utilities for checking if models are valid for chat completions.
"""

import re

# Patterns for non-chat models that should be excluded
NON_CHAT_MODEL_PATTERNS = [
    re.compile(r"-codex", re.IGNORECASE),  # Codex models (gpt-5.2-codex, etc.)
    re.compile(r"-audio", re.IGNORECASE),  # Audio models
    re.compile(r"-image", re.IGNORECASE),  # Image models
    re.compile(r"-realtime", re.IGNORECASE),  # Realtime models (unless chat-enabled)
    re.compile(r"-tts", re.IGNORECASE),  # Text-to-speech
    re.compile(r"-transcribe", re.IGNORECASE),  # Transcription
    re.compile(r"-search", re.IGNORECASE),  # Search API models
    re.compile(r"^gpt-realtime", re.IGNORECASE),  # Standalone realtime
    re.compile(r"^gpt-audio", re.IGNORECASE),  # Standalone audio
    re.compile(r"^gpt-image", re.IGNORECASE),  # Standalone image
    re.compile(r"-deep-research", re.IGNORECASE),  # Deep research models (o3-deep-research, etc.)
    re.compile(r"^omni-moderation", re.IGNORECASE),  # Moderation models
    re.compile(r"^text-davinci", re.IGNORECASE),  # Legacy completion models (not chat)
    re.compile(r"^davinci-", re.IGNORECASE),  # Legacy completion models
    re.compile(r"^curie-", re.IGNORECASE),  # Legacy completion models
    re.compile(r"^babbage-", re.IGNORECASE),  # Legacy completion models
    re.compile(r"^ada-", re.IGNORECASE),  # Legacy completion models
]

# Valid base chat model patterns (without date suffixes)
VALID_CHAT_BASE_PATTERNS = [
    re.compile(r"^gpt-5(\.\d+)?(-(pro|mini|nano))?$", re.IGNORECASE),
    re.compile(r"^gpt-4(\.\d+)?(-(mini|nano|turbo))?$", re.IGNORECASE),
    re.compile(r"^gpt-4o(-mini)?$", re.IGNORECASE),
    re.compile(r"^gpt-3\.5-turbo", re.IGNORECASE),
    re.compile(r"^o[134](-(pro|mini))?$", re.IGNORECASE),
]

OPENAI_MODEL_PATTERN = re.compile(
    r"^(gpt|o\d|o[1-9]|o-|o[a-z]|omni|text-davinci|davinci|curie|babbage|ada)",
    re.IGNORECASE,
)

# Temperature ranges per provider (min, max). Sources: OpenAI [0,2], Anthropic [0,1].
TEMPERATURE_RANGE_BY_PROVIDER: dict[str, tuple[float, float]] = {
    "openai": (0.0, 2.0),
    "anthropic": (0.0, 1.0),
    "lmstudio": (0.0, 2.0),
    "gemini": (0.0, 2.0),
}
DEFAULT_TEMPERATURE_RANGE = (0.0, 2.0)


def clamp_temperature_for_provider(provider: str, temperature: float) -> float:
    """
    Clamp temperature to the provider's valid range.
    OpenAI: [0, 2]; Anthropic: [0, 1]; LM Studio / Gemini: [0, 2].
    Unknown provider: clamp to [0, 2].
    """
    try:
        low, high = TEMPERATURE_RANGE_BY_PROVIDER.get((provider or "").strip().lower(), DEFAULT_TEMPERATURE_RANGE)
    except (TypeError, AttributeError):
        low, high = DEFAULT_TEMPERATURE_RANGE
    t = float(temperature)
    return max(low, min(high, t))


def is_valid_openai_chat_model(model_id: str) -> bool:
    """
    Validate if an OpenAI model ID is valid for chat completions.

    Returns True if the model is a valid chat completion model, False otherwise.
    Excludes specialized models (codex, audio, image, realtime, etc.).
    Dated snapshots (e.g. gpt-4o-2024-11-20) are accepted; base names may be deprecated.
    """
    if not model_id or not isinstance(model_id, str):
        return False

    model_id = model_id.strip()
    if not model_id:
        return False

    # Must match OpenAI model pattern
    if not OPENAI_MODEL_PATTERN.match(model_id):
        return False

    # Exclude non-chat models
    for pattern in NON_CHAT_MODEL_PATTERNS:
        if pattern.search(model_id):
            return False

    # Check if it matches a valid base pattern (with or without date suffix)
    # Remove date suffix (YYYY-MM-DD format) for pattern matching
    base_model = re.sub(r"-\d{4}-\d{2}-\d{2}(-preview)?$", "", model_id)
    base_model = re.sub(r"-latest$", "", base_model)
    base_model = re.sub(r"-preview$", "", base_model)

    for pattern in VALID_CHAT_BASE_PATTERNS:
        if pattern.match(base_model):
            return True

    # Allow dated versions of known valid models if base matches
    # This handles cases like gpt-4o-2024-05-13, gpt-5.2-pro-2025-12-11, etc.
    # But we'll be conservative and prefer base names
    if base_model in [
        "gpt-5.2-pro",
        "gpt-5.2",
        "gpt-5.1",
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o3",
        "o3-pro",
        "o3-mini",
        "o4-mini",
        "o1",
        "o1-pro",
    ]:
        return True

    # If it has a date suffix but doesn't match known patterns, be conservative
    # Prefer base model names without dates
    if re.search(r"-\d{4}-\d{2}-\d{2}", model_id):
        # Dated version - only allow if base is explicitly known
        return False

    # Fallback: if it starts with gpt- or o and doesn't match exclusion patterns, allow it
    # but this should be rare
    return bool(model_id.lower().startswith(("gpt-", "o")))


# OpenAI: dated suffix is -YYYY-MM-DD or -YYYY-MM-DD-preview; keep only chat + no date (latest).
OPENAI_DATED = re.compile(r"-\d{4}-\d{2}-\d{2}(-preview)?$")


def filter_openai_models_latest_only(model_ids: list[str]) -> list[str]:
    """
    Chat-only, latest only: exclude models with a -YYYY-MM-DD (or -preview) date suffix.
    Keeps e.g. gpt-4o, gpt-4.1-mini, o1; drops gpt-4o-2024-05-13, gpt-4.1-2025-04-14.
    """
    return sorted(
        m for m in model_ids if m and is_valid_openai_chat_model(m.strip()) and not OPENAI_DATED.search(m.strip())
    )


# Anthropic: family = strip -YYYYMMDD or -latest; one representative per family.
ANTHROPIC_DATED = re.compile(r"-\d{8}$")
ANTHROPIC_LATEST = re.compile(r"-latest$", re.IGNORECASE)


def _anthropic_family(model_id: str) -> str:
    """Family key: strip trailing -YYYYMMDD and -latest."""
    key = ANTHROPIC_DATED.sub("", model_id)
    return ANTHROPIC_LATEST.sub("", key)


def filter_anthropic_models_latest_only(model_ids: list[str]) -> list[str]:
    """
    One main/latest per family (e.g. one Sonnet 4.5, one Haiku 4.5, one Opus 4.6).
    Prefer: no date > -latest > most recent -YYYYMMDD.
    """
    claude = [m.strip() for m in model_ids if m and m.strip().lower().startswith("claude")]
    if not claude:
        return []

    by_family: dict[str, list[str]] = {}
    for m in claude:
        by_family.setdefault(_anthropic_family(m), []).append(m)

    def rank(m: str) -> tuple[int, int]:
        if ANTHROPIC_DATED.search(m):
            return (2, -int(m[-8:]))  # dated: prefer later date
        if ANTHROPIC_LATEST.search(m):
            return (1, 0)
        return (0, 0)  # main (no suffix)

    return sorted(min(fam, key=rank) for fam in by_family.values())


def suggest_base_model(model_id: str) -> str | None:
    """Suggest a base model name for a dated model ID."""
    if not model_id or not isinstance(model_id, str):
        return None

    # Remove date suffix
    base = re.sub(r"-\d{4}-\d{2}-\d{2}(-preview)?$", "", model_id)
    base = re.sub(r"-latest$", "", base)
    base = re.sub(r"-preview$", "", base)

    # If it changed, suggest the base
    if base != model_id and is_valid_openai_chat_model(base):
        return base
    return None
