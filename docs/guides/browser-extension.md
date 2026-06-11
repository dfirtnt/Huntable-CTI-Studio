# Browser Extension

The browser extension lets you send any article to Huntable CTI Studio with one click — no manual URL entry needed.

## Installation

1. Open Chrome/Edge and go to `chrome://extensions/`
2. Enable **Developer mode** (toggle in top right)
3. Click **Load unpacked** and select the `browser-extension/` directory in the project root
4. The extension icon appears in your browser toolbar

!!! tip "Icon placeholders"
    Run `./scripts/generate_extension_icons.sh` to create proper icon files if you see missing-image placeholders in the toolbar.

## Usage

1. Navigate to any article you want to analyze
2. Click the extension icon in your browser toolbar
3. Review the extracted content (title, URL, word count)
4. Click **Send to Huntable CTI Studio**
5. The processed article opens in your instance automatically

The extension extracts article content from the page using smart selectors (works on news, blogs, security research, government advisories like CISA, and technical docs).

## Configuration

Click the extension icon to access these settings:

| Setting | Description |
|---|---|
| **API URL** | Your Huntable CTI Studio instance URL (default: `http://127.0.0.1:8001`) |
| **Force scrape** | Scrape even if the URL already exists in the database |

Settings persist in `chrome.storage.local` across sessions.

## Image Text Extraction

The extension can extract text from images on the page using three modes:

| Mode | Description | Requirements |
|---|---|---|
| **OCR** (local, free) | Runs Tesseract.js WASM in-browser | None — fully offline |
| **Vision LLM** | Uses GPT-4o Vision or Claude via your app's API key | LLM provider configured in Settings |
| **Hybrid** | Vision LLM first, falls back to OCR on failure | Both of the above |

Vision LLM providers (`openai` or `anthropic`) are selected in the extension popup. The API key is resolved server-side by the backend proxy — the extension never stores or transmits API keys.

Extracted image text is appended to the article content as `[Image OCR: <alt text>]` blocks before sending.

## How It Works

The extension calls `POST /api/scrape-url` on your instance with the page title, URL, and extracted content (including any OCR text). The backend processes the article through the standard ingestion pipeline — threat hunting scoring and all.

## Non-Routable IP Protection

The extension blocks ingestion from private/local IP addresses (`127.0.0.1`, `192.168.x.x`, `10.x.x.x`, link-local, and IPv6 equivalents). This prevents accidental ingestion of internal documentation or localhost content. The API URL field also rejects non-routable addresses.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "Unable to extract article data" | Content script injection blocked by page CSP |
| "Non-routable IP" error | Current page is served from a private IP |
| "Content too short" | Page has fewer than 50 words of extractable text |
| API errors | Huntable CTI Studio not running on the configured URL |

Check the browser console (Chrome DevTools -> Console) for debug log lines prefixed with `CTIScraper Debug:`.

## File Structure

```
browser-extension/
  manifest.json       # MV3 extension manifest
  popup.html          # Extension popup UI
  popup.js            # Popup logic, OCR, image extraction
  background.js       # Service worker for API calls
  content.js          # Content script for page extraction (optional)
  icons/              # Extension icons
  tesseract*.wasm     # Bundled Tesseract.js OCR engine
```
