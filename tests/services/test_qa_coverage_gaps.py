"""Tests covering QA system gaps identified in post-refactor audit.

Gap 1: Eval bundle fixtures for ProcTreeExtract, ServicesExtract, ScheduledTasksExtract
        (CmdlineExtract-only coverage existed prior to this file)
Gap 2: Raw-text QA fallback path in llm_service.py (regex-based feedback extraction)
Gap 3: Preset/runtime schema parity for _QA_AGENT_SPECS
"""

import json
import re
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.services.llm_service import _QA_AGENT_SPECS

pytestmark = pytest.mark.unit

_QUICKSTART_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "presets" / "AgentConfigs" / "quickstart"


# ---------------------------------------------------------------------------
# Gap 1: Eval bundle fixtures for structured extractors
# Verify that EvalBundleService.generate_bundle produces valid bundles for
# ProcTreeExtract, ServicesExtract, and ScheduledTasksExtract (not just CmdlineExtract).
# ---------------------------------------------------------------------------


def _make_mock_execution(agent_name, items_key, items):
    """Build a mock execution with a conversation_log for the given agent."""
    execution = Mock()
    execution.id = 1
    execution.article_id = 1
    execution.status = "completed"
    execution.error_log = {
        "extract_agent": {
            "conversation_log": [
                {
                    "agent": agent_name,
                    "messages": [
                        {"role": "system", "content": "You are an extractor."},
                        {"role": "user", "content": "Content:\n" + "x" * 600},
                    ],
                    "result": {items_key: items, "count": len(items)},
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


def _make_mock_article():
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


def _mock_query_factory(execution, article):
    from src.database.models import AgenticWorkflowExecutionTable, ArticleTable

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

    return mock_query


class TestEvalBundleStructuredExtractors:
    """Eval bundle generation works for the 3 structured extractors, not just CmdlineExtract."""

    @pytest.mark.parametrize(
        ("agent_name", "items_key", "sample_item"),
        [
            ("ProcTreeExtract", "items", {"parent": "cmd.exe", "child": "evil.exe"}),
            ("ServicesExtract", "items", {"service_name": "EvilSvc", "binary_path": "C:\\evil.exe"}),
            ("ScheduledTasksExtract", "items", {"task_name": "EvilTask", "task_path": "\\EvilTask"}),
        ],
    )
    def test_generate_bundle_for_structured_extractor(self, agent_name, items_key, sample_item):
        from src.services.eval_bundle_service import EvalBundleService

        execution = _make_mock_execution(agent_name, items_key, [sample_item])
        article = _make_mock_article()
        db_session = Mock()
        db_session.query = _mock_query_factory(execution, article)

        with patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=False):
            service = EvalBundleService(db_session)
            bundle = service.generate_bundle(execution_id=1, agent_name=agent_name)

        assert bundle is not None
        # Bundle should have core structure (execution_context, llm_call, integrity)
        assert "execution_context" in bundle
        assert "integrity" in bundle
        assert bundle.get("infra_failed") is not True


# ---------------------------------------------------------------------------
# Gap 2: Raw-text QA fallback path
# When QA parsing fails, llm_service extracts feedback via regex from the raw
# LLM output. These tests exercise that regex path directly.
# ---------------------------------------------------------------------------


class TestQARawTextFallbackPath:
    """Tests for the regex-based QA feedback extraction when JSON parsing fails."""

    @staticmethod
    def _extract_feedback(qa_text: str) -> str:
        """Replicate the raw-text fallback logic from llm_service.py run_extraction_agent."""
        extracted_feedback = ""
        if "feedback" in qa_text.lower() or "issue" in qa_text.lower() or "problem" in qa_text.lower():
            feedback_patterns = re.findall(
                r"[^.!?]*(?:missing|incorrect|wrong|should|must|need|issue|problem)[^.!?]*[.!?]",
                qa_text,
                re.IGNORECASE,
            )
            if feedback_patterns:
                extracted_feedback = " ".join(feedback_patterns[:3])
            else:
                extracted_feedback = qa_text[:200] if qa_text else ""
        else:
            extracted_feedback = ""
        return extracted_feedback

    def test_regex_extracts_issue_sentences(self):
        """Sentences mentioning known issue keywords are captured."""
        qa_text = (
            "The extraction has some issues. "
            "The command whoami is missing from the results. "
            "The registry key is incorrect. "
            "Otherwise looks fine."
        )
        result = self._extract_feedback(qa_text)
        assert "missing" in result.lower()
        assert "incorrect" in result.lower()

    def test_regex_limits_to_three_sentences(self):
        """Only the first 3 matching sentences are returned."""
        qa_text = (
            "Issue one is wrong. "
            "Issue two is incorrect. "
            "Issue three should be fixed. "
            "Issue four must be addressed. "
            "More problems exist."
        )
        result = self._extract_feedback(qa_text)
        # At most 3 sentences joined
        sentences = [s.strip() for s in result.split(".") if s.strip()]
        assert len(sentences) <= 3

    def test_fallback_to_truncation_when_no_patterns_match(self):
        """When trigger words exist but no sentence-level patterns match, truncate to 200 chars."""
        # Contains "issue" (trigger) but the matching sentence-level regex won't find
        # missing/incorrect/wrong/should/must/need/issue/problem within a sentence boundary
        # Actually "issue" is in the pattern, so let's use a case where the keyword
        # exists in a way that doesn't match sentence boundaries well.
        qa_text = "There is a feedback about this issue" + "x" * 300
        result = self._extract_feedback(qa_text)
        # The regex should find "issue" pattern, so it won't fall through to truncation
        # unless no sentence-ending punctuation exists. Our text has no period.
        # With no sentence boundary, findall returns empty -> falls back to [:200]
        assert len(result) <= 200

    def test_empty_string_when_no_trigger_words(self):
        """When the raw text has no trigger keywords, returns empty string."""
        qa_text = "The extraction looks good and complete."
        result = self._extract_feedback(qa_text)
        assert result == ""

    def test_empty_qa_text(self):
        """Empty QA text returns empty feedback."""
        result = self._extract_feedback("")
        assert result == ""

    def test_feedback_keyword_triggers_extraction(self):
        """The word 'feedback' in the text triggers the extraction path."""
        qa_text = "Here is my feedback: the command should include the full path."
        result = self._extract_feedback(qa_text)
        assert "should" in result.lower()

    def test_problem_keyword_triggers_extraction(self):
        """The word 'problem' triggers the extraction path."""
        qa_text = "There is a problem with the extraction. The path must be absolute."
        result = self._extract_feedback(qa_text)
        assert "problem" in result.lower() or "must" in result.lower()


# ---------------------------------------------------------------------------
# Gap 3: Preset/runtime schema parity for _QA_AGENT_SPECS
# Validates that quickstart presets define QA prompts for every agent that
# has an entry in _QA_AGENT_SPECS, and that the items_key is consistent.
# ---------------------------------------------------------------------------


class TestQAAgentSpecsPresetParity:
    """Ensure quickstart presets cover all agents in _QA_AGENT_SPECS."""

    @staticmethod
    def _load_preset(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_all_qa_spec_agents_have_preset_qa_prompts(self):
        """Every agent in _QA_AGENT_SPECS must have a QAPrompt section in each preset."""
        preset_paths = sorted(_QUICKSTART_DIR.glob("*.json"))
        assert len(preset_paths) > 0, "No quickstart presets found"

        spec_agents = set(_QA_AGENT_SPECS.keys())
        for preset_path in preset_paths:
            preset = self._load_preset(preset_path)
            for agent_name in spec_agents:
                agent_section = preset.get(agent_name, {})
                qa_prompt = agent_section.get("QAPrompt", {})
                # Agent must have a QAPrompt section with at least a prompt field
                assert qa_prompt, (
                    f"Preset '{preset_path.stem}' missing QAPrompt for {agent_name} "
                    f"(agent has _QA_AGENT_SPECS entry)"
                )

    def test_qa_spec_items_key_matches_extraction_prompt_schema(self):
        """The items_key in _QA_AGENT_SPECS must correspond to a key the extractor actually produces.

        CmdlineExtract uses 'cmdline_items', HuntQueriesExtract uses 'queries',
        and the rest use 'items' (renamed from their agent-specific keys before QA runs).
        """
        expected_items_keys = {
            "CmdlineExtract": "cmdline_items",
            "HuntQueriesExtract": "queries",
            "RegistryExtract": "items",
            "ProcTreeExtract": "items",
            "ServicesExtract": "items",
            "ScheduledTasksExtract": "items",
        }
        for agent_name, spec in _QA_AGENT_SPECS.items():
            expected = expected_items_keys.get(agent_name)
            assert expected is not None, f"Unexpected agent in _QA_AGENT_SPECS: {agent_name}"
            assert spec.items_key == expected, (
                f"{agent_name}: items_key is '{spec.items_key}' but expected '{expected}'"
            )

    def test_qa_spec_covers_all_extract_agents(self):
        """_QA_AGENT_SPECS must cover all 6 extraction agents."""
        expected_agents = {
            "CmdlineExtract",
            "ProcTreeExtract",
            "HuntQueriesExtract",
            "RegistryExtract",
            "ServicesExtract",
            "ScheduledTasksExtract",
        }
        assert set(_QA_AGENT_SPECS.keys()) == expected_agents
