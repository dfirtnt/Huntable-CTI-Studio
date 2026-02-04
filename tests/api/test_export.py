"""
Unit tests for the annotations export endpoint.
"""

from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.web.routes import export as export_module


class _FakeResult:
    """Minimal fake result to satisfy SQLAlchemy query interface."""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def fetchall(self) -> list[SimpleNamespace]:
        return self._rows


class _FakeSession:
    """Fake session that returns a predefined set of annotation rows."""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    async def execute(self, query):
        return _FakeResult(self._rows)


@asynccontextmanager
async def _fake_session(rows: list[SimpleNamespace]):
    yield _FakeSession(rows)


@pytest.mark.asyncio
async def test_export_annotations_return_csv_with_bom(monkeypatch):
    """The export endpoint should return UTF-8 CSV data with a BOM."""
    rows = [
        SimpleNamespace(
            record_number=1,
            highlighted_text='Example text with emoji 😊\nand a newline, plus a comma, "quoted"',
            classification="Huntable",
            article_title="Threat Report",
            classification_date=datetime(2025, 12, 8, 17, 0, 0),
            annotation_type="huntable",
            usage="train",
            used_for_training=True,
            confidence_score=0.85,
            context_before="before",
            context_after="after",
        ),
        SimpleNamespace(
            record_number=2,
            highlighted_text="Path with escapes C:\\\\Program Files\\\\WinRAR\\\\WinRAR.exe",
            classification="Huntable",
            article_title="Paths",
            classification_date=datetime(2025, 12, 8, 17, 5, 0),
            annotation_type="CMD",
            usage="eval",
            used_for_training=False,
            confidence_score=0.15,
            context_before="",
            context_after="",
        ),
    ]

    monkeypatch.setattr(
        export_module.async_db_manager,
        "get_session",
        lambda: _fake_session(rows),
    )

    response = await export_module.api_export_annotations()

    assert response.status_code == 200
    content_type = response.headers["content-type"]
    assert "text/csv" in content_type
    assert "charset=utf-8" in content_type

    body = response.body
    assert isinstance(body, bytes)
    assert body.startswith("\ufeff".encode())

    text = body.decode("utf-8")
    assert "Example text with emoji 😊" in text
    assert '"quoted"' in text
    assert "Threat Report" in text
    assert "Huntable" in text
    assert 'attachment; filename="' in response.headers["content-disposition"]

    # Ensure we can round-trip the CSV without losing fields.
    reader = csv.reader(io.StringIO(text.lstrip("\ufeff")))
    rows = list(reader)
    assert len(rows) == 3  # header + two rows
    # Validate header columns (annotation metadata included).
    header = rows[0]
    assert "annotation_mode" in header
    assert "annotation_type" in header
    assert header.index("annotation_mode") == 3

    # Validate first (huntability) row metadata
    first_row = rows[1]
    assert first_row[1].startswith("Example text")
    assert first_row[3] == "Huntability"
    assert first_row[4] == "huntable"
    assert first_row[5] == "train"
    assert first_row[6] == "True"
    assert first_row[7] == "0.85"

    # Validate observable row
    second_row = rows[2]
    assert second_row[1].startswith("Path with escapes")
    assert second_row[3] == "Observables"
    assert second_row[4] == "CMD"
    assert second_row[5] == "eval"
    assert second_row[6] == "False"
    assert second_row[7] == "0.15"
    assert "WinRAR.exe" in second_row[1]
