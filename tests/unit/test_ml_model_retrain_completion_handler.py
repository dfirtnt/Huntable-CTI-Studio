"""Template contract: ml_hunt_comparison.html retrain completion handler.

After retrain polling detects status === 'complete', the completion handler
must:
  1. Call refreshRetrainingStatus()    — updates the status panel
  2. Call refreshModelVersionHistory() — updates the version list
  3. Call loadInitialData()            — refreshes KPI cards and chart
  4. Use a 1500ms delay (bumped from 1000ms to allow DB write to land)

The three data-fetching calls inside loadInitialData() must include
{ cache: 'no-store' } so the browser does not serve stale responses
after a retrain adds a new version:
  5. /api/ml-model-performance/summary
  6. /api/model/versions
  7. /api/model/classification-timeline
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]

TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "ml_hunt_comparison.html"


@pytest.fixture(scope="module")
def html() -> str:
    return TEMPLATE.read_text()


def _completion_block(html: str) -> str:
    """Extract the setTimeout(...) block inside the status==='complete' branch."""
    match = re.search(
        r"status\.status\s*===\s*['\"]complete['\"].*?setTimeout\s*\(\s*\(\)\s*=>\s*\{(.*?)\}\s*,\s*\d+\s*\)",
        html,
        re.DOTALL,
    )
    assert match, (
        "Could not locate setTimeout block in status==='complete' branch of "
        "ml_hunt_comparison.html — check polling handler structure"
    )
    return match.group(0)


# ---------------------------------------------------------------------------
# Completion handler: required function calls
# ---------------------------------------------------------------------------


class TestCompletionHandlerCalls:
    @pytest.fixture(scope="class")
    def block(self, html: str) -> str:
        return _completion_block(html)

    def test_calls_load_initial_data(self, block: str) -> None:
        assert "loadInitialData()" in block

    def test_calls_refresh_retraining_status(self, block: str) -> None:
        assert "refreshRetrainingStatus()" in block, (
            "Completion handler must call refreshRetrainingStatus() — "
            "without it the 'Active model vN' text requires a manual Refresh Status click"
        )

    def test_calls_refresh_model_version_history(self, block: str) -> None:
        assert "refreshModelVersionHistory()" in block, (
            "Completion handler must call refreshModelVersionHistory() — "
            "without it the version history list requires F5 to show the new entry"
        )

    def test_delay_is_1500ms(self, html: str) -> None:
        match = re.search(
            r"status\.status\s*===\s*['\"]complete['\"].*?setTimeout\s*\([^,]+,\s*(\d+)\s*\)",
            html,
            re.DOTALL,
        )
        assert match, "setTimeout not found in complete branch"
        assert int(match.group(1)) == 1500, f"Delay is {match.group(1)}ms; expected 1500ms to let DB write settle"


# ---------------------------------------------------------------------------
# cache: 'no-store' on data-fetching calls
# ---------------------------------------------------------------------------


class TestNoCacheHeaders:
    def test_summary_fetch_no_store(self, html: str) -> None:
        assert re.search(
            r"fetch\s*\(\s*['\"][^'\"]*ml-model-performance/summary['\"].*?no-store",
            html,
            re.DOTALL,
        ), "/api/ml-model-performance/summary must include { cache: 'no-store' }"

    def test_versions_fetch_no_store(self, html: str) -> None:
        assert re.search(
            r"fetch\s*\(\s*['\"][^'\"]*model/versions['\"].*?no-store",
            html,
            re.DOTALL,
        ), "/api/model/versions must include { cache: 'no-store' }"

    def test_timeline_fetch_no_store(self, html: str) -> None:
        assert re.search(
            r"fetch\s*\(\s*['\"][^'\"]*classification-timeline['\"].*?no-store",
            html,
            re.DOTALL,
        ), "/api/model/classification-timeline must include { cache: 'no-store' }"
