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

    def test_extract_llm_call_data_can_skip_langfuse_lookup(self):
        service = EvalBundleService(Mock())
        execution = Mock()
        execution.id = 12
        execution.error_log = {
            "extract_agent": {
                "conversation_log": [
                    {
                        "agent": "CmdlineExtract",
                        "messages": [{"role": "user", "content": "stored-message"}],
                        "llm_response": "stored-response",
                    }
                ]
            }
        }
        execution.config_snapshot = {
            "agent_models": {
                "CmdlineExtract_provider": "openai",
                "CmdlineExtract_model": "gpt-4o-mini",
            }
        }

        with (
            patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=True),
            patch.object(service, "_fetch_langfuse_generation") as fetch_langfuse_generation,
        ):
            llm_request, llm_response, warnings, attempt = service._extract_llm_call_data(
                execution=execution,
                agent_name="CmdlineExtract",
                attempt=None,
                fetch_langfuse=False,
            )

        fetch_langfuse_generation.assert_not_called()
        assert attempt == 1
        assert llm_request["messages"] == [{"role": "user", "content": "stored-message"}]
        assert llm_response["text_output"] == "stored-response"
        assert "MESSAGES_FETCHED_FROM_LANGFUSE" not in warnings
        assert "RESPONSE_FETCHED_FROM_LANGFUSE" not in warnings

    def test_fetch_langfuse_generation_uses_v4_observations_api(self):
        """_fetch_langfuse_generation queries observations.get_many via LangfuseAPI (v4), not client.api.generations (v3)."""
        service = EvalBundleService(Mock())

        matching_gen = Mock()
        matching_gen.name = "cmdlineextract_extraction"
        matching_gen.metadata = '{"agent_name":"CmdlineExtract"}'
        matching_gen.model_parameters = '{"messages":[{"role":"user","content":"payload"}]}'
        matching_gen.output = {"content": "structured-output"}
        usage_obj = Mock()
        usage_obj.prompt_tokens = 8
        usage_obj.completion_tokens = 2
        usage_obj.total_tokens = 10
        matching_gen.usage_details = usage_obj

        class ObsResponse:
            def __init__(self, data):
                self.data = data

        mock_api = Mock()
        mock_api.observations.get_many.return_value = ObsResponse([matching_gen])
        # trace_id is known via error_log, so trace.list should not be called
        mock_api.trace.list = Mock()

        execution = Mock()
        execution.error_log = {"langfuse_trace_id": "trace-xyz"}

        with (
            patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=True),
            patch("src.services.eval_bundle_service.get_langfuse_client", return_value=Mock()),
            patch("src.utils.langfuse_client._get_langfuse_api", return_value=mock_api),
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
        mock_api.observations.get_many.assert_called_once_with(trace_id="trace-xyz", type="GENERATION", limit=100)
        # The removed v3 attribute must never be reached
        mock_api.trace.list.assert_not_called()

    def test_fetch_langfuse_generation_resolves_trace_via_session_when_no_trace_id(self):
        """When trace_id is absent from error_log, falls back to trace.list(session_id=...) then observations."""
        service = EvalBundleService(Mock())

        matching_gen = Mock()
        matching_gen.name = "cmdlineextract_extraction"
        matching_gen.metadata = {}
        matching_gen.model_parameters = '{"messages":[{"role":"user","content":"session-path"}]}'
        matching_gen.output = "session-output"
        matching_gen.usage_details = None

        class ObsResponse:
            def __init__(self, data):
                self.data = data

        class TraceResponse:
            def __init__(self, trace_id):
                self.data = [Mock(id=trace_id)]

        mock_api = Mock()
        mock_api.trace.list.return_value = TraceResponse("resolved-trace-id")
        mock_api.observations.get_many.return_value = ObsResponse([matching_gen])

        execution = Mock()
        execution.error_log = {}  # no langfuse_trace_id

        with (
            patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=True),
            patch("src.services.eval_bundle_service.get_langfuse_client", return_value=Mock()),
            patch("src.utils.langfuse_client._get_langfuse_api", return_value=mock_api),
        ):
            result = service._fetch_langfuse_generation(
                execution_id=456,
                agent_name="CmdlineExtract",
                attempt=1,
                execution=execution,
            )

        assert result is not None
        mock_api.trace.list.assert_called_once_with(session_id="workflow_exec_456", limit=1, order_by="timestamp.desc")
        mock_api.observations.get_many.assert_called_once_with(
            trace_id="resolved-trace-id", type="GENERATION", limit=100
        )

    def test_fetch_langfuse_generation_returns_none_when_api_unavailable(self):
        """Returns None gracefully when _get_langfuse_api() cannot build a client."""
        service = EvalBundleService(Mock())
        execution = Mock()
        execution.error_log = {"langfuse_trace_id": "trace-xyz"}

        with (
            patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=True),
            patch("src.services.eval_bundle_service.get_langfuse_client", return_value=Mock()),
            patch("src.utils.langfuse_client._get_langfuse_api", return_value=None),
        ):
            result = service._fetch_langfuse_generation(
                execution_id=789,
                agent_name="CmdlineExtract",
                attempt=1,
                execution=execution,
            )

        assert result is None

    def test_fetch_langfuse_generation_null_name_does_not_crash(self):
        """Generations with name=None must not raise AttributeError on .lower()."""
        service = EvalBundleService(Mock())

        null_name_gen = Mock()
        null_name_gen.name = None  # explicit None, not missing attribute
        null_name_gen.metadata = {}

        matching_gen = Mock()
        matching_gen.name = "cmdlineextract_extraction"
        matching_gen.metadata = {}
        matching_gen.model_parameters = '{"messages":[{"role":"user","content":"ok"}]}'
        matching_gen.output = "result"
        matching_gen.usage_details = None

        class ObsResponse:
            def __init__(self, data):
                self.data = data

        mock_api = Mock()
        mock_api.observations.get_many.return_value = ObsResponse([null_name_gen, matching_gen])

        execution = Mock()
        execution.error_log = {"langfuse_trace_id": "trace-null"}

        with (
            patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=True),
            patch("src.services.eval_bundle_service.get_langfuse_client", return_value=Mock()),
            patch("src.utils.langfuse_client._get_langfuse_api", return_value=mock_api),
        ):
            result = service._fetch_langfuse_generation(
                execution_id=999,
                agent_name="CmdlineExtract",
                attempt=1,
                execution=execution,
            )

        assert result is not None
        assert result["messages"][0]["content"] == "ok"

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
                    "RankAgentQA": {
                        "verdict": "pass",
                        "summary": "All good",
                        "issues": [],
                        "feedback": "none",
                    }
                }
            },
            agent_name="rank_article",
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


class TestSlimTransform:
    """Tests for the slim bundle transform that strips redundant data."""

    def test_slim_strips_raw_payload_and_raw_response(self):
        """Slim transform removes raw_payload and raw_response."""
        service = EvalBundleService(Mock())
        bundle = {
            "llm_request": {
                "messages": [{"role": "user", "content": "short"}],
                "raw_payload": {"messages": [{"role": "user", "content": "short"}], "model": "test"},
                "payload_sha256": "abc123",
                "parameters": {"temperature": 0.0},
            },
            "llm_response": {
                "text_output": "response text",
                "raw_response": {"choices": [{"message": {"content": "response text"}}]},
                "response_sha256": "def456",
                "finish_reason": "stop",
            },
            "inputs": [],
            "integrity": {"warnings": []},
        }
        result = service._apply_slim_transform(bundle)
        assert "raw_payload" not in result["llm_request"]
        assert "payload_sha256" not in result["llm_request"]
        assert "raw_response" not in result["llm_response"]
        assert "response_sha256" not in result["llm_response"]
        # Structured fields preserved
        assert result["llm_request"]["messages"] == [{"role": "user", "content": "short"}]
        assert result["llm_response"]["text_output"] == "response text"

    def test_slim_strips_extraction_raw_result(self):
        """Slim transform removes extraction_context.raw_result."""
        service = EvalBundleService(Mock())
        bundle = {
            "llm_request": {"messages": []},
            "llm_response": {},
            "extraction_context": {
                "parsed_result": {"items": ["cmd.exe"], "count": 1},
                "raw_result": {"_llm_response": "very long raw text..."},
            },
            "inputs": [],
            "integrity": {"warnings": []},
        }
        result = service._apply_slim_transform(bundle)
        assert "raw_result" not in result["extraction_context"]
        assert result["extraction_context"]["parsed_result"]["count"] == 1

    def test_slim_deduplicates_long_messages(self):
        """Slim replaces long system/user message content with SHA refs."""
        service = EvalBundleService(Mock())
        long_prompt = "You are a security analyst. " * 100  # >500 chars
        long_article = "The threat actor deployed malware. " * 100
        bundle = {
            "llm_request": {
                "messages": [
                    {"role": "system", "content": long_prompt},
                    {"role": "user", "content": long_article},
                ],
            },
            "llm_response": {},
            "inputs": [
                {"name": "article_text", "sha256": "aaaa1111bbbb2222", "text": long_article},
                {"name": "system_prompt", "sha256": "cccc3333dddd4444", "text": long_prompt},
            ],
            "integrity": {"warnings": []},
        }
        result = service._apply_slim_transform(bundle)
        msgs = result["llm_request"]["messages"]
        assert msgs[0]["_slim_stripped"] is True
        assert "cccc3333dddd" in msgs[0]["content"]
        assert msgs[1]["_slim_stripped"] is True
        assert "aaaa1111bbbb" in msgs[1]["content"]

    def test_slim_preserves_short_messages(self):
        """Slim does NOT strip short messages (< 500 chars)."""
        service = EvalBundleService(Mock())
        bundle = {
            "llm_request": {
                "messages": [
                    {"role": "system", "content": "Brief prompt"},
                    {"role": "user", "content": "Short article"},
                ],
            },
            "llm_response": {},
            "inputs": [
                {"name": "article_text", "sha256": "abc", "text": "Short article"},
                {"name": "system_prompt", "sha256": "def", "text": "Brief prompt"},
            ],
            "integrity": {"warnings": []},
        }
        result = service._apply_slim_transform(bundle)
        msgs = result["llm_request"]["messages"]
        assert msgs[0]["content"] == "Brief prompt"
        assert msgs[1]["content"] == "Short article"
        assert "_slim_stripped" not in msgs[0]
        assert "_slim_stripped" not in msgs[1]

    def test_slim_sets_flag_and_warning(self):
        """Slim transform sets slim_applied=True and adds warning."""
        service = EvalBundleService(Mock())
        bundle = {
            "llm_request": {"messages": []},
            "llm_response": {},
            "inputs": [],
            "integrity": {"warnings": []},
        }
        result = service._apply_slim_transform(bundle)
        assert result["slim_applied"] is True
        assert "SLIM_TRANSFORM_APPLIED" in result["integrity"]["warnings"]

    def test_slim_generate_bundle_integration(self):
        """Full generate_bundle with slim=True produces a slim bundle."""
        db_session = Mock()

        execution = Mock()
        execution.id = 1
        execution.article_id = 1
        execution.status = "completed"
        long_prompt = "Extract command lines from the article. " * 50
        execution.error_log = {
            "extract_agent": {
                "conversation_log": [
                    {
                        "agent": "CmdlineExtract",
                        "messages": [
                            {"role": "system", "content": long_prompt},
                            {"role": "user", "content": "A" * 1000},
                        ],
                        "llm_response": "extracted items",
                    }
                ]
            }
        }
        execution.config_snapshot = {
            "agent_prompts": {
                "ExtractAgent": {"prompt": long_prompt},
                "CmdlineExtract": {"prompt": long_prompt},
            },
            "agent_models": {"ExtractAgent": {"provider": "openai", "model": "gpt-4o"}},
        }
        execution.started_at = datetime(2026, 1, 1)
        execution.completed_at = datetime(2026, 1, 1, 0, 1)
        execution.current_step = "extract_agent"
        execution.retry_count = 0
        execution.error_message = None
        execution.extraction_result = {
            "subresults": {
                "cmdline": {
                    "items": ["cmd.exe /c whoami"],
                    "count": 1,
                    "raw": {"_llm_response": "very long raw output" * 100},
                }
            }
        }

        article = Mock()
        article.content = "A" * 1000
        article.id = 1
        article.title = "Test"
        article.canonical_url = None
        article.published_at = None
        article.word_count = 200
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
            bundle = service.generate_bundle(execution_id=1, agent_name="CmdlineExtract", slim=True)

        assert bundle["slim_applied"] is True
        assert "SLIM_TRANSFORM_APPLIED" in bundle["integrity"]["warnings"]
        # raw_payload and raw_response stripped
        assert "raw_payload" not in bundle["llm_request"]
        assert "raw_response" not in bundle["llm_response"]
        # extraction raw_result stripped
        assert "raw_result" not in bundle.get("extraction_context", {})
        # System message replaced with ref
        system_msg = bundle["llm_request"]["messages"][0]
        assert system_msg.get("_slim_stripped") is True
        # Integrity hash still present (computed before slim)
        assert bundle["integrity"]["bundle_sha256"]


class TestBundleActualItemsTruthiness:
    """actual_items=[] (zero extraction) must appear in bundle, unlike None (field absent)."""

    def _make_scoring_row(self, actual_items):
        """Return a mock SubagentEvaluationTable row with the given actual_items."""
        row = Mock()
        row.expected_count = 3
        row.actual_count = 0
        row.score = 0.0
        row.status = "scored"
        row.expected_items = ["cmd-a", "cmd-b", "cmd-c"]
        row.actual_items = actual_items
        row.matched_count = 0
        row.missed_count = 3
        row.extra_count = 0
        return row

    def _make_execution(self):
        execution = Mock()
        execution.id = 1
        execution.article_id = 1
        execution.status = "completed"
        execution.error_log = {
            "extract_agent": {
                "conversation_log": [
                    {
                        "agent": "CmdlineExtract",
                        "messages": [{"role": "user", "content": "test"}],
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
        return execution

    def _build_query_fn(self, execution, article, scoring_row):
        from src.database.models import AgenticWorkflowExecutionTable, ArticleTable

        def mock_query(model):
            if model is AgenticWorkflowExecutionTable:
                q = Mock()
                q.filter.return_value.first.return_value = execution
                return q
            if model is ArticleTable:
                q = Mock()
                q.filter.return_value.first.return_value = article
                return q
            q = Mock()
            q.filter.return_value.first.return_value = scoring_row
            return q

        return mock_query

    def _make_article(self):
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
        return article

    def test_empty_actual_items_included_in_bundle(self):
        """actual_items=[] must be present -- zero extraction is semantically meaningful."""
        execution = self._make_execution()
        scoring_row = self._make_scoring_row(actual_items=[])
        article = self._make_article()
        db_session = Mock()
        db_session.query = self._build_query_fn(execution, article, scoring_row)

        with patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=False):
            service = EvalBundleService(db_session)
            bundle = service.generate_bundle(execution_id=1, agent_name="CmdlineExtract")

        workflow_meta = bundle.get("workflow", {})
        assert "actual_items" in workflow_meta, (
            "actual_items=[] must be serialised into the bundle so consumers "
            "can distinguish 'model returned nothing' from 'field not set'"
        )
        assert workflow_meta["actual_items"] == []

    def test_none_actual_items_absent_from_bundle(self):
        """actual_items=None (field never set) must be omitted from the bundle."""
        execution = self._make_execution()
        scoring_row = self._make_scoring_row(actual_items=None)
        scoring_row.matched_count = None
        scoring_row.missed_count = None
        scoring_row.extra_count = None
        article = self._make_article()
        db_session = Mock()
        db_session.query = self._build_query_fn(execution, article, scoring_row)

        with patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=False):
            service = EvalBundleService(db_session)
            bundle = service.generate_bundle(execution_id=1, agent_name="CmdlineExtract")

        workflow_meta = bundle.get("workflow", {})
        assert "actual_items" not in workflow_meta
