# Effective Troubleshooting Steps for CTI Scraper Sources

Based on troubleshooting SpecterOps Blog and other sources, here's my systematic approach:

## 1. **Initial Diagnosis - Identify the Scope**

### Database Status Check
```python
# Check source configuration and current state
sources = await db_manager.list_sources(SourceFilter(name_contains='SourceName'))
source = sources[0]
print(f'Active: {source.active}')
print(f'Last check: {source.last_check}')
print(f'Article count: {len(await db_manager.list_articles_by_source(source.id))}')
```

**Key Questions:**
- Is the source active in the database?
- When was it last checked?
- How many articles exist vs. expected?
- What's the health status?

## 2. **Configuration Verification**

### Check Source Config
```yaml
# Review sources.yaml for:
- RSS URL validity
- Active status
- Check frequency
- Special configurations (SSL, selectors, etc.)
```

**Common Issues Found:**
- ✅ **Broken RSS URLs** (Hunt.io, Picus Security returned HTML instead of RSS)
- ✅ **SSL Certificate Issues** (SpecterOps needed bypass)
- ✅ **Incorrect Content Selectors** (wrong CSS selectors for content extraction)

## 3. **Manual RSS Feed Testing**

### Test RSS Connectivity
```python
# Test with SSL verification disabled first
async with httpx.AsyncClient(verify=False) as client:
    response = await client.get(rss_url)
    print(f'Status: {response.status_code}')
    print(f'Content-Type: {response.headers.get("content-type")}')

    # Parse RSS to see what's available
    root = ET.fromstring(response.text)
    items = root.findall('.//item')
    print(f'RSS items found: {len(items)}')
```

**This reveals:**
- ✅ **SSL Issues** (certificate verification failures)
- ✅ **Invalid RSS Format** (some "RSS" URLs return HTML)
- ✅ **Content Quality** (description length, actual vs. summary content)

## 4. **Content Extraction Testing**

### Test Individual Article Scraping
```python
# Fetch a sample article to test content extraction
article_response = await client.get(article_url)
soup = BeautifulSoup(article_response.text, 'html.parser')

# Test different selectors
selectors = ['article', 'div.content', 'main', '.post-content']
for selector in selectors:
    content_elem = soup.select_one(selector)
    if content_elem:
        content = content_elem.get_text(strip=True)
        print(f'Selector "{selector}": {len(content)} chars')
```

**Key Findings:**
- ✅ **Selector Effectiveness** (which CSS selectors work best)
- ✅ **Content Length** (full articles vs. summaries)
- ✅ **Content Quality** (meaningful content vs. navigation/ads)

## 5. **End-to-End Parser Testing**

### Test Complete RSS Pipeline
```python
# Test the actual RSS parser with HTTP client
async with HTTPClient() as http_client:
    rss_parser = RSSParser(http_client)
    articles = await rss_parser.parse_feed(source)
    print(f'Parsed {len(articles)} articles')

    # Test database saving
    for article_data in articles:
        saved_article = await db_manager.create_article(article_data)
```

**This validates:**
- ✅ **Parser Logic** (RSS parsing with content extraction)
- ✅ **Database Integration** (saving articles successfully)
- ✅ **Deduplication** (handling existing articles)

## 6. **Configuration Fixes Applied**

### Common Fix Patterns

**SSL Certificate Issues:**
```python
# Already implemented in HTTPClient:
if domain == 'posts.specterops.io' and self.verify_ssl:
    client_config['verify'] = False  # SSL bypass
```

**Invalid RSS Feeds:**
```yaml
# Force web scraping when RSS is broken
rss_url: null
rss_only: false
```

**Content Quality Issues:**
```python
# Enhanced RSS parser with fallback to web scraping
if len(content) < source_min_length:
    # Trigger modern scraper fallback
    return await self.modern_scraper.scrape_url(url)
```

**Minimum Content Length Tuning:**
```yaml
config:
  min_content_length: 2000  # Reject articles under 2000 chars
```

## 7. **System Integration Verification**

### Check Automated Collection
```bash
# Verify background services are running
docker-compose ps
# Should show: cti_worker, cti_scheduler (UP)

# Check recent collection activity
# Look for recent last_check timestamps
```

### Update Source Statistics
```python
# Refresh source statistics for UI
await db_manager.update_source_article_count(source.id)
await db_manager.update_source_health(source.id, success=True)
```

## 8. **Post-Fix Validation**

### Verification Checklist
- ✅ **Articles Collected:** Manual collection works
- ✅ **Database Updated:** Article count reflects reality
- ✅ **UI Consistency:** Sources page shows correct stats
- ✅ **Automation Ready:** Background services will continue collection

### Cache Management
```bash
# Restart web service to clear cached data
docker-compose restart web
```

## **Most Effective Debugging Techniques**

1. **Progressive Testing:** Start simple (HTTP GET) → RSS parsing → full pipeline
2. **SSL Bypass First:** Disable SSL verification to isolate connectivity vs. certificate issues
3. **Manual Before Automated:** Test manual collection before debugging automation
4. **Content Quality Focus:** Verify you're getting full articles, not just summaries
5. **Configuration Comparison:** Compare working sources with broken ones
6. **Live RSS Analysis:** Parse actual RSS feeds to understand structure and content

## **Key Insights Learned**

- **Medium-based blogs** (like SpecterOps) work well with `article` selectors
- **SSL certificate issues** are common with security blogs
- **RSS feeds often contain summaries** requiring fallback to web scraping
- **Source statistics need manual refresh** after bulk operations
- **Configuration validation** prevents many issues before they occur

## **Common Issue Resolution Examples**

### SpecterOps Blog Case Study
**Problem:** 0 articles collected despite active source
**Root Cause:** SSL certificate verification failure
**Solution:** Already implemented SSL bypass for `posts.specterops.io`
**Result:** Successfully collected 10 high-quality articles (7K-50K chars)

### TheDFIRReport Case Study
**Problem:** Only collecting 200-character summaries from RSS
**Root Cause:** RSS feed contains article summaries, not full content
**Solution:** Enhanced RSS parser with content length threshold and web scraping fallback
**Result:** Full articles collected (46K+ characters) with comprehensive historical collection

### Hunt.io & Picus Security Case Study
**Problem:** RSS URLs returning HTML instead of RSS/XML
**Root Cause:** Invalid RSS feeds
**Solution:** Set `rss_url: null` and `rss_only: false` to force web scraping
**Result:** Direct web scraping bypasses broken RSS feeds

This systematic approach allows for quick identification and resolution of source collection issues while ensuring future automation works correctly.