"""
Contract test: eval_articles.yaml and eval_articles_data/*/articles.json must stay in sync.

Every (subagent, url) pair in the YAML must have a matching entry in the
corresponding articles.json, and vice versa.  A drift in either direction
means the eval UI will show wrong expected counts or articles with no content.

No DB, no network -- pure file reads.  Runs as part of the default unit suite.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent
_YAML_PATH = _ROOT / "config" / "eval_articles.yaml"
_DATA_DIR = _ROOT / "config" / "eval_articles_data"


def _load_yaml_pairs() -> dict[str, set[str]]:
    """Return {subagent: {url, ...}} from eval_articles.yaml."""
    with open(_YAML_PATH) as f:
        cfg = yaml.safe_load(f) or {}
    result: dict[str, set[str]] = defaultdict(set)
    for subagent, articles in cfg.get("subagents", {}).items():
        if not isinstance(articles, list):
            continue
        for entry in articles:
            if entry and entry.get("url"):
                result[subagent].add(entry["url"])
    return dict(result)


def _load_yaml_counts() -> dict[str, dict[str, int]]:
    """Return {subagent: {url: expected_count, ...}} from eval_articles.yaml."""
    with open(_YAML_PATH) as f:
        cfg = yaml.safe_load(f) or {}
    result: dict[str, dict[str, int]] = defaultdict(dict)
    for subagent, articles in cfg.get("subagents", {}).items():
        if not isinstance(articles, list):
            continue
        for entry in articles:
            if entry and entry.get("url") and "expected_count" in entry:
                result[subagent][entry["url"]] = entry["expected_count"]
    return dict(result)


def _load_json_pairs() -> dict[str, set[str]]:
    """Return {subagent: {url, ...}} from eval_articles_data/*/articles.json."""
    result: dict[str, set[str]] = defaultdict(set)
    if not _DATA_DIR.exists():
        return dict(result)
    for subdir in _DATA_DIR.iterdir():
        if not subdir.is_dir():
            continue
        articles_path = subdir / "articles.json"
        if not articles_path.exists():
            continue
        with open(articles_path) as f:
            articles = json.load(f)
        if not isinstance(articles, list):
            continue
        for entry in articles:
            if entry.get("url"):
                result[subdir.name].add(entry["url"])
    return dict(result)


def _load_json_counts() -> dict[str, dict[str, int]]:
    """Return {subagent: {url: expected_count, ...}} from articles.json files."""
    result: dict[str, dict[str, int]] = defaultdict(dict)
    if not _DATA_DIR.exists():
        return dict(result)
    for subdir in _DATA_DIR.iterdir():
        if not subdir.is_dir():
            continue
        articles_path = subdir / "articles.json"
        if not articles_path.exists():
            continue
        with open(articles_path) as f:
            articles = json.load(f)
        if not isinstance(articles, list):
            continue
        for entry in articles:
            if entry.get("url") and "expected_count" in entry:
                result[subdir.name][entry["url"]] = entry["expected_count"]
    return dict(result)


def _build_stale_params() -> list[pytest.param]:
    """(subagent, url) pairs in YAML with no matching articles.json entry."""
    yaml_pairs = _load_yaml_pairs()
    json_pairs = _load_json_pairs()
    params = []
    for subagent, urls in yaml_pairs.items():
        json_urls = json_pairs.get(subagent, set())
        for url in sorted(urls - json_urls):
            params.append(pytest.param(subagent, url, id=f"{subagent}::{url}"))
    return params or [pytest.param("__none__", "__none__", id="no_stale_entries")]


def _build_missing_params() -> list[pytest.param]:
    """(subagent, url) pairs in articles.json with no YAML entry."""
    yaml_pairs = _load_yaml_pairs()
    json_pairs = _load_json_pairs()
    params = []
    for subagent, urls in json_pairs.items():
        yaml_urls = yaml_pairs.get(subagent, set())
        for url in sorted(urls - yaml_urls):
            params.append(pytest.param(subagent, url, id=f"{subagent}::{url}"))
    return params or [pytest.param("__none__", "__none__", id="no_missing_entries")]


def _build_count_mismatch_params() -> list[pytest.param]:
    """(subagent, url) pairs whose expected_count differs between YAML and articles.json.

    Only checks URLs present in BOTH files (so this test stays orthogonal to the
    URL-presence tests above; one file having the URL and the other not is already
    flagged by test_yaml_has_no_stale_entries / test_yaml_covers_all_seed_articles).
    """
    yaml_counts = _load_yaml_counts()
    json_counts = _load_json_counts()
    params = []
    for subagent in sorted(set(yaml_counts) | set(json_counts)):
        yaml_for = yaml_counts.get(subagent, {})
        json_for = json_counts.get(subagent, {})
        common_urls = set(yaml_for) & set(json_for)
        for url in sorted(common_urls):
            if yaml_for[url] != json_for[url]:
                params.append(pytest.param(subagent, url, id=f"{subagent}::{url}"))
    return params or [pytest.param("__none__", "__none__", id="no_count_mismatches")]


@pytest.mark.unit
@pytest.mark.contract
@pytest.mark.parametrize("subagent,url", _build_stale_params())
def test_yaml_has_no_stale_entries(subagent: str, url: str) -> None:
    """Every URL in eval_articles.yaml must exist in the matching articles.json."""
    if subagent == "__none__":
        return  # sentinel: nothing to check
    json_pairs = _load_json_pairs()
    assert url in json_pairs.get(subagent, set()), (
        f"eval_articles.yaml has [{subagent}] {url} "
        f"but config/eval_articles_data/{subagent}/articles.json has no entry for it. "
        f"Either add the article to the JSON seed file or remove it from the YAML."
    )


@pytest.mark.unit
@pytest.mark.contract
@pytest.mark.parametrize("subagent,url", _build_missing_params())
def test_yaml_covers_all_seed_articles(subagent: str, url: str) -> None:
    """Every URL in articles.json must have an expected_count entry in eval_articles.yaml."""
    if subagent == "__none__":
        return  # sentinel: nothing to check
    yaml_pairs = _load_yaml_pairs()
    assert url in yaml_pairs.get(subagent, set()), (
        f"config/eval_articles_data/{subagent}/articles.json has {url} "
        f"but eval_articles.yaml has no [{subagent}] entry for it. "
        f"Add the URL with an expected_count to eval_articles.yaml."
    )


@pytest.mark.unit
@pytest.mark.contract
@pytest.mark.parametrize("subagent,url", _build_count_mismatch_params())
def test_yaml_and_json_expected_count_agree(subagent: str, url: str) -> None:
    """expected_count for a URL must match between eval_articles.yaml and articles.json.

    Eval scoring (evaluation_api.py:1131) uses YAML expected_count by default and
    falls back to articles.json on missing entries. If the two diverge for the same
    URL, results depend on which code path the eval run takes -- silently producing
    different score values for the same URL. Tighten the contract by failing CI on
    drift.
    """
    if subagent == "__none__":
        return  # sentinel: nothing to check
    yaml_counts = _load_yaml_counts()
    json_counts = _load_json_counts()
    yaml_ec = yaml_counts.get(subagent, {}).get(url)
    json_ec = json_counts.get(subagent, {}).get(url)
    assert yaml_ec == json_ec, (
        f"[{subagent}] {url}: "
        f"eval_articles.yaml expected_count={yaml_ec}, "
        f"articles.json expected_count={json_ec}. "
        f"Update both files to agree, or run scripts/fetch_eval_articles_static.py "
        f"if the YAML is the source of truth."
    )
