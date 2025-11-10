#!/usr/bin/env python3
"""
Compare observables extracted by Claude Sonnet 4.5, GPT-4o, and GPT-4o-mini
across all 6 benchmark articles to identify:
1. Where all three find the same information
2. How they convert it to similar logic
3. Differences in their approaches
"""

import json
import sys
from collections import defaultdict
from difflib import SequenceMatcher
import re

def normalize_observable(obs_value: str) -> str:
    """Normalize observable value for comparison."""
    # Remove placeholders
    normalized = re.sub(r'<[^>]+>', '<placeholder>', obs_value)
    normalized = re.sub(r'\[REMOVED\]', '<removed>', normalized)
    # Normalize whitespace
    normalized = ' '.join(normalized.split())
    # Lowercase for comparison
    return normalized.lower()

def extract_key_elements(obs_value: str) -> dict:
    """Extract key elements from an observable."""
    elements = {
        'commands': [],
        'paths': [],
        'processes': [],
        'registry_keys': [],
        'file_extensions': []
    }
    
    # Extract commands (common Windows commands)
    commands = ['powershell', 'cmd', 'whoami', 'systeminfo', 'tasklist', 'net', 
                'reg', 'schtasks', 'wscript', 'msbuild', 'rundll32', 'curl',
                'rdrleakdiag', 'vssadmin', 'nltest', 'sc', 'mshta', 'msiexec']
    for cmd in commands:
        if cmd in obs_value.lower():
            elements['commands'].append(cmd)
    
    # Extract paths (Windows-style paths)
    path_pattern = r'[A-Z]:\\[^\\s]+|%[A-Z_]+%|CSIDL_[A-Z_]+'
    paths = re.findall(path_pattern, obs_value, re.IGNORECASE)
    elements['paths'] = paths
    
    # Extract processes (.exe files)
    processes = re.findall(r'(\w+\.exe)', obs_value, re.IGNORECASE)
    elements['processes'] = list(set(processes))
    
    # Extract registry keys
    reg_keys = re.findall(r'(HKCU|HKLM|HKEY_[A-Z_]+)\\[^\\s]+', obs_value, re.IGNORECASE)
    elements['registry_keys'] = reg_keys
    
    # Extract file extensions
    extensions = re.findall(r'\.([a-z0-9]+)', obs_value, re.IGNORECASE)
    elements['file_extensions'] = list(set(extensions))
    
    return elements

def similarity_score(str1: str, str2: str) -> float:
    """Calculate similarity between two strings."""
    return SequenceMatcher(None, normalize_observable(str1), normalize_observable(str2)).ratio()

def load_results(filename: str) -> dict:
    """Load results from JSON file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {filename} not found")
        return {}

def main():
    # Load results from all three models
    # Note: Using the most recent timestamped files
    # For Sonnet, we'll use the original file which has the first run results
    # (The second run had API key issues, but we can compare with first run data)
    sonnet_file = "claude_extract_results_full.json"  # Original file (first run - 125 total observables)
    gpt4o_file = "gpt4o_extract_results_full_2025-11-10_16-01-32.json"
    gpt4o_mini_file = "gpt4o-mini_extract_results_full_2025-11-10_16-02-49.json"
    
    sonnet_results = load_results(sonnet_file)
    gpt4o_results = load_results(gpt4o_file)
    gpt4o_mini_results = load_results(gpt4o_mini_file)
    
    article_ids = ['1794', '1860', '1866', '1909', '1937', '1974']
    
    print("=" * 100)
    print("THREE-MODEL EXTRACTION COMPARISON ANALYSIS")
    print("=" * 100)
    print()
    
    # Overall statistics
    total_sonnet = sum(len(sonnet_results.get(aid, {}).get('observables', [])) for aid in article_ids)
    total_gpt4o = sum(len(gpt4o_results.get(aid, {}).get('observables', [])) for aid in article_ids)
    total_gpt4o_mini = sum(len(gpt4o_mini_results.get(aid, {}).get('observables', [])) for aid in article_ids)
    
    print("OVERALL STATISTICS")
    print("-" * 100)
    print(f"Claude Sonnet 4.5: {total_sonnet} total observables")
    print(f"GPT-4o:            {total_gpt4o} total observables")
    print(f"GPT-4o-mini:       {total_gpt4o_mini} total observables")
    print()
    
    # Per-article analysis
    all_matches = defaultdict(list)  # article_id -> list of matched observables
    all_unique = defaultdict(lambda: {'sonnet': [], 'gpt4o': [], 'gpt4o_mini': []})
    
    for article_id in article_ids:
        print("=" * 100)
        print(f"ARTICLE {article_id}")
        print("=" * 100)
        
        sonnet_obs = sonnet_results.get(article_id, {}).get('observables', [])
        gpt4o_obs = gpt4o_results.get(article_id, {}).get('observables', [])
        gpt4o_mini_obs = gpt4o_mini_results.get(article_id, {}).get('observables', [])
        
        sonnet_title = sonnet_results.get(article_id, {}).get('title', 'N/A')
        print(f"Title: {sonnet_title}")
        print()
        print(f"Counts: Sonnet={len(sonnet_obs)}, GPT-4o={len(gpt4o_obs)}, GPT-4o-mini={len(gpt4o_mini_obs)}")
        print()
        
        # Find matches across all three
        print("OBSERVABLES FOUND BY ALL THREE MODELS:")
        print("-" * 100)
        matches_found = 0
        
        for s_obs in sonnet_obs:
            s_value = s_obs.get('value', '')
            s_normalized = normalize_observable(s_value)
            
            # Check GPT-4o
            gpt4o_match = None
            best_gpt4o_score = 0
            for g_obs in gpt4o_obs:
                g_value = g_obs.get('value', '')
                g_normalized = normalize_observable(g_value)
                score = similarity_score(s_value, g_value)
                if score > best_gpt4o_score and score > 0.7:  # 70% similarity threshold
                    best_gpt4o_score = score
                    gpt4o_match = g_obs
            
            # Check GPT-4o-mini
            gpt4o_mini_match = None
            best_mini_score = 0
            for m_obs in gpt4o_mini_obs:
                m_value = m_obs.get('value', '')
                m_normalized = normalize_observable(m_value)
                score = similarity_score(s_value, m_value)
                if score > best_mini_score and score > 0.7:
                    best_mini_score = score
                    gpt4o_mini_match = m_obs
            
            # If found in all three
            if gpt4o_match and gpt4o_mini_match:
                matches_found += 1
                print(f"\n[{matches_found}] ALL THREE MODELS FOUND:")
                print(f"  Sonnet:      {s_value[:80]}...")
                print(f"  GPT-4o:      {gpt4o_match.get('value', '')[:80]}...")
                print(f"  GPT-4o-mini: {gpt4o_mini_match.get('value', '')[:80]}...")
                print(f"  Similarity:  Sonnet↔GPT-4o={best_gpt4o_score:.2f}, Sonnet↔Mini={best_mini_score:.2f}")
                
                # Extract key elements
                s_elements = extract_key_elements(s_value)
                g_elements = extract_key_elements(gpt4o_match.get('value', ''))
                m_elements = extract_key_elements(gpt4o_mini_match.get('value', ''))
                
                common_commands = set(s_elements['commands']) & set(g_elements['commands']) & set(m_elements['commands'])
                if common_commands:
                    print(f"  Common Commands: {', '.join(sorted(common_commands))}")
                
                all_matches[article_id].append({
                    'sonnet': s_obs,
                    'gpt4o': gpt4o_match,
                    'gpt4o_mini': gpt4o_mini_match,
                    'similarity_scores': {'sonnet_gpt4o': best_gpt4o_score, 'sonnet_mini': best_mini_score}
                })
        
        if matches_found == 0:
            print("  (No observables found by all three models)")
        
        print()
        print("UNIQUE TO EACH MODEL:")
        print("-" * 100)
        
        # Find unique to Sonnet
        sonnet_unique = []
        for s_obs in sonnet_obs:
            s_value = s_obs.get('value', '')
            found_in_others = False
            for g_obs in gpt4o_obs:
                if similarity_score(s_value, g_obs.get('value', '')) > 0.7:
                    found_in_others = True
                    break
            if not found_in_others:
                for m_obs in gpt4o_mini_obs:
                    if similarity_score(s_value, m_obs.get('value', '')) > 0.7:
                        found_in_others = True
                        break
            if not found_in_others:
                sonnet_unique.append(s_obs)
        
        # Find unique to GPT-4o
        gpt4o_unique = []
        for g_obs in gpt4o_obs:
            g_value = g_obs.get('value', '')
            found_in_others = False
            for s_obs in sonnet_obs:
                if similarity_score(g_value, s_obs.get('value', '')) > 0.7:
                    found_in_others = True
                    break
            if not found_in_others:
                for m_obs in gpt4o_mini_obs:
                    if similarity_score(g_value, m_obs.get('value', '')) > 0.7:
                        found_in_others = True
                        break
            if not found_in_others:
                gpt4o_unique.append(g_obs)
        
        # Find unique to GPT-4o-mini
        gpt4o_mini_unique = []
        for m_obs in gpt4o_mini_obs:
            m_value = m_obs.get('value', '')
            found_in_others = False
            for s_obs in sonnet_obs:
                if similarity_score(m_value, s_obs.get('value', '')) > 0.7:
                    found_in_others = True
                    break
            if not found_in_others:
                for g_obs in gpt4o_obs:
                    if similarity_score(m_value, g_obs.get('value', '')) > 0.7:
                        found_in_others = True
                        break
            if not found_in_others:
                gpt4o_mini_unique.append(m_obs)
        
        print(f"  Sonnet-only ({len(sonnet_unique)}):")
        for obs in sonnet_unique[:5]:  # Show first 5
            print(f"    - {obs.get('value', '')[:70]}...")
        if len(sonnet_unique) > 5:
            print(f"    ... and {len(sonnet_unique) - 5} more")
        
        print(f"  GPT-4o-only ({len(gpt4o_unique)}):")
        for obs in gpt4o_unique[:5]:
            print(f"    - {obs.get('value', '')[:70]}...")
        if len(gpt4o_unique) > 5:
            print(f"    ... and {len(gpt4o_unique) - 5} more")
        
        print(f"  GPT-4o-mini-only ({len(gpt4o_mini_unique)}):")
        for obs in gpt4o_mini_unique[:5]:
            print(f"    - {obs.get('value', '')[:70]}...")
        if len(gpt4o_mini_unique) > 5:
            print(f"    ... and {len(gpt4o_mini_unique) - 5} more")
        
        all_unique[article_id] = {
            'sonnet': sonnet_unique,
            'gpt4o': gpt4o_unique,
            'gpt4o_mini': gpt4o_mini_unique
        }
        
        print()
    
    # Summary
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    total_matches = sum(len(matches) for matches in all_matches.values())
    print(f"Total observables found by all three models: {total_matches}")
    print()
    
    print("CONSISTENCY ANALYSIS:")
    print("-" * 100)
    for article_id in article_ids:
        matches = len(all_matches[article_id])
        sonnet_count = len(sonnet_results.get(article_id, {}).get('observables', []))
        gpt4o_count = len(gpt4o_results.get(article_id, {}).get('observables', []))
        gpt4o_mini_count = len(gpt4o_mini_results.get(article_id, {}).get('observables', []))
        avg_count = (sonnet_count + gpt4o_count + gpt4o_mini_count) / 3
        
        consistency = (matches / avg_count * 100) if avg_count > 0 else 0
        print(f"Article {article_id}: {matches} common observables ({consistency:.1f}% consistency)")
    
    print()
    print("PATTERN ANALYSIS:")
    print("-" * 100)
    # Analyze common patterns
    all_common_commands = defaultdict(int)
    for article_id, matches in all_matches.items():
        for match in matches:
            s_value = match['sonnet'].get('value', '')
            elements = extract_key_elements(s_value)
            for cmd in elements['commands']:
                all_common_commands[cmd] += 1
    
    print("Most commonly extracted commands (found by all three):")
    for cmd, count in sorted(all_common_commands.items(), key=lambda x: -x[1])[:10]:
        print(f"  {cmd}: {count} times")
    
    print()
    print("Analysis complete!")

if __name__ == '__main__':
    main()

