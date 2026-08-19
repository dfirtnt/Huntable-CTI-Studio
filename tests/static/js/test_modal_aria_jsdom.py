"""jsdom-backed regression tests for modal ARIA injection (commit ca6f14a1).

These run without a browser or dev server. They confirm the actual static JS
files under src/web/static/js/ apply ARIA dialog semantics to dynamically created
modals:

  * ModalManager.confirm()/prompt() modals get role=dialog + aria-modal=true +
    a label (from options.title/heading text or humanized id).
  * ensureModalAria() is idempotent and never clobbers pre-set attributes.
  * standalone modals not routed through ModalManager carry explicit ARIA.

Run: python3 run_tests.py unit  (or) pytest tests/static/js/test_modal_aria_jsdom.py
Requires node + jsdom (installed into tests/static/js/.jsdom-venv by the harness).
"""

import os
import subprocess

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_HARNESS_DIR = os.path.dirname(__file__)
_JSDOM_DIR = os.path.join(_HARNESS_DIR, "jsdom_venv")
_NODE_MODULES = os.path.join(_JSDOM_DIR, "node_modules")


def _ensure_jsdom():
    # jsdom is a dev-only harness dependency, installed into tests/static/js/jsdom_venv.
    # If missing, install it (valid npm package name, no `npm init`).
    if os.path.isdir(os.path.join(_NODE_MODULES, "jsdom")):
        return
    os.makedirs(_JSDOM_DIR, exist_ok=True)
    pkg = os.path.join(_JSDOM_DIR, "package.json")
    if not os.path.exists(pkg):
        with open(pkg, "w", encoding="utf-8") as fh:
            fh.write('{\n  "name": "modal-aria-jsdom-harness",\n  "version": "1.0.0",\n  "private": true\n}\n')
    subprocess.run(
        ["npm", "install", "jsdom@24", "--no-audit", "--no-fund"],
        cwd=_JSDOM_DIR,
        check=True,
    )


def _read_js(rel):
    with open(os.path.join(_REPO_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _run_jsdom(driver_js):
    """Execute driver_js inside a jsdom window; return its stdout text.

    Uses jsdom ``runScripts: 'dangerously'`` so the real modal-manager.js runs in a
    genuine browser-like global (window/document/setTimeout all present). The driver
    is appended as a <script> element and shares that global.

    Node 25 rejects extra argv after ``node -e``, so the harness is written to a real
    file and invoked with positional args instead.
    """
    _ensure_jsdom()
    harness = r"""
    const { JSDOM } = require('jsdom');
    const fs = require('fs');
    const modalManagerSrc = fs.readFileSync(process.argv[2], 'utf8');
    const driverSrc = fs.readFileSync(process.argv[3], 'utf8');
    const results = [];
    const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', { runScripts: 'dangerously', pretendToBeVisual: true });
    const { window } = dom;
    window.console.log = (...a) => results.push(a.join(' '));
    window.console.error = (...a) => results.push('ERR ' + a.join(' '));
    try {
        const src = window.document.createElement('script');
        src.textContent = modalManagerSrc;
        window.document.body.appendChild(src);
        const drv = window.document.createElement('script');
        drv.textContent = driverSrc;
        window.document.body.appendChild(drv);
    } catch (e) {
        results.push('HARNESS_ERR ' + (e && e.stack ? e.stack : e));
    }
    process.stdout.write(results.join('\n'));
    """
    harness_path = os.path.join(_JSDOM_DIR, "_aria_harness.js")
    with open(harness_path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    driver_path = os.path.join(_HARNESS_DIR, "_aria_driver.js")
    with open(driver_path, "w", encoding="utf-8") as fh:
        fh.write(driver_js)
    try:
        out = subprocess.run(
            ["node", harness_path, os.path.join(_REPO_ROOT, "src/web/static/js/modal-manager.js"), driver_path],
            cwd=_JSDOM_DIR,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "NODE_PATH": _NODE_MODULES},
        )
    finally:
        if os.path.exists(driver_path):
            os.remove(driver_path)
    return out.stdout


# --- Drivers (string snippets executed inside the jsdom window) ---

_CONFIRM_DRIVER = r"""
const mm = window.ModalManager;
mm.confirm('Delete everything?', { title: 'Delete Rule', confirmText: 'Delete', cancelText: 'Cancel' })
  .catch(() => {});
const m = document.getElementById('_confirm_'); // id is dynamic; find by role
const modal = document.querySelector('[role="dialog"]');
console.log('confirm_role=' + (modal ? modal.getAttribute('role') : 'null'));
console.log('confirm_modal=' + (modal ? modal.getAttribute('aria-modal') : 'null'));
console.log('confirm_label=' + (modal ? modal.getAttribute('aria-label') : 'null'));
// cleanup so we don't leak
if (modal) modal.remove();
"""

_PROMPT_DRIVER = r"""
const mm = window.ModalManager;
mm.prompt('Name?', '', { title: 'Rename', required: true }).catch(() => {});
const modal = document.querySelector('[role="dialog"]');
console.log('prompt_role=' + (modal ? modal.getAttribute('role') : 'null'));
console.log('prompt_modal=' + (modal ? modal.getAttribute('aria-modal') : 'null'));
console.log('prompt_label=' + (modal ? modal.getAttribute('aria-label') : 'null'));
if (modal) modal.remove();
"""

_REGISTER_DRIVER = r"""
// A modal registered through ModalManager must receive ARIA from ensureModalAria
const modal = document.createElement('div');
modal.id = 'myTestModal';
modal.innerHTML = '<h3>Test Heading</h3><p>body</p>';
document.body.appendChild(modal);
window.ModalManager.register('myTestModal', { isDynamic: true });
console.log('reg_role=' + modal.getAttribute('role'));
console.log('reg_modal=' + modal.getAttribute('aria-modal'));
console.log('reg_label=' + modal.getAttribute('aria-label'));
modal.remove();
"""

_IDEMPOTENT_DRIVER = r"""
// ensureModalAria must NOT clobber a pre-set aria-label
const modal = document.createElement('div');
modal.id = 'presetModal';
modal.setAttribute('role', 'dialog');
modal.setAttribute('aria-modal', 'false'); // intentionally different from contract default
modal.setAttribute('aria-label', 'Preset Label');
document.body.appendChild(modal);
window.ModalManager.register('presetModal', { isDynamic: true });
console.log('id_role=' + modal.getAttribute('role'));
console.log('id_modal=' + modal.getAttribute('aria-modal'));
console.log('id_label=' + modal.getAttribute('aria-label'));
modal.remove();
"""

_NO_HEADING_DRIVER = r"""
// modal with no heading and no aria-label -> humanized id
const modal = document.createElement('div');
modal.id = 'validationConversationModal';
modal.innerHTML = '<p>body only</p>';
document.body.appendChild(modal);
window.ModalManager.register('validationConversationModal', { isDynamic: true });
console.log('nh_role=' + modal.getAttribute('role'));
console.log('nh_label=' + (modal.getAttribute('aria-label') || 'null'));
modal.remove();
"""


@pytest.mark.unit
def test_confirm_modal_has_aria():
    out = _run_jsdom(_CONFIRM_DRIVER)
    assert "confirm_role=dialog" in out, out
    assert "confirm_modal=true" in out, out
    assert "confirm_label=Delete Rule" in out, out


@pytest.mark.unit
def test_prompt_modal_has_aria():
    out = _run_jsdom(_PROMPT_DRIVER)
    assert "prompt_role=dialog" in out, out
    assert "prompt_modal=true" in out, out
    assert "prompt_label=Rename" in out, out


@pytest.mark.unit
def test_registered_modal_gets_aria_from_heading():
    out = _run_jsdom(_REGISTER_DRIVER)
    assert "reg_role=dialog" in out, out
    assert "reg_modal=true" in out, out
    assert "reg_label=Test Heading" in out, out


@pytest.mark.unit
def test_ensure_modal_aria_is_idempotent_and_non_clobbering():
    out = _run_jsdom(_IDEMPOTENT_DRIVER)
    assert "id_role=dialog" in out, out
    # Pre-set aria-modal=false must be preserved, not overwritten to true
    assert "id_modal=false" in out, out
    assert "id_label=Preset Label" in out, out


@pytest.mark.unit
def test_registered_modal_without_heading_uses_humanized_id():
    out = _run_jsdom(_NO_HEADING_DRIVER)
    assert "nh_role=dialog" in out, out
    assert "nh_label=validation Conversation" in out, out


@pytest.mark.unit
def test_standalone_observable_info_modal_has_direct_aria():
    """observable-utils.js showObservableInfoModal is NOT ModalManager-routed,
    so it must carry explicit ARIA at creation."""
    observable_src = _read_js("src/web/static/js/components/observable-utils.js")
    driver = (
        observable_src
        + r"""
        const host = document.createElement('div');
        host.id = 'obsInfo-1';
        host.innerHTML = '<p>value</p>';
        document.body.appendChild(host);
        showObservableInfoModal('obsInfo-1');
        const modal = document.getElementById('observableInfoModal');
        console.log('obs_role=' + (modal ? modal.getAttribute('role') : 'null'));
        console.log('obs_modal=' + (modal ? modal.getAttribute('aria-modal') : 'null'));
        console.log('obs_label=' + (modal ? modal.getAttribute('aria-label') : 'null'));
        if (modal) modal.remove();
        """
    )
    _ensure_jsdom()
    harness = r"""
    const { JSDOM } = require('jsdom');
    const fs = require('fs');
    const src = fs.readFileSync(process.argv[2], 'utf8');
    const results = [];
    const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', { runScripts: 'dangerously', pretendToBeVisual: true });
    const { window } = dom;
    window.console.log = (...a) => results.push(a.join(' '));
    window.console.error = (...a) => results.push('ERR ' + a.join(' '));
    try {
        const s = window.document.createElement('script');
        s.textContent = src;
        window.document.body.appendChild(s);
    } catch (e) {
        results.push('HARNESS_ERR ' + (e && e.stack ? e.stack : e));
    }
    process.stdout.write(results.join('\n'));
    """
    harness_path = os.path.join(_JSDOM_DIR, "_obs_harness.js")
    with open(harness_path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    driver_path = os.path.join(_HARNESS_DIR, "_obs_driver.js")
    with open(driver_path, "w", encoding="utf-8") as fh:
        fh.write(driver)
    try:
        proc = subprocess.run(
            ["node", harness_path, driver_path],
            cwd=_JSDOM_DIR,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "NODE_PATH": _NODE_MODULES},
        )
    finally:
        if os.path.exists(driver_path):
            os.remove(driver_path)
    out = proc.stdout
    assert "obs_role=dialog" in out, out
    assert "obs_modal=true" in out, out
    assert "obs_label=Observable detail" in out, out
