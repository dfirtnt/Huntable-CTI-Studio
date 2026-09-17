"""Generated Sigma rules are never attributed to the article's publisher.

SigmaAgent prompts used to carry an "AUTHOR PRESERVATION" carve-out: when the article
itself published a complete Sigma rule with an ``author`` field, the model was told to
copy that author. It triggered on what the article contained, not on whether the
generated rule reproduced anything, so newly written generic rules from detection
publishers came back as ``author: The Hunters Ledger`` (queue #14-#16 and #21,
2026-09-04), inconsistently within one execution. Publisher-authored rules are brought
in verbatim by the separate source_provided import path, which carries its own
attribution.

Prompt text lives in several sinks that must move together: the seed prompt files and
every quickstart preset (the live DB config is migrated separately). The generation
service also stamps the author in code, so an older config version cannot reintroduce it.
"""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SEED_PROMPTS = [ROOT / "src/prompts/sigma_generation.txt", ROOT / "src/prompts/sigma_generate_multi.txt"]
PRESETS = sorted((ROOT / "config/presets/AgentConfigs/quickstart").glob("*.json"))
CARVE_OUT_MARKERS = ("AUTHOR PRESERVATION", "reproduce that rule's author", "unless the article itself")


def _sigma_agent_prompt(preset: Path) -> str:
    return json.loads(preset.read_text(encoding="utf-8"))["SigmaAgent"]["Prompt"]["prompt"]


def test_the_quickstart_presets_are_all_present():
    assert len(PRESETS) == 12


@pytest.mark.parametrize("path", SEED_PROMPTS, ids=lambda p: p.name)
def test_seed_prompts_have_no_publisher_author_carve_out(path):
    text = path.read_text(encoding="utf-8")

    assert not [m for m in CARVE_OUT_MARKERS if m in text]
    assert "author: {author}, always" in text


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.name)
def test_preset_sigma_prompts_have_no_publisher_author_carve_out(preset):
    prompt = _sigma_agent_prompt(preset)

    assert not [m for m in CARVE_OUT_MARKERS if m in prompt]
    assert "supplied author" in prompt, "every SigmaAgent preset must still tell the model to use the supplied author"
