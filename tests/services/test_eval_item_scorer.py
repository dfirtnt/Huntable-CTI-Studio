"""Unit tests for src.services.eval_item_scorer.score_items.

Covers the normalization rules and the boundary cases that the wire-up in
agentic_workflow.py depends on (especially the zero-extraction case where the
model returned no items but expected_items still has ground truth).
"""

import pytest

from src.services.eval_item_scorer import (
    ItemScorerResult,
    calculate_f_beta,
    item_candidates,
    normalize_identity,
    score_items,
)


@pytest.mark.unit
def test_exact_match_full_recall():
    expected = ["whoami /groups", 'net group "domain admins" /domain']
    actual = ["whoami /groups", 'net group "domain admins" /domain']
    result = score_items(expected, actual)
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.matched_count == 2
    assert result.missed_count == 0
    assert result.extra_count == 0


@pytest.mark.unit
def test_case_insensitive_normalization():
    """Lowercase normalization means casing differences match."""
    expected = ['NET GROUP "Domain Admins" /domain']
    actual = ['net group "domain admins" /domain']
    result = score_items(expected, actual)
    assert result.matched_count == 1
    assert result.missed_count == 0


@pytest.mark.unit
def test_whitespace_collapse_normalization():
    """Internal whitespace runs collapse to single spaces."""
    expected = ["dir   >    out.txt"]
    actual = ["dir > out.txt"]
    result = score_items(expected, actual)
    assert result.matched_count == 1


@pytest.mark.unit
def test_ioc_defang_normalization():
    """[.] and [:] defang markers are normalized to . and : on both sides."""
    expected = ["curl http://evil[.]com/payload"]
    actual = ["curl http://evil.com/payload"]
    result = score_items(expected, actual)
    assert result.matched_count == 1


@pytest.mark.unit
@pytest.mark.parametrize("wrapper", ["cmd /c", "cmd.exe /k", "%COMSPEC% /c"])
def test_cmd_execution_wrappers_match_unwrapped_ground_truth(wrapper):
    """Only supported cmd execution wrappers compare as the contained command."""
    result = score_items(['net group "Domain Admins" /domain'], [f'{wrapper} net group "Domain Admins" /domain'])
    assert result.matched_count == 1
    assert result.missed_count == 0
    assert result.extra_count == 0


@pytest.mark.unit
def test_powershell_wrapper_is_not_stripped():
    result = score_items(["whoami /groups"], ["powershell.exe /c whoami /groups"])
    assert result.matched_count == 0


@pytest.mark.unit
def test_zero_extraction_against_nonempty_expected():
    """Critical case: model returned no items but ground truth has 9 items.

    This is the regression case from agentic_workflow.py -- when the scorer
    was being skipped entirely for actual_items=[] runs, zero-extraction
    runs silently became 'count only' instead of being scored as 0% recall.
    """
    expected = [f"item-{i}" for i in range(9)]
    actual: list[str] = []
    result = score_items(expected, actual)
    assert result.matched_count == 0
    assert result.missed_count == 9
    assert result.extra_count == 0
    assert result.precision == 0.0
    assert result.recall == 0.0


@pytest.mark.unit
def test_empty_expected_with_extras():
    """No ground truth + agent emitted items -- precision must not divide by zero."""
    expected: list[str] = []
    actual = ["whoami /groups", "ipconfig /all"]
    result = score_items(expected, actual)
    assert result.matched_count == 0
    assert result.missed_count == 0
    assert result.extra_count == 2
    assert result.precision == 0.0  # 0 / (0 + 2)
    assert result.recall == 0.0  # 0 / (0 + 0) -> defined as 0 here


@pytest.mark.unit
def test_partial_match_precision_recall():
    expected = ["a", "b", "c", "d"]
    actual = ["a", "b", "x"]  # 2 matched, 1 extra, 2 missed
    result = score_items(expected, actual)
    assert result.matched_count == 2
    assert result.missed_count == 2
    assert result.extra_count == 1
    # Precision = 2 / 3 = 0.6667; Recall = 2 / 4 = 0.5
    assert result.precision == 0.6667
    assert result.recall == 0.5


@pytest.mark.unit
def test_calculate_f_beta_defaults_to_precision_weighted_f05():
    assert calculate_f_beta(2 / 3, 0.5) == pytest.approx(0.625)


@pytest.mark.unit
def test_duplicates_dedup_to_single_match():
    """Same expected item listed twice on either side counts once."""
    expected = ["whoami /groups", "whoami /groups"]
    actual = ["whoami /groups"]
    result = score_items(expected, actual)
    assert result.matched_count == 1
    assert result.missed_count == 0
    assert result.extra_count == 0


@pytest.mark.unit
def test_returns_dataclass_with_lists():
    """Sanity check: result shape includes the matched/missed/extra item lists,
    not just counts -- the UI uses them for the missed-items modal."""
    expected = ["a", "b"]
    actual = ["a", "z"]
    result = score_items(expected, actual)
    assert isinstance(result, ItemScorerResult)
    assert result.matched == ["a"]
    assert result.missed == ["b"]
    assert result.extra == ["z"]


@pytest.mark.unit
def test_acceptable_item_is_excluded_from_precision_denominator():
    result = score_items(
        ["whoami /groups"],
        ["whoami /groups", "tasklist /svc", "hostname"],
        [{"value": "tasklist /svc", "justification": "Equivalent supported reading."}],
    )
    assert result.matched_count == 1
    assert result.neutral == ["tasklist /svc"]
    assert result.neutral_count == 1
    assert result.extra == ["hostname"]
    assert result.precision == 0.5


@pytest.mark.unit
def test_acceptable_item_requires_justification_and_cannot_mask_expected_item():
    with pytest.raises(ValueError, match="justification"):
        score_items([], ["tasklist /svc"], [{"value": "tasklist /svc"}])
    with pytest.raises(ValueError, match="must not duplicate expected"):
        score_items(["tasklist /svc"], ["tasklist /svc"], [{"value": "tasklist /svc", "justification": "No."}])


# ---------------------------------------------------------------------------
# Agent-aware canonical identities (structured extractor output)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_registry_hive_abbreviation_canonicalizes_across_forms():
    """HKLM and HKEY_LOCAL_MACHINE are the same hive; casing/slashes ignored."""
    assert normalize_identity("registry_artifacts", "HKLM\\System\\CurrentControlSet\\Control\\Lsa") == (
        normalize_identity("registry_artifacts", "HKEY_LOCAL_MACHINE\\system\\currentcontrolset\\control\\lsa")
    )


@pytest.mark.unit
def test_registry_structured_item_scores_against_path_ground_truth():
    """The regression: the item's `value` is a stringified dict that must be
    ignored; identity is built from registry_hive + registry_key_path."""
    expected = ["HKLM\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\WDigest"]
    actual = [
        {
            "value": "{'registry_hive': 'HKEY_LOCAL_MACHINE', 'registry_key_path': 'SYSTEM\\\\...'}",
            "registry_hive": "HKEY_LOCAL_MACHINE",
            "registry_key_path": "SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\WDigest",
            "registry_value_name": None,
        }
    ]
    result = score_items(expected, actual, subagent_name="registry_artifacts")
    assert result.matched_count == 1
    assert result.missed_count == 0
    assert result.extra_count == 0


@pytest.mark.unit
def test_registry_stringified_value_dict_never_false_matches_without_subagent():
    """Without agent-aware identity the stringified dict cannot match a clean
    GT path -- documents the pre-fix failure mode as a guard."""
    expected = ["HKLM\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\WDigest"]
    actual = [{"value": "{'registry_hive': 'HKEY_LOCAL_MACHINE', 'registry_key_path': 'SYSTEM\\\\...'}"}]
    result = score_items(expected, actual, subagent_name="registry_artifacts")
    # The item has no structured fields, so it yields no candidate -> missed, not a false match.
    assert result.matched_count == 0
    assert result.missed_count == 1


@pytest.mark.unit
def test_registry_value_name_candidate_matches_gt_with_trailing_value():
    expected = ["HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\App"]
    actual = [
        {
            "registry_hive": "HKCU",
            "registry_key_path": "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "registry_value_name": "App",
        }
    ]
    result = score_items(expected, actual, subagent_name="registry_artifacts")
    assert result.matched_count == 1


@pytest.mark.unit
def test_windows_services_match_on_service_name():
    expected = ["SecurityHealthService", "WinDefend"]
    actual = [
        {"service_name": "securityhealthservice", "value": "{'service_name': 'SecurityHealthService', ...}"},
        {"service_name": "WinDefend", "binary_path": "C:\\x.exe"},
    ]
    result = score_items(expected, actual, subagent_name="windows_services")
    assert result.matched_count == 2
    assert result.extra_count == 0


@pytest.mark.unit
def test_scheduled_tasks_match_by_name_or_path_and_freetext_is_missed():
    expected = ["WinUpdate", "\\Microsoft\\Windows\\App\\Task2", "QBot scheduled task description"]
    actual = [
        {"task_name": "WinUpdate", "task_path": "\\Microsoft\\Windows\\Update"},
        {"task_name": "Task2", "task_path": "\\Microsoft\\Windows\\App\\Task2"},
    ]
    result = score_items(expected, actual, subagent_name="scheduled_tasks")
    assert result.matched_count == 2  # WinUpdate by name, Task2 by path
    assert result.missed_count == 1  # free-text description has no structured counterpart
    assert result.extra_count == 0


@pytest.mark.unit
def test_network_indicator_defang_hxxp_and_brackets():
    expected = ["https://evil.com/a"]
    actual = [{"value": "hxxps://evil[.]com/a", "indicator_type": "url"}]
    result = score_items(expected, actual, subagent_name="network_indicators")
    assert result.matched_count == 1


@pytest.mark.unit
def test_process_lineage_from_value_and_from_fields():
    expected = ["wsusservice.exe -> cmd.exe", "w3wp.exe -> powershell.exe"]
    actual = [
        {"value": "wsusservice.exe -> cmd.exe"},
        {"parent": "w3wp.exe", "child": "powershell.exe"},
    ]
    result = score_items(expected, actual, subagent_name="process_lineage")
    assert result.matched_count == 2


@pytest.mark.unit
def test_hunt_queries_match_on_query_field():
    expected = ["title: Keychain access\ndetection:\n  sel:\n    cmdline: security"]
    actual = [{"query": "title: Keychain access detection: sel: cmdline: security", "type": "sigma"}]
    result = score_items(expected, actual, subagent_name="hunt_queries")
    assert result.matched_count == 1


@pytest.mark.unit
def test_item_candidates_ignore_generic_value_for_structured_agents():
    stringified = {"value": "{'service_name': 'X'}"}
    assert item_candidates("windows_services", stringified) == []
    assert item_candidates("registry_artifacts", {"value": "{'registry_hive': 'HKLM'}"}) == []


@pytest.mark.unit
def test_score_items_populates_resolved_actual_list():
    expected = ["a", "b"]
    actual = ["a", "z"]
    result = score_items(expected, actual)
    assert sorted(result.actual) == ["a", "z"]
