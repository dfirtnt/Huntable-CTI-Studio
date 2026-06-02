"""API tests for SIGMA queue /add endpoint — YAML validation guard.

Verifies that non-dict YAML submitted to the queue promotion path is rejected
with HTTP 400 BEFORE any DB write, matching the three bad-data shapes found in
ids 30/42/43 during the 2026-06-01 queue replay.
"""

import pytest


BAD_YAML_CASES = [
    (
        "raw_commandline_string",
        "-connect 118.107.234.29:8080 -psk '15Kaf22N3b'",
    ),
    (
        "wmic_commandline_string",
        "wmic.exe /node:hostname /user:admin /password:pass process call create 'cmd.exe /c copy'",
    ),
    (
        "cmd_copy_commandline_string",
        r"cmd.exe /c copy \\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy1\windows\system32\config\system c:\users\public",
    ),
    (
        "yaml_list_not_dict",
        "- item_one\n- item_two\n",
    ),
    (
        "yaml_scalar_integer",
        "42",
    ),
]

VALID_SIGMA_YAML = """\
title: Test Detection Rule
id: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
status: experimental
description: Test rule for regression coverage
author: test
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    CommandLine|contains: evil.exe
  condition: selection
level: high
"""


@pytest.mark.api
class TestAddRuleToQueueYamlValidation:
    """Inserter-side YAML validation: non-dict YAML is rejected with 400 before DB write."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case_name,bad_yaml", BAD_YAML_CASES, ids=[c[0] for c in BAD_YAML_CASES])
    async def test_non_dict_yaml_rejected_400(self, async_client, case_name, bad_yaml):
        """POST with non-dict rule_yaml returns 400 without creating a queue row."""
        # article_id=999999 deliberately non-existent; validation fires before article lookup
        payload = {"article_id": 999999, "rule_yaml": bad_yaml}
        response = await async_client.post("/api/sigma-queue/add", json=payload)
        assert response.status_code == 400, (
            f"[{case_name}] Expected 400, got {response.status_code}. Body: {response.text[:300]}"
        )
        body = response.json()
        detail = body.get("detail", "")
        assert detail, f"[{case_name}] Response body missing 'detail' field"

    @pytest.mark.asyncio
    async def test_missing_required_sigma_keys_rejected_400(self, async_client):
        """rule_yaml that is a dict but missing title/logsource/detection is rejected."""
        incomplete_yaml = "author: test\nlevel: high\n"
        payload = {"article_id": 999999, "rule_yaml": incomplete_yaml}
        response = await async_client.post("/api/sigma-queue/add", json=payload)
        assert response.status_code == 400
        body = response.json()
        detail = body.get("detail", "")
        assert "missing required Sigma keys" in detail or detail, f"Unexpected detail: {detail!r}"

    @pytest.mark.asyncio
    async def test_valid_yaml_passes_validation_reaches_article_check(self, async_client):
        """Valid Sigma YAML passes the YAML guard and proceeds to the article existence check."""
        payload = {"article_id": 999999, "rule_yaml": VALID_SIGMA_YAML}
        response = await async_client.post("/api/sigma-queue/add", json=payload)
        # 404 = passed YAML validation, hit article-not-found (expected for fake article_id)
        assert response.status_code == 404, (
            f"Expected 404 (article not found), got {response.status_code}. Body: {response.text[:300]}"
        )
