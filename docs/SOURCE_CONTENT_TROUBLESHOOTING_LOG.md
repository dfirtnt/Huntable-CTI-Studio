# Source & Content Troubleshooting Log

Chronological log of troubleshooting steps, issues encountered, and solutions applied.

---

## 2025-01-29

### Testing: Article Fix Script on Corrupted Articles
**Time:** Evening  
**Status:** Partial Success

**Test Results:**
- Tested fix script on 25 corrupted articles from last 2 days
- Successfully fixed: 1 article (1049 - DFIR Report)
- Skipped: 24 articles (JS-rendered pages)
- Skipped: 1 article (US-CERT, only 3 replacement chars - minimal corruption)

**Key Findings:**
1. **Encoding fix works:** New content has 0 replacement characters
2. **JS-rendered pages:** 24/25 corrupted articles are from Red Canary Blog and SecurityWeek
   - These sites require JavaScript to render content
   - After removing scripts, only 70-333 chars extracted (vs 17K-50K in database)
   - Script correctly detects and skips these pages
3. **Successful fix example:** Article 1049 (DFIR Report)
   - Before: 45,833 chars with corruption
   - After: 46,754 chars, 0 replacement characters
   - Content length increased, corruption eliminated

**Script Behavior:**
- Detects JS-rendered pages (<500 chars after extraction)
- Gracefully skips with clear message
- Doesn't break process on JS pages
- Only updates if corruption is significantly reduced

**Conclusion:**
- Encoding fix prevents new corruption going forward
- Most existing corrupted articles are from JS-rendered sources
- These cannot be fixed without headless browser (Playwright/Selenium)
- Script handles JS pages correctly without breaking

**Files Tested:**
- `fix_corrupted_articles.py` - Tested on articles 2542, 2521-2549, 2585, 2620-2628, 602, 603, 1049

---

## 2025-01-29

### Issue: Picus Security Blog - No Articles Extracted (URL Discovery Failure)
**Time:** Evening  
**Severity:** High  
**Status:** Resolved

**Symptoms:**
- Picus Security Blog: 88.89% failure rate (8/9 checks failed)
- Error: "No articles extracted from any method"
- Last success: Nov 4, 2025 (50 articles via basic_scraping)
- 136 consecutive failures since last success

**Investigation Steps:**
1. Checked source_checks table - all failures show "No articles extracted from any method"
2. Tested URL manually - found 38 matching blog links on base URL
3. Tested URLDiscovery.discover_urls() - returned 0 URLs
4. Found: URLDiscovery only works if `discovery` config exists in sources.yaml
5. Picus has no `discovery` config, only base URL and post_url_regex

**Root Cause:**
- `URLDiscovery.discover_urls()` requires explicit `discovery.strategies` config
- Sources without discovery config get 0 URLs discovered
- No fallback to scrape base URL for links matching post_url_regex

**Solution Applied:**
1. Added `_discover_from_base_url()` fallback method to URLDiscovery
2. When no discovery strategies configured, scrape base URL for links
3. Filter links by post_url_regex patterns from source config
4. Returns discovered URLs matching the patterns

**Files Changed:**
- `src/core/modern_scraper.py` - Added fallback discovery method

**Verification:**
- Tested URLDiscovery - now discovers 11 URLs from Picus base URL
- Manually updated database config (sync had nested config issue)
- Full scrape test: ✅ Success - 11 articles extracted via basic_scraping
- Sample article: 4,989 chars, properly extracted

**Additional Issue Found:**
- Source sync didn't properly update config (nested structure issue)
- Manual SQL update required to fix Picus config
- Need to investigate sync service config handling

**Result:**
- Picus Security Blog now working - can extract articles
- URL discovery fallback successfully implemented

---

### Issue: 100% Article Corruption - Replacement Characters
**Time:** Afternoon  
**Severity:** Critical  
**Status:** Resolved

**Symptoms:**
- SQL query revealed 100% of articles from top sources contain `\ufffd` replacement characters
- All major sources affected: The Hacker News (335 articles), Bleeping Computer (270), DFIR Report (91), etc.

**Investigation Steps:**
1. Ran SQL query to check corruption rate by source
2. Found all sources showing 100% corruption
3. Examined `src/utils/http.py` Response.text property
4. Found it uses `errors='replace'` as fallback, causing replacement characters

**Previous Attempts (Noted in code history):**
- Attempt 1-3: Tried manual brotli decompression fixes
- Result: Failed - httpx already handles decompression automatically
- Lesson: Don't manually decompress what httpx already does

**Root Cause:**
- `Response.text` property blindly decoded as UTF-8 with `errors='replace'`
- No charset detection - assumed UTF-8 for all content
- Double encoding/decoding in HTTPClient.get() method

**Solution Applied:**
1. Simplified `HTTPClient.get()` - removed all manual decompression, trust httpx completely
2. Fixed `Response.text` to use `charset-normalizer` for proper encoding detection
3. Added fallback chain: detected encoding → charset-normalizer → common encodings → utf-8 ignore

**Files Changed:**
- `src/utils/http.py` - Simplified decompression, added charset detection
- Removed unused brotli import checks

**Verification:**
- New articles should have <1% replacement characters
- `fix_corrupted_articles.py` will use fixed HTTPClient automatically

**Next Steps:**
- Run `python fix_corrupted_articles.py --all` to repair existing articles
- Monitor new articles for corruption rate

---

### Issue: Missing Source Check Historical Logging
**Time:** Afternoon  
**Severity:** High  
**Status:** Resolved

**Symptoms:**
- `source_checks` table had only 22 rows total
- No historical failure tracking
- Couldn't identify sources with high failure rates

**Investigation Steps:**
1. Ran SQL query: `SELECT count(*) FROM source_checks;` - returned 22
2. Checked `celery_app.py` - found it updates `sources` table but doesn't log to `source_checks`
3. Checked `AsyncDatabaseManager` - no `record_source_check()` method

**Root Cause:**
- `celery_app.py` tasks update health metrics but never call `record_source_check()`
- `AsyncDatabaseManager` missing the method entirely

**Solution Applied:**
1. Added `record_source_check()` method to `AsyncDatabaseManager`
2. Updated `check_all_sources()` to log after each source check
3. Updated `check_source()` to log with method and error details
4. Updated `collect_from_source()` to log collection results

**Files Changed:**
- `src/database/async_manager.py` - Added `record_source_check()` method
- `src/worker/celery_app.py` - Added logging calls in 3 tasks

**Verification:**
- `source_checks` table should populate on next source check cycle
- Query: `SELECT * FROM source_checks ORDER BY check_time DESC LIMIT 10;`

---

---

## 2025-01-29

### Issue: Source Sync Config Update Failure
**Time:** Evening  
**Status:** ✅ Fixed

**Symptoms:**
- Multiple sources showing empty configs in database after `sync-sources` command
- Sources affected: Picus Security, NCSC UK, Assetnote Research, Group-IB, Splunk Security Blog
- Configs properly defined in `sources.yaml` but not syncing to database

**Root Cause:**
1. **SourceConfigLoader** was passing config as plain dict instead of SourceConfig model
2. **SourceSyncService** was not properly extracting inner config from SourceConfig model
3. **SourceUpdate** Pydantic model was converting dict to SourceConfig incorrectly, losing inner config

**Solution:**
1. **Fixed `src/core/source_manager.py`:**
   - Modified `_parse_source` to create `SourceConfig` model with inner `config` dict properly set
   - Ensures `SourceCreate.config` is a `SourceConfig` model with `config.config` containing the actual config dict

2. **Fixed `src/services/source_sync.py`:**
   - Extract inner config from `SourceConfig` model: `config.config.config`
   - Create new `SourceConfig` model with proper structure for `SourceUpdate`
   - Pass `SourceConfig` model to `SourceUpdate` instead of raw dict

3. **Fixed `src/database/async_manager.py`:**
   - Enhanced `update_source` to handle nested config structures
   - Extract inner config from `SourceConfig` model if present
   - Clean up nested structures and remove `check_frequency`/`lookback_days` from config JSON

**Verification:**
- ✅ All sources now have configs properly synced
- ✅ Picus Security: 11 articles extracted successfully
- ✅ Splunk Security Blog: 50 articles discovered (content extraction needs work - JS-rendered)
- ✅ Group-IB: Config synced, but 403 Forbidden (anti-bot protection)
- ✅ Assetnote Research: Config synced, URLs discovered but content extraction failing (JS-rendered)
- ✅ NCSC UK: Config synced, but extraction selectors need updating

**Remaining Issues:**
1. **Content Extraction Failures:**
   - Splunk Security Blog: URLs discovered but content too short (0 chars) - JS-rendered pages
   - Assetnote Research: Same issue - JS-rendered content
   - NCSC UK: Selectors don't match page structure

2. **Anti-Bot Protection:**
   - Group-IB Threat Intelligence: 403 Forbidden errors
   - May need different user-agent, headers, or rate limiting adjustments

3. **Missing Discovery Config:**
   - Microsoft Security Response Center: RSS feed 404, no discovery config
   - Needs discovery strategy added to YAML config

**Files Modified:**
- `src/core/source_manager.py` - Fixed SourceConfig model creation
- `src/services/source_sync.py` - Fixed config extraction and SourceUpdate creation
- `src/database/async_manager.py` - Enhanced update_source to handle nested configs

---

## SQL Queries for Quick Diagnosis

### Check Corruption Rate
```sql
SELECT 
    s.name,
    count(*) as total,
    sum(case when a.content LIKE '%\ufffd%' then 1 else 0 end) as corrupt,
    round((sum(case when a.content LIKE '%\ufffd%' then 1 else 0 end)::numeric / count(*)::numeric) * 100, 2) as pct
FROM articles a
JOIN sources s ON a.source_id = s.id
GROUP BY s.name
ORDER BY pct DESC;
```

### Check Source Failure Rates
```sql
SELECT 
    s.name,
    count(*) as total_checks,
    sum(case when sc.success = false then 1 else 0 end) as failed,
    round((sum(case when sc.success = false then 1 else 0 end)::numeric / count(*)::numeric) * 100, 2) as failure_pct
FROM source_checks sc
JOIN sources s ON sc.source_id = s.id
GROUP BY s.name
ORDER BY failure_pct DESC;
```
