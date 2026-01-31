#!/usr/bin/env python3
"""
Add an article to the Langfuse cmdline_extractor_gt dataset for evaluation.

Usage:
    python scripts/add_article_to_cmdline_eval.py --url "https://www.huntress.com/blog/velociraptor-misuse-part-one-wsus-up" --id "article_63" --expected-count 6
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from langfuse import Langfuse

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_langfuse_client() -> Langfuse:
    """Initialize Langfuse client from environment variables."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not public_key or not secret_key:
        raise ValueError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")

    return Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
        flush_at=1,
        flush_interval=1.0,
    )


def get_article_by_url(url: str) -> ArticleTable:
    """Get article from database by URL."""
    db_manager = DatabaseManager()
    session = db_manager.get_session()

    try:
        # Try exact match first
        article = session.query(ArticleTable).filter(ArticleTable.canonical_url == url).first()

        if article:
            return article

        # Try partial match (URL might have query params)
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        normalized_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

        article = session.query(ArticleTable).filter(ArticleTable.canonical_url.like(f"{normalized_url}%")).first()

        if article:
            return article

        raise ValueError(f"Article not found in database: {url}")
    finally:
        session.close()


def add_article_to_dataset(url: str, item_id: str, expected_count: int, dataset_name: str = "cmdline_extractor_gt"):
    """Add article to Langfuse dataset."""
    # Get article from database
    logger.info(f"Fetching article from database: {url}")
    article = get_article_by_url(url)

    logger.info(f"Found article: ID={article.id}, Title={article.title[:50]}...")

    # Initialize Langfuse client
    client = get_langfuse_client()

    # Get or create dataset
    dataset = client.get_dataset(dataset_name)
    if not dataset:
        logger.info(f"Dataset '{dataset_name}' not found, creating it...")
        dataset = client.create_dataset(name=dataset_name)
        logger.info(f"Created dataset: {dataset_name}")

    # Prepare dataset item
    item_input = {
        "article_text": article.content,
        "article_title": article.title,
        "article_url": article.canonical_url,
        "article_id": article.id,
    }

    item_expected_output = {
        "expected_count": expected_count,
    }

    item_metadata = {
        "article_id": article.id,
        "source": "eval_articles.yaml",
    }

    # Create dataset item
    logger.info(f"Adding item '{item_id}' to dataset '{dataset_name}'...")
    try:
        dataset_item = dataset.create_item(
            id=item_id,
            input=item_input,
            expected_output=item_expected_output,
            metadata=item_metadata,
        )
        logger.info(f"✅ Successfully added item '{item_id}' to dataset '{dataset_name}'")
        logger.info(f"   Article ID: {article.id}")
        logger.info(f"   Expected count: {expected_count}")
        return dataset_item
    except Exception as e:
        # Check if item already exists
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            logger.warning(f"⚠️  Item '{item_id}' already exists in dataset. Updating...")
            # Try to update existing item
            try:
                # Langfuse doesn't have a direct update method, so we'll delete and recreate
                # First, try to get the item to see if it exists
                items = list(dataset.items) if hasattr(dataset, "items") else []
                existing_item = next((item for item in items if hasattr(item, "id") and item.id == item_id), None)

                if existing_item:
                    logger.info("Found existing item, deleting and recreating...")
                    # Note: Langfuse Python SDK may not have delete method
                    # If update fails, we'll log the error
                    logger.warning("⚠️  Cannot update existing item. Please delete manually or use a different ID.")
                    raise ValueError(f"Item '{item_id}' already exists. Please delete it first or use a different ID.")
            except Exception as update_error:
                logger.error(f"Failed to update item: {update_error}")
                raise
        else:
            logger.error(f"Failed to add item: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(description="Add an article to Langfuse cmdline_extractor_gt dataset")
    parser.add_argument("--url", required=True, help="Article URL (canonical_url from database)")
    parser.add_argument("--id", required=True, dest="item_id", help="Dataset item ID (e.g., 'article_63')")
    parser.add_argument(
        "--expected-count", type=int, required=True, dest="expected_count", help="Expected command-line count"
    )
    parser.add_argument(
        "--dataset", default="cmdline_extractor_gt", help="Dataset name (default: cmdline_extractor_gt)"
    )

    args = parser.parse_args()

    try:
        add_article_to_dataset(
            url=args.url,
            item_id=args.item_id,
            expected_count=args.expected_count,
            dataset_name=args.dataset,
        )
        logger.info("✅ Article successfully added to evaluation dataset")
    except Exception as e:
        logger.error(f"❌ Failed to add article: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
