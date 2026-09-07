"""Pin the Sigma prompt files to the kwargs the code formats them with.

Each prompt under ``src/prompts/`` is rendered with exactly one ``str.format`` pass by
``PromptLoader``. A stray ``{`` in a JSON example or a placeholder the caller never
passes fails at runtime with a KeyError/ValueError that only surfaces on a real LLM
call, so this test renders every Sigma prompt with the caller's exact kwarg set.

Kwarg sets are copied from the call sites:
  * sigma_generate_multi / sigma_generation -- SigmaGenerationService.generate_sigma_rules
    and _build_expansion_prompt
  * sigma_repair_single -- SigmaGenerationService._repair_rules and
    POST /api/sigma-queue/{id}/validate (attempts 2-3)
  * sigma_validate_single -- POST /api/sigma-queue/{id}/validate (attempt 1)
  * sigma_enrichment -- POST /api/sigma-queue/{id}/enrich

``sigma_generation.txt`` is the bootstrap seed that ``reset-to-defaults`` and
``bootstrap`` copy into the DB, and ``sigma_generate_multi.txt`` is the runtime file
fallback; they must stay byte-identical so both paths teach the same standard.
"""

from __future__ import annotations

import re
from pathlib import Path
from string import Formatter

import pytest

from src.utils.prompt_loader import PromptLoader

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "src" / "prompts"

GENERATION_KWARGS = {
    "title": "Example Article",
    "source": "Example Source",
    "url": "https://example.com/report",
    "content": "Example article content.",
    "observables_section": "Extracted Observables:\n[0] cmd: powershell -enc AAA",
    "date": "2026-09-03",
    "author": "Huntable CTI Studio",
}

PROMPT_KWARGS: dict[str, dict[str, str]] = {
    "sigma_generate_multi": GENERATION_KWARGS,
    "sigma_generation": GENERATION_KWARGS,
    "sigma_repair_single": {
        "validation_errors": "Detection must contain a 'condition' key",
        "original_rule": "title: Broken Rule\nlogsource:\n  category: process_creation\n",
    },
    "sigma_validate_single": {"rule_yaml": "title: Draft Rule\n"},
    "sigma_enrichment": {
        "rule_yaml": "title: Draft Rule\n",
        "article_title": "Example Article",
        "article_url": "https://example.com/report",
        "article_content_section": "Article content:\nExample article content.",
        "user_instruction": "Validate and polish this Sigma rule under the enabled directives.",
        "toggles_json": '{"d1": true, "d2": true}',
        "author_value": "Huntable CTI Studio User",
    },
}


def _placeholders(template: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(template) if field}


@pytest.fixture(scope="module")
def loader() -> PromptLoader:
    return PromptLoader(prompts_dir=str(PROMPTS_DIR))


def test_bootstrap_seed_is_byte_identical_to_runtime_prompt():
    seed = (PROMPTS_DIR / "sigma_generation.txt").read_bytes()
    runtime = (PROMPTS_DIR / "sigma_generate_multi.txt").read_bytes()
    assert seed == runtime, "sigma_generation.txt (DB seed) drifted from sigma_generate_multi.txt (file fallback)"


@pytest.mark.parametrize("prompt_name", sorted(PROMPT_KWARGS))
def test_prompt_placeholders_match_caller_kwargs(prompt_name: str):
    template = (PROMPTS_DIR / f"{prompt_name}.txt").read_text(encoding="utf-8")
    expected = set(PROMPT_KWARGS[prompt_name])
    assert _placeholders(template) == expected


@pytest.mark.parametrize("prompt_name", sorted(PROMPT_KWARGS))
def test_prompt_formats_in_one_pass(loader: PromptLoader, prompt_name: str):
    rendered = loader.format_prompt(prompt_name, **PROMPT_KWARGS[prompt_name])
    assert rendered.strip()
    # A doubled brace surviving the single format pass means the file was escaped for
    # two passes (the model would see "{{ ... }}" in a JSON example).
    assert "{{" not in rendered and "}}" not in rendered
    for value in PROMPT_KWARGS[prompt_name].values():
        assert value in rendered


def test_generation_prompt_teaches_the_shared_standard(loader: PromptLoader):
    rendered = loader.format_prompt("sigma_generate_multi", **GENERATION_KWARGS)
    assert "attack.command-and-control" in rendered
    assert not re.search(r"attack\.[a-z]+_[a-z_]+", rendered), "underscored tactic tag in generation prompt"
    assert "YYYY-MM-DD" in rendered and "YYYY/MM/DD" not in rendered
    assert "observables_used" in rendered
    for forbidden in ("UserAgent|", "HttpMethod:", "ServerName:", "ALPN:", "url|contains"):
        assert forbidden not in rendered, f"non-SigmaHQ field taught by example: {forbidden}"
