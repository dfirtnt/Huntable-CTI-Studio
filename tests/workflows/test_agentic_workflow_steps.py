"""Step-level tests for agentic workflow nodes.

Tests each workflow step (junk filter, rank bypass, OS detection,
similarity search, queue promotion) in isolation by intercepting the
StateGraph.add_node calls to capture the raw closures before compilation.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
)
from src.workflows.agentic_workflow import create_agentic_workflow

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def article():
    art = Mock(spec=ArticleTable)
    art.id = 1
    art.title = "APT29 Uses PowerShell Dropper"
    art.content = (
        "The threat actor executed powershell.exe -enc base64payload to download "
        "and execute a secondary stage. The C2 channel uses HTTPS over port 443. "
        "Registry run key HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run "
        "was modified for persistence. Process tree: cmd.exe -> powershell.exe -> "
        "rundll32.exe. " + "x" * 600
    )
    art.canonical_url = "https://example.com/apt29"
    art.article_metadata = {"threat_hunting_score": 85, "ml_hunt_score": 80}
    source_mock = Mock()
    source_mock.name = "Test Blog"
    art.source = source_mock
    return art


@pytest.fixture
def execution():
    ex = Mock(spec=AgenticWorkflowExecutionTable)
    ex.id = 100
    ex.article_id = 1
    ex.status = "pending"
    ex.current_step = None
    ex.error_log = None
    ex.error_message = None
    ex.config_snapshot = {}
    ex.extraction_result = None
    ex.ranking_score = None
    ex.ranking_reasoning = None
    ex.sigma_rules = None
    ex.similarity_results = None
    ex.started_at = None
    ex.junk_filter_result = None
    return ex


@pytest.fixture
def config_obj():
    cfg = Mock(spec=AgenticWorkflowConfigTable)
    cfg.id = 1
    cfg.version = 1
    cfg.agent_models = {
        "RankAgent": "gpt-4",
        "RankAgent_provider": "openai",
        "ExtractAgent": "gpt-4",
        "ExtractAgent_provider": "openai",
        "SigmaAgent": "gpt-4",
        "SigmaAgent_provider": "openai",
    }
    cfg.agent_prompts = {
        "RankAgent": {
            "prompt": json.dumps(
                {
                    "role": "You are a detection engineer.",
                    "user_template": "Title: {title}\nSource: {source}\nURL: {url}\nContent:\n{content}",
                }
            ),
        },
        "SigmaAgent": {
            "prompt": "Generate SIGMA rules for: {title}\n{content}",
        },
    }
    cfg.sigma_fallback_enabled = True
    return cfg


def _make_db_session(article, execution):
    """Build a mock DB session that routes queries to the right model."""
    session = Mock()
    session.commit = Mock()
    session.refresh = Mock()
    session.add = Mock()

    def query_side_effect(model):
        q = Mock()
        if model == ArticleTable:
            q.filter.return_value.first.return_value = article
        elif model == AgenticWorkflowExecutionTable:
            chain = q.filter.return_value
            chain.first.return_value = execution
            chain.order_by.return_value.first.return_value = execution
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.order_by.return_value.first.return_value = None
        return q

    session.query.side_effect = query_side_effect
    return session


def _default_state(**overrides):
    """Build a default WorkflowState dict, applying overrides."""
    base = {
        "article_id": 1,
        "execution_id": 100,
        "article": None,
        "config": {},
        "filtered_content": None,
        "junk_filter_result": None,
        "ranking_score": None,
        "ranking_reasoning": None,
        "should_continue": True,
        "os_detection_result": None,
        "detected_os": None,
        "extraction_result": None,
        "discrete_huntables_count": None,
        "sigma_rules": None,
        "similarity_results": None,
        "max_similarity": None,
        "queued_rules": None,
        "error": None,
        "current_step": "init",
        "status": "running",
        "termination_reason": None,
        "termination_details": None,
    }
    base.update(overrides)
    return base


def _capture_nodes(db_session, **extra_patches):
    """Call create_agentic_workflow with StateGraph.add_node patched to capture raw callables.

    Returns a dict of {node_name: callable}.
    """
    captured: dict = {}

    with (
        patch("src.workflows.agentic_workflow.ContentFilter") as mock_cf,
        patch("src.workflows.agentic_workflow.WorkflowTriggerService") as mock_ts,
        patch("src.workflows.agentic_workflow.StateGraph") as mock_sg,
    ):
        # Set default content filter result
        filter_result = Mock()
        filter_result.filtered_content = "filtered content here"
        filter_result.removed_chunks = []
        filter_result.is_huntable = True
        filter_result.confidence = 0.9
        mock_cf.return_value.filter_content.return_value = filter_result

        # Apply any additional patches (e.g. trigger service config)
        for target, mock_obj in extra_patches.items():
            if target == "trigger_service_config":
                mock_ts.return_value.get_active_config.return_value = mock_obj

        # Fake StateGraph that records add_node calls
        fake_graph = Mock()

        def add_node(name, fn):
            captured[name] = fn

        fake_graph.add_node = add_node
        fake_graph.add_edge = Mock()
        fake_graph.add_conditional_edges = Mock()
        fake_graph.set_entry_point = Mock()
        fake_graph.compile = Mock(return_value=Mock())
        mock_sg.return_value = fake_graph

        create_agentic_workflow(db_session)

    return captured


# ---------------------------------------------------------------------------
# Junk Filter Node
# ---------------------------------------------------------------------------


class TestJunkFilterNode:
    """Tests for the junk_filter_node step."""

    def test_junk_filter_returns_filtered_content(self, article, execution, config_obj):
        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session)
        state = _default_state(config={"junk_filter_threshold": 0.8})

        result = nodes["junk_filter"](state)
        assert result["filtered_content"] is not None
        assert result["current_step"] == "junk_filter"
        assert result["status"] == "running"

    def test_junk_filter_marks_failed_on_empty_content(self, article, execution, config_obj):
        """Junk filter sets status=failed when article has no content."""
        article.content = ""
        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session)

        state = _default_state()
        result = nodes["junk_filter"](state)
        assert result["status"] == "failed"
        assert result["error"] is not None

    def test_junk_filter_terminates_when_no_huntable_content(self, article, execution, config_obj):
        """When all chunks fail the filter, status=completed with junk termination reason."""
        db_session = _make_db_session(article, execution)

        with (
            patch("src.workflows.agentic_workflow.ContentFilter") as mock_cf,
            patch("src.workflows.agentic_workflow.WorkflowTriggerService"),
            patch("src.workflows.agentic_workflow.StateGraph") as mock_sg,
        ):
            filter_result = Mock()
            filter_result.filtered_content = ""
            filter_result.removed_chunks = [{"text": "junk", "confidence": 0.1}]
            filter_result.is_huntable = False
            filter_result.confidence = 0.1
            mock_cf.return_value.filter_content.return_value = filter_result

            fake_graph = Mock()
            captured: dict = {}
            fake_graph.add_node = lambda name, fn: captured.update({name: fn})
            fake_graph.add_edge = Mock()
            fake_graph.add_conditional_edges = Mock()
            fake_graph.set_entry_point = Mock()
            fake_graph.compile = Mock(return_value=Mock())
            mock_sg.return_value = fake_graph

            create_agentic_workflow(db_session)

        state = _default_state(config={"junk_filter_threshold": 0.8})
        result = captured["junk_filter"](state)

        assert result["status"] == "completed"
        assert result["termination_reason"] == "no_huntable_content"
        assert result["filtered_content"] == ""
        assert result["termination_details"]["confidence"] == 0.1
        assert result["termination_details"]["threshold"] == 0.8

    def test_junk_filter_article_not_found_fails(self, article, execution, config_obj):
        """Missing article -> failure."""
        db_session = _make_db_session(article, execution)

        def no_article(model):
            q = Mock()
            if model == ArticleTable:
                q.filter.return_value.first.return_value = None
            elif model == AgenticWorkflowExecutionTable:
                chain = q.filter.return_value
                chain.first.return_value = execution
            else:
                q.filter.return_value.first.return_value = None
            return q

        db_session.query.side_effect = no_article
        nodes = _capture_nodes(db_session)
        state = _default_state()
        result = nodes["junk_filter"](state)
        assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# Rank Agent Bypass Node
# ---------------------------------------------------------------------------


class TestRankAgentBypassNode:
    """Tests for the rank_agent_bypass_node step."""

    def test_bypass_sets_should_continue_true(self, article, execution, config_obj):
        execution.config_snapshot = {"skip_rank_agent": True}
        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session)

        state = _default_state(
            filtered_content="some content",
            current_step="junk_filter",
        )
        result = nodes["rank_agent_bypass"](state)
        assert result["should_continue"] is True
        assert result["ranking_score"] is None
        assert "bypass" in result["current_step"]

    def test_bypass_records_reason(self, article, execution, config_obj):
        execution.config_snapshot = {"skip_rank_agent": True}
        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session)

        state = _default_state(filtered_content="some content")
        result = nodes["rank_agent_bypass"](state)
        assert result["ranking_reasoning"] is not None


# ---------------------------------------------------------------------------
# Rank Article Node
# ---------------------------------------------------------------------------

_MOCK_RANK_RESULT = {
    "score": 7.0,
    "reasoning": "High huntability",
    "raw_response": "raw",
}


class TestRankArticleNode:
    """Tests for the rank_article_node step -- conversation log correctness."""

    @pytest.mark.asyncio
    async def test_conversation_log_records_configured_agent_prompt(self, article, execution, config_obj):
        """When RankAgent has a DB-configured system prompt, conversation_log records it.

        Regression: previously the log always wrote a hard-coded string, so a custom
        prompt configured in the UI was never reflected in the conversation log.
        """
        config_obj.agent_prompts = {
            "RankAgent": {"system": "Custom detection engineer persona for testing"},
        }
        execution.error_log = None

        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session, trigger_service_config=config_obj)

        with patch("src.workflows.agentic_workflow.LLMService") as mock_llm_cls:
            mock_llm_cls.compute_rank_ground_truth.return_value = {"ground_truth_rank": None}
            mock_instance = Mock()
            mock_instance.rank_article = AsyncMock(return_value=_MOCK_RANK_RESULT)
            mock_llm_cls.return_value = mock_instance

            await nodes["rank_article"](
                _default_state(filtered_content="threat intel content", current_step="junk_filter")
            )

        assert execution.error_log is not None
        conv_log = execution.error_log["rank_article"]["conversation_log"]
        assert len(conv_log) >= 1
        system_content = conv_log[0]["messages"][0]["content"]
        assert system_content == "Custom detection engineer persona for testing"

    @pytest.mark.asyncio
    async def test_conversation_log_uses_canonical_fallback_when_no_rank_agent_config(
        self, article, execution, config_obj
    ):
        """When no RankAgent config exists, conversation_log records the canonical fallback string.

        The fallback must match llm_service.py's system_message default so the QA agent
        evaluates against what the LLM actually received.
        """
        config_obj.agent_prompts = {}
        execution.error_log = None

        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session, trigger_service_config=config_obj)

        with patch("src.workflows.agentic_workflow.LLMService") as mock_llm_cls:
            mock_llm_cls.compute_rank_ground_truth.return_value = {"ground_truth_rank": None}
            mock_instance = Mock()
            mock_instance.rank_article = AsyncMock(return_value=_MOCK_RANK_RESULT)
            mock_llm_cls.return_value = mock_instance

            await nodes["rank_article"](
                _default_state(filtered_content="threat intel content", current_step="junk_filter")
            )

        assert execution.error_log is not None
        conv_log = execution.error_log["rank_article"]["conversation_log"]
        assert len(conv_log) >= 1
        system_content = conv_log[0]["messages"][0]["content"]
        assert "cybersecurity detection engineer" in system_content
        assert "1-10" in system_content
        assert "SIGMA huntability" in system_content
        assert "score and brief reasoning" in system_content


# ---------------------------------------------------------------------------
# Similarity Search Node
# ---------------------------------------------------------------------------


class TestSimilaritySearchNode:
    """Tests for the similarity_search_node step."""

    @pytest.mark.asyncio
    async def test_similarity_skips_when_no_sigma_rules(self, article, execution, config_obj):
        """No sigma rules -> similarity_results=None, max_similarity=0."""
        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session, trigger_service_config=config_obj)

        state = _default_state(
            sigma_rules=[],
            config={"similarity_threshold": 0.5},
        )
        result = await nodes["similarity_search"](state)
        assert result["similarity_results"] is None
        assert result["max_similarity"] == 0.0

    @pytest.mark.asyncio
    async def test_similarity_skips_when_error_present(self, article, execution, config_obj):
        """Existing error -> skip similarity search."""
        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session, trigger_service_config=config_obj)

        state = _default_state(
            sigma_rules=[{"title": "test rule"}],
            error="SIGMA validation failed",
            status="failed",
        )
        result = await nodes["similarity_search"](state)
        assert result["similarity_results"] is None
        assert result["max_similarity"] == 1.0

    @pytest.mark.asyncio
    async def test_similarity_runs_matching_service(self, article, execution, config_obj):
        """With sigma rules, runs SigmaMatchingService and returns results."""
        db_session = _make_db_session(article, execution)

        with patch("src.workflows.agentic_workflow.SigmaMatchingService") as mock_sms:
            mock_sms.return_value.compare_proposed_rule_to_embeddings.return_value = {
                "matches": [
                    {"similarity": 0.3, "novelty_score": 0.7, "novelty_label": "NOVEL"},
                ],
            }
            nodes = _capture_nodes(db_session, trigger_service_config=config_obj)

            state = _default_state(
                sigma_rules=[{"title": "Detect PowerShell Encoded Command"}],
                config={"similarity_threshold": 0.5},
            )
            result = await nodes["similarity_search"](state)

        assert result["similarity_results"] is not None
        assert len(result["similarity_results"]) == 1


# ---------------------------------------------------------------------------
# Queue Promotion Node
# ---------------------------------------------------------------------------


class TestQueuePromotionNode:
    """Tests for the promote_to_queue_node step."""

    def test_promotion_skips_when_no_rules(self, article, execution, config_obj):
        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session, trigger_service_config=config_obj)

        state = _default_state(
            sigma_rules=[],
            similarity_results=[],
            max_similarity=0.0,
            config={"similarity_threshold": 0.5},
        )
        result = nodes["promote_to_queue"](state)
        assert result["queued_rules"] == []

    def test_promotion_skips_when_error_present(self, article, execution, config_obj):
        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session, trigger_service_config=config_obj)

        state = _default_state(
            sigma_rules=[{"title": "rule1"}],
            similarity_results=None,
            error="Similarity search failed",
            status="failed",
        )
        result = nodes["promote_to_queue"](state)
        assert result["queued_rules"] == []
        assert result["status"] == "failed"

    def test_promotion_skips_when_similarity_too_high(self, article, execution, config_obj):
        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session, trigger_service_config=config_obj)

        state = _default_state(
            sigma_rules=[{"title": "rule1", "detection": {}}],
            similarity_results=[{"rule_title": "rule1", "max_similarity": 0.9, "similar_rules": []}],
            max_similarity=0.9,
            config={"similarity_threshold": 0.5},
        )
        result = nodes["promote_to_queue"](state)
        assert result["queued_rules"] == []

    def test_promotion_skips_when_similarity_results_none(self, article, execution, config_obj):
        """similarity_results=None means search did not run -> skip promotion."""
        db_session = _make_db_session(article, execution)
        nodes = _capture_nodes(db_session, trigger_service_config=config_obj)

        state = _default_state(
            sigma_rules=[{"title": "rule1"}],
            similarity_results=None,
            max_similarity=0.0,
        )
        result = nodes["promote_to_queue"](state)
        assert result["queued_rules"] == []
