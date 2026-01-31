#!/usr/bin/env python3
"""
Ensure all articles with hunt score > 50 have embeddings.

Generates missing embeddings for high-value articles.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime

from sqlalchemy import text

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable
from src.services.embedding_service import EmbeddingService


def main():
    """Ensure articles with hunt score > 50 have embeddings."""
    print("🔧 Ensuring Articles with Hunt Score > 50 Have Embeddings")
    print("=" * 60)

    db_manager = DatabaseManager()
    session = db_manager.get_session()

    try:
        # Find articles with hunt score > 50 that are missing embeddings
        query = text("""
            SELECT id, title, article_metadata
            FROM articles
            WHERE (article_metadata->>'threat_hunting_score')::float > 50
              AND embedding IS NULL
            ORDER BY (article_metadata->>'threat_hunting_score')::float DESC
        """)

        result = session.execute(query)
        rows = result.fetchall()

        print(f"\nFound {len(rows)} articles with hunt score > 50 missing embeddings\n")

        if not rows:
            print("✅ All articles with hunt score > 50 already have embeddings.")
            return

        # Initialize embedding service
        embedding_service = EmbeddingService()

        # Process each article
        processed = 0
        errors = 0

        for idx, row in enumerate(rows, 1):
            article_id = row.id
            title = row.title
            hunt_score = row.article_metadata.get("threat_hunting_score", 0) if row.article_metadata else 0

            print(f"[{idx}/{len(rows)}] Processing Article {article_id}: {title[:60]}")
            print(f"   Hunt Score: {hunt_score}")

            try:
                # Get the full article
                article = session.execute(
                    text("SELECT id, title, content FROM articles WHERE id = :id"), {"id": article_id}
                ).first()

                if not article or not article.content:
                    print("   ⚠️  No content available")
                    errors += 1
                    continue

                # Generate embedding
                embedding_text = f"{article.title}\n{article.content}"
                embedding = embedding_service.generate_embedding(embedding_text)

                # Update article using ORM
                article_obj = session.query(ArticleTable).filter_by(id=article_id).first()
                if article_obj:
                    article_obj.embedding = embedding
                    article_obj.embedding_model = "all-mpnet-base-v2"
                    article_obj.embedded_at = datetime.now()
                    session.commit()
                processed += 1
                print(f"   ✅ Embedding generated ({len(embedding)} dimensions)")

            except Exception as e:
                print(f"   ❌ Error: {e}")
                errors += 1
                session.rollback()
                continue

            print()

        # Summary
        print("=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"✅ Successfully processed: {processed}")
        print(f"❌ Errors: {errors}")
        print(f"📊 Total articles: {len(rows)}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
