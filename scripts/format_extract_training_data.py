#!/usr/bin/env python3
"""
Format Extract Agent training data for fine-tuning.

Converts harvested training data into instruction-following format
suitable for fine-tuning language models.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def load_extract_agent_prompt() -> tuple[Dict[str, Any], str]:
    """Load Extract Agent prompt config and instructions template."""
    prompts_dir = project_root / "src" / "prompts"
    
    # Load prompt config
    prompt_path = prompts_dir / "ExtractAgent"
    if prompt_path.exists():
        with open(prompt_path, 'r') as f:
            prompt_config = json.load(f)
    else:
        # Fallback to default structure
        prompt_config = {
            "role": "You are a detection engineer LLM. Your task is to extract telemetry-aware attacker techniques and observables that are useful to detection engineers and threat hunters.",
            "objective": "Extract telemetry-based observables (command-line executions, process chains, service/registry modifications, file path usage, event log manipulation). Output unique and discrete entries only.",
            "exclusions": {
                "do_not_extract": [
                    "Atomic IOCs like single IP addresses, domains, or file hashes",
                    "One-off URLs or email addresses without recognizable structure or patterns"
                ],
                "do_extract": [
                    "Command-line executions (especially chained or obfuscated)",
                    "Parent → child process chains",
                    "Registry key/value modification patterns",
                    "Service manipulation (creation, deletion, status change)",
                    "Suspicious file paths or locations (Temp dirs, uncommon drive paths)",
                    "Event log deletion or manipulation",
                    "Encoded or obfuscated values"
                ]
            },
            "output_format": {
                "observables": "Array of unique observables with tags (e.g., process_cmdline, registry_pattern, service_command)",
                "summary": {
                    "count": "Integer value representing the number of unique discrete observables extracted",
                    "source_url": "Source URL of the original content",
                    "platforms_detected": "Array of detected platforms (e.g., ['Windows'])"
                }
            }
        }
    
    # Load instructions template
    instructions_path = prompts_dir / "ExtractAgentInstructions.txt"
    if instructions_path.exists():
        with open(instructions_path, 'r') as f:
            instructions_template = f.read()
    else:
        # Fallback template
        instructions_template = """Title: {title}

URL: {url}

Content:

{content}

Extract telemetry-aware attacker behaviors and observables.

{prompt_config}

CRITICAL: Output your response as a valid JSON object only. Begin with {{{{ and end with }}}}. Do not include reasoning, explanations, or markdown outside the JSON object."""
    
    return prompt_config, instructions_template


def format_for_instruction_tuning(
    example: Dict[str, Any],
    prompt_config: Dict[str, Any],
    instructions_template: str
) -> Dict[str, Any]:
    """
    Format a training example for instruction tuning.
    
    Args:
        example: Training example with article content and extraction result
        prompt_config: Extract Agent prompt configuration
        instructions_template: Instructions template string
    
    Returns:
        Formatted example in instruction-following format
    """
    title = example.get('title', '')
    url = example.get('url', '')
    content = example.get('content', '')
    extraction_result = example.get('extraction_result', {})
    
    # Build prompt_config JSON string
    prompt_config_json = json.dumps(prompt_config, indent=2)
    
    # Format instruction (input)
    instruction = instructions_template.format(
        title=title,
        url=url,
        content=content,
        prompt_config=prompt_config_json
    )
    
    # Format response (output) - must be valid JSON
    # Ensure it matches expected format
    observables = extraction_result.get('observables', [])
    summary = extraction_result.get('summary', {})
    
    # Build response JSON
    response = {
        "observables": observables,
        "summary": {
            "count": extraction_result.get('discrete_huntables_count', len(observables)),
            "source_url": url,
            "platforms_detected": summary.get('platforms_detected', ['Windows'])
        }
    }
    
    response_json = json.dumps(response, ensure_ascii=False, indent=2)
    
    # Format for different fine-tuning frameworks
    # Format 1: Alpaca/ShareGPT format (for most instruction-tuning frameworks)
    alpaca_format = {
        "instruction": "Extract telemetry-aware attacker behaviors and observables from the threat intelligence article.",
        "input": instruction,
        "output": response_json
    }
    
    # Format 2: ChatML format (for models that use chat templates)
    chatml_format = [
        {
            "role": "system",
            "content": prompt_config.get("role", "You are a detection engineer LLM.")
        },
        {
            "role": "user",
            "content": instruction
        },
        {
            "role": "assistant",
            "content": response_json
        }
    ]
    
    # Format 3: Simple prompt-response (for basic fine-tuning)
    simple_format = {
        "prompt": instruction,
        "response": response_json
    }
    
    return {
        "article_id": example.get('article_id'),
        "source": example.get('source', 'unknown'),
        "alpaca": alpaca_format,
        "chatml": chatml_format,
        "simple": simple_format,
        "metadata": {
            "title": title,
            "url": url,
            "observables_count": len(observables),
            "discrete_huntables_count": extraction_result.get('discrete_huntables_count', 0)
        }
    }


def main():
    """Main formatting function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Format Extract Agent training data for fine-tuning')
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Input training data JSON file (from harvest script)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='outputs/training_data/extract_agent_formatted.json',
        help='Output formatted training data file'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['alpaca', 'chatml', 'simple', 'all'],
        default='all',
        help='Output format (default: all)'
    )
    parser.add_argument(
        '--max-examples',
        type=int,
        help='Maximum number of examples to format (for testing)'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Extract Agent Training Data Formatter")
    print("=" * 80)
    print()
    
    # Load training data
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        return
    
    print(f"📂 Loading training data from: {input_path}")
    with open(input_path, 'r') as f:
        training_data = json.load(f)
    
    print(f"   Found {len(training_data)} examples")
    
    # Load prompt config and template
    print("📝 Loading Extract Agent prompt configuration...")
    prompt_config, instructions_template = load_extract_agent_prompt()
    
    # Format examples
    print(f"🔄 Formatting examples...")
    formatted_examples = []
    
    max_examples = args.max_examples or len(training_data)
    
    for idx, example in enumerate(training_data[:max_examples]):
        try:
            formatted = format_for_instruction_tuning(
                example,
                prompt_config,
                instructions_template
            )
            formatted_examples.append(formatted)
            
            if (idx + 1) % 100 == 0:
                print(f"   Processed {idx + 1}/{max_examples} examples...")
                
        except Exception as e:
            print(f"⚠️  Error formatting example {idx}: {e}")
            continue
    
    print(f"   ✅ Formatted {len(formatted_examples)} examples")
    
    # Save formatted data
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save in requested format(s)
    if args.format == 'all':
        # Save all formats
        formats = ['alpaca', 'chatml', 'simple']
    else:
        formats = [args.format]
    
    for fmt in formats:
        # Extract format-specific data
        format_data = []
        for example in formatted_examples:
            if fmt in example:
                format_data.append(example[fmt])
        
        # Save format-specific file
        format_output = output_path.parent / f"{output_path.stem}_{fmt}{output_path.suffix}"
        with open(format_output, 'w') as f:
            json.dump(format_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved {fmt} format to: {format_output}")
        print(f"   - Examples: {len(format_data)}")
        print(f"   - File size: {format_output.stat().st_size / 1024 / 1024:.2f} MB")
    
    # Also save full format with metadata
    with open(output_path, 'w') as f:
        json.dump(formatted_examples, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Saved full formatted data to: {output_path}")
    
    # Statistics
    if formatted_examples:
        total_observables = sum(
            ex['metadata']['observables_count']
            for ex in formatted_examples
        )
        avg_observables = total_observables / len(formatted_examples)
        print(f"\n📊 Statistics:")
        print(f"   - Average observables per example: {avg_observables:.1f}")
        print(f"   - Total observables: {total_observables}")
    
    print("\n✅ Formatting complete!")


if __name__ == "__main__":
    main()

