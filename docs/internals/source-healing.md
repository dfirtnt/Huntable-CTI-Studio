# Source Auto-Healing Architecture

> **Owner:** `src/services/source_healing_service.py`
> **Coordinator:** `src/services/source_healing_coordinator.py`
> **Audit trail:** `healing_events` table + Langfuse traces

## How It Works

The healing pipeline runs when a source hits the `failure_threshold` (default: 100 consecutive failures). It executes up to `max_attempts` rounds per session (default: 5), each round following this cycle:

1. **Gather context** — source config, error history, working source examples (once, shared across rounds)
2. **Snapshot mutable fields** — deep-copy `url`, `rss_url`, `config` for rollback if all rounds exhaust
3. **Deep diagnostic probe** — 5 concurrent probes (HTTP, RSS content, blog page, sitemap, WP JSON) via `asyncio.gather`
4. **Deterministic pre-filters** — bot protection and URL redirect checks bypass the LLM entirely when the fix is obvious
5. **LLM analysis** — proposes config changes based on probe data; retries once on JSON parse failure
6. **Schema normalization** — rewrites structurally-plausible-but-semantically-wrong shapes (hoists misplaced `wp_json` to top-level, fixes `listing` key names) so LLM proposals match what the scraper actually reads
7. **Apply actions** — merges normalized config into the source
8. **Validate** — runs a real fetch (with 60-second timeout) and records the result as a source check
9. **Decide** — stop if healed, retry with validation logs if not
10. **Rollback** — if all rounds exhaust, restore `url`/`rss_url`/`config` to pre-healing snapshot and mark `healing_exhausted`

## Dispatch And Eligibility

Healing can be dispatched in two ways:

- **Scheduled scan**: `check_sources_for_healing` Celery task (hourly by default; configurable via Scheduled Jobs)
- **Manual trigger**: `POST /api/actions/trigger-healing` for a full scan, or `POST /api/sources/{source_id}/heal` for one source

For scheduled scans, a source is eligible only when all are true:

- `active = true`
- `consecutive_failures >= failure_threshold`
- `healing_exhausted = false`
- `last_success` is either null or older than 24 hours (`_RECENT_SUCCESS_GRACE_PERIOD` — prevents healing for transient failures like container restarts or network blips)

## Deep Diagnostic Probes

The probe phase (`_probe_urls`) runs five probes **concurrently** via `asyncio.gather`, sharing a single `httpx.AsyncClient` (15-second timeout, up to 5 redirects). All five probes execute in parallel before the LLM sees anything:

| Probe | What it detects | Key fields |
|---|---|---|
| **HTTP probe** | Status codes, redirects, content-type, bot protection (CloudFront, Akamai, WAF) | `status_code`, `final_url`, `bot_protection_detected`, `bot_protection_provider` |
| **RSS content analysis** | Empty feeds (200 OK but 0 items), article URL patterns from `<link>` elements | `item_count`, `verdict: EMPTY_FEED`, `sample_urls`, `sample_titles` |
| **Blog page analysis** | JS-rendered pages (large HTML, tiny visible text), post link discovery | `visible_text_length`, `is_likely_js_rendered`, `sample_post_links` |
| **Sitemap discovery** | Available sitemaps, post-specific sitemaps, article-like URL filtering from generic sitemaps | `post_sitemaps`, `post_sitemap_sample`, `sample_urls` (filtered), `sample_locs` (fallback) |
| **WP JSON API check** | WordPress REST API availability and content | `endpoint`, `has_content`, `sample_posts` |

### Sitemap Article-URL Filtering

When no post-specific sub-sitemap is found (e.g., `post-sitemap.xml`), the sitemap probe filters generic sitemap URLs to extract article-like entries. A URL qualifies as article-like when it:
- Starts with the source URL prefix
- Is not the homepage itself
- Does not end in a static-asset extension (`.xml`, `.png`, `.jpg`, `.css`, `.js`)
- Has more path segments than the source URL

This produces the `sample_urls` field (up to 5 URLs + `sample_urls_total` count). If no article-like URLs survive the filter, the raw `sample_locs` fallback provides the first 5 sitemap URLs unfiltered.

### RSS Article-URL Extraction

The RSS probe now extracts `<link>` URLs from RSS/Atom entries (both `<link>text</link>` and `<link href="..."/>` forms) and passes them as `sample_urls`. This gives the LLM real URL patterns to inform `post_url_regex` corrections — instead of guessing `/threat-research/` when the actual pattern is `/research/`.

### Why This Matters

Before these probes, the LLM received only HTTP status codes. It would see "RSS: HTTP 200" and assume the feed was working — when in reality it had zero items. The LLM wasted 8 rounds on VMRay Blog because it never knew the RSS was empty.

## What Self-Healing CAN Fix (Config-Only)

These are problems the LLM can resolve by changing `url`, `rss_url`, or `config`:

### 1. Dead/empty RSS feeds
- **Signal:** `rss_content_analysis.verdict = "EMPTY_FEED"` or HTTP 404/403
- **Fix:** Set `rss_url` to null → forces fallthrough to scraping tiers
- **Example:** Google Cloud TI had a 404 RSS URL

### 2. Wrong URL (site migrated)
- **Signal:** HTTP probe shows redirect chain to new domain
- **Fix:** Update `url` to the redirect target

### 3. JS-rendered pages
- **Signal:** `blog_page_analysis.is_likely_js_rendered = true`
- **Fix:** Set `use_playwright: true` in config
- **Example:** Group-IB was a full SPA, one config flag fixed it

### 4. Wrong discovery strategy
- **Signal:** 0 URLs discovered, but `sitemap_discovery` or `blog_page_analysis.sample_post_links` has URLs
- **Fix:** Add listing or sitemap discovery strategy with appropriate selectors
- **Example:** Google Cloud TI needed listing discovery with `a[href*='threat-intelligence/']`

### 5. Wrong URL regex
- **Signal:** URLs discovered but all filtered; `post_sitemap_sample` shows different URL pattern than `post_url_regex`
- **Fix:** Rewrite `post_url_regex` based on observed URLs from sitemap/listing probe

### 6. Wrong extraction selectors
- **Signal:** Pages fetched but 0 content extracted (articles_found=0 in validation)
- **Fix:** Update `extract.body_selectors`

### 7. WordPress sites with accessible WP JSON API
- **Signal:** `wp_json_api_check.has_content = true`
- **Fix:** Set top-level `wp_json: {"endpoints": [...], "url_field_priority": [...]}` (NOT under `discovery.strategies` — the scraper reads it from the top level only)
- **Example:** VMRay Blog — WP JSON returned full content without needing Playwright

## What Self-Healing CANNOT Fix

### 1. Code bugs
- **Signal:** Python exceptions in error_message (AttributeError, TypeError, KeyError)
- **Example:** `configure_source_robots` AttributeError crashed RSS for every source with a `robots` config
- **LLM should:** Return `{"diagnosis": "Code-level bug: <error>", "actions": []}` and stop

### 2. Missing runtime dependencies
- **Signal:** Playwright launch errors mentioning missing executables
- **Example:** Playwright browsers not installed in Docker container
- **LLM should:** Report the specific error, not try alternative configs

### 3. Platform capability gaps
- **Signal:** Configured strategy isn't recognized by the scraper
- **Example:** `wp_json` strategy didn't exist before it was added to the code
- **LLM should:** Only propose strategies documented in the system prompt

### 4. Bot protection / Cloudflare challenges
- **Signal:** HTTP 403 with challenge headers, or HTML contains challenge JS
- **LLM should:** Report "site uses bot protection" and stop

## Deterministic Pre-Filters

Before calling the LLM, the pipeline checks for two cases where the fix is deterministic and doesn't need AI reasoning:

### Bot Protection Detection

If the HTTP probe returns a 403 with bot-protection signatures (CloudFront, Akamai, or generic WAF phrases like "request blocked", "access denied"), the pipeline short-circuits immediately:
- Returns a diagnosis identifying the provider
- Returns empty actions (auto-healing cannot bypass bot protection)
- Saves an LLM call and avoids futile retry rounds

### URL Redirect Pre-Filter

On **round 1 only** (no `previous_attempts`), if the HTTP probe shows the source URL redirects to a different domain/path:
- Applies `{"field": "url", "value": "<redirected_url>"}` without calling the LLM
- Ignores trailing-slash-only differences (e.g., `example.com/blog` vs `example.com/blog/`)
- Skipped on retry rounds — if the redirect was already tried and didn't fix the issue, the LLM takes over

## Schema Normalization

Between LLM analysis and config persistence, the pipeline runs `_normalize_proposed_config` to bridge historical drift between the healing prompt documentation and the scraper's reader code. This prevents structurally-plausible LLM proposals from producing silent no-ops.

### wp_json Hoisting

**Problem:** The system prompt historically described `wp_json` as a discovery strategy alongside `listing` and `sitemap`, leading LLMs to place it under `config.discovery.strategies`. But the scraper reads it from **top-level** `config.wp_json` (the fast path in `modern_scraper.scrape_source`). When misplaced, `wp_json` is explicitly ignored (`pass` at line 78-82 of `modern_scraper.py`).

**Fix:** When the normalizer sees `{"discovery": {"strategies": [{"wp_json": {"endpoints": [...]}}]}}`, it hoists the `wp_json` entry to `config.wp_json` and removes it from the strategies list. If the strategies list becomes empty after hoisting, the entire `discovery` section is dropped.

**Example:**
```python
# LLM proposes (wrong location):
{"discovery": {"strategies": [{"wp_json": {"endpoints": ["https://x.com/wp-json/wp/v2/posts"]}}]}}

# Normalizer rewrites to (correct location):
{"wp_json": {"endpoints": ["https://x.com/wp-json/wp/v2/posts"]}}
```

### listing Strategy Key Fixes

**Problem:** The prompt informally says "listing (CSS selector on listing page)" but doesn't document the exact required keys. LLMs often emit `selector` (matching the informal description) instead of the actual key `post_link_selector`, and omit the required `urls` array.

**Fix:** 
- When `listing` contains `selector` but not `post_link_selector`, rename `selector` → `post_link_selector`
- When `listing` has no `urls` key, inject `urls: [source.url]` as a sensible default (the source's own homepage as the listing page)

**Example:**
```python
# LLM proposes:
{"discovery": {"strategies": [{"listing": {"selector": "h2 a"}}]}}

# Normalizer rewrites to:
{"discovery": {"strategies": [{"listing": {"urls": ["https://x.com/blog/"], "post_link_selector": "h2 a"}}]}}
```

### Audit Trail

Each normalization produces a human-readable note logged at INFO level:
```
[AutoHeal] Normalized LLM-proposed config for source 2: Hoisted wp_json from discovery.strategies to top-level config.wp_json (the scraper reads it only from there); Injected listing.urls=[...] from source URL (listing discovery returns zero URLs without it)
```

The healing events table stores the **normalized** config in `actions_applied`, while `actions_proposed` preserves the raw LLM output. This lets you see both what the LLM intended and what actually landed in the database.

### Passthrough Behavior

Well-formed configs that already match the scraper's schema pass through unchanged. The normalizer is defensive — it only rewrites when it detects specific known drift patterns.

## Config Rollback on Exhaustion

When all healing rounds exhaust without success, the pipeline **restores the source to its pre-healing state** instead of leaving it in a partially-modified (potentially worse) configuration:

1. Before the loop starts, a deep copy of `url`, `rss_url`, and `config` is saved
2. After exhaustion, the current values are compared to the originals
3. Only fields that were actually changed during healing are rolled back
4. `healing_exhausted` is always set to `true`

This prevents the scenario where a healing attempt changes `rss_url` to `null` (to try scraping), fails across all rounds, and leaves the source permanently unable to use its original RSS feed.

## LLM JSON Retry

If the LLM returns a response that cannot be parsed as valid JSON (markdown fences are already stripped), the pipeline retries **once** with a clarification prompt:
- Appends the failed response as an `assistant` message
- Adds a `user` message requesting strict JSON format with an exact schema example
- If the retry also fails, the original parse-failure diagnosis stands

## Validation Timeout

Each validation fetch has a **60-second timeout** (`asyncio.wait_for`). If the fetch exceeds this:
- The validation is recorded as failed with `method: "timeout"`
- The error message includes context: "may indicate JS-rendered content or slow server"
- The next LLM round sees this timeout in its validation details, helping it diagnose JS-rendering issues

## Futility Detection

If 3+ rounds produce the same fundamental outcome (e.g., "0 articles" regardless of config), it's likely not a config problem. The system prompt instructs the LLM to recognize this and return an empty actions list with a diagnostic explaining the suspected platform limitation.

## Working Source Examples

The LLM receives configs from up to 3 healthy sources (sorted by article count) as reference. This lets it copy patterns that already work — e.g., if it sees a working listing strategy, it can adapt it for the failing source rather than guessing the config schema.

## Validation Fetch Logging

Each validation attempt records a `source_check` entry with an `[AutoHeal validation]` prefix. This means:
- The check history shows what each healing round's fix actually produced
- Subsequent LLM rounds see their predecessor's validation results (method, articles_found, error, rss_parsing_stats)
- The healing history UI displays validation details (`method`, `articles_found`, `error`) when present
- Validation timeouts (>60s) are recorded with `method: "timeout"` and a descriptive error
- If no validation summary exists (for example, LLM transport/runtime failure before apply/validate), the UI shows `Details:` with the stored `error_detail`

## Config Fields the LLM Can Modify

Only these fields are writable: `url`, `rss_url`, `config`.

The LLM **cannot** set `active` (operator-only action) or change the source name/identifier.

## Local LLM Support

The healing pipeline is provider-agnostic. `SourceHealingConfig` loads `provider`, `model`, and
optional `api_key` values from App Settings, then passes them to `LLMService`. In practice, this
means the healer can use a local OpenAI-compatible backend such as LMStudio instead of a hosted
API.

Recommended local setup:

- `SOURCE_HEALING_PROVIDER=lmstudio`
- `SOURCE_HEALING_MODEL=<loaded local model>`
- Leave `SOURCE_HEALING_API_KEY` empty for LMStudio

Recommended models:

- `Qwen2.5-14B-Instruct` for the best JSON discipline and the most reliable config rewrites
- `Llama 3.1-8B-Instruct` when you want a lighter local fallback

Why local models work well here:

- The prompt is strict JSON with a fixed schema.
- The service already handles deterministic cases like redirects and bot protection without LLM help.
- Validation is bounded and mechanical, so the model mostly rewrites source config rather than
  performing open-ended analysis.

Local models are still subject to the same hard limits as hosted models:

- Bot-protected sites cannot be healed by config changes alone.
- Code-level failures and missing runtime dependencies should be reported, not worked around.

## Key Files

| File | Purpose |
|---|---|
| `src/services/source_healing_service.py` | Core healing pipeline — probes, LLM calls, validation |
| `src/services/source_healing_coordinator.py` | Scheduled scan that dispatches healing for failing sources |
| `src/services/source_healing_config.py` | Settings: provider, model, max_attempts, threshold |
| `src/models/healing_event.py` | Pydantic models for audit trail |
| `src/database/models.py` | `HealingEventTable` schema |
| `src/web/templates/sources.html` | Healing history slide-out panel |
