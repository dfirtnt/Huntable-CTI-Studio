# 📚 Usage Examples

This document provides practical examples of using the Threat Intelligence Aggregator for various common scenarios.

## 🚀 Getting Started Examples

### Basic Setup and First Collection

```bash
# 1. Initialize with sample sources
./threat-intel init --config config/sources.yaml

# 2. Test a few sources first
./threat-intel test --source crowdstrike_blog
./threat-intel test --source microsoft_security

# 3. Run a single collection
./threat-intel collect --dry-run  # Test without saving
./threat-intel collect             # Actually collect and save

# 4. Check results
./threat-intel stats
```

### Setting Up Continuous Monitoring

```bash
# Start continuous monitoring (every 10 minutes)
./threat-intel monitor --interval 600 --max-concurrent 3

# Or run in background
nohup ./threat-intel monitor --interval 600 > monitor.log 2>&1 &
```

## 🎯 Source Management Examples

### Adding New Sources

```bash
# Add a simple RSS source
./threat-intel sources add \
  "new_security_blog" \
  "New Security Blog" \
  "https://newsecurityblog.com" \
  --rss-url "https://newsecurityblog.com/feed.xml" \
  --tier 1 \
  --weight 1.5

# View all sources
./threat-intel sources list

# Export current configuration
./threat-intel sources export --output my_sources.yaml
```

### Managing Source Health

```bash
# List only active sources
./threat-intel sources list --active

# List sources by tier
./threat-intel sources list --tier 1 --format json

# Disable problematic source
./threat-intel sources disable old_broken_source
```

## 📊 Data Export Examples

### Exporting Recent Articles

```bash
# Export last 7 days as JSON
./threat-intel export --days 7 --format json --output weekly_intel.json

# Export from specific source
./threat-intel export --source crowdstrike_blog --days 30 --format csv --output crowdstrike_month.csv

# Export high-quality articles only (using jq for filtering)
./threat-intel export --days 7 --format json | \
  jq '[.[] | select(.metadata.quality_score > 0.7)]' > high_quality.json
```

### Creating Custom Reports

```bash
# Export with specific fields for analysis
./threat-intel export --days 30 --format json | \
  jq '[.[] | {title: .title, url: .url, published: .published_at, source: .source_id, tags: .tags}]' \
  > monthly_summary.json

# Count articles by source
./threat-intel export --days 7 --format json | \
  jq 'group_by(.source_id) | map({source: .[0].source_id, count: length}) | sort_by(.count) | reverse'
```

## 🔧 Advanced Configuration Examples

### Custom Source Configuration

Create `config/custom_sources.yaml`:

```yaml
version: "1.0"

sources:
  # High-priority government source
  - id: "cisa_advisories"
    name: "CISA Security Advisories"
    url: "https://www.cisa.gov/news-events/cybersecurity-advisories"
    rss_url: ""
    tier: 2
    weight: 2.0  # Maximum priority
    check_frequency: 1800  # Check every 30 minutes
    active: true
    scope:
      allow: ["cisa.gov"]
      post_url_regex: ["^https://www\\.cisa\\.gov/news-events/cybersecurity-advisories/.*"]
    discovery:
      strategies:
        - listing:
            urls: ["https://www.cisa.gov/news-events/cybersecurity-advisories"]
            post_link_selector: "a[href*='/cybersecurity-advisories/']"
            max_pages: 5
    extract:
      prefer_jsonld: true
      title_selectors: ["h1", ".page-title", "meta[property='og:title']::attr(content)"]
      date_selectors:
        - "meta[property='article:published_time']::attr(content)"
        - ".published-date"
        - "time[datetime]::attr(datetime)"
      body_selectors: [".field--name-body", "article", "main"]
      author_selectors: [".author", "meta[name='author']::attr(content)"]

  # Custom threat hunting blog
  - id: "custom_threat_blog"
    name: "Custom Threat Hunting Blog"
    url: "https://threathunting.example.com/blog"
    rss_url: "https://threathunting.example.com/feed"
    tier: 1
    weight: 1.8
    check_frequency: 3600
    active: true
```

### Environment-Specific Settings

```bash
# Development environment
export DATABASE_URL="sqlite:///dev_threat_intel.db"
export SOURCES_CONFIG="config/dev_sources.yaml"

# Production environment
export DATABASE_URL="postgresql://threat_intel:password@db-server:5432/threat_intel_prod"
export SOURCES_CONFIG="config/prod_sources.yaml"
export USER_AGENT="ThreatIntelProd/1.0 (+https://company.com/security)"

# Run with environment-specific settings
./threat-intel init
```

## 🛠️ Troubleshooting Examples

### Debugging Failed Sources

```bash
# Test specific problematic source with debug output
./threat-intel --debug test --source problematic_source

# Check source health status
./threat-intel sources list --format json | jq '.[] | select(.consecutive_failures > 0)'

# Manually re-enable a disabled source
./threat-intel sources enable previously_disabled_source
```

### Database Maintenance

```bash
# View database statistics
./threat-intel stats

# Clean up old data (if implemented)
./threat-intel cleanup --days 180

# Backup database (SQLite)
cp threat_intel.db threat_intel_backup_$(date +%Y%m%d).db

# Reset and reinitialize (WARNING: destroys all data)
rm threat_intel.db
./threat-intel init --config config/sources.yaml
```

## 🔍 Analysis Examples

### Threat Keyword Analysis

```bash
# Find articles mentioning specific threats
./threat-intel export --days 30 --format json | \
  jq '.[] | select(.content | test("ransomware|malware|APT"; "i")) | {title, url, published_at}'

# Count articles by threat type
./threat-intel export --days 30 --format json | \
  jq '[.[] | select(.tags[]? | test("malware|ransomware|apt"; "i"))] | group_by(.tags[0]) | map({threat_type: .[0].tags[0], count: length})'
```

### Source Performance Analysis

```bash
# Analyze collection patterns
./threat-intel export --days 7 --format json | \
  jq 'group_by(.source_id) | map({
    source: .[0].source_id,
    articles: length,
    avg_quality: ([.[].metadata.quality_score // 0] | add / length),
    latest: (.[].published_at | max)
  }) | sort_by(.articles) | reverse'
```

### Time-based Analysis

```bash
# Articles published by day
./threat-intel export --days 30 --format json | \
  jq 'group_by(.published_at[:10]) | map({date: .[0].published_at[:10], count: length}) | sort_by(.date)'

# Peak publishing hours
./threat-intel export --days 7 --format json | \
  jq '[.[] | .published_at[11:13]] | group_by(.) | map({hour: .[0], count: length}) | sort_by(.hour)'
```

## 🎮 Integration Examples

### Webhook Integration (Custom Script)

Create `scripts/webhook_processor.py`:

```python
#!/usr/bin/env python3
import json
import requests
import subprocess
import sys

def send_to_webhook(articles, webhook_url):
    """Send new articles to a webhook endpoint."""
    if not articles:
        return
    
    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'articles_count': len(articles),
        'articles': articles[:5]  # Send first 5 articles
    }
    
    try:
        response = requests.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        print(f"Sent {len(articles)} articles to webhook")
    except Exception as e:
        print(f"Webhook failed: {e}")

# Usage in monitoring script
if __name__ == "__main__":
    # Run collection and capture output
    result = subprocess.run([
        "./threat-intel", "collect", "--format", "json"
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        articles = json.loads(result.stdout)
        send_to_webhook(articles, "https://your-webhook-url.com/threat-intel")
```

### SIEM Integration

```bash
# Export in SIEM-friendly format
./threat-intel export --days 1 --format json | \
  jq '.[] | {
    "@timestamp": .published_at,
    "event.kind": "alert",
    "event.category": ["threat"],
    "threat.indicator.type": "url",
    "threat.indicator.url.full": .url,
    "message": .title,
    "source.ip": .source_id,
    "tags": .tags
  }' > siem_feed.json

# Send to Elasticsearch
curl -H "Content-Type: application/json" \
     -X POST "http://elasticsearch:9200/threat-intel/_bulk" \
     --data-binary "@siem_feed.json"
```

### Slack/Teams Notifications

Create `scripts/notify_slack.sh`:

```bash
#!/bin/bash

# Collect new articles and format for Slack
NEW_ARTICLES=$(./threat-intel collect --dry-run --format json | jq length)

if [ "$NEW_ARTICLES" -gt 0 ]; then
    MESSAGE="🚨 *Threat Intelligence Update*\nFound $NEW_ARTICLES new articles.\n\nRun \`./threat-intel stats\` for details."
    
    curl -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"$MESSAGE\"}" \
        "$SLACK_WEBHOOK_URL"
fi
```

## 🔄 Automation Examples

### Cron Job Setup

```bash
# Edit crontab
crontab -e

# Add these lines for automated collection
# Collect every 2 hours
0 */2 * * * cd /path/to/CTIScraper && ./threat-intel collect >> logs/collect.log 2>&1

# Daily statistics report
0 8 * * * cd /path/to/CTIScraper && ./threat-intel stats > logs/daily_stats.log

# Weekly cleanup and backup
0 2 * * 0 cd /path/to/CTIScraper && cp threat_intel.db backups/backup_$(date +\%Y\%m\%d).db
```

### Systemd Service (Linux)

Create `/etc/systemd/system/threat-intel.service`:

```ini
[Unit]
Description=Threat Intelligence Aggregator
After=network.target

[Service]
Type=simple
User=threat-intel
WorkingDirectory=/opt/threat-intel-aggregator
ExecStart=/opt/threat-intel-aggregator/threat-intel monitor --interval 600
Restart=always
RestartSec=30
Environment=DATABASE_URL=postgresql://threat_intel:password@localhost/threat_intel
Environment=SOURCES_CONFIG=/opt/threat-intel-aggregator/config/prod_sources.yaml

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl enable threat-intel.service
sudo systemctl start threat-intel.service

# Check status
sudo systemctl status threat-intel.service
```

## 📈 Performance Optimization Examples

### High-Volume Configuration

For collecting from many sources:

```bash
# Use PostgreSQL for better performance
export DATABASE_URL="postgresql://user:pass@localhost/threat_intel"

# Increase concurrency
./threat-intel monitor --interval 300 --max-concurrent 10

# Batch process articles
./threat-intel collect --batch-size 200
```

### Resource Monitoring

```bash
# Monitor system resources during collection
top -p $(pgrep -f threat-intel)

# Monitor database size
du -h threat_intel.db

# Check network usage
iftop -i eth0
```

These examples should cover most common use cases. Adapt them to your specific environment and requirements!
