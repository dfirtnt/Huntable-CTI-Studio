"""Regression tests for CodeQL py/stack-trace-exposure findings.

These tests guard against future regressions where exception messages flow
into HTTP response bodies. The canary pattern: each test plants a uniquely
recognizable string inside an exception (something an attacker could not
craft on their own — e.g. an internal hostname, a fake DB column, a fake
API key prefix), triggers the code path, then asserts the canary string
does NOT appear anywhere in the response detail or message returned to
the client.

If a future change reintroduces `f"...{str(e)}"` or
`detail=str(e)` style code, these tests will fail because the canary
string will leak through.

Background: see PR #80 and commits 34276d89 / e8e9578c which removed
22 ineffective `# codeql[py/stack-trace-exposure]` comments and
refactored the genuine str(e) leaks the comments were hiding.

Test design notes:
- We call route handlers / helper functions directly with mocked
  dependencies. This is faster and more focused than spinning up the
  full HTTP stack for each case.
- Each canary string is structured so that "no part of it appears in
  the response" is a strong assertion — a snippet test (e.g. just
  asserting "10.0.0.5" is missing) lets a partial leak through.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import yaml
from fastapi import HTTPException

pytestmark = [pytest.mark.api, pytest.mark.security]


# ---------------------------------------------------------------------------
# Canary strings — structured so partial leaks are detectable
# ---------------------------------------------------------------------------

# Each canary is a recognizable phrase we plant in a mocked exception. None
# of these should ever surface in an HTTP response body.
CANARY_INTERNAL_HOST = "internal-canary-host-198.51.100.42"
CANARY_DB_DETAIL = "canary-db-column-secret_internal_field"
CANARY_API_KEY_PREFIX = "sk-canary-leaked-12345abcdef"
CANARY_REDIS_PASSWORD = "canary-redis-pass-deadbeef"
CANARY_FILE_PATH = "/opt/canary/internal/secrets.json"
CANARY_YAML_DETAIL = "canary-yaml-internal-mapping-detail"
CANARY_EXEC_DETAIL = "canary-execution-internal-detail-99"


def _assert_no_canary(haystack: object, *canaries: str) -> None:
    """Recursively assert no canary substring appears anywhere in *haystack*.

    Works on dicts, lists, strings, and arbitrary nested structures by
    flattening to JSON. We compare lowercased to catch case-shifted leaks.
    """
    blob = json.dumps(haystack, default=str).lower()
    for canary in canaries:
        assert canary.lower() not in blob, f"Canary string {canary!r} leaked into response: {haystack!r}"


# ---------------------------------------------------------------------------
# scrape.py — httpx.RequestError 400 detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_single_url_http_request_error_does_not_leak_exception_detail():
    """An httpx.RequestError must NOT have str(exc) flow into the 400 detail."""
    from src.web.routes.scrape import _scrape_single_url

    # Build an httpx.RequestError carrying a canary string
    err = httpx.RequestError(f"connection broken: {CANARY_INTERNAL_HOST}")

    # Mock the async client so .get() raises our canary error
    client = MagicMock()
    client.get = AsyncMock(side_effect=err)
    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(return_value=client)
    async_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("src.web.routes.scrape.httpx.AsyncClient", MagicMock(return_value=async_cm)),
        patch("src.web.routes.scrape.validate_url_for_scraping", return_value="https://example.test/x"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await _scrape_single_url(
            url="https://example.test/x",
            title=None,
            force_scrape=False,
            pre_scraped_content=None,
        )

    assert exc_info.value.status_code == 400
    _assert_no_canary(exc_info.value.detail, CANARY_INTERNAL_HOST)


# ---------------------------------------------------------------------------
# workflow_executions.py — eval bundle 404 ValueError detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_eval_bundle_value_error_does_not_leak_exception_detail():
    """A ValueError raised by EvalBundleService must NOT leak into the 404 detail."""
    from src.web.routes.workflow_executions import export_eval_bundle

    class _ExportRequest:
        agent_name = "fake_agent"
        attempt = 1
        inline_large_text = False
        max_inline_chars = 1000

    fake_request = MagicMock()  # FastAPI Request — not actually inspected here
    bundle_service = MagicMock()
    bundle_service.generate_bundle.side_effect = ValueError(
        f"Execution 99 not found in {CANARY_DB_DETAIL}",
    )

    db_manager = MagicMock()
    session = MagicMock()
    db_manager.get_session.return_value = session

    with (
        patch("src.web.routes.workflow_executions.get_db_manager", return_value=db_manager),
        patch("src.web.routes.workflow_executions.EvalBundleService", return_value=bundle_service),
        pytest.raises(HTTPException) as exc_info,
    ):
        await export_eval_bundle(fake_request, execution_id=99, export_request=_ExportRequest())

    assert exc_info.value.status_code == 404
    _assert_no_canary(exc_info.value.detail, CANARY_DB_DETAIL)


# ---------------------------------------------------------------------------
# sigma_ab_test.py — invalid YAML 400 detail
# ---------------------------------------------------------------------------


def test_parse_and_validate_rule_yaml_error_does_not_leak_exception_detail():
    """yaml.YAMLError raised during AB-test rule parse must NOT leak into the 400 detail."""
    from src.web.routes.sigma_ab_test import _parse_and_validate_rule

    bad_yaml = "any non-empty content"

    with (
        patch(
            "src.web.routes.sigma_ab_test.yaml.safe_load",
            side_effect=yaml.YAMLError(f"mapping issue at {CANARY_YAML_DETAIL}"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        _parse_and_validate_rule(bad_yaml, field="rule_a")

    assert exc_info.value.status_code == 400
    _assert_no_canary(exc_info.value.detail, CANARY_YAML_DETAIL)


# ---------------------------------------------------------------------------
# ai.py — LMStudio /models error message must not include str(e) or response.text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lmstudio_chat_models_does_not_leak_httperror_or_response_text():
    """LMStudio chat models endpoint message must not contain str(e) from httpx
    errors nor full upstream response.text."""
    from src.web.routes import ai as ai_module

    # First simulate every URL raising httpx.HTTPError carrying a canary
    err = httpx.HTTPError(f"DNS lookup failed for {CANARY_INTERNAL_HOST}")
    client = MagicMock()
    client.get = AsyncMock(side_effect=err)
    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(return_value=client)
    async_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(ai_module, "httpx", create=False) as httpx_mock,
        patch.object(
            ai_module,
            "_lmstudio_url_candidates",
            return_value=["http://localhost:1234/v1"],
        ),
    ):
        # Reattach AsyncClient and exception classes from real httpx
        httpx_mock.AsyncClient = MagicMock(return_value=async_cm)
        httpx_mock.HTTPError = httpx.HTTPError
        httpx_mock.TimeoutException = httpx.TimeoutException
        httpx_mock.ConnectError = httpx.ConnectError

        result = await ai_module.api_get_lmstudio_models()

    assert result["success"] is False
    _assert_no_canary(result, CANARY_INTERNAL_HOST)


@pytest.mark.asyncio
async def test_lmstudio_chat_models_non_200_does_not_leak_response_text():
    """When LMStudio returns non-200, response.text must NOT leak into the message."""
    from src.web.routes import ai as ai_module

    bad_response = MagicMock()
    bad_response.status_code = 500
    bad_response.text = f"upstream error: {CANARY_API_KEY_PREFIX}"

    client = MagicMock()
    client.get = AsyncMock(return_value=bad_response)
    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(return_value=client)
    async_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(ai_module, "httpx", create=False) as httpx_mock,
        patch.object(
            ai_module,
            "_lmstudio_url_candidates",
            return_value=["http://localhost:1234/v1"],
        ),
    ):
        httpx_mock.AsyncClient = MagicMock(return_value=async_cm)
        httpx_mock.HTTPError = httpx.HTTPError
        httpx_mock.TimeoutException = httpx.TimeoutException
        httpx_mock.ConnectError = httpx.ConnectError

        result = await ai_module.api_get_lmstudio_models()

    assert result["success"] is False
    _assert_no_canary(result, CANARY_API_KEY_PREFIX)


@pytest.mark.asyncio
async def test_lmstudio_embedding_models_does_not_leak_httperror():
    """Mirror of chat-models test for the embedding models endpoint."""
    from src.web.routes import ai as ai_module

    err = httpx.HTTPError(f"connect failed: {CANARY_INTERNAL_HOST}")
    client = MagicMock()
    client.get = AsyncMock(side_effect=err)
    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(return_value=client)
    async_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(ai_module, "httpx", create=False) as httpx_mock,
        patch.object(
            ai_module,
            "_lmstudio_url_candidates",
            return_value=["http://localhost:1234/v1"],
        ),
    ):
        httpx_mock.AsyncClient = MagicMock(return_value=async_cm)
        httpx_mock.HTTPError = httpx.HTTPError
        httpx_mock.TimeoutException = httpx.TimeoutException
        httpx_mock.ConnectError = httpx.ConnectError

        result = await ai_module.api_get_lmstudio_embedding_models()

    assert result["success"] is False
    _assert_no_canary(result, CANARY_INTERNAL_HOST)


# ---------------------------------------------------------------------------
# health.py — service health Redis check must not leak str(redis_exc)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_services_health_redis_failure_does_not_leak_exception_detail():
    """When Redis health check fails, the response 'error' field must be a
    static string, not str(redis_exc)."""
    from src.web.routes import health as health_module

    fake_redis_module = MagicMock()
    # Make the redis client constructor raise a canary-bearing exception
    fake_redis_module.from_url.side_effect = Exception(
        f"AUTH failed: invalid password {CANARY_REDIS_PASSWORD} on host {CANARY_INTERNAL_HOST}",
    )

    # WORKFLOW_LMSTUDIO_ENABLED off so we don't need to mock the LMStudio path.
    # Langfuse check is gated by is_langfuse_enabled() which we mock to False.
    with (
        patch.dict("sys.modules", {"redis": fake_redis_module}),
        patch.dict("os.environ", {"WORKFLOW_LMSTUDIO_ENABLED": "false"}, clear=False),
        patch("src.utils.langfuse_client.is_langfuse_enabled", return_value=False),
    ):
        result = await health_module.api_services_health()

    assert result["services"]["redis"]["status"] == "unhealthy"
    _assert_no_canary(result, CANARY_REDIS_PASSWORD, CANARY_INTERNAL_HOST)
