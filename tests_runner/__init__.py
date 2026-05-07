"""tests_runner - Huntable CTI Studio unified test runner package.

Entry points::

    # via shim (canonical)
    python run_tests.py smoke

    # via package module
    python -m tests_runner.cli smoke
"""

from tests_runner.cli import main  # noqa: F401 -- re-exported for convenience
