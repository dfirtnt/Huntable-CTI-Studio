# Huntable CTI Studio Browser Extension

A browser extension that sends articles directly to your Huntable CTI Studio instance for
threat intelligence analysis, with optional in-browser OCR / Vision LLM text extraction
from page images.

Full usage, configuration, image text extraction modes, and troubleshooting are documented
in [`docs/guides/browser-extension.md`](../docs/guides/browser-extension.md) — that page is
the canonical, actively maintained reference. This file exists only so the extension
directory is self-describing; keep it in sync by editing the linked doc, not this file.

## Quick start

1. Open `chrome://extensions/`, enable **Developer mode**, click **Load unpacked**, and
   select this `browser-extension/` directory.
2. Click the extension icon, set the **API URL** to your Huntable CTI Studio instance
   (default `http://127.0.0.1:8001`).
3. Navigate to an article, click the extension icon, then **Send to Huntable CTI Studio**.

### File Structure

```
browser-extension/
  manifest.json       # MV3 extension manifest
  popup.html          # Extension popup UI
  popup.js            # Popup logic, OCR, image extraction
  background.js       # Service worker for API calls
  content.js           # Content script for page extraction (optional)
  icons/               # Extension icons
  tesseract*.wasm      # Bundled Tesseract.js OCR engine
```
