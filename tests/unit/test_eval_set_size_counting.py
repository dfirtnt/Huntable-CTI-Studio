"""Regression tests for _count_csv_data_rows() in ml_hunt_comparison.py.

Locks the embedded-newline behavior that caused the original bug: counting
lines with wc -l-style logic over-counts CSV rows when quoted fields contain
literal \\n. Eval chunks are ~1000 chars and frequently contain newlines, so
this matters in practice.

Also locks graceful degradation on missing/corrupt files (the helper must
return None, never raise — the endpoint must always respond).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="module")
def counter():
    from src.web.routes.ml_hunt_comparison import _count_csv_data_rows

    return _count_csv_data_rows


class TestSimpleCounting:
    def test_counts_data_rows_excluding_header(self, tmp_path, counter) -> None:
        csv = tmp_path / "simple.csv"
        csv.write_text("col_a,col_b\n1,2\n3,4\n5,6\n")
        assert counter(str(csv)) == 3

    def test_empty_data_returns_zero(self, tmp_path, counter) -> None:
        csv = tmp_path / "header_only.csv"
        csv.write_text("col_a,col_b\n")
        assert counter(str(csv)) == 0


class TestEmbeddedNewlines:
    """The specific bug class: quoted fields containing literal \\n must not
    inflate the row count. This was the original failure mode."""

    def test_embedded_newline_in_quoted_field_counts_as_one_row(self, tmp_path, counter) -> None:
        csv = tmp_path / "newlines.csv"
        # Three data rows, but one of them has TWO embedded newlines in its
        # quoted chunk_text column. wc -l-style counting would report 5 lines
        # of data; csv.reader correctly reports 3.
        csv.write_text(
            "annotation_id,chunk_text,label\n"
            '1,"line1\nline2\nline3",huntable\n'
            '2,"single line",not_huntable\n'
            '3,"with\nembedded",huntable\n'
        )
        assert counter(str(csv)) == 3, (
            "Embedded newlines in quoted fields over-counted rows. Regression of the original wc -l bug."
        )

    def test_realistic_chunk_with_newlines(self, tmp_path, counter) -> None:
        """Simulate an actual eval_set row with a multi-line chunk_text."""
        csv = tmp_path / "realistic.csv"
        chunk = (
            "Persistence was established via reg add HKLM\\\\Software\\\\Microsoft\\\\Windows.\n"
            "Then the attacker ran:\n"
            "  schtasks /create /tn evil /tr C:\\\\Users\\\\Public\\\\evil.exe\n"
            "Followed by lateral movement over SMB."
        )
        csv.write_text(f'annotation_id,chunk_text,label\n1,"{chunk}",huntable\n2,"second row",not_huntable\n')
        assert counter(str(csv)) == 2


class TestGracefulFailure:
    def test_missing_file_returns_none(self, tmp_path, counter) -> None:
        missing = tmp_path / "does_not_exist.csv"
        assert counter(str(missing)) is None

    def test_unreadable_path_returns_none_not_raises(self, tmp_path, counter) -> None:
        # Pass a directory path instead of a file — open() raises IsADirectoryError
        # which is an OSError subclass. The helper must catch it.
        result = counter(str(tmp_path))
        assert result is None

    def test_empty_file_returns_zero_or_none_not_raises(self, tmp_path, counter) -> None:
        csv = tmp_path / "empty.csv"
        csv.write_text("")
        # Either 0 (treated as "header was empty") or None is acceptable here.
        # The contract is: do not raise.
        result = counter(str(csv))
        assert result in (None, 0)


class TestEndpointIntegration:
    """End-to-end: the live eval_set.csv on disk gives a sensible count.

    Skipped if the file isn't present in the test environment. When present,
    asserts the count is in a plausible range (the actual gold-standard set
    is 240 rows; we just check >0 and <10k to lock the basic shape)."""

    def test_real_eval_set_yields_plausible_count(self, counter) -> None:
        real_path = REPO_ROOT / "outputs" / "evaluation_data" / "eval_set.csv"
        if not real_path.exists():
            pytest.skip("Live eval_set.csv not present in this checkout")
        count = counter(str(real_path))
        assert count is not None
        assert 0 < count < 10000, f"Implausible eval-set count: {count}"
