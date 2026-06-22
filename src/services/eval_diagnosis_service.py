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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.services.llm_service import LLMService

logger = logging.getLogger(__name__)

DIAGNOSES_DIR = Path(__file__).resolve().parents[2] / "data" / "diagnoses"
CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "contracts"

AGENT_TO_CONTRACT: dict[str, str] = {
    "CmdlineExtract": "cmdline-extract.md",
    "ProcTreeExtract": "proctree-extract.md",
    "HuntQueriesExtract": "huntquery-extract.md",
    "RegistryExtract": "registry-extract.md",
    "ServicesExtract": "services-extract.md",
    "ScheduledTasksExtract": "scheduled-tasks-extract.md",
    "NetworkIndicatorExtract": "network-indicator-extract.md",
}

STANDARD_CONTRACT_FILE = "extractor-standard.md"

_DIAGNOSIS_SYSTEM_PROMPT = """\
You are an expert LLM extraction agent debugger for the Huntable CTI pipeline.

Your job: analyze a single eval bundle (containing the full LLM request, response,
parsed extraction results, and QA feedback) against the extractor contract and
produce a structured diagnosis -- even when the run "succeeded" on count alone.

You have two reference documents provided in the user message:
1. The EXTRACTOR STANDARD -- mandatory rules for ALL extractors.
2. The SPECIFIC EXTRACTOR CONTRACT -- rules for this particular agent type.

Respond ONLY with valid JSON matching this exact schema (no markdown fences,
no commentary outside the JSON):

{
  "summary": "1-2 sentence plain-English explanation of what went wrong or right, including any hidden issues",
  "failure_category": "<one of: prompt_gap, model_limitation, input_noise, infrastructure, correct_behavior>",
  "confidence": 0.0-1.0,
  "run_signals": {
    "truncation_detected": true|false,
    "context_pressure": "low|medium|high",
    "contract_compliance": "full|partial|violated",
    "finish_reason": "<stop|length|error|unknown>",
    "token_utilization_pct": <integer 0-100 or null>
  },
  "root_causes": [
    {"cause": "concise description", "evidence": "quote or reference from bundle", "severity": "high|medium|low"}
  ],
  "recommendations": [
    {"type": "<prompt_edit|model_tuning|infra_fix>", "action": "specific actionable step", "rationale": "why this would help", "priority": 1}
  ],
  "contract_violations": ["specific contract rule text that was violated, if any"]
}

Field definitions:

failure_category:
- prompt_gap: The prompt/contract does not cover this case or is ambiguous.
- model_limitation: The model failed despite clear instructions (hallucination, missed context, etc.)
- input_noise: The source article is ambiguous, malformed, or lacks extractable content.
- infrastructure: Bundle shows infra issues (empty messages, timeout, context overflow, rate limit/TPM error).
- correct_behavior: The extraction was actually correct; the expected_count is wrong or the evaluator miscounted.

run_signals -- populate for EVERY run, including successful ones:
- truncation_detected: true if finish_reason == "length" OR the response JSON appears cut off mid-value.
- context_pressure: "high" if prompt_tokens > 80% of model context window; "medium" if 50-80%; "low" otherwise.
- contract_compliance: "full" = all required fields present and well-formed; "partial" = fields present but some malformed or empty; "violated" = required fields missing or wrong type.
- finish_reason: read from response choices[0].finish_reason; use "unknown" if absent from bundle.
- token_utilization_pct: (prompt_tokens / model_context_window) * 100, rounded to nearest integer. Use null if context window size is unknown for this model.

recommendation types:
- prompt_edit: A concrete change to the system prompt, task instructions, or contract. Quote the clause to change and show the proposed replacement.
- model_tuning: A parameter or model selection change -- name the specific model (e.g., "For gemma-3-12b, reduce max_tokens from 2000 to 1200"). Never give generic tuning advice.
- infra_fix: A pipeline fix (retry logic, timeout increase, input preprocessing, chunk splitting, etc.).

Guidelines:
- Check run_signals FIRST. Truncation and context pressure are silent failure modes that corrupt output even when count delta is 0.
- If finish_reason == "length", truncation is always a root cause regardless of extraction score.
- Check contract compliance independently of count: delta=0 runs can still have malformed fields, wrong types, or missing required keys.
- Rate limit and TPM errors typically appear as HTTP 429, empty choices, or error fields in the bundle -- flag these as infrastructure with infra_fix recommendations.
- Context window exceeded: if prompt_tokens approaches or exceeds the model's context window, flag as infrastructure and recommend chunk splitting or prompt compression.
- Model tuning recommendations should account for which model is being used and its known behaviors. Smaller local models (gemma, mistral, phi) benefit from shorter prompts, explicit JSON examples, and lower temperatures. Larger frontier models tolerate more complex instructions.
- Priority 1 = highest priority (fix first).
- If the extraction looks correct and the expected count is wrong, say so in summary and use failure_category=correct_behavior.
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
        standard_text = self._load_contract_file(STANDARD_CONTRACT_FILE)
        agent_contract_file = AGENT_TO_CONTRACT.get(agent_name)
        agent_contract_text = ""
        if agent_contract_file:
            agent_contract_text = self._load_contract_file(agent_contract_file)
        else:
            logger.warning(f"No contract mapping for agent: {agent_name}")

        messages = self._build_diagnosis_prompt(
            bundle=bundle,
            agent_name=agent_name,
            standard_text=standard_text,
            contract_text=agent_contract_text,
        )

        logger.info(
            f"Diagnosing bundle for execution={bundle.get('workflow', {}).get('execution_id')} "
            f"agent={agent_name} via {provider}/{model_name or 'default'}"
        )
        response = await self.llm_service.request_chat(
            provider=provider,
            model_name=model_name,
            messages=messages,
            max_tokens=3500,
            temperature=temperature,
            timeout=120.0,
            failure_context=f"eval_diagnosis:{agent_name}",
        )

        raw_text = ""
        finish_reason = "unknown"
        choices = response.get("choices", [])
        if choices:
            raw_text = choices[0].get("message", {}).get("content", "")
            finish_reason = choices[0].get("finish_reason", "unknown") or "unknown"

        findings = self._parse_diagnosis_response(raw_text, finish_reason=finish_reason)

        diagnosis_id = str(uuid.uuid4())
        execution_id = bundle.get("workflow", {}).get("execution_id")
        workflow_meta = bundle.get("workflow", {})

        diagnosis = {
            "diagnosis_id": diagnosis_id,
            "created_at": datetime.now(UTC).isoformat(),
            "execution_id": execution_id,
            "agent_name": agent_name,
            "provider_used": provider,
            "model_used": model_name or "default",
            "score_context": {
                "expected_count": workflow_meta.get("expected_count"),
                "actual_count": workflow_meta.get("actual_count"),
                "delta": workflow_meta.get("evaluation_score"),
                # Item-level context (present only when expected_items was set)
                "matched_count": workflow_meta.get("matched_count"),
                "missed_count": workflow_meta.get("missed_count"),
                "extra_count": workflow_meta.get("extra_count"),
                "missed_items": workflow_meta.get("missed_items"),
                "extra_items": workflow_meta.get("extra_items"),
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
        workflow_meta = bundle.get("workflow", {})
        expected = workflow_meta.get("expected_count", "unknown")
        actual = workflow_meta.get("actual_count", "unknown")
        delta = workflow_meta.get("evaluation_score", "unknown")

        bundle_json = json.dumps(bundle, indent=None, default=str)

        # Build item-level context block when available
        missed_items = workflow_meta.get("missed_items")
        extra_items = workflow_meta.get("extra_items")
        matched_count = workflow_meta.get("matched_count")
        item_context = ""
        if matched_count is not None or missed_items or extra_items:
            item_context = (
                f"\n- Matched items (correct): {matched_count}\n"
                f"- Missed items (in expected but not extracted): {len(missed_items) if missed_items else 0}\n"
            )
            if missed_items:
                item_context += "  Missed:\n" + "".join(f"    - {i}\n" for i in missed_items[:20])
            if extra_items:
                item_context += f"- Extra items (extracted but not in expected): {len(extra_items)}\n"
                item_context += "  Extra:\n" + "".join(f"    - {i}\n" for i in extra_items[:20])

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
            f"- Delta of 0 = perfect extraction\n"
            f"{item_context}\n"
            f"Analyze this extraction result. Identify root causes of any discrepancy "
            f"and provide actionable recommendations."
        )

        return [
            {"role": "system", "content": _DIAGNOSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _parse_diagnosis_response(self, raw_text: str, finish_reason: str = "unknown") -> dict[str, Any]:
        """Parse the LLM JSON response with fallback strategies."""
        truncated = finish_reason == "length"

        if not raw_text:
            return self._empty_diagnosis("Empty response from LLM", truncated=truncated)

        text = raw_text.strip()

        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            text = text[first_brace : last_brace + 1]

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse diagnosis response: {e}")
            reason = "Response truncated by token limit -- JSON incomplete" if truncated else f"JSON parse error: {e}"
            return self._empty_diagnosis(reason, truncated=truncated)

        required = {"summary", "failure_category", "confidence", "root_causes", "recommendations"}
        missing = required - set(parsed.keys())
        if missing:
            logger.warning(f"Diagnosis response missing fields: {missing}")
            parsed.setdefault("summary", "Diagnosis incomplete -- missing fields in LLM response")
            parsed.setdefault("failure_category", "model_limitation")
            parsed.setdefault("confidence", 0.0)
            parsed.setdefault("root_causes", [])
            parsed.setdefault("recommendations", [])

        parsed.setdefault("contract_violations", [])
        run_signals = parsed.setdefault("run_signals", {})
        run_signals.setdefault("truncation_detected", truncated)
        run_signals.setdefault("context_pressure", "unknown")
        run_signals.setdefault("contract_compliance", "unknown")
        run_signals.setdefault("finish_reason", finish_reason)
        run_signals.setdefault("token_utilization_pct", None)
        return parsed

    def _empty_diagnosis(self, reason: str, truncated: bool = False) -> dict[str, Any]:
        """Return a minimal diagnosis when parsing fails."""
        return {
            "summary": f"Diagnosis failed: {reason}",
            "failure_category": "infrastructure",
            "confidence": 0.0,
            "run_signals": {
                "truncation_detected": truncated,
                "context_pressure": "unknown",
                "contract_compliance": "unknown",
                "finish_reason": "length" if truncated else "unknown",
                "token_utilization_pct": None,
            },
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
