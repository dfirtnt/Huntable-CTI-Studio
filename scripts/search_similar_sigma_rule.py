#!/usr/bin/env python3
"""
Script to search for similar SIGMA rules using a provided rule's detection logic.
"""

import sys
from typing import Any

from src.database.manager import DatabaseManager
from src.services.lmstudio_embedding_client import LMStudioEmbeddingClient
from src.services.sigma_sync_service import SigmaSyncService


def search_similar_rules(rule_content: dict[str, Any], top_k: int = 20, threshold: float = 0.5) -> list[dict[str, Any]]:
    """
    Search for similar SIGMA rules using standardized section-based matching.

    Args:
        rule_content: Rule data with detection, logsource, etc.
        top_k: Number of results to return
        threshold: Minimum similarity threshold

    Returns:
        List of similar rules with similarity scores
    """
    # Import weights for consistency
    from src.services.sigma_matching_service import SIMILARITY_WEIGHTS

    # Use SigmaSyncService for standardized embedding text generation
    sync_service = SigmaSyncService()

    # Generate section embeddings using standardized approach
    section_texts = sync_service.create_section_embeddings_text(rule_content)
    section_texts_list = [
        section_texts["title"],
        section_texts["description"],
        section_texts["tags"],
        section_texts["signature"],
    ]

    # Generate embeddings
    embedding_client = LMStudioEmbeddingClient()
    section_embeddings = embedding_client.generate_embeddings_batch(section_texts_list)

    # Handle cases where batch might return fewer embeddings than expected
    while len(section_embeddings) < 4:
        section_embeddings.append([0.0] * 768)  # Zero vector for missing sections

    # Use signature embedding for comparison (detection logic focus)
    signature_emb = section_embeddings[3]
    embedding_str = "[" + ",".join(map(str, signature_emb)) + "]"
    print(f"Generated signature embedding (dimension: {len(signature_emb)})")

    # Query database using section embeddings
    db_manager = DatabaseManager()
    session = db_manager.get_session()

    try:
        # Use raw connection like sigma_matching_service does
        connection = session.connection()
        cursor = connection.connection.cursor()
        zero_vector = "[" + ",".join(["0.0"] * 768) + "]"

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
                CASE
                    WHEN sr.logsource_embedding IS NOT NULL AND %(embedding)s != %(zero_vec)s
                        THEN 1 - (sr.logsource_embedding <=> %(embedding)s::vector)
                    WHEN sr.embedding IS NOT NULL AND %(embedding)s != %(zero_vec)s
                        THEN 1 - (sr.embedding <=> %(embedding)s::vector)
                    ELSE 0.0
                END AS signature_sim
            FROM sigma_rules sr
            WHERE (
                sr.logsource_embedding IS NOT NULL OR
                sr.embedding IS NOT NULL
            )
            ORDER BY signature_sim DESC
            LIMIT %(limit)s
        """

        cursor.execute(query_text, {"embedding": embedding_str, "zero_vec": zero_vector, "limit": top_k})

        rows = cursor.fetchall()
        cursor.close()

        rules = []
        for row in rows:
            signature_sim = float(row[9]) if row[9] is not None else 0.0
            # Apply signature weight for consistency with other implementations
            weighted_sim = signature_sim * SIMILARITY_WEIGHTS["signature"]
            if weighted_sim >= threshold:
                rules.append(
                    {
                        "id": row[0],
                        "rule_id": row[1],
                        "title": row[2],
                        "description": row[3],
                        "tags": row[4] if row[4] else [],
                        "level": row[5],
                        "status": row[6],
                        "file_path": row[7],
                        "detection": row[8],
                        "similarity": weighted_sim,
                    }
                )

        return rules
    finally:
        session.close()


def main():
    # Parse the provided rule content
    rule_content = {
        "title": "Suspicious Process Command Execution from GoAnywhere Tomcat",
        "description": "Detects suspicious command-line activity from processes spawned by GoAnywhere tomcat service, including reconnaissance commands like whoami, systeminfo, net commands, nltest, dsquery, and PowerShell activity",
        "logsource": {"category": "process_creation", "product": "windows"},
        "detection": {
            "selection": {
                "InitiatingProcessFolderPath": "*\\GoAnywhere\\*",
                "InitiatingProcessFileName": "tomcat",
                "ProcessCommandLine": [
                    "*whoami*",
                    "*systeminfo*",
                    "*net user*",
                    "*net group*",
                    "*localgroup administrators*",
                    "*nltest /trusted_domains*",
                    "*dsquery*",
                    "*samaccountname=*",
                    "*query session*",
                    "*adscredentials*",
                    "*o365accountconfiguration*",
                    "*Invoke-Expression*",
                    "*DownloadString*",
                    "*DownloadFile*",
                    "*FromBase64String*",
                    "*System.IO.Compression*",
                    "*System.IO.MemoryStream*",
                    "*iex *",
                    "*Invoke-WebRequest*",
                    "*set-MpPreference*",
                    "*add-MpPreference*",
                    "*certutil*",
                    "*bitsadmin*",
                ],
            },
            "condition": "selection",
        },
        "tags": ["attack.execution", "attack.discovery"],
        "fields": ["InitiatingProcessFileName", "ProcessCommandLine"],
        "falsepositives": ["Legitimate administrative scripts running in GoAnywhere environments."],
        "level": "high",
    }

    print("Searching for similar SIGMA rules...\n")
    print("Query Rule:")
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
            print(f"   Similarity: {rule['similarity']:.4f} ({rule['similarity'] * 100:.2f}%)")
            print(f"   Level: {rule.get('level', 'N/A')} | Status: {rule.get('status', 'N/A')}")
            print(f"   File: {rule['file_path']}")
            if rule.get("description"):
                desc = rule["description"][:150] + "..." if len(rule["description"]) > 150 else rule["description"]
                print(f"   Description: {desc}")
            if rule.get("tags"):
                print(f"   Tags: {', '.join(rule['tags'][:5])}")
            print("-" * 100)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
