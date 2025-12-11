"""
Unit tests for the annotations export endpoint.
"""

from __future__ import annotations

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
            highlighted_text="Example text with emoji 😊",
            classification="Huntable",
            article_title="Threat Report",
            classification_date=datetime(2025, 12, 8, 17, 0, 0),
        )
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
    assert body.startswith("\ufeff".encode("utf-8"))

    text = body.decode("utf-8")
    assert "Example text with emoji 😊" in text
    assert "Threat Report" in text
    assert "Huntable" in text
    assert 'attachment; filename="' in response.headers["content-disposition"]
