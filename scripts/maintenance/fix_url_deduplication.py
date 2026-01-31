#!/usr/bin/env python3
"""
Fix URL deduplication in CTIScraper

This script adds the missing get_existing_urls() method and updates the worker
to properly check for URL duplicates before scraping.
"""

import os
import sys

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))


def fix_async_manager():
    """Add get_existing_urls method to AsyncDatabaseManager."""

    # Read current file
    with open("src/database/async_manager.py") as f:
        content = f.read()

    # Find the get_existing_content_hashes method and add get_existing_urls after it
    insert_point = content.find("async def get_existing_content_hashes(self, limit: int = 10000) -> set:")
    if insert_point == -1:
        print("❌ Could not find get_existing_content_hashes method")
        return False

    # Find the end of the method
    method_start = content.find("async def get_existing_content_hashes", insert_point)
    method_end = content.find("async def get_total_article_count", method_start)

    if method_end == -1:
        print("❌ Could not find end of get_existing_content_hashes method")
        return False

    # Insert the new method
    new_method = '''
    async def get_existing_urls(self, limit: int = 10000) -> set:
        """Get existing canonical URLs for deduplication."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleTable.canonical_url).where(ArticleTable.archived == False).limit(limit)
                )
                urls = result.scalars().all()
                return set(urls)
                
        except Exception as e:
            logger.error(f"Failed to get existing URLs: {e}")
            return set()
    
    '''

    new_content = content[:method_end] + new_method + content[method_end:]

    # Write back
    with open("src/database/async_manager.py", "w") as f:
        f.write(new_content)

    print("✅ Added get_existing_urls() to AsyncDatabaseManager")
    return True


def fix_sync_manager():
    """Add get_existing_urls method to DatabaseManager."""

    # Read current file
    with open("src/database/manager.py") as f:
        content = f.read()

    # Find the get_existing_content_hashes method and add get_existing_urls after it
    insert_point = content.find("def get_existing_content_hashes(self, limit: int = 10000) -> Set[str]:")
    if insert_point == -1:
        print("❌ Could not find get_existing_content_hashes method")
        return False

    # Find the end of the method
    method_start = content.find("def get_existing_content_hashes", insert_point)
    method_end = content.find("def record_source_check", method_start)

    if method_end == -1:
        print("❌ Could not find end of get_existing_content_hashes method")
        return False

    # Insert the new method
    new_method = '''
    def get_existing_urls(self, limit: int = 10000) -> Set[str]:
        """Get set of existing canonical URLs for deduplication."""
        with self.get_session() as session:
            urls = session.query(ArticleTable.canonical_url).where(ArticleTable.archived == False).limit(limit).all()
            return {url_tuple[0] for url_tuple in urls}
    
    '''

    new_content = content[:method_end] + new_method + content[method_end:]

    # Write back
    with open("src/database/manager.py", "w") as f:
        f.write(new_content)

    print("✅ Added get_existing_urls() to DatabaseManager")
    return True


def fix_worker():
    """Update worker to use existing URLs for deduplication."""

    # Read current file
    with open("src/worker/celery_app.py") as f:
        content = f.read()

    # Find and replace the worker code that gets existing hashes
    old_pattern = """                # Get existing content hashes for deduplication
                existing_hashes = await db.get_existing_content_hashes()"""

    new_pattern = """                # Get existing content hashes and URLs for deduplication
                existing_hashes = await db.get_existing_content_hashes()
                existing_urls = await db.get_existing_urls()"""

    if old_pattern in content:
        content = content.replace(old_pattern, new_pattern)

        # Also update the processor call
        old_processor_call = """                            # Process articles through deduplication with source-specific config
                            # Note: source.config is already a dict from database, not a Pydantic model
                            source_config = source.config if source.config else None
                            dedup_result = await processor.process_articles(articles, existing_hashes, source_config=source_config)"""

        new_processor_call = """                            # Process articles through deduplication with source-specific config
                            # Note: source.config is already a dict from database, not a Pydantic model
                            source_config = source.config if source.config else None
                            dedup_result = await processor.process_articles(articles, existing_hashes, existing_urls, source_config=source_config)"""

        if old_processor_call in content:
            content = content.replace(old_processor_call, new_processor_call)
        else:
            # Try alternative pattern
            alt_pattern = """                            dedup_result = await processor.process_articles(articles, existing_hashes)"""
            alt_replacement = """                            dedup_result = await processor.process_articles(articles, existing_hashes, existing_urls)"""
            content = content.replace(alt_pattern, alt_replacement)

        # Write back
        with open("src/worker/celery_app.py", "w") as f:
            f.write(content)

        print("✅ Updated worker to use existing URLs for deduplication")
        return True
    print("❌ Could not find worker pattern to update")
    return False


def main():
    """Apply all fixes."""
    print("🔧 Fixing URL deduplication in CTIScraper...")

    success = True
    success &= fix_async_manager()
    success &= fix_sync_manager()
    success &= fix_worker()

    if success:
        print("\n✅ All fixes applied successfully!")
        print("\n📋 Next steps:")
        print("1. Restart the worker: docker-compose restart cti_worker")
        print("2. Monitor logs: docker-compose logs -f cti_worker")
        print("3. Check for reduced duplicate rates")
        print("4. Consider cleaning up existing duplicates")
    else:
        print("\n❌ Some fixes failed. Check the output above.")


if __name__ == "__main__":
    main()
