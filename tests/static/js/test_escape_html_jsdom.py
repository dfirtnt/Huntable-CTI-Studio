"""jsdom-backed unit tests for the shared ``escapeHtml`` helper in utils.js.

Context: ``fix(web): escape client-side innerHTML sinks on three pages`` routed
every ``${...}`` interpolation in the dashboard, hunt-metrics and article-detail
``innerHTML`` builders through the global ``escapeHtml`` (src/web/static/js/utils.js).
The escaping was applied *uniformly* -- including to fields that are not obviously
tainted -- on the stated premise that ``escapeHtml`` is "a no-op on markup-free
values and is null/number-safe". Several newly-wrapped values are numbers
(``score``, ``keyword.match_count``, ``article.hunt_score``) or may be absent, and
one lands in an HTML *attribute* (``title="${escapeHtml(comparison.chunk_text)}"``).

``tests/unit/test_template_escaping_contract.py`` proves the wrapper is *present*
in the templates, and the Playwright specs prove one string payload renders inert.
Neither pins the behaviour the fix now depends on: that ``escapeHtml`` stringifies
numbers (so ``escapeHtml(0)`` is ``"0"`` not ``""``), maps null/undefined to the
empty string (so blanket-escaping an absent field does not throw or print
``"undefined"``), and escapes BOTH quote characters (so the attribute sink cannot
be broken out of). If a future edit "simplifies" ``escapeHtml`` to assume string
input or drop quote escaping, those widgets silently break or regress and no other
test would catch it. These tests lock that contract at unit speed, no browser or
dev server required.

Run: python3 run_tests.py unit  (or)  pytest tests/static/js/test_escape_html_jsdom.py
Requires node + jsdom (shared harness venv at tests/static/js/jsdom_venv).
"""

import json
import os
import subprocess

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_HARNESS_DIR = os.path.dirname(__file__)
_JSDOM_DIR = os.path.join(_HARNESS_DIR, "jsdom_venv")
_NODE_MODULES = os.path.join(_JSDOM_DIR, "node_modules")
_UTILS_JS = os.path.join(_REPO_ROOT, "src/web/static/js/utils.js")


def _ensure_jsdom():
    # jsdom is a dev-only harness dependency, shared with test_modal_aria_jsdom.py.
    if os.path.isdir(os.path.join(_NODE_MODULES, "jsdom")):
        return
    os.makedirs(_JSDOM_DIR, exist_ok=True)
    pkg = os.path.join(_JSDOM_DIR, "package.json")
    if not os.path.exists(pkg):
        with open(pkg, "w", encoding="utf-8") as fh:
            fh.write('{\n  "name": "escape-html-jsdom-harness",\n  "version": "1.0.0",\n  "private": true\n}\n')
    subprocess.run(
        ["npm", "install", "jsdom@24", "--no-audit", "--no-fund"],
        cwd=_JSDOM_DIR,
        check=True,
    )


def _escape_html(values: list) -> list[str]:
    """Load the real utils.js into jsdom and return escapeHtml(v) for each value.

    ``values`` is JSON-encoded and handed to the driver so Python controls the
    exact inputs (including null via ``None``); the driver prints one JSON line per
    result which we decode back, keeping the round-trip lossless.
    """
    _ensure_jsdom()
    harness = r"""
    const { JSDOM } = require('jsdom');
    const fs = require('fs');
    const utilsSrc = fs.readFileSync(process.argv[2], 'utf8');
    const inputs = JSON.parse(process.argv[3]);
    const out = [];
    const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', { runScripts: 'dangerously', pretendToBeVisual: true });
    const { window } = dom;
    try {
        const s = window.document.createElement('script');
        s.textContent = utilsSrc;
        window.document.body.appendChild(s);
        const fn = window.escapeHtml;
        out.push('TYPE:' + typeof fn);
        for (const v of inputs) {
            // JSON has no undefined; the sentinel string requests the real undefined.
            const arg = (v === '__UNDEFINED__') ? undefined : v;
            out.push('VAL:' + JSON.stringify(fn(arg)));
        }
    } catch (e) {
        out.push('HARNESS_ERR ' + (e && e.stack ? e.stack : e));
    }
    process.stdout.write(out.join('\n'));
    """
    harness_path = os.path.join(_JSDOM_DIR, "_escape_html_harness.js")
    with open(harness_path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    result = subprocess.run(
        ["node", harness_path, _UTILS_JS, json.dumps(values)],
        cwd=_JSDOM_DIR,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "NODE_PATH": _NODE_MODULES},
    )
    lines = result.stdout.splitlines()
    assert lines and lines[0] == "TYPE:function", f"escapeHtml did not load as a function: {result.stdout}"
    assert not any(line.startswith("HARNESS_ERR") for line in lines), result.stdout
    return [json.loads(line[len("VAL:") :]) for line in lines if line.startswith("VAL:")]


def test_escape_html_is_number_safe():
    """The fix wraps numeric fields (score/match_count/hunt_score); they must stringify, not vanish."""
    assert _escape_html([0, 75, -3, 4.5]) == ["0", "75", "-3", "4.5"]


def test_escape_html_maps_nullish_to_empty_string():
    """Blanket-escaping an absent field must yield '' -- never throw, never 'null'/'undefined'."""
    assert _escape_html([None, "__UNDEFINED__"]) == ["", ""]


def test_escape_html_is_a_noop_on_markup_free_values():
    assert _escape_html(["powershell.exe", "T1059.001", ""]) == ["powershell.exe", "T1059.001", ""]


def test_escape_html_neutralizes_tag_and_event_handler_markup():
    (escaped,) = _escape_html(["<img src=x onerror=alert(1)>"])
    assert "<" not in escaped and ">" not in escaped
    assert escaped == "&lt;img src=x onerror=alert(1)&gt;"


def test_escape_html_escapes_both_quote_characters_for_attribute_context():
    """title="${escapeHtml(...)}" is an attribute sink: a raw quote would break out."""
    assert _escape_html(['a"b', "a'b", "a&b"]) == ["a&quot;b", "a&#39;b", "a&amp;b"]


def test_escape_html_blocks_the_combined_attribute_breakout_payload():
    """The exact shape the chunk-dialog Playwright spec fires: no raw quote or angle bracket survives."""
    (escaped,) = _escape_html(['"><svg onload="x">'])
    assert '"' not in escaped
    assert "<" not in escaped and ">" not in escaped
    assert escaped == "&quot;&gt;&lt;svg onload=&quot;x&quot;&gt;"
