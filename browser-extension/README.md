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
  icons/               # Extension icons
  tesseract*.wasm      # Bundled Tesseract.js OCR engine
```

## Vendored dependencies

The OCR engine files below are copied, unmodified, from npm. Each file was verified
byte-for-byte (sha256) against the published npm tarball of the listed version.

| File | Upstream package | Version | sha256 | Upstream |
|------|------------------|---------|--------|----------|
| `tesseract.min.js` | `tesseract.js` (`dist/tesseract.min.js`) | 5.1.1 | `a8e29918d098b2b06e1012bdaeffb4aec0445c5d5654709023e0bd1f442a80e8` | https://www.npmjs.com/package/tesseract.js/v/5.1.1 |
| `worker.min.js` | `tesseract.js` (`dist/worker.min.js`) | 5.1.1 | `aca1229639fc9907d86f96e825955a2b7c5716d17f3bc3acd71f9c7ab66181fc` | https://www.npmjs.com/package/tesseract.js/v/5.1.1 |
| `tesseract-core.wasm.js` | `tesseract.js-core` | 5.1.1 | `2b8c8c92b8788807061fb4bb16c5acdf000c149e100255f879f78d2c58ca9969` | https://www.npmjs.com/package/tesseract.js-core/v/5.1.1 |
| `tesseract-core.wasm` | `tesseract.js-core` | 5.1.1 | `b47a852b19181ae0999f9d970c368cd351135a320ea978b35bd38602d8bcc0bc` | https://www.npmjs.com/package/tesseract.js-core/v/5.1.1 |
| `tesseract-core-simd.wasm.js` | `tesseract.js-core` | 5.1.1 | `63f232c4f7a97b04e52eb940202700b2c6239783a75d0ff0553274fac530cd5c` | https://www.npmjs.com/package/tesseract.js-core/v/5.1.1 |
| `tesseract-core-simd.wasm` | `tesseract.js-core` | 5.1.1 | `baa2f54ef5af43ada4605fd7ae999bde3c6ecc96bfe0d0410b0b4f4a5f9c8b91` | https://www.npmjs.com/package/tesseract.js-core/v/5.1.1 |

- Vendored in commit `8228383` (2026-09-03). No later commit changes these files.
- No `traineddata` (language) files are vendored. The worker fetches language data from
  jsDelivr at runtime (`cdn.jsdelivr.net/npm/@tesseract.js-data/`).

To upgrade: `npm pack tesseract.js@<ver>` and `npm pack tesseract.js-core@<ver>`, then copy
`package/dist/tesseract.min.js` and `package/dist/worker.min.js` from the first tarball, and
`package/tesseract-core*.wasm` plus `package/tesseract-core*.wasm.js` from the second. Update
the table hashes (`sha256sum`) in the same commit.
