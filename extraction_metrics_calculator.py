#!/usr/bin/env python3
"""
Calculate quantitative metrics for three-model extraction comparison.
Provides measurable KPIs for model performance, agreement, and quality.
"""

import json
from collections import defaultdict
from typing import Dict, List, Tuple

def load_results(filename: str) -> dict:
    """Load results from JSON file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def normalize_observable(obs_value: str) -> str:
    """Normalize observable for comparison."""
    import re
    normalized = re.sub(r'<[^>]+>', '<placeholder>', obs_value)
    normalized = re.sub(r'\[REMOVED\]', '<removed>', normalized)
    normalized = ' '.join(normalized.split()).lower()
    return normalized

def similarity_score(str1: str, str2: str) -> float:
    """Calculate similarity between two strings."""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, normalize_observable(str1), normalize_observable(str2)).ratio()

def find_matches(target_obs: List[dict], candidate_obs: List[dict], threshold: float = 0.7) -> List[Tuple[dict, dict, float]]:
    """Find matching observables between two lists."""
    matches = []
    for t_obs in target_obs:
        t_value = t_obs.get('value', '')
        best_match = None
        best_score = 0
        for c_obs in candidate_obs:
            c_value = c_obs.get('value', '')
            score = similarity_score(t_value, c_value)
            if score > best_score and score >= threshold:
                best_score = score
                best_match = c_obs
        if best_match:
            matches.append((t_obs, best_match, best_score))
    return matches

def calculate_metrics():
    """Calculate all metrics for the three-model comparison."""
    
    # Load results
    sonnet_file = "claude-sonnet-4-5_extract_results_full_2025-11-10_16-21-13.json"
    gpt4o_file = "gpt4o_extract_results_full_2025-11-10_16-01-32.json"
    gpt4o_mini_file = "gpt4o-mini_extract_results_full_2025-11-10_16-02-49.json"
    
    sonnet_results = load_results(sonnet_file)
    gpt4o_results = load_results(gpt4o_file)
    gpt4o_mini_results = load_results(gpt4o_mini_file)
    
    article_ids = ['1794', '1860', '1866', '1909', '1937', '1974']
    
    metrics = {
        'coverage_metrics': {},
        'agreement_metrics': {},
        'quality_metrics': {},
        'confidence_metrics': {},
        'efficiency_metrics': {}
    }
    
    # Coverage Metrics
    total_sonnet = sum(len(sonnet_results.get(aid, {}).get('observables', [])) for aid in article_ids)
    total_gpt4o = sum(len(gpt4o_results.get(aid, {}).get('observables', [])) for aid in article_ids)
    total_gpt4o_mini = sum(len(gpt4o_mini_results.get(aid, {}).get('observables', [])) for aid in article_ids)
    
    metrics['coverage_metrics'] = {
        'total_extractions': {
            'sonnet': total_sonnet,
            'gpt4o': total_gpt4o,
            'gpt4o_mini': total_gpt4o_mini
        },
        'avg_per_article': {
            'sonnet': total_sonnet / len(article_ids),
            'gpt4o': total_gpt4o / len(article_ids),
            'gpt4o_mini': total_gpt4o_mini / len(article_ids)
        },
        'coverage_ratio': {
            'gpt4o_vs_sonnet': total_gpt4o / total_sonnet if total_sonnet > 0 else 0,
            'gpt4o_mini_vs_sonnet': total_gpt4o_mini / total_sonnet if total_sonnet > 0 else 0,
            'gpt4o_mini_vs_gpt4o': total_gpt4o_mini / total_gpt4o if total_gpt4o > 0 else 0
        },
        'extraction_rate': {
            'sonnet': total_sonnet / len(article_ids),
            'gpt4o': total_gpt4o / len(article_ids),
            'gpt4o_mini': total_gpt4o_mini / len(article_ids)
        }
    }
    
    # Agreement Metrics
    all_three_matches = 0
    sonnet_gpt4o_matches = 0
    sonnet_mini_matches = 0
    gpt4o_mini_matches = 0
    
    sonnet_unique = 0
    gpt4o_unique = 0
    gpt4o_mini_unique = 0
    
    per_article_agreement = {}
    
    for article_id in article_ids:
        sonnet_obs = sonnet_results.get(article_id, {}).get('observables', [])
        gpt4o_obs = gpt4o_results.get(article_id, {}).get('observables', [])
        gpt4o_mini_obs = gpt4o_mini_results.get(article_id, {}).get('observables', [])
        
        # Find all three matches
        all_three_count = 0
        for s_obs in sonnet_obs:
            s_value = s_obs.get('value', '')
            gpt4o_match = None
            mini_match = None
            
            for g_obs in gpt4o_obs:
                if similarity_score(s_value, g_obs.get('value', '')) >= 0.7:
                    gpt4o_match = g_obs
                    break
            
            for m_obs in gpt4o_mini_obs:
                if similarity_score(s_value, m_obs.get('value', '')) >= 0.7:
                    mini_match = m_obs
                    break
            
            if gpt4o_match and mini_match:
                all_three_count += 1
            elif gpt4o_match:
                sonnet_gpt4o_matches += 1
            elif mini_match:
                sonnet_mini_matches += 1
        
        # Find GPT-4o + GPT-4o-mini matches (not in Sonnet)
        for g_obs in gpt4o_obs:
            g_value = g_obs.get('value', '')
            found_in_sonnet = any(similarity_score(g_value, s_obs.get('value', '')) >= 0.7 for s_obs in sonnet_obs)
            found_in_mini = any(similarity_score(g_value, m_obs.get('value', '')) >= 0.7 for m_obs in gpt4o_mini_obs)
            
            if found_in_mini and not found_in_sonnet:
                gpt4o_mini_matches += 1
        
        # Count unique
        for s_obs in sonnet_obs:
            s_value = s_obs.get('value', '')
            found_in_others = False
            for g_obs in gpt4o_obs:
                if similarity_score(s_value, g_obs.get('value', '')) >= 0.7:
                    found_in_others = True
                    break
            if not found_in_others:
                for m_obs in gpt4o_mini_obs:
                    if similarity_score(s_value, m_obs.get('value', '')) >= 0.7:
                        found_in_others = True
                        break
            if not found_in_others:
                sonnet_unique += 1
        
        for g_obs in gpt4o_obs:
            g_value = g_obs.get('value', '')
            found_in_others = False
            for s_obs in sonnet_obs:
                if similarity_score(g_value, s_obs.get('value', '')) >= 0.7:
                    found_in_others = True
                    break
            if not found_in_others:
                for m_obs in gpt4o_mini_obs:
                    if similarity_score(g_value, m_obs.get('value', '')) >= 0.7:
                        found_in_others = True
                        break
            if not found_in_others:
                gpt4o_unique += 1
        
        for m_obs in gpt4o_mini_obs:
            m_value = m_obs.get('value', '')
            found_in_others = False
            for s_obs in sonnet_obs:
                if similarity_score(m_value, s_obs.get('value', '')) >= 0.7:
                    found_in_others = True
                    break
            if not found_in_others:
                for g_obs in gpt4o_obs:
                    if similarity_score(m_value, g_obs.get('value', '')) >= 0.7:
                        found_in_others = True
                        break
                if not found_in_others:
                    gpt4o_mini_unique += 1
        
        total_obs = len(sonnet_obs) + len(gpt4o_obs) + len(gpt4o_mini_obs)
        avg_obs = total_obs / 3
        agreement_pct = (all_three_count / avg_obs * 100) if avg_obs > 0 else 0
        
        per_article_agreement[article_id] = {
            'all_three_count': all_three_count,
            'agreement_percentage': agreement_pct,
            'sonnet_count': len(sonnet_obs),
            'gpt4o_count': len(gpt4o_obs),
            'gpt4o_mini_count': len(gpt4o_mini_obs)
        }
        
        all_three_matches += all_three_count
    
    total_unique = sonnet_unique + gpt4o_unique + gpt4o_mini_unique
    total_observables = total_sonnet + total_gpt4o + total_gpt4o_mini
    
    metrics['agreement_metrics'] = {
        'all_three_agreement': {
            'count': all_three_matches,
            'percentage_of_total': (all_three_matches / total_observables * 100) if total_observables > 0 else 0,
            'percentage_of_avg': (all_three_matches / (total_observables / 3) * 100) if total_observables > 0 else 0
        },
        'two_model_agreements': {
            'sonnet_gpt4o': sonnet_gpt4o_matches,
            'sonnet_gpt4o_mini': sonnet_mini_matches,
            'gpt4o_gpt4o_mini': gpt4o_mini_matches,
            'total_two_model': sonnet_gpt4o_matches + sonnet_mini_matches + gpt4o_mini_matches
        },
        'unique_extractions': {
            'sonnet_unique': sonnet_unique,
            'gpt4o_unique': gpt4o_unique,
            'gpt4o_mini_unique': gpt4o_mini_unique,
            'total_unique': total_unique,
            'unique_percentage': (total_unique / total_observables * 100) if total_observables > 0 else 0
        },
        'consensus_strength': {
            'high_confidence': all_three_matches,  # All three agree
            'medium_confidence': sonnet_gpt4o_matches + sonnet_mini_matches + gpt4o_mini_matches,  # Two agree
            'low_confidence': total_unique,  # Only one model
            'high_confidence_pct': (all_three_matches / total_observables * 100) if total_observables > 0 else 0,
            'medium_confidence_pct': ((sonnet_gpt4o_matches + sonnet_mini_matches + gpt4o_mini_matches) / total_observables * 100) if total_observables > 0 else 0,
            'low_confidence_pct': (total_unique / total_observables * 100) if total_observables > 0 else 0
        },
        'per_article_agreement': per_article_agreement
    }
    
    # Quality Metrics
    observable_types = defaultdict(lambda: {'sonnet': 0, 'gpt4o': 0, 'gpt4o_mini': 0})
    techniques = defaultdict(lambda: {'sonnet': 0, 'gpt4o': 0, 'gpt4o_mini': 0})
    
    for article_id in article_ids:
        for model_name, results in [('sonnet', sonnet_results), ('gpt4o', gpt4o_results), ('gpt4o_mini', gpt4o_mini_results)]:
            obs_list = results.get(article_id, {}).get('observables', [])
            for obs in obs_list:
                obs_type = obs.get('type', 'unknown')
                observable_types[obs_type][model_name] += 1
                
                # Detect techniques from value
                value = obs.get('value', '').lower()
                if '→' in obs.get('value', '') or '->' in obs.get('value', ''):
                    techniques['process_chain'][model_name] += 1
                if 'reg' in value and ('add' in value or 'save' in value):
                    techniques['registry_modification'][model_name] += 1
                if 'schtasks' in value or 'scheduled' in value:
                    techniques['scheduled_task'][model_name] += 1
                if 'powershell' in value and ('-enc' in value or 'encoded' in value or 'base64' in value):
                    techniques['encoded_powershell'][model_name] += 1
    
    metrics['quality_metrics'] = {
        'observable_type_diversity': {
            'sonnet': len([t for t in observable_types if observable_types[t]['sonnet'] > 0]),
            'gpt4o': len([t for t in observable_types if observable_types[t]['gpt4o'] > 0]),
            'gpt4o_mini': len([t for t in observable_types if observable_types[t]['gpt4o_mini'] > 0])
        },
        'technique_detection': dict(techniques),
        'type_distribution': {k: dict(v) for k, v in observable_types.items()}
    }
    
    # Confidence Metrics
    metrics['confidence_metrics'] = {
        'multi_model_consensus_rate': {
            'three_model': (all_three_matches / total_observables * 100) if total_observables > 0 else 0,
            'two_model': ((sonnet_gpt4o_matches + sonnet_mini_matches + gpt4o_mini_matches) / total_observables * 100) if total_observables > 0 else 0,
            'any_consensus': ((all_three_matches + sonnet_gpt4o_matches + sonnet_mini_matches + gpt4o_mini_matches) / total_observables * 100) if total_observables > 0 else 0
        },
        'single_model_only_rate': {
            'sonnet_only': (sonnet_unique / total_observables * 100) if total_observables > 0 else 0,
            'gpt4o_only': (gpt4o_unique / total_observables * 100) if total_observables > 0 else 0,
            'gpt4o_mini_only': (gpt4o_mini_unique / total_observables * 100) if total_observables > 0 else 0,
            'total_single_model': (total_unique / total_observables * 100) if total_observables > 0 else 0
        },
        'high_confidence_detection_rate': (all_three_matches / total_observables * 100) if total_observables > 0 else 0
    }
    
    # Efficiency Metrics (placeholder - would need cost/time data)
    metrics['efficiency_metrics'] = {
        'extraction_efficiency': {
            'sonnet_obs_per_article': total_sonnet / len(article_ids),
            'gpt4o_obs_per_article': total_gpt4o / len(article_ids),
            'gpt4o_mini_obs_per_article': total_gpt4o_mini / len(article_ids)
        },
        'note': 'Cost and time metrics require additional data (API costs, processing time)'
    }
    
    return metrics

def print_metrics_report(metrics: dict):
    """Print a formatted metrics report."""
    print("=" * 80)
    print("THREE-MODEL EXTRACTION METRICS REPORT")
    print("=" * 80)
    print()
    
    # Coverage Metrics
    print("COVERAGE METRICS")
    print("-" * 80)
    cov = metrics['coverage_metrics']
    print(f"Total Extractions:")
    print(f"  Sonnet 4.5:     {cov['total_extractions']['sonnet']:3d} observables")
    print(f"  GPT-4o:         {cov['total_extractions']['gpt4o']:3d} observables")
    print(f"  GPT-4o-mini:   {cov['total_extractions']['gpt4o_mini']:3d} observables")
    print()
    print(f"Average per Article:")
    print(f"  Sonnet 4.5:     {cov['avg_per_article']['sonnet']:.1f} observables/article")
    print(f"  GPT-4o:         {cov['avg_per_article']['gpt4o']:.1f} observables/article")
    print(f"  GPT-4o-mini:   {cov['avg_per_article']['gpt4o_mini']:.1f} observables/article")
    print()
    print(f"Coverage Ratio (vs Sonnet baseline):")
    print(f"  GPT-4o:         {cov['coverage_ratio']['gpt4o_vs_sonnet']:.1%}")
    print(f"  GPT-4o-mini:   {cov['coverage_ratio']['gpt4o_mini_vs_sonnet']:.1%}")
    print(f"  GPT-4o-mini vs GPT-4o: {cov['coverage_ratio']['gpt4o_mini_vs_gpt4o']:.1%}")
    print()
    
    # Agreement Metrics
    print("AGREEMENT METRICS")
    print("-" * 80)
    agree = metrics['agreement_metrics']
    print(f"All Three Models Agree:")
    print(f"  Count:          {agree['all_three_agreement']['count']:3d} observables")
    print(f"  % of Total:     {agree['all_three_agreement']['percentage_of_total']:.1f}%")
    print(f"  % of Average:   {agree['all_three_agreement']['percentage_of_avg']:.1f}%")
    print()
    print(f"Two-Model Agreements:")
    print(f"  Sonnet + GPT-4o:        {agree['two_model_agreements']['sonnet_gpt4o']:3d}")
    print(f"  Sonnet + GPT-4o-mini:   {agree['two_model_agreements']['sonnet_gpt4o_mini']:3d}")
    print(f"  GPT-4o + GPT-4o-mini:   {agree['two_model_agreements']['gpt4o_gpt4o_mini']:3d}")
    print(f"  Total Two-Model:        {agree['two_model_agreements']['total_two_model']:3d}")
    print()
    print(f"Unique Extractions (Single Model Only):")
    print(f"  Sonnet-only:    {agree['unique_extractions']['sonnet_unique']:3d}")
    print(f"  GPT-4o-only:    {agree['unique_extractions']['gpt4o_unique']:3d}")
    print(f"  GPT-4o-mini-only: {agree['unique_extractions']['gpt4o_mini_unique']:3d}")
    print(f"  Total Unique:   {agree['unique_extractions']['total_unique']:3d} ({agree['unique_extractions']['unique_percentage']:.1f}%)")
    print()
    print(f"Consensus Strength:")
    print(f"  High Confidence (3 models):   {agree['consensus_strength']['high_confidence']:3d} ({agree['consensus_strength']['high_confidence_pct']:.1f}%)")
    print(f"  Medium Confidence (2 models):  {agree['consensus_strength']['medium_confidence']:3d} ({agree['consensus_strength']['medium_confidence_pct']:.1f}%)")
    print(f"  Low Confidence (1 model):     {agree['consensus_strength']['low_confidence']:3d} ({agree['consensus_strength']['low_confidence_pct']:.1f}%)")
    print()
    print(f"Per-Article Agreement:")
    for article_id, data in agree['per_article_agreement'].items():
        print(f"  Article {article_id}: {data['all_three_count']:2d} common ({data['agreement_percentage']:.1f}%) - "
              f"Sonnet:{data['sonnet_count']:2d} GPT-4o:{data['gpt4o_count']:2d} Mini:{data['gpt4o_mini_count']:2d}")
    print()
    
    # Quality Metrics
    print("QUALITY METRICS")
    print("-" * 80)
    qual = metrics['quality_metrics']
    print(f"Observable Type Diversity:")
    print(f"  Sonnet 4.5:     {qual['observable_type_diversity']['sonnet']} unique types")
    print(f"  GPT-4o:         {qual['observable_type_diversity']['gpt4o']} unique types")
    print(f"  GPT-4o-mini:   {qual['observable_type_diversity']['gpt4o_mini']} unique types")
    print()
    print(f"Technique Detection:")
    for tech, counts in qual['technique_detection'].items():
        print(f"  {tech}:")
        print(f"    Sonnet: {counts['sonnet']:3d}, GPT-4o: {counts['gpt4o']:3d}, GPT-4o-mini: {counts['gpt4o_mini']:3d}")
    print()
    
    # Confidence Metrics
    print("CONFIDENCE METRICS")
    print("-" * 80)
    conf = metrics['confidence_metrics']
    print(f"Multi-Model Consensus Rate:")
    print(f"  Three-Model Consensus:  {conf['multi_model_consensus_rate']['three_model']:.1f}%")
    print(f"  Two-Model Consensus:   {conf['multi_model_consensus_rate']['two_model']:.1f}%")
    print(f"  Any Consensus:         {conf['multi_model_consensus_rate']['any_consensus']:.1f}%")
    print()
    print(f"Single-Model-Only Rate:")
    print(f"  Sonnet-only:    {conf['single_model_only_rate']['sonnet_only']:.1f}%")
    print(f"  GPT-4o-only:    {conf['single_model_only_rate']['gpt4o_only']:.1f}%")
    print(f"  GPT-4o-mini-only: {conf['single_model_only_rate']['gpt4o_mini_only']:.1f}%")
    print(f"  Total Single-Model: {conf['single_model_only_rate']['total_single_model']:.1f}%")
    print()
    print(f"High-Confidence Detection Rate: {conf['high_confidence_detection_rate']:.1f}%")
    print()
    
    # Efficiency Metrics
    print("EFFICIENCY METRICS")
    print("-" * 80)
    eff = metrics['efficiency_metrics']
    print(f"Extraction Efficiency:")
    print(f"  Sonnet 4.5:     {eff['extraction_efficiency']['sonnet_obs_per_article']:.1f} obs/article")
    print(f"  GPT-4o:         {eff['extraction_efficiency']['gpt4o_obs_per_article']:.1f} obs/article")
    print(f"  GPT-4o-mini:   {eff['extraction_efficiency']['gpt4o_mini_obs_per_article']:.1f} obs/article")
    print()
    print(f"Note: {eff['note']}")
    print()

if __name__ == '__main__':
    metrics = calculate_metrics()
    print_metrics_report(metrics)
    
    # Save to JSON
    with open('extraction_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)
    print("Metrics saved to: extraction_metrics.json")

