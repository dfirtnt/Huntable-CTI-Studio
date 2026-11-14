#!/usr/bin/env python3
"""
Render the agent prompts in config/presets/AgentConfigs/quickstart/*.json from src/prompts/.

The quickstart presets embed a full copy of every agent prompt. Editing a prompt by
hand in each preset is how they drifted: a fix reached some presets and not others,
and nothing errored. This script makes src/prompts/ the only place prompts are edited:

  * Agents with one shared prompt (extractors, RankAgent default) render from
    src/prompts/<AGENT_PROMPT_FILES[agent]>.
  * Agents with per-provider variants (SigmaAgent, RankAgent for LM Studio) render
    from src/prompts/quickstart/, with the variant per preset chosen in
    src/prompts/quickstart/manifest.yml.
  * A line ``@@include <name>@@`` in a variant file is replaced by
    src/prompts/quickstart/shared/<name>.txt, so a rule shared by every variant is
    written once.

Only each agent's ``Prompt.prompt`` field is written; models, effort, thresholds and
``instructions`` are left as they are.

Run from repo root:
  uv run --frozen python scripts/build_quickstart_prompts.py          # rewrite presets
  uv run --frozen python scripts/build_quickstart_prompts.py --check  # exit 1 on drift
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "src" / "prompts"
VARIANTS_DIR = PROMPTS_DIR / "quickstart"
SHARED_DIR = VARIANTS_DIR / "shared"
MANIFEST_PATH = VARIANTS_DIR / "manifest.yml"
QUICKSTART_DIR = REPO_ROOT / "config" / "presets" / "AgentConfigs" / "quickstart"

INCLUDE_RE = re.compile(r"^@@include ([a-z0-9_]+)@@$", re.MULTILINE)

# How each agent's prompt is stored in the preset JSON. "json" agents keep a
# compact JSON string; "text" agents keep the file text without its trailing newline.
JSON_AGENTS = {
    "SigmaAgent",
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "RegistryExtract",
    "ServicesExtract",
    "ScheduledTasksExtract",
}


def _read_source(path: Path) -> str:
    """Source files end with one newline that is not part of the prompt."""
    text = path.read_text(encoding="utf-8")
    return text[:-1] if text.endswith("\n") else text


def _expand_includes(text: str) -> str:
    def _sub(match: re.Match[str]) -> str:
        return _read_source(SHARED_DIR / f"{match.group(1)}.txt")

    return INCLUDE_RE.sub(_sub, text)


def render_prompt(agent: str, variant: str, agent_prompt_files: dict[str, str]) -> str:
    """The exact ``Prompt.prompt`` string a preset should carry for this agent."""
    if agent == "SigmaAgent":
        record = {
            "system": _expand_includes(_read_source(VARIANTS_DIR / f"SigmaAgent.{variant}.system.txt")),
            "user": _read_source(VARIANTS_DIR / f"SigmaAgent.{variant}.user.txt"),
        }
        return json.dumps(record, ensure_ascii=False)

    if variant == "default":
        source = _read_source(PROMPTS_DIR / agent_prompt_files[agent])
    else:
        source = _read_source(VARIANTS_DIR / f"{agent}.{variant}.txt")
    source = _expand_includes(source)
    if agent in JSON_AGENTS:
        return json.dumps(json.loads(source), ensure_ascii=False)
    return source.rstrip("\n")


def load_manifest() -> dict[str, dict[str, str]]:
    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}
    return {name: (variants or {}) for name, variants in (data.get("presets") or {}).items()}


def render_preset(preset_path: Path, manifest: dict[str, dict[str, str]], agent_prompt_files: dict[str, str]) -> str:
    """The preset file's full text with every agent prompt rendered from source."""
    raw = preset_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    variants = manifest[preset_path.name]
    for agent in agent_prompt_files:
        prompt = (data.get(agent) or {}).get("Prompt")
        if not isinstance(prompt, dict) or "prompt" not in prompt:
            continue
        prompt["prompt"] = render_prompt(agent, variants.get(agent, "default"), agent_prompt_files)
    # Keep each file's existing trailing-newline convention so a regeneration is a no-op.
    return json.dumps(data, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else "")


def build(check: bool) -> list[str]:
    """Render every preset. Returns the names that differ (and, unless check, rewrites them)."""
    sys.path.insert(0, str(REPO_ROOT))
    from src.utils.default_agent_prompts import AGENT_PROMPT_FILES

    manifest = load_manifest()
    presets = sorted(QUICKSTART_DIR.glob("*.json"))
    missing = [p.name for p in presets if p.name not in manifest]
    stale = sorted(set(manifest) - {p.name for p in presets})
    if missing or stale:
        raise SystemExit(f"manifest.yml out of date: unlisted presets {missing}, listed but absent {stale}")

    changed = []
    for path in presets:
        rendered = render_preset(path, manifest, AGENT_PROMPT_FILES)
        if rendered != path.read_text(encoding="utf-8"):
            changed.append(path.name)
            if not check:
                path.write_text(rendered, encoding="utf-8")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report drift without writing; exit 1 if any")
    args = parser.parse_args()

    changed = build(check=args.check)
    verb = "Out of date" if args.check else "Rewrote"
    for name in changed:
        print(f"{verb}: {name}")
    if not changed:
        print("All quickstart preset prompts match src/prompts/.")
    if args.check and changed:
        print("Run: uv run --frozen python scripts/build_quickstart_prompts.py", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
