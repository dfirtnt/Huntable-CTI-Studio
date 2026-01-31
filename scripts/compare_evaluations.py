#!/usr/bin/env python3
"""
Compare evaluation results between baseline and fine-tuned models.
"""

import json
from pathlib import Path
from typing import Any


def load_evaluation(filepath: Path) -> dict[str, Any]:
    """Load evaluation results."""
    with open(filepath) as f:
        return json.load(f)


def compare_evaluations(baseline: dict[str, Any], finetuned: dict[str, Any]) -> dict[str, Any]:
    """Compare two evaluation results."""
    baseline_metrics = baseline.get("metrics", {})
    finetuned_metrics = finetuned.get("metrics", {})

    comparison = {
        "baseline_model": baseline.get("model_name", "unknown"),
        "finetuned_model": finetuned.get("model_name", "unknown"),
        "baseline_timestamp": baseline.get("timestamp", "unknown"),
        "finetuned_timestamp": finetuned.get("timestamp", "unknown"),
        "improvements": {},
        "regressions": {},
        "unchanged": {},
    }

    # Compare metrics
    metrics_to_compare = [
        "json_validity_rate",
        "field_completeness_rate",
        "avg_discrete_count",
        "total_discrete",
        "count_accuracy",
        "type_error_rate",
        "error_rate",
    ]

    for metric in metrics_to_compare:
        baseline_val = baseline_metrics.get(metric)
        finetuned_val = finetuned_metrics.get(metric)

        if baseline_val is None or finetuned_val is None:
            continue

        diff = finetuned_val - baseline_val
        percent_change = (diff / baseline_val * 100) if baseline_val != 0 else 0

        if diff > 0.01:  # Improvement
            comparison["improvements"][metric] = {
                "baseline": baseline_val,
                "finetuned": finetuned_val,
                "diff": diff,
                "percent_change": percent_change,
            }
        elif diff < -0.01:  # Regression
            comparison["regressions"][metric] = {
                "baseline": baseline_val,
                "finetuned": finetuned_val,
                "diff": diff,
                "percent_change": percent_change,
            }
        else:  # Unchanged
            comparison["unchanged"][metric] = {"baseline": baseline_val, "finetuned": finetuned_val}

    return comparison


def print_comparison(comparison: dict[str, Any]):
    """Print comparison results."""
    print("=" * 80)
    print("Evaluation Comparison")
    print("=" * 80)
    print()
    print(f"Baseline: {comparison['baseline_model']}")
    print(f"Fine-tuned: {comparison['finetuned_model']}")
    print()

    if comparison["improvements"]:
        print("✅ Improvements:")
        for metric, data in comparison["improvements"].items():
            print(f"   {metric}:")
            print(f"     Baseline: {data['baseline']:.3f}")
            print(f"     Fine-tuned: {data['finetuned']:.3f}")
            print(f"     Change: {data['diff']:+.3f} ({data['percent_change']:+.1f}%)")
        print()

    if comparison["regressions"]:
        print("⚠️  Regressions:")
        for metric, data in comparison["regressions"].items():
            print(f"   {metric}:")
            print(f"     Baseline: {data['baseline']:.3f}")
            print(f"     Fine-tuned: {data['finetuned']:.3f}")
            print(f"     Change: {data['diff']:+.3f} ({data['percent_change']:+.1f}%)")
        print()

    if comparison["unchanged"]:
        print("➡️  Unchanged:")
        for metric, data in comparison["unchanged"].items():
            print(f"   {metric}: {data['baseline']:.3f}")
        print()


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Compare evaluation results")
    parser.add_argument("--baseline", type=str, required=True, help="Path to baseline evaluation JSON")
    parser.add_argument("--finetuned", type=str, required=True, help="Path to fine-tuned evaluation JSON")
    parser.add_argument("--output", type=str, help="Output path for comparison JSON (optional)")

    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    finetuned_path = Path(args.finetuned)

    if not baseline_path.exists():
        print(f"❌ Baseline file not found: {baseline_path}")
        return

    if not finetuned_path.exists():
        print(f"❌ Fine-tuned file not found: {finetuned_path}")
        return

    # Load evaluations
    baseline = load_evaluation(baseline_path)
    finetuned = load_evaluation(finetuned_path)

    # Compare
    comparison = compare_evaluations(baseline, finetuned)

    # Print
    print_comparison(comparison)

    # Save if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved comparison to: {output_path}")


if __name__ == "__main__":
    main()
