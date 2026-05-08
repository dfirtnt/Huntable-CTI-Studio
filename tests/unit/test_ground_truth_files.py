"""Data integrity tests for config/eval_articles_data/*/ground_truth.json.

These files are hand-authored (or agent-drafted) item-level ground truth used
by eval2's precision/recall/F1 scoring.  They are not generated at runtime, so
a static validation test is the right backstop: catch schema drift, broken URL
cross-refs, and malformed JSON before a bad file silently zeroes out scores.

No server or DB needed -- all assertions are against files on disk.
"""

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).parent.parent.parent / "config" / "eval_articles_data"

SUBAGENTS = [
    "cmdline",
    "hunt_queries",
    "process_lineage",
    "registry_artifacts",
    "scheduled_tasks",
    "windows_services",
]


def _load_ground_truth(subagent: str) -> list[dict]:
    path = ROOT / subagent / "ground_truth.json"
    assert path.exists(), f"ground_truth.json missing for {subagent}: {path}"
    with open(path) as f:
        return json.load(f)


def _load_articles(subagent: str) -> list[dict]:
    path = ROOT / subagent / "articles.json"
    assert path.exists(), f"articles.json missing for {subagent}: {path}"
    with open(path) as f:
        return json.load(f)


@pytest.mark.parametrize("subagent", SUBAGENTS)
def test_ground_truth_is_valid_json_list(subagent):
    """ground_truth.json must be a non-empty JSON array."""
    data = _load_ground_truth(subagent)
    assert isinstance(data, list), f"{subagent}: top-level must be a list"
    assert len(data) > 0, f"{subagent}: ground_truth.json is empty"


@pytest.mark.parametrize("subagent", SUBAGENTS)
def test_ground_truth_entry_schema(subagent):
    """Every entry must have 'url' (str) and 'expected_items' (list)."""
    data = _load_ground_truth(subagent)
    for i, entry in enumerate(data):
        assert isinstance(entry, dict), f"{subagent}[{i}]: entry must be a dict"
        assert "url" in entry, f"{subagent}[{i}]: missing 'url'"
        assert isinstance(entry["url"], str), f"{subagent}[{i}]: 'url' must be a str"
        assert entry["url"].startswith("http"), f"{subagent}[{i}]: url looks malformed"
        assert "expected_items" in entry, f"{subagent}[{i}]: missing 'expected_items'"
        assert isinstance(entry["expected_items"], list), (
            f"{subagent}[{i}]: 'expected_items' must be a list, got "
            f"{type(entry['expected_items'])}"
        )
        for j, item in enumerate(entry["expected_items"]):
            assert isinstance(item, str), (
                f"{subagent}[{i}].expected_items[{j}]: items must be strings"
            )
            assert item.strip(), (
                f"{subagent}[{i}].expected_items[{j}]: item is blank"
            )


@pytest.mark.parametrize("subagent", SUBAGENTS)
def test_ground_truth_urls_exist_in_articles(subagent):
    """Every URL in ground_truth.json must appear in articles.json.

    A stale URL (e.g. after renaming an article) means the ground truth is
    silently ignored at eval time -- the scorer never finds a matching article.
    """
    gt_data = _load_ground_truth(subagent)
    art_data = _load_articles(subagent)
    article_urls = {a["url"] for a in art_data}
    orphans = [e["url"] for e in gt_data if e["url"] not in article_urls]
    assert not orphans, (
        f"{subagent}: ground_truth.json has URLs not in articles.json: {orphans}"
    )


@pytest.mark.parametrize("subagent", SUBAGENTS)
def test_ground_truth_covers_all_articles(subagent):
    """Every article in articles.json should have a matching entry in ground_truth.json.

    Missing entries mean the article is silently unannotated (falls back to
    count-only display on eval2).  This is a warning-level check, not a hard
    failure, but we want it tracked.
    """
    gt_data = _load_ground_truth(subagent)
    art_data = _load_articles(subagent)
    gt_urls = {e["url"] for e in gt_data}
    unannotated = [a["url"] for a in art_data if a["url"] not in gt_urls]
    assert not unannotated, (
        f"{subagent}: articles.json has URLs without a ground_truth.json entry: "
        f"{unannotated}"
    )


@pytest.mark.parametrize("subagent", SUBAGENTS)
def test_ground_truth_no_duplicate_urls(subagent):
    """Each URL should appear at most once per ground_truth.json."""
    data = _load_ground_truth(subagent)
    urls = [e["url"] for e in data]
    seen = set()
    duplicates = [u for u in urls if u in seen or seen.add(u)]
    assert not duplicates, f"{subagent}: duplicate URLs in ground_truth.json: {duplicates}"


@pytest.mark.parametrize("subagent", SUBAGENTS)
def test_ground_truth_ascii_only(subagent):
    """Items must be ASCII-only (repo convention).

    Non-ASCII characters (smart quotes, em-dashes, etc.) can silently break
    exact-match scoring when the extractor outputs plain ASCII.
    """
    data = _load_ground_truth(subagent)
    violations = []
    for entry in data:
        for item in entry.get("expected_items", []):
            try:
                item.encode("ascii")
            except UnicodeEncodeError:
                violations.append((entry["url"], repr(item)))
    assert not violations, (
        f"{subagent}: non-ASCII characters found in expected_items: {violations}"
    )
