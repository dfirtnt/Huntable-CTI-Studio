"""
Extract Agent Evaluator.

Evaluates Extract Agent performance on test datasets.
"""

import json
import logging
from pathlib import Path
from typing import Any

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable
from src.services.evaluation.base_evaluator import BaseAgentEvaluator
from src.services.llm_service import LLMService
from src.utils.content_filter import ContentFilter

logger = logging.getLogger(__name__)


class ExtractAgentEvaluator(BaseAgentEvaluator):
    """
    Evaluator for Extract Agent.

    Metrics:
    - JSON validity rate
    - Field completeness rate
    - Observable count (avg, total)
    - Count accuracy vs ground truth
    - Command-line extraction count
    - Type error rate
    """

    def __init__(
        self,
        model_version: str | None = None,
        evaluation_type: str = "baseline",
        workflow_config_version: int | None = None,
    ):
        """Initialize Extract Agent evaluator."""
        super().__init__(
            agent_name="ExtractAgent",
            model_version=model_version,
            evaluation_type=evaluation_type,
            workflow_config_version=workflow_config_version,
        )

    async def evaluate_dataset(
        self,
        test_data_path: Path,
        llm_service: LLMService | None = None,
        content_filter: ContentFilter | None = None,
        junk_filter_threshold: float = 0.8,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Evaluate Extract Agent on test dataset.

        Args:
            test_data_path: Path to test dataset JSON file
            llm_service: LLM service instance
            content_filter: Content filter instance
            junk_filter_threshold: Junk filter threshold
            **kwargs: Additional parameters

        Returns:
            Dictionary with evaluation results
        """
        # Load test data
        with open(test_data_path) as f:
            test_data = json.load(f)

        # Initialize services if not provided
        if not llm_service:
            llm_service = LLMService()
        if not content_filter:
            content_filter = ContentFilter()

        # Get database session
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        results = []

        try:
            for example in test_data:
                article_id = example.get("article_id")
                expected_extraction = example.get("expected_extraction") or example.get("extraction_result")

                if not article_id:
                    logger.warning("Skipping example without article_id")
                    continue

                # Get article from database
                article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()

                if not article:
                    logger.warning(f"Article {article_id} not found, skipping")
                    results.append({"article_id": article_id, "error": "Article not found", "evaluation": None})
                    continue

                # Evaluate article
                try:
                    result = await self._evaluate_article(
                        article, llm_service, content_filter, junk_filter_threshold, expected_extraction
                    )
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error evaluating article {article_id}: {e}")
                    results.append({"article_id": article_id, "error": str(e), "evaluation": None})
        finally:
            db_session.close()

        self.results = results
        return self.calculate_metrics()

    async def _evaluate_article(
        self,
        article: ArticleTable,
        llm_service: LLMService,
        content_filter: ContentFilter,
        junk_filter_threshold: float,
        expected_extraction: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate extraction on a single article."""
        # Apply junk filter (matches workflow)
        content = article.content or ""
        if content:
            hunt_score = article.article_metadata.get("threat_hunting_score", 0) if article.article_metadata else 0
            filter_result = content_filter.filter_content(
                content, min_confidence=junk_filter_threshold, hunt_score=hunt_score, article_id=article.id
            )
            filtered_content = filter_result.filtered_content or content
        else:
            filtered_content = content

        # Get prompt config
        from src.database.manager import DatabaseManager
        from src.services.workflow_trigger_service import WorkflowTriggerService

        db_session = DatabaseManager().get_session()
        try:
            trigger_service = WorkflowTriggerService(db_session)
            config_obj = trigger_service.get_active_config()

            if not config_obj or not config_obj.agent_prompts or "ExtractAgent" not in config_obj.agent_prompts:
                raise ValueError("ExtractAgent prompt not found in workflow config")

            agent_prompt_data = config_obj.agent_prompts["ExtractAgent"]

            # Parse prompt JSON
            prompt_config_dict = None
            if isinstance(agent_prompt_data.get("prompt"), str):
                prompt_config_dict = json.loads(agent_prompt_data["prompt"])
            elif isinstance(agent_prompt_data.get("prompt"), dict):
                prompt_config_dict = agent_prompt_data["prompt"]

            instructions_template_str = agent_prompt_data.get("instructions")
        finally:
            db_session.close()

        # Run extraction
        try:
            extraction_result = await llm_service.extract_behaviors(
                content=filtered_content,
                title=article.title,
                url=article.canonical_url or "",
                prompt_config_dict=prompt_config_dict,
                instructions_template_str=instructions_template_str,
                article_id=article.id,
            )
        except Exception as e:
            return {"article_id": article.id, "error": str(e), "extraction_result": None, "evaluation": None}

        # Evaluate
        expected_observables = None
        if expected_extraction:
            expected_observables = expected_extraction.get("observables", [])

        evaluation = self._evaluate_extraction_result(extraction_result, expected_observables)

        return {
            "article_id": article.id,
            "title": article.title,
            "url": article.canonical_url or "",
            "extraction_result": extraction_result,
            "evaluation": evaluation,
            "expected_extraction": expected_extraction,
        }

    def _evaluate_extraction_result(
        self, result: dict[str, Any], expected_observables: list[str] | None = None
    ) -> dict[str, Any]:
        """Evaluate a single extraction result."""
        evaluation = {
            "json_valid": False,
            "has_required_fields": False,
            "observable_count": 0,
            "discrete_count": 0,
            "count_match": None,
            "field_errors": [],
            "type_errors": [],
        }

        if not result:
            evaluation["field_errors"].append("Result is None or empty")
            return evaluation

        # JSON validity (already parsed if we got here)
        evaluation["json_valid"] = True

        # Required fields
        required_fields = ["behavioral_observables", "observable_list", "discrete_huntables_count", "content", "url"]

        missing_fields = []
        for field in required_fields:
            if field not in result:
                missing_fields.append(field)

        evaluation["has_required_fields"] = len(missing_fields) == 0
        if missing_fields:
            evaluation["field_errors"].extend([f"Missing: {f}" for f in missing_fields])

        # Observable counts
        behavioral_obs = result.get("behavioral_observables", [])
        observable_list = result.get("observable_list", [])
        discrete_count = result.get("discrete_huntables_count", 0)

        evaluation["observable_count"] = len(observable_list)
        evaluation["discrete_count"] = discrete_count

        # Count command-lines
        commandline_count = 0
        for obs in observable_list:
            if isinstance(obs, dict):
                if "commandline" in str(obs).lower() or "command" in str(obs).lower():
                    commandline_count += 1

        evaluation["commandline_count"] = commandline_count

        # Type checks
        if not isinstance(behavioral_obs, list):
            evaluation["type_errors"].append(f"behavioral_observables is {type(behavioral_obs)}, expected list")
        if not isinstance(observable_list, list):
            evaluation["type_errors"].append(f"observable_list is {type(observable_list)}, expected list")
        if not isinstance(discrete_count, int):
            evaluation["type_errors"].append(f"discrete_huntables_count is {type(discrete_count)}, expected int")

        # Count accuracy (if expected provided)
        if expected_observables is not None:
            expected_count = len(expected_observables)
            actual_count = discrete_count
            evaluation["count_match"] = expected_count == actual_count
            evaluation["count_diff"] = actual_count - expected_count
            evaluation["expected_count"] = expected_count

        return evaluation

    def calculate_metrics(self) -> dict[str, Any]:
        """Calculate aggregate metrics from results."""
        if not self.results:
            return {}

        total = len(self.results)
        errors = sum(1 for r in self.results if r.get("error"))
        valid_results = [r for r in self.results if r.get("evaluation") and not r.get("error")]

        if not valid_results:
            return {
                "total_articles": total,
                "errors": errors,
                "valid_results": 0,
                "error_rate": errors / total if total > 0 else 0,
            }

        evaluations = [r["evaluation"] for r in valid_results]

        metrics = {
            "total_articles": total,
            "errors": errors,
            "valid_results": len(valid_results),
            "error_rate": errors / total if total > 0 else 0,
            # JSON validity
            "json_validity_rate": sum(1 for e in evaluations if e["json_valid"]) / len(evaluations),
            # Field completeness
            "field_completeness_rate": sum(1 for e in evaluations if e["has_required_fields"]) / len(evaluations),
            # Observable counts
            "avg_observable_count": sum(e["observable_count"] for e in evaluations) / len(evaluations),
            "avg_discrete_count": sum(e["discrete_count"] for e in evaluations) / len(evaluations),
            "total_observables": sum(e["observable_count"] for e in evaluations),
            "total_discrete": sum(e["discrete_count"] for e in evaluations),
            # Command-line counts
            "avg_commandline_count": sum(e.get("commandline_count", 0) for e in evaluations) / len(evaluations),
            "total_commandlines": sum(e.get("commandline_count", 0) for e in evaluations),
            # Count accuracy (if expected provided)
            "count_accuracy": None,
            "avg_count_diff": None,
        }

        # Count accuracy
        count_matches = [e for e in evaluations if e.get("count_match") is not None]
        if count_matches:
            metrics["count_accuracy"] = sum(1 for e in count_matches if e["count_match"]) / len(count_matches)
            metrics["avg_count_diff"] = sum(e.get("count_diff", 0) for e in count_matches) / len(count_matches)

        # Type errors
        type_errors = [e for e in evaluations if e.get("type_errors")]
        metrics["type_error_rate"] = len(type_errors) / len(evaluations) if evaluations else 0

        self.metrics = metrics
        return metrics
