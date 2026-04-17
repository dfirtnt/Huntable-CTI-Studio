#!/usr/bin/env python3
"""
Format Extract Agent training data for fine-tuning.

Converts harvested training data into instruction-following format
suitable for fine-tuning language models.
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_extract_agent_prompt() -> tuple[dict[str, Any], str]:
    """Load Extract Agent prompt config and instructions template.

    The user-message template is code-owned in llm_service._EXTRACT_BEHAVIORS_TEMPLATE.
    This script uses a local copy for training data formatting; keep in sync if the
    runtime template changes.
    """
    prompts_dir = project_root / "src" / "prompts"

    # Load prompt config from seed file (contract-compliant JSON)
    prompt_path = prompts_dir / "ExtractAgent"
    if prompt_path.exists():
        with open(prompt_path) as f:
            prompt_config = json.load(f)
    else:
        # Minimal valid fallback
        prompt_config = {
            "role": "You are an extraction agent for cyber threat intelligence articles. You extract huntable behaviors and observables relevant to EDR detection, threat hunting, and Sigma rule generation.",
            "task": "Extract huntable behaviors and observables. Output unique and discrete entries only.",
        }

    # Template is code-owned in llm_service._EXTRACT_BEHAVIORS_TEMPLATE.
    # Kept here as a local copy for training data formatting.
    instructions_template = (
        "Title: {title}\n\n"
        "URL: {url}\n\n"
        "Content:\n\n"
        "{content}\n\n"
        "Extract huntable behaviors and observables relevant to EDR detection, threat hunting, "
        "and Sigma rule generation. Use only information explicitly present in the content. "
        "Do not invent or autofill missing pieces.\n\n"
        "Prompt config (schema and constraints):\n"
        "{prompt_config}\n\n"
        "Output a single valid JSON object only. No markdown, no code fences, no prose outside JSON. "
        "If a category is empty, return an empty array for that field."
    )

    return prompt_config, instructions_template


def format_for_instruction_tuning(
    example: dict[str, Any], prompt_config: dict[str, Any], instructions_template: str
) -> dict[str, Any]:
    """
    Format a training example for instruction tuning.

    Args:
        example: Training example with article content and extraction result
        prompt_config: Extract Agent prompt configuration
        instructions_template: Instructions template string

    Returns:
        Formatted example in instruction-following format
    """
    title = example.get("title", "")
    url = example.get("url", "")
    content = example.get("content", "")
    extraction_result = example.get("extraction_result", {})

    # Build prompt_config JSON string
    prompt_config_json = json.dumps(prompt_config, indent=2)

    # Format instruction (input)
    instruction = instructions_template.format(title=title, url=url, content=content, prompt_config=prompt_config_json)

    # Format response (output) - must be valid JSON
    # Ensure it matches expected format
    observables = extraction_result.get("observables", [])
    summary = extraction_result.get("summary", {})

    # Build response JSON
    response = {
        "observables": observables,
        "summary": {
            "count": extraction_result.get("discrete_huntables_count", len(observables)),
            "source_url": url,
            "platforms_detected": summary.get("platforms_detected", ["Windows"]),
        },
    }

    response_json = json.dumps(response, ensure_ascii=False, indent=2)

    # Format for different fine-tuning frameworks
    # Format 1: Alpaca/ShareGPT format (for most instruction-tuning frameworks)
    alpaca_format = {
        "instruction": "Extract huntable behaviors and observables from the threat intelligence article.",
        "input": instruction,
        "output": response_json,
    }

    # Format 2: ChatML format (for models that use chat templates)
    chatml_format = [
        {"role": "system", "content": prompt_config.get("role", "You are an extraction agent.")},
        {"role": "user", "content": instruction},
        {"role": "assistant", "content": response_json},
    ]

    # Format 3: Simple prompt-response (for basic fine-tuning)
    simple_format = {"prompt": instruction, "response": response_json}

    return {
        "article_id": example.get("article_id"),
        "source": example.get("source", "unknown"),
        "alpaca": alpaca_format,
        "chatml": chatml_format,
        "simple": simple_format,
        "metadata": {
            "title": title,
            "url": url,
            "observables_count": len(observables),
            "discrete_huntables_count": extraction_result.get("discrete_huntables_count", 0),
        },
    }


def main():
    """Main formatting function."""
    import argparse

    parser = argparse.ArgumentParser(description="Format Extract Agent training data for fine-tuning")
    parser.add_argument("--input", type=str, required=True, help="Input training data JSON file (from harvest script)")
    parser.add_argument(
        "--output",
        type=str,
        default="outputs/training_data/extract_agent_formatted.json",
        help="Output formatted training data file",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["alpaca", "chatml", "simple", "all"],
        default="all",
        help="Output format (default: all)",
    )
    parser.add_argument("--max-examples", type=int, help="Maximum number of examples to format (for testing)")

    args = parser.parse_args()

    print("=" * 80)
    print("Extract Agent Training Data Formatter")
    print("=" * 80)
    print()

    # Load training data
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        return

    print(f"Loading training data from: {input_path}")
    with open(input_path) as f:
        training_data = json.load(f)

    print(f"   Found {len(training_data)} examples")

    # Load prompt config and template
    print("Loading Extract Agent prompt configuration...")
    prompt_config, instructions_template = load_extract_agent_prompt()
