# Source Auto-Healing Architecture

> **Owner:** `src/services/source_healing_service.py`
> **Coordinator:** `src/services/source_healing_coordinator.py`
> **Audit trail:** `healing_events` table + Langfuse traces

## How It Works

The healing pipeline runs when a source hits the `failure_threshold` (default: 3 consecutive failures). It executes up to `max_attempts` rounds per session (default: 8), each round following this cycle:

1. **Gather context** — source config, error history, working source examples
2. **Deep diagnostic probe** — RSS content, sitemap, WP JSON API, JS-rendering detection
3. **LLM analysis** — proposes config changes based on probe data
4. **Apply actions** — merges proposed config into the source
5. **Validate** — runs a real fetch and records the result as a source check
6. **Decide** — stop if healed, retry with validation logs if not

## Deep Diagnostic Probes

The probe phase (`_probe_urls`) runs five checks before the LLM sees anything:

| Probe | What it detects | Key fields |
|---|---|---|
| **HTTP probe** | Status codes, redirects, content-type | `status_code`, `final_url` |
| **RSS content analysis** | Empty feeds (200 OK but 0 items) | `item_count`, `verdict: EMPTY_FEED` |
| **Blog page analysis** | JS-rendered pages (large HTML, tiny visible text) | `visible_text_length`, `is_likely_js_rendered`, `sample_post_links` |
| **Sitemap discovery** | Available sitemaps, post-specific sitemaps, URL patterns | `post_sitemaps`, `post_sitemap_sample` |
| **WP JSON API check** | WordPress REST API availability and content | `endpoint`, `has_content`, `sample_posts` |

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
- **Fix:** Set `discovery.strategies: [{"wp_json": {"endpoints": [...]}}]`
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

## Futility Detection

If 3+ rounds produce the same fundamental outcome (e.g., "0 articles" regardless of config), it's likely not a config problem. The system prompt instructs the LLM to recognize this and return an empty actions list with a diagnostic explaining the suspected platform limitation.

## Working Source Examples

The LLM receives configs from up to 3 healthy sources (sorted by article count) as reference. This lets it copy patterns that already work — e.g., if it sees a working listing strategy, it can adapt it for the failing source rather than guessing the config schema.

## Validation Fetch Logging

Each validation attempt records a `source_check` entry with an `[AutoHeal validation]` prefix. This means:
- The check history shows what each healing round's fix actually produced
- Subsequent LLM rounds see their predecessor's validation results
- The healing history UI displays validation details (method, articles found, error)

## Config Fields the LLM Can Modify

Only these fields are writable: `url`, `rss_url`, `config`.

The LLM **cannot** set `active` (operator-only action) or change the source name/identifier.

## Key Files

| File | Purpose |
|---|---|
| `src/services/source_healing_service.py` | Core healing pipeline — probes, LLM calls, validation |
| `src/services/source_healing_coordinator.py` | Scheduled scan that dispatches healing for failing sources |
| `src/services/source_healing_config.py` | Settings: provider, model, max_attempts, threshold |
| `src/models/healing_event.py` | Pydantic models for audit trail |
| `src/database/models.py` | `HealingEventTable` schema |
| `src/web/templates/sources.html` | Healing history slide-out panel |
