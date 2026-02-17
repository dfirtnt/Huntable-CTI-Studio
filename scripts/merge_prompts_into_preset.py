#!/usr/bin/env python3
"""
Merge prompt file contents from src/prompts into a workflow preset JSON.
Reads preset from path (e.g. ~/Downloads/anthropicnolmstudioprompt.json),
fills agent_prompts from repo files, writes merged preset to output path.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "src" / "prompts"

# Agents and their prompt file paths (relative to src/prompts)
AGENT_PROMPT_FILES = {
    "RankAgent": "lmstudio_sigma_ranking.txt",
    "SigmaAgent": "sigma_generation.txt",
    "QAAgent": "QAAgentCMD",
    "CmdlineExtract": "CmdlineExtract",
    "CmdLineQA": "CmdLineQA",
    "ProcTreeExtract": "ProcTreeExtract",
    "ProcTreeQA": "ProcTreeQA",
    "HuntQueriesExtract": "HuntQueriesExtract",
    "HuntQueriesQA": "HuntQueriesQA",
    "ExtractAgent": "ExtractAgent",
}


def load_prompt(agent_name: str) -> str:
    fname = AGENT_PROMPT_FILES[agent_name]
    path = PROMPTS_DIR / fname
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def main() -> None:
    preset_path = Path(sys.argv[1]).expanduser()
    out_path = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else preset_path

    preset = json.loads(preset_path.read_text(encoding="utf-8"))
    agent_prompts = preset.get("agent_prompts") or {}

    for agent_name in AGENT_PROMPT_FILES:
        content = load_prompt(agent_name)
        if not content:
            continue
        existing = agent_prompts.get(agent_name) or {}
        if isinstance(existing, dict) and "disabled_agents" in existing:
            continue  # skip ExtractAgentSettings-like entries
        agent_prompts[agent_name] = {
            "model": existing.get("model", "Not configured"),
            "prompt": content,
            "instructions": existing.get("instructions", ""),
        }

    preset["agent_prompts"] = agent_prompts
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(preset, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote merged preset to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/merge_prompts_into_preset.py <preset.json> [out.json]")
        sys.exit(1)
    main()
