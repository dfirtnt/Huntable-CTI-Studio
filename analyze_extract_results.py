#!/usr/bin/env python3
"""Analyze Extract Agent benchmark results across all models."""
import json
import os
import glob
import statistics
from collections import defaultdict
from typing import Dict, List, Any

# Article IDs in test set
ARTICLE_IDS = [1974, 1909, 1866, 1860, 1937, 1794]

def load_results_file(filepath: str) -> Dict[str, Any]:
    """Load results from a JSON file."""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r') as f:
        return json.load(f)

def extract_count_from_result(result: Any, model_name: str) -> int:
    """Extract discrete count from result (handles different formats)."""
    if isinstance(result, dict):
        # Format 1: Simple count dict (claude/gpt4o summary files)
        if 'observable_count' in result:
            return result['observable_count']
        
        # Format 2: Full result with summary
        if 'summary' in result and isinstance(result['summary'], dict):
            if 'count' in result['summary']:
                return result['summary']['count']
        
        # Format 3: Full result with discrete_huntables_count
        if 'discrete_huntables_count' in result:
            return result['discrete_huntables_count']
        
        # Format 4: Array of runs (lmstudio format)
        if isinstance(result.get('discrete_count'), int):
            return result['discrete_count']
    
    elif isinstance(result, list) and len(result) > 0:
        # LMStudio format: array of runs
        first_run = result[0]
        if isinstance(first_run, dict):
            if 'discrete_count' in first_run:
                return first_run['discrete_count']
            if 'metrics' in first_run and 'discrete_count' in first_run['metrics']:
                return first_run['metrics']['discrete_count']
    
    return None

def check_json_validity(result: Any) -> bool:
    """Check if result has valid JSON."""
    if isinstance(result, dict):
        if 'json_valid' in result:
            return result['json_valid']
        if 'error' in result:
            return False
        # If it has expected fields (observables, summary with count), assume valid
        # Cloud models store in full_response or directly
        if 'full_response' in result:
            return True  # Full response indicates successful extraction
        if 'observables' in result or 'summary' in result:
            return True  # Has expected structure
        if 'observable_count' in result:
            return True  # Summary file with count = successful
    
    elif isinstance(result, list) and len(result) > 0:
        first_run = result[0]
        if isinstance(first_run, dict):
            if 'json_valid' in first_run:
                return first_run['json_valid']
            if 'metrics' in first_run and 'json_valid' in first_run['metrics']:
                return first_run['metrics']['json_valid']
            # If it has discrete_count, assume valid
            if 'discrete_count' in first_run:
                return True
    
    return False

def analyze_model_results(model_name: str, results: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze results for a single model."""
    analysis = {
        'model': model_name,
        'articles_tested': 0,
        'articles_complete': 0,
        'json_valid_rate': 0.0,
        'counts': {},
        'json_valid_articles': [],
        'json_invalid_articles': [],
        'errors': []
    }
    
    valid_count = 0
    total_articles = 0
    
    for article_id in ARTICLE_IDS:
        article_key = str(article_id)
        if article_key not in results:
            continue
        
        total_articles += 1
        result = results[article_key]
        
        # Extract count
        count = extract_count_from_result(result, model_name)
        if count is not None:
            analysis['counts'][article_id] = count
        
        # Check JSON validity
        is_valid = check_json_validity(result)
        if is_valid:
            valid_count += 1
            analysis['json_valid_articles'].append(article_id)
        else:
            analysis['json_invalid_articles'].append(article_id)
            # Try to extract error
            if isinstance(result, dict) and 'error' in result:
                analysis['errors'].append(f"Article {article_id}: {result['error']}")
            elif isinstance(result, list) and len(result) > 0:
                first_run = result[0]
                if isinstance(first_run, dict) and 'error' in first_run.get('metrics', {}):
                    analysis['errors'].append(f"Article {article_id}: {first_run['metrics']['error']}")
    
    analysis['articles_tested'] = total_articles
    analysis['articles_complete'] = len(analysis['counts'])
    if total_articles > 0:
        analysis['json_valid_rate'] = valid_count / total_articles * 100
    
    # Calculate statistics on counts
    if analysis['counts']:
        counts_list = list(analysis['counts'].values())
        analysis['count_stats'] = {
            'min': min(counts_list),
            'max': max(counts_list),
            'mean': statistics.mean(counts_list),
            'median': statistics.median(counts_list),
            'total': sum(counts_list)
        }
        if len(counts_list) > 1:
            analysis['count_stats']['stdev'] = statistics.stdev(counts_list)
        else:
            analysis['count_stats']['stdev'] = 0.0
    else:
        analysis['count_stats'] = None
    
    return analysis

def main():
    """Main analysis function."""
    print("=" * 80)
    print("Extract Agent Benchmark Results Analysis")
    print("=" * 80)
    print()
    
    # Load all result files
    all_results = {}
    
    # Cloud models (try full results first, fallback to summary)
    cloud_models = {
        'Claude Sonnet 4.5': ('claude_extract_results_full.json', 'claude_extract_results.json'),
        'GPT-4o': ('gpt4o_extract_results_full.json', 'gpt4o_extract_results.json'),
    }
    
    # LMStudio models
    lmstudio_files = glob.glob('lmstudio_extract_*.json')
    
    # Load cloud model results
    for model_name, (full_file, summary_file) in cloud_models.items():
        # Try full results first, fallback to summary
        results = load_results_file(full_file)
        if not results:
            results = load_results_file(summary_file)
        if results:
            all_results[model_name] = results
    
    # Load LMStudio model results
    for filepath in lmstudio_files:
        model_name = os.path.basename(filepath).replace('lmstudio_extract_', '').replace('.json', '')
        results = load_results_file(filepath)
        if results:
            all_results[f"LMStudio: {model_name}"] = results
    
    if not all_results:
        print("❌ No result files found!")
        return
    
    print(f"Found {len(all_results)} model result files\n")
    
    # Analyze each model
    analyses = {}
    for model_name, results in all_results.items():
        analyses[model_name] = analyze_model_results(model_name, results)
    
    # Print summary table
    print("=" * 80)
    print("SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Model':<40} {'Articles':<12} {'JSON Valid %':<15} {'Avg Count':<12} {'Total Count':<12}")
    print("-" * 80)
    
    for model_name in sorted(analyses.keys()):
        analysis = analyses[model_name]
        articles = f"{analysis['articles_complete']}/{analysis['articles_tested']}"
        json_rate = f"{analysis['json_valid_rate']:.1f}%"
        avg_count = f"{analysis['count_stats']['mean']:.1f}" if analysis['count_stats'] else "N/A"
        total_count = f"{analysis['count_stats']['total']}" if analysis['count_stats'] else "N/A"
        
        print(f"{model_name:<40} {articles:<12} {json_rate:<15} {avg_count:<12} {total_count:<12}")
    
    print()
    
    # Per-article comparison
    print("=" * 80)
    print("PER-ARTICLE COMPARISON")
    print("=" * 80)
    print(f"{'Article':<10}", end="")
    for model_name in sorted(analyses.keys()):
        print(f"{model_name[:20]:<22}", end="")
    print()
    print("-" * 80)
    
    for article_id in sorted(ARTICLE_IDS):
        print(f"{article_id:<10}", end="")
        for model_name in sorted(analyses.keys()):
            analysis = analyses[model_name]
            count = analysis['counts'].get(article_id, 'N/A')
            if count == 'N/A':
                print(f"{'N/A':<22}", end="")
            else:
                print(f"{count:<22}", end="")
        print()
    
    print()
    
    # JSON validity details
    print("=" * 80)
    print("JSON VALIDITY DETAILS")
    print("=" * 80)
    for model_name in sorted(analyses.keys()):
        analysis = analyses[model_name]
        print(f"\n{model_name}:")
        print(f"  Valid: {len(analysis['json_valid_articles'])} articles")
        if analysis['json_invalid_articles']:
            print(f"  Invalid: {analysis['json_invalid_articles']}")
        if analysis['errors']:
            print(f"  Errors: {len(analysis['errors'])}")
            for error in analysis['errors'][:3]:  # Show first 3
                print(f"    - {error}")
    
    print()
    
    # Count statistics
    print("=" * 80)
    print("COUNT STATISTICS")
    print("=" * 80)
    for model_name in sorted(analyses.keys()):
        analysis = analyses[model_name]
        if analysis['count_stats']:
            stats = analysis['count_stats']
            print(f"\n{model_name}:")
            print(f"  Min: {stats['min']}, Max: {stats['max']}, Mean: {stats['mean']:.2f}, Median: {stats['median']:.2f}")
            if 'stdev' in stats:
                print(f"  StdDev: {stats['stdev']:.2f}, Total: {stats['total']}")
    
    print()
    
    # Model comparison insights
    print("=" * 80)
    print("INSIGHTS")
    print("=" * 80)
    
    # Find models with complete data
    complete_models = [m for m, a in analyses.items() if a['articles_complete'] == 6]
    if complete_models:
        print(f"\n✅ Complete models (6/6 articles): {', '.join(complete_models)}")
    
    # Find highest/lowest counts
    if complete_models:
        model_totals = {}
        for model_name in complete_models:
            if analyses[model_name]['count_stats']:
                model_totals[model_name] = analyses[model_name]['count_stats']['total']
        
        if model_totals:
            highest = max(model_totals.items(), key=lambda x: x[1])
            lowest = min(model_totals.items(), key=lambda x: x[1])
            print(f"\n📊 Highest total count: {highest[0]} ({highest[1]} observables)")
            print(f"📊 Lowest total count: {lowest[0]} ({lowest[1]} observables)")
            print(f"📊 Range: {highest[1] - lowest[1]} observables difference")
    
    # JSON validity comparison
    json_rates = {m: a['json_valid_rate'] for m, a in analyses.items() if a['articles_tested'] > 0}
    if json_rates:
        best_json = max(json_rates.items(), key=lambda x: x[1])
        print(f"\n✅ Best JSON validity: {best_json[0]} ({best_json[1]:.1f}%)")
    
    # Consistency (lower stdev = more consistent)
    consistent_models = []
    for model_name, analysis in analyses.items():
        if analysis['count_stats'] and 'stdev' in analysis['count_stats']:
            if analysis['count_stats']['stdev'] < 5.0:  # Low variance
                consistent_models.append((model_name, analysis['count_stats']['stdev']))
    
    if consistent_models:
        consistent_models.sort(key=lambda x: x[1])
        print(f"\n📈 Most consistent models (lowest std dev):")
        for model_name, stdev in consistent_models[:3]:
            print(f"   {model_name}: {stdev:.2f}")
    
    print()

if __name__ == "__main__":
    main()

