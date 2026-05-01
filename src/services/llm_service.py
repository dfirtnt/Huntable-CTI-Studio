"""
LLM Service for Deepseek-R1 integration via LMStudio.

Provides LLM-based ranking and extraction for agentic workflow.
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import math
import os
import re
import subprocess
from collections.abc import Callable
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, NamedTuple

import httpx

from src.database.manager import DatabaseManager
from src.database.models import AppSettingsTable
from src.services.provider_model_catalog import get_model_context_tokens
from src.utils.langfuse_client import log_llm_completion, log_llm_error, trace_llm_call
from src.utils.model_validation import clamp_temperature_for_provider, model_supports_variable_temperature

logger = logging.getLogger(__name__)

# Minimum user message length (chars) to avoid empty/malformed prompts
MIN_USER_CONTENT_CHARS = 500
DEBUG_ARTIFACT_PREVIEW_CHARS = 2048


class PreprocessInvariantError(Exception):
    """
    Raised when pre-inference invariants fail (empty/malformed messages).
    Classify as infra_failed, not model failure. Do NOT emit llm_response.
    """

    def __init__(self, message: str, debug_artifacts: dict[str, Any] | None = None):
        super().__init__(message)
        self.debug_artifacts = debug_artifacts or {}


class ContextLengthExceededError(RuntimeError):
    """
    Raised when the API rejects a request because the prompt exceeds the model's context window.
    Unrecoverable -- retrying will not help. Fail-fast and surface as execution failure.
    """


# Always-required traceability fields (Extractor Contract sec 3-4)
_TRACEABILITY_FIELDS = frozenset({"value", "source_evidence", "extraction_justification", "confidence_score"})
# Fields that must appear in every item regardless of extractor type
_TRACEABILITY_REQUIRED = frozenset({"source_evidence", "extraction_justification", "confidence_score"})
# "value" is required only for simple extractors; structured extractors with domain-specific
# identity fields (task_name/task_path/indicator_type/etc.) satisfy the contract without it.
_TRACEABILITY_VALUE_FIELD = "value"


# Text tokens required by the Extractor Contract (extractor-standard.md).
# HARD_FAIL checks raise ValueError -- missing these makes the prompt structurally broken.
# WARN_ONLY checks log a warning -- existing prompts predate the v1.1 contract language;
# promote to HARD_FAIL after all seed prompts are brought into conformance.
_SYSTEM_HARD_FAIL: list[tuple[str, str]] = []
_SYSTEM_WARN_ONLY: list[tuple[str, str]] = [
    ("LITERAL TEXT EXTRACTOR", "ROLE block (sec 1)"),
    ("sub-agent of ExtractAgent", "ARCHITECTURE CONTEXT (sec 3)"),
    ("Do NOT use prior knowledge", "INPUT CONTRACT (sec 4)"),
    ("Do NOT fetch", "INPUT CONTRACT fetch rule (sec 4)"),
    ("[ ]", "VERIFICATION CHECKLIST (sec 12)"),
]
_INSTRUCTIONS_HARD_FAIL: list[tuple[str, str]] = []
_INSTRUCTIONS_WARN_ONLY: list[tuple[str, str]] = [
    ("ONLY valid JSON", "JSON-only directive (sec 13)"),
    ("When in doubt, OMIT", "FINAL REMINDER (sec 16)"),
    ("source_evidence", "traceability field mention (sec 14)"),
]


# ---------------------------------------------------------------------------
# QA corrections dispatch
# ---------------------------------------------------------------------------


class _QaAgentSpec(NamedTuple):
    """Per-agent spec for applying QA corrections.

    items_key:    Key in last_result that holds the items list.
    matcher:      Returns True when a removal entry matches an item.
    removal_id:   Converts a removal entry to its stored representation
                  (str for simple agents, dict for structured agents).
    """

    items_key: str
    matcher: "Callable[[dict, dict], bool]"
    removal_id: "Callable[[dict], Any]"


def _value_matcher(removal_key: str) -> "Callable[[dict, dict], bool]":
    """Match a single removal field against item.value (CmdlineExtract, HuntQueriesExtract)."""

    def _match(removal: dict, item: dict) -> bool:
        r = (removal.get(removal_key) or "").strip()
        v = (item.get("value") or "").strip() if isinstance(item, dict) else str(item).strip()
        return bool(r) and r == v

    return _match


def _composite_matcher(field_pairs: list[tuple[str, str]]) -> "Callable[[dict, dict], bool]":
    """Match a removal entry against an item using multiple identity fields.

    At least one field must be non-empty in the removal, and all non-empty
    removal fields must match the corresponding item field (case-insensitive).
    """

    def _match(removal: dict, item: dict) -> bool:
        if not isinstance(item, dict):
            return False
        active = [(rf, itf) for rf, itf in field_pairs if (removal.get(rf) or "").strip()]
        if not active:
            return False
        return all(
            (removal.get(rf) or "").strip().lower() == (item.get(itf) or "").strip().lower() for rf, itf in active
        )

    return _match


def _first_nonempty_matcher(fields: list[str]) -> "Callable[[dict, dict], bool]":
    """Match using the first non-empty identity field in the removal entry.

    Used by ScheduledTasksExtract where identity is whichever of
    task_name / task_path / store_path is non-null.
    """

    def _match(removal: dict, item: dict) -> bool:
        if not isinstance(item, dict):
            return False
        for field in fields:
            r = (removal.get(field) or "").strip()
            if r:
                return r.lower() == (item.get(field) or "").strip().lower()
        return False

    return _match


# Map agent names to their QA-corrections spec.
# items_key reflects the key in last_result AFTER the rename step
# (registry_artifacts / process_lineage / windows_services / scheduled_tasks
# are all renamed to "items" before QA runs; queries and cmdline_items stay).
_QA_AGENT_SPECS: dict[str, _QaAgentSpec] = {
    "CmdlineExtract": _QaAgentSpec(
        "cmdline_items",
        _value_matcher("command"),
        lambda r: (r.get("command") or "").strip(),
    ),
    "HuntQueriesExtract": _QaAgentSpec(
        "queries",
        _value_matcher("query"),
        lambda r: (r.get("query") or "").strip(),
    ),
    "RegistryExtract": _QaAgentSpec(
        "items",
        _composite_matcher(
            [
                ("registry_hive", "registry_hive"),
                ("registry_key_path", "registry_key_path"),
                ("registry_value_name", "registry_value_name"),
            ]
        ),
        lambda r: r,
    ),
    "ProcTreeExtract": _QaAgentSpec(
        "items",
        _composite_matcher(
            [
                ("parent", "parent"),
                ("child", "child"),
            ]
        ),
        lambda r: r,
    ),
    "ServicesExtract": _QaAgentSpec(
        "items",
        _composite_matcher(
            [
                ("service_name", "service_name"),
                ("binary_path", "binary_path"),
            ]
        ),
        lambda r: r,
    ),
    "ScheduledTasksExtract": _QaAgentSpec(
        "items",
        _first_nonempty_matcher(["task_name", "task_path", "store_path"]),
        lambda r: r,
    ),
}


class PromptConfigValidationError(ValueError):
    """Raised when prompt config violates hard-fail contract requirements."""


def _validate_qa_prompt_config(agent_name: str, qa_prompt_config: dict[str, Any]) -> None:
    """Validate a QA agent prompt config before the QA retry loop.

    Called once when qa_prompt_config is provided, so a misconfigured QA prompt aborts
    cleanly rather than silently falling back to defaults mid-run.

    Hard-fail rules (structural -- config is unusable without these):
      - system/role key: REQUIRED, non-empty
      - instructions key: REQUIRED, non-empty
      - evaluation_criteria key: REQUIRED, must be a non-empty list

    Warn-only rules (text-pattern checks):
      - objective: present (falls back to a generic string if absent, but should be set)
    """
    qa_system = (qa_prompt_config.get("system") or qa_prompt_config.get("role") or "").strip()
    if not qa_system:
        raise PromptConfigValidationError(
            f"{agent_name} QA: prompt_config missing required 'system'/'role' key. "
            "The QA agent needs a non-empty system prompt to function."
        )

    instructions = (qa_prompt_config.get("instructions") or "").strip()
    if not instructions:
        raise PromptConfigValidationError(
            f"{agent_name} QA: prompt_config missing required 'instructions' key. "
            "Without instructions the QA agent has no evaluation directive."
        )

    criteria = qa_prompt_config.get("evaluation_criteria")
    if not criteria:
        raise PromptConfigValidationError(
            f"{agent_name} QA: prompt_config missing required 'evaluation_criteria' key (must be non-empty list). "
            "The QA retry loop uses evaluation_criteria to build the grading rubric."
        )
    if not isinstance(criteria, list):
        raise PromptConfigValidationError(
            f"{agent_name} QA: 'evaluation_criteria' must be a list, got {type(criteria).__name__}."
        )

    if not qa_prompt_config.get("objective"):
        logger.warning(
            "%s QA: prompt_config missing 'objective' -- will fall back to generic 'Verify extraction.' string. "
            "Add an explicit objective for clearer QA behaviour.",
            agent_name,
        )


def _validate_extraction_prompt_config(agent_name: str, prompt_config: dict[str, Any]) -> None:
    """Enforce Extractor Contract required fields (docs/contracts/extractor-standard.md).

    Called once before the retry loop so a misconfigured prompt aborts immediately.
    Raises ValueError on hard-fail violations; logs warnings for warn-only checks.

    Hard-fail rules (contract sections mapped to config keys):
      - user_template must NOT be present (code-owned scaffold; sec 5 note)
      - system/role key: REQUIRED, non-empty (sections 1-12 -> system message)
      - instructions key: REQUIRED, non-empty (sections 13-16 -> JSON schema footer)
      - json_example traceability fields: REQUIRED if json_example is present (sec 14)

    Warn-only rules (text pattern checks -- existing prompts predate v1.1 contract language):
      - system body tokens: LITERAL TEXT EXTRACTOR, sub-agent of ExtractAgent, etc.
      - instructions tokens: ONLY valid JSON, When in doubt OMIT, traceability fields
    """
    if "user_template" in prompt_config:
        raise PromptConfigValidationError(
            f"{agent_name}: prompt_config must not contain 'user_template'. "
            "Extractor Contract (extractor-standard.md sec 5 note): the user message scaffold "
            "is code-owned; preset authors must not write or edit user_template."
        )

    system_content = (prompt_config.get("system") or prompt_config.get("role") or "").strip()
    if not system_content:
        raise PromptConfigValidationError(
            f"{agent_name}: prompt_config missing required 'system'/'role' key. "
            "Extractor Contract (extractor-standard.md sec 1) mandates a non-empty system message."
        )

    instructions = (prompt_config.get("instructions") or "").strip()
    if not instructions:
        raise PromptConfigValidationError(
            f"{agent_name}: prompt_config missing required 'instructions' key. "
            "Extractor Contract (extractor-standard.md sec 2) mandates instructions "
            "containing output schema + JSON enforcement."
        )

    # Text-pattern checks on system body (warn-only until seed prompts conform to v1.1)
    for token, label in _SYSTEM_HARD_FAIL:
        if token not in system_content:
            raise PromptConfigValidationError(
                f"{agent_name}: system prompt missing required token for {label}: {token!r}"
            )
    for token, label in _SYSTEM_WARN_ONLY:
        if token not in system_content:
            logger.warning(
                "%s: extractor contract system-body warning for %s "
                "(WARN_ONLY -- promote to hard-fail after prompts conform to extractor-standard.md v1.1)",
                agent_name,
                label,
            )

    # Text-pattern checks on instructions (warn-only until seed prompts conform to v1.1)
    for token, label in _INSTRUCTIONS_HARD_FAIL:
        if token not in instructions:
            raise PromptConfigValidationError(
                f"{agent_name}: instructions missing required token for {label}: {token!r}"
            )
    for token, label in _INSTRUCTIONS_WARN_ONLY:
        if token not in instructions:
            logger.warning(
                "%s: extractor contract instructions warning for %s "
                "(WARN_ONLY -- promote to hard-fail after prompts conform to extractor-standard.md v1.1)",
                agent_name,
                label,
            )

    json_example = prompt_config.get("json_example")
    if json_example is None:
        raise PromptConfigValidationError(
            f"{agent_name}: prompt_config missing required 'json_example'. "
            "Extractor Contract (extractor-standard.md sec 4) requires json_example "
            "including all traceability fields."
        )

    parsed_example: Any = json_example
    if isinstance(json_example, str):
        try:
            parsed_example = json.loads(json_example)
        except (ValueError, json.JSONDecodeError) as exc:
            raise PromptConfigValidationError(
                f"{agent_name}: json_example is not valid JSON. "
                "Extractor Contract requires a parseable json_example so the LLM receives a valid schema contract."
            ) from exc

    if not isinstance(parsed_example, dict):
        return

    # Locate the items array (first list value in the top-level dict)
    item_fields: set[str] = set()
    for v in parsed_example.values():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            item_fields = set(v[0].keys())
            break

    if item_fields:
        # Always-required: source_evidence, extraction_justification, confidence_score
        missing_required = _TRACEABILITY_REQUIRED - item_fields
        if missing_required:
            raise PromptConfigValidationError(
                f"{agent_name}: json_example items are missing traceability fields: {sorted(missing_required)}. "
                "Extractor Contract (extractor-standard.md sec 3-4) requires "
                "source_evidence, extraction_justification, confidence_score in every item."
            )

        # "value" is required for simple extractors (no domain-specific identity fields).
        # Structured extractors (task_name/task_path/indicator_type/etc.) satisfy the
        # contract through their domain fields and do not need a redundant "value" key.
        has_domain_fields = bool(item_fields - _TRACEABILITY_FIELDS)
        if not has_domain_fields and _TRACEABILITY_VALUE_FIELD not in item_fields:
            raise PromptConfigValidationError(
                f"{agent_name}: json_example items are missing 'value' field. "
                "Extractor Contract (extractor-standard.md sec 3-4) requires 'value' "
                "for simple extractors. Add 'value' or use named domain-specific identity fields."
            )


def _validate_preprocess_invariants(
    messages: list[dict[str, Any]],
    *,
    agent_name: str,
    content_sha256: str,
    attention_preprocessor_enabled: bool,
    execution_id: int | None = None,
    user_prompt: str = "",
) -> None:
    """
    Fail-fast guard: ensure LLM is never called with empty/malformed request.
    Raises PreprocessInvariantError with debug artifacts on failure.
    """
    artifacts: dict[str, Any] = {
        "agent_name": agent_name,
        "content_sha256": content_sha256,
        "attention_preprocessor_enabled": attention_preprocessor_enabled,
        "execution_id": execution_id,
    }
    if user_prompt:
        artifacts["user_prompt_sha256"] = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()
        artifacts["user_prompt_preview"] = user_prompt[:DEBUG_ARTIFACT_PREVIEW_CHARS]

    if not messages or not isinstance(messages, list):
        raise PreprocessInvariantError(
            f"{agent_name}: messages must be a non-empty list, got {type(messages).__name__}",
            debug_artifacts=artifacts,
        )

    roles = {m.get("role") for m in messages if isinstance(m, dict)}
    if "system" not in roles:
        raise PreprocessInvariantError(
            f"{agent_name}: messages must contain a system message, got roles={roles}",
            debug_artifacts=artifacts,
        )
    if "user" not in roles:
        raise PreprocessInvariantError(
            f"{agent_name}: messages must contain a user message, got roles={roles}",
            debug_artifacts=artifacts,
        )

    user_msg = next((m for m in messages if isinstance(m, dict) and m.get("role") == "user"), None)
    if not user_msg:
        raise PreprocessInvariantError(
            f"{agent_name}: user message not found in messages",
            debug_artifacts=artifacts,
        )

    user_content = user_msg.get("content", "")
    if isinstance(user_content, list):
        user_content = " ".join(c.get("text", str(c)) for c in user_content if isinstance(c, dict))
    user_content = str(user_content or "").strip()

    if len(user_content) < MIN_USER_CONTENT_CHARS:
        raise PreprocessInvariantError(
            f"{agent_name}: user message content length ({len(user_content)}) below minimum ({MIN_USER_CONTENT_CHARS})",
            debug_artifacts=artifacts,
        )
    if not user_content:
        raise PreprocessInvariantError(
            f"{agent_name}: user message content is empty or whitespace-only",
            debug_artifacts=artifacts,
        )

    # Require article content marker when template uses it (CmdlineExtract: "Content:")
    if agent_name == "CmdlineExtract" and "Content:" not in user_content:
        raise PreprocessInvariantError(
            f"{agent_name}: user message must contain 'Content:' delimiter (article content marker)",
            debug_artifacts=artifacts,
        )


# LM Studio context limits (default to 32768 for reasoning models, 4096 for others)
# Reasoning models need large context windows for both reasoning and output
MAX_CONTEXT_TOKENS = int(os.getenv("LMSTUDIO_MAX_CONTEXT", "32768"))
PROMPT_OVERHEAD_TOKENS = 500  # Reserve for prompt templates, system messages, etc.

# Minimum context length threshold for workflow (configurable)
MIN_CONTEXT_LENGTH_THRESHOLD = int(os.getenv("LMSTUDIO_MIN_CONTEXT_THRESHOLD", "16384"))

WORKFLOW_PROVIDER_APPSETTING_KEYS = {
    "openai_enabled": "WORKFLOW_OPENAI_ENABLED",
    "openai_api_key": "WORKFLOW_OPENAI_API_KEY",
    "anthropic_enabled": "WORKFLOW_ANTHROPIC_ENABLED",
    "anthropic_api_key": "WORKFLOW_ANTHROPIC_API_KEY",
    "lmstudio_enabled": "WORKFLOW_LMSTUDIO_ENABLED",
}


class LLMService:
    """Service for LLM API calls using Deepseek-R1 via LMStudio."""

    def __init__(self, config_models: dict[str, str] | None = None):
        """
        Initialize LLM service with LMStudio configuration.

        Args:
            config_models: Optional dict of agent models from workflow config.
                          Format: {"RankAgent": "model_name", "ExtractAgent": "...", "SigmaAgent": "..."}
                          If provided, these override environment variables.
        """
        from src.utils.lmstudio_url import get_lmstudio_base_url

        self.lmstudio_url = get_lmstudio_base_url("http://host.docker.internal:1234/v1")
        self.assumed_lmstudio_context_tokens = int(os.getenv("WORKFLOW_LMSTUDIO_CONTEXT_TOKENS", "16384"))
        self.assumed_cloud_context_tokens = int(os.getenv("WORKFLOW_CLOUD_CONTEXT_TOKENS", "80000"))

        # Default model (fallback for backward compatibility)
        default_model = os.getenv("LMSTUDIO_MODEL", "mistralai/mistral-7b-instruct-v0.3")

        # Per-operation model configuration
        # Priority: config_models > environment variables > default
        config_models = config_models or {}

        self.lmstudio_model = default_model  # Keep for backward compatibility

        workflow_settings = self._load_workflow_provider_settings()
        # Prefer AppSettings, fall back to env; if a key exists, default enable unless explicitly false
        self.openai_api_key = (
            workflow_settings.get(WORKFLOW_PROVIDER_APPSETTING_KEYS["openai_api_key"])
            or os.getenv("WORKFLOW_OPENAI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        if isinstance(self.openai_api_key, str):
            self.openai_api_key = self.openai_api_key.strip()
        self.anthropic_api_key = (
            workflow_settings.get(WORKFLOW_PROVIDER_APPSETTING_KEYS["anthropic_api_key"])
            or os.getenv("WORKFLOW_ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
        )

        def _enabled(setting_key: str, env_key: str, default: bool) -> bool:
            # AppSettings override, then env flag, else default
            flag = workflow_settings.get(setting_key)
            if flag is None:
                flag = os.getenv(env_key)
            return self._bool_from_setting(flag, default)

        self.workflow_openai_enabled = _enabled(
            WORKFLOW_PROVIDER_APPSETTING_KEYS["openai_enabled"],
            "WORKFLOW_OPENAI_ENABLED",
            bool(self.openai_api_key),
        )
        self.workflow_anthropic_enabled = _enabled(
            WORKFLOW_PROVIDER_APPSETTING_KEYS["anthropic_enabled"],
            "WORKFLOW_ANTHROPIC_ENABLED",
            bool(self.anthropic_api_key),
        )
        self.workflow_lmstudio_enabled = _enabled(
            WORKFLOW_PROVIDER_APPSETTING_KEYS["lmstudio_enabled"],
            "WORKFLOW_LMSTUDIO_ENABLED",
            False,
        )

        self.provider_defaults = {
            "lmstudio": default_model,
            "openai": os.getenv("WORKFLOW_OPENAI_MODEL", "gpt-4o-mini"),
            "anthropic": os.getenv("WORKFLOW_ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        }

        self.provider_rank = self._canonicalize_provider(config_models.get("RankAgent_provider") or "")
        self.provider_extract = self._canonicalize_provider(config_models.get("ExtractAgent_provider") or "")
        self.provider_sigma = self._canonicalize_provider(config_models.get("SigmaAgent_provider") or "")

        rank_override = (config_models.get("RankAgent") or "").strip()
        rank_env = os.getenv("LMSTUDIO_MODEL_RANK", "").strip()
        self.model_rank = self._resolve_agent_model(
            "RankAgent", rank_override, rank_env, self.provider_rank, default_model
        )
        self.model_extract = self._resolve_agent_model(
            "ExtractAgent",
            (config_models.get("ExtractAgent") or "").strip(),
            os.getenv("LMSTUDIO_MODEL_EXTRACT", "").strip(),
            self.provider_extract,
            default_model,
            require_specific_model=False,
        )
        self.model_sigma = self._resolve_agent_model(
            "SigmaAgent",
            (config_models.get("SigmaAgent") or "").strip(),
            os.getenv("LMSTUDIO_MODEL_SIGMA", "").strip(),
            self.provider_sigma,
            default_model=default_model,
            require_specific_model=False,
        )

        # Detect if model requires system message conversion (Mistral models don't support system role)
        self._needs_system_conversion = self._model_needs_system_conversion(default_model)

        # Recommended settings for reasoning models (temperature/top_p work well for structured output)
        # Temperature 0.0 for deterministic scoring
        self.temperature = float(os.getenv("LMSTUDIO_TEMPERATURE", "0.0"))

        # Per-agent temperature settings (from config, fallback to global)
        self.temperature_rank = float(
            config_models.get("RankAgent_temperature", os.getenv("LMSTUDIO_TEMPERATURE", "0.0"))
        )
        self.temperature_extract = float(
            config_models.get("ExtractAgent_temperature", os.getenv("LMSTUDIO_TEMPERATURE", "0.0"))
        )
        self.temperature_sigma = float(
            config_models.get("SigmaAgent_temperature", os.getenv("LMSTUDIO_TEMPERATURE", "0.0"))
        )

        self.top_p = float(os.getenv("LMSTUDIO_TOP_P", "0.9"))

        # Per-agent top_p settings (from config, fallback to global)
        # Handle both string and numeric values from JSONB
        rank_top_p_raw = config_models.get("RankAgent_top_p") if config_models else None
        if rank_top_p_raw is not None:
            self.top_p_rank = float(rank_top_p_raw)
        else:
            self.top_p_rank = float(os.getenv("LMSTUDIO_TOP_P", "0.9"))

        extract_top_p_raw = config_models.get("ExtractAgent_top_p") if config_models else None
        if extract_top_p_raw is not None:
            self.top_p_extract = float(extract_top_p_raw)
        else:
            self.top_p_extract = float(os.getenv("LMSTUDIO_TOP_P", "0.9"))

        sigma_top_p_raw = config_models.get("SigmaAgent_top_p") if config_models else None
        if sigma_top_p_raw is not None:
            self.top_p_sigma = float(sigma_top_p_raw)
        else:
            self.top_p_sigma = float(os.getenv("LMSTUDIO_TOP_P", "0.9"))

        # Store config_models for per-subagent top_p lookup
        self.config_models = config_models if config_models else {}

        self.seed = int(os.getenv("LMSTUDIO_SEED", "42")) if os.getenv("LMSTUDIO_SEED") else None

        model_source = "config" if config_models else "environment"
        logger.info(
            f"Initialized LLMService ({model_source}) - Providers: "
            f"rank={self.provider_rank}, extract={self.provider_extract}, sigma={self.provider_sigma} "
            f"- Models: rank={self.model_rank}, extract={self.model_extract}, sigma={self.model_sigma}"
        )

    def get_top_p_for_agent(self, agent_name: str) -> float:
        """
        Get top_p value for a specific agent.

        Args:
            agent_name: Agent name (e.g., "CmdlineExtract", "RankAgent", "ExtractAgent")

        Returns:
            top_p value for the agent, or global default if not configured
        """
        # Check for agent-specific top_p in config
        top_p_key = f"{agent_name}_top_p"
        if self.config_models and top_p_key in self.config_models:
            return float(self.config_models[top_p_key])

        # Fallback to main agent top_p values
        if agent_name == "RankAgent":
            return self.top_p_rank
        if agent_name == "ExtractAgent":
            return self.top_p_extract
        if agent_name == "SigmaAgent":
            return self.top_p_sigma
        if agent_name in [
            "CmdlineExtract",
            "ProcTreeExtract",
            "HuntQueriesExtract",
            "RegistryExtract",
            "ServicesExtract",
            "ScheduledTasksExtract",
        ]:
            # Sub-agents fall back to ExtractAgent top_p
            return self.top_p_extract

        # Default to global top_p
        return self.top_p

    def _bool_from_setting(self, value: str | None, default: bool = False) -> bool:
        if value is None:
            return default
        return str(value).strip().lower() == "true"

    def _canonicalize_provider(self, provider: str | None) -> str:
        normalized = (provider or "").strip().lower()
        if normalized in {"openai", "chatgpt", "gpt4o", "gpt-4o", "gpt-4o-mini"}:
            return "openai"
        if normalized in {"anthropic", "claude", "claude-sonnet-4-5"}:
            return "anthropic"
        if normalized in {"lmstudio", "local", "local_llm", "deepseek"} or not normalized:
            return "lmstudio"
        if normalized == "auto":
            return "lmstudio"
        logger.warning(f"Unknown provider '{provider}' for workflow; defaulting to LMStudio")
        return "lmstudio"

    def _load_workflow_provider_settings(self) -> dict[str, str | None]:
        settings: dict[str, str | None] = {}
        db_session = None
        try:
            db_manager = DatabaseManager()
            db_session = db_manager.get_session()
            query = db_session.query(AppSettingsTable).filter(
                AppSettingsTable.key.in_(WORKFLOW_PROVIDER_APPSETTING_KEYS.values())
            )
            for row in query:
                settings[row.key] = row.value
            if not settings:
                logger.debug(
                    "Workflow provider settings empty from AppSettings; "
                    "ensure API keys are saved in Settings (click Save) or set in .env"
                )
        except Exception as exc:
            logger.warning(
                "Unable to load workflow provider settings from AppSettings: %s. "
                "Workers read keys from DB; ensure Settings are saved.",
                exc,
            )
        finally:
            if db_session:
                db_session.close()
        return settings

    def _resolve_agent_model(
        self,
        agent_name: str,
        override: str,
        env_value: str,
        provider: str,
        default_model: str,
        require_specific_model: bool = True,
    ) -> str:
        if override:
            return override
        if provider == "lmstudio":
            if env_value:
                return env_value
            if require_specific_model:
                raise ValueError(
                    f"{agent_name} model must be configured for LMStudio "
                    f"(workflow config or LMSTUDIO_MODEL_{agent_name.upper()})."
                )
            return default_model
        return self.provider_defaults.get(provider, default_model)

    def _model_needs_system_conversion(self, model_name: str) -> bool:
        """Check if model requires system message conversion (e.g., Mistral models)."""
        model_lower = model_name.lower()
        # Mistral models and some others don't support system role in LM Studio
        # Qwen models support system role, so no conversion needed
        return any(x in model_lower for x in ["mistral", "mixtral"]) and "qwen" not in model_lower

    def _convert_messages_for_model(self, messages: list, model_name: str) -> list:
        """Convert system messages to user messages for models that don't support system role."""
        if not self._model_needs_system_conversion(model_name):
            return messages

        # For Mistral, convert system to user message using instruction format
        converted = []
        system_content = None

        # Collect system message
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg["content"]
                break

        # Get user messages (should only be one)
        user_messages = [msg for msg in messages if msg.get("role") != "system"]

        if system_content and user_messages:
            # For Mistral, use direct instruction format without system role wrapper
            # Merge into a single user message with clear task separation
            user_content = user_messages[0]["content"]
            # Only prepend system if it's not already integrated into the prompt
            if not user_content.startswith("Task:") and not user_content.startswith("You are"):
                # For ranking/extraction prompts that already have structure, just use user content
                # System role instructions are usually redundant
                converted = user_messages
            else:
                # Combine with clear separator
                converted = [{"role": "user", "content": f"{system_content}\n\n{user_content}"}]
        else:
            converted = messages if not any(m.get("role") == "system" for m in messages) else user_messages

        return converted

    @staticmethod
    def _read_file_sync(file_path: str) -> str:
        """Synchronous file read helper (to be run in thread)."""
        with open(file_path, encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _read_json_file_sync(file_path: str) -> dict:
        """Synchronous JSON file read helper (to be run in thread)."""
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough estimate: ~4 characters per token."""
        return len(text) // 4

    def _get_context_limit(self, provider: str | None, model_name: str | None = None) -> int:
        if model_name:
            catalog_val = get_model_context_tokens(model_name)
            if catalog_val is not None:
                return catalog_val
        canonical = self._canonicalize_provider(provider or "")
        if canonical == "lmstudio":
            return self.assumed_lmstudio_context_tokens
        return self.assumed_cloud_context_tokens

    def _get_context_limit_for_provider(self, provider: str | None) -> int:
        return self._get_context_limit(provider, model_name=None)

    @staticmethod
    def _truncate_content(
        content: str, max_context_tokens: int, max_output_tokens: int, prompt_overhead: int = PROMPT_OVERHEAD_TOKENS
    ) -> str:
        """
        Truncate content to fit within LM Studio context limits.

        Args:
            content: Article content to truncate
            max_context_tokens: Maximum context window (default: 4096)
            max_output_tokens: Maximum output tokens requested
            prompt_overhead: Tokens reserved for prompt/system messages

        Returns:
            Truncated content with notice if truncated
        """
        # Calculate available tokens for content
        # Reserve: prompt overhead + output tokens + safety margin (10%)
        available_tokens = max_context_tokens - prompt_overhead - max_output_tokens
        available_tokens = int(available_tokens * 0.9)  # 10% safety margin

        content_tokens = LLMService._estimate_tokens(content)

        if content_tokens <= available_tokens:
            return content

        # Truncate to fit
        max_chars = available_tokens * 4
        truncated = content[:max_chars]

        # Try to truncate at sentence boundary
        last_period = truncated.rfind(".")
        last_newline = truncated.rfind("\n")
        last_boundary = max(last_period, last_newline)

        if last_boundary > max_chars * 0.8:
            truncated = truncated[: last_boundary + 1]

        return truncated + "\n\n[Content truncated to fit context window]"

    @staticmethod
    def compute_rank_ground_truth(hunt_score: Any | None, ml_score: Any | None) -> dict[str, float | None]:
        """
        Derive a 1-10 ground truth rank from hunt and ML scores (0-100 scale).
        Rounds the mean score to the nearest 10, then maps to 1-10.
        """

        def _to_float(value: Any) -> float | None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        hunt = _to_float(hunt_score)
        ml = _to_float(ml_score)

        if hunt is None or ml is None:
            return {
                "ground_truth_rank": None,
                "ground_truth_mean": None,
                "rounded_to_nearest_10": None,
                "hunt_score": hunt,
                "ml_score": ml,
            }

        mean_score = (hunt + ml) / 2
        rounded_to_nearest_10 = math.floor((mean_score + 5) / 10) * 10
        ground_truth_rank = max(1.0, min(10.0, rounded_to_nearest_10 / 10))

        return {
            "ground_truth_rank": ground_truth_rank,
            "ground_truth_mean": mean_score,
            "rounded_to_nearest_10": rounded_to_nearest_10,
            "hunt_score": hunt,
            "ml_score": ml,
        }

    def _lmstudio_url_candidates(self) -> list:
        """Get list of LMStudio URL candidates for fallback (all normalized to end with /v1)."""
        from src.utils.lmstudio_url import normalize_lmstudio_base_url

        candidates = [
            self.lmstudio_url,
            normalize_lmstudio_base_url("http://localhost:1234"),
            normalize_lmstudio_base_url("http://127.0.0.1:1234"),
        ]

        # If URL contains localhost or 127.0.0.1, also try host.docker.internal (for Docker containers)
        if "localhost" in self.lmstudio_url.lower() or "127.0.0.1" in self.lmstudio_url:
            docker_url = self.lmstudio_url.replace("localhost", "host.docker.internal").replace(
                "127.0.0.1", "host.docker.internal"
            )
            if docker_url not in candidates:
                candidates.append(docker_url)

        # Also add host.docker.internal as fallback
        if "http://host.docker.internal:1234/v1" not in candidates:
            candidates.append("http://host.docker.internal:1234/v1")

        # Remove duplicates while preserving order
        seen = set()
        unique_candidates = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                unique_candidates.append(candidate)

        return unique_candidates

    @staticmethod
    def estimate_model_max_context(model_name: str, is_reasoning_model: bool = False) -> int:
        """Heuristic context-window ceiling based on model-size tokens in the name.

        Used as a fallback when the provider does not report context length.
        """
        model_lower = model_name.lower()
        if "1b" in model_lower:
            return 2048
        if "32b" in model_lower or "30b" in model_lower:
            return 32768
        if "13b" in model_lower or "14b" in model_lower:
            return 16384
        if "7b" in model_lower or "8b" in model_lower:
            return 8192
        if "3b" in model_lower or "2b" in model_lower:
            return 4096
        return 4096 if is_reasoning_model else 2048

    async def check_model_context_length(
        self, model_name: str | None = None, threshold: int | None = None
    ) -> dict[str, Any]:
        """
        Check LMStudio model context length and validate against threshold.

        Args:
            model_name: Model name to check (defaults to rank model)
            threshold: Minimum context length threshold (defaults to MIN_CONTEXT_LENGTH_THRESHOLD)

        Returns:
            Dict with 'context_length', 'threshold', 'is_sufficient', 'model_name', 'method'

        Raises:
            RuntimeError: If context length cannot be determined or is below threshold
        """
        if model_name is None:
            model_name = self.model_rank

        if threshold is None:
            threshold = MIN_CONTEXT_LENGTH_THRESHOLD

        # If provider is not LMStudio, skip LMStudio context probe
        if getattr(self, "provider_rank", None) and self.provider_rank != "lmstudio":
            logger.info(
                "Skipping LMStudio context check for non-LMStudio provider",
                extra={"provider": self.provider_rank, "model": model_name, "threshold": threshold},
            )
            return {
                "context_length": None,
                "threshold": threshold,
                "is_sufficient": True,
                "model_name": model_name,
                "method": f"{self.provider_rank}_skip",
            }

        # Check for manual override via environment variable
        # Format: LMSTUDIO_CONTEXT_LENGTH_<MODEL_NAME>=<value>
        # e.g., LMSTUDIO_CONTEXT_LENGTH_qwen2-7b-instruct=32768
        override_key = f"LMSTUDIO_CONTEXT_LENGTH_{model_name.replace('/', '_').replace('-', '_')}"
        override_value = os.getenv(override_key)
        if override_value:
            try:
                context_length = int(override_value)
                logger.info(
                    f"Using manual context length override for {model_name}: "
                    f"{context_length} tokens (from {override_key})"
                )
                is_sufficient = context_length >= threshold
                return {
                    "context_length": context_length,
                    "threshold": threshold,
                    "is_sufficient": is_sufficient,
                    "model_name": model_name,
                    "method": "environment_override",
                }
            except ValueError:
                logger.warning(f"Invalid context length override value '{override_value}' for {override_key}, ignoring")

        # Method 0: Prefer LMStudio CLI (`lms ps`) when available.
        # This catches suffixed model identifiers (e.g. qwen/qwen3-8b:2) and
        # reports the effective loaded context even when /models omits context fields.
        try:
            which_result = subprocess.run(["which", "lms"], capture_output=True, text=True, timeout=5)
            if which_result.returncode == 0:
                ps_result = subprocess.run(["lms", "ps"], capture_output=True, text=True, timeout=10)
                if ps_result.returncode == 0:
                    loaded_contexts: list[int] = []
                    for raw_line in ps_result.stdout.splitlines():
                        line = raw_line.strip()
                        if not line or line.startswith("IDENTIFIER"):
                            continue
                        # Row shape:
                        # IDENTIFIER MODEL STATUS SIZE UNIT CONTEXT DEVICE [TTL]
                        match = re.match(r"^(\S+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s+(\d+)\b", line)
                        if not match:
                            continue
                        identifier = match.group(1)
                        model = match.group(2)
                        context_tokens = int(match.group(3))
                        if identifier == model_name or model == model_name or identifier.startswith(f"{model_name}:"):
                            loaded_contexts.append(context_tokens)

                    if loaded_contexts:
                        context_length = max(loaded_contexts)
                        is_sufficient = context_length >= threshold
                        logger.info(
                            "Detected LMStudio context via lms ps for %s: %s tokens",
                            model_name,
                            context_length,
                        )
                        return {
                            "context_length": context_length,
                            "threshold": threshold,
                            "is_sufficient": is_sufficient,
                            "model_name": model_name,
                            "method": "lms_ps",
                        }
        except Exception as exc:
            logger.debug("LMStudio CLI context probe failed for %s: %s", model_name, exc)

        lmstudio_urls = self._lmstudio_url_candidates()
        context_length = None
        detection_method = None

        # Method 1: Try to get context length from /models endpoint
        # LMStudio reports the configured context window here when available.
        async with httpx.AsyncClient() as client:
            for lmstudio_url in lmstudio_urls:
                try:
                    response = await client.get(f"{lmstudio_url}/models", timeout=5.0)
                    if response.status_code == 200:
                        models_data = response.json()
                        for model in models_data.get("data", []):
                            if model.get("id") == model_name:
                                # Check for context_length field (may vary by LMStudio version)
                                detected_context = model.get("context_length") or model.get("context_length_max")
                                if detected_context:
                                    if detected_context >= threshold:
                                        # Reasonable value that meets threshold - trust it
                                        context_length = detected_context
                                        detection_method = "api_models_endpoint"
                                        logger.info(
                                            f"Detected {model_name} context length "
                                            f"({context_length} tokens) from /models endpoint"
                                        )
                                        break
                                    # Value is below threshold - might be wrong, but log it
                                    logger.warning(
                                        f"/models endpoint returned {detected_context} for {model_name}, "
                                        f"which is below threshold {threshold}. Will verify with test request."
                                    )
                                    # Don't trust it - let Method 2 verify
                        if context_length:
                            break
                except httpx.HTTPError:
                    continue

        # Method 2: Test actual configured context length with a real request
        # This is more reliable than /models endpoint which may return theoretical max
        if context_length is None:
            async with httpx.AsyncClient() as client:
                for lmstudio_url in lmstudio_urls:
                    try:
                        # Test if threshold-sized context works
                        # Use longer timeout to allow for prompt processing (600s read timeout)
                        test_content = "x" * (threshold * 4)  # ~4 chars per token
                        test_payload = {
                            "model": model_name,
                            "messages": [{"role": "user", "content": test_content}],
                            "max_tokens": 10,
                        }

                        # Use longer timeout for test requests (600s read timeout like other LM Studio calls)
                        read_timeout = 600.0
                        response = await client.post(
                            f"{lmstudio_url}/chat/completions",
                            json=test_payload,
                            timeout=httpx.Timeout(60.0, connect=30.0, read=read_timeout),
                        )

                        if response.status_code == 200:
                            # Threshold works - model has at least this much context
                            # Trust that it's configured correctly and use threshold as minimum
                            context_length = threshold
                            detection_method = "test_request_threshold_verified"
                            logger.info(
                                f"Verified {model_name} supports threshold context length "
                                f"({threshold} tokens) via test request"
                            )
                            break
                        if response.status_code == 400:
                            # Parse error message for actual configured context length
                            error_text = response.text.lower()
                            if "context length" in error_text or "context overflow" in error_text:
                                # Try to extract the actual configured length from error
                                # Error format: "context length of only X tokens"
                                match = re.search(r"context length of (?:only )?(\d+)\s*tokens?", error_text)
                                if match:
                                    context_length = int(match.group(1))
                                    detection_method = "error_message_parsing"
                                    logger.info(
                                        f"Detected {model_name} context length "
                                        f"({context_length} tokens) from error message"
                                    )
                                    break
                                # Alternative: "greater than the context length of X tokens"
                                match = re.search(r"context length of (\d+)\s*tokens?", error_text)
                                if match:
                                    context_length = int(match.group(1))
                                    detection_method = "error_message_parsing"
                                    logger.info(
                                        f"Detected {model_name} context length "
                                        f"({context_length} tokens) from error message"
                                    )
                                    break
                    except httpx.TimeoutException:
                        # Test request timed out - this might mean the context is too large
                        # or the model is slow. Don't fail here, try next URL or fall back.
                        logger.warning(f"Context length test request timed out for {model_name} at {lmstudio_url}")
                        continue
                    except httpx.HTTPError as e:
                        logger.debug(f"Context length test request failed for {model_name} at {lmstudio_url}: {e}")
                        continue

        # Method 3: Fallback - infer from model name patterns
        if context_length is None:
            # Try to infer from model size in name (14b, 8b, etc.)
            model_lower = model_name.lower()
            inferred_context = None

            # Check for model size patterns
            if "14b" in model_lower or "13b" in model_lower:
                inferred_context = 16384  # 13B-14B models typically support 16K
            elif "30b" in model_lower or "32b" in model_lower:
                inferred_context = 32768  # 30B-32B models typically support 32K
            elif "8b" in model_lower or "7b" in model_lower:
                inferred_context = 8192  # 7B-8B models typically support 8K
            elif "4b" in model_lower or "3b" in model_lower:
                inferred_context = 4096  # 3B-4B models typically support 4K
            elif "1b" in model_lower or "2b" in model_lower:
                inferred_context = 2048  # 1B-2B models typically support 2K

            # Check if it's a reasoning model (often have larger context)
            is_reasoning = "r1" in model_lower or "reasoning" in model_lower
            if is_reasoning and inferred_context:
                # Reasoning models often configured with larger context
                inferred_context = max(inferred_context, 16384)

            if inferred_context:
                context_length = inferred_context
                detection_method = "fallback_model_name_inference"
                logger.warning(
                    f"Could not determine context length for {model_name} via API. "
                    f"Inferred {context_length} tokens from model name pattern. "
                    f"This may be incorrect - verify in LMStudio UI."
                )
            else:
                # Last resort: use conservative defaults
                context_length = MAX_CONTEXT_TOKENS if is_reasoning else 4096
                detection_method = "fallback_conservative"
                logger.warning(
                    f"Could not determine context length for {model_name}. "
                    f"Using conservative fallback: {context_length} tokens "
                    f"(reasoning_model={is_reasoning}). "
                    f"Verify actual context length in LMStudio UI."
                )

        is_sufficient = context_length >= threshold

        result = {
            "context_length": context_length,
            "threshold": threshold,
            "is_sufficient": is_sufficient,
            "model_name": model_name,
            "method": detection_method,
        }

        if not is_sufficient:
            # Provide actionable error message with CLI command
            cli_command = f"lms load {model_name} --context-length {threshold}"
            error_msg = (
                f"LMStudio model '{model_name}' has context length of {context_length} tokens, "
                f"which is below the required threshold of {threshold} tokens.\n"
                f"Fix: Run this command to load the model with sufficient context:\n"
                f"  {cli_command}\n"
                f"Or manually: LMStudio UI → Load model → Context tab → Set to {threshold}+ tokens → Reload"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(
            f"Context length check passed: {model_name} has {context_length} tokens "
            f"(threshold: {threshold}, method: {detection_method})"
        )

        return result

    def _validate_provider(self, provider: str) -> None:
        if not provider:
            raise RuntimeError(
                "No LLM provider configured for this agent. "
                "Set Provider to 'anthropic', 'openai', or 'lmstudio' in workflow settings."
            )
        if provider == "openai":
            if not self.workflow_openai_enabled:
                raise RuntimeError(
                    "OpenAI provider is disabled for agentic workflows "
                    "(enable WORKFLOW_OPENAI_ENABLED or set in Settings)."
                )
            if not self.openai_api_key:
                raise RuntimeError("OpenAI API key is not configured for agentic workflows.")
        elif provider == "anthropic":
            if not self.workflow_anthropic_enabled:
                raise RuntimeError(
                    "Anthropic provider is disabled for agentic workflows "
                    "(enable WORKFLOW_ANTHROPIC_ENABLED or set in Settings)."
                )
            if not self.anthropic_api_key:
                raise RuntimeError(
                    "Anthropic API key is not configured for agentic workflows. "
                    "Save the key in Settings (click Save after entering it) or set "
                    "WORKFLOW_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY in .env and restart workers."
                )
        elif provider != "lmstudio":
            raise RuntimeError(f"Provider '{provider}' is not supported for agentic workflows.")

    async def request_chat(
        self,
        *,
        provider: str,
        model_name: str | None,
        messages: list,
        max_tokens: int,
        temperature: float,
        timeout: float,
        failure_context: str,
        top_p: float | None = None,
        seed: int | None = None,
        cancellation_event: asyncio.Event | None = None,
    ) -> dict[str, Any]:
        # LAST-LINE CIRCUIT BREAKER: panic button — never invoke model with empty messages
        if not messages or (isinstance(messages, list) and len(messages) == 0):
            raise PreprocessInvariantError(
                f"LLM called with empty messages (failure_context={failure_context})",
                debug_artifacts={
                    "failure_context": failure_context,
                    "provider": provider,
                    "model_name": model_name,
                },
            )

        provider = self._canonicalize_provider(provider)
        logger.debug(f"request_chat called with provider={provider}, model_name={model_name}")
        self._validate_provider(provider)
        temperature = clamp_temperature_for_provider(provider, temperature)

        resolved_model = model_name or self.provider_defaults.get(provider) or self.lmstudio_model

        # Safety check: Log if we're routing to LMStudio when OpenAI might be expected
        if provider == "lmstudio":
            # Check if this might be a misconfiguration
            if self.openai_api_key and self.workflow_openai_enabled:
                logger.warning(
                    f"Routing to LMStudio but OpenAI is available and enabled. "
                    f"This may indicate provider wasn't set correctly in config. "
                    f"failure_context={failure_context}, model={resolved_model}"
                )
            # Normalize model name for LMStudio
            # Try to keep full name first (some models like google/gemma-3-12b need the prefix)
            # If that fails, fall back to removing prefix and date suffix
            normalized_model = resolved_model
            if normalized_model:
                # First, try the model name as-is (some models need the full path)
                # Only normalize if we get an error (handled in _post_lmstudio_chat)
                # For now, keep the full name - LMStudio will accept it if the model is loaded with that name
                # Remove only date suffixes (e.g., "-2507", "-2024") but keep prefixes

                normalized_model = re.sub(r"-\d{4,8}$", "", normalized_model)

            payload = {
                "model": normalized_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if top_p is not None:
                payload["top_p"] = float(top_p)  # Ensure it's a float, not string
                logger.debug(f"LMStudio payload top_p: {payload['top_p']} (type: {type(payload['top_p'])})")
            if seed is not None:
                payload["seed"] = seed
            return await self._post_lmstudio_chat(
                payload,
                model_name=resolved_model,
                timeout=timeout,
                failure_context=failure_context,
                cancellation_event=cancellation_event,
            )
        if provider == "openai":
            logger.info(f"Routing to OpenAI: model={resolved_model}, failure_context={failure_context}")
            return await self._call_openai_chat(
                messages=messages,
                model_name=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        if provider == "anthropic":
            return await self._call_anthropic_chat(
                messages=messages,
                model_name=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        raise RuntimeError(f"Provider '{provider}' is not implemented for agentic workflows.")

    async def _call_openai_chat(
        self, *, messages: list, model_name: str, temperature: float, max_tokens: int, timeout: float
    ) -> dict[str, Any]:
        # Defense-in-depth: circuit breaker at HTTP boundary
        if not messages or (isinstance(messages, list) and len(messages) == 0):
            raise PreprocessInvariantError("LLM invoked with empty messages (OpenAI path)")
        if not self.openai_api_key:
            raise RuntimeError("OpenAI API key not configured for agentic workflows.")

        # Runtime validation: check if model is valid for chat completions
        from src.web.routes.ai import is_valid_openai_chat_model

        if not is_valid_openai_chat_model(model_name):
            base_model = re.sub(r"-\d{4}-\d{2}-\d{2}(-preview)?$", "", model_name)
            base_model = re.sub(r"-latest$", "", base_model)
            base_model = re.sub(r"-preview$", "", base_model)
            suggestion = (
                f" Use a supported chat model (e.g. dated snapshot or '{base_model}' if still available)."
                if base_model != model_name
                else ""
            )
            raise RuntimeError(
                f"Model '{model_name}' is not a valid OpenAI chat completion model.{suggestion} "
                f"Specialized models (codex, audio, image, realtime, etc.) and unrecognized IDs are not supported."
            )

        # gpt-4.1/gpt-5.x require max_completion_tokens (max_tokens unsupported).
        # Reasoning models (o1/o3/o4/gpt-5.x) reject temperature -- omit proactively.
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }
        if model_supports_variable_temperature(model_name):
            payload["temperature"] = temperature

        def _temperature_unsupported(resp: httpx.Response) -> bool:
            if resp.status_code != 400:
                return False
            text = (resp.text or "").lower()
            return (
                "temperature" in text
                and "unsupported_value" in text
                and "only the default (1) value is supported" in text
            )

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0, read=timeout)) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )

            # Defense-in-depth: if an unrecognized model rejects temperature, retry without it.
            if _temperature_unsupported(response):
                logger.warning(
                    "OpenAI model %s rejected non-default temperature=%s; retrying request without temperature.",
                    model_name,
                    temperature,
                )
                retry_payload = dict(payload)
                retry_payload.pop("temperature", None)
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=retry_payload,
                )

        if response.status_code != 200:
            raise RuntimeError(f"OpenAI API error ({response.status_code}): {response.text}")

        return response.json()

    async def _call_anthropic_chat(
        self, *, messages: list, model_name: str, temperature: float, max_tokens: int, timeout: float
    ) -> dict[str, Any]:
        # Defense-in-depth: circuit breaker at HTTP boundary
        if not messages or (isinstance(messages, list) and len(messages) == 0):
            raise PreprocessInvariantError("LLM invoked with empty messages (Anthropic path)")
        if not self.anthropic_api_key:
            raise RuntimeError("Anthropic API key not configured for agentic workflows.")

        anthropic_api_url = os.getenv("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")

        anthropic_messages = []
        system_prompt = ""
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system" and not system_prompt:
                system_prompt = content or system_prompt
                continue
            anthropic_messages.append({"role": role, "content": content})

        if not anthropic_messages:
            anthropic_placeholder = messages[0].get("content", "") if messages else ""
            anthropic_messages.append({"role": "user", "content": anthropic_placeholder})

        payload = {
            "model": model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": anthropic_messages,
        }

        response = await self._call_anthropic_with_retry(
            api_key=self.anthropic_api_key, payload=payload, anthropic_api_url=anthropic_api_url, timeout=timeout
        )

        result = response.json()
        content = result.get("content", [])
        text_parts: list[str] = []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text") or ""
                    if t:
                        text_parts.append(t)
        text = "".join(text_parts)

        normalized: dict[str, Any] = {
            "choices": [{"message": {"content": text}}],
            "usage": result.get("usage", {}),
        }
        if isinstance(result.get("stop_reason"), str):
            normalized["stop_reason"] = result["stop_reason"]
        if isinstance(result.get("model"), str):
            normalized["model"] = result["model"]
        return normalized

    async def _call_anthropic_with_retry(
        self,
        *,
        api_key: str,
        payload: dict[str, Any],
        anthropic_api_url: str,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        timeout: float = 60.0,
    ) -> httpx.Response:
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        last_exception = None

        for attempt in range(max_retries):
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0, read=timeout)) as client:
                try:
                    response = await client.post(
                        anthropic_api_url,
                        headers=headers,
                        json=payload,
                    )

                    if response.status_code == 200:
                        return response

                    if response.status_code == 429:
                        delay = max(
                            self._parse_retry_after(response.headers.get("retry-after")), base_delay * (2**attempt)
                        )
                        delay = min(delay, max_delay)
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Anthropic API rate limited (429). "
                                f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s."
                            )
                            await asyncio.sleep(delay)
                            continue
                        raise RuntimeError(f"Anthropic API rate limit exceeded: {response.text}")

                    if 500 <= response.status_code < 600:
                        delay = min(base_delay * (2**attempt), max_delay)
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Anthropic API server error ({response.status_code}). Retrying after {delay:.1f}s."
                            )
                            await asyncio.sleep(delay)
                            continue

                    if response.status_code >= 400:
                        raise RuntimeError(f"Anthropic API error ({response.status_code}): {response.text}")

                except httpx.TimeoutException as exc:
                    delay = min(base_delay * (2**attempt), max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(f"Anthropic API timeout. Retry {attempt + 1}/{max_retries} after {delay:.1f}s.")
                        await asyncio.sleep(delay)
                        last_exception = exc
                        continue
                    raise RuntimeError("Anthropic API timeout") from exc
                except Exception as exc:
                    delay = min(base_delay * (2**attempt), max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(f"Anthropic API error: {exc}. Retrying after {delay:.1f}s.")
                        await asyncio.sleep(delay)
                        last_exception = exc
                        continue
                    raise RuntimeError(f"Anthropic API error: {exc}") from exc

        if last_exception:
            raise RuntimeError("Anthropic API failed after retries") from last_exception
        raise RuntimeError("Anthropic API failed after retries")

    def _parse_retry_after(self, header_value: str | None) -> float:
        if not header_value:
            return 30.0
        try:
            return float(header_value.strip())
        except ValueError:
            try:
                retry_date = parsedate_to_datetime(header_value)
                now = datetime.now(retry_date.tzinfo) if retry_date.tzinfo else datetime.now()
                delta = retry_date - now
                return max(0.0, delta.total_seconds())
            except (TypeError, ValueError):
                logger.warning(f"Could not parse retry-after header: {header_value}")
                return 30.0

    async def _post_lmstudio_chat(
        self,
        payload: dict[str, Any],
        *,
        model_name: str,
        timeout: float,
        failure_context: str,
        cancellation_event: asyncio.Event | None = None,
    ) -> dict[str, Any]:
        """
        Call LMStudio /chat/completions with automatic fallback handling.

        Args:
            payload: JSON payload to send to LMStudio
            model_name: Name of the LMStudio model (for logging)
            timeout: Request timeout in seconds
            failure_context: Contextual message for raised errors

        Returns:
            Parsed JSON response from LMStudio

        Raises:
            RuntimeError: If all LMStudio URL candidates fail
            httpx.TimeoutException: If request times out
        """
        # Defense-in-depth: circuit breaker at HTTP boundary
        payload_messages = payload.get("messages", []) if isinstance(payload, dict) else []
        if not payload_messages or (isinstance(payload_messages, list) and len(payload_messages) == 0):
            raise PreprocessInvariantError(
                f"LLM invoked with empty messages (LMStudio path, failure_context={failure_context})"
            )

        lmstudio_urls = self._lmstudio_url_candidates()
        last_error_detail = ""

        logger.info(f"LMStudio URL candidates for {failure_context}: {lmstudio_urls}")

        # Check for cancellation before starting
        if cancellation_event and cancellation_event.is_set():
            raise asyncio.CancelledError("Request cancelled by client")

        async def make_request(client: httpx.AsyncClient, url: str) -> httpx.Response:
            """Make the HTTP request as a cancellable task."""
            # For LM Studio, read timeout must be long enough to allow prompt processing
            # before any response data is sent.
            read_timeout = 600.0
            return await client.post(
                f"{url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=httpx.Timeout(timeout, connect=30.0, read=read_timeout),
            )

        # Use longer connect timeout to allow DNS resolution and connection establishment
        connect_timeout = 30.0  # Increased from 10.0 to handle Docker networking
        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=connect_timeout))
        try:
            for idx, lmstudio_url in enumerate(lmstudio_urls):
                # Check for cancellation before each attempt
                if cancellation_event and cancellation_event.is_set():
                    raise asyncio.CancelledError("Request cancelled by client")

                logger.info(
                    f"Attempting LMStudio at {lmstudio_url} with model {model_name} "
                    f"({failure_context}) attempt {idx + 1}/{len(lmstudio_urls)}"
                )
                logger.debug(
                    f"Request payload preview: model={payload.get('model')}, "
                    f"messages_count={len(payload.get('messages', []))}, "
                    f"max_tokens={payload.get('max_tokens')}, "
                    f"temperature={payload.get('temperature')}, top_p={payload.get('top_p')}"
                )

                # Log full payload for debugging (truncate long content)
                if logger.isEnabledFor(logging.DEBUG):
                    payload_copy = payload.copy()
                    if "messages" in payload_copy:
                        messages_copy = []
                        for msg in payload_copy["messages"]:
                            msg_copy = msg.copy()
                            if "content" in msg_copy and len(msg_copy["content"]) > 500:
                                msg_copy["content"] = (
                                    msg_copy["content"][:500] + f"... [truncated, total length: {len(msg['content'])}]"
                                )
                            messages_copy.append(msg_copy)
                        payload_copy["messages"] = messages_copy
                    logger.debug(f"Full LMStudio request payload: {json.dumps(payload_copy, indent=2)}")

                try:
                    # Make request
                    request_task = asyncio.create_task(make_request(client, lmstudio_url))

                    # Monitor for cancellation while waiting for response
                    if cancellation_event:
                        # Create a task that waits for cancellation
                        async def wait_for_cancellation():
                            if cancellation_event:
                                await cancellation_event.wait()

                        cancellation_task = asyncio.create_task(wait_for_cancellation())

                        # Wait for either request completion or cancellation
                        done, pending = await asyncio.wait(
                            [request_task, cancellation_task], return_when=asyncio.FIRST_COMPLETED
                        )

                        # Cancel pending tasks
                        for task in pending:
                            task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await task

                        # Check if cancellation occurred
                        if cancellation_event.is_set():
                            # Cancel the request task and close the client to stop the HTTP request
                            if not request_task.done():
                                request_task.cancel()
                                # Explicitly close the client connection to stop the underlying HTTP request
                                with contextlib.suppress(Exception):
                                    await client.aclose()
                                with contextlib.suppress(
                                    asyncio.CancelledError, httpx.RequestError, httpx.ConnectError
                                ):
                                    await request_task
                            raise asyncio.CancelledError("Request cancelled by client")

                        # Get the response
                        response = await request_task
                    else:
                        # No cancellation support, just await the request
                        response = await request_task

                    if response.status_code == 200:
                        result = response.json()
                        # Log successful response for debugging
                        logger.info(f"LMStudio response received: status=200, model={result.get('model', 'unknown')}")
                        if "choices" in result and len(result["choices"]) > 0:
                            content = result["choices"][0].get("message", {}).get("content", "")
                            logger.debug(f"LMStudio response content length: {len(content)} chars")
                            logger.debug(f"LMStudio response content preview: {content[:500]}")
                        if "usage" in result:
                            logger.info(f"LMStudio token usage: {result['usage']}")
                        return result
                    # Extract error message from response
                    error_text = response.text
                    try:
                        error_json = response.json()
                        error_message = (
                            error_json.get("error", {}).get("message", error_text)
                            if isinstance(error_json.get("error"), dict)
                            else error_text
                        )
                    except (ValueError, KeyError, AttributeError):
                        error_message = error_text[:500]  # Limit length

                    last_error_detail = f"Status {response.status_code}: {error_message}"
                    logger.error(f"LMStudio at {lmstudio_url} returned {response.status_code}: {error_message}")

                    # For 400 errors, check if it's a model name issue and retry with different format
                    if response.status_code == 400:
                        error_lower = error_message.lower()
                        current_model_in_payload = payload.get("model", "")

                        # Check if it's a model identifier error - try with/without prefix
                        if "invalid model identifier" in error_lower or (
                            "model" in error_lower and ("not found" in error_lower or "not loaded" in error_lower)
                        ):
                            # Try both directions: with prefix (if model_name has it) and without prefix
                            retry_attempts = []

                            # If model_name has a prefix but payload doesn't, try with prefix
                            if "/" in model_name and "/" not in current_model_in_payload:
                                retry_attempts.append(("with prefix", model_name))

                            # If model_name has a prefix, also try without prefix
                            if "/" in model_name:
                                model_without_prefix = model_name.split("/")[-1]
                                if model_without_prefix != current_model_in_payload:
                                    retry_attempts.append(("without prefix", model_without_prefix))

                            # Try each retry attempt
                            for retry_type, retry_model in retry_attempts:
                                logger.info(f"Retrying {retry_type}: {retry_model}")
                                payload_retry = payload.copy()
                                payload_retry["model"] = retry_model
                                try:
                                    response_retry = await make_request(client, lmstudio_url)
                                    if response_retry.status_code == 200:
                                        result = response_retry.json()
                                        logger.info(f"LMStudio accepted model {retry_type}: {retry_model}")
                                        return result
                                    logger.debug(f"Retry {retry_type} failed: {response_retry.status_code}")
                                except Exception as retry_exc:
                                    logger.debug(f"Retry {retry_type} failed: {retry_exc}")

                        # Close client before raising
                        with contextlib.suppress(Exception):
                            await client.aclose()

                        # Check for common errors that indicate LMStudio isn't ready
                        if (
                            "context length" in error_lower
                            or (
                                "model" in error_lower
                                and "not loaded" in error_lower
                                and "invalid model identifier" not in error_lower
                            )
                            or "no model" in error_lower
                        ):
                            raise RuntimeError(
                                f"{failure_context}: LMStudio is not ready. "
                                f"Please ensure LMStudio is running and a model is loaded."
                            )

                        raise RuntimeError(
                            f"{failure_context}: Invalid request to LMStudio. "
                            f"Status {response.status_code}: {error_message}. "
                            f"This usually means the model '{model_name}' is not loaded, "
                            f"the request format is invalid, or the context window is too small."
                        )

                except RuntimeError:
                    # Re-raise RuntimeErrors (like 400 errors) immediately without trying other URLs
                    with contextlib.suppress(Exception):
                        await client.aclose()
                    raise

                except httpx.TimeoutException as e:
                    last_error_detail = f"Request timeout after {timeout}s"
                    logger.warning(f"LMStudio at {lmstudio_url} timed out: {e}")
                    # Don't retry if this is the last URL - fail fast
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(
                            f"{failure_context}: Request timeout after {timeout}s - "
                            f"LMStudio service may be down, slow, or overloaded. "
                            f"Check if LMStudio is running at {lmstudio_url}"
                        ) from e
                    # Continue to next URL candidate
                    continue

                except httpx.ConnectError as e:
                    last_error_detail = f"Connection error: {str(e)}"
                    logger.error(f"LMStudio at {lmstudio_url} connection failed: {type(e).__name__}: {e}")
                    # Don't retry on connection errors - try next URL immediately
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(
                            f"{failure_context}: Cannot connect to LMStudio service. "
                            f"Tried URLs: {lmstudio_urls}. Last error: {str(e)}. "
                            f"Verify LMStudio is running and accessible at {lmstudio_url}"
                        ) from e
                    # Continue to next URL candidate
                    continue

                except asyncio.CancelledError:
                    # Re-raise cancellation errors
                    raise
                except Exception as e:
                    last_error_detail = str(e)
                    logger.error(f"LMStudio API request failed at {lmstudio_url}: {e}")
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(f"{failure_context}: {str(e)}") from e
        finally:
            # Ensure client is closed
            with contextlib.suppress(Exception):
                await client.aclose()

        raise RuntimeError(f"{failure_context}: All LMStudio URLs failed. Last error: {last_error_detail}")

    async def rank_article(
        self,
        title: str,
        content: str,
        source: str,
        url: str,
        _prompt_template_path: str | None = None,
        prompt_template: str | None = None,
        execution_id: int | None = None,
        article_id: int | None = None,
        qa_feedback: str | None = None,
        ground_truth_rank: float | None = None,
        ground_truth_details: dict[str, float | None] | None = None,
    ) -> dict[str, Any]:
        """
        Rank an article using LLM (Step 1 of workflow).

        Args:
            title: Article title
            content: Article content (filtered)
            source: Article source name
            url: Article URL
            _prompt_template_path: Unused; prompt_template from workflow config is required
            prompt_template: Optional prompt template string (required from workflow config)
            ground_truth_rank: Optional 1-10 ground truth rank to log to Langfuse
            ground_truth_details: Optional dict of source scores/rounding used for ground truth

        Returns:
            Dict with 'score' (1-10 float) and 'reasoning' (str)
        """
        # Use provided prompt template only (no file fallback)
        if not prompt_template:
            raise ValueError(
                "RankAgent prompt_template must be provided from workflow config. No file fallback available."
            )

        prompt_template_str = prompt_template
        system_override = None
        is_json_prompt = False
        try:
            parsed_prompt = json.loads(prompt_template_str)
            if isinstance(parsed_prompt, dict):
                is_json_prompt = True
                user_template = (
                    parsed_prompt.get("user") or parsed_prompt.get("user_template") or parsed_prompt.get("prompt") or ""
                )
                system_override = parsed_prompt.get("system") or parsed_prompt.get("role") or None
                if user_template:
                    prompt_template_str = user_template
                elif system_override:
                    prompt_template_str = system_override
        except json.JSONDecodeError:
            pass

        if is_json_prompt and not system_override:
            raise PreprocessInvariantError(
                "RankAgent prompt resolved to an empty system message. "
                "Ensure the prompt config contains a non-empty 'system' or 'role' key."
            )

        logger.info(f"Using RankAgent prompt from workflow config (length: {len(prompt_template_str)} chars)")

        # Get actual model context length to use for truncation
        # IMPORTANT: LM Studio's configured context may be much smaller than detected/theoretical max
        # Use very conservative fixed limits to ensure we never exceed actual configured context
        # Reasoning models: 8192 max, non-reasoning: 4096 max
        # These are conservative limits that should work with most LM Studio configurations

        # Determine model used for ranking
        model_name = self.model_rank
        if not model_name:
            raise ValueError("RankAgent model is not configured. Set agent_models.RankAgent or LMSTUDIO_MODEL_RANK.")

        # For reasoning models (deepseek-r1), need higher max_tokens
        # But keep conservative to avoid exceeding context
        # Reasoning can use 1000-2000 tokens, final answer needs ~100 tokens
        is_reasoning_model = "r1" in model_name.lower() or "reasoning" in model_name.lower()
        # Increase max_output_tokens to prevent truncation (non-reasoning models need more space for detailed analysis)
        max_output_tokens = 2000 if is_reasoning_model else 2000  # Increased from 600 to prevent truncation

        # Determine model-specific context limits based on model size
        model_max_context = self.estimate_model_max_context(model_name, is_reasoning_model)

        try:
            context_check = await self.check_model_context_length(model_name=model_name)
            detected_length = context_check["context_length"]
            detection_method = context_check.get("method", "unknown")
        except Exception as e:
            logger.warning(f"Could not get model context length: {e}")
            detected_length = model_max_context
            detection_method = "fallback"

        # If detection returned None (e.g., non-LMStudio provider skip), fall back to model_max_context
        if detected_length is None:
            detected_length = model_max_context
            detection_method = f"{detection_method}_fallback_none"

        # Trust detected context if it's reasonable (not too large, within model limits)
        # Only use very conservative caps if detection seems unreliable
        if detection_method == "environment_override":
            # Trust manual override completely
            actual_context_length = detected_length
        elif detection_method == "api_models_endpoint":
            # LMStudio reported a configured context window directly; trust it with a safety margin.
            actual_context_length = int(detected_length * 0.90)
            logger.info(f"Trusting LMStudio reported context {detected_length} for {model_name}")
        elif 4096 <= detected_length <= model_max_context:
            # Detected context is in reasonable range - trust it (with small safety margin)
            actual_context_length = int(detected_length * 0.90)  # 10% safety margin
            logger.info(f"Trusting detected context {detected_length} for {model_name} (method: {detection_method})")
        elif detected_length > model_max_context:
            # Detected context exceeds model's likely max - cap to model max
            actual_context_length = int(model_max_context * 0.90)
            logger.warning(
                f"Detected context {detected_length} exceeds model max {model_max_context}, "
                f"capping to {actual_context_length}"
            )
        else:
            # Detected context is very small or unreliable - use conservative model-specific cap
            conservative_cap = min(4096, model_max_context) if is_reasoning_model else min(2048, model_max_context)
            actual_context_length = int(conservative_cap * 0.75)  # 25% safety margin for unreliable detection
            logger.warning(
                f"Using conservative context {actual_context_length} for {model_name} "
                f"(detected: {detected_length}, method: {detection_method})"
            )

        logger.info(
            f"Using context length {actual_context_length} for truncation "
            f"(detected: {detected_length}, reasoning: {is_reasoning_model}, "
            f"model_max: {model_max_context}, method: {detection_method})"
        )

        # Estimate prompt overhead more accurately
        # Account for: template text + title + source + URL + system message + formatting
        base_prompt_tokens = self._estimate_tokens(
            prompt_template_str.format(
                title=title,
                source=source,
                url=url,
                content="",  # Estimate without content first
            )
        )
        # Add system message if present
        system_message_tokens = 50 if not self._model_needs_system_conversion(model_name) else 0
        # Add message formatting overhead (~100 tokens for JSON structure, role fields, etc.)
        message_formatting_overhead = 100
        # Total prompt overhead (not including content)
        total_prompt_overhead = base_prompt_tokens + system_message_tokens + message_formatting_overhead

        # Truncate content to fit within remaining context
        # Reserve: prompt overhead + output tokens + safety margin (15%)
        available_tokens = actual_context_length - total_prompt_overhead - max_output_tokens
        available_tokens = int(available_tokens * 0.85)  # 15% safety margin

        if available_tokens <= 0:
            logger.error(f"Available tokens for content is {available_tokens} - prompt overhead too large")
            available_tokens = 1000  # Minimum fallback

        content_tokens = self._estimate_tokens(content)
        truncation_warning = None
        if content_tokens <= available_tokens:
            truncated_content = content
        else:
            # Truncate to fit
            max_chars = available_tokens * 4
            truncated = content[:max_chars]

            # Try to truncate at sentence boundary
            last_period = truncated.rfind(".")
            last_newline = truncated.rfind("\n")
            last_boundary = max(last_period, last_newline)

            if last_boundary > max_chars * 0.8:
                truncated = truncated[: last_boundary + 1]

            truncated_content = truncated + "\n\n[Content truncated to fit context window]"

            truncation_warning = (
                f"Content truncated: {content_tokens} → {self._estimate_tokens(truncated_content)} tokens "
                f"(available: {available_tokens}, context: {actual_context_length})"
            )
            logger.warning(
                f"Truncated article content from {content_tokens} to "
                f"{self._estimate_tokens(truncated_content)} tokens (available: {available_tokens}, "
                f"prompt overhead: {total_prompt_overhead}, max_output: {max_output_tokens}, "
                f"context: {actual_context_length})"
            )

        # Format prompt with truncated content
        prompt_text = prompt_template_str.format(title=title, source=source, url=url, content=truncated_content)

        # Add QA feedback if provided
        if qa_feedback:
            prompt_text = f"{qa_feedback}\n\n{prompt_text}"

        # Final verification: estimate total prompt tokens
        total_prompt_tokens = self._estimate_tokens(prompt_text) + system_message_tokens + message_formatting_overhead
        total_tokens_needed = total_prompt_tokens + max_output_tokens
        if total_tokens_needed > actual_context_length:
            logger.error(
                f"WARNING: Total tokens needed ({total_tokens_needed}) "
                f"exceeds context length ({actual_context_length}). "
                f"This may cause context overflow errors."
            )

        # Use ranking-specific model
        model_name = self.model_rank

        # For Mistral, use direct instruction format without separate system message
        system_message = system_override or (
            "You are a cybersecurity detection engineer. "
            "Score threat intelligence articles 1-10 for SIGMA huntability. "
            "Output only a score and brief reasoning."
        )
        if self._model_needs_system_conversion(model_name):
            # Single user message with integrated instructions
            combined_prompt = f"{system_message}\n\n{prompt_text}" if system_message else prompt_text
            messages = [{"role": "user", "content": combined_prompt}]
        else:
            messages = [{"role": "system", "content": system_message}, {"role": "user", "content": prompt_text}]

        converted_messages = self._convert_messages_for_model(messages, model_name)
        logger.info(f"Ranking request: max_tokens={max_output_tokens} (reasoning_model={is_reasoning_model})")

        ranking_metadata = {
            "prompt_length": len(prompt_text),
            "max_tokens": max_output_tokens,
            "title": title,
            "source": source,
            "messages": messages,  # Include messages for input display
        }

        if ground_truth_rank is not None:
            ranking_metadata["ground_truth_rank"] = ground_truth_rank
        if ground_truth_details:
            ranking_metadata["ground_truth_details"] = ground_truth_details

        # Trace LLM call with Langfuse
        with trace_llm_call(
            name="rank_article",
            model=model_name,
            execution_id=execution_id,
            article_id=article_id,
            metadata=ranking_metadata,
        ) as generation:
            try:
                # Reasoning models need longer timeouts - they generate extensive reasoning + answer
                ranking_timeout = 180.0 if is_reasoning_model else 60.0

                result = await self.request_chat(
                    provider=self.provider_rank,
                    model_name=model_name,
                    messages=converted_messages,
                    max_tokens=max_output_tokens,
                    temperature=self.temperature_rank,
                    timeout=ranking_timeout,
                    failure_context="Failed to rank article",
                    top_p=self.top_p_rank,
                    seed=self.seed,
                )

                # Deepseek-R1 returns reasoning in 'reasoning_content', fallback to 'content'
                message = result["choices"][0]["message"]
                response_text = message.get("content", "") or message.get("reasoning_content", "")

                # Check if response was truncated due to token limit
                finish_reason = result["choices"][0].get("finish_reason", "")
                response_truncation_warning = None
                if finish_reason == "length":
                    completion_tokens = result.get("usage", {}).get("completion_tokens", 0)
                    response_truncation_warning = (
                        f"Response truncated (finish_reason=length). "
                        f"Used {completion_tokens} tokens. "
                        f"max_tokens={max_output_tokens} may need to be increased."
                    )
                    logger.warning(
                        f"Ranking response was truncated (finish_reason=length). "
                        f"Used {completion_tokens} tokens. "
                        f"max_tokens={max_output_tokens} may need to be increased."
                    )

                # Fail if response is empty
                if not response_text or len(response_text.strip()) == 0:
                    logger.error("LLM returned empty response for ranking")
                    raise ValueError("LLM returned empty response for ranking. Check LMStudio is responding correctly.")

                logger.info(f"Ranking response received: {len(response_text)} chars (finish_reason={finish_reason})")

                # Parse score from response - look for "SIGMA HUNTABILITY SCORE: X" pattern first

                score = None

                # Try multiple patterns, searching entire response (not just first 200 chars)
                # Pattern 1: "SIGMA HUNTABILITY SCORE: X" (exact format)
                score_match = re.search(
                    r"SIGMA\s+HUNTABILITY\s+SCORE[:\s]+(\d+(?:\.\d+)?)", response_text, re.IGNORECASE
                )
                if score_match:
                    score = float(score_match.group(1))
                else:
                    # Pattern 2: "Score: X" or "**Score:** X"
                    score_match = re.search(
                        r"(?:^|\n|^|\*|#)\s*Score[:\s#*]+\s*(\d+(?:\.\d+)?)",
                        response_text,
                        re.IGNORECASE | re.MULTILINE,
                    )
                    if score_match:
                        score = float(score_match.group(1))
                    else:
                        # Pattern 2b: "Score: N/10" format
                        # Handles custom prompts that produce "Agent Value Score: 6/10" etc.
                        score_match = re.search(
                            r"Score[:\s]+(\d+(?:\.\d+)?)\s*/\s*10",
                            response_text,
                            re.IGNORECASE,
                        )
                        if score_match:
                            score = float(score_match.group(1))
                        else:
                            # Pattern 2c: Generic "N/10" anywhere in response
                            score_match = re.search(
                                r"\b(\d+(?:\.\d+)?)\s*/\s*10\b",
                                response_text,
                            )
                            if score_match:
                                score = float(score_match.group(1))
                            else:
                                # Pattern 3: Look for numbers 1-10 in the last 500 chars (where final answer usually is)
                                # Reasoning models often put the score at the end after reasoning
                                tail_text = response_text[-500:] if len(response_text) > 500 else response_text
                                score_match = re.search(r"\b([1-9]|10)(?:\.\d+)?\b", tail_text)
                                if score_match:
                                    score = float(score_match.group(1))

                if score is not None:
                    score = max(1.0, min(10.0, score))  # Clamp to 1-10
                    logger.info(f"Parsed ranking score: {score}/10")
                else:
                    # If truncated and no score found, provide helpful error
                    if finish_reason == "length":
                        error_msg = (
                            f"Ranking response was truncated and no score found. "
                            f"Response length: {len(response_text)} chars. "
                            f"Try increasing max_tokens (current: {max_output_tokens}). "
                            f"Response preview: {response_text[-300:]}"
                        )
                    else:
                        error_msg = f"Could not parse score from LLM response. Response: {response_text[:500]}"
                    logger.error(error_msg)
                    log_llm_error(generation, ValueError(error_msg))
                    raise ValueError(error_msg)

                # Log completion to Langfuse
                usage = result.get("usage", {})
                completion_metadata = {
                    "score": score,
                    "finish_reason": finish_reason,
                    "response_length": len(response_text),
                }
                if ground_truth_rank is not None:
                    completion_metadata["ground_truth_rank"] = ground_truth_rank
                if ground_truth_details:
                    completion_metadata["ground_truth_details"] = ground_truth_details

                log_llm_completion(
                    generation,
                    input_messages=messages,
                    output=response_text.strip(),
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                    metadata=completion_metadata,
                    ground_truth=ground_truth_rank,
                )

                warnings = []
                if truncation_warning:
                    warnings.append(truncation_warning)
                if response_truncation_warning:
                    warnings.append(response_truncation_warning)

                return {
                    "score": score,
                    "reasoning": response_text.strip(),
                    "raw_response": response_text,
                    "warnings": warnings if warnings else None,
                }

            except Exception as e:
                logger.error(f"Error ranking article: {e}")
                if generation:
                    log_llm_error(generation, e)
                raise

    async def run_extraction_agent(
        self,
        agent_name: str,
        content: str,
        title: str,
        url: str,
        prompt_config: dict[str, Any],
        qa_prompt_config: dict[str, Any] | None = None,
        max_extraction_retries: int = 5,
        execution_id: int | None = None,
        model_name: str | None = None,
        temperature: float = 0.0,
        top_p: float | None = None,
        qa_model_override: str | None = None,
        provider: str | None = None,
        attention_preprocessor_enabled: bool = True,
    ) -> dict[str, Any]:
        """
        Run a generic extraction agent with optional QA loop.

        Args:
            agent_name: Name of the sub-agent (e.g. "CmdlineExtract")
            content: Article content
            title: Article title
            url: Article URL
            prompt_config: Extraction prompt configuration
            qa_prompt_config: QA prompt configuration (optional)
            max_extraction_retries: Max retries on extraction exceptions/timeouts (QA runs exactly once per attempt)
            provider: LLM provider to use (e.g. "lmstudio", "openai", "anthropic").
                     If None, uses self.provider_extract (from ExtractAgent_provider)

        Returns:
            Dict with extraction results
        """
        logger.info(
            f"Running extraction agent {agent_name} (QA enabled: {bool(qa_prompt_config)}, provider={provider}, model_name={model_name})"
        )

        # Validate content is not empty
        if not content or len(content.strip()) == 0:
            error_msg = f"Empty content provided to {agent_name}. Cannot run extraction."
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Validate prompt_config
        if not prompt_config:
            error_msg = f"Empty prompt_config provided to {agent_name}. Cannot run extraction."
            logger.error(error_msg)
            raise ValueError(error_msg)
        _validate_extraction_prompt_config(agent_name, prompt_config)
        logger.debug(f"{agent_name} prompt_config keys: {list(prompt_config.keys())}")

        current_try = 0
        feedback = ""
        last_result = {"items": [], "count": 0}

        # Determine model to use
        # Priority: 1) provided model_name, 2) prompt_config.model, 3) ExtractAgent model, 4) error
        if not model_name:
            # Check if prompt_config has a model field (some prompts store model in config)
            model_name = prompt_config.get("model")
        if not model_name:
            model_name = self.model_extract
        if not model_name:
            raise ValueError(
                f"No model configured for {agent_name}. "
                f"Please set {agent_name}_model or ExtractAgent model in workflow config."
            )

        source = "parameter" if model_name == prompt_config.get("model") else "fallback"
        logger.info(f"{agent_name} resolved model: {model_name} (from: {source})")

        while current_try < max_extraction_retries:
            current_try += 1

            # 1. Run Extraction
            try:
                resolved_provider = (
                    provider if provider and isinstance(provider, str) and provider.strip() else self.provider_extract
                )
                if not (provider and isinstance(provider, str) and provider.strip()):
                    logger.warning(
                        f"{agent_name} provider was None/empty, "
                        f"falling back to ExtractAgent provider: {resolved_provider}. "
                        f"This may indicate the provider wasn't set in workflow config."
                    )
                effective_provider = self._canonicalize_provider(resolved_provider)
                if not effective_provider:
                    effective_provider = self._canonicalize_provider(self.provider_extract) or resolved_provider

                context_limit_tokens = self._get_context_limit(effective_provider, model_name=model_name)
                if effective_provider == "lmstudio" and model_name:
                    try:
                        context_check = await self.check_model_context_length(model_name=model_name)
                        detected_context_limit = context_check.get("context_length")
                        if isinstance(detected_context_limit, int) and detected_context_limit > 0:
                            context_limit_tokens = detected_context_limit
                            logger.info(
                                f"{agent_name} using detected LMStudio context limit "
                                f"{context_limit_tokens} for model {model_name} "
                                f"(method: {context_check.get('method', 'unknown')})"
                            )
                    except Exception as e:
                        logger.warning(
                            f"{agent_name} could not determine LMStudio context length for {model_name}: {e}"
                        )

                # CmdlineExtract: optional attention preprocessor (snippets first, then full article)
                snippet_count: int | None = None
                if agent_name == "CmdlineExtract" and attention_preprocessor_enabled:
                    from src.services.cmdline_attention_preprocessor import process as preprocess_cmdline_attention

                    preprocess_result = preprocess_cmdline_attention(content, agent_name=agent_name)
                    snippets = preprocess_result.get("high_likelihood_snippets", [])
                    snippet_count = len(snippets)
                    full_article = preprocess_result.get("full_article", content)
                    logger.debug(f"Cmdline attention preprocessor enabled: True. Snippets found: {snippet_count}")

                    # Cheap mechanical invariant: byte-preserving preprocessor must not alter newline count
                    orig_nl = content.count("\n")
                    prep_nl = full_article.count("\n")
                    if abs(prep_nl - orig_nl) > 1:
                        raise PreprocessInvariantError(
                            f"{agent_name}: newline count mismatch (preprocessed={prep_nl}, original={orig_nl})",
                            debug_artifacts={
                                "agent_name": agent_name,
                                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                                "attention_preprocessor_enabled": True,
                                "execution_id": execution_id,
                                "orig_newline_count": orig_nl,
                                "prep_newline_count": prep_nl,
                            },
                        )

                    # Cap snippets to 25% of context budget (tokens) before joining.
                    # Dense articles can produce 300+ snippets; without a ceiling the
                    # snippet section crowds out the article itself (article_2068: 0/7
                    # extracted with preprocessor ON, 6/7 with it OFF).
                    # Trim from the end -- earlier snippets tend to be higher-signal.
                    if snippets:
                        max_snippet_tokens = int(context_limit_tokens * 0.25)
                        kept: list[str] = []
                        budget = max_snippet_tokens
                        for s in snippets:
                            cost = self._estimate_tokens(s) + 2  # +2 for separator
                            if cost > budget:
                                break
                            kept.append(s)
                            budget -= cost
                        snippets = kept or snippets[:1]  # always keep at least one
                        snippet_count = len(snippets)

                    snippets_section = "\n\n".join(snippets) if snippets else ""
                    snippets_header = "=== HIGH-LIKELIHOOD COMMAND SNIPPETS ===\n"
                    full_header = "\n\n=== FULL ARTICLE (REFERENCE ONLY) ===\n"
                    combined_prefix = snippets_header + snippets_section + full_header

                    # Reserve: snippets + 256 token overhead + template + output
                    snippet_tokens = self._estimate_tokens(combined_prefix)
                    overhead_tokens = 256 + PROMPT_OVERHEAD_TOKENS + 1000
                    available_for_article = max(0, context_limit_tokens - snippet_tokens - overhead_tokens)
                    available_for_article = int(available_for_article * 0.9)  # safety margin

                    article_tokens = self._estimate_tokens(full_article)
                    if article_tokens <= available_for_article:
                        truncated_article = full_article
                    else:
                        max_chars = available_for_article * 4
                        truncated_article = full_article[:max_chars]
                        last_boundary = max(truncated_article.rfind("."), truncated_article.rfind("\n"))
                        if last_boundary > max_chars * 0.8:
                            truncated_article = truncated_article[: last_boundary + 1]
                        truncated_article = truncated_article + "\n\n[Content truncated to fit context window]"

                    truncated_content = combined_prefix + truncated_article
                else:
                    truncated_content = self._truncate_content(content, context_limit_tokens, 1000)

                logger.info(
                    f"{agent_name} prompt construction: content_length={len(content)}, "
                    f"truncated_length={len(truncated_content)}, "
                    f"context_limit={context_limit_tokens}"
                )

                # Legacy format - build prompt from individual fields.
                # The extractor/QA scaffold is fixed in runtime; UI edits only affect
                # the editable prompt fields (role/objective, instructions, examples).
                task = prompt_config.get("objective", "Extract information.")
                instructions = prompt_config.get("instructions", "Output valid JSON.")
                output_format = json.dumps(prompt_config.get("output_format", {}), indent=2)
                json_example = prompt_config.get("json_example")
                json_example_str = ""
                if json_example:
                    json_format_instruction = (
                        "\n\nYou MUST output JSON in this exact format. "
                        "No markdown code fences, no prose, just the raw JSON object."
                    )
                    if isinstance(json_example, dict):
                        json_example_str = (
                            f"\n\nREQUIRED JSON STRUCTURE (example):\n"
                            f"{json.dumps(json_example, indent=2)}"
                            f"{json_format_instruction}"
                        )
                    else:
                        json_example_str = (
                            f"\n\nREQUIRED JSON STRUCTURE (example):\n{json_example}{json_format_instruction}"
                        )

                user_prompt = f"""Title: {title}
URL: {url}

Content:
{truncated_content}

Task: {task}

Output Format Specification:
{output_format}{json_example_str}

CRITICAL INSTRUCTIONS: {instructions}

IMPORTANT: Your response must end with a valid JSON object matching the structure above.
If you include reasoning, place it BEFORE the JSON. The JSON must be parseable and complete.
"""

                # Append traceability requirements for observable traceability feature.
                # Simple extractors require a generic "value" identity field.
                # Structured extractors (ScheduledTasksExtract) use domain-specific identity
                # fields (task_name, task_path, trigger, etc.) in place of "value" -- the
                # injected reminder must match what the json_example schema actually specifies
                # so the LLM does not hallucinate a "value" field that is not in the contract.
                _SIMPLE_EXTRACTORS = (
                    "CmdlineExtract",
                    "ProcTreeExtract",
                    "HuntQueriesExtract",
                    "RegistryExtract",
                    "ServicesExtract",
                )
                _STRUCTURED_EXTRACTORS = ("ScheduledTasksExtract",)
                _traceability_common = """

TRACEABILITY (REQUIRED): For each extracted item, the object MUST include these fields:
- source_evidence: The full paragraph from the article containing this observable (verbatim).
- extraction_justification: Which prompt rule or rubric triggered this extraction.
- confidence_score: A number between 0.0 and 1.0 for extraction confidence.
Every item in the output array MUST be an object (not a plain string)."""
                if user_prompt and agent_name in _SIMPLE_EXTRACTORS:
                    user_prompt = (
                        user_prompt.rstrip()
                        + _traceability_common
                        + ' The object MUST have a "value" field plus source_evidence, extraction_justification, and confidence_score.\n'
                    )
                elif user_prompt and agent_name in _STRUCTURED_EXTRACTORS:
                    user_prompt = (
                        user_prompt.rstrip()
                        + _traceability_common
                        + " The object MUST include the domain-specific identity fields defined in your json_example schema plus source_evidence, extraction_justification, and confidence_score.\n"
                    )

                logger.debug(f"{agent_name} full user prompt length: {len(user_prompt)} chars")
                if feedback:
                    user_prompt = f"PREVIOUS FEEDBACK (FIX THESE ISSUES):\n{feedback}\n\n" + user_prompt
                # Minimal user prefix when preset uses "user" (bulk in system, minimal in user)
                user_prefix = (prompt_config.get("user") or "").strip()
                if user_prefix:
                    user_prompt = f"{user_prefix}\n\n{user_prompt}"

                system_content = prompt_config.get("system") or prompt_config.get(
                    "role", "You are a detection engineer."
                )

                messages = [{"role": "system", "content": system_content}, {"role": "user", "content": user_prompt}]

                # Fail-fast: never call model with empty/malformed request
                content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
                _validate_preprocess_invariants(
                    messages,
                    agent_name=agent_name,
                    content_sha256=content_sha256,
                    attention_preprocessor_enabled=attention_preprocessor_enabled,
                    execution_id=execution_id,
                    user_prompt=user_prompt,
                )

                converted_messages = self._convert_messages_for_model(messages, model_name)

                # Reasoning models need longer timeouts - they generate extensive reasoning + answer
                is_reasoning_model = "r1" in model_name.lower() or "reasoning" in model_name.lower()
                extraction_timeout = 600.0 if is_reasoning_model else 180.0

                # Build Langfuse metadata (include preprocessor info for CmdlineExtract)
                trace_metadata: dict[str, Any] = {
                    "agent_name": agent_name,
                    "attempt": current_try,
                    "prompt_length": len(user_prompt),
                    "title": title,
                    "messages": messages,  # Include messages for input display
                }
                if agent_name == "CmdlineExtract":
                    trace_metadata["attention_preprocessor_enabled"] = attention_preprocessor_enabled
                    if snippet_count is not None:
                        trace_metadata["attention_preprocessor_snippet_count"] = snippet_count

                # Trace LLM call with Langfuse (each sub-agent gets its own trace)
                with trace_llm_call(
                    name=f"{agent_name.lower()}_extraction",
                    model=model_name,
                    execution_id=execution_id,
                    metadata=trace_metadata,
                ) as generation:
                    logger.info(
                        f"{agent_name} provider resolution: provider={provider}, "
                        f"effective_provider={effective_provider}, "
                        f"self.provider_extract={self.provider_extract}"
                    )
                    # Use provided top_p or get from agent config
                    effective_top_p = top_p if top_p is not None else self.get_top_p_for_agent(agent_name)
                    logger.info(
                        f"{agent_name} extraction attempt {current_try}: "
                        f"using provider={effective_provider}, model={model_name}, "
                        f"temperature={temperature}, top_p={effective_top_p}"
                    )
                    try:
                        response = await self.request_chat(
                            provider=effective_provider,
                            model_name=model_name,
                            messages=converted_messages,
                            max_tokens=2000,
                            temperature=temperature,
                            top_p=effective_top_p,
                            timeout=extraction_timeout,
                            failure_context=f"{agent_name} extraction attempt {current_try}",
                            seed=self.seed,
                        )
                    except Exception as e:
                        log_llm_error(
                            generation,
                            e,
                            metadata={
                                "agent_name": agent_name,
                                "attempt": current_try,
                                "model": model_name,
                            },
                        )
                        raise

                    # Parse response (moved inside with block so generation is still active)
                    response_text = response["choices"][0]["message"].get("content", "")
                    # Handle Deepseek reasoning
                    if not response_text:
                        response_text = response["choices"][0]["message"].get("reasoning_content", "")

                    # Log the actual response for debugging
                    logger.info(f"{agent_name} raw response length: {len(response_text)} chars")
                    logger.info(f"{agent_name} response (first 1000 chars): {response_text[:1000]}")
                    logger.debug(f"{agent_name} full response: {response_text}")

                    # Log response metadata
                    if "usage" in response:
                        logger.info(f"{agent_name} token usage: {response['usage']}")

                    # Extract JSON with multiple strategies and escape sequence fixing
                    last_result = None
                    json_str = None

                    def fix_json_escapes(text: str) -> str:
                        """Fix common JSON escape sequence issues, especially Windows paths."""
                        # Pre-process: Fix patterns where models over-escape quotes

                        # Fix four backslashes + quote -> escaped quote (\\\\" -> \")
                        # In the raw text, four backslashes means: backslash + backslash + backslash + backslash
                        # We want to convert this to: backslash + quote (escaped quote)
                        text = re.sub(r'\\\\\\\\"', r'\\"', text)
                        # Fix triple backslash + quote -> escaped quote (\\\" -> \")
                        text = re.sub(r'\\\\\\"', r'\\"', text)
                        # Fix \\" patterns that are clearly wrong (two backslashes + quote -> escaped quote)
                        # This handles cases like: /tn \\"Task-... which should be /tn \"Task-...
                        # We match \\" (two backslashes + quote) and replace with \" (escaped quote)
                        # But be careful: we don't want to break Windows paths like C:\\ProgramData
                        # So we only fix \\" that appears in contexts suggesting quoted text
                        # Pattern: \\" followed by alphanumeric (opening quote)
                        # OR preceded by alphanumeric (closing quote)
                        # In regex: \\\\" means match two backslashes + quote
                        text = re.sub(r'\\\\"(?=[A-Za-z0-9])', r'\\"', text)  # Opening quotes: \\"Task -> \"Task
                        # For closing quotes, use a simpler pattern: match \\" that's not part of a path
                        # Look for \\" preceded by alphanumeric/dash/underscore and not followed by backslash
                        text = re.sub(r'([A-Za-z0-9_-])\\\\"(?!\\)', r'\1\\"', text)  # Closing quotes

                        # Strategy: Find all backslashes and check if they're properly escaped
                        # For Windows paths like C:\ProgramData, we need C:\\ProgramData in JSON
                        result = []
                        i = 0
                        while i < len(text):
                            if text[i] == "\\":
                                # Check if this is already part of a valid escape sequence
                                if i + 1 < len(text):
                                    next_char = text[i + 1]
                                    # Valid escape sequences: \\, \", \/, \b, \f, \n, \r, \t, \uXXXX
                                    if next_char == "\\":
                                        # Already escaped backslash - keep both characters and skip the next one
                                        result.append("\\\\")
                                        i += 2
                                        continue
                                    if next_char in ['"', "/", "b", "f", "n", "r", "t"]:
                                        # Valid escape sequence - keep as is
                                        result.append(text[i])
                                        i += 1
                                        continue
                                    if next_char == "u" and i + 5 < len(text):
                                        # Check if it's a valid unicode escape \uXXXX
                                        hex_chars = text[i + 2 : i + 6]
                                        if len(hex_chars) == 4 and all(
                                            c in "0123456789abcdefABCDEF" for c in hex_chars
                                        ):
                                            # Valid unicode escape - keep all 6 characters
                                            result.append(text[i : i + 6])
                                            i += 6
                                            continue
                                        # Invalid - looks like \u but not valid, double the backslash
                                        result.append("\\\\")
                                        i += 1
                                        continue
                                    # Invalid escape - double the backslash
                                    result.append("\\\\")
                                    i += 1
                                    continue
                                # Backslash at end of string - invalid, double it
                                result.append("\\\\")
                                i += 1
                                continue
                            result.append(text[i])
                            i += 1
                        return "".join(result)

                    def try_parse_json(text: str) -> tuple[dict, bool]:
                        """Try to parse JSON, return (result, success)."""
                        try:
                            return json.loads(text), True
                        except json.JSONDecodeError:
                            # Try fixing escape sequences
                            try:
                                fixed = fix_json_escapes(text)
                                return json.loads(fixed), True
                            except (json.JSONDecodeError, ValueError):
                                return None, False

                    try:
                        # Strategy 1: Try to extract from markdown code fences first

                        code_fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response_text, re.DOTALL)
                        if code_fence_match:
                            json_str = code_fence_match.group(1).strip()
                            logger.info(f"{agent_name}: Found JSON in markdown code fence")
                            parsed, success = try_parse_json(json_str)
                            if success:
                                last_result = parsed
                        else:
                            # Strategy 2: Find JSON object (first { to last })
                            start = response_text.find("{")
                            end = response_text.rfind("}")
                            if start != -1 and end != -1 and end > start:
                                json_str = response_text[start : end + 1]
                                parsed, success = try_parse_json(json_str)
                                if success:
                                    last_result = parsed
                                    logger.info(f"{agent_name}: Found JSON object from {start} to {end}")
                            else:
                                # Strategy 3: Try to find any valid JSON structure
                                # Look for all potential JSON objects and try the largest one
                                json_candidates = []
                                search_pos = 0
                                while search_pos <= len(response_text):
                                    open_pos = response_text.find("{", search_pos)
                                    if open_pos == -1:
                                        break

                                    brace_count = 0
                                    json_end = -1
                                    for i in range(open_pos, len(response_text)):
                                        if response_text[i] == "{":
                                            brace_count += 1
                                        elif response_text[i] == "}":
                                            brace_count -= 1
                                            if brace_count == 0:
                                                json_end = i + 1
                                                break

                                    if json_end != -1:
                                        candidate = response_text[open_pos:json_end]
                                        parsed, success = try_parse_json(candidate)
                                        expected_keys = [
                                            "cmdline_items",
                                            "items",
                                            "process_lineage",
                                            "sigma_queries",
                                            "registry_artifacts",
                                            "windows_services",
                                            "scheduled_tasks",
                                            "count",
                                        ]
                                        if success and parsed and any(k in parsed for k in expected_keys):
                                            json_candidates.append((len(candidate), parsed))

                                    search_pos = open_pos + 1

                                if json_candidates:
                                    # Sort by length (largest first) and take the first valid one
                                    json_candidates.sort(key=lambda x: x[0], reverse=True)
                                    last_result = json_candidates[0][1]
                                    logger.info(f"{agent_name}: Found JSON from candidate search")

                        if last_result:
                            logger.info(f"{agent_name} parsed JSON keys: {list(last_result.keys())}")
                            # Check for agent-specific result keys
                            # IMPORTANT: Check for nested cmdline structure BEFORE checking cmdline_items
                            # because the LLM might return {"cmdline": {"items": []}} instead of {"cmdline_items": []}
                            if "cmdline" in last_result and isinstance(last_result["cmdline"], dict):
                                # Handle nested cmdline structure: {"cmdline": {"items": [], "count": 0}}
                                cmdline_data = last_result["cmdline"]
                                if "items" in cmdline_data:
                                    last_result["cmdline_items"] = cmdline_data["items"]
                                    if "count" in cmdline_data:
                                        last_result["count"] = cmdline_data["count"]
                                    # Remove the nested cmdline structure
                                    del last_result["cmdline"]
                                    count = len(last_result.get("cmdline_items", []))
                                    logger.info(
                                        f"{agent_name} normalized nested cmdline structure: found {count} cmdline_items"
                                    )
                                    if count == 0:
                                        logger.warning(
                                            f"{agent_name}: cmdline_items array is empty after normalization!"
                                        )
                            elif "cmdline_items" in last_result:
                                count = len(last_result.get("cmdline_items", []))
                                logger.info(f"{agent_name} found {count} cmdline_items")
                                if count == 0:
                                    logger.warning(f"{agent_name}: cmdline_items array is empty!")
                            elif "process_lineage" in last_result:
                                count = len(last_result.get("process_lineage", []))
                                logger.info(f"{agent_name} found {count} process_lineage items")
                                # Normalize to 'items' for consistency with frontend
                                last_result["items"] = last_result.pop("process_lineage")
                            elif "sigma_queries" in last_result:
                                count = len(last_result.get("sigma_queries", []))
                                logger.info(f"{agent_name} found {count} sigma_queries")
                                last_result["items"] = last_result.pop("sigma_queries")
                            elif "registry_artifacts" in last_result:
                                count = len(last_result.get("registry_artifacts", []))
                                logger.info(f"{agent_name} found {count} registry_artifacts")
                                last_result["items"] = last_result.pop("registry_artifacts")
                            elif "windows_services" in last_result:
                                count = len(last_result.get("windows_services", []))
                                logger.info(f"{agent_name} found {count} windows_services")
                                last_result["items"] = last_result.pop("windows_services")
                            elif "scheduled_tasks" in last_result:
                                count = len(last_result.get("scheduled_tasks", []))
                                logger.info(f"{agent_name} found {count} scheduled_tasks")
                                last_result["items"] = last_result.pop("scheduled_tasks")
                            elif "items" in last_result:
                                count = len(last_result.get("items", []))
                                logger.info(f"{agent_name} found {count} items")
                            else:
                                logger.warning(
                                    f"{agent_name}: No recognized items key found. Keys: {list(last_result.keys())}"
                                )
                        else:
                            # Fallback if no JSON found
                            logger.warning(
                                f"{agent_name}: No JSON found in response. Response length: {len(response_text)}"
                            )
                            logger.warning(f"{agent_name}: Response preview: {response_text[:500]}")
                            last_result = {"items": [], "count": 0, "error": "No JSON found"}

                    except Exception as e:
                        logger.warning(f"{agent_name}: Exception during JSON parsing: {e}")
                        logger.warning(f"{agent_name}: JSON string attempted: {json_str[:200] if json_str else 'None'}")
                        logger.warning(f"{agent_name}: Full response: {response_text[:1000]}")
                        last_result = {"items": [], "count": 0, "error": f"JSON parse exception: {str(e)}"}

                    # Ensure we have a result
                    if not last_result:
                        last_result = {"items": [], "count": 0, "error": "Failed to parse response"}

                    # Normalize and validate traceability on items (observable traceability feature)
                    _CONFIDENCE_LEVEL_MAP = {"high": 0.95, "medium": 0.7, "low": 0.4}

                    def _normalize_traceability_item(
                        item: Any, agent_name: str, _level_map: dict = _CONFIDENCE_LEVEL_MAP
                    ) -> Any:
                        if isinstance(item, str):
                            # Wrap plain strings into objects so confidence can be surfaced
                            return {"value": item, "confidence_score": None}
                        if not isinstance(item, dict):
                            return item
                        out = dict(item)
                        if "value" not in out and ("source_evidence" in out or "extraction_justification" in out):
                            out["value"] = (
                                out.get("command_line") or out.get("cmdline") or out.get("query") or str(item)
                            )
                        conf = out.get("confidence_score")
                        if conf is not None:
                            try:
                                f = float(conf)
                                if not (0.0 <= f <= 1.0):
                                    out["confidence_score"] = None
                            except (TypeError, ValueError):
                                out["confidence_score"] = None
                        # Fallback: map confidence_level (high/medium/low) to confidence_score
                        if out.get("confidence_score") is None and out.get("confidence_level"):
                            mapped = _level_map.get(str(out["confidence_level"]).lower())
                            if mapped is not None:
                                out["confidence_score"] = mapped
                        return out

                    for key in (
                        "cmdline_items",
                        "items",
                        "registry_artifacts",
                        "windows_services",
                        "scheduled_tasks",
                        "queries",
                        "process_lineage",
                    ):
                        if key not in last_result or not isinstance(last_result[key], list):
                            continue
                        last_result[key] = [_normalize_traceability_item(it, agent_name) for it in last_result[key]]

                    # Log completion to Langfuse with parsed result (inside with block so generation is still active)
                    if generation:
                        # Include full result for dataset/eval support - Langfuse needs complete output
                        # Use the full last_result so datasets can access all extracted items
                        output_for_langfuse = {
                            "parsed_items_count": last_result.get("count", len(last_result.get("items", []))),
                            "has_error": "error" in last_result,
                        }
                        # Include all items (not just preview) for dataset/eval support
                        if "items" in last_result:
                            output_for_langfuse["items"] = last_result["items"]
                        if "cmdline_items" in last_result:
                            output_for_langfuse["cmdline_items"] = last_result["cmdline_items"]
                        # Include any other result fields that might be useful
                        for key in [
                            "process_lineage",
                            "sigma_queries",
                            "registry_artifacts",
                            "windows_services",
                            "scheduled_tasks",
                        ]:
                            if key in last_result:
                                output_for_langfuse[key] = last_result[key]
                        # Include error if present
                        if "error" in last_result:
                            output_for_langfuse["error"] = last_result["error"]

                        # Create dataset-compatible input format
                        # Schema only allows article_text (additionalProperties: false)
                        dataset_input = {
                            "article_text": content[:10000]
                            if len(content) > 10000
                            else content,  # Truncate for dataset
                        }

                        log_llm_completion(
                            generation=generation,
                            input_messages=messages,
                            output=json.dumps(output_for_langfuse, indent=2),
                            usage=response.get("usage", {}),
                            metadata={
                                "agent_name": agent_name,
                                "attempt": current_try,
                                "parsed_result_keys": list(last_result.keys()),
                                "item_count": output_for_langfuse["parsed_items_count"],
                            },
                            input_object=dataset_input,  # Use dataset-compatible format
                        )

                    # Store messages and response in result for eval bundle export
                    # These are needed when Langfuse is disabled
                    last_result["_llm_messages"] = messages
                    last_result["_llm_response"] = response_text
                    last_result["_llm_attempt"] = current_try
                    # CmdlineExtract: surface preprocessor info for trace UI / Langfuse
                    if agent_name == "CmdlineExtract":
                        last_result["_attention_preprocessor"] = {
                            "enabled": attention_preprocessor_enabled,
                            "snippet_count": snippet_count if snippet_count is not None else 0,
                        }

                # If no QA config, return immediately
                if not qa_prompt_config:
                    return last_result

                # 2. Run QA -- validate config once on first attempt
                if current_try == 1:
                    _validate_qa_prompt_config(agent_name, qa_prompt_config)

                qa_task = qa_prompt_config.get("objective", "Verify extraction.")
                qa_criteria = qa_prompt_config.get("evaluation_criteria", [])
                qa_criteria_json = json.dumps(qa_criteria, indent=2)
                qa_criteria_text = (
                    "\n".join([f"- {criterion}" for criterion in qa_criteria])
                    if isinstance(qa_criteria, list)
                    else qa_criteria_json
                )

                qa_model_to_use = qa_model_override or model_name

                # Handle different extraction result formats
                if "cmdline_items" in last_result:
                    cmdline_items = last_result.get("cmdline_items", [])
                    if cmdline_items:
                        extracted_commands_text = "\n".join(
                            [
                                f"{i + 1}. {cmd.get('value', cmd) if isinstance(cmd, dict) else cmd}"
                                for i, cmd in enumerate(cmdline_items)
                            ]
                        )
                    else:
                        extracted_commands_text = "No commands extracted."
                elif "items" in last_result:
                    items = last_result.get("items", [])
                    if items:
                        extracted_commands_text = "\n".join([f"{i + 1}. {item}" for i, item in enumerate(items)])
                    else:
                        extracted_commands_text = "No items extracted."
                else:
                    # Fallback: format entire result as JSON
                    extracted_commands_text = json.dumps(last_result, indent=2)

                qa_prompt = f"""Task: {qa_task}

Article Title: {title}
Article URL: {url}

Original Extraction Task: {task}

Original Extraction Instructions:
{instructions}

Original Extraction Output Format:
{output_format}{json_example_str}

Source Text:
{truncated_content}

Extracted Data:
{json.dumps(last_result, indent=2)}

Evaluation Criteria:
{qa_criteria_json}

Instructions: {qa_prompt_config.get("instructions", "Evaluate and return JSON.")}
"""
                logger.debug(f"{agent_name} QA using legacy programmatic format (len={len(qa_prompt)} chars)")

                qa_system = (qa_prompt_config.get("system") or qa_prompt_config.get("role") or "").strip()
                if not qa_system:
                    raise PreprocessInvariantError(
                        f"{agent_name} QA prompt resolved to an empty system message. "
                        "Ensure the QA prompt config contains a non-empty 'system' or 'role' key."
                    )
                qa_user_content = (qa_prompt_config.get("user") or "").strip()
                if qa_user_content:
                    qa_prompt = f"{qa_user_content}\n\n{qa_prompt}"
                qa_messages = [
                    {"role": "system", "content": qa_system},
                    {"role": "user", "content": qa_prompt},
                ]

                # Delegate LLM call, parsing, and normalization to QAEvaluator
                from src.services.qa_evaluator import QAEvaluator

                _qa_eval = await QAEvaluator(self).evaluate(
                    messages=qa_messages,
                    agent_name=agent_name,
                    model_name=qa_model_to_use,
                    provider=self.provider_extract,
                    temperature=temperature,
                    seed=self.seed,
                    max_tokens=1000,
                    timeout=180.0,
                    execution_id=execution_id,
                    attempt=current_try,
                )
                qa_result = _qa_eval
                parsing_failed = _qa_eval.get("parsing_failed", False)
                parse_error = _qa_eval.get("_parse_error")
                qa_text = _qa_eval.get("_qa_text", "")

                # QAEvaluator normalizes verdict; status is kept only for backward-compat storage.
                # The one exception (handled below) is when there are no items to validate at all.
                status = qa_result.get("verdict", "needs_revision")

                # Extract feedback from QA result (try multiple fields, fallback to raw text if parsing failed)
                extracted_feedback = ""
                if not parsing_failed:
                    extracted_feedback = (
                        qa_result.get("feedback")
                        or qa_result.get("qa_corrections_applied")
                        or qa_result.get("summary")
                        or ""
                    )
                else:
                    # QA parsing failed - try to extract feedback from raw text
                    if "feedback" in qa_text.lower() or "issue" in qa_text.lower() or "problem" in qa_text.lower():
                        feedback_patterns = re.findall(
                            r"[^.!?]*(?:missing|incorrect|wrong|should|must|need|issue|problem)[^.!?]*[.!?]",
                            qa_text,
                            re.IGNORECASE,
                        )
                        if feedback_patterns:
                            extracted_feedback = " ".join(feedback_patterns[:3])
                        else:
                            # Fallback: use first 200 chars of QA text as feedback
                            extracted_feedback = qa_text[:200] if qa_text else ""
                    else:
                        extracted_feedback = ""

                # Capture pre-filter count so traces can distinguish "extractor found nothing"
                # from "extractor found things and QA removed them all".
                # Defensive: handle the case where the model emits e.g. {"cmdline_items": null}
                # by treating None as an empty list.
                _spec = _QA_AGENT_SPECS.get(agent_name)
                items_key = (
                    _spec.items_key if _spec else ("cmdline_items" if "cmdline_items" in last_result else "items")
                )
                pre_filter_count = len(last_result.get(items_key) or [])

                # If QA parsing failed and there was nothing to validate, return cleanly --
                # the QA call was effectively a no-op, no need to record a parse-failure verdict.
                if parsing_failed and pre_filter_count == 0:
                    logger.info(
                        f"{agent_name} QA parse failed but extraction returned 0 items; "
                        f"returning without recording verdict (no-op)."
                    )
                    return last_result

                # Apply QA corrections for all extractors that have a spec entry.
                applied_removals: list = []
                if (
                    not parsing_failed
                    and qa_result
                    and _spec is not None
                    and isinstance(qa_result.get("corrections"), dict)
                ):
                    removal_entries = [r for r in qa_result["corrections"].get("removed", []) if isinstance(r, dict)]
                    if removal_entries:
                        before_items = last_result.get(items_key) or []
                        after_items = []
                        actual_removals: list = []
                        for item in before_items:
                            matched = any(_spec.matcher(r, item) for r in removal_entries)
                            if matched:
                                # Find first matching removal to record identity
                                for r in removal_entries:
                                    if _spec.matcher(r, item):
                                        actual_removals.append(_spec.removal_id(r))
                                        break
                            else:
                                after_items.append(item)
                        if actual_removals:
                            last_result[items_key] = after_items
                            last_result["count"] = len(after_items)
                            applied_removals = actual_removals
                            logger.info(
                                f"{agent_name} QA removed {len(before_items) - len(after_items)} items "
                                f"(pre={len(before_items)}, post={len(after_items)}). "
                                f"Removed: {applied_removals}"
                            )

                # Store QA result in the agent result for later retrieval (always store if QA ran)
                if qa_prompt_config:  # QA was enabled, so store result even if parsing failed
                    # verdict is already normalized by QAEvaluator
                    verdict = qa_result.get("verdict", "needs_revision")
                    # Keep status for backward-compat in stored _qa_result bundles
                    qa_status = qa_result.get("status") or verdict

                    # Build display issues list from corrections (read for display only;
                    # actual filtering already happened above via _QA_AGENT_SPECS dispatch).
                    _CORRECTION_IDENT_FIELDS = (
                        "command",
                        "query",
                        "registry_key_path",
                        "registry_value_name",
                        "service_name",
                        "task_name",
                        "task_path",
                        "parent",
                        "child",
                    )

                    def _correction_ident(
                        entry: dict,
                        _fields: tuple = _CORRECTION_IDENT_FIELDS,
                    ) -> str:
                        for f in _fields:
                            v = (entry.get(f) or "").strip()
                            if v:
                                return v
                        return ""

                    issues = []
                    if qa_result and isinstance(qa_result.get("corrections"), dict):
                        corrections_obj = qa_result["corrections"]
                        for removed in corrections_obj.get("removed", []):
                            if not isinstance(removed, dict):
                                continue
                            ident = _correction_ident(removed)
                            reason = removed.get("reason", "")
                            issues.append(
                                {
                                    "type": "compliance",
                                    "description": f"Removed: {ident} - {reason}",
                                    "severity": "medium",
                                }
                            )
                        for added in corrections_obj.get("added", []):
                            if not isinstance(added, dict):
                                continue
                            ident = _correction_ident(added)
                            found = added.get("found_in", "")
                            issues.append(
                                {
                                    "type": "completeness",
                                    "description": f"Added (not applied): {ident} - Found in: {found}",
                                    "severity": "low",
                                }
                            )

                    # Set appropriate summary based on verdict
                    # Override any misleading summary when verdict is "pass"
                    if verdict == "pass":
                        # If no feedback or feedback indicates failure, use positive message
                        if (
                            not extracted_feedback
                            or "failed" in extracted_feedback.lower()
                            or "without feedback" in extracted_feedback.lower()
                        ):
                            extracted_feedback = "QA passed successfully."
                    elif not extracted_feedback:
                        # Only set failure message if no feedback exists
                        extracted_feedback = "QA failed without feedback."

                    # Always store QA result when QA runs, even if parsing failed
                    if parsing_failed:
                        error_description = (
                            f"QA response parsing failed: {parse_error}"
                            if parse_error
                            else "QA response parsing failed"
                        )
                        raw_snippet = qa_text[:500] if qa_text else "No response received"
                        feedback_with_diagnostic = (
                            extracted_feedback
                            or f"QA response could not be parsed. Raw response preview: {raw_snippet}"
                        )
                        last_result["_qa_result"] = {
                            "verdict": "needs_revision",
                            "summary": extracted_feedback or "QA evaluation ran but response parsing failed",
                            "status": "fail",
                            "feedback": feedback_with_diagnostic,
                            "issues": [{"type": "compliance", "description": error_description, "severity": "medium"}],
                            "corrections_applied": {"removed": []},
                            "pre_filter_count": pre_filter_count,
                        }
                    else:
                        last_result["_qa_result"] = {
                            "verdict": verdict,
                            "summary": extracted_feedback,
                            "status": qa_status,
                            "feedback": extracted_feedback,
                            "issues": issues,
                            "corrections_applied": {"removed": applied_removals},
                            "pre_filter_count": pre_filter_count,
                        }

                # After applying corrections (or recording the parse failure),
                # always return -- extraction QA no longer drives a re-extraction loop.
                items = last_result.get("cmdline_items") or last_result.get("items") or []
                logger.info(
                    f"{agent_name} QA complete on attempt {current_try} (status={status}). "
                    f"Returning {len(items)} items."
                )
                return last_result

            except PreprocessInvariantError:
                raise  # Fail-fast: do not retry infra invariants
            except PromptConfigValidationError:
                raise  # Fail-fast: contract violations must surface immediately
            except ContextLengthExceededError:
                raise  # Fail-fast: context overflow is unrecoverable, retrying will not help
            except Exception as e:
                if "context_length_exceeded" in str(e):
                    raise ContextLengthExceededError(str(e)) from e
                logger.error(f"{agent_name} error on attempt {current_try}: {e}", exc_info=True)
                # On last attempt, store all API errors in result (not just connection errors)
                if current_try >= max_extraction_retries:
                    last_result = {
                        "items": [],
                        "count": 0,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "error_details": {
                            "message": str(e),
                            "exception_type": type(e).__name__,
                            "attempt": current_try,
                            "agent_name": agent_name,
                        },
                        "connection_error": "connection" in str(e).lower() or "cannot connect" in str(e).lower(),
                    }
                feedback = f"Previous attempt failed with error: {str(e)}"
                # Continue loop

        logger.warning(f"{agent_name} failed all {max_extraction_retries} attempts. Returning last result.")
        return last_result
