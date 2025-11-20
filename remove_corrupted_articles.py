#!/usr/bin/env python3
"""Remove articles containing corrupted character sequence ''."""

import sys
from typing import List

from sqlalchemy import text

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable


def find_corrupted_articles() -> List[int]:
    """Find all articles containing '' in content."""
    db = DatabaseManager()
    corrupted_sequence = ''
    
    with db.get_session() as session:
        # Fetch all non-archived articles and filter in Python
        # This is safer than SQL LIKE for multi-byte sequences
        all_articles = session.query(ArticleTable.id, ArticleTable.title, ArticleTable.content).filter(
            ArticleTable.archived == False
        ).all()
        
        corrupted = []
        for aid, title, content in all_articles:
            if content and corrupted_sequence in content:
                corrupted.append((aid, title))
        
        article_ids = [aid for aid, _ in corrupted]
        
        if article_ids:
            print(f"🔍 Found {len(article_ids)} articles with '' in content:")
            for aid, title in corrupted[:20]:  # Show first 20
                print(f"   ID {aid}: {title[:60]}...")
            if len(corrupted) > 20:
                print(f"   ... and {len(corrupted) - 20} more")
        
        return article_ids


def delete_articles(article_ids: List[int], dry_run: bool = False) -> tuple[int, int]:
    """Delete articles and all related records."""
    if not article_ids:
        return 0, 0
    
    db = DatabaseManager()
    successful = 0
    failed = 0
    
    with db.get_session() as session:
        for article_id in article_ids:
            try:
                if dry_run:
                    article = session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                    if article:
                        print(f"[DRY RUN] Would delete article {article_id}: {article.title[:50]}...")
                    successful += 1
                    continue
                
                # Delete related records first to avoid foreign key constraints
                # Delete from article_annotations table
                session.execute(
                    text("DELETE FROM article_annotations WHERE article_id = :article_id"),
                    {"article_id": article_id}
                )
                
                # Delete from content_hashes table
                session.execute(
                    text("DELETE FROM content_hashes WHERE article_id = :article_id"),
                    {"article_id": article_id}
                )
                
                # Delete from simhash_buckets table
                session.execute(
                    text("DELETE FROM simhash_buckets WHERE article_id = :article_id"),
                    {"article_id": article_id}
                )
                
                # Delete the article
                article = session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                if article:
                    title = article.title
                    session.delete(article)
                    session.commit()
                    print(f"✅ Deleted article {article_id}: {title[:50]}...")
                    successful += 1
                else:
                    print(f"⚠️ Article {article_id} not found")
                    failed += 1
                    
            except Exception as e:
                session.rollback()
                print(f"❌ Error deleting article {article_id}: {e}")
                failed += 1
    
    return successful, failed


def main():
    """Main function."""
    dry_run = '--dry-run' in sys.argv
    
    print("🔍 Searching for articles with '' in content...")
    article_ids = find_corrupted_articles()
    
    if not article_ids:
        print("✅ No articles found with '' in content")
        sys.exit(0)
    
    if dry_run:
        print(f"\n[DRY RUN] Would delete {len(article_ids)} articles")
        delete_articles(article_ids, dry_run=True)
    else:
        print(f"\n⚠️  About to delete {len(article_ids)} articles")
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled")
            sys.exit(0)
        
        print(f"\n🗑️  Deleting {len(article_ids)} articles...")
        successful, failed = delete_articles(article_ids)
        
        print(f"\n{'='*60}")
        print("Summary:")
        print(f"{'='*60}")
        print(f"✅ Successfully deleted: {successful}/{len(article_ids)}")
        if failed > 0:
            print(f"❌ Failed to delete: {failed}/{len(article_ids)}")
        sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

