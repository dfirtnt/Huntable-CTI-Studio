"""
QA Agent Service for validating LLM agent outputs.

Evaluates agent outputs against source articles and prompts, providing
feedback for revision when issues are detected.
"""

import logging
import json
from typing import Dict, Any, Optional

from src.database.models import ArticleTable
from src.services.llm_service import LLMService
from src.utils.langfuse_client import trace_llm_call, log_llm_completion, log_llm_error

logger = logging.getLogger(__name__)


class QAAgentService:
    """Service for quality assurance evaluation of agent outputs."""
    
    def __init__(self, llm_service: LLMService):
        """
        Initialize QA Agent Service.
        
        Args:
            llm_service: LLMService instance for QA evaluation
        """
        self.llm_service = llm_service
    
    async def evaluate_agent_output(
        self,
        article: ArticleTable,
        agent_prompt: str,
        agent_output: Dict[str, Any],
        agent_name: str,
        config_obj: Optional[Any] = None,
        execution_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Evaluate agent output for compliance, accuracy, and fidelity.
        
        Args:
            article: Source article
            agent_prompt: Original prompt given to the agent
            agent_output: Agent's output to evaluate
            agent_name: Name of the agent being evaluated
            config_obj: Workflow config object (for getting QA prompt)
            execution_id: Optional workflow execution id for Langfuse tracing
        
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
            
            # Use default QA prompt structure if not found in config
            if not qa_prompt_dict:
                qa_prompt_dict = self._get_default_qa_prompt()
            
            # Format QA evaluation prompt
            qa_system_prompt = qa_prompt_dict.get("role", "") + "\n\n" + qa_prompt_dict.get("objective", "")
            
            # Build evaluation input
            evaluation_input = {
                "article": article.content[:10000] if article.content else "",  # Truncate for context
                "agent_prompt": agent_prompt[:5000] if agent_prompt else "",  # Truncate for context
                "agent_output": json.dumps(agent_output, indent=2) if isinstance(agent_output, dict) else str(agent_output)
            }
            
            # Create user message with evaluation criteria
            evaluation_criteria = qa_prompt_dict.get("evaluation_criteria", [])
            criteria_text = "\n".join([f"- {criterion}" for criterion in evaluation_criteria])
            
            user_message = f"""Evaluate the following agent output:

**Article Content:**
{evaluation_input['article']}

**Agent Prompt:**
{evaluation_input['agent_prompt']}

**Agent Output:**
{evaluation_input['agent_output']}

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
            
            # Call LLM for QA evaluation
            # Use extract model for QA (can be configured separately later)
            messages = [
                {"role": "system", "content": qa_system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            # Convert messages for model compatibility
            converted_messages = self.llm_service._convert_messages_for_model(messages, self.llm_service.model_extract)
            
            # Create payload for LMStudio API
            payload = {
                "model": self.llm_service.model_extract,
                "messages": converted_messages,
                "max_tokens": 2000,  # Enough for detailed QA evaluation
                "temperature": 0.1,  # Low temperature for consistent evaluation
                "top_p": 0.9
            }
            
            generation = None
            # Call LMStudio API with Langfuse tracing
            with trace_llm_call(
                name=f"qa_{agent_name.lower()}",
                model=self.llm_service.model_extract,
                execution_id=execution_id,
                article_id=article.id if article else None,
                metadata={"messages": converted_messages, "agent_name": agent_name}
            ) as generation:
                response = await self.llm_service._post_lmstudio_chat(
                    payload=payload,
                    model_name=self.llm_service.model_extract,
                    timeout=300.0,
                    failure_context=f"QA evaluation for {agent_name}"
                )
            
            # Parse response
            response_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if generation:
                log_llm_completion(
                    generation=generation,
                    input_messages=converted_messages,
                    output=response_text or "",
                    usage=response.get("usage", {}),
                    metadata={"agent_name": agent_name, "qa_prompt": qa_prompt_dict}
                )
            
            # Try to extract JSON from response
            qa_result = self._parse_qa_response(response_text)
            
            return qa_result
            
        except Exception as e:
            logger.error(f"QA evaluation error for {agent_name}: {e}", exc_info=True)
            if 'generation' in locals() and generation:
                log_llm_error(generation, e, metadata={"agent_name": agent_name})
            # Return failure verdict on error
            return {
                "summary": f"QA evaluation failed: {str(e)}",
                "issues": [
                    {
                        "type": "compliance",
                        "description": f"QA evaluation error: {str(e)}",
                        "location": "QA service",
                        "severity": "high"
                    }
                ],
                "verdict": "critical_failure"
            }
    
    def _parse_qa_response(self, response_text: str) -> Dict[str, Any]:
        """Parse QA response text into structured format."""
        try:
            # Try to extract JSON from response
            # Look for JSON object in the response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                # Validate structure
                if "verdict" in result and "summary" in result:
                    if "issues" not in result:
                        result["issues"] = []
                    return result
        except Exception as e:
            logger.warning(f"Failed to parse QA response as JSON: {e}")
        
        # Fallback: create structured response from text
        verdict = "needs_revision"
        if "pass" in response_text.lower() or "✅" in response_text:
            verdict = "pass"
        elif "critical" in response_text.lower() or "❌" in response_text:
            verdict = "critical_failure"
        
        return {
            "summary": response_text[:500] if response_text else "QA evaluation completed",
            "issues": [],
            "verdict": verdict
        }
    
    async def generate_feedback(
        self,
        qa_result: Dict[str, Any],
        agent_name: str
    ) -> str:
        """
        Generate feedback message for agent based on QA results.
        
        Args:
            qa_result: QA evaluation result
            agent_name: Name of the agent
        
        Returns:
            Feedback string for agent to use in retry
        """
        issues = qa_result.get("issues", [])
        summary = qa_result.get("summary", "")
        
        if not issues:
            return f"QA feedback: {summary}. Please review and improve your output."
        
        # Group issues by type
        compliance_issues = [i for i in issues if i.get("type") == "compliance"]
        factuality_issues = [i for i in issues if i.get("type") == "factuality"]
        formatting_issues = [i for i in issues if i.get("type") == "formatting"]
        
        feedback_parts = []
        
        if compliance_issues:
            feedback_parts.append("**Compliance Issues:**")
            for issue in compliance_issues:
                feedback_parts.append(f"- {issue.get('description', '')} (severity: {issue.get('severity', 'unknown')})")
        
        if factuality_issues:
            feedback_parts.append("\n**Factuality Issues:**")
            for issue in factuality_issues:
                feedback_parts.append(f"- {issue.get('description', '')} (location: {issue.get('location', 'unknown')})")
        
        if formatting_issues:
            feedback_parts.append("\n**Formatting Issues:**")
            for issue in formatting_issues:
                feedback_parts.append(f"- {issue.get('description', '')} (location: {issue.get('location', 'unknown')})")
        
        feedback = "\n".join(feedback_parts)
        
        if summary:
            feedback = f"QA Summary: {summary}\n\n{feedback}"
        
        return f"Previous QA feedback:\n{feedback}\n\nPlease revise your output based on this feedback."
    
    def _get_default_qa_prompt(self) -> Dict[str, Any]:
        """Get default QA prompt structure."""
        return {
            "role": "You are a quality assurance agent responsible for evaluating LLM agent outputs for compliance, accuracy, and fidelity to source materials.",
            "objective": "For each task, verify that the evaluated agent's output strictly adheres to its original instructions and is fully supported by the source article content. Identify all deviations, omissions, hallucinations, or format violations.",
            "evaluation_criteria": [
                "✅ Does the output fully comply with the original prompt's rules and constraints?",
                "✅ Are all outputs directly grounded in the source article?",
                "⚠️ Are there any hallucinated elements not supported by the article?",
                "⚠️ Were any expected outputs omitted based on the prompt and article content?",
                "❌ Are there formatting violations (YAML structure, required fields missing, etc)?",
                "❌ Are any forbidden behaviors or outputs present (as defined by the agent_prompt)?"
            ]
        }
