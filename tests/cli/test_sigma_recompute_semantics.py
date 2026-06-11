from types import SimpleNamespace
from unittest.mock import Mock, patch

from click.testing import CliRunner

from src.cli.sigma_commands import _clean_json_null_semantic_atoms, sigma_group


def test_recompute_semantics_clears_stale_fields_for_unsupported_rules():
    stale_rule = SimpleNamespace(
        rule_id="stale-rule",
        logsource={"product": "unsupported"},
        detection={"selection": {"Image": "bad.exe"}, "condition": "selection"},
        canonical_class="windows.process_creation",
        positive_atoms=[{"kind": "field", "field": "Image", "op": "endswith", "value": "bad.exe"}],
        negative_atoms=[],
        surface_score=0.5,
    )
    supported_rule = SimpleNamespace(
        rule_id="supported-rule",
        logsource={"product": "windows", "category": "process_creation"},
        detection={"selection": {"Image": "cmd.exe"}, "condition": "selection"},
        canonical_class=None,
        positive_atoms=None,
        negative_atoms=None,
        surface_score=None,
    )
    semantic_fields = {
        "canonical_class": "windows.process_creation",
        "positive_atoms": [{"identity": "field:process.executable:eq:cmd.exe"}],
        "negative_atoms": [],
        "surface_score": 1.0,
    }

    session = Mock()
    session.query.return_value.all.return_value = [stale_rule, supported_rule]
    session.get_bind.return_value.dialect.name = "sqlite"

    with (
        patch("src.cli.sigma_commands.DatabaseManager") as db_manager,
        patch("src.services.sigma_atom_precompute.is_sigma_similarity_available", return_value=True),
        patch(
            "src.services.sigma_atom_precompute.precompute_atom_fields",
            side_effect=[None, semantic_fields],
        ),
    ):
        db_manager.return_value.get_session.return_value = session
        result = CliRunner().invoke(sigma_group, ["recompute-semantics"])

    assert result.exit_code == 0, result.output
    assert stale_rule.canonical_class is None
    assert stale_rule.positive_atoms is None
    assert stale_rule.negative_atoms is None
    assert stale_rule.surface_score is None
    assert supported_rule.canonical_class == "windows.process_creation"
    assert supported_rule.positive_atoms == [{"identity": "field:process.executable:eq:cmd.exe"}]
    assert supported_rule.negative_atoms == []
    assert supported_rule.surface_score == 1.0
    assert "Total processed: 1" in result.output
    assert "Unsupported (skipped): 1" in result.output
    assert "Cleared stale semantic fields: 1" in result.output
    session.commit.assert_called_once()
    session.close.assert_called_once()


def test_clean_json_null_semantic_atoms_normalizes_postgres_json_nulls():
    session = Mock()
    session.get_bind.return_value.dialect.name = "postgresql"
    session.execute.return_value.rowcount = 179

    cleaned = _clean_json_null_semantic_atoms(session)

    assert cleaned == 179
    sql = str(session.execute.call_args.args[0])
    assert "UPDATE sigma_rules" in sql
    assert "positive_atoms = CAST('null' AS jsonb)" in sql
    assert "negative_atoms = CAST('null' AS jsonb)" in sql


def test_clean_json_null_semantic_atoms_skips_non_postgres_backends():
    session = Mock()
    session.get_bind.return_value.dialect.name = "sqlite"

    cleaned = _clean_json_null_semantic_atoms(session)

    assert cleaned == 0
    session.execute.assert_not_called()
