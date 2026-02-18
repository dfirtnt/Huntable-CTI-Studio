"""
Default agent prompts loaded from src/prompts at runtime.

Used when creating the initial workflow config and when config has empty agent_prompts
so LLM agents ship with working defaults without requiring a separate merge step.
"""

from pathlib import Path

# src/utils/default_agent_prompts.py -> src/utils -> src
_SRC_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = _SRC_DIR / "prompts"

# Agent name -> filename under src/prompts (no .txt required; some files have no extension)
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
    "OSDetectionAgent": "OSDetectionAgent",
}


def get_default_agent_prompts() -> dict:
    """
    Load default agent prompts from src/prompts.

    Returns dict: agent_name -> {"model": "Not configured", "prompt": str, "instructions": ""}.
    Missing or unreadable files are skipped. Callers get a dict that may be empty if
    prompts dir is missing.
    """
    result = {}
    if not PROMPTS_DIR.exists():
        return result
    for agent_name, fname in AGENT_PROMPT_FILES.items():
        path = PROMPTS_DIR / fname
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not content:
            continue
        result[agent_name] = {
            "model": "Not configured",
            "prompt": content,
            "instructions": "",
        }
    return result
