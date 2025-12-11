import pytest

from src.extractors.encoder_classifier import classify_candidates
from src.extractors.hybrid_cmdline_extractor import (
    extract_commands,
    literal_filter,
    update_cmdline_state,
)
from src.extractors.regex_windows import extract_candidate_lines
from workflows.nodes.hybrid_extractor_node import HybridExtractorNode


@pytest.fixture(autouse=True)
def force_heuristic(monkeypatch):
    monkeypatch.setenv("CMDLINE_ENCODER_MODE", "heuristic")
    monkeypatch.setenv("CMDLINE_QA_ENABLED", "false")


def test_event_logs_rejected():
    candidates = ["Service Control Manager/7036; Velociraptor running"]
    assert classify_candidates(candidates) == []


def test_argv_arrays_rejected():
    candidates = ['Velociraptor/1000; ARGV: ["C:\\\\Program Files\\\\Velociraptor\\\\Velociraptor.exe", "-v"]']
    assert classify_candidates(candidates) == []


def test_msi_lines_rejected():
    candidates = ['MsiInstaller/11707; Product installed successfully "C:\\\\Program Files\\\\App\\\\app.exe" /S']
    assert classify_candidates(candidates) == []


def test_exe_with_no_args_rejected():
    candidates = ["calc.exe"]
    assert classify_candidates(candidates) == []


def test_multiline_commands_accepted():
    article_text = r"""
    Noise text ahead
    "C:\Program Files\App\app.exe" -flag1 -flag2
    trailing info
    """
    result = extract_commands(article_text)
    expected = '"C:\\Program Files\\App\\app.exe" -flag1 -flag2'
    assert expected in result["cmdline_items"]


def test_powershell_encoded_commands_accepted():
    article_text = "powershell.exe -ExecutionPolicy Bypass -enc AAA=="
    result = extract_commands(article_text)
    assert "powershell.exe -ExecutionPolicy Bypass -enc AAA==" in result["cmdline_items"]


def test_dedupe_preserved():
    cmd = r'C:\Windows\System32\net.exe group "domain users" /do'
    article_text = f"{cmd}\n{cmd}"
    result = extract_commands(article_text)
    assert result["cmdline_items"].count(cmd) == 1
    assert result["count"] == 1


def test_exact_literal_matching():
    cmd = 'PowerShell.EXE -NoP -enc QURERVQ='
    article_text = f"Observed: {cmd}"
    result = extract_commands(article_text)
    assert cmd in result["cmdline_items"]


def test_integration_article_output_count():
    article_text = """
    powershell.exe -ExecutionPolicy Bypass -enc AAA
    C:\\\\Windows\\\\System32\\\\net.exe group "domain users" /do
    """
    candidates = extract_candidate_lines(article_text)
    assert len(candidates) >= 2

    result = extract_commands(article_text)
    assert result["count"] == len(result["cmdline_items"])
    assert result["count"] >= 2


def test_hybrid_node_calls_pipeline(monkeypatch):
    calls = []
    monkeypatch.setenv("CMDLINE_QA_ENABLED", "true")

    monkeypatch.setattr(
        "workflows.nodes.hybrid_extractor_node.extract_candidate_lines",
        lambda text: calls.append("regex") or ["cmd"],
    )
    monkeypatch.setattr(
        "workflows.nodes.hybrid_extractor_node.classify_candidates",
        lambda cands: calls.append("classify") or cands,
    )
    monkeypatch.setattr(
        "workflows.nodes.hybrid_extractor_node.literal_filter",
        lambda cmds, article: calls.append("literal") or cmds,
    )
    monkeypatch.setattr(
        "workflows.nodes.hybrid_extractor_node.qa_validate",
        lambda cmds, article: calls.append("qa") or cmds,
    )

    result = HybridExtractorNode().run("cmd appears here")
    assert result["cmdline_items"]
    assert calls == ["regex", "classify", "literal", "qa"]


def test_literal_filter_applied_before_qa(monkeypatch):
    qa_seen = {}
    monkeypatch.setenv("CMDLINE_QA_ENABLED", "true")

    monkeypatch.setattr(
        "workflows.nodes.hybrid_extractor_node.extract_candidate_lines",
        lambda text: ["keep", "drop"],
    )
    monkeypatch.setattr(
        "workflows.nodes.hybrid_extractor_node.classify_candidates",
        lambda cands: cands,
    )
    monkeypatch.setattr(
        "workflows.nodes.hybrid_extractor_node.literal_filter",
        lambda cmds, article: ["keep"],
    )

    def fake_qa(cmds, article):
        qa_seen["input"] = list(cmds)
        return cmds

    monkeypatch.setattr("workflows.nodes.hybrid_extractor_node.qa_validate", fake_qa)

    result = HybridExtractorNode().run("keep only")
    assert qa_seen["input"] == ["keep"]
    assert result["cmdline_items"] == ["keep"]


def test_update_cmdline_state_sets_keys():
    state = {}
    update_cmdline_state(state, ["one", "two"])
    assert state["cmdline_items"] == ["one", "two"]
    assert state["count"] == 2


def test_literal_filter_matches_article_text():
    cmds = ["abc", "xyz"]
    article = "noise abc noise"
    assert literal_filter(cmds, article) == ["abc"]
