"""Regression tests for safeguards in the one-time article rescrape script."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "rescrape_collapsed_articles.py"
_SPEC = importlib.util.spec_from_file_location("rescrape_collapsed_articles", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
rescrape_collapsed_articles = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rescrape_collapsed_articles)

_DEFAULT_RATIO = rescrape_collapsed_articles.DEFAULT_MIN_EXISTING_CONTENT_RATIO
_LOOSE_RATIO = rescrape_collapsed_articles.LOOSE_MIN_EXISTING_CONTENT_RATIO


# ---------------------------------------------------------------------------
# Absolute floor: title shells are never a valid refresh
# ---------------------------------------------------------------------------


def test_rejects_title_shell_content():
    with pytest.raises(ValueError, match="too short"):
        rescrape_collapsed_articles._validate_refresh_content("x" * 10_000, "title\n")


def test_rejects_content_just_below_min_chars():
    min_chars = rescrape_collapsed_articles.MIN_REFRESH_CONTENT_CHARS
    # Ratio is fine (1.0x) — only the absolute char floor should reject this.
    body = "x" * (min_chars - 2) + "\n"
    with pytest.raises(ValueError, match="too short"):
        rescrape_collapsed_articles._validate_refresh_content(body, body)


def test_accepts_content_at_min_chars():
    min_chars = rescrape_collapsed_articles.MIN_REFRESH_CONTENT_CHARS
    body = "x" * (min_chars - 1) + "\n"
    assert rescrape_collapsed_articles._validate_refresh_content(body, body) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Drift floor: the default must be strict enough to catch real page edits
# ---------------------------------------------------------------------------


def test_default_ratio_is_strict():
    assert _DEFAULT_RATIO == 0.95


def test_rejects_ratio_just_under_default_threshold():
    existing = "x" * 10_000
    # 0.94x — just under the 0.95 floor.
    fresh = "x" * 9_399 + "\n"
    with pytest.raises(ValueError, match="regressed"):
        rescrape_collapsed_articles._validate_refresh_content(existing, fresh)


def test_accepts_ratio_just_over_default_threshold():
    existing = "x" * 10_000
    # 0.9501x — just over the 0.95 floor.
    fresh = "x" * 9_500 + "\n"
    ratio = rescrape_collapsed_articles._validate_refresh_content(existing, fresh)
    assert ratio == pytest.approx(0.9501)


def test_accepts_ratio_exactly_at_threshold():
    existing = "x" * 10_000
    fresh = "x" * 9_499 + "\n"  # exactly 9_500 chars == 0.95 * 10_000
    ratio = rescrape_collapsed_articles._validate_refresh_content(existing, fresh)
    assert ratio == pytest.approx(0.95)


def test_rejects_measured_sekoia_drift_case():
    """Article 6759: 18,177 stored chars re-fetched at ~14,200 after a page edit.

    0.78x cleared the old 0.5 floor and would have destroyed ~4,000 chars.
    """
    existing = "x" * 18_177
    fresh = "x" * 14_200 + "\n"
    with pytest.raises(ValueError, match="regressed"):
        rescrape_collapsed_articles._validate_refresh_content(existing, fresh)

    # ...and the old permissive floor is exactly what let it through.
    ratio = rescrape_collapsed_articles._validate_refresh_content(existing, fresh, _LOOSE_RATIO)
    assert ratio == pytest.approx(0.78, abs=0.01)


def test_regression_message_reports_both_ratios():
    with pytest.raises(ValueError) as excinfo:
        rescrape_collapsed_articles._validate_refresh_content("x" * 10_000, "x" * 8_000 + "\n")
    message = str(excinfo.value)
    assert "0.80x" in message  # observed drift
    assert "0.95x" in message  # configured floor


# ---------------------------------------------------------------------------
# Explicit escape hatch
# ---------------------------------------------------------------------------


def test_loose_ratio_allows_lossy_overwrite():
    existing = "x" * 10_000
    fresh = "x" * 6_000 + "\n"
    ratio = rescrape_collapsed_articles._validate_refresh_content(existing, fresh, _LOOSE_RATIO)
    assert ratio == pytest.approx(0.6001)


def test_loose_ratio_still_enforces_its_own_floor():
    with pytest.raises(ValueError, match="regressed"):
        rescrape_collapsed_articles._validate_refresh_content("x" * 10_000, "x" * 4_000 + "\n", _LOOSE_RATIO)


# ---------------------------------------------------------------------------
# Structure floor: flat content is never a valid refresh
# ---------------------------------------------------------------------------


def test_rejects_flat_fresh_content():
    with pytest.raises(ValueError, match="0 newlines"):
        rescrape_collapsed_articles._validate_refresh_content("x" * 1_000, "x" * 1_000)


def test_rejects_flat_fresh_content_even_when_larger():
    """A bigger but still-collapsed body is not a repair."""
    with pytest.raises(ValueError, match="0 newlines"):
        rescrape_collapsed_articles._validate_refresh_content("x" * 1_000, "x" * 5_000)


def test_allows_substantial_structured_refresh():
    ratio = rescrape_collapsed_articles._validate_refresh_content("x" * 1_000, "x" * 1_200 + "\n")
    assert ratio == pytest.approx(1.201)


# ---------------------------------------------------------------------------
# Ratio helper
# ---------------------------------------------------------------------------


def test_content_ratio_handles_empty_existing_content():
    assert rescrape_collapsed_articles._content_ratio("", "x" * 100) == float("inf")


def test_content_ratio_matches_length_quotient():
    assert rescrape_collapsed_articles._content_ratio("x" * 400, "x" * 100) == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def test_min_ratio_flag_defaults_to_strict_value():
    args = rescrape_collapsed_articles._build_parser().parse_args([])
    assert args.min_ratio == _DEFAULT_RATIO


def test_min_ratio_flag_accepts_loose_escape_hatch():
    args = rescrape_collapsed_articles._build_parser().parse_args(["--min-ratio", "0.5"])
    assert args.min_ratio == _LOOSE_RATIO


def test_eval_exclusion_constants_still_point_at_fixtures():
    """The eval-URL exclusion is load-bearing; it must not be weakened."""
    assert rescrape_collapsed_articles.EVAL_YAML.name == "eval_articles.yaml"
    assert rescrape_collapsed_articles.EVAL_DATA_DIR.name == "eval_articles_data"
