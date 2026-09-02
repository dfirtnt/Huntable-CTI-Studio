"""No browser-side code may pull a credential out of the settings API.

`queue.js` used to read `WORKFLOW_OPENAI_API_KEY` (falling back to
`OPENAI_API_KEY`) out of `GET /api/settings` and forward it to the Sigma enrich
and validate endpoints as an `X-*-API-Key` header. That is the pattern the
settings-masking change exists to end: the routes now resolve the stored key
server-side, so no page needs the value at all.

A static guard, because the failure it protects against is someone re-adding a
convenient `settings.OPENAI_API_KEY` read during unrelated work. That would
compile, pass every behavioural test (the server-side fallback still works), and
quietly put a live credential back into the DOM -- there is no runtime assertion
that would notice.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATIC_JS = _REPO_ROOT / "src" / "web" / "static" / "js"
_TEMPLATES = _REPO_ROOT / "src" / "web" / "templates"

# Keys `settings._is_sensitive_setting` masks. A page reading one of these back
# would only ever receive null now, so any such read is either dead or a mistake.
_CREDENTIAL_KEYS = (
    "GITHUB_TOKEN",
    "LANGFUSE_SECRET_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "WORKFLOW_OPENAI_API_KEY",
    "WORKFLOW_ANTHROPIC_API_KEY",
    "HUGGINGFACE_API_TOKEN",
)

# settings.html legitimately names these keys: it POSTs new values and reads the
# configured/hint metadata. It never reads `.value` for one -- that contract is
# enforced behaviourally by tests/playwright/settings_credentials.spec.ts.
_ALLOWED_FILES = {"settings.html"}


def _client_side_sources() -> list[Path]:
    files = [p for p in _STATIC_JS.rglob("*.js") if "node_modules" not in p.parts]
    files += [p for p in _TEMPLATES.rglob("*.html")]
    return [p for p in files if p.name not in _ALLOWED_FILES]


def _reads_from_settings_payload(text: str, key: str) -> list[str]:
    """Find `something.KEY` / `something['KEY']` reads off a settings-shaped object."""
    patterns = (
        rf"\bsettings\s*\.\s*{key}\b",
        rf"\bsettings\s*\[\s*['\"]{key}['\"]\s*\]",
        rf"\bdata\s*\.\s*settings\s*\.\s*{key}\b",
    )
    hits: list[str] = []
    for pattern in patterns:
        hits.extend(match.group(0) for match in re.finditer(pattern, text))
    return hits


class TestNoClientSideCredentialReads:
    def test_no_page_reads_a_masked_key_out_of_the_settings_payload(self):
        offenders: dict[str, list[str]] = {}
        for path in _client_side_sources():
            text = path.read_text(encoding="utf-8", errors="replace")
            for key in _CREDENTIAL_KEYS:
                hits = _reads_from_settings_payload(text, key)
                if hits:
                    offenders.setdefault(str(path.relative_to(_REPO_ROOT)), []).extend(hits)

        assert not offenders, (
            "client-side code is reading credential values out of the settings payload; "
            f"the server resolves these now: {offenders}"
        )

    def test_queue_js_sends_no_provider_key_header(self):
        """The two enrich/validate call sites that used to forward the key."""
        queue_js = (_STATIC_JS / "workflow" / "queue.js").read_text(encoding="utf-8")

        for header in ("X-OpenAI-API-Key", "X-Anthropic-API-Key"):
            assert header not in queue_js, f"queue.js still forwards {header} from the browser"

    def test_no_page_calls_the_github_api_directly(self):
        """The PAT reached a third-party origin from the page; it is server-side now."""
        # lgtm[py/incomplete-url-substring-sanitization] -- substring absence check on
        # trusted, repo-controlled source files, not URL sanitization of untrusted input.
        offenders = [
            str(path.relative_to(_REPO_ROOT))
            for path in _client_side_sources()
            if "api.github.com" in path.read_text(encoding="utf-8", errors="replace")
        ]
        settings_html = (_TEMPLATES / "settings.html").read_text(encoding="utf-8")
        # lgtm[py/incomplete-url-substring-sanitization] -- same as above.
        if "api.github.com" in settings_html:
            offenders.append("src/web/templates/settings.html")

        assert not offenders, f"a page is calling api.github.com directly with the stored token: {offenders}"

    def test_the_guard_itself_would_catch_a_regression(self):
        """Pin the detector, so a broken regex cannot make this file vacuous."""
        sample = "const apiKey = settings.WORKFLOW_OPENAI_API_KEY || settings['OPENAI_API_KEY'];"

        assert _reads_from_settings_payload(sample, "WORKFLOW_OPENAI_API_KEY")
        assert _reads_from_settings_payload(sample, "OPENAI_API_KEY")
        assert not _reads_from_settings_payload(sample, "GITHUB_TOKEN")
