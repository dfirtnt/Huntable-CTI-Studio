"""Helper for static-analysis tests that grep workflow.html's JS surface.

workflow.html's inline <script> block was split into
src/web/static/js/workflow/*.js across several refactor commits (all loaded
back into the page via <script src> tags in the same load order). Tests that
regex/substring-match a JS function or constant need the combined surface,
not just the template file, or they silently see an empty match once the
target code moves into one of the modules.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_TEMPLATE = _REPO_ROOT / "src" / "web" / "templates" / "workflow.html"
_WORKFLOW_JS_DIR = _REPO_ROOT / "src" / "web" / "static" / "js" / "workflow"

# Load order matches the <script src> tags in workflow.html.
_WORKFLOW_JS_MODULES = (
    "prompt-editor.js",
    "page.js",
    "executions.js",
    "queue.js",
    "config.js",
)


def read_workflow_src() -> str:
    """Return workflow.html concatenated with its extracted JS modules."""
    parts = [WORKFLOW_TEMPLATE.read_text(encoding="utf-8")]
    parts.extend((_WORKFLOW_JS_DIR / name).read_text(encoding="utf-8") for name in _WORKFLOW_JS_MODULES)
    return "\n".join(parts)
