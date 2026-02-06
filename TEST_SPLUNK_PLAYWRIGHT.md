# Testing Splunk Playwright Scraping

## Quick Test

Run the test script in Docker:

```bash
# If using docker-compose.dev2.yml
docker exec cti_web_dev2 python3 scripts/test_splunk_playwright.py

# Or if using standard docker-compose.yml
docker exec cti_web python3 scripts/test_splunk_playwright.py
```

## Using CLI Collect Command

Test via the CLI collect command:

```bash
# In Docker container
docker exec cti_web_dev2 python3 -m src.cli.main collect --source splunk_security_blog --dry-run

# Or via run_cli.sh
./run_cli.sh collect --source splunk_security_blog --dry-run
```

## Expected Results

✅ **Success indicators:**
- Method should be `playwright_scraping`
- Articles should be found (at least 1)
- Content length should be > 2000 chars
- No errors in logs

## Troubleshooting

If Playwright browsers aren't installed:
```bash
docker exec cti_web_dev2 playwright install chromium
```

If test fails with import errors, ensure you're running in Docker container with all dependencies installed.
