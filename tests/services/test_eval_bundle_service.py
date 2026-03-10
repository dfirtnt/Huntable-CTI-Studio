"""Tests for EvalBundleService."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from src.database.models import AgenticWorkflowExecutionTable, ArticleTable
from src.services.eval_bundle_service import EvalBundleService

pytestmark = pytest.mark.unit


class TestEvalBundleIllegalState:
    """Test illegal state detection: messages==[] AND status==completed."""

    def test_empty_messages_completed_status_sets_infra_failed(self):
        """Bundle with messages=[] and status=completed must have infra_failed=True."""
        db_session = Mock()

        # Mock execution with completed status and empty messages in conversation_log
        execution = Mock()
        execution.id = 1
        execution.article_id = 1
        execution.status = "completed"
        execution.error_log = {
            "extract_agent": {
                "conversation_log": [
                    {
                        "agent": "CmdlineExtract",
                        "messages": [],  # Empty — illegal when completed
                        "result": {"cmdline_items": [], "count": 0},
                    }
                ]
            }
        }
        execution.config_snapshot = {}
        execution.started_at = None
        execution.completed_at = None
        execution.current_step = None
        execution.retry_count = 0
        execution.error_message = None
        execution.extraction_result = {}

        # Mock article
        article = Mock()
        article.content = "Test article content"
        article.id = 1
        article.title = "Test"
        article.canonical_url = None
        article.published_at = None
        article.word_count = 100
        article.discovered_at = None
        article.article_metadata = {}
        article.source = None

        def mock_query(model):
            q = Mock()
            f = Mock()
            if model == AgenticWorkflowExecutionTable:
                f.first.return_value = execution
            elif model == ArticleTable:
                f.first.return_value = article
            else:
                f.first.return_value = None
            q.filter.return_value = f
            return q

        db_session.query = mock_query

        with patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=False):
            service = EvalBundleService(db_session)
            bundle = service.generate_bundle(execution_id=1, agent_name="CmdlineExtract")

        assert "ILLEGAL_STATE_MESSAGES_EMPTY_BUT_COMPLETED" in bundle["integrity"]["warnings"]
        assert bundle.get("infra_failed") is True
        assert bundle["execution_context"]["infra_failed"] is True
        assert bundle["execution_context"]["infra_failed_reason"] == "messages empty but execution marked completed"

    def test_valid_messages_completed_status_does_not_set_infra_failed(self):
        """Bundle with valid messages and status=completed must NOT have infra_failed (negative case)."""
        db_session = Mock()

        execution = Mock()
        execution.id = 1
        execution.article_id = 1
        execution.status = "completed"
        execution.error_log = {
            "extract_agent": {
                "conversation_log": [
                    {
                        "agent": "CmdlineExtract",
                        "messages": [
                            {"role": "system", "content": "You are an extractor."},
                            {"role": "user", "content": "Content:\n" + "x" * 600},
                        ],
                        "result": {"cmdline_items": ["cmd1"], "count": 1},
                    }
                ]
            }
        }
        execution.config_snapshot = {}
        execution.started_at = None
        execution.completed_at = None
        execution.current_step = None
        execution.retry_count = 0
        execution.error_message = None
        execution.extraction_result = {}

        article = Mock()
        article.content = "Test article content"
        article.id = 1
        article.title = "Test"
        article.canonical_url = None
        article.published_at = None
        article.word_count = 100
        article.discovered_at = None
        article.article_metadata = {}
        article.source = None

        def mock_query(model):
            q = Mock()
            f = Mock()
            if model == AgenticWorkflowExecutionTable:
                f.first.return_value = execution
            elif model == ArticleTable:
                f.first.return_value = article
            else:
                f.first.return_value = None
            q.filter.return_value = f
            return q

        db_session.query = mock_query

        with patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=False):
            service = EvalBundleService(db_session)
            bundle = service.generate_bundle(execution_id=1, agent_name="CmdlineExtract")

        assert "ILLEGAL_STATE_MESSAGES_EMPTY_BUT_COMPLETED" not in bundle["integrity"]["warnings"]
        assert bundle.get("infra_failed") is not True
        assert bundle["execution_context"].get("infra_failed") is not True


class TestEvalBundleServiceHelpers:
    """Focused branch/failure-path coverage for helper extraction methods."""

    def test_extract_llm_call_data_missing_agent_log_returns_empty(self):
        service = EvalBundleService(Mock())
        execution = Mock()
        execution.id = 99
        execution.error_log = {"other_agent": {"conversation_log": []}}
        execution.config_snapshot = {}

        with patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=False):
            llm_request, llm_response, warnings, attempt = service._extract_llm_call_data(
                execution=execution,
                agent_name="rank_article",
                attempt=1,
            )

        assert attempt is None
        assert any(w.startswith("AGENT_LOG_MISSING") for w in warnings)
        assert llm_request["messages"] is None
        assert llm_response["text_output"] == ""

    def test_extract_llm_call_data_prefers_langfuse_messages_and_response(self):
        service = EvalBundleService(Mock())
        execution = Mock()
        execution.id = 11
        execution.error_log = {
            "extract_agent": {
                "conversation_log": [
                    {
                        "agent": "CmdlineExtract",
                        "messages": [{"role": "user", "content": "fallback"}],
                        "llm_response": "fallback-response",
                    }
                ]
            }
        }
        execution.config_snapshot = {
            "agent_models": {
                "CmdlineExtract_provider": "openai",
                "CmdlineExtract_model": "gpt-4o-mini",
                "CmdlineExtract_temperature": 0.2,
                "CmdlineExtract_top_p": 0.9,
                "CmdlineExtract_max_tokens": 500,
            }
        }

        langfuse_payload = {
            "messages": [{"role": "user", "content": "langfuse-message"}],
            "response": "langfuse-response",
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        }

        with (
            patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=True),
            patch.object(service, "_fetch_langfuse_generation", return_value=langfuse_payload),
        ):
            llm_request, llm_response, warnings, attempt = service._extract_llm_call_data(
                execution=execution,
                agent_name="CmdlineExtract",
                attempt=None,
            )

        assert attempt == 1
        assert llm_request["provider"] == "openai"
        assert llm_request["model"] == "gpt-4o-mini"
        assert llm_request["messages"] == langfuse_payload["messages"]
        assert llm_request["reconstructed"] is False
        assert llm_response["text_output"] == "langfuse-response"
        assert llm_response["usage"]["total_tokens"] == 14
        assert "MESSAGES_FETCHED_FROM_LANGFUSE" in warnings
        assert "RESPONSE_FETCHED_FROM_LANGFUSE" in warnings

    def test_fetch_langfuse_generation_falls_back_to_manual_filtering(self):
        service = EvalBundleService(Mock())

        matching_generation = Mock()
        matching_generation.session_id = "workflow_exec_123"
        matching_generation.trace_id = "trace-xyz"
        matching_generation.name = "cmdlineextract_extraction"
        matching_generation.metadata = '{"agent_name":"CmdlineExtract"}'
        matching_generation.model_parameters = '{"messages":[{"role":"user","content":"payload"}]}'
        matching_generation.output = {"content": "structured-output"}
        usage_obj = Mock()
        usage_obj.prompt_tokens = 8
        usage_obj.completion_tokens = 2
        usage_obj.total_tokens = 10
        matching_generation.usage_details = usage_obj

        class Response:
            def __init__(self, data):
                self.data = data

        generations_api = Mock()
        generations_api.list.side_effect = [
            RuntimeError("session_id query failed"),
            RuntimeError("trace_id query failed"),
            Response([matching_generation]),
        ]
        client = Mock()
        client.api.generations = generations_api

        execution = Mock()
        execution.error_log = {"langfuse_trace_id": "trace-xyz"}

        with (
            patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=True),
            patch("src.services.eval_bundle_service.get_langfuse_client", return_value=client),
        ):
            result = service._fetch_langfuse_generation(
                execution_id=123,
                agent_name="CmdlineExtract",
                attempt=1,
                execution=execution,
            )

        assert result is not None
        assert result["messages"][0]["content"] == "payload"
        assert result["response"] == "structured-output"
        assert result["usage"]["total_tokens"] == 10
        assert generations_api.list.call_count == 3

    def test_extract_system_prompt_and_config_snapshot_string_payloads(self):
        service = EvalBundleService(Mock())
        execution = Mock()
        execution.config_snapshot = """
        {
          "config_version": "v-test",
          "min_hunt_score": 75,
          "cmdline_attention_preprocessor_enabled": true,
          "agent_models": {
            "CmdlineExtract_provider": "openai",
            "CmdlineExtract_model": "gpt-4o-mini",
            "CmdlineExtract_temperature": 0.1
          },
          "agent_prompts": {
            "SigmaAgent": {"prompt": "Generate sigma safely."}
          }
        }
        """

        warnings: list[str] = []
        system_prompt = service._extract_system_prompt(execution, "generate_sigma", warnings)
        filtered = service._extract_config_snapshot(execution, "CmdlineExtract", warnings)

        assert system_prompt["text"] == "Generate sigma safely."
        assert system_prompt["length_chars"] > 0
        assert filtered["config_version"] == "v-test"
        assert filtered["min_hunt_score"] == 75
        assert filtered["agent_models"]["CmdlineExtract"]["provider"] == "openai"
        assert filtered["agent_models"]["CmdlineExtract"]["model"] == "gpt-4o-mini"

    def test_extract_context_and_metadata_helpers(self):
        service = EvalBundleService(Mock())
        warnings: list[str] = []

        execution = Mock()
        execution.extraction_result = {
            "subresults": {
                "cmdline": {
                    "items": ["cmd.exe /c whoami"],
                    "count": 1,
                    "raw": {"qa_corrections_applied": [{"field": "items", "fix": "normalized"}]},
                }
            }
        }
        extraction_context = service._extract_extraction_context(
            execution=execution,
            agent_name="CmdlineExtract",
            subagent_name="cmdline",
            warnings=warnings,
        )
        assert extraction_context["parsed_result"]["count"] == 1
        assert extraction_context["qa_corrections_applied"] is True

        qa = service._extract_qa_results(
            error_log={
                "qa_results": {
                    "CmdLineQA": {
                        "verdict": "pass",
                        "summary": "All good",
                        "issues": [],
                        "feedback": "none",
                    }
                }
            },
            agent_name="CmdlineExtract",
            warnings=warnings,
        )
        assert qa["verdict"] == "pass"
        assert qa["has_issues"] is False

        execution.status = "completed"
        execution.current_step = "done"
        execution.retry_count = 0
        execution.error_message = None
        execution.started_at = datetime(2026, 1, 1, 12, 0, 0)
        execution.completed_at = execution.started_at + timedelta(seconds=15)
        exec_context = service._extract_execution_context(execution, warnings)
        assert exec_context["duration_seconds"] == 15.0

        article = Mock()
        article.id = 7
        article.title = "Title"
        article.canonical_url = "https://example.com/a"
        article.published_at = datetime(2026, 1, 2, 0, 0, 0)
        article.word_count = 321
        article.discovered_at = datetime(2026, 1, 2, 1, 0, 0)
        article.article_metadata = {"threat_hunting_score": 88.0, "ml_hunt_score": 0.91}
        article.source = Mock()
        article.source.name = "Source A"
        article.source.id = 3

        metadata = service._extract_article_metadata(article, warnings)
        assert metadata["threat_hunting_score"] == 88.0
        assert metadata["ml_hunt_score"] == 0.91
        assert metadata["source_name"] == "Source A"

    def test_empty_messages_failed_status_does_not_set_infra_failed(self):
        """Bundle with messages=[] but status!=completed must NOT set infra_failed."""
        db_session = Mock()

        execution = Mock()
        execution.id = 1
        execution.article_id = 1
        execution.status = "failed"
        execution.error_log = {
            "extract_agent": {
                "conversation_log": [
                    {
                        "agent": "CmdlineExtract",
                        "messages": [],
                        "result": {"error": "Something failed"},
                    }
                ]
            }
        }
        execution.config_snapshot = {}
        execution.started_at = None
        execution.completed_at = None
        execution.current_step = None
        execution.retry_count = 0
        execution.error_message = "Failed"
        execution.extraction_result = {}

        article = Mock()
        article.content = "Test article content"
        article.id = 1
        article.title = "Test"
        article.canonical_url = None
        article.published_at = None
        article.word_count = 100
        article.discovered_at = None
        article.article_metadata = {}
        article.source = None

        def mock_query(model):
            q = Mock()
            f = Mock()
            if model == AgenticWorkflowExecutionTable:
                f.first.return_value = execution
            elif model == ArticleTable:
                f.first.return_value = article
            else:
                f.first.return_value = None
            q.filter.return_value = f
            return q

        db_session.query = mock_query

        with patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=False):
            service = EvalBundleService(db_session)
            bundle = service.generate_bundle(execution_id=1, agent_name="CmdlineExtract")

        assert "ILLEGAL_STATE_MESSAGES_EMPTY_BUT_COMPLETED" not in bundle["integrity"]["warnings"]
        assert bundle.get("infra_failed") is not True
        assert bundle["execution_context"].get("infra_failed") is not True
