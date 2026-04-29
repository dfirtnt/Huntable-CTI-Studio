"""Tests for the Concurrency Throttle feature on /run-subagent-eval.

Covers:
- The new pydantic field on SubagentEvalRunRequest (default, bounds).
- The _THROTTLE_PATTERNS regex used to derive `throttled` on eval results
  (must match known OpenAI / Anthropic / generic throttle wordings, and
  must NOT match historically-seen non-throttle failure strings).

A DB audit at feature-build time confirmed zero historical rows in
agentic_workflow_executions matched the throttle patterns; the negative
cases here are drawn from that same audit so a too-eager regex change
would be caught.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.web.routes.evaluation_api import (
    _EVAL_STAGGER_SECONDS,
    _THROTTLE_PATTERNS,
    SubagentEvalRunRequest,
    _execution_is_throttled,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# SubagentEvalRunRequest.concurrency_throttle_seconds
# ---------------------------------------------------------------------------


def test_concurrency_throttle_default_is_five_seconds():
    req = SubagentEvalRunRequest(subagent_name="cmdline", article_urls=["u"])
    assert req.concurrency_throttle_seconds == 5.0


def test_concurrency_throttle_accepts_zero_lower_bound():
    req = SubagentEvalRunRequest(subagent_name="cmdline", article_urls=["u"], concurrency_throttle_seconds=0.0)
    assert req.concurrency_throttle_seconds == 0.0


def test_concurrency_throttle_accepts_sixty_upper_bound():
    req = SubagentEvalRunRequest(subagent_name="cmdline", article_urls=["u"], concurrency_throttle_seconds=60.0)
    assert req.concurrency_throttle_seconds == 60.0


def test_concurrency_throttle_rejects_negative():
    with pytest.raises(ValidationError):
        SubagentEvalRunRequest(subagent_name="cmdline", article_urls=["u"], concurrency_throttle_seconds=-0.1)


def test_concurrency_throttle_rejects_above_max():
    with pytest.raises(ValidationError):
        SubagentEvalRunRequest(subagent_name="cmdline", article_urls=["u"], concurrency_throttle_seconds=60.1)


def test_concurrency_throttle_accepts_fractional_value():
    # 0.5s step is valid on the input; ensure the model preserves sub-second
    # throttles for users who want to barely-stagger large batches.
    req = SubagentEvalRunRequest(subagent_name="cmdline", article_urls=["u"], concurrency_throttle_seconds=2.5)
    assert req.concurrency_throttle_seconds == 2.5


# ---------------------------------------------------------------------------
# _THROTTLE_PATTERNS regex
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error_text",
    [
        # OpenAI 429 with retry hint (shape seen in eval bundle v2102/v2122).
        "Error code: 429 - Rate limit reached. Please try again in 7.6s.",
        "HTTP 429 Too Many Requests",
        # Anthropic wordings.
        "anthropic.RateLimitError: rate_limit_error - per-minute input tokens exceeded",
        "APIStatusError: 529 overloaded_error",
        "overloaded",
        # Generic fallbacks.
        "Received rate limit response from provider",
        "rate_limit",  # underscore form
        "Rate Limit",  # mixed case
    ],
)
def test_throttle_patterns_match_known_throttle_errors(error_text):
    assert _THROTTLE_PATTERNS.search(error_text) is not None, f"Expected throttle-pattern match for: {error_text!r}"


@pytest.mark.parametrize(
    "error_text",
    [
        # All of these are real historical failure strings pulled from the
        # agentic_workflow_executions table during feature audit. None of
        # them are throttle-related; a regex regression that matches these
        # would light up the TPM badge on benign SIGMA/config/LMStudio bugs.
        "'observables_section'",
        "No valid SIGMA rules could be generated after all phases",
        "'NoneType' object has no attribute 'get'",
        "'int' object has no attribute 'lower'",
        "tuple index out of range",
        "Anthropic API key is not configured for agentic workflows.",
        "Model 'qwen/qwen3-8b' is not a valid OpenAI chat completion model.",
        "LMStudio model 'qwen/qwen3-8b' has context length of 8192 tokens, which is below the required threshold of 16384 tokens.",
        "Can't reconnect until invalid transaction is rolled back.",
        "(psycopg2.DatabaseError) error with status PGRES_TUPLES_OK and no message from the libpq",
        "This result object does not return rows. It has been closed automatically.",
        "Context size has been exceeded.",
    ],
)
def test_throttle_patterns_do_not_match_historical_non_throttle_errors(error_text):
    assert _THROTTLE_PATTERNS.search(error_text) is None, (
        f"False-positive throttle match on historical failure: {error_text!r}"
    )


# ---------------------------------------------------------------------------
# Interaction: internal DB-race floor is preserved alongside user throttle
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _execution_is_throttled: both-surface detection
# ---------------------------------------------------------------------------


def test_execution_is_throttled_from_error_message():
    assert _execution_is_throttled("OpenAI API error (429): Rate limit reached", None) is True


def test_execution_is_throttled_from_error_log_conversation_entry():
    """Real historical shape: workflow completed (error_message=None) but a
    sub-agent's LLM call raised 429 during the run. DB audit at build time
    found 40 executions matching this pattern — none of which lit up the
    badge before this fix.
    """
    error_log = {
        "extract_agent": {
            "completed": True,
            "conversation_log": [
                {"agent": "ProcTreeExtract", "result": {"status": "skipped_for_eval"}},
                {
                    "agent": "CmdlineExtract",
                    "result": {
                        "count": 0,
                        "error_type": "RuntimeError",
                        "error": (
                            'OpenAI API error (429): {"error": {"message": '
                            '"Rate limit reached for gpt-4o in organization '
                            "org-abc on tokens per min (TPM): Limit 450000, "
                            'Used 449500."}}'
                        ),
                    },
                },
            ],
        }
    }
    assert _execution_is_throttled(None, error_log) is True


def test_execution_is_throttled_error_details_field():
    # error_details is a separate field that may carry the 429 body on some
    # code paths; include it in the scan to avoid a false-negative drift.
    error_log = {
        "extract_agent": {
            "conversation_log": [
                {
                    "agent": "CmdlineExtract",
                    "result": {
                        "count": 0,
                        "error_details": "HTTP 429 Too Many Requests",
                    },
                }
            ]
        }
    }
    assert _execution_is_throttled(None, error_log) is True


def test_execution_not_throttled_when_error_log_has_other_errors():
    error_log = {
        "extract_agent": {
            "conversation_log": [
                {
                    "agent": "CmdlineExtract",
                    "result": {
                        "count": 0,
                        "error_type": "AttributeError",
                        "error": "'NoneType' object has no attribute 'get'",
                    },
                }
            ]
        }
    }
    assert _execution_is_throttled(None, error_log) is False


def test_execution_not_throttled_when_everything_clean():
    assert _execution_is_throttled(None, None) is False
    assert _execution_is_throttled("", {}) is False
    assert _execution_is_throttled(None, {"extract_agent": {"conversation_log": []}}) is False


def test_execution_is_throttled_ignores_malformed_error_log():
    # Defensive: error_log column is JSONB and may contain non-dict values
    # on legacy rows. Function must not raise on malformed input.
    assert _execution_is_throttled(None, "not a dict") is False
    assert _execution_is_throttled(None, ["not a dict"]) is False
    assert _execution_is_throttled(None, {"extract_agent": "broken"}) is False
    assert _execution_is_throttled(None, {"extract_agent": {"conversation_log": "broken"}}) is False
    assert _execution_is_throttled(None, {"extract_agent": {"conversation_log": [None, "string-entry"]}}) is False


def test_internal_stagger_floor_is_positive():
    # The frontend assumes _EVAL_STAGGER_SECONDS is the DB-race floor that
    # always applies, independent of the user's Concurrency Throttle. If it
    # ever drops to zero, the status-text "dispatch window" math and the
    # comment in agent_evals.html would need to change.
    assert _EVAL_STAGGER_SECONDS > 0
