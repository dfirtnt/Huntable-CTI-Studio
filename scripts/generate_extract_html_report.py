#!/usr/bin/env python3
"""Generate HTML report for Extract Agent benchmark results."""

import glob
import json
import os
import statistics
from datetime import datetime
from typing import Any

ARTICLE_IDS = [1974, 1909, 1866, 1860, 1937, 1794]


def load_results_file(filepath: str) -> dict[str, Any]:
    """Load results from a JSON file."""
    if not os.path.exists(filepath):
        return None
    with open(filepath) as f:
        return json.load(f)


def extract_count_from_result(result: Any, model_name: str) -> int:
    """Extract discrete count from result."""
    if isinstance(result, dict):
        if "observable_count" in result:
            return result["observable_count"]
        if "summary" in result and isinstance(result["summary"], dict):
            if "count" in result["summary"]:
                return result["summary"]["count"]
        if "discrete_huntables_count" in result:
            return result["discrete_huntables_count"]
        if isinstance(result.get("discrete_count"), int):
            return result["discrete_count"]
    elif isinstance(result, list) and len(result) > 0:
        first_run = result[0]
        if isinstance(first_run, dict):
            if "discrete_count" in first_run:
                return first_run["discrete_count"]
            if "metrics" in first_run and "discrete_count" in first_run["metrics"]:
                return first_run["metrics"]["discrete_count"]
    return None


def check_json_validity(result: Any) -> bool:
    """Check if result has valid JSON."""
    if isinstance(result, dict):
        if "json_valid" in result:
            return result["json_valid"]
        if "error" in result:
            return False
        if "full_response" in result:
            return True
        if "observables" in result or "summary" in result:
            return True
        if "observable_count" in result:
            return True
    elif isinstance(result, list) and len(result) > 0:
        first_run = result[0]
        if isinstance(first_run, dict):
            if "json_valid" in first_run:
                return first_run["json_valid"]
            if "metrics" in first_run and "json_valid" in first_run["metrics"]:
                return first_run["metrics"]["json_valid"]
            if "discrete_count" in first_run:
                return True
    return False


def analyze_all_models() -> dict[str, dict[str, Any]]:
    """Analyze all model results."""
    all_results = {}

    # Cloud models
    cloud_models = {
        "Claude Sonnet 4.5": ("claude_extract_results_full.json", "claude_extract_results.json"),
        "GPT-4o": ("gpt4o_extract_results_full.json", "gpt4o_extract_results.json"),
    }

    for model_name, (full_file, summary_file) in cloud_models.items():
        results = load_results_file(full_file)
        if not results:
            results = load_results_file(summary_file)
        if results:
            all_results[model_name] = results

    # LMStudio models
    for filepath in glob.glob("lmstudio_extract_*.json"):
        model_name = os.path.basename(filepath).replace("lmstudio_extract_", "").replace(".json", "")
        results = load_results_file(filepath)
        if results:
            all_results[model_name] = results

    # Analyze each model
    analyses = {}
    for model_name, results in all_results.items():
        counts = {}
        valid_count = 0
        total_articles = 0

        for article_id in ARTICLE_IDS:
            article_key = str(article_id)
            if article_key not in results:
                continue

            total_articles += 1
            result = results[article_key]

            count = extract_count_from_result(result, model_name)
            if count is not None:
                counts[article_id] = count

            if check_json_validity(result):
                valid_count += 1

        json_valid_rate = (valid_count / total_articles * 100) if total_articles > 0 else 0

        if counts:
            counts_list = list(counts.values())
            stats = {
                "min": min(counts_list),
                "max": max(counts_list),
                "mean": statistics.mean(counts_list),
                "median": statistics.median(counts_list),
                "total": sum(counts_list),
            }
            if len(counts_list) > 1:
                stats["stdev"] = statistics.stdev(counts_list)
            else:
                stats["stdev"] = 0.0
        else:
            stats = None

        analyses[model_name] = {
            "counts": counts,
            "articles_tested": total_articles,
            "articles_complete": len(counts),
            "json_valid_rate": json_valid_rate,
            "stats": stats,
        }

    return analyses


def generate_html(analyses: dict[str, dict[str, Any]]) -> str:
    """Generate HTML report."""

    # Sort models by total count (descending)
    sorted_models = sorted(analyses.items(), key=lambda x: x[1]["stats"]["total"] if x[1]["stats"] else 0, reverse=True)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Extract Agent Benchmark Results</title>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 15px; margin-top: 0; }}
        h2 {{ color: #34495e; margin-top: 40px; border-bottom: 2px solid #ecf0f1; padding-bottom: 10px; }}
        .meta {{ color: #7f8c8d; margin: 20px 0; font-size: 14px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th {{ background: #34495e; color: white; padding: 12px; text-align: left; font-weight: 600; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #ecf0f1; }}
        tr:hover {{ background: #f8f9fa; }}
        .status-ok {{ color: #27ae60; font-weight: bold; }}
        .status-warn {{ color: #f39c12; font-weight: bold; }}
        .status-error {{ color: #e74c3c; font-weight: bold; }}
        .bar-container {{ display: flex; align-items: center; margin: 5px 0; }}
        .bar-label {{ width: 250px; font-size: 13px; font-weight: 500; }}
        .bar-wrapper {{ flex: 1; height: 25px; background: #ecf0f1; border-radius: 4px; position: relative; overflow: hidden; }}
        .bar {{ height: 100%; background: linear-gradient(90deg, #3498db, #2980b9); display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; color: white; font-size: 11px; font-weight: bold; transition: width 0.3s; }}
        .bar-value {{ width: 80px; text-align: right; font-family: monospace; font-size: 13px; margin-left: 10px; }}
        .highlight {{ background: #d4edda; border-left: 4px solid #28a745; padding: 15px; margin: 20px 0; }}
        .warning {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
        .error-box {{ background: #f8d7da; border-left: 4px solid #dc3545; padding: 15px; margin: 20px 0; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 6px; border-left: 4px solid #3498db; }}
        .stat-label {{ font-size: 12px; color: #7f8c8d; text-transform: uppercase; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #2c3e50; margin-top: 5px; }}
        .comparison-table {{ font-size: 13px; }}
        .comparison-table td {{ text-align: center; }}
        .comparison-table th {{ white-space: nowrap; position: relative; }}
        .comparison-table th.rotated {{ 
            height: 140px; 
            vertical-align: bottom; 
            padding: 0;
            padding-bottom: 5px;
            text-align: left;
        }}
        .comparison-table th.rotated > div {{
            transform: rotate(-45deg);
            transform-origin: left bottom;
            position: absolute;
            left: 50%;
            bottom: 0;
            width: 200px;
            margin-left: -100px;
            text-align: left;
            white-space: nowrap;
            padding: 5px;
        }}
        .model-name {{ font-weight: 600; color: #2c3e50; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Extract Agent Benchmark Results</h1>
        <div class="meta">
            <strong>Generated:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}<br>
            <strong>Test Articles:</strong> {len(ARTICLE_IDS)} articles (IDs: {", ".join(map(str, ARTICLE_IDS))})<br>
            <strong>Runs per Model:</strong> 1 run per article (deterministic: temp=0, top_p=1)
        </div>
"""

    # Summary statistics
    complete_models = [m for m, a in analyses.items() if a["articles_complete"] == 6]
    total_models = len(analyses)

    html += f"""
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Models Tested</div>
                <div class="stat-value">{total_models}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Complete Models</div>
                <div class="stat-value">{len(complete_models)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Observables</div>
                <div class="stat-value">{sum(a["stats"]["total"] for a in analyses.values() if a["stats"])}</div>
            </div>
        </div>
"""

    # Model comparison table
    html += """
        <h2>Model Comparison</h2>
        <table>
            <thead>
                <tr>
                    <th>Model</th>
                    <th>Articles</th>
                    <th>JSON Valid %</th>
                    <th>Avg Count</th>
                    <th>Total Count</th>
                    <th>Std Dev</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
"""

    for model_name, analysis in sorted_models:
        articles = f"{analysis['articles_complete']}/{analysis['articles_tested']}"
        json_rate = f"{analysis['json_valid_rate']:.1f}%"

        if analysis["stats"]:
            avg_count = f"{analysis['stats']['mean']:.1f}"
            total_count = f"{analysis['stats']['total']}"
            stdev = f"{analysis['stats']['stdev']:.2f}"
        else:
            avg_count = "N/A"
            total_count = "N/A"
            stdev = "N/A"

        # Status
        if analysis["articles_complete"] == 6 and analysis["json_valid_rate"] == 100:
            status = '<span class="status-ok">✅ Complete</span>'
        elif analysis["articles_complete"] == 6:
            status = '<span class="status-warn">⚠️ Complete (JSON issues)</span>'
        else:
            status = '<span class="status-error">❌ Incomplete</span>'

        html += f"""
                <tr>
                    <td class="model-name">{model_name}</td>
                    <td>{articles}</td>
                    <td>{json_rate}</td>
                    <td>{avg_count}</td>
                    <td>{total_count}</td>
                    <td>{stdev}</td>
                    <td>{status}</td>
                </tr>
"""

    html += """
            </tbody>
        </table>
"""

    # Per-article comparison
    html += """
        <h2>Per-Article Comparison</h2>
        <table class="comparison-table">
            <thead>
                <tr>
                    <th>Article ID</th>
"""

    for model_name, _ in sorted_models:
        html += f'<th class="rotated"><div>{model_name}</div></th>\n'

    html += """
                </tr>
            </thead>
            <tbody>
"""

    for article_id in sorted(ARTICLE_IDS):
        html += f"<tr><td><strong>{article_id}</strong></td>"
        for model_name, _ in sorted_models:
            analysis = analyses[model_name]
            count = analysis["counts"].get(article_id, "N/A")
            if count == "N/A":
                html += '<td style="color: #95a5a6;">N/A</td>'
            else:
                html += f"<td>{count}</td>"
        html += "</tr>\n"

    html += """
            </tbody>
        </table>
"""

    # Extraction volume comparison
    html += """
        <h2>Extraction Volume Comparison</h2>
        <p style="color: #7f8c8d; font-size: 14px;">Total observables extracted per model</p>
"""

    if sorted_models:
        max_total = max(a["stats"]["total"] for _, a in sorted_models if a["stats"])

        for model_name, analysis in sorted_models:
            if analysis["stats"]:
                total = analysis["stats"]["total"]
                percentage = (total / max_total * 100) if max_total > 0 else 0
                html += f"""
        <div class="bar-container">
            <div class="bar-label">{model_name}</div>
            <div class="bar-wrapper">
                <div class="bar" style="width: {percentage}%;">{total}</div>
            </div>
            <div class="bar-value">{total}</div>
        </div>
"""

    # Recommendations
    html += """
        <h2>Recommendations</h2>
"""

    if complete_models:
        html += """
        <div class="highlight">
            <strong>✅ Production Ready Models:</strong>
            <ul>
"""
        for model in complete_models:
            analysis = analyses[model]
            if analysis["json_valid_rate"] == 100:
                html += f"<li><strong>{model}</strong> - Complete coverage (6/6), 100% JSON validity</li>\n"
        html += """
            </ul>
        </div>
"""

    incomplete_models = [m for m, a in analyses.items() if a["articles_complete"] < 6]
    if incomplete_models:
        html += """
        <div class="warning">
            <strong>⚠️ Incomplete Models:</strong>
            <ul>
"""
        for model in incomplete_models:
            analysis = analyses[model]
            html += f"<li><strong>{model}</strong> - {analysis['articles_complete']}/6 articles completed</li>\n"
        html += """
            </ul>
        </div>
"""

    json_issues = [m for m, a in analyses.items() if a["json_valid_rate"] < 100 and a["articles_tested"] > 0]
    if json_issues:
        html += """
        <div class="error-box">
            <strong>❌ JSON Parsing Issues:</strong>
            <ul>
"""
        for model in json_issues:
            analysis = analyses[model]
            html += f"<li><strong>{model}</strong> - {analysis['json_valid_rate']:.1f}% JSON validity</li>\n"
        html += """
            </ul>
        </div>
"""

    html += """
    </div>
</body>
</html>
"""

    return html


def main():
    """Generate HTML report."""
    print("Analyzing Extract Agent benchmark results...")
    analyses = analyze_all_models()

    if not analyses:
        print("❌ No result files found!")
        return

    print(f"Found {len(analyses)} models")

    html = generate_html(analyses)

    output_file = "extract_agent_benchmark_report.html"
    with open(output_file, "w") as f:
        f.write(html)

    print(f"\n✅ HTML report generated: {output_file}")
    print(f"   Open in browser: file://{os.path.abspath(output_file)}")


if __name__ == "__main__":
    main()
