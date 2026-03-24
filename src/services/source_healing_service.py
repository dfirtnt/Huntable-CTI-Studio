"""Autonomous AI source healing service.

Gathers context about a failing source, probes its URLs, asks an LLM for a fix,
and applies the LLM's recommended actions directly to the source configuration.
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime

import httpx
from sqlalchemy import select

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import SourceCheckTable, SourceTable
from src.models.source import SourceUpdate
from src.services.llm_service import LLMService
from src.services.source_healing_config import SourceHealingConfig

logger = logging.getLogger(__name__)

# Fields the LLM is allowed to modify on a source
_MUTABLE_FIELDS = {"url", "rss_url", "config"}

_RETRY_DELAY_SECONDS = 30

SYSTEM_PROMPT = """\
You are an autonomous source-health repair agent for a Cyber Threat Intelligence (CTI) \
ingestion platform. A "source" is a website or RSS feed that the platform scrapes for \
threat intelligence articles.

You will receive:
1. The source's current configuration (name, URL, RSS URL, scraping config, active status).
2. Its recent error history (the last check records showing what failed and why).
3. Live HTTP probe results for its URL and RSS URL.

Your task: diagnose why the source is failing and propose concrete configuration changes \
to restore it to a working state.

RULES:
- Respond ONLY with a JSON object. No markdown fences, no commentary outside the JSON.
- Use this exact schema:
  {
    "diagnosis": "Brief explanation of the root cause",
    "actions": [
      {"field": "<field_name>", "value": <new_value>}
    ]
  }
- Valid field names: "url", "rss_url", "config".
- For "config", the value must be a JSON object that will be merged into the existing config.
- If the source URL redirects to a new location (shown in probe results), update "url" to \
the final redirect target.
- If the RSS feed URL is broken but the main URL works, try removing or updating "rss_url".
- Do NOT set the "active" field. Source activation/deactivation is an operator-only action.
- Do NOT fabricate URLs. Only use URLs observed in redirect chains from the probe results.
- If you cannot determine a fix, return {"diagnosis": "...", "actions": []}.
- Do NOT change the source name or identifier.
"""


class SourceHealingService:
    """Runs the full heal cycle for a single source: gather, probe, analyze, apply, log."""

    def __init__(self, config: SourceHealingConfig):
        self.config = config

    async def run(self, source_id: int) -> None:
        """Execute the healing pipeline for a source. All exceptions are caught and logged."""
        try:
            await self._run_inner(source_id)
        except Exception:
            logger.exception("[AutoHeal] Unexpected error healing source %s", source_id)

    async def _run_inner(self, source_id: int) -> None:
        db = AsyncDatabaseManager()

        # 1. Gather context (once — shared across rounds)
        source_snapshot = await self._get_source_snapshot(db, source_id)
        if source_snapshot is None:
            logger.warning("[AutoHeal] Source %s not found, skipping", source_id)
            return

        error_history = await self._get_error_history(db, source_id)
        previous_attempts: list[dict] = []

        for round_num in range(1, self.config.max_attempts + 1):
            logger.info(
                "[AutoHeal] Source '%s' (id=%s) — round %d/%d",
                source_snapshot.get("name", "?"), source_id,
                round_num, self.config.max_attempts,
            )

            # 2. Probe URLs (re-probe each round — state may have changed)
            probe_results = await self._probe_urls(source_snapshot)

            # 3. Ask LLM (include previous attempt context if retrying)
            proposed_actions = await self._analyze_with_llm(
                source_snapshot, error_history, probe_results,
                previous_attempts=previous_attempts,
            )

            # 4. Apply actions
            applied = await self._apply_actions(db, source_id, proposed_actions, source_snapshot)

            # 5. Validate
            fix_validated: bool | None = None
            if applied:
                fix_validated = await self._validate_fix(db, source_id)

            # 6. Record audit event
            from src.models.healing_event import HealingEventCreate

            event = HealingEventCreate(
                source_id=source_id,
                round_number=round_num,
                diagnosis=proposed_actions.get("diagnosis", "N/A") if isinstance(proposed_actions, dict) else "N/A",
                actions_proposed=proposed_actions.get("actions", []) if isinstance(proposed_actions, dict) else [],
                actions_applied=applied,
                validation_success=fix_validated,
            )
            await db.create_healing_event(event)

            # 7. Decide: stop or retry
            if fix_validated is True:
                logger.info("[AutoHeal] Source '%s' healed on round %d", source_snapshot.get("name", "?"), round_num)
                return

            if not applied:
                logger.info("[AutoHeal] No actions applied for source '%s', stopping", source_snapshot.get("name", "?"))
                break

            # Record this attempt for next round's LLM context
            previous_attempts.append({
                "round": round_num,
                "diagnosis": proposed_actions.get("diagnosis", "N/A") if isinstance(proposed_actions, dict) else "N/A",
                "actions_applied": applied,
                "validation_result": "FAIL" if fix_validated is False else "NO_CHANGE",
            })

            # Re-read source snapshot (it was modified by _apply_actions)
            source_snapshot = await self._get_source_snapshot(db, source_id)
            if source_snapshot is None:
                break

            # Wait before next round
            if round_num < self.config.max_attempts:
                await asyncio.sleep(_RETRY_DELAY_SECONDS)

        # All rounds exhausted — mark source as healing_exhausted
        logger.warning(
            "[AutoHeal] Source '%s' (id=%s) exhausted %d healing rounds",
            source_snapshot.get("name", "?") if source_snapshot else "?",
            source_id, self.config.max_attempts,
        )
        try:
            from src.models.source import SourceUpdate
            await db.update_source(source_id, SourceUpdate(healing_exhausted=True))
        except Exception:
            logger.exception("[AutoHeal] Failed to mark source %s as healing_exhausted", source_id)

    # ── Step 1: Gather context ──────────────────────────────────────────

    @staticmethod
    async def _get_source_snapshot(db: AsyncDatabaseManager, source_id: int) -> dict | None:
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(SourceTable).where(SourceTable.id == source_id)
                )
                src = result.scalar_one_or_none()
                if src is None:
                    return None
                return {
                    "id": src.id,
                    "identifier": src.identifier,
                    "name": src.name,
                    "url": src.url,
                    "rss_url": src.rss_url,
                    "active": src.active,
                    "config": src.config or {},
                    "consecutive_failures": src.consecutive_failures,
                    "last_check": src.last_check.isoformat() if src.last_check else None,
                    "last_success": src.last_success.isoformat() if src.last_success else None,
                }
        except Exception:
            logger.exception("[AutoHeal] Failed to load source snapshot for %s", source_id)
            return None

    @staticmethod
    async def _get_error_history(
        db: AsyncDatabaseManager, source_id: int, limit: int = 20
    ) -> list[dict]:
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(SourceCheckTable)
                    .where(SourceCheckTable.source_id == source_id)
                    .order_by(SourceCheckTable.check_time.desc())
                    .limit(limit)
                )
                checks = result.scalars().all()
                return [
                    {
                        "check_time": c.check_time.isoformat() if c.check_time else None,
                        "success": c.success,
                        "method": c.method,
                        "articles_found": c.articles_found,
                        "error_message": (c.error_message or "")[:300],
                    }
                    for c in checks
                ]
        except Exception:
            logger.exception("[AutoHeal] Failed to load error history for source %s", source_id)
            return []

    # ── Step 2: Probe URLs ──────────────────────────────────────────────

    @staticmethod
    async def _probe_urls(source_snapshot: dict) -> list[dict]:
        """Make live HTTP requests to the source's URLs to gather diagnostic info."""
        urls_to_probe = []
        if source_snapshot.get("url"):
            urls_to_probe.append(("url", source_snapshot["url"]))
        if source_snapshot.get("rss_url"):
            urls_to_probe.append(("rss_url", source_snapshot["rss_url"]))

        results = []
        for label, url in urls_to_probe:
            # Only probe http/https
            if not url.startswith(("http://", "https://")):
                results.append({"label": label, "url": url, "reachable": False, "error": "Invalid scheme"})
                continue

            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(10.0),
                    follow_redirects=True,
                    max_redirects=5,
                ) as client:
                    resp = await client.get(url, headers={"User-Agent": "HuntableCTI-HealthCheck/1.0"})
                    final_url = str(resp.url)
                    results.append({
                        "label": label,
                        "url": url,
                        "reachable": True,
                        "status_code": resp.status_code,
                        "final_url": final_url if final_url != url else None,
                        "content_type": resp.headers.get("content-type", ""),
                    })
            except Exception as e:
                results.append({
                    "label": label,
                    "url": url,
                    "reachable": False,
                    "error": str(e)[:200],
                })

        return results

    # ── Step 3: LLM analysis ───────────────────────────────────────────

    async def _analyze_with_llm(
        self, source_snapshot: dict, error_history: list[dict], probe_results: list[dict],
        previous_attempts: list[dict] | None = None,
    ) -> dict:
        """Call the configured LLM to diagnose and propose fixes."""
        user_message = self._build_user_prompt(source_snapshot, error_history, probe_results, previous_attempts)

        try:
            llm = LLMService()
        except Exception:
            logger.exception(
                "[AutoHeal] Failed to initialize LLMService for source %s — "
                "check provider settings and API keys",
                source_snapshot.get("id"),
            )
            return {"diagnosis": "LLM service initialization failed", "actions": []}

        # Override API key if a dedicated one is configured
        if self.config.api_key:
            provider = llm._canonicalize_provider(self.config.provider)
            if provider == "openai":
                llm.openai_api_key = self.config.api_key
            elif provider == "anthropic":
                llm.anthropic_api_key = self.config.api_key
            else:
                logger.warning(
                    "[AutoHeal] Dedicated API key configured but provider '%s' "
                    "does not support key override — using default key",
                    self.config.provider,
                )

        from src.utils.langfuse_client import trace_llm_call, log_llm_completion

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        try:
            with trace_llm_call(
                name="source_healing",
                model=self.config.model,
                session_id=f"healing_source_{source_snapshot.get('id')}",
                metadata={
                    "source_id": source_snapshot.get("id"),
                    "source_name": source_snapshot.get("name"),
                    "messages": messages,
                },
            ) as generation:
                response = await llm.request_chat(
                    provider=self.config.provider,
                    model_name=self.config.model,
                    messages=messages,
                    max_tokens=1024,
                    temperature=0.0,
                    timeout=45.0,
                    failure_context="SourceHealingAgent",
                )

                content = response.get("content", "")
                result = self._parse_llm_response(content)

                log_llm_completion(generation, messages, content)
                return result

        except Exception:
            logger.exception("[AutoHeal] LLM call failed for source %s", source_snapshot.get("id"))
            return {"diagnosis": "LLM call failed", "actions": []}

    @staticmethod
    def _build_user_prompt(
        source_snapshot: dict, error_history: list[dict], probe_results: list[dict],
        previous_attempts: list[dict] | None = None,
    ) -> str:
        parts = [
            "## Source Configuration",
            json.dumps(
                {k: v for k, v in source_snapshot.items() if k != "id"},
                indent=2,
                default=str,
            ),
            "",
            "## Recent Check History (newest first)",
        ]
        if error_history:
            for check in error_history:
                status = "OK" if check["success"] else "FAIL"
                parts.append(
                    f"- [{status}] {check['check_time']} method={check['method']} "
                    f"articles={check['articles_found']} error={check['error_message'] or 'none'}"
                )
        else:
            parts.append("No check history available.")

        parts.append("")
        parts.append("## Live URL Probe Results")
        for probe in probe_results:
            if probe.get("reachable"):
                redirect_note = f" → redirected to {probe['final_url']}" if probe.get("final_url") else ""
                parts.append(
                    f"- {probe['label']}: HTTP {probe['status_code']} "
                    f"({probe.get('content_type', 'unknown')}){redirect_note}"
                )
            else:
                parts.append(f"- {probe['label']}: UNREACHABLE — {probe.get('error', 'unknown error')}")

        if not probe_results:
            parts.append("No URLs to probe.")

        if previous_attempts:
            parts.append("")
            parts.append("## Previous Healing Attempts (this session)")
            for attempt in previous_attempts:
                parts.append(
                    f"- Round {attempt['round']}: diagnosis=\"{attempt['diagnosis']}\" "
                    f"actions={json.dumps(attempt['actions_applied'])} "
                    f"result={attempt['validation_result']}"
                )
            parts.append("")
            parts.append(
                "Your previous fix did not work. Propose a DIFFERENT approach. "
                "Do not repeat the same actions."
            )

        parts.append("")
        parts.append("Diagnose the issue and propose actions to fix this source.")
        return "\n".join(parts)

    @staticmethod
    def _parse_llm_response(content: str) -> dict:
        """Parse the LLM response as JSON, stripping markdown fences if present."""
        if not content or not content.strip():
            return {"diagnosis": "Empty LLM response", "actions": []}

        # Strip markdown code fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", content.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "actions" in parsed:
                return parsed
            return {"diagnosis": "Unexpected response format", "actions": []}
        except json.JSONDecodeError:
            logger.warning("[AutoHeal] Failed to parse LLM response as JSON: %.200s", content)
            return {"diagnosis": "Failed to parse LLM response", "actions": []}

    # ── Step 4: Apply actions ──────────────────────────────────────────

    @staticmethod
    async def _apply_actions(
        db: AsyncDatabaseManager, source_id: int, analysis: dict, source_snapshot: dict
    ) -> list[dict]:
        """Apply LLM-proposed actions to the source. Returns list of applied actions."""
        actions = analysis.get("actions", [])
        if not actions:
            return []

        applied = []
        for action in actions:
            field = action.get("field")
            value = action.get("value")

            if field not in _MUTABLE_FIELDS:
                logger.warning("[AutoHeal] Skipping disallowed field '%s' for source %s", field, source_id)
                continue

            try:
                update_kwargs = {}
                if field == "config" and isinstance(value, dict):
                    # Merge LLM-proposed config over existing config to preserve existing keys
                    from src.models.source import SourceConfig

                    existing_config = source_snapshot.get("config") or {}
                    merged = {**existing_config, **value}
                    update_kwargs["config"] = SourceConfig(**merged)
                elif field in ("url", "rss_url") and isinstance(value, str):
                    if not value.startswith(("http://", "https://")):
                        logger.warning("[AutoHeal] Skipping invalid URL for field '%s': %s", field, value)
                        continue
                    update_kwargs[field] = value
                else:
                    logger.warning(
                        "[AutoHeal] Skipping action with unexpected type: field=%s value=%s",
                        field,
                        type(value).__name__,
                    )
                    continue

                update_data = SourceUpdate(**update_kwargs)
                result = await db.update_source(source_id, update_data)
                if result:
                    applied.append({"field": field, "value": value})
                    logger.info("[AutoHeal] Applied: source %s — set %s = %s", source_id, field, value)
                else:
                    logger.warning("[AutoHeal] update_source returned None for source %s", source_id)

            except Exception:
                logger.exception("[AutoHeal] Failed to apply action field=%s for source %s", field, source_id)

        return applied

    # ── Step 5: Validate fix ───────────────────────────────────────────

    @staticmethod
    async def _validate_fix(db: AsyncDatabaseManager, source_id: int) -> bool:
        """
        Attempt a real fetch of the (now-updated) source to confirm the fix worked.

        On success, calls update_source_health(success=True) which resets consecutive_failures,
        healing_attempts, and healing_exhausted. On failure, leaves the counters as-is so the
        next scheduled healing scan can retry.
        """
        from src.core.fetcher import ContentFetcher

        try:
            source = await db.get_source(source_id)
            if source is None:
                logger.warning("[AutoHeal] Validation skipped — source %s not found after applying fix", source_id)
                return False

            start_time = time.monotonic()
            async with ContentFetcher() as fetcher:
                fetch_result = await fetcher.fetch_source(source)

            response_time = time.monotonic() - start_time
            success = bool(fetch_result and fetch_result.success)

            if success:
                logger.info(
                    "[AutoHeal] Validation PASSED for source '%s' (id=%s) — resetting failure counters",
                    source.name,
                    source_id,
                )
                await db.update_source_health(source_id, True, response_time)
            else:
                error = getattr(fetch_result, "error", "unknown") if fetch_result else "no result"
                logger.warning(
                    "[AutoHeal] Validation FAILED for source '%s' (id=%s) — %s",
                    source.name,
                    source_id,
                    error,
                )

            return success

        except Exception:
            logger.exception("[AutoHeal] Validation fetch raised an exception for source %s", source_id)
            return False
