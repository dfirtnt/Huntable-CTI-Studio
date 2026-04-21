"""
Static-analysis test: every dismiss-type Cancel button in HTML templates
must live inside a container that provides Escape key coverage.

ESC coverage is satisfied by any one of:
  1. Container id ends with 'Modal' -- modal-manager.js auto-detects these
     via [id$="Modal"] selector and registers them on DOMContentLoaded.
  2. ModalManager.register('<id>', ...) is called explicitly in the file.
  3. A document.addEventListener('keydown', ...) block in the file references
     both 'Escape' and the container id (or the close function) within 500
     chars of the Escape check.

What counts as a dismiss Cancel button:
  A <button> whose visible text is exactly "Cancel" and whose onclick does
  NOT perform an async action-cancel (cancelExecution, cancelAllRunning, etc.).
  Buttons inside <script> blocks are excluded (they are JS-generated HTML and
  are tested by the Playwright modal suite instead).

Failure means: a user clicking the visible Cancel button cannot invoke the
same action by pressing Escape -- violating the UX contract in
.cursor/agents/ui-designer.md Section 6.1.
"""

import re
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src" / "web" / "templates"

# A dismiss-type Cancel button in static HTML.
CANCEL_BTN_RE = re.compile(r"<button\b([^>]*)>\s*Cancel\s*</button>", re.IGNORECASE)

# Extract onclick= attribute value (single or double quoted).
ONCLICK_RE = re.compile(r'\bonclick=["\']([^"\']+)["\']', re.IGNORECASE)

# Function name called by onclick (e.g. "closeEnrichExpanded" from "closeEnrichExpanded()").
FN_NAME_RE = re.compile(r"(\w+)\s*\(")

# Action-cancel buttons: these cancel async operations or inline edits, not dialogs.
# Extend this list when a new action-cancel pattern is introduced.
ACTION_CANCEL_RE = re.compile(
    r"cancelExecution|cancelAllRunning|cancelEnrichSystemPrompt",
    re.IGNORECASE,
)

# Opening element with a dialog-related id (overlay or modal).
DIALOG_CONTAINER_RE = re.compile(
    r"""<(?:div|section|aside|form)\b[^>]*\bid=["']"""
    r"""([^"']*(?:Modal|modal|overlay|Overlay)[^"']*)["']""",
    re.IGNORECASE,
)

# Fallback: any id ending in 'Modal' in an opening tag.
MODAL_SUFFIX_RE = re.compile(r"""\bid=["'](\w+Modal)["']""")

# Explicit ModalManager.register call.
MM_REGISTER_PREFIX = r"""ModalManager\.register\s*\(\s*["']"""

# 'Escape' string literal in JS keydown handlers.
ESCAPE_STR_RE = re.compile(r"""["']Escape["']""")

# Large modals (e.g. enrichModal in workflow.html) span 300+ lines. Use a
# generous window so the ancestor search reliably reaches the container opening.
LOOKBACK_CHARS = 40_000
ESC_WINDOW = 500


def _script_ranges(content: str) -> list[tuple[int, int]]:
    """Return (start, end) byte offsets of all <script>...</script> blocks."""
    ranges: list[tuple[int, int]] = []
    cursor = 0
    while True:
        open_m = re.search(r"<script\b[^>]*>", content[cursor:], re.IGNORECASE)
        if not open_m:
            break
        open_end = cursor + open_m.end()
        close_m = re.search(r"</script>", content[open_end:], re.IGNORECASE)
        if not close_m:
            break
        close_end = open_end + close_m.end()
        ranges.append((cursor + open_m.start(), close_end))
        cursor = close_end
    return ranges


def _in_script(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in ranges)


def _find_enclosing_container_id(text_before: str) -> str | None:
    """
    Return the id of the most-recently-opened dialog/overlay container
    in the slice of template text that precedes the cancel button.
    """
    chunk = text_before[-LOOKBACK_CHARS:]
    matches = list(DIALOG_CONTAINER_RE.finditer(chunk))
    if matches:
        return matches[-1].group(1)
    # Fallback: any id ending in 'Modal'
    matches = list(MODAL_SUFFIX_RE.finditer(chunk))
    return matches[-1].group(1) if matches else None


def _is_esc_covered(file_content: str, container_id: str, close_fn: str | None) -> bool:
    """Return True if the container is reachable via the Escape key."""
    # Rule 1: modal-manager auto-detects ids ending in 'Modal'.
    if container_id.endswith("Modal"):
        return True

    # Rule 2: explicit ModalManager.register('<container_id>', ...) in the file.
    pattern = MM_REGISTER_PREFIX + re.escape(container_id) + r"""["']"""
    if re.search(pattern, file_content):
        return True

    # Rule 3: keydown/Escape handler referencing the container id or close fn.
    for m in ESCAPE_STR_RE.finditer(file_content):
        start = max(0, m.start() - ESC_WINDOW)
        end = min(len(file_content), m.end() + ESC_WINDOW)
        window = file_content[start:end]
        if container_id in window:
            return True
        if close_fn and close_fn in window:
            return True

    return False


def _collect_violations() -> list[dict]:
    """Scan all templates and return info on uncovered cancel buttons."""
    violations: list[dict] = []

    for tmpl in sorted(TEMPLATES_DIR.glob("*.html")):
        content = tmpl.read_text(encoding="utf-8")
        script_spans = _script_ranges(content)

        for btn_m in CANCEL_BTN_RE.finditer(content):
            # Skip buttons inside <script> blocks (JS-generated HTML).
            if _in_script(btn_m.start(), script_spans):
                continue

            attrs = btn_m.group(1)
            onclick_m = ONCLICK_RE.search(attrs)
            onclick = onclick_m.group(1).strip() if onclick_m else ""

            # Skip action-cancel buttons (cancel async jobs, not dialogs).
            if ACTION_CANCEL_RE.search(onclick):
                continue

            fn_m = FN_NAME_RE.search(onclick) if onclick else None
            close_fn = fn_m.group(1) if fn_m else None

            text_before = content[: btn_m.start()]
            container_id = _find_enclosing_container_id(text_before)
            line_no = text_before.count("\n") + 1

            if container_id is None:
                # No dialog container found within the lookback window.
                # This means the Cancel button is on a regular page (not inside a
                # modal/overlay), so ESC coverage is out of scope for this test.
                continue

            if not _is_esc_covered(content, container_id, close_fn):
                violations.append(
                    {
                        "template": tmpl.name,
                        "line": line_no,
                        "onclick": onclick or "(none)",
                        "container_id": container_id,
                        "reason": (
                            f"#{container_id} has no Escape key coverage: "
                            "id does not end in 'Modal', no ModalManager.register() call, "
                            "and no keydown/Escape handler references it."
                        ),
                    }
                )

    return violations


@pytest.mark.unit
class TestCancelButtonEscCoverage:
    """Every dismiss-type Cancel button must be reachable via the Escape key."""

    def test_all_cancel_buttons_are_esc_covered(self):
        violations = _collect_violations()
        if not violations:
            return

        lines = ["", "CANCEL BUTTONS MISSING ESCAPE KEY COVERAGE:", ""]
        for v in violations:
            lines.append(f"  {v['template']}:{v['line']}")
            lines.append(f"    onclick   : {v['onclick']}")
            lines.append(f"    container : #{v['container_id']}")
            lines.append(f"    reason    : {v['reason']}")
            lines.append("")
        lines.append(
            "Fix options: rename the container id to end in 'Modal', call "
            "ModalManager.register() for it, or add a keydown/Escape handler "
            "that references the container id."
        )
        pytest.fail("\n".join(lines))
