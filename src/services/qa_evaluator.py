"""
Shared QA evaluator: LLM call, 6-strategy response parser, fail-closed default,
and schema normalization. Call sites own message building and retry semantics.

Canonical output key: `verdict` (pass | needs_revision | critical_failure).
The legacy `status` key is normalized here so callers never see it.
"""

import json
import logging
import re
from typing import Any

from src.utils.langfuse_client import log_llm_completion, trace_llm_call

logger = logging.getLogger(__name__)


def _normalize_verdict(raw: str) -> str:
    """Map any verdict/status string to the three canonical values."""
    v = (raw or "").strip().lower()
    if v == "pass":
        return "pass"
    if v == "critical_failure":
        return "critical_failure"
    return "needs_revision"


class QAEvaluator:
    """
    Shared QA evaluation primitive.

    Owns:
      - The LLM call (via llm_service.request_chat)
      - The 6-strategy JSON response parser
      - Fail-closed default (parse failure -> verdict=needs_revision)
      - Schema normalization (status -> verdict)

    Does NOT own:
      - Message building (caller's responsibility)
      - Retry loops (caller's responsibility)
      - Correction application (caller's responsibility)
    """

    def __init__(self, llm_service: Any) -> None:
        self._llm = llm_service

    async def evaluate(
        self,
        *,
        messages: list[dict],
        agent_name: str,
        model_name: str,
        provider: str,
        temperature: float = 0.1,
        top_p: float | None = None,
        seed: int | None = None,
        max_tokens: int = 1000,
        timeout: float = 180.0,
        execution_id: int | None = None,
        article_id: int | None = None,
        attempt: int = 1,
    ) -> dict[str, Any]:
        """
        Run one QA LLM call, parse the response, and return a normalized result.

        Returns a dict that always contains:
          verdict      - "pass" | "needs_revision" | "critical_failure"
          summary      - str
          issues       - list
          parsing_failed - bool
          _qa_text     - raw LLM response text (for fallback feedback extraction at call sites)
          _parse_error - error description if parsing_failed, else None

        All other keys from the parsed LLM JSON are passed through unchanged.
        """
        converted = self._llm._convert_messages_for_model(messages, model_name)

        with trace_llm_call(
            name=f"{agent_name.lower()}_qa",
            model=model_name,
            execution_id=execution_id,
            article_id=article_id,
            metadata={
                "agent_name": agent_name,
                "attempt": attempt,
                "messages": messages,
            },
        ) as generation:
            response = await self._llm.request_chat(
                provider=provider,
                model_name=model_name,
                messages=converted,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                timeout=timeout,
                seed=seed,
                failure_context=f"{agent_name} QA attempt {attempt}",
            )

        qa_text = response["choices"][0]["message"].get("content", "")
        logger.info(f"{agent_name} QA response (first 500 chars): {qa_text[:500]}")

        if generation:
            log_llm_completion(
                generation=generation,
                input_messages=messages,
                output=qa_text[:500],
                usage=response.get("usage", {}),
                metadata={"agent_name": agent_name, "attempt": attempt, "qa": True},
            )

        parsed, parsing_failed, parse_error = self._parse_response_text(qa_text, agent_name)

        if parsing_failed:
            verdict = "needs_revision"
        else:
            raw = parsed.get("verdict") or parsed.get("status") or "needs_revision"
            verdict = _normalize_verdict(raw)

        summary = parsed.get("summary") or parsed.get("feedback") or ""
        if not summary:
            if parsing_failed:
                summary = f"QA response parsing failed: {parse_error}"
            elif verdict == "pass":
                summary = "QA passed successfully."
            else:
                summary = "QA failed without feedback."

        return {
            **parsed,
            "verdict": verdict,
            "summary": summary,
            "issues": parsed.get("issues", []),
            "parsing_failed": parsing_failed,
            "_qa_text": qa_text,
            "_parse_error": parse_error,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_response_text(self, qa_text: str, agent_name: str) -> tuple[dict[str, Any], bool, str | None]:
        """
        Try 6 strategies in order to extract a JSON object from qa_text.

        Returns (result_dict, parsing_failed, error_message_or_None).
        """
        strategies_tried: list[str] = []

        # Strategy 1: balanced-brace walk (handles nested JSON correctly)
        try:
            start_idx = qa_text.find("{")
            if start_idx != -1:
                brace_count = 0
                end_idx = start_idx
                in_string = False
                escape_next = False
                for i in range(start_idx, len(qa_text)):
                    char = qa_text[i]
                    if escape_next:
                        escape_next = False
                        continue
                    if char == "\\":
                        escape_next = True
                        continue
                    if char == '"' and not escape_next:
                        in_string = not in_string
                        continue
                    if not in_string:
                        if char == "{":
                            brace_count += 1
                        elif char == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i
                                break
                if brace_count == 0 and end_idx > start_idx:
                    result = json.loads(qa_text[start_idx : end_idx + 1])
                    logger.info(f"{agent_name} QA parsed keys: {list(result.keys())}")
                    return result, False, None
                strategies_tried.append(f"balanced_braces_unbalanced(count={brace_count})")
                raise ValueError(f"Unbalanced braces (count: {brace_count})")
            strategies_tried.append("no_opening_brace")
            raise ValueError("No opening brace found")
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: full text if it looks like JSON
        try:
            stripped = qa_text.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                result = json.loads(stripped)
                logger.info(f"{agent_name} QA parsed keys (full text): {list(result.keys())}")
                return result, False, None
            strategies_tried.append("full_text_not_json")
        except (json.JSONDecodeError, ValueError):
            strategies_tried.append("full_text_parse_error")

        # Strategy 3: JSON inside markdown code blocks
        try:
            code_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", qa_text, re.DOTALL)
            if code_match:
                result = json.loads(code_match.group(1))
                logger.info(f"{agent_name} QA parsed keys (code block): {list(result.keys())}")
                return result, False, None
            strategies_tried.append("no_code_block")
        except (json.JSONDecodeError, ValueError):
            strategies_tried.append("code_block_parse_error")

        # Strategy 4: permissive regex for shallow-nested objects
        try:
            for match in re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", qa_text, re.DOTALL):
                try:
                    candidate = json.loads(match)
                    if "status" in candidate or "verdict" in candidate:
                        logger.info(f"{agent_name} QA parsed keys (regex): {list(candidate.keys())}")
                        return candidate, False, None
                except json.JSONDecodeError:
                    continue
            strategies_tried.append("regex_no_valid_json")
        except Exception:
            strategies_tried.append("regex_exception")

        # Strategy 5: find JSON after common text prefixes
        try:
            for prefix in ("```json", "```", "JSON:", "Response:", "Output:"):
                prefix_idx = qa_text.find(prefix)
                if prefix_idx == -1:
                    continue
                after = qa_text[prefix_idx + len(prefix) :].strip()
                start = after.find("{")
                if start == -1:
                    continue
                depth = 0
                end = start
                for i in range(start, len(after)):
                    if after[i] == "{":
                        depth += 1
                    elif after[i] == "}":
                        depth -= 1
                        if depth == 0:
                            end = i
                            break
                if depth == 0:
                    try:
                        result = json.loads(after[start : end + 1])
                        logger.info(f"{agent_name} QA parsed keys (prefix '{prefix}'): {list(result.keys())}")
                        return result, False, None
                    except json.JSONDecodeError:
                        continue
            strategies_tried.append("prefix_extraction_failed")
        except Exception:
            strategies_tried.append("prefix_exception")

        # Strategy 6: brute-force substring scan
        try:
            for start_pos in range(len(qa_text)):
                if qa_text[start_pos] != "{":
                    continue
                for end_pos in range(start_pos + 1, min(start_pos + 5000, len(qa_text) + 1)):
                    try:
                        candidate = json.loads(qa_text[start_pos:end_pos])
                        if isinstance(candidate, dict) and (
                            "status" in candidate or "verdict" in candidate or "summary" in candidate
                        ):
                            logger.info(f"{agent_name} QA parsed keys (brute force): {list(candidate.keys())}")
                            return candidate, False, None
                    except (json.JSONDecodeError, ValueError):
                        continue
            strategies_tried.append("brute_force_failed")
        except Exception as exc:
            strategies_tried.append(f"brute_force_exception({exc})")

        error_msg = f"All parsing strategies failed. Tried: {', '.join(strategies_tried)}"
        logger.error(
            f"{agent_name} QA parsing failed: {error_msg}. "
            f"Response preview: {qa_text[:500]}. Treating as needs_revision."
        )
        return {}, True, error_msg
