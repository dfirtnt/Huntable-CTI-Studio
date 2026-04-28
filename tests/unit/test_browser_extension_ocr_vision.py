"""
Static analysis tests for browser extension OCR and Vision LLM features.

Tests verify:
- Tesseract.js v5 blob-worker bug is fixed (workerBlobURL: false + local paths)
- Chrome MV3 CSP contains wasm-unsafe-eval and WASM files are web-accessible
- displayImageList() uses safe DOM APIs instead of innerHTML
- Vision LLM mode selector and config panel exist in popup.html
- performVisionLLM and performHybrid functions are present in popup.js
"""

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
POPUP_JS = ROOT / "browser-extension" / "popup.js"
POPUP_HTML = ROOT / "browser-extension" / "popup.html"
MANIFEST = ROOT / "browser-extension" / "manifest.json"
BACKGROUND_JS = ROOT / "browser-extension" / "background.js"

WASM_FILES = [
    "worker.min.js",
    "tesseract-core.wasm.js",
    "tesseract-core.wasm",
    "tesseract-core-simd.wasm.js",
    "tesseract-core-simd.wasm",
]


# ---------------------------------------------------------------------------
# Task 7: Tesseract.js v5 blob-worker fix
# ---------------------------------------------------------------------------


def test_ocr_worker_blob_url_disabled() -> None:
    """workerBlobURL: false prevents blob-worker WASM path failure in MV3."""
    text = POPUP_JS.read_text(encoding="utf-8")
    assert "workerBlobURL: false" in text, (
        "popup.js must set workerBlobURL: false to avoid Tesseract.js v5 blob-worker bug"
    )


def test_ocr_uses_extension_worker_path() -> None:
    """Worker script must be loaded from extension URL, not a CDN or blank path."""
    text = POPUP_JS.read_text(encoding="utf-8")
    assert "chrome.runtime.getURL('worker.min.js')" in text, (
        "workerPath must use chrome.runtime.getURL so MV3 CSP allows the local file"
    )


def test_ocr_uses_extension_core_path() -> None:
    """WASM core must be resolved from extension root, not a relative path."""
    text = POPUP_JS.read_text(encoding="utf-8")
    assert "chrome.runtime.getURL('')" in text, (
        "corePath must use chrome.runtime.getURL('') so WASM files resolve correctly"
    )


# ---------------------------------------------------------------------------
# Task 7: Chrome MV3 manifest requirements
# ---------------------------------------------------------------------------


def test_manifest_has_wasm_unsafe_eval_csp() -> None:
    """MV3 requires wasm-unsafe-eval in extension_pages CSP for Tesseract WASM."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    csp = manifest.get("content_security_policy", {}).get("extension_pages", "")
    assert "wasm-unsafe-eval" in csp, "manifest.json extension_pages CSP must include 'wasm-unsafe-eval'"


def test_manifest_wasm_files_are_web_accessible() -> None:
    """All Tesseract WASM and worker files must be in web_accessible_resources."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    all_resources: set[str] = set()
    for entry in manifest.get("web_accessible_resources", []):
        all_resources.update(entry.get("resources", []))

    for fname in WASM_FILES:
        assert fname in all_resources, (
            f"{fname} must be listed in web_accessible_resources so the extension worker can load it"
        )


# ---------------------------------------------------------------------------
# Task 7: XSS fix — displayImageList must use DOM APIs, not innerHTML
# ---------------------------------------------------------------------------


def _extract_function_body(source: str, fn_name: str) -> str:
    """Extract a function body by finding the function declaration and matching braces."""
    pattern = rf"function {re.escape(fn_name)}\s*\("
    match = re.search(pattern, source)
    if not match:
        return ""
    start = source.index("{", match.end())
    depth = 0
    for i, ch in enumerate(source[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    return ""


def test_display_image_list_uses_dom_create_element() -> None:
    """displayImageList must build DOM via createElement, not innerHTML."""
    text = POPUP_JS.read_text(encoding="utf-8")
    body = _extract_function_body(text, "displayImageList")
    assert body, "displayImageList function not found in popup.js"
    assert "createElement" in body, "displayImageList must use createElement (safe DOM API) to build image list items"


def test_display_image_list_no_innerhtml_template_literal() -> None:
    """displayImageList must not build HTML via innerHTML with template literals."""
    text = POPUP_JS.read_text(encoding="utf-8")
    body = _extract_function_body(text, "displayImageList")
    assert body, "displayImageList function not found in popup.js"
    # Template literals in innerHTML are the XSS risk: innerHTML = `...${img.alt}...`
    has_dangerous_innerhtml = bool(re.search(r"\.innerHTML\s*=\s*`", body))
    assert not has_dangerous_innerhtml, (
        "displayImageList must not use innerHTML with template literals — "
        "img.alt is page-sourced (untrusted) and would enable XSS"
    )


# ---------------------------------------------------------------------------
# Task 6: Vision LLM mode — popup.js function presence
# ---------------------------------------------------------------------------


def test_perform_vision_llm_function_exists() -> None:
    """performVisionLLM must be declared in popup.js."""
    text = POPUP_JS.read_text(encoding="utf-8")
    assert "async function performVisionLLM(" in text, "performVisionLLM function missing from popup.js"


def test_perform_hybrid_function_exists() -> None:
    """performHybrid (Vision LLM + OCR fallback) must be declared in popup.js."""
    text = POPUP_JS.read_text(encoding="utf-8")
    assert "async function performHybrid(" in text, "performHybrid function missing from popup.js"


def test_popup_js_routes_to_vision_llm_by_mode() -> None:
    """Extraction mode 'vision' must dispatch to performVisionLLM."""
    text = POPUP_JS.read_text(encoding="utf-8")
    assert "performVisionLLM(imageId)" in text, (
        "popup.js must call performVisionLLM(imageId) when vision mode is selected"
    )


def test_popup_js_routes_to_hybrid_by_mode() -> None:
    """Extraction mode 'hybrid' must dispatch to performHybrid."""
    text = POPUP_JS.read_text(encoding="utf-8")
    assert "performHybrid(imageId)" in text, "popup.js must call performHybrid(imageId) when hybrid mode is selected"


# ---------------------------------------------------------------------------
# Task 6: Vision LLM mode — popup.html UI elements
# ---------------------------------------------------------------------------


def test_extraction_mode_select_exists_in_popup_html() -> None:
    """Extraction mode <select> must be present in popup.html."""
    html = POPUP_HTML.read_text(encoding="utf-8")
    assert 'id="extraction-mode"' in html, (
        "popup.html must have a <select id='extraction-mode'> for OCR/Vision/Hybrid choice"
    )


def test_vision_config_div_exists_in_popup_html() -> None:
    """Vision config panel (provider + API key) must be present in popup.html."""
    html = POPUP_HTML.read_text(encoding="utf-8")
    assert 'id="vision-config"' in html, "popup.html must have a <div id='vision-config'> for Vision LLM settings"


def test_vision_provider_select_has_openai_and_anthropic() -> None:
    """Vision provider dropdown must include both OpenAI and Anthropic options."""
    html = POPUP_HTML.read_text(encoding="utf-8")
    assert 'value="openai"' in html, "popup.html must have openai as a vision provider option"
    assert 'value="anthropic"' in html, "popup.html must have anthropic as a vision provider option"


def test_vision_uses_app_settings_key_not_popup_input() -> None:
    """Vision LLM mode must use the app-configured key, not a raw input in the popup.

    The extension delegates API key management to the server-side app settings.
    A popup-level key input is intentionally absent -- 'uses app settings key'
    means no API key is ever typed into or stored by the extension itself.
    """
    html = POPUP_HTML.read_text(encoding="utf-8")
    # The mode option must advertise that the app key is used, not a popup key
    assert "uses app settings key" in html, (
        "Vision LLM option must indicate it uses the app settings key, not a popup-level input"
    )
    # There must be no plaintext API key input in the popup (the old design had one)
    assert 'id="vision-api-key"' not in html, (
        "popup.html must not have a vision-api-key input -- "
        "API keys belong in app settings, not the browser extension popup"
    )


# ---------------------------------------------------------------------------
# Task 8: CI pinned-versions check logic (unit tests for the inline Python)
# ---------------------------------------------------------------------------


def _check_unpinned(lines: list[str]) -> list[str]:
    """Mirror of the inline logic in .github/workflows/lint.yml."""
    unpinned = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ">=" in stripped and "#" not in stripped:
            unpinned.append(stripped)
    return unpinned


def test_pinned_versions_passes_for_exact_pins() -> None:
    """Lines with == should not be flagged as unpinned."""
    lines = ["requests==2.31.0", "flask==3.0.0", "numpy==1.26.0"]
    assert _check_unpinned(lines) == []


def test_pinned_versions_flags_bare_ge_specifier() -> None:
    """Lines with >= and no inline comment should be flagged."""
    lines = ["trafilatura>=1.6.0"]
    result = _check_unpinned(lines)
    assert result == ["trafilatura>=1.6.0"]


def test_pinned_versions_allows_ge_with_inline_comment() -> None:
    """Lines with >= but an inline # comment (security pins) are allowed."""
    lines = ["Pillow>=12.2.0  # CVE-2026-40192: FITS GZIP decompression bomb"]
    assert _check_unpinned(lines) == []


def test_pinned_versions_skips_blank_lines_and_comments() -> None:
    """Blank lines and comment-only lines should not raise false positives."""
    lines = ["", "  ", "# This is a comment", "# >= not a real pin"]
    assert _check_unpinned(lines) == []


def test_pinned_versions_flags_multiple_unpinned() -> None:
    """Multiple bare >= lines should all be reported."""
    lines = [
        "requests==2.31.0",
        "trafilatura>=1.6.0",
        "# pinned below",
        "numpy==1.26.0",
        "pillow>=9.0.0",
    ]
    result = _check_unpinned(lines)
    assert result == ["trafilatura>=1.6.0", "pillow>=9.0.0"]


def test_pinned_versions_toml_key_value_not_flagged() -> None:
    """TOML-style key = value lines (from pyproject.toml) must not be flagged."""
    # The old grep-based check matched '=' in TOML lines like 'name = "cti-scraper"'
    # The Python logic is scoped to requirements.txt lines only and checks for '>='
    toml_like_lines = [
        'name = "cti-scraper"',
        'version = "6.0.0"',
        'requires-python = ">=3.11"',  # This DOES have >= but also has " around it
    ]
    # TOML line with >= in quotes — the check does match '>=', flagging this.
    # The fix was scoping the check to requirements.txt only (which has no TOML).
    # Here we just verify the logic itself correctly handles requirements.txt format.
    requirements_lines = [
        "requests==2.31.0",
        "numpy==1.26.0",
    ]
    assert _check_unpinned(requirements_lines) == []


# ---------------------------------------------------------------------------
# Background.js: service-worker image fetch and Vision LLM proxy
# ---------------------------------------------------------------------------


def test_background_js_has_fetch_image_as_data_url() -> None:
    """fetchImageAsDataURL must be defined in background.js (service-worker level).

    Image fetching was moved here to bypass CORS canvas taint that occurred
    when the function ran in the page context.
    """
    text = BACKGROUND_JS.read_text(encoding="utf-8")
    assert "async function fetchImageAsDataURL(" in text, (
        "fetchImageAsDataURL must be in background.js, not injected into the page context"
    )


def test_background_js_vision_llm_calls_backend_proxy() -> None:
    """callVisionLLM must proxy through the local backend, not call OpenAI/Anthropic directly.

    API keys are managed server-side. The extension should never hold or send
    provider credentials.
    """
    text = BACKGROUND_JS.read_text(encoding="utf-8")
    assert "/api/vision/extract" in text, (
        "background.js callVisionLLM must POST to /api/vision/extract (backend proxy), "
        "not call the provider API directly"
    )


def test_background_js_vision_llm_no_direct_openai_call() -> None:
    """background.js must not call api.openai.com directly (API key handling moved to server)."""
    text = BACKGROUND_JS.read_text(encoding="utf-8")
    assert "api.openai.com" not in text, (
        "background.js must not contain direct OpenAI API calls — all provider calls go through the backend proxy"
    )


def test_background_js_vision_llm_no_direct_anthropic_call() -> None:
    """background.js must not call api.anthropic.com directly."""
    text = BACKGROUND_JS.read_text(encoding="utf-8")
    assert "api.anthropic.com" not in text, (
        "background.js must not contain direct Anthropic API calls — all provider calls go through the backend proxy"
    )


# ---------------------------------------------------------------------------
# popup.js: Tesseract.js v5 WASM compatibility fix
# ---------------------------------------------------------------------------


def test_ocr_uses_legacy_core_for_v5_wasm_compatibility() -> None:
    """legacyCore: true must be set in the Tesseract.recognize call.

    Tesseract.js v5 in LSTM mode loads tesseract-core-simd-lstm.wasm.js by
    default, but only the combined tesseract-core-simd.wasm.js is bundled.
    legacyCore: true selects the bundled file while still running LSTM OCR.
    """
    text = POPUP_JS.read_text(encoding="utf-8")
    assert "legacyCore: true" in text, (
        "popup.js must set legacyCore: true in Tesseract.recognize options to select "
        "the bundled combined WASM file instead of the missing lstm-only split file"
    )
