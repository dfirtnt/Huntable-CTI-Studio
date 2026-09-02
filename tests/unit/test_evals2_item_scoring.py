"""Regression: a no-output extraction must not be graded as 100% precision.

``agent_evals2.html`` computed per-article precision as::

    const p = ((r.matched_count + r.extra_count) > 0)
        ? r.matched_count / (r.matched_count + r.extra_count)
        : 1;                                   // 0 predictions == 100% precision

so an extractor that returned **nothing** was credited with precision 1.0. The
server uses ``0.0`` for that same degenerate case (``evaluation_api.py``
per-config aggregates and ``eval_item_scorer.py``), so the SYS.03 summary strip
and the server-computed SYS.04 trend chart reported different numbers for
identical rows -- 64.4% against 51-55% on the CommandLine dataset.

Worse than the discrepancy: the metric rewarded silence. An extractor emitting
zero items for every article averaged 100% precision, which is precisely the
failure an eval harness exists to catch. Measured on the live corpus when this
was fixed, 223 of 911 scored rows (24%) hit the degenerate branch, including
``windows_services`` at 3/3.

Three client sites disagreed on the same row: the table cell rendered ``n/a``,
the summary strip counted 1.0, and the item-detail modal displayed ``100%
(0/0)``. All three now route through ``scoredArticleMetrics()``.

These tests EXECUTE the template's JavaScript under Node rather than asserting
over its text, and pin it against the Python convention it must match. A regex
assertion cannot tell 0 from 1.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

EVALS2_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "agent_evals2.html"

# (matched, extra, expected) -- the degenerate rows are the point of this suite.
CASES = [
    (0, 0, 31),  # extractor returned nothing, ground truth exists -- the live regression
    (0, 0, 0),  # nothing expected and nothing produced
    (3, 0, 3),  # perfect
    (2, 2, 4),  # half the predictions are wrong
    (5, 1, 10),  # partial
    (0, 4, 4),  # all predictions wrong
]


def _extract_js_function(template_text: str, name: str) -> str:
    """Slice one function out of the template by its column-0 closing brace.

    Naive brace counting over-reads: this template's JS contains template
    literals and nested object braces.
    """
    start = template_text.index(f"function {name}(")
    end = template_text.index("\n}\n", start) + len("\n}\n")
    return template_text[start:end]


# The live CommandLine dataset the defect was reported against ("Latest (all
# runs)", latest row per article_url), read from subagent_evaluations on
# 2026-08-20 as (matched, extra, expected). The last row -- 0 produced against 31
# expected -- is the article named in the bug report.
CMDLINE_DATASET = [
    (3, 0, 5),
    (0, 2, 1),
    (7, 2, 22),
    (2, 3, 7),
    (6, 4, 15),
    (1, 2, 2),
    (5, 4, 26),
    (1, 0, 1),
    (56, 16, 56),
    (0, 0, 31),
]


def _python_convention(matched: int, extra: int, expected: int) -> dict:
    """The server's formula, transcribed from evaluation_api.py aggregates."""
    precision_denom = matched + extra
    return {
        "precision": matched / precision_denom if precision_denom > 0 else 0.0,
        "recall": matched / expected if expected > 0 else 0.0,
    }


@pytest.mark.unit
@pytest.mark.regression
class TestEvals2ItemScoring:
    @pytest.fixture(scope="class")
    def js_results(self) -> list[dict]:
        if shutil.which("node") is None:
            pytest.skip("node is required to execute the template's scoring helper")

        fn = _extract_js_function(EVALS2_TEMPLATE.read_text(), "scoredArticleMetrics")
        rows = [{"status": "completed", "matched_count": m, "extra_count": e, "expected_count": x} for m, e, x in CASES]
        script = f"{fn}\nconst rows = {json.dumps(rows)};\nconsole.log(JSON.stringify(rows.map(scoredArticleMetrics)));"
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30, check=True)
        return json.loads(out.stdout)

    def test_no_output_extraction_scores_zero_precision(self, js_results: list[dict]) -> None:
        """matched=0, extra=0 must score 0 -- never 1. This is the whole bug."""
        assert js_results[0]["precision"] == 0.0
        assert js_results[1]["precision"] == 0.0

    def test_matches_the_server_convention_on_every_case(self, js_results: list[dict]) -> None:
        """The strip and the server-computed trend chart must not disagree."""
        for (matched, extra, expected), got in zip(CASES, js_results, strict=True):
            want = _python_convention(matched, extra, expected)
            assert got["precision"] == pytest.approx(want["precision"]), (
                f"precision diverged from the server for matched={matched} extra={extra}"
            )
            assert got["recall"] == pytest.approx(want["recall"]), (
                f"recall diverged from the server for matched={matched} expected={expected}"
            )

    def test_unscored_rows_are_excluded_rather_than_scored(self) -> None:
        """A row with no ground truth is undefined, not zero -- it must not
        enter the mean at all, or every unscored article drags the average down."""
        if shutil.which("node") is None:
            pytest.skip("node is required to execute the template's scoring helper")

        fn = _extract_js_function(EVALS2_TEMPLATE.read_text(), "scoredArticleMetrics")
        rows = [
            {"status": "completed", "matched_count": None, "extra_count": None, "expected_count": 5},
            {"status": "pending", "matched_count": 1, "extra_count": 0, "expected_count": 1},
            None,
        ]
        script = f"{fn}\nconst rows = {json.dumps(rows)};\nconsole.log(JSON.stringify(rows.map(scoredArticleMetrics)));"
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30, check=True)
        assert json.loads(out.stdout) == [None, None, None]

    def test_recall_denominator_is_reported_for_perfect_recall_gating(self, js_results: list[dict]) -> None:
        """An article with no ground truth to recall is not a 'perfect recall'.

        The old code awarded recall 1.0 AND incremented perfectRecall when
        expected_count was 0.
        """
        no_ground_truth = js_results[1]
        assert no_ground_truth["recallDenom"] == 0
        assert no_ground_truth["recall"] == 0.0

    def test_all_three_consumers_route_through_the_helper(self) -> None:
        """Table cell, summary strip, and modal must share one convention.

        They previously disagreed three ways on the same row (n/a / 1.0 /
        '100% (0/0)'), which is what made the defect survive review.
        """
        text = EVALS2_TEMPLATE.read_text()
        assert text.count("scoredArticleMetrics(") >= 4, "expected the helper definition plus three call sites"
        assert "> 0) ? r.matched_count / (r.matched_count + r.extra_count) : 1" not in text
        assert "const recall = expected > 0 ? matched / expected : 1;" not in text


def _run_js(functions: list[str], body: str) -> object:
    """Execute template functions under Node and return the JSON they print."""
    if shutil.which("node") is None:
        pytest.skip("node is required to execute the template's scoring helpers")
    text = EVALS2_TEMPLATE.read_text()
    src = "\n".join(_extract_js_function(text, name) for name in functions)
    out = subprocess.run(["node", "-e", f"{src}\n{body}"], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


def _rows(cases: list[tuple[int, int, int]]) -> list[dict]:
    return [{"status": "completed", "matched_count": m, "extra_count": e, "expected_count": x} for m, e, x in cases]


@pytest.mark.unit
@pytest.mark.regression
class TestEvals2AggregateSummary:
    """The headline AVG PRECISION the summary strip displays.

    Extracted out of ``renderAggregateSummary`` so the number can be pinned
    without a DOM: the displayed value is the thing the bug report was about,
    and it was previously computed inside a render function where no test could
    reach it.
    """

    def _aggregate(self, cases: list[tuple[int, int, int]]) -> dict:
        return _run_js(
            ["scoredArticleMetrics", "aggregateScoredMetrics"],
            f"console.log(JSON.stringify(aggregateScoredMetrics({json.dumps(_rows(cases))})));",
        )

    def test_reproduces_the_reported_dataset_under_the_fixed_convention(self) -> None:
        """The live CommandLine dataset must average 54.4%, not the 64.4% shown.

        Pins the exact acceptance-criterion number. The 10-point gap is entirely
        the single 0-produced/31-expected article, which the old code credited
        with precision 1.0 while its own table cell rendered n/a.
        """
        agg = self._aggregate(CMDLINE_DATASET)

        assert agg["scoredCount"] == 10
        assert round(agg["avgPrecision"] * 100, 1) == 54.4

        # The pre-fix convention, for contrast -- this is what the strip showed.
        prefix = sum((m / (m + e) if (m + e) > 0 else 1.0) for m, e, _ in CMDLINE_DATASET) / len(CMDLINE_DATASET)
        assert round(prefix * 100, 1) == 64.4, "dataset no longer reproduces the reported defect"

    def test_matches_the_server_macro_average(self) -> None:
        """Strip and server-computed trend chart must agree on the same rows."""
        agg = self._aggregate(CMDLINE_DATASET)
        want = sum(_python_convention(m, e, x)["precision"] for m, e, x in CMDLINE_DATASET) / len(CMDLINE_DATASET)
        assert agg["avgPrecision"] == pytest.approx(want)

    def test_silence_scores_zero_not_one(self) -> None:
        """An extractor emitting nothing for every article must score 0%.

        This is the failure an eval harness exists to catch; under the old
        convention it scored a perfect 100%.
        """
        agg = self._aggregate([(0, 0, 5), (0, 0, 12), (0, 0, 3)])

        assert agg["avgPrecision"] == 0.0
        assert agg["perfectRecall"] == 0

    def test_no_ground_truth_is_not_a_perfect_recall(self) -> None:
        """The old code awarded recall 1.0 AND incremented perfectRecall when
        expected_count was 0."""
        agg = self._aggregate([(0, 0, 0), (2, 0, 2)])

        assert agg["perfectRecall"] == 1, "only the genuinely-complete row counts"
        assert agg["avgRecall"] == pytest.approx(0.5)

    def test_unscored_rows_leave_the_divisor_alone(self) -> None:
        """A row excluded from the numerator must be excluded from the divisor.

        Membership is decided solely by scoredArticleMetrics. A duplicated filter
        condition that drifted would skip a row while still dividing by it,
        silently understating the mean.
        """
        rows = _rows([(2, 0, 2), (1, 1, 2)])
        rows.append({"status": "completed", "matched_count": None, "extra_count": None, "expected_count": 9})
        rows.append({"status": "pending", "matched_count": 1, "extra_count": 0, "expected_count": 1})

        agg = _run_js(
            ["scoredArticleMetrics", "aggregateScoredMetrics"],
            f"console.log(JSON.stringify(aggregateScoredMetrics({json.dumps(rows)})));",
        )
        assert agg["scoredCount"] == 2
        assert agg["avgPrecision"] == pytest.approx(0.75)

    def test_returns_null_when_nothing_is_scored(self) -> None:
        """The strip hides itself rather than rendering NaN%."""
        rows = [{"status": "completed", "matched_count": None, "extra_count": None, "expected_count": 4}]
        agg = _run_js(
            ["scoredArticleMetrics", "aggregateScoredMetrics"],
            f"console.log(JSON.stringify(aggregateScoredMetrics({json.dumps(rows)})));",
        )
        assert agg is None
