"""Every Sigma rule committed to this repository must parse under pySigma.

Standalone fixture rules and the complete example rules embedded in the
``docs/contracts/*.md`` prompt contracts are what the generator and its tests
are shown as "correct Sigma". A rule using a modifier that does not exist
(``|any``) or a malformed condition parses as YAML and then fails the same
``SigmaCollection.from_yaml`` gate the runtime applies -- and, if it lives in a
contract, teaches the LLM the mistake. This is the parse-level check only
(no backend conversion; see the 2026-09-02 portability measurement for why).

No server or DB needed -- all assertions are against files on disk.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from sigma.collection import SigmaCollection

pytestmark = pytest.mark.unit

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

STANDALONE_GLOBS = (
    ("tests/fixtures/sigma", "*.y*ml"),
    ("tests/sigma_atom_similarity/fixtures", "*.y*ml"),
)
# Fixtures whose purpose is to be invalid.
STANDALONE_EXCLUDE = re.compile(r"invalid", re.IGNORECASE)

CONTRACT_DIR = REPO_ROOT / "docs" / "contracts"
_FENCE = re.compile(r"^```ya?ml[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_TOP_LEVEL_KEY = re.compile(r"^(title|logsource|detection):", re.MULTILINE)
# Output-shape templates (`title: <descriptive title ...>`) are not rules.
_TEMPLATE_TITLE = re.compile(r"^title:\s*<", re.MULTILINE)


def _standalone_rules() -> list[tuple[str, str]]:
    found = []
    for rel, pattern in STANDALONE_GLOBS:
        for path in sorted((REPO_ROOT / rel).glob(pattern)):
            if STANDALONE_EXCLUDE.search(path.name):
                continue
            found.append((str(path.relative_to(REPO_ROOT)), path.read_text(encoding="utf-8")))
    return found


def _contract_example_rules() -> list[tuple[str, str]]:
    """Fenced ```yaml blocks in docs/contracts that are complete rules.

    Fragments (a lone ``detection:`` snippet, a ``logsource:`` stanza) and
    placeholder templates (``title: <descriptive title ...>``) are skipped:
    only blocks carrying all of title/logsource/detection at column 0 with a
    literal title are held to the parse gate.
    """
    found = []
    for md in sorted(CONTRACT_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        for n, match in enumerate(_FENCE.finditer(text), start=1):
            block = match.group(1)
            keys = set(_TOP_LEVEL_KEY.findall(block))
            if keys >= {"title", "logsource", "detection"} and not _TEMPLATE_TITLE.search(block):
                found.append((f"{md.relative_to(REPO_ROOT)}#yaml-block-{n}", block))
    return found


_STANDALONE = _standalone_rules()
_CONTRACT = _contract_example_rules()


def _parse(rule_yaml: str) -> None:
    collection = SigmaCollection.from_yaml(rule_yaml)
    for rule in collection.rules:
        for condition in rule.detection.parsed_condition:
            _ = condition.parsed


def test_committed_sigma_corpus_is_not_empty():
    # Guards the gate against going vacuous if fixture paths move. The contract
    # corpus is deliberately not asserted non-empty: today docs/contracts holds
    # only output templates and fragments, and the scan exists so a literal
    # example added later is checked automatically.
    assert _STANDALONE, "no standalone Sigma fixtures found -- STANDALONE_GLOBS is stale"


@pytest.mark.parametrize(("label", "rule_yaml"), _STANDALONE, ids=[s[0] for s in _STANDALONE])
def test_standalone_fixture_rule_parses(label, rule_yaml):
    _parse(rule_yaml)


@pytest.mark.parametrize(("label", "rule_yaml"), _CONTRACT, ids=[c[0] for c in _CONTRACT])
def test_contract_example_rule_parses(label, rule_yaml):
    _parse(rule_yaml)
