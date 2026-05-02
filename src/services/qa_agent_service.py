"""
QA Agent Service for validating LLM agent outputs.

Evaluates agent outputs against source articles and prompts, providing
feedback for revision when issues are detected.
"""

import json
import logging
from typing import Any

from src.database.models import ArticleTable
from src.services.llm_service import LLMService
from src.services.qa_evaluator import QAEvaluator

logger = logging.getLogger(__name__)


class QAAgentService:
    """Service for quality assurance evaluation of agent outputs."""

    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    async def evaluate_agent_output(
        self,
        article: ArticleTable,
        agent_prompt: str,
        agent_output: dict[str, Any],
        agent_name: str,
        config_obj: Any | None = None,
        execution_id: int | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """
        Evaluate agent output for compliance, accuracy, and fidelity.

        Returns:
            Dict with keys: summary, issues[], verdict
        """
        try:
            # Get QA prompt from config
            qa_prompt_dict = None
            if config_obj and config_obj.agent_prompts:
                qa_prompt_data = config_obj.agent_prompts.get("QAAgent")
                if qa_prompt_data:
                    prompt_str = qa_prompt_data.get("prompt", "")
                    if isinstance(prompt_str, str):
                        try:
                            qa_prompt_dict = json.loads(prompt_str)
                            # Handle nested JSON if present
                            if isinstance(qa_prompt_dict, dict) and len(qa_prompt_dict) == 1:
                                first_value = next(iter(qa_prompt_dict.values()))
                                if isinstance(first_value, dict):
                                    qa_prompt_dict = first_value
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse QAAgent prompt JSON, using default")

            if not qa_prompt_dict:
                qa_prompt_dict = self._get_default_qa_prompt()

            # Build system prompt
            qa_system_prompt = (
                (qa_prompt_dict.get("system") or qa_prompt_dict.get("role") or "").strip()
                + "\n\n"
                + qa_prompt_dict.get("objective", "")
            ).strip()
            if not qa_system_prompt:
                raise ValueError(
                    f"QA prompt for {agent_name} resolved to an empty system message. "
                    "Ensure the prompt config contains a non-empty 'role' or 'system' key."
                )

            # Build evaluation input
            evaluation_input = {
                "article": article.content[:10000] if article.content else "",
                "agent_prompt": agent_prompt[:5000] if agent_prompt else "",
                "agent_output": json.dumps(agent_output, indent=2)
                if isinstance(agent_output, dict)
                else str(agent_output),
            }

            evaluation_criteria = qa_prompt_dict.get("evaluation_criteria", [])
            criteria_text = "\n".join([f"- {criterion}" for criterion in evaluation_criteria])

            user_message = f"""Evaluate the following agent output:

**Article Content:**
{evaluation_input["article"]}

**Agent Prompt:**
{evaluation_input["agent_prompt"]}

**Agent Output:**
{evaluation_input["agent_output"]}

**Evaluation Criteria:**
{criteria_text}

Please provide your evaluation in the following JSON format:
{{
  "summary": "Brief summary of overall quality",
  "issues": [
    {{
      "type": "compliance | factuality | formatting",
      "description": "short explanation",
      "location": "line number or section, if applicable",
      "severity": "low | medium | high"
    }}
  ],
  "verdict": "pass | needs_revision | critical_failure"
}}"""

            messages = [{"role": "system", "content": qa_system_prompt}, {"role": "user", "content": user_message}]

            # Resolve model and sampling parameters
            qa_model_override = None
            qa_temperature = 0.1
            qa_top_p = 0.9
            if config_obj and hasattr(config_obj, "agent_models") and config_obj.agent_models:
                qa_model_override = config_obj.agent_models.get(agent_name)
                if not qa_model_override:
                    qa_model_override = config_obj.agent_models.get(f"{agent_name}QA")

                qa_temp_key = f"{agent_name}QA_temperature"
                if qa_temp_key in config_obj.agent_models:
                    qa_temperature = float(config_obj.agent_models[qa_temp_key])
                elif agent_name == "RankAgent":
                    qa_temperature = float(config_obj.agent_models.get("RankAgentQA_temperature", 0.1))

                qa_top_p_key = f"{agent_name}QA_top_p"
                if qa_top_p_key in config_obj.agent_models:
                    qa_top_p = float(config_obj.agent_models[qa_top_p_key])
                elif agent_name == "RankAgent":
                    qa_top_p = float(config_obj.agent_models.get("RankAgentQA_top_p", 0.9))

            target_model = qa_model_override or self.llm_service.model_extract

            # Resolve provider
            qa_provider = provider
            if not qa_provider and config_obj and hasattr(config_obj, "agent_models") and config_obj.agent_models:
                qa_provider_key = f"{agent_name}QA_provider"
                qa_provider = config_obj.agent_models.get(qa_provider_key)
                if not qa_provider:
                    agent_provider_key = f"{agent_name}_provider"
                    qa_provider = config_obj.agent_models.get(agent_provider_key)
                if not qa_provider:
                    qa_provider = config_obj.agent_models.get("ExtractAgent_provider")
            if not qa_provider:
                qa_provider = self.llm_service.provider_extract

            # Delegate LLM call, parsing, and normalization to QAEvaluator
            evaluator = QAEvaluator(self.llm_service)
            qa_result = await evaluator.evaluate(
                messages=messages,
                agent_name=agent_name,
                model_name=target_model,
                provider=qa_provider,
                temperature=qa_temperature,
                top_p=qa_top_p,
                max_tokens=2000,
                timeout=300.0,
                execution_id=execution_id,
                article_id=article.id if article else None,
            )

            # Strip internal housekeeping keys before returning to callers
            return {k: v for k, v in qa_result.items() if not k.startswith("_")}

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"QA evaluation error for {agent_name}: {e}", exc_info=True)
            return {
                "summary": f"QA evaluation failed: {str(e)}",
                "issues": [
                    {
                        "type": "compliance",
                        "description": f"QA evaluation error: {str(e)}",
                        "location": "QA service",
                        "severity": "high",
                    }
                ],
                "verdict": "critical_failure",
            }

    async def generate_feedback(self, qa_result: dict[str, Any], agent_name: str) -> str:
        """
        Generate feedback message for agent based on QA results.

        Returns:
            Feedback string for agent to use in retry
        """
        issues = qa_result.get("issues", [])
        summary = qa_result.get("summary", "")

        if not issues:
            return f"QA feedback: {summary}. Please review and improve your output."

        compliance_issues = [i for i in issues if i.get("type") == "compliance"]
        factuality_issues = [i for i in issues if i.get("type") == "factuality"]
        formatting_issues = [i for i in issues if i.get("type") == "formatting"]

        feedback_parts = []

        if compliance_issues:
            feedback_parts.append("**Compliance Issues:**")
            for issue in compliance_issues:
                feedback_parts.append(
                    f"- {issue.get('description', '')} (severity: {issue.get('severity', 'unknown')})"
                )

        if factuality_issues:
            feedback_parts.append("\n**Factuality Issues:**")
            for issue in factuality_issues:
                feedback_parts.append(
                    f"- {issue.get('description', '')} (location: {issue.get('location', 'unknown')})"
                )

        if formatting_issues:
            feedback_parts.append("\n**Formatting Issues:**")
            for issue in formatting_issues:
                feedback_parts.append(
                    f"- {issue.get('description', '')} (location: {issue.get('location', 'unknown')})"
                )

        feedback = "\n".join(feedback_parts)

        if summary:
            feedback = f"QA Summary: {summary}\n\n{feedback}"

        return f"Previous QA feedback:\n{feedback}\n\nPlease revise your output based on this feedback."

    def _get_default_qa_prompt(self) -> dict[str, Any]:
        """Get default QA prompt structure."""
        return {
            "role": "You are a quality assurance agent responsible for evaluating LLM agent outputs for compliance, accuracy, and fidelity to source materials.",
            "objective": "For each task, verify that the evaluated agent's output strictly adheres to its original instructions and is fully supported by the source article content. Identify all deviations, omissions, hallucinations, or format violations.",
            "evaluation_criteria": [
                "[PASS] Does the output fully comply with the original prompt's rules and constraints?",
                "[PASS] Are all outputs directly grounded in the source article?",
                "[WARN] Are there any hallucinated elements not supported by the article?",
                "[WARN] Were any expected outputs omitted based on the prompt and article content?",
                "[FAIL] Are there formatting violations (YAML structure, required fields missing, etc)?",
                "[FAIL] Are any forbidden behaviors or outputs present (as defined by the agent_prompt)?",
            ],
        }
