#!/usr/bin/env python3
"""
Script to search for similar SIGMA rules using a provided rule's detection logic.
"""

import sys
import json
from typing import Dict, Any, List
from sqlalchemy import text

from src.database.manager import DatabaseManager
from src.services.lmstudio_embedding_client import LMStudioEmbeddingClient
from src.database.models import SigmaRuleTable


def create_rule_embedding_text(rule_data: Dict[str, Any]) -> str:
    """
    Create enriched text for embedding from a rule.
    Uses the same format as SigmaSyncService.create_rule_embedding_text
    """
    parts = []
    
    # Title (10% weight)
    if rule_data.get('title'):
        parts.append(f"Title: {rule_data['title']}")
    
    # Description (10% weight)
    if rule_data.get('description'):
        parts.append(f"Description: {rule_data['description']}")
    
    # MITRE ATT&CK tags (10% weight)
    tags = rule_data.get('tags', [])
    if tags:
        attack_tags = [t for t in tags if t.startswith('attack.')]
        if attack_tags:
            parts.append(f"MITRE: {', '.join(attack_tags)}")
    
    # Logsource (25% weight - repeat 5x)
    logsource = rule_data.get('logsource', {})
    if isinstance(logsource, dict) and logsource:
        logsource_str = json.dumps(logsource, separators=(',', ':'))
        parts.extend([f"Logsource: {logsource_str}"] * 5)
    
    # Detection logic (45% weight - repeat 9x)
    detection = rule_data.get('detection', {})
    if isinstance(detection, dict) and detection:
        detection_str = json.dumps(detection, separators=(',', ':'))
        parts.extend([f"Detection: {detection_str}"] * 9)
    
    return ' '.join(parts)


def search_similar_rules(rule_content: Dict[str, Any], top_k: int = 20, threshold: float = 0.5) -> List[Dict[str, Any]]:
    """
    Search for similar SIGMA rules.
    
    Args:
        rule_content: Rule data with detection, logsource, etc.
        top_k: Number of results to return
        threshold: Minimum similarity threshold
        
    Returns:
        List of similar rules with similarity scores
    """
    # Create embedding text from rule
    embedding_text = create_rule_embedding_text(rule_content)
    print(f"Generated embedding text (length: {len(embedding_text)} chars)")
    
    # Generate embedding
    embedding_client = LMStudioEmbeddingClient()
    embedding = embedding_client.generate_embedding(embedding_text)
    embedding_str = '[' + ','.join(map(str, embedding)) + ']'
    print(f"Generated embedding (dimension: {len(embedding)})")
    
    # Query database
    db_manager = DatabaseManager()
    session = db_manager.get_session()
    
    try:
        # Use raw connection like sigma_matching_service does
        connection = session.connection()
        cursor = connection.connection.cursor()
        
        query_text = """
            SELECT 
                sr.id,
                sr.rule_id,
                sr.title,
                sr.description,
                sr.tags,
                sr.level,
                sr.status,
                sr.file_path,
                sr.detection,
                1 - (sr.embedding <=> %(embedding)s::vector) AS similarity
            FROM sigma_rules sr
            WHERE sr.embedding IS NOT NULL
            ORDER BY similarity DESC
            LIMIT %(limit)s
        """
        
        cursor.execute(query_text, {
            'embedding': embedding_str,
            'limit': top_k
        })
        
        rows = cursor.fetchall()
        cursor.close()
        
        rules = []
        for row in rows:
            similarity = float(row[9])
            if similarity >= threshold:
                rules.append({
                    'id': row[0],
                    'rule_id': row[1],
                    'title': row[2],
                    'description': row[3],
                    'tags': row[4] if row[4] else [],
                    'level': row[5],
                    'status': row[6],
                    'file_path': row[7],
                    'detection': row[8],
                    'similarity': similarity
                })
        
        return rules
    finally:
        session.close()


def main():
    # Parse the provided rule content
    rule_content = {
        'title': 'Suspicious Process Command Execution from GoAnywhere Tomcat',
        'description': 'Detects suspicious command-line activity from processes spawned by GoAnywhere tomcat service, including reconnaissance commands like whoami, systeminfo, net commands, nltest, dsquery, and PowerShell activity',
        'logsource': {
            'category': 'process_creation',
            'product': 'windows'
        },
        'detection': {
            'selection': {
                'InitiatingProcessFolderPath': '*\\GoAnywhere\\*',
                'InitiatingProcessFileName': 'tomcat',
                'ProcessCommandLine': [
                    '*whoami*',
                    '*systeminfo*',
                    '*net user*',
                    '*net group*',
                    '*localgroup administrators*',
                    '*nltest /trusted_domains*',
                    '*dsquery*',
                    '*samaccountname=*',
                    '*query session*',
                    '*adscredentials*',
                    '*o365accountconfiguration*',
                    '*Invoke-Expression*',
                    '*DownloadString*',
                    '*DownloadFile*',
                    '*FromBase64String*',
                    '*System.IO.Compression*',
                    '*System.IO.MemoryStream*',
                    '*iex *',
                    '*Invoke-WebRequest*',
                    '*set-MpPreference*',
                    '*add-MpPreference*',
                    '*certutil*',
                    '*bitsadmin*'
                ]
            },
            'condition': 'selection'
        },
        'tags': ['attack.execution', 'attack.discovery'],
        'fields': ['InitiatingProcessFileName', 'ProcessCommandLine'],
        'falsepositives': ['Legitimate administrative scripts running in GoAnywhere environments.'],
        'level': 'high'
    }
    
    print("Searching for similar SIGMA rules...\n")
    print(f"Query Rule:")
    print(f"  Title: {rule_content['title']}")
    print(f"  Detection: {len(rule_content['detection']['selection']['ProcessCommandLine'])} command patterns\n")
    
    # Run search
    try:
        results = search_similar_rules(rule_content, top_k=20, threshold=0.5)
        
        if not results:
            print("No similar rules found (threshold: 0.5)")
            return
        
        print(f"\nFound {len(results)} similar rules:\n")
        print("-" * 100)
        
        for i, rule in enumerate(results, 1):
            print(f"\n{i}. {rule['title']}")
            print(f"   Rule ID: {rule['rule_id']}")
            print(f"   Similarity: {rule['similarity']:.4f} ({rule['similarity']*100:.2f}%)")
            print(f"   Level: {rule.get('level', 'N/A')} | Status: {rule.get('status', 'N/A')}")
            print(f"   File: {rule['file_path']}")
            if rule.get('description'):
                desc = rule['description'][:150] + '...' if len(rule['description']) > 150 else rule['description']
                print(f"   Description: {desc}")
            if rule.get('tags'):
                print(f"   Tags: {', '.join(rule['tags'][:5])}")
            print("-" * 100)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

