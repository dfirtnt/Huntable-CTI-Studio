#!/usr/bin/env python3
"""
Comprehensive three-way comparison: Claude Sonnet 4.5, GPT-4o, and GPT-4o-mini
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
    normalized = re.sub(r'<domain>', '<placeholder>', normalized)
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
        'file_extensions': [],
        'techniques': []
    }
    
    # Extract commands (common Windows commands)
    commands = ['powershell', 'cmd', 'whoami', 'systeminfo', 'tasklist', 'net', 
                'reg', 'schtasks', 'wscript', 'msbuild', 'rundll32', 'curl',
                'rdrleakdiag', 'vssadmin', 'nltest', 'sc', 'mshta', 'msiexec',
                'w3wp', 'wsusservice', 'rdpclip']
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
    
    # Detect techniques
    if '→' in obs_value or '->' in obs_value:
        elements['techniques'].append('process_chain')
    if 'reg' in obs_value.lower() and ('add' in obs_value.lower() or 'save' in obs_value.lower()):
        elements['techniques'].append('registry_modification')
    if 'schtasks' in obs_value.lower() or 'scheduled' in obs_value.lower():
        elements['techniques'].append('scheduled_task')
    if 'powershell' in obs_value.lower() and ('-enc' in obs_value.lower() or 'encoded' in obs_value.lower() or 'base64' in obs_value.lower()):
        elements['techniques'].append('encoded_powershell')
    
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

def find_best_match(target_value: str, candidate_list: list, threshold: float = 0.7) -> tuple:
    """Find best matching observable from candidate list."""
    best_match = None
    best_score = 0
    for candidate in candidate_list:
        candidate_value = candidate.get('value', '')
        score = similarity_score(target_value, candidate_value)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate
    return best_match, best_score

def main():
    # Load results from all three models
    sonnet_file = "claude-sonnet-4-5_extract_results_full_2025-11-10_16-21-13.json"
    gpt4o_file = "gpt4o_extract_results_full_2025-11-10_16-01-32.json"
    gpt4o_mini_file = "gpt4o-mini_extract_results_full_2025-11-10_16-02-49.json"
    
    sonnet_results = load_results(sonnet_file)
    gpt4o_results = load_results(gpt4o_file)
    gpt4o_mini_results = load_results(gpt4o_mini_file)
    
    article_ids = ['1794', '1860', '1866', '1909', '1937', '1974']
    
    print("=" * 100)
    print("THREE-MODEL EXTRACTION COMPARISON ANALYSIS")
    print("Claude Sonnet 4.5 vs GPT-4o vs GPT-4o-mini")
    print("=" * 100)
    print()
    
    # Overall statistics
    total_sonnet = sum(len(sonnet_results.get(aid, {}).get('observables', [])) for aid in article_ids)
    total_gpt4o = sum(len(gpt4o_results.get(aid, {}).get('observables', [])) for aid in article_ids)
    total_gpt4o_mini = sum(len(gpt4o_mini_results.get(aid, {}).get('observables', [])) for aid in article_ids)
    
    print("OVERALL STATISTICS")
    print("-" * 100)
    print(f"Claude Sonnet 4.5: {total_sonnet} total observables")
    print(f"GPT-4o:             {total_gpt4o} total observables")
    print(f"GPT-4o-mini:       {total_gpt4o_mini} total observables")
    print()
    
    # Per-article analysis
    all_three_matches = defaultdict(list)  # Found by all three
    two_model_matches = defaultdict(lambda: {'sonnet_gpt4o': [], 'sonnet_mini': [], 'gpt4o_mini': []})
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
            
            # Check GPT-4o
            gpt4o_match, g4o_score = find_best_match(s_value, gpt4o_obs)
            
            # Check GPT-4o-mini
            mini_match, mini_score = find_best_match(s_value, gpt4o_mini_obs)
            
            # If found in all three
            if gpt4o_match and mini_match:
                matches_found += 1
                print(f"\n[{matches_found}] ALL THREE MODELS FOUND:")
                print(f"  Sonnet:      {s_value[:75]}...")
                print(f"  GPT-4o:      {gpt4o_match.get('value', '')[:75]}...")
                print(f"  GPT-4o-mini: {mini_match.get('value', '')[:75]}...")
                print(f"  Similarity:  Sonnet↔GPT-4o={g4o_score:.2f}, Sonnet↔Mini={mini_score:.2f}")
                
                # Extract key elements
                s_elements = extract_key_elements(s_value)
                g_elements = extract_key_elements(gpt4o_match.get('value', ''))
                m_elements = extract_key_elements(mini_match.get('value', ''))
                
                common_commands = set(s_elements['commands']) & set(g_elements['commands']) & set(m_elements['commands'])
                common_techniques = set(s_elements['techniques']) & set(g_elements['techniques']) & set(m_elements['techniques'])
                
                if common_commands:
                    print(f"  Common Commands: {', '.join(sorted(common_commands))}")
                if common_techniques:
                    print(f"  Common Techniques: {', '.join(sorted(common_techniques))}")
                
                all_three_matches[article_id].append({
                    'sonnet': s_obs,
                    'gpt4o': gpt4o_match,
                    'gpt4o_mini': mini_match,
                    'similarity_scores': {'sonnet_gpt4o': g4o_score, 'sonnet_mini': mini_score}
                })
        
        if matches_found == 0:
            print("  (No observables found by all three models)")
        
        print()
        print("OBSERVABLES FOUND BY TWO MODELS:")
        print("-" * 100)
        
        # Sonnet + GPT-4o (but not mini)
        sonnet_gpt4o_count = 0
        for s_obs in sonnet_obs:
            s_value = s_obs.get('value', '')
            gpt4o_match, _ = find_best_match(s_value, gpt4o_obs)
            mini_match, _ = find_best_match(s_value, gpt4o_mini_obs)
            if gpt4o_match and not mini_match:
                sonnet_gpt4o_count += 1
                if sonnet_gpt4o_count <= 3:  # Show first 3
                    print(f"  Sonnet+GPT-4o: {s_value[:70]}...")
        
        # Sonnet + GPT-4o-mini (but not GPT-4o)
        sonnet_mini_count = 0
        for s_obs in sonnet_obs:
            s_value = s_obs.get('value', '')
            gpt4o_match, _ = find_best_match(s_value, gpt4o_obs)
            mini_match, _ = find_best_match(s_value, gpt4o_mini_obs)
            if mini_match and not gpt4o_match:
                sonnet_mini_count += 1
                if sonnet_mini_count <= 3:
                    print(f"  Sonnet+GPT-4o-mini: {s_value[:70]}...")
        
        # GPT-4o + GPT-4o-mini (but not Sonnet)
        gpt4o_mini_count = 0
        for g4o_obs in gpt4o_obs:
            g4o_value = g4o_obs.get('value', '')
            sonnet_match, _ = find_best_match(g4o_value, sonnet_obs)
            mini_match, _ = find_best_match(g4o_value, gpt4o_mini_obs)
            if mini_match and not sonnet_match:
                gpt4o_mini_count += 1
                if gpt4o_mini_count <= 3:
                    print(f"  GPT-4o+GPT-4o-mini: {g4o_value[:70]}...")
        
        if sonnet_gpt4o_count == 0 and sonnet_mini_count == 0 and gpt4o_mini_count == 0:
            print("  (No observables found by exactly two models)")
        else:
            print(f"\n  Summary: Sonnet+GPT-4o={sonnet_gpt4o_count}, Sonnet+Mini={sonnet_mini_count}, GPT-4o+Mini={gpt4o_mini_count}")
        
        print()
        print("UNIQUE TO EACH MODEL:")
        print("-" * 100)
        
        # Find unique to each model
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
        for obs in sonnet_unique[:5]:
            obs_type = obs.get('type', 'N/A')
            value = obs.get('value', '')[:65]
            print(f"    [{obs_type}] {value}...")
        if len(sonnet_unique) > 5:
            print(f"    ... and {len(sonnet_unique) - 5} more")
        
        print(f"  GPT-4o-only ({len(gpt4o_unique)}):")
        for obs in gpt4o_unique[:5]:
            obs_type = obs.get('type', 'N/A')
            value = obs.get('value', '')[:65]
            print(f"    [{obs_type}] {value}...")
        if len(gpt4o_unique) > 5:
            print(f"    ... and {len(gpt4o_unique) - 5} more")
        
        print(f"  GPT-4o-mini-only ({len(gpt4o_mini_unique)}):")
        for obs in gpt4o_mini_unique[:5]:
            obs_type = obs.get('type', 'N/A')
            value = obs.get('value', '')[:65]
            print(f"    [{obs_type}] {value}...")
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
    total_all_three = sum(len(matches) for matches in all_three_matches.values())
    print(f"Total observables found by ALL THREE models: {total_all_three}")
    print()
    
    print("CONSISTENCY ANALYSIS:")
    print("-" * 100)
    for article_id in article_ids:
        matches = len(all_three_matches[article_id])
        sonnet_count = len(sonnet_results.get(article_id, {}).get('observables', []))
        gpt4o_count = len(gpt4o_results.get(article_id, {}).get('observables', []))
        gpt4o_mini_count = len(gpt4o_mini_results.get(article_id, {}).get('observables', []))
        avg_count = (sonnet_count + gpt4o_count + gpt4o_mini_count) / 3
        
        consistency = (matches / avg_count * 100) if avg_count > 0 else 0
        print(f"Article {article_id}: {matches} common observables ({consistency:.1f}% consistency)")
    
    print()
    print("PATTERN ANALYSIS - Commands Found by All Three:")
    print("-" * 100)
    all_common_commands = defaultdict(int)
    for article_id, matches in all_three_matches.items():
        for match in matches:
            s_value = match['sonnet'].get('value', '')
            elements = extract_key_elements(s_value)
            for cmd in elements['commands']:
                all_common_commands[cmd] += 1
    
    for cmd, count in sorted(all_common_commands.items(), key=lambda x: -x[1])[:10]:
        print(f"  {cmd}: {count} times")
    
    print()
    print("Analysis complete!")

if __name__ == '__main__':
    main()

