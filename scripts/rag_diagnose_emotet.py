#!/usr/bin/env python3
"""
Diagnose RAG results for "Emotet delivery techniques".
Checks: lexical Emotet articles, embedding search results at 0.38 threshold.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    from src.database.async_manager import async_db_manager
    from src.services.rag_service import get_rag_service

    query = "Emotet delivery techniques"
    threshold = 0.38

    # 1. Lexical: articles containing "emotet" in title or content
    all_articles = await async_db_manager.list_articles()
    emotet_lexical = [
        a for a in all_articles if "emotet" in (a.title or "").lower() or "emotet" in (a.content or "").lower()
    ]
    print(f"Lexical 'emotet' matches: {len(emotet_lexical)} articles")
    for a in emotet_lexical[:10]:
        print(f"  - {a.id}: {a.title[:70]}...")

    # 2. Embedding search: top 50, threshold 0.38 (original behavior: top 5)
    rag = get_rag_service()
    results_5 = await rag.find_similar_content(query=query, top_k=5, threshold=threshold, use_chunks=False)
    results_50 = await rag.find_similar_content(query=query, top_k=50, threshold=threshold, use_chunks=False)
    print(f"\nEmbedding search (threshold={threshold}):")
    print(f"  top_k=5:  {len(results_5)} articles")
    print(f"  top_k=50: {len(results_50)} articles")
    if results_50:
        print("  Top 10 by similarity:")
        for r in results_50[:10]:
            sim = r.get("similarity", 0)
            title = (r.get("title") or "")[:60]
            print(f"    {sim:.2f} | {title}")

    # 3. How many of top 50 are lexical Emotet matches?
    emotet_ids = {a.id for a in emotet_lexical}
    in_both = [r for r in results_50 if r.get("id") in emotet_ids]
    print(f"\nArticles in both lexical + embedding (top 50): {len(in_both)}")


if __name__ == "__main__":
    asyncio.run(main())
