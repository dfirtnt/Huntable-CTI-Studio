"""Extractor contract cross-listing lint.

docs/contracts/extractor-standard.md mandates that every extractor contract's
ARCHITECTURE CONTEXT block list ALL sibling extractors and that boundary rules
exist in both directions ("When adding a new extractor: Update ALL existing
extractor prompts to list the new sibling"). This suite pins that invariant so
the next extractor addition cannot ship one-directional again (as happened when
NetworkIndicatorExtract landed in v7.2.0), and pins the companion drop-in
prompt + mkdocs nav registration every extractor contract ships with.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = ROOT / "docs" / "contracts"
PROMPTS_DIR = ROOT / "src" / "prompts"
MKDOCS_YML = ROOT / "mkdocs.yml"

# Extractor name -> contract markdown stem. Seed prompt files in src/prompts/
# use the extractor name itself as the filename.
EXTRACTORS = {
    "CmdlineExtract": "cmdline-extract",
    "ProcTreeExtract": "proctree-extract",
    "RegistryExtract": "registry-extract",
    "ServicesExtract": "services-extract",
    "ScheduledTasksExtract": "scheduled-tasks-extract",
    "HuntQueriesExtract": "huntquery-extract",
    "NetworkIndicatorExtract": "network-indicator-extract",
}


def _architecture_context(text: str, path: Path) -> str:
    marker = "## ARCHITECTURE CONTEXT"
    assert marker in text, f"{path.name} is missing an ARCHITECTURE CONTEXT section"
    start = text.index(marker) + len(marker)
    end = text.find("\n## ", start)
    return text[start:end] if end != -1 else text[start:]


@pytest.mark.parametrize("extractor", sorted(EXTRACTORS))
def test_contract_architecture_context_lists_all_siblings(extractor: str) -> None:
    contract_path = CONTRACTS_DIR / f"{EXTRACTORS[extractor]}.md"
    section = _architecture_context(contract_path.read_text(encoding="utf-8"), contract_path)
    missing = [sibling for sibling in EXTRACTORS if sibling != extractor and sibling not in section]
    assert not missing, (
        f"{contract_path.name} ARCHITECTURE CONTEXT does not list sibling(s) "
        f"{missing}; extractor-standard.md requires ALL siblings to be listed "
        "with boundary rules in both directions"
    )


@pytest.mark.parametrize("extractor", sorted(EXTRACTORS))
def test_seed_prompt_lists_all_siblings(extractor: str) -> None:
    prompt_path = PROMPTS_DIR / extractor
    text = prompt_path.read_text(encoding="utf-8")
    missing = [sibling for sibling in EXTRACTORS if sibling != extractor and sibling not in text]
    assert not missing, (
        f"src/prompts/{extractor} does not mention sibling(s) {missing}; "
        "seed prompts must declare all siblings per extractor-standard.md"
    )


@pytest.mark.parametrize("extractor", sorted(EXTRACTORS))
def test_contract_has_dropin_companion(extractor: str) -> None:
    dropin_path = CONTRACTS_DIR / f"{EXTRACTORS[extractor]}-dropin.md"
    assert dropin_path.is_file(), (
        f"{dropin_path.name} is missing; every extractor contract ships a companion drop-in prompt"
    )


@pytest.mark.parametrize("extractor", sorted(EXTRACTORS))
def test_contract_and_dropin_registered_in_mkdocs_nav(extractor: str) -> None:
    nav_text = MKDOCS_YML.read_text(encoding="utf-8")
    stem = EXTRACTORS[extractor]
    assert f"contracts/{stem}.md" in nav_text, f"contracts/{stem}.md is not registered in mkdocs.yml nav"
    assert f"contracts/{stem}-dropin.md" in nav_text, f"contracts/{stem}-dropin.md is not registered in mkdocs.yml nav"
