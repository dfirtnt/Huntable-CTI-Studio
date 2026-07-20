"""Prompt validation helpers for LLMService."""

import hashlib
import json
import logging
from typing import Any

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


class PromptConfigValidationError(ValueError):
    """Raised when prompt config violates hard-fail contract requirements."""


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


def _parse_rank_prompt(prompt_template: str) -> tuple[str, str | None]:
    """Resolve RankAgent's user-message template and optional system override.

    The DB stores RankAgent prompts in several historical shapes:
      * Locked scaffold JSON: {"role": ..., "user_template": ...}
      * Legacy simple JSON:   {"system": ..., "user": ...}
      * Generic JSON:         {"prompt": ..., ...}
      * Raw text:             template string with {title}/{content} placeholders

    Returns (user_template_str, system_override_or_None).  Raises
    PreprocessInvariantError if the input parses as JSON but yields no
    usable system override -- a misconfigured prompt that would otherwise
    silently fall back to empty.

    KNOWN LIMITATION (shape-5 / auto-persist): if prompt_template is a plain
    persona string with no {title}/{content} placeholders (the auto-persist
    UI path produces this), it is returned as-is and the caller's .format()
    becomes a no-op, dropping the article from the user message.  The fix is
    to stop generating shape-5 at the UI write side; this helper preserves
    backwards compatibility until that lands.
    """
    user_template_str = prompt_template
    system_override: str | None = None
    is_json_prompt = False
    try:
        parsed_prompt = json.loads(prompt_template)
        if isinstance(parsed_prompt, dict):
            is_json_prompt = True
            user_template = (
                parsed_prompt.get("user") or parsed_prompt.get("user_template") or parsed_prompt.get("prompt") or ""
            )
            system_override = parsed_prompt.get("system") or parsed_prompt.get("role") or None
            if user_template:
                user_template_str = user_template
            elif system_override:
                user_template_str = system_override
    except json.JSONDecodeError:
        pass

    if is_json_prompt and not system_override:
        raise PreprocessInvariantError(
            "RankAgent prompt resolved to an empty system message. "
            "Ensure the prompt config contains a non-empty 'system' or 'role' key."
        )

    return user_template_str, system_override


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
