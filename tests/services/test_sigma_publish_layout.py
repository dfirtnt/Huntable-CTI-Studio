"""Destination layout for published Sigma rules: logsource -> directory, family, slug, collisions."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from src.services.sigma_publish_layout import (
    BUNDLED_LAYOUT,
    RuleLayoutError,
    UnmappedLogsourceError,
    assign_filenames,
    collision_filename,
    index_repository_filenames,
    layout_path,
    load_rule_layout,
    logsource_dir,
    place_rule,
    resolve_family,
    slugify_title,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def layout():
    return load_rule_layout(None)


# Every (product, category, service) combination present in Huntable-SIGMA-Rules today.
@pytest.mark.parametrize(
    "logsource,expected",
    [
        ({"product": "windows", "category": "process_creation"}, "windows/process_creation"),
        ({"product": "windows", "category": "registry_set"}, "windows/registry/registry_set"),
        ({"product": "windows", "category": "registry_event"}, "windows/registry/registry_event"),
        ({"product": "windows", "category": "file_event"}, "windows/file/file_event"),
        ({"product": "windows", "category": "file_delete"}, "windows/file/file_delete"),
        ({"product": "windows", "category": "ps_script"}, "windows/powershell/powershell_script"),
        ({"product": "windows", "category": "network_connection"}, "windows/network_connection"),
        ({"product": "windows", "category": "process_access"}, "windows/process_access"),
        ({"product": "windows", "category": "image_load"}, "windows/image_load"),
        ({"product": "windows", "category": "pipe_created"}, "windows/pipe_created"),
        ({"product": "windows", "category": "dns_query"}, "windows/dns_query"),
        ({"product": "windows", "category": "driver_load"}, "windows/driver_load"),
        ({"product": "windows", "category": "create_remote_thread"}, "windows/create_remote_thread"),
        ({"product": "windows", "service": "security"}, "windows/builtin/security"),
        ({"product": "windows", "service": "system"}, "windows/builtin/system"),
        ({"product": "windows", "service": "sysmon"}, "windows/sysmon"),
    ],
)
def test_current_repo_logsources_map_to_sigmahq_directories(layout, logsource, expected):
    assert logsource_dir(logsource, layout) == expected


def test_lookup_is_case_insensitive_and_ignores_extra_logsource_keys(layout):
    logsource = {"product": "Windows", "category": "Process_Creation", "definition": "Sysmon EID 1"}
    assert logsource_dir(logsource, layout) == "windows/process_creation"


@pytest.mark.parametrize(
    "logsource",
    [
        {"product": "ibm_instana", "category": "audit"},
        {"product": "windows", "category": "not_a_category"},
        {"product": "windows"},
        {},
    ],
)
def test_unmapped_logsource_fails_loudly(layout, logsource):
    with pytest.raises(UnmappedLogsourceError, match="no directory"):
        logsource_dir(logsource, layout)


def test_missing_logsource_is_unmapped(layout):
    with pytest.raises(UnmappedLogsourceError):
        logsource_dir(None, layout)


@pytest.mark.parametrize(
    "title,expected",
    [
        (
            "AMSI Bypass via Suspicious amsi.dll Load from Non-Standard Path",
            "amsi_bypass_via_suspicious_amsi_dll_load_from_non_standard_path",
        ),
        (
            "Bloody Wolf: NetSupport RAT Persistence via Registry Run Key (T1547.001)",
            "bloody_wolf_netsupport_rat_persistence_via_registry_run_key",
        ),
        ("PowerShell New-Item creating directory in C:\\Temp", "powershell_new_item_creating_directory_in_c_temp"),
        (
            "Shell Process Spawned from main.exe (XiebroC2 Implant Parent-Child Pattern)",
            "shell_process_spawned_from_main_exe_xiebroc2_implant_parent_child_pattern",
        ),
        (
            "XWorm V5.6 Operator Configuration Registry Key Write",
            "xworm_v5_6_operator_configuration_registry_key_write",
        ),
        (
            "CVE-2026-20817 WER LPE PoC Token Inspection of WerFault.exe",
            "cve_2026_20817_wer_lpe_poc_token_inspection_of_werfault_exe",
        ),
        ("Caf\u00e9 \u2014 Suspicious Run", "cafe_suspicious_run"),
        ("", "untitled_rule"),
    ],
)
def test_slugify_title(title, expected):
    assert slugify_title(title) == expected


def test_long_title_is_cut_on_a_word_boundary_within_sigmahq_limit():
    title = "Instana API Enumeration via Stolen JWT from Non-Management-Platform Source (ARPA Observability Harvester)"
    slug = slugify_title(title)
    assert len(slug) <= 90
    assert slug == "instana_api_enumeration_via_stolen_jwt_from_non_management_platform_source_arpa"


@pytest.mark.parametrize(
    "title,description,expected",
    [
        ("HijackLoader WVault.exe Hollow-Host Launched", "", "hijackloader"),
        ("Chaos Loader Stage-4 Masquerade Scheduled Task", "", "chaos"),
        ("Chaos TorBrowserTor Ransomware Encrypted File Extension Created", "", "chaos"),
        ("Artifact Kit EAX-Redirect Process Hollowing", "", "cobalt-strike"),
        ("Ligolo-ng Reverse Tunnel Agent Execution", "", "ligolo-ng"),
        ("CVE-2026-20817 WER LPE PoC Token Inspection", "", "cve-2026-20817"),
        ("Registry Run Key Persistence", "Persistence used by the XWorm loader.", "xworm"),
        ("Registry Run Key Persistence", "Generic persistence.", None),
        ("XWorm dropper", "Mentions HijackLoader later", "xworm"),
    ],
)
def test_resolve_family_title_then_description(layout, title, description, expected):
    assert resolve_family(title, description, layout) == expected


def _rule(**overrides):
    rule = {
        "title": "Suspicious Child Of Word",
        "id": "4b5e9c2a-0000-4000-8000-000000000001",
        "description": "Detects a test.",
        "tags": ["attack.execution", "attack.t1204.002"],
        "logsource": {"product": "windows", "category": "process_creation"},
    }
    rule.update(overrides)
    return rule


def test_generic_rule_placement(layout):
    placement = place_rule(_rule(), layout)
    assert placement.path() == PurePosixPath("rules/windows/process_creation/suspicious_child_of_word.yml")
    assert not placement.emerging_threat and not placement.warnings


def test_emerging_threat_rule_placement(layout):
    rule = _rule(title="XWorm Registry Run Key Persistence", tags=["attack.persistence", "detection.emerging-threats"])
    placement = place_rule(rule, layout)
    assert placement.path() == PurePosixPath("rules-emerging-threats/xworm/xworm_registry_run_key_persistence.yml")


def test_unresolved_emerging_threat_goes_to_unsorted_with_warning(layout):
    rule = _rule(tags=["attack.execution", "detection.emerging-threats"])
    placement = place_rule(rule, layout)
    assert placement.directory == PurePosixPath("rules-emerging-threats/_unsorted")
    assert placement.unsorted
    assert "_unsorted" in placement.warnings[0]


def test_emerging_threat_still_requires_a_mapped_logsource(layout):
    rule = _rule(tags=["detection.emerging-threats"], logsource={"product": "nowhere"})
    with pytest.raises(UnmappedLogsourceError):
        place_rule(rule, layout)


def test_rule_without_title_cannot_be_placed(layout):
    with pytest.raises(RuleLayoutError, match="title"):
        place_rule(_rule(title=""), layout)


# --- collisions ---


def test_collision_suffix_is_deterministic_and_order_independent(layout):
    first = place_rule(_rule(id="aaaaaaaa-0000-4000-8000-000000000001"), layout)
    second = place_rule(_rule(id="bbbbbbbb-0000-4000-8000-000000000002", title="Suspicious Child of Word!"), layout)
    a = assign_filenames(
        {"aaaaaaaa-0000-4000-8000-000000000001": first, "bbbbbbbb-0000-4000-8000-000000000002": second}, {}
    )
    b = assign_filenames(
        {"bbbbbbbb-0000-4000-8000-000000000002": second, "aaaaaaaa-0000-4000-8000-000000000001": first}, {}
    )
    assert a == b
    assert a["aaaaaaaa-0000-4000-8000-000000000001"].name == "suspicious_child_of_word_aaaaaaaa.yml"
    assert a["bbbbbbbb-0000-4000-8000-000000000002"].name == "suspicious_child_of_word_bbbbbbbb.yml"


def test_collision_with_existing_repo_file_of_another_rule(layout):
    placement = place_rule(_rule(id="cccccccc-0000-4000-8000-000000000003"), layout)
    existing = {
        "suspicious_child_of_word.yml": (PurePosixPath("rules/windows/x/suspicious_child_of_word.yml"), "other")
    }
    paths = assign_filenames({"cccccccc-0000-4000-8000-000000000003": placement}, existing)
    assert paths["cccccccc-0000-4000-8000-000000000003"].name == "suspicious_child_of_word_cccccccc.yml"


def test_republishing_the_same_rule_id_keeps_its_filename(layout):
    rule_id = "dddddddd-0000-4000-8000-000000000004"
    placement = place_rule(_rule(id=rule_id), layout)
    existing = {"suspicious_child_of_word.yml": (PurePosixPath("rules/windows/process_creation/x.yml"), rule_id)}
    assert assign_filenames({rule_id: placement}, existing)[rule_id].name == "suspicious_child_of_word.yml"


def test_collision_filename_stays_within_limit():
    name = collision_filename("a_" * 45, "eeeeeeee-0000")
    assert name.endswith("_eeeeeeee.yml") and len(name) - len(".yml") <= 90


def test_repository_index_covers_both_roots(tmp_path, layout):
    for rel, rule_id in (("rules/windows/a/one.yml", "1"), ("rules-emerging-threats/x/two.yml", "2")):
        path = tmp_path / rel
        path.parent.mkdir(parents=True)
        path.write_text(f"title: t\nid: '{rule_id}'\n", encoding="utf-8")
    index = index_repository_filenames(tmp_path, layout)
    assert index["one.yml"] == (PurePosixPath("rules/windows/a/one.yml"), "1")
    assert index["two.yml"] == (PurePosixPath("rules-emerging-threats/x/two.yml"), "2")


# --- table loading ---


def test_destination_layout_wins_over_bundled(tmp_path):
    assert layout_path(tmp_path) == BUNDLED_LAYOUT
    (tmp_path / ".huntable").mkdir()
    custom = tmp_path / ".huntable" / "rule-layout.yml"
    custom.write_text("version: 1\nlogsource_dirs:\n  - {category: audit, dir: misc/audit}\n", encoding="utf-8")
    layout = load_rule_layout(tmp_path)
    assert layout.source == custom
    assert logsource_dir({"category": "audit"}, layout) == "misc/audit"


def test_conflicting_mapping_in_table_is_rejected(tmp_path):
    (tmp_path / ".huntable").mkdir()
    (tmp_path / ".huntable" / "rule-layout.yml").write_text(
        "version: 1\nlogsource_dirs:\n  - {category: a, dir: x}\n  - {category: a, dir: y}\n", encoding="utf-8"
    )
    with pytest.raises(RuleLayoutError, match="mapped twice"):
        load_rule_layout(tmp_path)


def test_bundled_layout_is_ascii():
    BUNDLED_LAYOUT.read_text(encoding="ascii")
    assert Path(BUNDLED_LAYOUT).name == "sigma_rule_layout.yml"
