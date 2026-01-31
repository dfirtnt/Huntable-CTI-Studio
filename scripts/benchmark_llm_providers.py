#!/usr/bin/env python3
"""
Comprehensive LLM Provider Benchmark Script

Tests all 5 LLM providers (OpenAI, Anthropic, LM Studio, MLX, llama.cpp)
across different model sizes and measures performance metrics.

Usage:
    python scripts/benchmark_llm_providers.py
    python scripts/benchmark_llm_providers.py --provider mlx --model-size 1b
    python scripts/benchmark_llm_providers.py --quick
"""

import argparse
import asyncio
import json

# Add src to path for imports
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

sys.path.append(str(Path(__file__).parent.parent))

from src.services.llm_generation_service import LLMGenerationService

console = Console()


class LLMBenchmark:
    """Comprehensive LLM provider benchmarking tool."""

    def __init__(self):
        self.service = LLMGenerationService()
        self.results = []
        self.test_prompts = [
            "Analyze this threat intelligence about PowerShell malware execution with encoded commands.",
            "What are the key indicators of compromise for this ransomware campaign?",
            "Generate SIGMA rules for detecting suspicious network traffic patterns.",
            "Summarize the attack techniques used in this APT campaign.",
            "Identify the persistence mechanisms described in this threat report.",
        ]

    async def test_provider(self, provider: str, model_name: str, prompt: str, warmup: bool = False) -> dict[str, Any]:
        """Test a single provider with a prompt."""
        start_time = time.time()

        try:
            # Build minimal context for testing
            context = "Sample threat intelligence content about malware execution and persistence mechanisms."

            # Generate response
            response = await self.service.generate_rag_response(
                query=prompt,
                retrieved_chunks=[
                    {
                        "title": "Test Article",
                        "source_name": "Test Source",
                        "content": context,
                        "canonical_url": "https://example.com",
                        "similarity": 0.95,
                    }
                ],
                conversation_history=None,
                provider=provider,
            )

            end_time = time.time()
            response_time = end_time - start_time

            return {
                "success": True,
                "response_time": response_time,
                "response_length": len(response.get("response", "")),
                "provider": provider,
                "model_name": model_name,
                "response": response.get("response", "")[:100] + "..."
                if len(response.get("response", "")) > 100
                else response.get("response", ""),
                "error": None,
            }

        except Exception as e:
            end_time = time.time()
            response_time = end_time - start_time

            return {
                "success": False,
                "response_time": response_time,
                "response_length": 0,
                "provider": provider,
                "model_name": model_name,
                "response": "",
                "error": str(e),
            }

    async def benchmark_provider(self, provider: str, model_name: str) -> dict[str, Any]:
        """Benchmark a single provider with multiple prompts."""
        console.print(f"[blue]Testing {provider} ({model_name})...[/blue]")

        # Test availability first
        if provider == "openai" and not self.service.openai_api_key:
            return {"available": False, "reason": "OpenAI API key not configured"}
        if provider == "anthropic" and not self.service.anthropic_api_key:
            return {"available": False, "reason": "Anthropic API key not configured"}
        if provider == "lmstudio" and not self.service._is_lmstudio_available():
            return {"available": False, "reason": "LM Studio service not available"}
        if provider == "mlx" and not self.service._is_mlx_available():
            return {"available": False, "reason": "MLX not available or model not found"}
        if provider == "llamacpp" and not self.service._is_llamacpp_available():
            return {"available": False, "reason": "llama.cpp not available or model not found"}

        results = []

        # Cold start test (first request)
        console.print("  [yellow]Cold start test...[/yellow]")
        cold_result = await self.test_provider(provider, model_name, self.test_prompts[0])
        results.append(cold_result)

        # Warm requests (average of remaining prompts)
        console.print("  [yellow]Warm requests test...[/yellow]")
        warm_results = []
        for prompt in self.test_prompts[1:]:
            result = await self.test_provider(provider, model_name, prompt)
            warm_results.append(result)

        # Calculate metrics
        successful_results = [r for r in results + warm_results if r["success"]]
        if not successful_results:
            return {
                "available": True,
                "successful": False,
                "reason": "All requests failed",
                "cold_start_time": cold_result["response_time"],
                "avg_warm_time": 0,
                "success_rate": 0,
                "avg_response_length": 0,
            }

        cold_start_time = cold_result["response_time"]
        avg_warm_time = (
            sum(r["response_time"] for r in warm_results if r["success"])
            / len([r for r in warm_results if r["success"]])
            if warm_results
            else 0
        )
        success_rate = len(successful_results) / len(results + warm_results)
        avg_response_length = sum(r["response_length"] for r in successful_results) / len(successful_results)

        return {
            "available": True,
            "successful": True,
            "cold_start_time": cold_start_time,
            "avg_warm_time": avg_warm_time,
            "success_rate": success_rate,
            "avg_response_length": avg_response_length,
            "total_requests": len(results + warm_results),
            "successful_requests": len(successful_results),
        }

    async def run_benchmark(self, providers: list[str] | None = None, quick: bool = False) -> dict[str, Any]:
        """Run comprehensive benchmark across all providers."""
        if providers is None:
            providers = ["openai", "anthropic", "lmstudio", "mlx", "llamacpp"]

        console.print(
            Panel.fit(
                "[bold blue]LLM Provider Performance Benchmark[/bold blue]\n"
                f"Testing providers: {', '.join(providers)}\n"
                f"Quick mode: {'Yes' if quick else 'No'}",
                border_style="blue",
            )
        )

        benchmark_results = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            for provider in providers:
                task = progress.add_task(f"Testing {provider}...", total=100)

                # Get model name for this provider
                model_name = self.service._get_model_name(provider)

                # Run benchmark
                result = await self.benchmark_provider(provider, model_name)
                benchmark_results[provider] = result

                progress.update(task, completed=100)

        # Generate summary
        self.generate_summary_table(benchmark_results)

        # Save results
        self.save_results(benchmark_results)

        return benchmark_results

    def generate_summary_table(self, results: dict[str, Any]):
        """Generate a summary table of benchmark results."""
        table = Table(title="LLM Provider Performance Summary")

        table.add_column("Provider", style="cyan", no_wrap=True)
        table.add_column("Model", style="magenta")
        table.add_column("Available", style="green")
        table.add_column("Cold Start", style="yellow", justify="right")
        table.add_column("Avg Warm", style="yellow", justify="right")
        table.add_column("Success Rate", style="green", justify="right")
        table.add_column("Avg Length", style="blue", justify="right")

        for provider, result in results.items():
            if not result.get("available", False):
                table.add_row(
                    provider.title(), self.service._get_model_name(provider), "❌ No", "-", "-", "-", "-", style="red"
                )
            elif not result.get("successful", False):
                table.add_row(
                    provider.title(),
                    self.service._get_model_name(provider),
                    "⚠️ Failed",
                    f"{result.get('cold_start_time', 0):.2f}s",
                    "-",
                    f"{result.get('success_rate', 0):.1%}",
                    "-",
                    style="yellow",
                )
            else:
                table.add_row(
                    provider.title(),
                    self.service._get_model_name(provider),
                    "✅ Yes",
                    f"{result.get('cold_start_time', 0):.2f}s",
                    f"{result.get('avg_warm_time', 0):.2f}s",
                    f"{result.get('success_rate', 0):.1%}",
                    f"{result.get('avg_response_length', 0):.0f}",
                    style="green",
                )

        console.print(table)

        # Performance ranking
        successful_results = {k: v for k, v in results.items() if v.get("successful", False)}
        if successful_results:
            console.print("\n[bold]Performance Ranking (by average warm time):[/bold]")
            sorted_results = sorted(successful_results.items(), key=lambda x: x[1].get("avg_warm_time", float("inf")))

            for i, (provider, result) in enumerate(sorted_results, 1):
                speedup = sorted_results[0][1].get("avg_warm_time", 1) / result.get("avg_warm_time", 1)
                console.print(f"{i}. {provider.title()}: {result.get('avg_warm_time', 0):.2f}s ({speedup:.1f}x)")

    def save_results(self, results: dict[str, Any]):
        """Save benchmark results to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create logs directory if it doesn't exist
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        # Save JSON results
        json_file = logs_dir / f"llm_benchmark_results_{timestamp}.json"
        with open(json_file, "w") as f:
            json.dump({"timestamp": timestamp, "results": results, "test_prompts": self.test_prompts}, f, indent=2)

        # Save Markdown report
        md_file = logs_dir / f"LLM_BENCHMARK_REPORT_{timestamp}.md"
        with open(md_file, "w") as f:
            f.write("# LLM Provider Benchmark Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("## Summary\n\n")
            f.write("| Provider | Model | Available | Cold Start | Avg Warm | Success Rate | Avg Length |\n")
            f.write("|----------|-------|-----------|------------|----------|--------------|------------|\n")

            for provider, result in results.items():
                if not result.get("available", False):
                    f.write(
                        f"| {provider.title()} | {self.service._get_model_name(provider)} | ❌ No | - | - | - | - |\n"
                    )
                elif not result.get("successful", False):
                    f.write(
                        f"| {provider.title()} | {self.service._get_model_name(provider)} | ⚠️ Failed | {result.get('cold_start_time', 0):.2f}s | - | {result.get('success_rate', 0):.1%} | - |\n"
                    )
                else:
                    f.write(
                        f"| {provider.title()} | {self.service._get_model_name(provider)} | ✅ Yes | {result.get('cold_start_time', 0):.2f}s | {result.get('avg_warm_time', 0):.2f}s | {result.get('success_rate', 0):.1%} | {result.get('avg_response_length', 0):.0f} |\n"
                    )

            f.write("\n## Detailed Results\n\n")
            for provider, result in results.items():
                f.write(f"### {provider.title()}\n\n")
                if not result.get("available", False):
                    f.write("**Status:** Not Available\n")
                    f.write(f"**Reason:** {result.get('reason', 'Unknown')}\n\n")
                elif not result.get("successful", False):
                    f.write("**Status:** Failed\n")
                    f.write(f"**Reason:** {result.get('reason', 'Unknown')}\n")
                    f.write(f"**Cold Start Time:** {result.get('cold_start_time', 0):.2f}s\n\n")
                else:
                    f.write("**Status:** Successful\n")
                    f.write(f"**Cold Start Time:** {result.get('cold_start_time', 0):.2f}s\n")
                    f.write(f"**Average Warm Time:** {result.get('avg_warm_time', 0):.2f}s\n")
                    f.write(f"**Success Rate:** {result.get('success_rate', 0):.1%}\n")
                    f.write(f"**Average Response Length:** {result.get('avg_response_length', 0):.0f} characters\n")
                    f.write(f"**Total Requests:** {result.get('total_requests', 0)}\n")
                    f.write(f"**Successful Requests:** {result.get('successful_requests', 0)}\n\n")

        console.print("\n[green]Results saved to:[/green]")
        console.print(f"  JSON: {json_file}")
        console.print(f"  Markdown: {md_file}")


async def main():
    """Main benchmark function."""
    parser = argparse.ArgumentParser(description="LLM Provider Performance Benchmark")
    parser.add_argument("--provider", help="Test specific provider only")
    parser.add_argument("--model-size", help="Test specific model size (1b, 3b, 7b)")
    parser.add_argument("--quick", action="store_true", help="Quick test with fewer prompts")

    args = parser.parse_args()

    benchmark = LLMBenchmark()

    # Override test prompts for quick mode
    if args.quick:
        benchmark.test_prompts = benchmark.test_prompts[:2]

    # Determine providers to test
    providers = None
    if args.provider:
        providers = [args.provider]

    # Run benchmark
    await benchmark.run_benchmark(providers=providers, quick=args.quick)


if __name__ == "__main__":
    asyncio.run(main())
