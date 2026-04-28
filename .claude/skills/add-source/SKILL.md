---
name: add-source
description: >
  Add a new CTI intelligence source to Huntable CTI Studio for article ingestion.
  Use this skill when the user says "add a source", "add a feed", "new source",
  "add this blog", "ingest from <url>", or wants to configure a new RSS/scraping
  source for the ingestion pipeline.
---

# Add Source

This skill adds a new CTI intelligence source to `config/sources.yaml` and syncs
it to the database. It handles both RSS-based and scraping-only sources.

## Workflow

### Step 1 — Gather source information

Collect from the user (ask if not provided):

| Field | Required | Example |
|-------|----------|---------|
| **Blog/site URL** | Yes | `https://www.vmray.com/blog/` |
| **RSS feed URL** | No | `https://www.vmray.com/blog/feed/` |
| **Source name** | Yes (can derive) | `VMRay Blog` |

### Step 2 — Discover source details

Use web tools to visit the site and determine:

1. **RSS feed discovery** — Check for `<link rel="alternate" type="application/rss+xml">` in the page head, or try common paths (`/feed/`, `/rss/`, `/feed.xml`, `/rss.xml`, `/atom.xml`). If an RSS URL was provided, validate it returns valid XML.
2. **Domain** — Extract the domain for the `allow` list (e.g., `vmray.com`)
3. **Post URL pattern** — Look at article links to derive a `post_url_regex` (e.g., `^https://www\\.vmray\\.com/blog/.*`)
4. **Content selectors** — Inspect an article page for appropriate `body_selectors`, `title_selectors`, `date_selectors`, `author_selectors` if the site needs scraping
5. **Content type** — Determine if articles are CTI-relevant (threat intel, malware analysis, detection engineering, vulnerability research)

### Step 3 — Generate the source identifier

Create a snake_case `id` from the source name:
- `VMRay Blog` → `vmray_blog`
- `Unit 42 Threat Research` → `unit42_threat_research`

Check `config/sources.yaml` for duplicate identifiers before proceeding.

### Step 4 — Build the YAML entry

Use this template, adapting based on discovery:

```yaml
# {Source Name} — {brief note about RSS availability}
- id: "{identifier}"
  name: "{Source Name}"
  url: "{site_url}"
  rss_url: {rss_url or null}
  check_frequency: 1800  # 30 minutes
  active: true
  config:
    allow: ["{domain}"]
    post_url_regex: ["{regex_pattern}"]
    robots:
      enabled: true
      user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
      respect_delay: true
      max_requests_per_minute: 10
      crawl_delay: 1.0
    min_content_length: 1500
    title_filter_keywords: ["webinar", "training", "careers", "job posting"]
    rss_only: {true if rss_url and no scraping needed, else false}
    extract:
      prefer_jsonld: true
      title_selectors: ["h1", "meta[property='og:title']::attr(content)"]
      date_selectors:
        - "meta[property='article:published_time']::attr(content)"
        - "time[datetime]::attr(datetime)"
      body_selectors: {discovered selectors or defaults}
      author_selectors: ["meta[name='author']::attr(content)", ".author-name"]
  description: "{one-line description of what intelligence this source provides}"
```

**Decision rules:**
- If RSS is available and reliable: set `rss_only: true`, still populate `extract` as fallback
- If no RSS: set `rss_url: null`, `rss_only: false`
- If the site uses JavaScript rendering: add `use_playwright: true` to config
- If the site has anti-bot protections: note in the YAML comment

### Step 5 — Determine placement in sources.yaml

Read `config/sources.yaml` and place the new entry in the appropriate section based on the existing category comments:
- `PREMIUM THREAT INTELLIGENCE SOURCES` — top-tier vendor blogs (CrowdStrike, Mandiant, etc.)
- `SECURITY VENDOR & RESEARCH BLOGS` — security vendor blogs
- `INDEPENDENT RESEARCH & COMMUNITY` — independent researchers, community blogs
- If unsure, append at the end of the most relevant section

### Step 6 — Edit sources.yaml

Use the Edit tool to insert the new source entry at the chosen location.

### Step 7 — Sync to database

Run the sync command to insert the new source without touching existing sources:

```bash
./run_cli.sh sync-sources --config config/sources.yaml --no-remove --new-only
```

If the CLI is not available (e.g., Docker not running), tell the user:
> Source added to `config/sources.yaml`. Run `./run_cli.sh sync-sources --no-remove --new-only` to sync to the database.

### Step 8 — Verify

If Docker is running, verify via:
```bash
curl -s http://localhost:8001/api/health/ingestion | jq '.ingestion.source_breakdown[] | select(.name == "{Source Name}") | {name, active, total: .total_articles}'
```

Or direct the user to the Sources page in the UI.

## Important constraints

- **Always use `--no-remove --new-only`** when syncing — never overwrite existing source configs
- **Respect robots.txt** — always include the `robots` config block with `enabled: true`
- **Set reasonable rate limits** — `max_requests_per_minute: 10` and `crawl_delay: 1.0` unless the site explicitly allows more
- **Filter non-CTI content** — use `title_filter_keywords` to exclude webinars, product announcements, job postings
- **Validate URLs** — ensure the blog URL and RSS URL are reachable before adding
