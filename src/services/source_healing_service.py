"""Autonomous AI source healing service.

Gathers context about a failing source, probes its URLs, asks an LLM for a fix,
and applies the LLM's recommended actions directly to the source configuration.
"""

import asyncio
import json
import logging
import re
import time

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
2. Its recent error history (the last check records showing what failed and why — including \
any "[AutoHeal validation]" entries from previous healing attempts).
3. Deep diagnostic probe results — not just HTTP status, but:
   - RSS feed content analysis (item count, sample titles — an RSS returning HTTP 200 with \
zero items is an empty feed, not a working feed)
   - Sitemap discovery (available sitemaps and sample post URLs with their actual URL patterns)
   - WordPress JSON API availability check
   - Blog page content analysis (visible text length, whether the page is JS-rendered)
   - Sample blog post links found on the listing page
4. Configurations from similar WORKING sources as reference examples.
5. (On retries) Previous healing attempts WITH validation fetch logs.

DIAGNOSTIC PLAYBOOK — follow this order:
1. Check if RSS has items. If RSS returns 200 but 0 items → the feed is EMPTY, not working. \
Set rss_url to null to force fallback to scraping tiers.
2. If blog page text is very short (<500 chars) but HTML is large → page is JS-rendered. \
Set "use_playwright": true in config.
3. Check RSS sample_urls (if RSS is available) to learn the ACTUAL URL pattern of articles. \
If RSS sample URLs show "/research/" paths, use that in post_url_regex — do NOT guess \
"/threat-research/" or other patterns. Use only what you observe in sample_urls.
4. Check sitemap sample URLs to learn the ACTUAL URL pattern before writing post_url_regex. \
Never guess URL patterns — use what you observe in the probe data.
5. For WordPress sites, check if wp-json API returns content. If it returns posts with \
content, configure wp_json discovery (endpoints + url_field_priority).
6. If the blog page has post links visible, use a listing discovery strategy with the \
appropriate CSS selector.
7. Look at the working source examples to see what configs succeed for similar site types.

PLATFORM CAPABILITIES:
- Fetch tiers: RSS → Playwright (if use_playwright=true) → Modern scraping → Legacy scraping
- Discovery strategies: "listing" (CSS selector on listing page), "sitemap" (XML sitemap), \
"wp_json" (WordPress REST API). Strategies can be bare strings like "sitemap" or dicts \
like {"sitemap": {"urls": [...]}}.
- wp_json config: {"endpoints": ["https://example.com/wp-json/wp/v2/posts?per_page=50"], \
"url_field_priority": ["link", "guid.rendered"]}
- Setting rss_url to null skips the RSS tier entirely.
- Setting "use_playwright": true enables headless browser rendering for JS-heavy sites.
- If RSS is reachable but returns zero articles, the fetcher will fall through to the next \
tier automatically.

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
- If the RSS feed URL is broken but the main URL works, set "rss_url" to null.
- Do NOT set the "active" field. Source activation/deactivation is an operator-only action.
- Do NOT fabricate URLs. Only use URLs observed in the probe results or sitemap samples.
- If you cannot determine a fix, return {"diagnosis": "...", "actions": []}.
- Do NOT change the source name or identifier.
- If 3+ rounds have failed with the same fundamental outcome, report a platform limitation \
rather than trying more config permutations.
"""


class SourceHealingService:
    """Runs the full heal cycle for a single source: gather, probe, analyze, apply, log."""

    def __init__(self, config: SourceHealingConfig):
        self.config = config

    async def run(self, source_id: int) -> None:
        """Execute the healing pipeline for a source. All exceptions are caught and logged."""
        try:
            # Reload Langfuse client from AppSettings so Celery workers match Settings UI (not a stale env-only client).
            from src.utils.langfuse_client import reset_langfuse_client

            reset_langfuse_client()
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
        working_examples = await self._get_working_source_examples(db, source_id)
        previous_attempts: list[dict] = []

        for round_num in range(1, self.config.max_attempts + 1):
            logger.info(
                "[AutoHeal] Source '%s' (id=%s) — round %d/%d",
                source_snapshot.get("name", "?"),
                source_id,
                round_num,
                self.config.max_attempts,
            )

            # 2. Deep diagnostic probe (re-probe each round — state may have changed)
            probe_results = await self._probe_urls(source_snapshot)

            # 3. Ask LLM (include previous attempt context if retrying)
            proposed_actions = await self._analyze_with_llm(
                source_snapshot,
                error_history,
                probe_results,
                previous_attempts=previous_attempts,
                working_examples=working_examples,
            )

            # 4. Apply actions
            applied = await self._apply_actions(db, source_id, proposed_actions, source_snapshot)

            # 5. Validate
            validation: dict | None = None
            fix_validated: bool | None = None
            if applied:
                validation = await self._validate_fix(db, source_id)
                fix_validated = validation.get("success")

            # 6. Record audit event (include validation details in error_message)
            from src.models.healing_event import HealingEventCreate

            validation_summary = None
            if validation is not None:
                parts = []
                parts.append(f"method={validation.get('method', '?')}")
                parts.append(f"articles_found={validation.get('articles_found', 0)}")
                parts.append(f"response_time={validation.get('response_time', '?')}s")
                if validation.get("error"):
                    parts.append(f"error={validation['error']}")
                if validation.get("rss_parsing_stats"):
                    parts.append(f"rss_stats={json.dumps(validation['rss_parsing_stats'])}")
                validation_summary = " | ".join(parts)

            event_error_message = validation_summary
            if event_error_message is None and isinstance(proposed_actions, dict):
                raw_detail = proposed_actions.get("error_detail") or ""
                # Truncate and strip potential secrets from exception strings
                event_error_message = raw_detail[:500] if raw_detail else None

            event = HealingEventCreate(
                source_id=source_id,
                round_number=round_num,
                diagnosis=proposed_actions.get("diagnosis", "N/A") if isinstance(proposed_actions, dict) else "N/A",
                actions_proposed=proposed_actions.get("actions", []) if isinstance(proposed_actions, dict) else [],
                actions_applied=applied,
                validation_success=fix_validated,
                error_message=event_error_message,
            )
            await db.create_healing_event(event)

            # 7. Decide: stop or retry
            if fix_validated is True:
                logger.info("[AutoHeal] Source '%s' healed on round %d", source_snapshot.get("name", "?"), round_num)
                return

            if not applied:
                logger.info("[AutoHeal] No actions applied for source '%s', stopping", source_snapshot.get("name", "?"))
                break

            # Record this attempt for next round's LLM context (with validation details)
            attempt_record = {
                "round": round_num,
                "diagnosis": proposed_actions.get("diagnosis", "N/A") if isinstance(proposed_actions, dict) else "N/A",
                "actions_applied": applied,
                "validation_result": "FAIL" if fix_validated is False else "NO_CHANGE",
            }
            if validation is not None:
                attempt_record["validation_details"] = {
                    "method": validation.get("method"),
                    "articles_found": validation.get("articles_found", 0),
                    "error": validation.get("error"),
                    "rss_parsing_stats": validation.get("rss_parsing_stats"),
                }
            previous_attempts.append(attempt_record)

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
            source_id,
            self.config.max_attempts,
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
                result = await session.execute(select(SourceTable).where(SourceTable.id == source_id))
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
    async def _get_error_history(db: AsyncDatabaseManager, source_id: int, limit: int = 20) -> list[dict]:
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

    # ── Step 2: Deep diagnostic probe ────────────────────────────────────

    @staticmethod
    async def _probe_urls(source_snapshot: dict) -> list[dict]:
        """Run deep diagnostic probes: HTTP checks, RSS content inspection,
        sitemap discovery, WP JSON detection, and JS-rendering detection."""
        import re as _re

        _UA = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        results: list[dict] = []

        async def _fetch(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
            try:
                return await client.get(url, headers={"User-Agent": _UA})
            except Exception as exc:
                logger.debug("[AutoHeal-probe] fetch %s failed: %s", url, exc)
                return None

        source_url = source_snapshot.get("url", "")
        rss_url = source_snapshot.get("rss_url", "")
        base_domain = ""
        if source_url:
            from urllib.parse import urlparse

            parsed = urlparse(source_url)
            base_domain = f"{parsed.scheme}://{parsed.netloc}"

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            # ── 1. Basic HTTP probe for url and rss_url ──
            for label, url in [("url", source_url), ("rss_url", rss_url)]:
                if not url or not url.startswith(("http://", "https://")):
                    if url:
                        results.append({"label": label, "url": url, "reachable": False, "error": "Invalid scheme"})
                    continue
                resp = await _fetch(client, url)
                if resp is None:
                    results.append({"label": label, "url": url, "reachable": False, "error": "Connection failed"})
                else:
                    final_url = str(resp.url)
                    probe_result = {
                        "label": label,
                        "url": url,
                        "reachable": True,
                        "status_code": resp.status_code,
                        "final_url": final_url if final_url != url else None,
                        "content_type": resp.headers.get("content-type", ""),
                    }

                    # Check for bot protection (CloudFront, Akamai, etc.)
                    if resp.status_code == 403:
                        body_lower = resp.text[:5000].lower()
                        server_header = resp.headers.get("server", "").lower()
                        cf_id = resp.headers.get("x-amz-cf-id")

                        bot_protection_provider = None
                        if "cloudfront" in body_lower or "cloudfront" in server_header or cf_id:
                            bot_protection_provider = "CloudFront"
                        elif "akamai" in body_lower or "akamai" in server_header:
                            bot_protection_provider = "Akamai"
                        elif any(
                            phrase in body_lower for phrase in ["request blocked", "access denied", "bot protection"]
                        ):
                            bot_protection_provider = "Unknown WAF"

                        if bot_protection_provider:
                            probe_result["bot_protection_detected"] = True
                            probe_result["bot_protection_provider"] = bot_protection_provider
                            # Add dedicated result for easy detection
                            results.append(
                                {
                                    "label": "bot_protection_detected",
                                    "url": url,
                                    "provider": bot_protection_provider,
                                    "status_code": 403,
                                    "message": f"Site uses {bot_protection_provider} bot protection that blocks automated requests",
                                }
                            )

                    results.append(probe_result)

            # ── 2. RSS content inspection ──
            if rss_url and rss_url.startswith(("http://", "https://")):
                resp = await _fetch(client, rss_url)
                rss_info: dict = {"label": "rss_content_analysis"}
                if resp and resp.status_code == 200:
                    body = resp.text[:50_000]
                    items = _re.findall(r"<item[\s>]", body, _re.IGNORECASE)
                    entries = _re.findall(r"<entry[\s>]", body, _re.IGNORECASE)
                    count = len(items) + len(entries)
                    titles = _re.findall(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", body)
                    # Extract URLs from <link> tags (RSS) and <link href="..."> (Atom)
                    rss_links = _re.findall(r"<link[^>]*>([^<]+)</link>", body, _re.IGNORECASE)
                    atom_links = _re.findall(r'<link[^>]+href="([^"]+)"', body, _re.IGNORECASE)
                    all_links = rss_links + atom_links
                    rss_info["item_count"] = count
                    rss_info["sample_titles"] = [t.strip() for t in titles[1:4]]  # skip channel title
                    rss_info["sample_urls"] = [link.strip() for link in all_links[:5]]  # first 5 article URLs
                    rss_info["verdict"] = "has_items" if count > 0 else "EMPTY_FEED"
                elif resp:
                    rss_info["verdict"] = f"HTTP_{resp.status_code}"
                else:
                    rss_info["verdict"] = "unreachable"
                results.append(rss_info)

            # ── 3. Blog page content analysis (JS-rendering detection) ──
            if source_url and source_url.startswith(("http://", "https://")):
                resp = await _fetch(client, source_url)
                page_info: dict = {"label": "blog_page_analysis"}
                if resp and resp.status_code == 200:
                    body = resp.text
                    page_info["html_length"] = len(body)
                    # Strip tags to measure visible text
                    clean = _re.sub(r"<script[^>]*>.*?</script>", "", body, flags=_re.DOTALL)
                    clean = _re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=_re.DOTALL)
                    clean = _re.sub(r"<[^>]+>", " ", clean)
                    clean = _re.sub(r"\s+", " ", clean).strip()
                    page_info["visible_text_length"] = len(clean)
                    page_info["is_likely_js_rendered"] = len(clean) < 500 and len(body) > 10_000

                    # Extract blog post links from the page
                    href_pattern = _re.compile(r'href="([^"]+)"')
                    all_hrefs = href_pattern.findall(body)
                    # Heuristic: blog post links usually contain the source domain + /blog/ or similar
                    from urllib.parse import urljoin

                    post_links = set()
                    for href in all_hrefs:
                        full = urljoin(source_url, href)
                        # Skip the listing page itself, anchors, assets
                        if full == source_url or full.rstrip("/") == source_url.rstrip("/"):
                            continue
                        if any(x in full for x in [".png", ".jpg", ".css", ".js", ".xml", ".ico"]):
                            continue
                        if full.startswith(source_url.rstrip("/") + "/") and full.count("/") > source_url.count("/"):
                            post_links.add(full)
                    page_info["post_links_found"] = len(post_links)
                    page_info["sample_post_links"] = sorted(post_links)[:5]
                elif resp:
                    page_info["status_code"] = resp.status_code
                else:
                    page_info["error"] = "unreachable"
                results.append(page_info)

            # ── 4. Sitemap discovery ──
            sitemap_info: dict = {"label": "sitemap_discovery"}
            sitemap_urls_to_try = []
            if base_domain:
                sitemap_urls_to_try = [
                    f"{base_domain}/sitemap.xml",
                    f"{base_domain}/sitemap_index.xml",
                ]
            for sm_url in sitemap_urls_to_try:
                resp = await _fetch(client, sm_url)
                if resp and resp.status_code == 200 and "<loc>" in resp.text.lower():
                    # Found a sitemap — extract sub-sitemaps or post URLs
                    locs = _re.findall(r"<loc>(.*?)</loc>", resp.text)
                    # Look for a post/blog-specific sitemap
                    post_sitemaps = [loc for loc in locs if any(k in loc.lower() for k in ["post", "blog", "article"])]
                    sitemap_info["sitemap_url"] = sm_url
                    sitemap_info["total_locs"] = len(locs)
                    sitemap_info["post_sitemaps"] = post_sitemaps[:5]

                    # If we found a post-specific sitemap, sample its URLs
                    if post_sitemaps:
                        psm_resp = await _fetch(client, post_sitemaps[0])
                        if psm_resp and psm_resp.status_code == 200:
                            post_urls = _re.findall(r"<loc>(.*?)</loc>", psm_resp.text)
                            sitemap_info["post_sitemap_sample"] = post_urls[:5]
                            sitemap_info["post_sitemap_total"] = len(post_urls)
                    elif locs:
                        sitemap_info["sample_locs"] = locs[:5]
                    break
            else:
                sitemap_info["verdict"] = "no_sitemap_found"
            results.append(sitemap_info)

            # ── 5. WordPress JSON API check ──
            wp_info: dict = {"label": "wp_json_api_check"}
            if base_domain:
                for wp_path in ["/wp-json/wp/v2/posts?per_page=3", "/wp-json/wp/v2/blog_post?per_page=3"]:
                    wp_url = base_domain + wp_path
                    resp = await _fetch(client, wp_url)
                    if resp and resp.status_code == 200:
                        try:
                            import json as _json

                            posts = _json.loads(resp.text)
                            if isinstance(posts, list) and posts:
                                has_content = any(
                                    len(p.get("content", {}).get("rendered", "") or "") > 100 for p in posts[:3]
                                )
                                wp_info["endpoint"] = wp_url
                                wp_info["post_count_sample"] = len(posts)
                                wp_info["has_content"] = has_content
                                wp_info["sample_posts"] = [
                                    {
                                        "title": (p.get("title", {}).get("rendered", ""))[:80],
                                        "link": p.get("link", ""),
                                        "date": p.get("date", ""),
                                        "content_length": len(p.get("content", {}).get("rendered", "") or ""),
                                    }
                                    for p in posts[:3]
                                ]
                                break
                        except Exception:
                            pass
                if "endpoint" not in wp_info:
                    wp_info["verdict"] = "not_available"
            results.append(wp_info)

        return results

    @staticmethod
    async def _get_working_source_examples(
        db: "AsyncDatabaseManager",
        source_id: int,
        limit: int = 3,
    ) -> list[dict]:
        """Return configs from similar working sources as reference examples."""
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(SourceTable)
                    .where(SourceTable.active == True)  # noqa: E712
                    .where(SourceTable.consecutive_failures == 0)
                    .where(SourceTable.id != source_id)
                    .where(SourceTable.total_articles > 0)
                    .order_by(SourceTable.total_articles.desc())
                    .limit(limit)
                )
                sources = result.scalars().all()
                return [
                    {
                        "name": s.name,
                        "url": s.url,
                        "rss_url": s.rss_url,
                        "config": s.config or {},
                        "total_articles": s.total_articles,
                    }
                    for s in sources
                ]
        except Exception:
            logger.exception("[AutoHeal] Failed to load working source examples")
            return []

    # ── Step 3: LLM analysis ───────────────────────────────────────────

    async def _analyze_with_llm(
        self,
        source_snapshot: dict,
        error_history: list[dict],
        probe_results: list[dict],
        previous_attempts: list[dict] | None = None,
        working_examples: list[dict] | None = None,
    ) -> dict:
        """Call the configured LLM to diagnose and propose fixes."""

        # Check for bot protection detection - skip LLM if detected
        bot_protection_result = next(
            (r for r in probe_results if r.get("label") == "bot_protection_detected"),
            None,
        )
        if bot_protection_result:
            provider = bot_protection_result.get("provider", "Unknown")
            return {
                "diagnosis": f"BLOCKED: Site uses {provider} bot protection that blocks automated requests. "
                f"Auto-healing cannot bypass bot protection systems. Manual configuration or browser automation required.",
                "actions": [],
                "platform_limitation": "bot_protection",
            }

        user_message = self._build_user_prompt(
            source_snapshot,
            error_history,
            probe_results,
            previous_attempts,
            working_examples,
        )

        try:
            llm = LLMService()
        except Exception:
            logger.exception(
                "[AutoHeal] Failed to initialize LLMService for source %s — check provider settings and API keys",
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
                logger.warning(  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                    "[AutoHeal] Dedicated API key configured but provider '%s' "
                    "does not support key override — using default key",
                    self.config.provider,
                )

        from src.utils.langfuse_client import (
            get_langfuse_setting,
            log_llm_completion,
            trace_llm_call,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        lf_host = get_langfuse_setting("LANGFUSE_HOST", "LANGFUSE_HOST", "https://cloud.langfuse.com")
        lf_project_id = get_langfuse_setting("LANGFUSE_PROJECT_ID", "LANGFUSE_PROJECT_ID")

        try:
            with trace_llm_call(
                name="source_healing",
                model=self.config.model,
                session_id=f"healing_source_{source_snapshot.get('id')}",
                metadata={
                    "source_id": source_snapshot.get("id"),
                    "source_name": source_snapshot.get("name"),
                    "messages": messages,
                    "langfuse_host": lf_host,
                    "langfuse_project_id": lf_project_id,
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

                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not (content and str(content).strip()):
                    stop = response.get("stop_reason")
                    logger.warning(
                        "[AutoHeal] Empty LLM content for source %s provider=%s model=%s stop_reason=%s "
                        "response_keys=%s",
                        source_snapshot.get("id"),
                        self.config.provider,
                        self.config.model,
                        stop,
                        list(response.keys()) if isinstance(response, dict) else type(response).__name__,
                    )

                result = self._parse_llm_response(content if content is not None else "")

                # Retry once if JSON parsing failed
                if result.get("diagnosis") == "Failed to parse LLM response":
                    logger.warning(
                        "[AutoHeal] JSON parse failed for source %s -- retrying with clarification prompt",
                        source_snapshot.get("id"),
                    )

                    retry_messages = messages + [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": (
                                "Your previous response could not be parsed as valid JSON. "
                                "Please respond with ONLY valid JSON in this exact format:\n\n"
                                '{"diagnosis": "brief description of the problem", '
                                '"actions": [{"field": "rss_url", "value": null}, '
                                '{"field": "config", "value": {...}}]}\n\n'
                                "Do not include any explanatory text outside the JSON structure. "
                                "Do not use markdown code fences."
                            ),
                        },
                    ]

                    try:
                        retry_response = await llm.request_chat(
                            provider=self.config.provider,
                            model_name=self.config.model,
                            messages=retry_messages,
                            max_tokens=1024,
                            temperature=0.0,
                            timeout=45.0,
                            failure_context="SourceHealingAgent_Retry",
                        )

                        retry_content = retry_response.get("choices", [{}])[0].get("message", {}).get("content", "")
                        result = self._parse_llm_response(retry_content if retry_content else "")
                        log_llm_completion(generation, retry_messages, retry_content)
                    except Exception as retry_exc:
                        logger.warning(
                            "[AutoHeal] Retry failed for source %s: %s", source_snapshot.get("id"), retry_exc
                        )

                if result.get("diagnosis") == "Empty LLM response":
                    sr = response.get("stop_reason")
                    if isinstance(sr, str) and sr:
                        result["diagnosis"] = f"Empty LLM response (stop_reason={sr})"
                elif result.get("diagnosis") != "Failed to parse LLM response":
                    log_llm_completion(generation, messages, content)

                return result

        except httpx.HTTPStatusError as exc:
            sc = exc.response.status_code if exc.response is not None else None
            logger.exception(
                "[AutoHeal] LLM HTTP error for source %s status=%s",
                source_snapshot.get("id"),
                sc,
            )
            return {
                "diagnosis": f"LLM HTTP error ({sc})",
                "actions": [],
                "error_detail": str(exc) or f"HTTPStatusError ({sc})",
            }
        except httpx.TimeoutException as exc:
            logger.exception("[AutoHeal] LLM timeout for source %s", source_snapshot.get("id"))
            return {
                "diagnosis": "LLM request timed out",
                "actions": [],
                "error_detail": str(exc) or exc.__class__.__name__,
            }
        except Exception as exc:
            logger.exception("[AutoHeal] LLM call failed for source %s", source_snapshot.get("id"))
            detail = str(exc).strip() or exc.__class__.__name__
            return {
                "diagnosis": f"LLM call failed: {exc.__class__.__name__}",
                "actions": [],
                "error_detail": detail,
            }

    @staticmethod
    def _build_user_prompt(
        source_snapshot: dict,
        error_history: list[dict],
        probe_results: list[dict],
        previous_attempts: list[dict] | None = None,
        working_examples: list[dict] | None = None,
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

        # ── Render deep diagnostic probes ──
        parts.append("")
        parts.append("## Deep Diagnostic Probe Results")

        for probe in probe_results:
            label = probe.get("label", "unknown")

            if label in ("url", "rss_url"):
                if probe.get("reachable"):
                    redirect_note = f" → redirected to {probe['final_url']}" if probe.get("final_url") else ""
                    parts.append(
                        f"- {label}: HTTP {probe['status_code']} "
                        f"({probe.get('content_type', 'unknown')}){redirect_note}"
                    )
                else:
                    parts.append(f"- {label}: UNREACHABLE — {probe.get('error', 'unknown error')}")

            elif label == "rss_content_analysis":
                verdict = probe.get("verdict", "?")
                parts.append(f"- RSS Feed Content: {verdict}")
                if probe.get("item_count") is not None:
                    parts.append(f"  Items in feed: {probe['item_count']}")
                if probe.get("sample_titles"):
                    parts.append(f"  Sample titles: {probe['sample_titles']}")
                if probe.get("sample_urls"):
                    parts.append(f"  Sample article URLs: {probe['sample_urls']}")

            elif label == "blog_page_analysis":
                parts.append("- Blog Page Analysis:")
                if "html_length" in probe:
                    parts.append(f"  HTML size: {probe['html_length']} chars")
                    parts.append(f"  Visible text: {probe['visible_text_length']} chars")
                    parts.append(f"  Likely JS-rendered: {probe.get('is_likely_js_rendered', False)}")
                if probe.get("post_links_found", 0) > 0:
                    parts.append(f"  Post links found on page: {probe['post_links_found']}")
                    parts.append(f"  Sample post links: {json.dumps(probe.get('sample_post_links', []))}")
                elif "status_code" in probe:
                    parts.append(f"  HTTP status: {probe['status_code']}")
                elif "error" in probe:
                    parts.append(f"  Error: {probe['error']}")

            elif label == "sitemap_discovery":
                if probe.get("sitemap_url"):
                    parts.append(f"- Sitemap found: {probe['sitemap_url']}")
                    parts.append(f"  Total URLs: {probe.get('total_locs', '?')}")
                    if probe.get("post_sitemaps"):
                        parts.append(f"  Post-specific sitemaps: {json.dumps(probe['post_sitemaps'])}")
                    if probe.get("post_sitemap_sample"):
                        parts.append(f"  Post sitemap URL count: {probe.get('post_sitemap_total', '?')}")
                        parts.append(f"  Sample post URLs: {json.dumps(probe['post_sitemap_sample'])}")
                    elif probe.get("sample_locs"):
                        parts.append(f"  Sample URLs: {json.dumps(probe['sample_locs'])}")
                else:
                    parts.append(f"- Sitemap: {probe.get('verdict', 'not found')}")

            elif label == "wp_json_api_check":
                if probe.get("endpoint"):
                    parts.append(f"- WordPress JSON API: AVAILABLE at {probe['endpoint']}")
                    parts.append(f"  Sample posts: {probe.get('post_count_sample', '?')}")
                    parts.append(f"  Has rendered content: {probe.get('has_content', False)}")
                    if probe.get("sample_posts"):
                        for sp in probe["sample_posts"]:
                            parts.append(
                                f'    - "{sp.get("title", "?")}" → {sp.get("link", "?")} '
                                f"(date={sp.get('date', '?')}, content={sp.get('content_length', 0)} chars)"
                            )
                else:
                    parts.append(f"- WordPress JSON API: {probe.get('verdict', 'not available')}")

        if not probe_results:
            parts.append("No probe results available.")

        # ── Working source examples ──
        if working_examples:
            parts.append("")
            parts.append("## Working Source Examples (for reference)")
            parts.append("These sources are currently healthy and collecting articles successfully:")
            for ex in working_examples:
                parts.append(f"### {ex['name']} ({ex.get('total_articles', '?')} articles)")
                parts.append(f"URL: {ex.get('url', '?')}")
                if ex.get("rss_url"):
                    parts.append(f"RSS: {ex['rss_url']}")
                parts.append(f"Config: {json.dumps(ex.get('config', {}), indent=2, default=str)}")
                parts.append("")

        if previous_attempts:
            parts.append("")
            parts.append("## Previous Healing Attempts (this session)")
            for attempt in previous_attempts:
                parts.append(f"### Round {attempt['round']} — {attempt['validation_result']}")
                parts.append(f"Diagnosis: {attempt['diagnosis']}")
                parts.append(f"Actions applied: {json.dumps(attempt['actions_applied'])}")

                vd = attempt.get("validation_details")
                if vd:
                    parts.append("Validation fetch results:")
                    parts.append(f"  - Fetch method used: {vd.get('method', 'unknown')}")
                    parts.append(f"  - Articles extracted: {vd.get('articles_found', 0)}")
                    if vd.get("error"):
                        parts.append(f"  - Error: {vd['error']}")
                    if vd.get("rss_parsing_stats"):
                        parts.append(f"  - RSS parsing stats: {json.dumps(vd['rss_parsing_stats'])}")
                else:
                    parts.append("Validation fetch results: not available")
                parts.append("")

            parts.append(
                "Your previous fix did not work. The validation fetch logs above show exactly "
                "what happened when the platform tried to collect with your config changes. "
                "Analyze those logs carefully and propose a DIFFERENT approach. "
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
    async def _validate_fix(db: AsyncDatabaseManager, source_id: int) -> dict:
        """
        Attempt a real fetch of the (now-updated) source to confirm the fix worked.

        Returns a dict with ``success`` (bool), ``error`` (str | None), ``method``,
        ``articles_found``, ``response_time``, and ``rss_parsing_stats`` so callers
        (and subsequent LLM rounds) can see exactly what happened.

        On success, calls update_source_health(success=True) which resets
        consecutive_failures, healing_attempts, and healing_exhausted.
        """
        from src.core.fetcher import ContentFetcher

        fail_result: dict = {
            "success": False,
            "error": None,
            "method": "unknown",
            "articles_found": 0,
            "response_time": 0.0,
            "rss_parsing_stats": {},
        }

        try:
            source = await db.get_source(source_id)
            if source is None:
                logger.warning("[AutoHeal] Validation skipped — source %s not found after applying fix", source_id)
                fail_result["error"] = "Source not found after applying fix"
                return fail_result

            start_time = time.monotonic()
            async with ContentFetcher() as fetcher:
                fetch_result = await fetcher.fetch_source(source)

            response_time = time.monotonic() - start_time
            success = bool(fetch_result and fetch_result.success)

            method = fetch_result.method if fetch_result else "unknown"
            articles_found = len(fetch_result.articles) if fetch_result and fetch_result.articles else 0
            error_msg = (fetch_result.error if fetch_result and not fetch_result.success else None) or None
            rss_stats = fetch_result.rss_parsing_stats if fetch_result else {}

            # Record a source check so the log trail (and future LLM rounds) can see
            # what the validation fetch actually produced.
            try:
                await db.record_source_check(
                    source_id=source_id,
                    success=success,
                    method=method,
                    articles_found=articles_found,
                    response_time=response_time,
                    error_message=f"[AutoHeal validation] {error_msg}" if error_msg else "[AutoHeal validation] OK",
                )
            except Exception:
                logger.exception("[AutoHeal] Failed to record validation source check for %s", source_id)

            if success:
                logger.info(
                    "[AutoHeal] Validation PASSED for source '%s' (id=%s) — resetting failure counters",
                    source.name,
                    source_id,
                )
                await db.update_source_health(source_id, True, response_time)
            else:
                logger.warning(
                    "[AutoHeal] Validation FAILED for source '%s' (id=%s) — %s",
                    source.name,
                    source_id,
                    error_msg or "unknown",
                )

            return {
                "success": success,
                "error": error_msg,
                "method": method,
                "articles_found": articles_found,
                "response_time": round(response_time, 2),
                "rss_parsing_stats": rss_stats,
            }

        except Exception as exc:
            logger.exception("[AutoHeal] Validation fetch raised an exception for source %s", source_id)
            fail_result["error"] = str(exc)[:300]
            return fail_result
