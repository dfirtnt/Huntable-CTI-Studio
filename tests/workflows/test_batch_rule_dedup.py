"""Intra-batch Sigma dedup compares matched values, not condition syntax.

``_detection_leaf_values`` used to collect the ``condition`` expression as if it were a
matched value, because it denylisted four literal strings instead of skipping the key.
Real conditions (``selection_image and selection_command``, ``all of selection_*``)
never matched that denylist, so every pair's union was inflated and duplicates slipped
through. Measured on execution 25 (article 989): queue #19 and #21 are the same
wscript.exe-from-Windows-Temp detection, yet overlapped only 0.50.
"""

import pytest
import yaml

from src.workflows.agentic_workflow import (
    _batch_rules_are_duplicates,
    _deduplicate_batch_rules,
    _detection_leaf_values,
)

pytestmark = pytest.mark.unit

PROCESS_CREATION = {"category": "process_creation", "product": "windows"}

# Detection blocks of queue #19 and #21, verbatim from the live queue (execution 25).
QUEUE_19 = yaml.safe_load(r"""
title: Script Host Executing VBScript From Windows Temp
logsource: {category: process_creation, product: windows}
detection:
  selection_image:
    Image|endswith: \wscript.exe
    OriginalFileName: wscript.exe
  selection_command:
    CommandLine|contains|all:
    - \Windows\Temp\
    - .vbs
  condition: selection_image and selection_command
""")
QUEUE_21 = yaml.safe_load(r"""
title: Script Host Executing VBScript From Windows Temp (restated)
logsource: {category: process_creation, product: windows}
detection:
  selection_image:
    Image|endswith: \wscript.exe
  selection_script:
    CommandLine|contains|all:
    - \Windows\Temp\
    - .vbs
  condition: all of selection_*
""")


def _rule(title, detection, logsource=PROCESS_CREATION):
    return {"title": title, "logsource": logsource, "detection": detection}


def test_rules_differing_only_in_condition_syntax_have_identical_leaf_sets():
    a = {
        "sel_img": {"Image|endswith": "\\reg.exe"},
        "sel_cmd": {"CommandLine|contains": "save"},
        "condition": "sel_img and sel_cmd",
    }
    b = {
        "sel_img": {"Image|endswith": "\\reg.exe"},
        "sel_cmd": {"CommandLine|contains": "save"},
        "condition": "all of sel_*",
    }

    assert _detection_leaf_values(a) == _detection_leaf_values(b) == frozenset({"\\reg.exe", "save"})
    duplicate, overlap = _batch_rules_are_duplicates(_detection_leaf_values(a), _detection_leaf_values(b))
    assert duplicate is True
    assert overlap == 1.0


def test_list_form_condition_and_timeframe_are_not_values():
    detection = {
        "selection": {"EventID": "4625"},
        "timeframe": "5m",
        "condition": ["selection | count() > 10", "selection"],
    }

    assert _detection_leaf_values(detection) == frozenset({"4625"})


def test_a_selection_field_that_happens_to_be_named_condition_is_still_a_value():
    detection = {"selection": {"condition": "degraded"}, "condition": "selection"}

    assert _detection_leaf_values(detection) == frozenset({"degraded"})


def test_queue_19_and_21_are_one_detection_and_the_more_specific_rule_is_kept():
    values_19 = _detection_leaf_values(QUEUE_19["detection"])
    values_21 = _detection_leaf_values(QUEUE_21["detection"])
    assert values_19 == frozenset({"\\wscript.exe", "wscript.exe", "\\windows\\temp\\", ".vbs"})
    assert values_21 < values_19, "#21 is a less specific restatement of #19"

    kept = _deduplicate_batch_rules([QUEUE_21, QUEUE_19])

    assert kept == [QUEUE_19]


def test_identical_values_are_duplicates_regardless_of_order():
    first = _rule(
        "SAM hive save",
        {"sel": {"Image|endswith": "\\reg.exe", "CommandLine|contains|all": ["save", "hklm\\sam"]}, "condition": "sel"},
    )
    second = _rule(
        "SAM dump",
        {
            "a": {"Image|endswith": "\\reg.exe"},
            "b": {"CommandLine|contains|all": ["hklm\\sam", "save"]},
            "condition": "a and b",
        },
    )

    assert _deduplicate_batch_rules([first, second]) == [first]


def test_distinct_detections_on_the_same_tool_are_both_kept():
    """Queue #9 / #10 (execution 2): net.exe group enumeration vs enabling an account."""
    enumerate_group = _rule(
        "Domain Admins enumeration",
        {
            "sel": {
                "Image|endswith": "\\net.exe",
                "OriginalFileName": "net.exe",
                "CommandLine|contains|all": ["group", "domain admins", "/dom"],
            },
            "condition": "sel",
        },
    )
    enable_account = _rule(
        "Enable domain administrator",
        {
            "sel": {
                "Image|endswith": "\\net.exe",
                "OriginalFileName": "net.exe",
                "CommandLine|contains|all": ["user", "administrator", "/active:yes", "/dom"],
            },
            "condition": "sel",
        },
    )

    assert _deduplicate_batch_rules([enumerate_group, enable_account]) == [enumerate_group, enable_account]


def test_containment_needs_at_least_three_values_in_the_smaller_rule():
    """A two-value rule is "contained" in far too many unrelated rules to call it a duplicate."""
    small = frozenset({"\\cmd.exe", "/c"})
    large = frozenset({"\\cmd.exe", "/c", "whoami"})

    duplicate, overlap = _batch_rules_are_duplicates(small, large)

    assert overlap == pytest.approx(2 / 3)
    assert duplicate is False


def test_containment_needs_jaccard_of_at_least_point_six():
    small = frozenset({"a", "b", "c"})
    large = frozenset({"a", "b", "c", "d", "e", "f"})

    assert _batch_rules_are_duplicates(small, large) == (False, 0.5)


def test_rules_on_different_logsources_are_never_compared():
    detection = {"sel": {"Image|endswith": "\\reg.exe", "CommandLine|contains": "save"}, "condition": "sel"}
    windows = _rule("windows", detection)
    linux = _rule("linux", detection, logsource={"category": "process_creation", "product": "linux"})

    assert _deduplicate_batch_rules([windows, linux]) == [windows, linux]
