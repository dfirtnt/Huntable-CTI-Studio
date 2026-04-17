# Source Self-Healing: Executive Overview

When CTI sources (RSS feeds, blogs, threat intel sites) stop working, the system's **auto-healer** acts like a smart troubleshooter. It diagnoses the problem, proposes a fix, validates it works, and rolls back if it doesn't.

---

## How It Works

The healing pipeline kicks in when a source has **100 consecutive failures** (configurable). It then runs up to **5 diagnostic rounds**, where each round:

1. **Probe the site** — 5 simultaneous checks (HTTP status, RSS content, page structure, sitemap, WordPress API)
2. **Check for obvious issues** — bot protection and URL redirects are handled automatically (no AI needed)
3. **Ask an LLM** — analyze probe data and suggest config changes
4. **Apply the fix** — update url, rss_url, or extraction selectors
5. **Validate** — actually fetch the source to confirm the fix works
6. **Rollback if needed** — restore original config if all 5 rounds fail

---

## What It Can Fix

| Problem | Signal | Fix |
|---|---|---|
| **Dead RSS feed** | Feed returns 200 but 0 items | Set `rss_url` to null — forces scraper fallback |
| **Site migrated** | HTTP redirect chain to new domain | Update `url` to redirect target |
| **JS-rendered pages** | Large HTML but tiny visible text | Enable Playwright rendering |
| **Wrong discovery method** | 0 URLs found but sitemap has URLs | Add listing or sitemap strategy with selectors |
| **Wrong URL regex** | URLs found but all filtered out | Rewrite `post_url_regex` from observed patterns |
| **Wrong selectors** | Pages fetched but 0 content extracted | Update body extraction selectors |
| **WordPress with JSON API** | WP JSON API returns content | Configure `wp_json` (direct content, no Playwright needed) |

---

## What It Cannot Fix

| Problem | Reason |
|---|---|---|
| **Code bugs** | Python exceptions need developer fixes |
| **Missing Playwright browsers** | Runtime dependency issue, not config |
| **Bot protection** (Cloudflare, WAF) | Cannot be bypassed via config changes |
| **Platform capability gaps** | Strategy not yet implemented in the scraper |

---

## Key Safety Features

- **Deterministic pre-filters** — redirect and bot protection detected without LLM (saves cost and rounds)
- **Schema normalization** — automatically fixes common LLM mistakes (e.g., `wp_json` in wrong config location)
- **Rollback on exhaustion** — restores original config if all rounds fail, preventing partial/broken states
- **Audit trail** — every healing event logged to database + Langfuse traces for debugging
- **Local LLM support** — can use LMStudio/Qwen instead of hosted APIs for cost savings

---

## Dispatch Triggers

- **Scheduled scan** — hourly check via Celery task (configurable via Scheduled Jobs)
- **Manual trigger** — API endpoint for single source or full scan

---

## Reference

- Architecture: `docs/internals/source-healing.md`
- Implementation: `src/services/source_healing_service.py`
- Coordinator: `src/services/source_healing_coordinator.py`
- Config: `src/services/source_healing_config.py`
