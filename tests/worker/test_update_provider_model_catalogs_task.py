"""The daily catalog job must surface models missing from config/model_capabilities.json."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.worker.celery_app import _parse_unclassified_models, update_provider_model_catalogs

pytestmark = pytest.mark.unit


def _run_with_stdout(stdout: str):
    completed = SimpleNamespace(returncode=0, stdout=stdout, stderr="")
    with patch("src.worker.celery_app.subprocess.run", return_value=completed):
        if hasattr(update_provider_model_catalogs, "apply"):
            return update_provider_model_catalogs.apply().get()
        # tests/worker/conftest.py strips the Celery decorator; call the bound body directly.
        fake_task = SimpleNamespace(request=SimpleNamespace(retries=0), retry=lambda **_: None)
        return update_provider_model_catalogs(fake_task)


def test_parse_reads_the_last_marker_line():
    stdout = 'noise\nUNCLASSIFIED_MODELS={"openai": ["gpt-9"]}\n'
    assert _parse_unclassified_models(stdout) == {"openai": ["gpt-9"]}
    assert _parse_unclassified_models("no marker") == {}
    assert _parse_unclassified_models("UNCLASSIFIED_MODELS=not json") == {}


def test_unclassified_models_are_warned_and_returned(caplog):
    with caplog.at_level(logging.WARNING, logger="src.worker.celery_app"):
        result = _run_with_stdout(
            'Updated provider model catalog JSON\nUNCLASSIFIED_MODELS={"openai": ["gpt-9"], "anthropic": ["claude-x"]}\n'
        )
    assert result["status"] == "success"
    assert result["unclassified_models"] == ["anthropic:claude-x", "openai:gpt-9"]
    warning = [
        r for r in caplog.records if r.levelno == logging.WARNING and "model_capabilities.json" in r.getMessage()
    ]
    assert warning, "expected a WARNING naming the unclassified models"
    assert "openai:gpt-9" in warning[0].getMessage()
    assert "anthropic:claude-x" in warning[0].getMessage()


def test_fully_classified_catalog_produces_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="src.worker.celery_app"):
        result = _run_with_stdout("Updated provider model catalog JSON\nUNCLASSIFIED_MODELS={}\n")
    assert result["status"] == "success"
    assert result["unclassified_models"] == []
    assert not [r for r in caplog.records if "model_capabilities.json" in r.getMessage()]
