/**
 * Per-launch progress tracking for the Agent Evals pages.
 *
 * Each "Run Evaluation" click becomes its own run: it keeps the subagent it was
 * launched for and the execution IDs the launch returned, so a second launch
 * (for the same or another extractor) never takes over an earlier poll loop.
 * Before this, both pages read the page-global `currentSubagent` (and, on
 * agent_evals.html, a page-global execution map) on every poll, so launching
 * extractor B while A was still running made A's loop poll B, and the shared
 * status line showed whichever loop wrote last.
 *
 * The poll budget is sized to the worker queue: a run launched behind other
 * in-flight runs on this page waits for their executions too, so its deadline
 * counts every execution still outstanding ahead of it. Any progress pushes the
 * deadline out again, so a slow but moving queue never times out.
 *
 * Pure logic (no DOM); loaded as a browser global and require()-able from Node
 * for tests.
 */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.EvalRunTracker = factory();
    }
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const POLL_INTERVAL_MS = 2000;
    // Fixed allowance for dispatch and worker pickup.
    const BASE_BUDGET_MS = 120000;
    // Per queued execution. Measured extractor executions run 4-36s on the
    // 2-slot workflow worker; 45s keeps the slowest (cmdline) inside budget.
    const PER_EXECUTION_MS = 45000;
    // Granted from the moment of any progress on the run.
    const STALL_EXTENSION_MS = 180000;
    // ~60s of consecutive failed polls (a dev web restart takes ~45s).
    const MAX_CONSECUTIVE_FAILURES = 30;

    function pollBudgetMs(ownExecutions, executionsAhead) {
        return BASE_BUDGET_MS + PER_EXECUTION_MS * (ownExecutions + executionsAhead);
    }

    /**
     * Collapse eval records into per-execution statuses for one run.
     *
     * An execution can own more than one record (hunt_queries also matches
     * historical hunt_queries_edr rows), so counting records would overcount.
     * An execution is completed if any of its records completed, failed if all
     * of them failed, and pending otherwise -- including when no record for it
     * has come back yet.
     */
    function countExecutionStatuses(results, executionIds) {
        const byExec = new Map();
        for (const id of executionIds) byExec.set(Number(id), []);
        for (const r of results || []) {
            const id = Number(r.execution_id);
            if (byExec.has(id)) byExec.get(id).push(r.status);
        }
        let completed = 0;
        let failed = 0;
        let pending = 0;
        byExec.forEach((statuses) => {
            if (statuses.includes('completed')) completed++;
            else if (statuses.length > 0 && statuses.every((s) => s === 'failed')) failed++;
            else pending++;
        });
        return { completed, failed, pending, total: byExec.size };
    }

    function createRegistry(options) {
        const now = (options && options.now) || (() => Date.now());
        const runs = new Map();
        let seq = 0;

        function outstandingExecutions() {
            let n = 0;
            runs.forEach((run) => {
                if (run.state === 'polling') n += run.total - run.done;
            });
            return n;
        }

        function start(subagent, executionIds) {
            // Finished runs from earlier launches drop out of the status line.
            runs.forEach((run, id) => {
                if (run.state !== 'polling') runs.delete(id);
            });
            const ids = executionIds.map(Number).filter((id) => Number.isFinite(id));
            const ahead = outstandingExecutions();
            const t = now();
            const run = {
                id: ++seq,
                subagent,
                executionIds: ids,
                total: ids.length,
                done: 0,
                completed: 0,
                failed: 0,
                pending: ids.length,
                executionsAhead: ahead,
                startedAt: t,
                deadline: t + pollBudgetMs(ids.length, ahead),
                consecutiveFailures: 0,
                state: ids.length > 0 ? 'polling' : 'done',
            };
            runs.set(run.id, run);
            return run;
        }

        function update(runId, counts) {
            const run = runs.get(runId);
            if (!run || run.state !== 'polling') return run;
            run.consecutiveFailures = 0;
            const done = counts.completed + counts.failed;
            if (done > run.done) {
                run.deadline = Math.max(run.deadline, now() + STALL_EXTENSION_MS);
            }
            run.completed = counts.completed;
            run.failed = counts.failed;
            run.pending = counts.pending;
            run.done = done;
            if (done >= run.total) run.state = 'done';
            else if (now() > run.deadline) run.state = 'timed_out';
            return run;
        }

        function recordFailure(runId) {
            const run = runs.get(runId);
            if (!run || run.state !== 'polling') return run;
            run.consecutiveFailures++;
            if (run.consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) run.state = 'lost';
            else if (now() > run.deadline) run.state = 'timed_out';
            return run;
        }

        function anyPolling() {
            for (const run of runs.values()) if (run.state === 'polling') return true;
            return false;
        }

        function describe(run) {
            const failedNote = run.failed > 0 ? `, ${run.failed} failed` : '';
            const base = `${run.subagent}: ${run.done}/${run.total} done${failedNote}`;
            switch (run.state) {
                case 'done':
                    return `${base} - finished`;
                case 'timed_out':
                    return `${base} - stopped watching (still running server-side; use Load Previous Results)`;
                case 'lost':
                    return `${base} - lost connection to server (use Load Previous Results once it is back)`;
                default:
                    if (run.consecutiveFailures > 0) {
                        return `${base} - reconnecting (${run.consecutiveFailures}/${MAX_CONSECUTIVE_FAILURES})`;
                    }
                    return run.done === 0 && run.executionsAhead > 0 ? `${base} - queued` : base;
            }
        }

        function statusLines() {
            return Array.from(runs.values()).map(describe);
        }

        return {
            start,
            update,
            recordFailure,
            anyPolling,
            statusLines,
            get: (runId) => runs.get(runId),
            runs: () => Array.from(runs.values()),
        };
    }

    function resultsUrl(run) {
        const params = new URLSearchParams({ subagent: run.subagent });
        for (const id of run.executionIds) params.append('execution_ids', String(id));
        return `/api/evaluations/subagent-eval-results?${params.toString()}`;
    }

    return {
        POLL_INTERVAL_MS,
        BASE_BUDGET_MS,
        PER_EXECUTION_MS,
        STALL_EXTENSION_MS,
        MAX_CONSECUTIVE_FAILURES,
        pollBudgetMs,
        countExecutionStatuses,
        createRegistry,
        resultsUrl,
    };
});
