"""AGENTS.md UI Stability Contracts must name IDs and functions that still exist.

AGENTS.md lists contract-grade DOM IDs and JS functions that require a spec before
renaming or removing. Nothing else references that list, so a rename used to pass CI
while the contract silently pointed at nothing. The list is parsed from AGENTS.md
itself, so the test and the doc cannot drift apart.

Templated entries (`#toggle-{agentname}-enabled`, `#tab-content-*`) match their
static fragments, which covers both literal HTML ids and JS template-literal ids.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
AGENTS_MD = ROOT / "AGENTS.md"
SOURCE_GLOBS = (("src/web/templates", "*.html"), ("src/web/static/js", "*.js"))


def _section(heading: str) -> str:
    text = AGENTS_MD.read_text(encoding="utf-8")
    match = re.search(rf"^### {re.escape(heading)}\n(.*?)(?=^#{{2,3}} )", text, re.M | re.S)
    assert match, f"AGENTS.md is missing the '### {heading}' section"
    return match.group(1)


def _contract_ids() -> list[str]:
    return re.findall(r"#([A-Za-z][\w{}*-]*)", _section("Contract-grade DOM IDs"))


def _contract_functions() -> list[str]:
    names = []
    for token in re.findall(r"`([A-Za-z]\w*(?:\[\w+\])?)\(", _section("Contract-grade JS functions")):
        base, _, optional = token.partition("[")
        names.append(base)
        if optional:
            names.append(base + optional.rstrip("]"))
    return names


def _source_text() -> str:
    parts = []
    for directory, pattern in SOURCE_GLOBS:
        parts.extend(p.read_text(encoding="utf-8") for p in sorted((ROOT / directory).rglob(pattern)))
    return "\n".join(parts)


SOURCE = _source_text()


def test_contract_lists_parse_non_empty() -> None:
    # Guards against a vacuous pass if the headings or token format change.
    assert len(_contract_ids()) >= 15
    assert len(_contract_functions()) >= 15


@pytest.mark.parametrize("contract_id", _contract_ids())
def test_contract_dom_id_exists(contract_id: str) -> None:
    pattern = re.escape(contract_id)
    pattern = re.sub(r"\\\{\w+\\\}", r"[\\w${}.]+", pattern).replace(r"\*", r"[\w-]+")
    assert re.search(rf"(?:id=[\"']|[\"'`#]){pattern}(?![\w-])", SOURCE), (
        f"AGENTS.md lists #{contract_id} as contract-grade, but no template or JS defines it. "
        "Renaming it requires a spec; update AGENTS.md if the rename is intentional."
    )


@pytest.mark.parametrize("function_name", _contract_functions())
def test_contract_js_function_is_defined(function_name: str) -> None:
    name = re.escape(function_name)
    definition = rf"\bfunction\s+{name}\s*\(|\b{name}\s*=\s*(?:async\s+)?(?:function\b|\()"
    assert re.search(definition, SOURCE), (
        f"AGENTS.md lists {function_name}() as contract-grade, but no template or JS defines it. "
        "Renaming it requires a spec; update AGENTS.md if the rename is intentional."
    )
