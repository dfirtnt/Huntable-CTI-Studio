# Source Healing Playbook

The diagnostic knowledge carried forward from the deprecated auto-healing
service. The probes establish ground truth about a source; the playbook maps
that truth to exactly one config fix.

## Table of contents

1. Probe recipes (run all five)
2. Diagnostic playbook (apply in order)
3. Platform capabilities (what the scraper can do)
4. Canonical config shapes (copy exactly)
5. What config cannot fix
6. Schema validity checks

---

## 1. Probe recipes

Run all five against the source's `url` and `rss_url`. Use a real browser
User-Agent — some CDNs reject default agents. Capture the raw output; the
operator should see the same evidence you reason from.

```
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
```

### Probe 1 — HTTP reachability + bot protection

```bash
curl -sS -A "$UA" -o /dev/null -w '%{http_code} %{url_effective}\n' -L "<URL>"
```

- Note the final effective URL. If it differs from the source `url` by domain,
  the site **migrated** → the fix is updating `url` to the redirect target.
- On `403`, retry once with full browser headers
  (`-H 'Accept: text/html,application/xhtml+xml,...'  -H 'Accept-Language: en-US,en;q=0.9'`).
  If the retry succeeds, it was UA filtering, not a hard block.
- If still blocked, inspect the body/headers for `cloudfront`, `akamai`,
  `x-amz-cf-id`, "request blocked", "access denied" → **bot protection**
  (see §5; config cannot fix this).

### Probe 2 — RSS / Atom content

```bash
curl -sS -A "$UA" "<RSS_URL>" | head -c 50000
```

- Count `<item` and `<entry` occurrences. **200 with zero items = an empty
  feed, which is broken, not working.**
- Extract the first few `<link>` / `href` values: these are the **real
  article URL pattern**. Use what you observe here for `post_url_regex` — never
  guess `/threat-research/` when the samples show `/research/`.

### Probe 3 — Sitemap discovery

```bash
curl -sS -A "$UA" "<BASE>/sitemap.xml"        | head -c 20000
curl -sS -A "$UA" "<BASE>/sitemap_index.xml"  | head -c 20000
curl -sS -A "$UA" "<BASE>/post-sitemap.xml"   | head -c 20000
curl -sS -A "$UA" "<BASE>/robots.txt"         | grep -i sitemap
```

- If a sitemap lists post URLs, that is a reliable discovery strategy and a
  ground-truth source of the URL pattern.

### Probe 4 — WordPress JSON API

```bash
curl -sS -A "$UA" "<BASE>/wp-json/wp/v2/posts?per_page=5" | head -c 5000
```

- If this returns a JSON array of posts with `link` fields, the WP-JSON fast
  path is the best fix: it bypasses HTML scraping and Playwright entirely.

### Probe 5 — Page content / JS-render detection

```bash
curl -sS -A "$UA" "<LISTING_URL>" -o /tmp/sh_page.html
wc -c /tmp/sh_page.html                                   # raw HTML size
python3 -c "import re,sys;h=open('/tmp/sh_page.html').read();import html;t=re.sub('<[^>]+>',' ',re.sub(r'(?is)<(script|style).*?>.*?</\1>',' ',h));print('visible_chars',len(' '.join(t.split())))"
grep -oE '<a [^>]*href="[^"]+"' /tmp/sh_page.html | grep -iE 'blog|post|article|research|20[0-9]{2}' | head -20
```

- **Large HTML but very short visible text (< ~500 chars) = JS-rendered.**
  Fix: `config.use_playwright: true`.
- The grepped anchors show whether a listing-page discovery strategy is viable
  and which CSS pattern the post links use.

---

## 2. Diagnostic playbook

Apply in this order; stop at the first rule whose evidence is present.

1. **RSS returns 200 but 0 items** → set `rss_url` to `null`. An empty feed
   blocks the fetcher on a dead tier; nulling it forces fallback to scraping.
2. **Page visible text very short but HTML large** → JS-rendered. Set
   `{"use_playwright": true}`.
3. **RSS has items** → read the sample URLs to learn the *actual* article path,
   and use exactly that in `post_url_regex`. Do not guess.
4. **Sitemap has post URLs** → learn the real pattern from sitemap samples
   before writing `post_url_regex`; consider a `sitemap` discovery strategy.
5. **WordPress site where wp-json returns posts** → configure the `wp_json`
   fast path (top-level config key — see §4). Preferred over Playwright.
6. **Listing page has visible post links** → add a `listing` discovery
   strategy with the observed CSS selector.
7. **Pages fetched but 0 content extracted** → fix `body_selectors`. Use a
   working source on the same platform as the model; the clean text the page
   actually contains tells you which elements hold the body.
8. **Redirect chain to a new domain** → update `url` to the final target.
9. **3+ attempts, same fundamental outcome** → report a platform limitation;
   stop permuting config.

---

## 3. Platform capabilities

- **Fetch tiers, in order:** RSS → Playwright (if `use_playwright: true`) →
  modern scraping → legacy scraping. Setting `rss_url` to `null` skips the RSS
  tier. If RSS is reachable but returns zero articles, the fetcher does **not**
  automatically fall through — that is why rule 1 nulls `rss_url`.
- **Discovery strategies** live under `config.discovery.strategies`. Two kinds:
  - `listing` — **requires both** `urls` (listing pages to crawl) and
    `post_link_selector` (CSS for post anchors). Missing either silently
    yields zero URLs. The key is `post_link_selector`, not `selector`.
  - `sitemap` — `{"sitemap": {"urls": ["https://site/post-sitemap.xml"]}}`.
- **`wp_json` is NOT a discovery strategy.** It is a top-level `config.wp_json`
  field read by the scraper's fast path. Placing it under
  `discovery.strategies` makes it a silent no-op — a common and costly mistake.

---

## 4. Canonical config shapes

Copy these shapes exactly; they are what the scraper actually reads.

**WP-JSON fast path** (best for WordPress; no Playwright needed):
```json
{"wp_json": {"endpoints": ["https://example.com/wp-json/wp/v2/posts?per_page=50"],
             "url_field_priority": ["link", "guid.rendered"]}}
```

**Listing discovery:**
```json
{"discovery": {"strategies": [{"listing": {"urls": ["https://example.com/blog/"],
                                            "post_link_selector": "h2.entry-title a"}}]}}
```

**Sitemap discovery:**
```json
{"discovery": {"strategies": [{"sitemap": {"urls": ["https://example.com/post-sitemap.xml"]}}]}}
```

**Enable JS rendering:**
```json
{"use_playwright": true}
```

**Force scrape fallback (dead RSS):** field change, not a config merge —
`rss_url = NULL`.

All config changes are **merged** into the existing `config`. Preserve every
key the fix does not explicitly change.

---

## 5. What config cannot fix

Report these as a diagnosis and stop — do not burn attempts trying config
permutations:

| Problem | Why config cannot fix it |
|---------|--------------------------|
| Bot protection (Cloudflare, Akamai, WAF, CloudFront) | The block is on the request, not the parser. Needs an operator decision (different access path), not a selector. |
| Missing Playwright browsers | Runtime dependency, not configuration. |
| Python exceptions / code bugs | Needs a developer fix. |
| Platform capability gap | The required strategy is not implemented in the scraper. |

For these, the correct output is a clear diagnosis plus the recommendation
(e.g. "Cloudflare bot protection on every request; cannot be healed via
config — consider deactivating or sourcing via RSS if one exists elsewhere").

---

## 6. Schema validity checks

Before proposing a `config` change, sanity-check it so a structurally invalid
fix never reaches the database:

- `wp_json` is at the **top level** of `config`, never under
  `discovery.strategies`.
- `listing` strategies include **both** `urls` and `post_link_selector`.
- `post_url_regex` values are valid regexes and reflect a URL pattern actually
  seen in probe output.
- `use_playwright` is a boolean.
- The proposed change is a **merge**: the full intended `config` still contains
  every pre-existing key.

Cross-check against `src/config/workflow_config_schema.py` and existing working
sources' configs when unsure — a working same-platform source is the best
template.
