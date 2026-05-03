"""
Eval Diagnosis Service -- LLM-powered failure analysis for eval bundles.

Sends a slim eval bundle + the relevant extractor contract to a frontier model
and returns a structured diagnosis identifying root causes, contract violations,
and actionable recommendations.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.services.llm_service import LLMService

logger = logging.getLogger(__name__)

# Where diagnosis JSON files are persisted.
DIAGNOSES_DIR = Path(__file__).resolve().parents[2] / "data" / "diagnoses"

# Where extractor contract markdown files live.
CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "contracts"

# Map agent names to their contract filenames.
AGENT_TO_CONTRACT: dict[str, str] = {
    "CmdlineExtract": "cmdline-extract.md",
    "ProcTreeExtract": "proctree-extract.md",
    "HuntQueriesExtract": "huntquery-extract.md",
    "RegistryExtract": "registry-extract.md",
    "ServicesExtract": "services-extract.md",
    "ScheduledTasksExtract": "scheduled-tasks-extract.md",
}

# The foundation standard that applies to ALL extractors.
STANDARD_CONTRACT_FILE = "extractor-standard.md"

# System prompt for the diagnosis LLM call.
_DIAGNOSIS_SYSTEM_PROMPT = """\
You are an expert LLM extraction agent debugger for the Huntable CTI pipeline.

Your job: analyze a single eval bundle (containing the full LLM request, response,
parsed extraction results, and QA feedback) against the extractor contract and
produce a structured failure diagnosis.

You have two reference documents provided in the user message:
1. The EXTRACTOR STANDARD -- mandatory rules for ALL extractors.
2. The SPECIFIC EXTRACTOR CONTRACT -- rules for this particular agent type.

Respond ONLY with valid JSON matching this exact schema (no markdown fences,
no commentary outside the JSON):

{
  "summary": "1-2 sentence plain-English explanation of what went wrong (or right)",
  "failure_category": "<one of: prompt_gap, model_limitation, input_noise, infrastructure, correct_behavior>",
  "confidence": 0.0-1.0,
  "root_causes": [
    {"cause": "concise description", "evidence": "quote or reference from bundle", "severity": "high|medium|low"}
  ],
  "recommendations": [
    {"action": "specific actionable step", "rationale": "why this would help", "priority": 1}
  ],
  "contract_violations": ["specific contract rule text that was violated, if any"]
}

Failure category definitions:
- prompt_gap: The prompt/contract does not cover this case or is ambiguous.
- model_limitation: The model failed despite clear instructions (hallucination, missed context, etc.)
- input_noise: The source article is ambiguous, malformed, or lacks extractable content.
- infrastructure: Bundle shows infra issues (empty messages, timeout, context overflow).
- correct_behavior: The extraction was actually correct; the expected_count is wrong or the evaluator miscounted.

Guidelines:
- Be specific. Quote from the bundle and contract.
- If the extraction looks correct and the expected count is wrong, say so.
- Recommendations should be concrete prompt edits, not vague advice.
- Priority 1 = highest priority (fix first).
"""


class EvalDiagnosisService:
    """Analyzes eval bundles via LLM to produce structured failure diagnoses."""

    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    async def diagnose_bundle(
        self,
        bundle: dict[str, Any],
        agent_name: str,
        provider: str = "openai",
        model_name: str | None = "gpt-4o",
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Analyze a single eval bundle against its extractor contract."""
        # Load contract context
        standard_text = self._load_contract_file(STANDARD_CONTRACT_FILE)
        agent_contract_file = AGENT_TO_CONTRACT.get(agent_name)
        agent_contract_text = ""
        if agent_contract_file:
            agent_contract_text = self._load_contract_file(agent_contract_file)
        else:
            logger.warning(f"No contract mapping for agent: {agent_name}")

        # Build prompt
        messages = self._build_diagnosis_prompt(
            bundle=bundle,
            agent_name=agent_name,
            standard_text=standard_text,
            contract_text=agent_contract_text,
        )

        # Call LLM
        logger.info(
            f"Diagnosing bundle for execution={bundle.get('workflow', {}).get('execution_id')} "
            f"agent={agent_name} via {provider}/{model_name or 'default'}"
        )
        response = await self.llm_service.request_chat(
            provider=provider,
            model_name=model_name,
            messages=messages,
            max_tokens=2000,
            temperature=temperature,
            timeout=120.0,
            failure_context=f"eval_diagnosis:{agent_name}",
        )

        # Extract text from response
        raw_text = ""
        choices = response.get("choices", [])
        if choices:
            raw_text = choices[0].get("message", {}).get("content", "")

        # Parse structured response
        findings = self._parse_diagnosis_response(raw_text)

        # Build envelope
        diagnosis_id = str(uuid.uuid4())
        execution_id = bundle.get("workflow", {}).get("execution_id")
        workflow_meta = bundle.get("workflow", {})

        diagnosis = {
            "diagnosis_id": diagnosis_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "execution_id": execution_id,
            "agent_name": agent_name,
            "provider_used": provider,
            "model_used": model_name or "default",
            "score_context": {
                "expected_count": workflow_meta.get("expected_count"),
                "actual_count": workflow_meta.get("actual_count"),
                "delta": workflow_meta.get("evaluation_score"),
            },
            **findings,
        }

        return diagnosis

    def _load_contract_file(self, filename: str) -> str:
        """Load a contract markdown file from docs/contracts/."""
        filepath = CONTRACTS_DIR / filename
        if not filepath.exists():
            logger.error(f"Contract file not found: {filepath}")
            return f"[Contract file {filename} not found]"
        return filepath.read_text(encoding="utf-8")

    def _build_diagnosis_prompt(
        self,
        bundle: dict[str, Any],
        agent_name: str,
        standard_text: str,
        contract_text: str,
    ) -> list[dict[str, str]]:
        """Construct the messages array for the diagnosis LLM call."""
        # Extract scoring context for the user message
        workflow_meta = bundle.get("workflow", {})
        expected = workflow_meta.get("expected_count", "unknown")
        actual = workflow_meta.get("actual_count", "unknown")
        delta = workflow_meta.get("evaluation_score", "unknown")

        # Serialize bundle (compact) for inclusion
        bundle_json = json.dumps(bundle, indent=None, default=str)

        user_content = (
            f"## Extractor Standard (mandatory for all extractors)\n\n"
            f"{standard_text}\n\n"
            f"---\n\n"
            f"## Specific Contract: {agent_name}\n\n"
            f"{contract_text}\n\n"
            f"---\n\n"
            f"## Eval Bundle\n\n"
            f"```json\n{bundle_json}\n```\n\n"
            f"---\n\n"
            f"## Scoring Context\n\n"
            f"- Expected count: {expected}\n"
            f"- Actual count: {actual}\n"
            f"- Delta (actual - expected): {delta}\n"
            f"- Delta of 0 = perfect extraction\n\n"
            f"Analyze this extraction result. Identify root causes of any discrepancy "
            f"and provide actionable recommendations."
        )

        return [
            {"role": "system", "content": _DIAGNOSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _parse_diagnosis_response(self, raw_text: str) -> dict[str, Any]:
        """Parse the LLM JSON response with fallback strategies."""
        if not raw_text:
            return self._empty_diagnosis("Empty response from LLM")

        # Strategy 1: Try direct parse
        text = raw_text.strip()

        # Strategy 2: Strip markdown code fences
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        # Strategy 3: Find first { to last }
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            text = text[first_brace : last_brace + 1]

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse diagnosis response: {e}")
            return self._empty_diagnosis(f"JSON parse error: {e}")

        # Validate required fields
        required = {"summary", "failure_category", "confidence", "root_causes", "recommendations"}
        missing = required - set(parsed.keys())
        if missing:
            logger.warning(f"Diagnosis response missing fields: {missing}")
            # Still return what we got, fill defaults
            parsed.setdefault("summary", "Diagnosis incomplete -- missing fields in LLM response")
            parsed.setdefault("failure_category", "model_limitation")
            parsed.setdefault("confidence", 0.0)
            parsed.setdefault("root_causes", [])
            parsed.setdefault("recommendations", [])

        parsed.setdefault("contract_violations", [])
        return parsed

    def _empty_diagnosis(self, reason: str) -> dict[str, Any]:
        """Return a minimal diagnosis when parsing fails."""
        return {
            "summary": f"Diagnosis failed: {reason}",
            "failure_category": "infrastructure",
            "confidence": 0.0,
            "root_causes": [{"cause": reason, "evidence": "N/A", "severity": "high"}],
            "recommendations": [],
            "contract_violations": [],
        }

    def save_diagnosis(self, diagnosis: dict[str, Any]) -> Path:
        """Persist diagnosis JSON to disk. Returns the file path."""
        DIAGNOSES_DIR.mkdir(parents=True, exist_ok=True)

        exec_id = diagnosis.get("execution_id", "unknown")
        agent = diagnosis.get("agent_name", "unknown")
        short_id = diagnosis.get("diagnosis_id", "")[:8]

        filename = f"{exec_id}_{agent}_{short_id}.json"
        filepath = DIAGNOSES_DIR / filename

        filepath.write_text(
            json.dumps(diagnosis, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info(f"Diagnosis saved: {filepath}")
        return filepath
