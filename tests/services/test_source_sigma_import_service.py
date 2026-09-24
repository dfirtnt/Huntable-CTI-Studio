from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.database.models import SigmaRuleQueueTable
from src.services.source_sigma_import_service import (
    LOCAL_REVIEW_ONLY,
    SOURCE_ORIGIN,
    detect_license,
    evaluate_source_rule_delivery,
    import_source_sigma_rules,
    load_destination_license_allowlist,
    scan_sigma_rules,
    scan_sigma_rules_with_diagnostics,
)

pytestmark = pytest.mark.unit


def _rule(number: int, *, logsource: str = "category: process_creation\n  product: windows") -> str:
    return f"""title: Source Rule {number}
id: 00000000-0000-0000-0000-{number:012d}
author: Publisher
logsource:
  {logsource}
detection:
  selection:
    Image|endswith: '\\tool{number}.exe'
  condition: selection
level: high
"""


def _article(rule_count: int) -> str:
    sections = ["Publisher detection notes\n"]
    for index in range(rule_count):
        sections.extend([_rule(index + 1), f"\nNarrative after rule {index + 1}.\n\n"])
    sections.append("License: CC BY 4.0\n")
    return "".join(sections)


@pytest.mark.parametrize("article_id,expected", [(980, 5), (986, 4), (989, 11), (995, 9), (997, 10)])
def test_reference_article_fixture_counts(article_id, expected):
    content = f"Reference fixture {article_id}\n" + _article(expected)
    assert len(scan_sigma_rules(content)) == expected


def test_scanner_preserves_exact_article_substring():
    content = "Intro\r\n" + _rule(1).replace("\n", "\r\n") + "\r\nTrailing prose\r\n"
    [candidate] = scan_sigma_rules(content)
    assert candidate.yaml_text == content[candidate.start : candidate.end]
    assert candidate.yaml_text.startswith("title: Source Rule 1\r\n")
    assert candidate.parsed["id"].endswith("000000000001")


@pytest.mark.parametrize(
    "bad_content",
    [
        "title: fragment only\nlogsource:\n  product: windows\n",
        "title: query\nquery: index=main | stats count\n",
        "- title: sequence rule\n  logsource: {}\n  detection: {}\n",
        "title: invalid\nlogsource: [\ndetection: nope\n",
    ],
)
def test_scanner_rejects_fragments_non_mappings_and_non_sigma_queries(bad_content):
    assert scan_sigma_rules(bad_content) == []


def test_flattened_eval_fixture_records_structural_rejection_reason():
    flattened = """title: Flattened Eval Rule
id: 00000000-0000-0000-0000-000000000099
logsource:
category: process_creation
product: windows
detection:
selection:
Image|endswith: \\tool.exe
condition: selection
"""
    result = scan_sigma_rules_with_diagnostics(flattened)
    assert result.candidates == ()
    assert len(result.rejections) == 1
    assert result.rejections[0].reason == "invalid_or_missing_logsource"
    assert flattened[result.rejections[0].start : result.rejections[0].end] == flattened


def test_license_detection_prefers_noncommercial_and_records_exact_span():
    content = "License: CC BY-NC 4.0\n\n" + _rule(1) + "\nAlso says CC BY 4.0 later."
    [candidate] = scan_sigma_rules(content)
    evidence = detect_license(content, candidate)
    assert evidence.license_id == "CC-BY-NC-4.0"
    assert content[evidence.start : evidence.end] == evidence.evidence


def test_destination_allowlist_is_machine_readable_and_fail_closed(tmp_path: Path):
    assert load_destination_license_allowlist(tmp_path) == set()
    policy = tmp_path / ".huntable" / "source-rule-license-policy.yml"
    policy.parent.mkdir()
    policy.write_text("version: 1\nallowed_licenses:\n  - id: CC-BY-4.0\n", encoding="utf-8")
    assert load_destination_license_allowlist(tmp_path) == {"CC-BY-4.0"}


def test_delivery_policy_blocks_missing_and_noncommercial_licenses(tmp_path: Path):
    for license_id in (None, "CC-BY-NC-4.0"):
        rule = SimpleNamespace(
            rule_origin=SOURCE_ORIGIN,
            declared_license=license_id,
            source_permission_granted_by=None,
            source_permission_basis=None,
            source_permission_granted_at=None,
        )
        assert evaluate_source_rule_delivery(rule, tmp_path).eligible is False


def test_delivery_policy_allows_cc_by_4_only_when_destination_allows_it(tmp_path: Path):
    rule = SimpleNamespace(
        rule_origin=SOURCE_ORIGIN,
        declared_license="CC-BY-4.0",
        source_permission_granted_by=None,
        source_permission_basis=None,
        source_permission_granted_at=None,
    )
    assert evaluate_source_rule_delivery(rule, tmp_path).eligible is False
    policy = tmp_path / ".huntable" / "source-rule-license-policy.yml"
    policy.parent.mkdir()
    policy.write_text("allowed_licenses:\n  - id: CC-BY-4.0\n", encoding="utf-8")
    assert evaluate_source_rule_delivery(rule, tmp_path).eligible is True


def test_recorded_source_permission_overrides_license_block(tmp_path: Path):
    rule = SimpleNamespace(
        rule_origin=SOURCE_ORIGIN,
        declared_license="CC-BY-NC-4.0",
        source_permission_granted_by="reviewer",
        source_permission_basis="Written publisher permission, ticket ABC-123",
        source_permission_granted_at=object(),
    )
    decision = evaluate_source_rule_delivery(rule, tmp_path)
    assert decision.eligible is True
    assert decision.basis == "source_permission"


def test_import_uses_articles_content_not_extractor_output_and_preserves_yaml(tmp_path: Path):
    content = "Intro\n" + _rule(7) + "\nProse\n"
    article = SimpleNamespace(
        id=77,
        canonical_url="https://publisher.example/article",
        content=content,
        authors=["Publisher"],
        hunt_queries=[{"query": _rule(999) + "inflated extractor text"}],
    )
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    session.begin_nested.return_value = nullcontext()
    added: list[SigmaRuleQueueTable] = []
    session.add.side_effect = added.append
    session.flush.side_effect = lambda: setattr(added[-1], "id", 123)
    similarity = {
        "matches": [],
        "canonical_class": None,
        "behavioral_matches_found": 0,
        "total_candidates_evaluated": 0,
    }
    with (
        patch(
            "src.services.source_sigma_import_service.SigmaMatchingService.assess_rule_novelty",
            return_value=similarity,
        ),
        patch("src.workflows.agentic_workflow._deduplicate_batch_rules", side_effect=AssertionError("must not run")),
    ):
        result = import_source_sigma_rules(session, article, tmp_path)

    assert result.imported == 1
    assert len(added) == 1
    row = added[0]
    assert row.rule_origin == SOURCE_ORIGIN
    assert row.rule_yaml == content[row.source_extraction_start : row.source_extraction_end]
    assert "999" not in row.rule_yaml
    assert row.status == LOCAL_REVIEW_ONLY
    assert row.rule_metadata["logsource_unresolved"] is True
    session.commit.assert_called_once()


def test_generated_rows_keep_generated_default():
    assert SigmaRuleQueueTable().rule_origin is None  # SQLAlchemy default applies on INSERT
    assert SigmaRuleQueueTable.__table__.c.rule_origin.default.arg == "generated"
    assert SigmaRuleQueueTable.__table__.c.rule_origin.server_default.arg == "generated"
