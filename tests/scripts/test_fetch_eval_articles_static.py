"""Regression tests for the one-time eval-fixture refresh script."""

import asyncio
import importlib.util
import json
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


def _run_process_subagent(monkeypatch, articles_def, existing_by_url, fetch_article):
    monkeypatch.setattr(fetch_eval_articles_static, "fetch_article", fetch_article)
    return asyncio.run(
        fetch_eval_articles_static.process_subagent(
            "test_agent",
            articles_def,
            asyncio.Semaphore(1),
            {},
            {},
            existing_by_url,
            {},
            {},
        )
    )


def test_fetch_failure_keeps_existing_entry_and_refreshes_siblings(monkeypatch, capsys):
    async def fetch_article(url):
        if url == "https://example.test/fails":
            raise RuntimeError("network unavailable")
        return "Fresh title", "x" * 600

    outcome = _run_process_subagent(
        monkeypatch,
        [
            {"url": "https://example.test/fails", "expected_count": 1},
            {"url": "https://example.test/fresh", "expected_count": 2},
        ],
        {
            "https://example.test/fails": {
                "url": "https://example.test/fails",
                "title": "Existing title",
                "content": "existing content",
                "expected_count": 1,
            }
        },
        fetch_article,
    )

    assert outcome.refreshed == 1
    assert outcome.kept_existing == [("https://example.test/fails", "network unavailable")]
    assert outcome.failed == []
    assert outcome.articles == [
        {
            "url": "https://example.test/fails",
            "title": "Existing title",
            "content": "existing content",
            "expected_count": 1,
        },
        {
            "url": "https://example.test/fresh",
            "title": "Fresh title",
            "content": "x" * 600,
            "expected_count": 2,
        },
    ]
    assert "KEEP: https://example.test/fails" in capsys.readouterr().out


def test_title_shell_keeps_existing_entry(monkeypatch):
    async def fetch_article(_url):
        return "Bot wall", "x" * 63

    outcome = _run_process_subagent(
        monkeypatch,
        [{"url": "https://example.test/shell", "expected_count": 1}],
        {
            "https://example.test/shell": {
                "url": "https://example.test/shell",
                "title": "Existing title",
                "content": "existing content",
                "expected_count": 1,
            }
        },
        fetch_article,
    )

    assert outcome.refreshed == 0
    assert outcome.kept_existing[0][1].startswith("cleaned article content is too short")
    assert outcome.articles[0]["content"] == "existing content"


def test_ground_truth_loss_keeps_existing_entry(monkeypatch):
    async def fetch_article(_url):
        return "Fresh title", "unrelated refreshed body " + "x" * 600

    original = {
        "url": "https://example.test/ground-truth",
        "title": "Existing title",
        "content": "prior body with reg save HKLM\\SYSTEM C:\\temp\\system.hive " + "x" * 600,
        "expected_count": 1,
    }
    monkeypatch.setattr(fetch_eval_articles_static, "fetch_article", fetch_article)
    outcome = asyncio.run(
        fetch_eval_articles_static.process_subagent(
            "test_agent",
            [{"url": original["url"], "expected_count": 1}],
            asyncio.Semaphore(1),
            {},
            {},
            {original["url"]: original},
            {original["url"]: ["reg save HKLM\\SYSTEM C:\\temp\\system.hive"]},
            {},
        )
    )

    assert outcome.refreshed == 0
    assert outcome.kept_existing[0][1].startswith("refresh lost 1 previously supported")
    assert outcome.articles == [original]


def test_fetch_failure_without_existing_entry_is_fatal(monkeypatch):
    async def fetch_article(_url):
        raise RuntimeError("network unavailable")

    outcome = _run_process_subagent(
        monkeypatch,
        [{"url": "https://example.test/missing", "expected_count": 1}],
        {},
        fetch_article,
    )

    assert outcome.articles is None
    assert outcome.failed == [("https://example.test/missing", "network unavailable")]


def test_permanently_retained_url_is_not_fetched(monkeypatch):
    url = next(iter(fetch_eval_articles_static.NEVER_REFRESH_URLS))

    async def fetch_article(_url):
        raise AssertionError("permanently retained URL must not be fetched")

    outcome = _run_process_subagent(
        monkeypatch,
        [{"url": url, "expected_count": 13}],
        {url: {"url": url, "title": "Existing", "content": "existing", "expected_count": 13}},
        fetch_article,
    )

    assert outcome.refreshed == 0
    assert outcome.kept_existing == [(url, "URL is permanently retained after ground-truth retention failure")]


def test_shared_url_fetch_is_reused_with_byte_identical_content(monkeypatch):
    calls = 0

    async def fetch_article(_url):
        nonlocal calls
        calls += 1
        return "Fresh title", "x" * 600 + "\u2013"

    fetched_by_url = {}
    failures_by_url = {}
    args = (
        "test_agent",
        [{"url": "https://example.test/shared", "expected_count": 1}],
        asyncio.Semaphore(1),
        fetched_by_url,
        failures_by_url,
        {},
        {},
        {},
    )
    monkeypatch.setattr(fetch_eval_articles_static, "fetch_article", fetch_article)
    first = asyncio.run(fetch_eval_articles_static.process_subagent(*args))
    second = asyncio.run(fetch_eval_articles_static.process_subagent(*args))

    assert calls == 1
    assert first.articles[0]["content"] == second.articles[0]["content"]


def test_main_exits_nonzero_for_partial_refresh(monkeypatch):
    async def partial_refresh():
        return True

    monkeypatch.setattr(fetch_eval_articles_static, "main_async", partial_refresh)

    with pytest.raises(SystemExit) as exc_info:
        fetch_eval_articles_static.main()

    assert exc_info.value.code == 1


def test_main_async_reconciles_guard_rejection_across_shared_url(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "eval_articles.yaml"
    data_dir = tmp_path / "data"
    shared_url = "https://example.test/shared"
    config_path.write_text(
        "subagents:\n"
        "  first:\n"
        f"    - url: {shared_url}\n"
        "      expected_count: 1\n"
        "  second:\n"
        f"    - url: {shared_url}\n"
        "      expected_count: 1\n"
    )
    existing_content = "prior body with preserved item " + "x" * 600
    for subagent in ("first", "second"):
        fixture_dir = data_dir / subagent
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "articles.json").write_text(
            json.dumps(
                [
                    {
                        "url": shared_url,
                        "title": "Existing title",
                        "content": existing_content,
                        "expected_count": 1,
                    }
                ]
            )
        )
    (data_dir / "second" / "ground_truth.json").write_text(
        json.dumps([{"url": shared_url, "expected_items": ["preserved item"]}])
    )

    async def fetch_article(_url):
        return "Fresh title", "fresh body without that item " + "x" * 600

    monkeypatch.setattr(fetch_eval_articles_static, "CONFIG_EVAL_ARTICLES", config_path)
    monkeypatch.setattr(fetch_eval_articles_static, "DATA_DIR", data_dir)
    monkeypatch.setattr(fetch_eval_articles_static, "fetch_article", fetch_article)

    assert asyncio.run(fetch_eval_articles_static.main_async()) is True
    first = json.loads((data_dir / "first" / "articles.json").read_text())[0]
    second = json.loads((data_dir / "second" / "articles.json").read_text())[0]
    assert first["content"] == second["content"] == existing_content
    assert "Summary: 0 refreshed, 1 kept-existing (refresh lost 1 previously supported" in capsys.readouterr().out
