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
