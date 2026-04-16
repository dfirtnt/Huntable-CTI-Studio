"""Unit tests for seed_eval_articles service (run return reason, _load_articles_by_url)."""

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from src.services.seed_eval_articles import _load_articles_by_url, run

pytestmark = pytest.mark.unit

_EVAL_DATA_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent / "config" / "eval_articles_data"
_EVAL_SETS = (
    [p.name for p in _EVAL_DATA_ROOT.iterdir() if (p / "articles.json").exists()] if _EVAL_DATA_ROOT.exists() else []
)


class TestEvalArticleDataIntegrity:
    """Data integrity checks on config/eval_articles_data JSON files.

    These are regression guards: failures here mean the seed data was
    corrupted or reverted to a known-bad state.
    """

    @pytest.fixture(params=_EVAL_SETS)
    def articles(self, request):
        path = _EVAL_DATA_ROOT / request.param / "articles.json"
        return request.param, json.loads(path.read_text())

    def test_no_untitled_articles(self, articles):
        """Regression: no entry may have the scraper fallback title 'Untitled Article'."""
        set_name, data = articles
        offenders = [a.get("url", "<no url>") for a in data if a.get("title") == "Untitled Article"]
        assert offenders == [], f"{set_name}: {len(offenders)} article(s) still have 'Untitled Article': {offenders}"

    def test_all_entries_have_non_empty_url(self, articles):
        set_name, data = articles
        missing = [i for i, a in enumerate(data) if not a.get("url", "").strip()]
        assert missing == [], f"{set_name}: entries at indices {missing} are missing a url"

    def test_all_entries_have_non_empty_title(self, articles):
        set_name, data = articles
        missing = [a.get("url", f"index:{i}") for i, a in enumerate(data) if not a.get("title", "").strip()]
        assert missing == [], f"{set_name}: {len(missing)} article(s) have empty title: {missing}"

    def test_all_entries_have_non_negative_expected_count(self, articles):
        set_name, data = articles
        bad = [
            a.get("url", f"index:{i}")
            for i, a in enumerate(data)
            if not isinstance(a.get("expected_count"), int) or a["expected_count"] < 0
        ]
        assert bad == [], f"{set_name}: {len(bad)} article(s) have invalid expected_count: {bad}"

    def test_process_lineage_titles_are_real(self):
        """Regression: the 8 DFIR Report articles that were 'Untitled Article' must have real titles."""
        path = _EVAL_DATA_ROOT / "process_lineage" / "articles.json"
        data = json.loads(path.read_text())
        dfir_articles = [a for a in data if "thedfirreport.com" in a.get("url", "")]
        assert dfir_articles, "Expected at least one thedfirreport.com article in process_lineage"
        offenders = [a["url"] for a in dfir_articles if a.get("title") in (None, "", "Untitled Article")]
        assert offenders == [], f"DFIR Report articles still lack real titles: {offenders}"


class TestLoadArticlesByUrl:
    """Test _load_articles_by_url with temp dirs."""

    def test_returns_empty_when_dir_missing(self, tmp_path):
        """Missing data_dir returns empty dict."""
        data_dir = tmp_path / "nonexistent"
        assert not data_dir.exists()
        assert _load_articles_by_url(data_dir) == {}

    def test_returns_empty_when_no_articles_json(self, tmp_path):
        """Empty dir or no articles.json returns empty."""
        (tmp_path / "cmdline").mkdir()
        assert _load_articles_by_url(tmp_path) == {}

    def test_loads_first_url_wins(self, tmp_path):
        """Loads articles from subdir/articles.json; first URL wins on duplicate."""
        sub = tmp_path / "cmdline"
        sub.mkdir()
        (sub / "articles.json").write_text(
            json.dumps(
                [
                    {"url": "https://a.com/1", "title": "First", "content": "c1"},
                    {"url": "https://a.com/1", "title": "Second", "content": "c2"},
                    {"url": "https://b.com/2", "title": "B", "content": "c3"},
                ]
            )
        )
        by_url = _load_articles_by_url(tmp_path)
        assert len(by_url) == 2
        assert by_url["https://a.com/1"]["title"] == "First"
        assert by_url["https://b.com/2"]["title"] == "B"

    def test_skips_entry_without_url(self, tmp_path):
        """Entries without url are skipped."""
        sub = tmp_path / "x"
        sub.mkdir()
        (sub / "articles.json").write_text(json.dumps([{"title": "No URL", "content": "x"}]))
        assert _load_articles_by_url(tmp_path) == {}


class TestRunReturnReason:
    """Test run() return (created_count, error_count, reason)."""

    @pytest.fixture
    def mock_db(self):
        """Mock DatabaseManager and session."""
        session = MagicMock()
        manager = MagicMock()
        manager.get_session.return_value.__enter__ = MagicMock(return_value=session)
        manager.get_session.return_value.__exit__ = MagicMock(return_value=None)
        return manager, session

    def test_returns_no_config_data_when_no_articles(self, tmp_path, mock_db):
        """When data_dir has no articles, returns (0, 0, 'no_config_data')."""
        manager, session = mock_db
        session.query.return_value.filter.return_value.first.return_value = MagicMock(id=1)

        with patch("src.services.seed_eval_articles.DatabaseManager", return_value=manager):
            with patch("src.services.seed_eval_articles._project_root", return_value=tmp_path):
                created, errors, reason = run(project_root=tmp_path)

        assert created == 0
        assert errors == 0
        assert reason == "no_config_data"

    def test_returns_already_present_when_all_urls_exist(self, tmp_path, mock_db):
        """When all article URLs already in DB, returns (0, 0, 'already_present')."""
        manager, session = mock_db
        # _get_or_create_eval_source
        session.query.return_value.filter.return_value.first.return_value = MagicMock(id=1)
        # existing_urls query: return both URLs so to_create is empty
        session.query.return_value.filter.return_value.all.return_value = [
            ("https://a.com/1",),
            ("https://b.com/2",),
        ]

        data_dir = tmp_path / "config" / "eval_articles_data"
        data_dir.mkdir(parents=True)
        (data_dir / "cmdline").mkdir()
        (data_dir / "cmdline" / "articles.json").write_text(
            json.dumps(
                [
                    {"url": "https://a.com/1", "title": "A", "content": ""},
                    {"url": "https://b.com/2", "title": "B", "content": ""},
                ]
            )
        )

        with patch("src.services.seed_eval_articles.DatabaseManager", return_value=manager):
            # First call: source_id; then get_session for existing_urls (all)
            def first_all(*args, **kwargs):
                q = session.query.return_value.filter.return_value
                if hasattr(q, "all"):
                    return [("https://a.com/1",), ("https://b.com/2",)]
                return []

            session.query.return_value.filter.return_value.all.return_value = [
                ("https://a.com/1",),
                ("https://b.com/2",),
            ]

            created, errors, reason = run(project_root=tmp_path)

        assert created == 0
        assert errors == 0
        assert reason == "already_present"

    def test_returns_created_errors_empty_reason_when_some_created(self, tmp_path, mock_db):
        """When some articles created, returns (created, errors, '')."""
        manager, session = mock_db
        session.query.return_value.filter.return_value.first.return_value = MagicMock(id=1)
        session.query.return_value.filter.return_value.all.return_value = []  # no existing URLs

        data_dir = tmp_path / "config" / "eval_articles_data"
        data_dir.mkdir(parents=True)
        (data_dir / "cmdline").mkdir()
        (data_dir / "cmdline" / "articles.json").write_text(
            json.dumps(
                [
                    {"url": "https://new.com/1", "title": "New", "content": "body"},
                ]
            )
        )

        created_articles = [MagicMock(id=10)]
        manager.create_articles_bulk = MagicMock(return_value=(created_articles, []))

        with patch("src.services.seed_eval_articles.DatabaseManager", return_value=manager):
            created, errors, reason = run(project_root=tmp_path)

        assert created == 1
        assert errors == 0
        assert reason == ""
