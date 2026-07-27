"""Regression tests for direct route-level LLM callers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.web.routes.ai import _call_openai_article_analysis
from src.web.routes.scrape import api_vision_extract

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_article_analysis_route_records_openai_completion():
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "choices": [{"message": {"content": "analysis"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=client)
    client_cm.__aexit__ = AsyncMock(return_value=False)
    trace_cm = MagicMock()
    trace_cm.__enter__.return_value = MagicMock()
    trace_cm.__exit__.return_value = False

    with (
        patch("src.web.routes.ai.httpx.AsyncClient", return_value=client_cm),
        patch("src.web.routes.ai.trace_llm_call", return_value=trace_cm) as trace_call,
        patch("src.web.routes.ai.log_llm_completion") as log_completion,
    ):
        result = await _call_openai_article_analysis(
            article_id=12,
            model="gpt-4o",
            prompt="rank this article",
            api_key="test-key",
            max_tokens=2000,
            temperature=0.3,
        )

    assert result == "analysis"
    assert trace_call.call_args.kwargs["article_id"] == 12
    assert trace_call.call_args.kwargs["metadata"]["messages"]
    assert log_completion.call_args.kwargs["usage"]["total_tokens"] == 7


@pytest.mark.asyncio
async def test_vision_route_records_redacted_input_and_output():
    trace_cm = MagicMock()
    trace_cm.__enter__.return_value = MagicMock()
    trace_cm.__exit__.return_value = False

    with (
        patch("asyncio.to_thread", new=AsyncMock(return_value="test-key")),
        patch("src.web.routes.scrape._call_openai_vision", new=AsyncMock(return_value={"text": "visible text"})),
        patch("src.web.routes.scrape.trace_llm_call", return_value=trace_cm) as trace_call,
        patch("src.web.routes.scrape.log_llm_completion") as log_completion,
    ):
        result = await api_vision_extract(
            {"provider": "openai", "imageDataUrl": "data:image/png;base64,AAAA"}
        )

    assert result == {"text": "visible text"}
    trace_metadata = trace_call.call_args.kwargs["metadata"]
    assert trace_metadata["image_data_redacted"] is True
    assert "AAAA" not in str(trace_metadata["messages"])
    assert log_completion.call_args.kwargs["output"] == "visible text"
