#!/usr/bin/env python3
"""
Compare observables extracted by GPT-4o and GPT-4o-mini
across all 6 benchmark articles to identify:
1. Where both find the same information
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
        'file_extensions': [],
        'techniques': []
    }
    
    # Extract commands (common Windows commands)
    commands = ['powershell', 'cmd', 'whoami', 'systeminfo', 'tasklist', 'net', 
                'reg', 'schtasks', 'wscript', 'msbuild', 'rundll32', 'curl',
                'rdrleakdiag', 'vssadmin', 'nltest', 'sc', 'mshta', 'msiexec',
                'w3wp', 'wsusservice']
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
    if 'powershell' in obs_value.lower() and ('-enc' in obs_value.lower() or 'encoded' in obs_value.lower()):
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

def main():
    # Load results from GPT-4o and GPT-4o-mini
    gpt4o_file = "gpt4o_extract_results_full_2025-11-10_16-01-32.json"
    gpt4o_mini_file = "gpt4o-mini_extract_results_full_2025-11-10_16-02-49.json"
    
    gpt4o_results = load_results(gpt4o_file)
    gpt4o_mini_results = load_results(gpt4o_mini_file)
    
    article_ids = ['1794', '1860', '1866', '1909', '1937', '1974']
    
    print("=" * 100)
    print("GPT-4o vs GPT-4o-mini EXTRACTION COMPARISON ANALYSIS")
    print("=" * 100)
    print()
    
    # Overall statistics
    total_gpt4o = sum(len(gpt4o_results.get(aid, {}).get('observables', [])) for aid in article_ids)
    total_gpt4o_mini = sum(len(gpt4o_mini_results.get(aid, {}).get('observables', [])) for aid in article_ids)
    
    print("OVERALL STATISTICS")
    print("-" * 100)
    print(f"GPT-4o:      {total_gpt4o} total observables")
    print(f"GPT-4o-mini: {total_gpt4o_mini} total observables")
    print(f"Ratio:       {total_gpt4o_mini/total_gpt4o:.2f}x (mini extracts {total_gpt4o_mini/total_gpt4o*100:.1f}% of GPT-4o)")
    print()
    
    # Per-article analysis
    all_matches = defaultdict(list)  # article_id -> list of matched observables
    all_unique = defaultdict(lambda: {'gpt4o': [], 'gpt4o_mini': []})
    
    for article_id in article_ids:
        print("=" * 100)
        print(f"ARTICLE {article_id}")
        print("=" * 100)
        
        gpt4o_obs = gpt4o_results.get(article_id, {}).get('observables', [])
        gpt4o_mini_obs = gpt4o_mini_results.get(article_id, {}).get('observables', [])
        
        gpt4o_title = gpt4o_results.get(article_id, {}).get('title', 'N/A')
        print(f"Title: {gpt4o_title}")
        print()
        print(f"Counts: GPT-4o={len(gpt4o_obs)}, GPT-4o-mini={len(gpt4o_mini_obs)}")
        print()
        
        # Find matches between the two
        print("OBSERVABLES FOUND BY BOTH MODELS:")
        print("-" * 100)
        matches_found = 0
        
        for g4o_obs in gpt4o_obs:
            g4o_value = g4o_obs.get('value', '')
            
            # Check GPT-4o-mini
            mini_match = None
            best_mini_score = 0
            for m_obs in gpt4o_mini_obs:
                m_value = m_obs.get('value', '')
                score = similarity_score(g4o_value, m_value)
                if score > best_mini_score and score > 0.7:  # 70% similarity threshold
                    best_mini_score = score
                    mini_match = m_obs
            
            # If found in both
            if mini_match:
                matches_found += 1
                print(f"\n[{matches_found}] BOTH MODELS FOUND:")
                print(f"  GPT-4o:      {g4o_value[:85]}...")
                print(f"  GPT-4o-mini: {mini_match.get('value', '')[:85]}...")
                print(f"  Similarity:  {best_mini_score:.2f}")
                
                # Extract key elements
                g4o_elements = extract_key_elements(g4o_value)
                m_elements = extract_key_elements(mini_match.get('value', ''))
                
                common_commands = set(g4o_elements['commands']) & set(m_elements['commands'])
                common_techniques = set(g4o_elements['techniques']) & set(m_elements['techniques'])
                
                if common_commands:
                    print(f"  Common Commands: {', '.join(sorted(common_commands))}")
                if common_techniques:
                    print(f"  Common Techniques: {', '.join(sorted(common_techniques))}")
                
                # Compare source contexts
                g4o_context = g4o_obs.get('source_context', '')
                m_context = mini_match.get('source_context', '')
                if g4o_context and m_context:
                    context_sim = similarity_score(g4o_context, m_context)
                    if context_sim < 0.8:
                        print(f"  Context Similarity: {context_sim:.2f} (different interpretations)")
                
                all_matches[article_id].append({
                    'gpt4o': g4o_obs,
                    'gpt4o_mini': mini_match,
                    'similarity': best_mini_score,
                    'common_elements': {
                        'commands': list(common_commands),
                        'techniques': list(common_techniques)
                    }
                })
        
        if matches_found == 0:
            print("  (No observables found by both models)")
        
        print()
        print("UNIQUE TO EACH MODEL:")
        print("-" * 100)
        
        # Find unique to GPT-4o
        gpt4o_unique = []
        for g4o_obs in gpt4o_obs:
            g4o_value = g4o_obs.get('value', '')
            found_in_mini = False
            for m_obs in gpt4o_mini_obs:
                if similarity_score(g4o_value, m_obs.get('value', '')) > 0.7:
                    found_in_mini = True
                    break
            if not found_in_mini:
                gpt4o_unique.append(g4o_obs)
        
        # Find unique to GPT-4o-mini
        gpt4o_mini_unique = []
        for m_obs in gpt4o_mini_obs:
            m_value = m_obs.get('value', '')
            found_in_g4o = False
            for g4o_obs in gpt4o_obs:
                if similarity_score(m_value, g4o_obs.get('value', '')) > 0.7:
                    found_in_g4o = True
                    break
            if not found_in_g4o:
                gpt4o_mini_unique.append(m_obs)
        
        print(f"  GPT-4o-only ({len(gpt4o_unique)}):")
        for obs in gpt4o_unique[:8]:  # Show first 8
            obs_type = obs.get('type', 'N/A')
            value = obs.get('value', '')[:65]
            print(f"    [{obs_type}] {value}...")
        if len(gpt4o_unique) > 8:
            print(f"    ... and {len(gpt4o_unique) - 8} more")
        
        print(f"  GPT-4o-mini-only ({len(gpt4o_mini_unique)}):")
        for obs in gpt4o_mini_unique[:8]:
            obs_type = obs.get('type', 'N/A')
            value = obs.get('value', '')[:65]
            print(f"    [{obs_type}] {value}...")
        if len(gpt4o_mini_unique) > 8:
            print(f"    ... and {len(gpt4o_mini_unique) - 8} more")
        
        all_unique[article_id] = {
            'gpt4o': gpt4o_unique,
            'gpt4o_mini': gpt4o_mini_unique
        }
        
        print()
    
    # Summary
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    total_matches = sum(len(matches) for matches in all_matches.values())
    print(f"Total observables found by both models: {total_matches}")
    print()
    
    print("CONSISTENCY ANALYSIS:")
    print("-" * 100)
    for article_id in article_ids:
        matches = len(all_matches[article_id])
        gpt4o_count = len(gpt4o_results.get(article_id, {}).get('observables', []))
        gpt4o_mini_count = len(gpt4o_mini_results.get(article_id, {}).get('observables', []))
        avg_count = (gpt4o_count + gpt4o_mini_count) / 2
        
        consistency = (matches / avg_count * 100) if avg_count > 0 else 0
        print(f"Article {article_id}: {matches} common observables ({consistency:.1f}% consistency)")
    
    print()
    print("PATTERN ANALYSIS:")
    print("-" * 100)
    # Analyze common patterns
    all_common_commands = defaultdict(int)
    all_common_techniques = defaultdict(int)
    for article_id, matches in all_matches.items():
        for match in matches:
            for cmd in match['common_elements']['commands']:
                all_common_commands[cmd] += 1
            for tech in match['common_elements']['techniques']:
                all_common_techniques[tech] += 1
    
    print("Most commonly extracted commands (found by both):")
    for cmd, count in sorted(all_common_commands.items(), key=lambda x: -x[1])[:10]:
        print(f"  {cmd}: {count} times")
    
    print()
    print("Most commonly extracted techniques (found by both):")
    for tech, count in sorted(all_common_techniques.items(), key=lambda x: -x[1])[:10]:
        print(f"  {tech}: {count} times")
    
    print()
    print("DIFFERENTIATION ANALYSIS:")
    print("-" * 100)
    print("What GPT-4o extracts that GPT-4o-mini misses:")
    gpt4o_only_techniques = defaultdict(int)
    for article_id, unique_obs in all_unique.items():
        for obs in unique_obs['gpt4o']:
            elements = extract_key_elements(obs.get('value', ''))
            for tech in elements['techniques']:
                gpt4o_only_techniques[tech] += 1
    
    for tech, count in sorted(gpt4o_only_techniques.items(), key=lambda x: -x[1])[:5]:
        print(f"  {tech}: {count} times (only in GPT-4o)")
    
    print()
    print("What GPT-4o-mini extracts that GPT-4o misses:")
    mini_only_techniques = defaultdict(int)
    for article_id, unique_obs in all_unique.items():
        for obs in unique_obs['gpt4o_mini']:
            elements = extract_key_elements(obs.get('value', ''))
            for tech in elements['techniques']:
                mini_only_techniques[tech] += 1
    
    for tech, count in sorted(mini_only_techniques.items(), key=lambda x: -x[1])[:5]:
        print(f"  {tech}: {count} times (only in GPT-4o-mini)")
    
    print()
    print("Analysis complete!")

if __name__ == '__main__':
    main()

