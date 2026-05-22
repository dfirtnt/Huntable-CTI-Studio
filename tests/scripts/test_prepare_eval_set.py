"""Tests for scripts/prepare_eval_set.py.

Guards three core contracts:

1. Label mapping: "Huntable" → "huntable", "Not Huntable" → "not_huntable";
   unknown labels are dropped, not raised.
2. Length filter: rows with highlighted_text shorter than min_length are dropped.
3. Output schema: kept rows carry all OUTPUT_FIELDS columns with labels
   restricted to {"huntable", "not_huntable"} — the exact constraint that
   ModelEvaluator validates on load.

All tests are pure unit tests: no filesystem writes, no DB, no LLM calls.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "prepare_eval_set.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("prepare_eval_set", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["prepare_eval_set"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LONG = "A" * 250  # passes default min_length=200
_SHORT = "A" * 100  # fails default min_length=200


def _row(text: str, classification: str, record_number: str = "1", source: str = "test.csv") -> dict:
    return {
        "highlighted_text": text,
        "classification": classification,
        "record_number": record_number,
        "_source_file": source,
        "classification_date": "2026-01-01",
    }


# ---------------------------------------------------------------------------
# Label mapping
# ---------------------------------------------------------------------------


class TestLabelMapping:
    def test_huntable_maps_to_lowercase_huntable(self, script) -> None:
        assert script.LABEL_MAP["Huntable"] == "huntable"

    def test_not_huntable_maps_to_not_huntable_underscore(self, script) -> None:
        assert script.LABEL_MAP["Not Huntable"] == "not_huntable"

    def test_label_map_has_exactly_two_entries(self, script) -> None:
        assert len(script.LABEL_MAP) == 2

    def test_huntable_row_kept_with_correct_label(self, script) -> None:
        kept, dropped = script.build_eval_rows([_row(_LONG, "Huntable")], min_length=200)
        assert len(kept) == 1 and not dropped
        assert kept[0]["label"] == "huntable"

    def test_not_huntable_row_kept_with_correct_label(self, script) -> None:
        kept, dropped = script.build_eval_rows([_row(_LONG, "Not Huntable")], min_length=200)
        assert len(kept) == 1 and not dropped
        assert kept[0]["label"] == "not_huntable"

    def test_unknown_label_dropped_not_raised(self, script) -> None:
        kept, dropped = script.build_eval_rows([_row(_LONG, "Maybe")], min_length=200)
        assert kept == [] and len(dropped) == 1

    def test_empty_label_dropped(self, script) -> None:
        kept, dropped = script.build_eval_rows([_row(_LONG, "")], min_length=200)
        assert kept == [] and len(dropped) == 1

    def test_lowercase_huntable_rejected_as_source_label(self, script) -> None:
        """'huntable' (already-mapped form) is not a valid source label."""
        kept, dropped = script.build_eval_rows([_row(_LONG, "huntable")], min_length=200)
        assert kept == [] and len(dropped) == 1


# ---------------------------------------------------------------------------
# Length filter
# ---------------------------------------------------------------------------


class TestLengthFilter:
    def test_row_exactly_at_min_length_is_kept(self, script) -> None:
        kept, dropped = script.build_eval_rows([_row("B" * 200, "Huntable")], min_length=200)
        assert len(kept) == 1 and not dropped

    def test_row_one_below_min_length_is_dropped(self, script) -> None:
        kept, dropped = script.build_eval_rows([_row("B" * 199, "Huntable")], min_length=200)
        assert not kept and len(dropped) == 1

    def test_short_row_dropped(self, script) -> None:
        kept, dropped = script.build_eval_rows([_row(_SHORT, "Huntable")], min_length=200)
        assert not kept and len(dropped) == 1

    def test_custom_min_length_respected(self, script) -> None:
        text = "C" * 500
        kept_500, _ = script.build_eval_rows([_row(text, "Huntable")], min_length=500)
        kept_501, _ = script.build_eval_rows([_row(text, "Huntable")], min_length=501)
        assert len(kept_500) == 1 and len(kept_501) == 0


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class TestOutputSchema:
    def test_output_fields_contains_model_evaluator_required_columns(self, script) -> None:
        required = {"annotation_id", "chunk_text", "label"}
        assert required.issubset(set(script.OUTPUT_FIELDS))

    def test_kept_row_has_all_output_fields(self, script) -> None:
        kept, _ = script.build_eval_rows([_row(_LONG, "Huntable", record_number="42")], min_length=200)
        for field in script.OUTPUT_FIELDS:
            assert field in kept[0], f"Missing field: {field}"

    def test_annotation_id_from_record_number(self, script) -> None:
        kept, _ = script.build_eval_rows([_row(_LONG, "Huntable", record_number="RN-99")], min_length=200)
        assert kept[0]["annotation_id"] == "RN-99"

    def test_article_id_is_zero(self, script) -> None:
        kept, _ = script.build_eval_rows([_row(_LONG, "Huntable")], min_length=200)
        assert kept[0]["article_id"] == 0

    def test_source_file_populated(self, script) -> None:
        kept, _ = script.build_eval_rows([_row(_LONG, "Not Huntable", source="labeled_2026.csv")], min_length=200)
        assert kept[0]["source_file"] == "labeled_2026.csv"

    def test_output_labels_restricted_to_valid_set(self, script) -> None:
        rows = [
            _row(_LONG, "Huntable"),
            _row(_LONG, "Not Huntable"),
            _row(_SHORT, "Huntable"),  # dropped by length
            _row(_LONG, "BadLabel"),  # dropped by label
        ]
        kept, _ = script.build_eval_rows(rows, min_length=200)
        labels = {r["label"] for r in kept}
        assert labels <= {"huntable", "not_huntable"}

    def test_mixed_batch_correct_counts(self, script) -> None:
        rows = [
            _row(_LONG, "Huntable"),
            _row(_LONG, "Not Huntable"),
            _row(_SHORT, "Huntable"),  # dropped: short
            _row(_LONG, "JUNK"),  # dropped: unknown label
        ]
        kept, dropped = script.build_eval_rows(rows, min_length=200)
        assert len(kept) == 2 and len(dropped) == 2


# ---------------------------------------------------------------------------
# CSV write round-trip: output must satisfy ModelEvaluator column contract
# ---------------------------------------------------------------------------


class TestCsvWriteRoundTrip:
    def test_written_csv_has_required_columns(self, script, tmp_path) -> None:
        rows = [_row(_LONG, "Huntable"), _row(_LONG, "Not Huntable")]
        kept, _ = script.build_eval_rows(rows, min_length=200)
        out = tmp_path / "eval_set.csv"
        with open(out, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=script.OUTPUT_FIELDS).writeheader()
            csv.DictWriter(f, fieldnames=script.OUTPUT_FIELDS).writerows(kept)

        import pandas as pd

        df = pd.read_csv(out)
        for col in ["annotation_id", "chunk_text", "label"]:
            assert col in df.columns

    def test_written_csv_labels_are_valid(self, script, tmp_path) -> None:
        rows = [_row(_LONG, "Huntable"), _row(_LONG, "Not Huntable")]
        kept, _ = script.build_eval_rows(rows, min_length=200)
        out = tmp_path / "eval_set.csv"
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=script.OUTPUT_FIELDS)
            writer.writeheader()
            writer.writerows(kept)

        import pandas as pd

        df = pd.read_csv(out)
        assert set(df["label"].unique()) <= {"huntable", "not_huntable"}
