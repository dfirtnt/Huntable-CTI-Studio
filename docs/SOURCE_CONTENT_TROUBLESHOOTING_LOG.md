# Source & Content Troubleshooting Log

Chronological log of troubleshooting steps, issues encountered, and solutions applied.

---

## 2025-01-29

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
