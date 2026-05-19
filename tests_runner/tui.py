"""Terminal UI components for the test runner.

Glyph   -- ASCII-only display constants (repo policy: ASCII only in code).
RunnerTUI -- Optional Rich Live TUI; falls back to plain output when rich is
             unavailable or when the output is not a TTY.
"""

from __future__ import annotations

import os
import sys
import time


class Glyph:
    """ASCII-only display constants for status indicators (repo policy: ASCII-only in code)."""

    PASS = "[PASS]"
    FAIL = "[FAIL]"
    WARN = "[WARN]"
    INFO = "[INFO]"
    TIP = "Tip:"
    BAR_FILL = "="
    BAR_EMPTY = " "


class RunnerTUI:
    """Optional Rich Live TUI for the pytest streaming section.

    Activated when --tui=rich, or --tui=auto (default) on a real TTY with
    NO_COLOR unset.  Falls back gracefully to plain output in all other cases
    so the old behaviour is preserved without any code path changes.

    Usage::
        tui = RunnerTUI(config.tui)
        tui.start(pytest_groups)
        ...
        if tui.is_active:
            tui.on_line(line)
        else:
            print(line, end="", flush=True)
        ...
        tui.finish()
    """

    MAX_LOG_LINES = 30

    def __init__(self, mode: str = "auto"):
        self._live = None
        self._log_lines: list[str] = []
        self._categories_seen: list[str] = []
        self._all_categories: list[str] = []
        self._test_count = 0
        self._start_time = time.time()
        self._active = self._should_activate(mode)

    @staticmethod
    def _should_activate(mode: str) -> bool:
        if mode == "plain":
            return False
        if os.getenv("NO_COLOR"):
            return False
        if not sys.stdout.isatty():
            return False
        try:
            import rich  # noqa: F401

            return mode in ("auto", "rich")
        except ImportError:
            return False

    @property
    def is_active(self) -> bool:
        return self._active and self._live is not None

    def start(self, all_categories: list[str]) -> None:
        if not self._active:
            return
        try:
            from rich.console import Console
            from rich.live import Live

            self._all_categories = list(all_categories)
            self._start_time = time.time()
            self._live = Live(
                self._render(),
                console=Console(),
                refresh_per_second=4,
                transient=False,
            )
            self._live.start()
        except Exception:
            # Rich unavailable or terminal too narrow; fall back silently.
            self._active = False
            self._live = None

    def on_line(self, line: str) -> None:
        """Push a raw pytest output line to the log panel and refresh."""
        stripped = line.rstrip("\n")
        if stripped:
            self._log_lines.append(stripped)
            if len(self._log_lines) > self.MAX_LOG_LINES:
                del self._log_lines[0]
        if self.is_active:
            self._live.update(self._render())

    def on_category(self, categories_seen: set[str], test_count: int) -> None:
        """Update the footer when a new category starts."""
        self._categories_seen = [c for c in self._all_categories if c in categories_seen]
        self._test_count = test_count
        if self.is_active:
            self._live.update(self._render())

    def finish(self) -> None:
        """Stop the Live context and release the terminal."""
        if self.is_active:
            self._live.stop()
            self._live = None

    def _render(self):
        from rich.console import Group
        from rich.panel import Panel
        from rich.text import Text

        log_text = Text("\n".join(self._log_lines[-self.MAX_LOG_LINES :]))
        log_panel = Panel(log_text, title="pytest output", border_style="dim")

        elapsed = time.time() - self._start_time
        m, s = divmod(int(elapsed), 60)
        n_seen = len(self._categories_seen)
        n_total = len(self._all_categories)
        bar = (
            "[" + "".join("=" if c in self._categories_seen else " " for c in self._all_categories) + "]"
            if n_total
            else "[?]"
        )
        status_line = f"Categories: {bar} {n_seen}/{n_total} | tests: {self._test_count} | elapsed: {m:02d}:{s:02d}"
        footer = Panel(Text(status_line, style="bold"), border_style="blue")
        return Group(log_panel, footer)


# Keep the old underscore name as an alias so run_tests.py can import it without change.
_RunnerTUI = RunnerTUI
