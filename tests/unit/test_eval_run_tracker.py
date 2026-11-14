"""Regression: overlapping eval launches on the Agent Evals pages must not share a poll loop.

Both ``agent_evals.html`` and ``agent_evals2.html`` read the page-global
``currentSubagent`` on every poll (and ``agent_evals.html`` also replaced a
page-global execution map at each launch). Launching extractor B while A was
still running made A's loop poll B's rows; the shared status line showed
whichever loop wrote last. On 2026-10-17 five extractors launched within a
minute all ran correctly server-side (47/47 executions completed) while the page
reported the wrong agent's progress. The fixed 60-poll budget (2 min) also gave
up on launches queued behind earlier ones on the 2-slot workflow worker.

``eval-run-tracker.js`` now gives each launch its own subagent, execution IDs,
and queue-sized deadline. These tests EXECUTE that module under Node.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TRACKER_JS = REPO / "src" / "web" / "static" / "js" / "components" / "eval-run-tracker.js"
TEMPLATES = [REPO / "src" / "web" / "templates" / name for name in ("agent_evals.html", "agent_evals2.html")]

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def _run_node(body: str):
    if shutil.which("node") is None:
        pytest.skip("node is required to execute eval-run-tracker.js")
    script = f"const T = require({json.dumps(str(TRACKER_JS))});\n{body}"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


def test_overlapping_runs_keep_their_own_subagent_and_executions():
    got = _run_node(
        """
        const reg = T.createRegistry({ now: () => 0 });
        const a = reg.start('cmdline', [101, 102]);
        const b = reg.start('hunt_queries', [201, 202, 203]);
        console.log(JSON.stringify({
            aUrl: T.resultsUrl(a), bUrl: T.resultsUrl(b),
            aSub: reg.get(a.id).subagent, bSub: reg.get(b.id).subagent,
        }));
        """
    )
    assert got["aSub"] == "cmdline"
    assert got["bSub"] == "hunt_queries"
    assert got["aUrl"] == "/api/evaluations/subagent-eval-results?subagent=cmdline&execution_ids=101&execution_ids=102"
    assert got["bUrl"] == (
        "/api/evaluations/subagent-eval-results?subagent=hunt_queries"
        "&execution_ids=201&execution_ids=202&execution_ids=203"
    )


def test_budget_counts_executions_queued_ahead_on_the_page():
    got = _run_node(
        """
        const reg = T.createRegistry({ now: () => 0 });
        const a = reg.start('cmdline', Array.from({ length: 10 }, (_, i) => i + 1));
        const b = reg.start('process_lineage', Array.from({ length: 10 }, (_, i) => i + 100));
        console.log(JSON.stringify({ a: a.deadline, b: b.deadline, aheadB: b.executionsAhead,
            base: T.BASE_BUDGET_MS, per: T.PER_EXECUTION_MS }));
        """
    )
    assert got["a"] == got["base"] + 10 * got["per"]
    assert got["aheadB"] == 10
    assert got["b"] == got["base"] + 20 * got["per"]


def test_progress_extends_deadline_and_stall_times_out():
    got = _run_node(
        """
        let t = 0;
        const reg = T.createRegistry({ now: () => t });
        const run = reg.start('cmdline', [1, 2, 3]);
        const first = run.deadline;
        // Progress just before the deadline pushes it out.
        t = first - 1;
        reg.update(run.id, { completed: 1, failed: 0, pending: 2 });
        const extended = run.deadline;
        const stateAfterProgress = run.state;
        // No further progress past the extended deadline -> stop watching.
        t = extended + 1;
        reg.update(run.id, { completed: 1, failed: 0, pending: 2 });
        console.log(JSON.stringify({ first, extended, stateAfterProgress, final: run.state,
            stall: T.STALL_EXTENSION_MS, line: reg.statusLines()[0] }));
        """
    )
    assert got["extended"] == got["first"] - 1 + got["stall"]
    assert got["stateAfterProgress"] == "polling"
    assert got["final"] == "timed_out"
    assert got["line"].startswith("cmdline: 1/3 done - stopped watching")


def test_run_finishes_only_when_all_its_executions_are_done():
    got = _run_node(
        """
        const reg = T.createRegistry({ now: () => 0 });
        const a = reg.start('cmdline', [1, 2]);
        const b = reg.start('registry_artifacts', [3]);
        reg.update(b.id, { completed: 1, failed: 0, pending: 0 });
        const mid = { a: a.state, b: b.state, any: reg.anyPolling() };
        reg.update(a.id, { completed: 1, failed: 1, pending: 0 });
        console.log(JSON.stringify({ mid, a: a.state, any: reg.anyPolling(), lines: reg.statusLines() }));
        """
    )
    assert got["mid"] == {"a": "polling", "b": "done", "any": True}
    assert got["a"] == "done"
    assert got["any"] is False
    assert got["lines"] == [
        "cmdline: 2/2 done, 1 failed - finished",
        "registry_artifacts: 1/1 done - finished",
    ]


def test_sustained_outage_marks_run_lost_and_success_resets_streak():
    got = _run_node(
        """
        const reg = T.createRegistry({ now: () => 0 });
        const run = reg.start('cmdline', [1]);
        for (let i = 0; i < T.MAX_CONSECUTIVE_FAILURES - 1; i++) reg.recordFailure(run.id);
        reg.update(run.id, { completed: 0, failed: 0, pending: 1 });
        const afterReset = { state: run.state, failures: run.consecutiveFailures };
        for (let i = 0; i < T.MAX_CONSECUTIVE_FAILURES; i++) reg.recordFailure(run.id);
        console.log(JSON.stringify({ afterReset, final: run.state }));
        """
    )
    assert got["afterReset"] == {"state": "polling", "failures": 0}
    assert got["final"] == "lost"


def test_counts_one_status_per_execution():
    """hunt_queries can return two records for one execution; count executions, not rows.
    An execution with no record yet is still pending."""
    got = _run_node(
        """
        const results = [
            { execution_id: 1, status: 'completed' },
            { execution_id: 1, status: 'pending' },   // second record, same execution
            { execution_id: 2, status: 'failed' },
            { execution_id: 3, status: 'pending' },
            { execution_id: 99, status: 'completed' }, // another launch's row
        ];
        console.log(JSON.stringify(T.countExecutionStatuses(results, [1, 2, 3, 4])));
        """
    )
    assert got == {"completed": 1, "failed": 1, "pending": 2, "total": 4}


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_pages_poll_through_the_tracker_not_page_globals(template: Path):
    """Both pages must load the tracker and must not poll by the page's current selection."""
    text = template.read_text()
    assert "js/components/eval-run-tracker.js" in text
    assert "EvalRunTracker.resultsUrl(run)" in text
    assert "subagent-eval-results?subagent=${subagent}" not in text
    assert "counts_only=true&subagent=' + encodeURIComponent(currentSubagent)" not in text
    assert "executionResults" not in text
