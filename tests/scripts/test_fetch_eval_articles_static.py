"""Regression tests for the one-time eval-fixture refresh script."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "fetch_eval_articles_static.py"
_SPEC = importlib.util.spec_from_file_location("fetch_eval_articles_static", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
fetch_eval_articles_static = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fetch_eval_articles_static)


def test_rejects_title_only_bot_wall_shell():
    with pytest.raises(ValueError, match="too short"):
        fetch_eval_articles_static._validate_content_length("CrowdStrike article title")


def test_rejects_major_regression_against_committed_fixture():
    with pytest.raises(ValueError, match="regressed"):
        fetch_eval_articles_static._validate_content_length("x" * 5_877, "x" * 20_378)


def test_allows_substantial_first_fetch_without_prior_fixture():
    fetch_eval_articles_static._validate_content_length("x" * 500)


def test_rejects_refresh_that_loses_previously_supported_ground_truth_item():
    with pytest.raises(ValueError, match="lost 1 previously supported"):
        fetch_eval_articles_static._validate_ground_truth_retention(
            "unrelated refreshed body",
            "prior body with reg save HKLM\\SYSTEM C:\\temp\\system.hive",
            ["reg save HKLM\\SYSTEM C:\\temp\\system.hive"],
        )


def test_allows_preexisting_ground_truth_gap():
    fetch_eval_articles_static._validate_ground_truth_retention(
        "refreshed body", "prior body", ["missing in both bodies"]
    )
