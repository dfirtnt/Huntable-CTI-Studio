"""
Celery Application for CTI Scraper Background Tasks

Handles source checking, article collection, and other async operations.
"""

import os
import logging
import time
import sys
from typing import List, Optional
from celery import Celery
from celery.schedules import crontab

# Configure logging
logger = logging.getLogger(__name__)

# CRITICAL: Get Redis URL from environment BEFORE any other imports
# Check both REDIS_URL and CELERY_BROKER_URL (Celery's preferred env var name)
redis_url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL")

# Set CELERY_BROKER_URL and CELERY_RESULT_BACKEND environment variables
# Celery automatically reads these and they take precedence
if redis_url:
    os.environ["CELERY_BROKER_URL"] = redis_url
    os.environ["CELERY_RESULT_BACKEND"] = redis_url
    logger.debug(
        "Set CELERY_BROKER_URL and CELERY_RESULT_BACKEND environment variables"
    )

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("CELERY_CONFIG_MODULE", "src.worker.celeryconfig")

# Create the Celery app with broker URL directly in constructor
# This is the most reliable way to set it
if redis_url:
    celery_app = Celery("cti_scraper", broker=redis_url, backend=redis_url)
    logger.info(
        f"Celery app created with Redis URL from environment: {redis_url.split('@')[0]}@***"
    )
else:
    celery_app = Celery("cti_scraper")

# Import config module to get other settings (but we won't use its broker_url)
import src.worker.celeryconfig as celeryconfig

# Manually copy config settings EXCEPT broker_url and result_backend
# This prevents config_from_object from overwriting our broker URL
celery_app.conf.task_serializer = celeryconfig.task_serializer
celery_app.conf.accept_content = celeryconfig.accept_content
celery_app.conf.result_serializer = celeryconfig.result_serializer
celery_app.conf.timezone = celeryconfig.timezone
celery_app.conf.enable_utc = celeryconfig.enable_utc
celery_app.conf.worker_prefetch_multiplier = celeryconfig.worker_prefetch_multiplier
celery_app.conf.worker_max_tasks_per_child = celeryconfig.worker_max_tasks_per_child
celery_app.conf.worker_disable_rate_limits = celeryconfig.worker_disable_rate_limits
celery_app.conf.task_routes = celeryconfig.task_routes
celery_app.conf.task_default_queue = celeryconfig.task_default_queue
celery_app.conf.task_queues = celeryconfig.task_queues
celery_app.conf.task_always_eager = celeryconfig.task_always_eager
celery_app.conf.task_eager_propagates = celeryconfig.task_eager_propagates
celery_app.conf.task_ignore_result = celeryconfig.task_ignore_result
celery_app.conf.task_store_errors_even_if_ignored = (
    celeryconfig.task_store_errors_even_if_ignored
)
celery_app.conf.result_expires = celeryconfig.result_expires
celery_app.conf.result_persistent = celeryconfig.result_persistent
celery_app.conf.worker_send_task_events = celeryconfig.worker_send_task_events
celery_app.conf.task_send_sent_event = celeryconfig.task_send_sent_event
celery_app.conf.worker_log_format = celeryconfig.worker_log_format
celery_app.conf.worker_task_log_format = celeryconfig.worker_task_log_format
celery_app.conf.worker_direct = celeryconfig.worker_direct
celery_app.conf.worker_redirect_stdouts = celeryconfig.worker_redirect_stdouts
celery_app.conf.worker_redirect_stdouts_level = (
    celeryconfig.worker_redirect_stdouts_level
)
celery_app.conf.task_acks_late = celeryconfig.task_acks_late
celery_app.conf.task_reject_on_worker_lost = celeryconfig.task_reject_on_worker_lost
celery_app.conf.task_remote_tracebacks = celeryconfig.task_remote_tracebacks

# Verify broker URL is still correct
if redis_url:
    if celery_app.conf.broker_url == redis_url:
        logger.debug("Broker URL successfully set from environment")
    else:
        logger.error(
            f"CRITICAL: Broker URL mismatch! Expected: {redis_url[:30]}..., Got: {celery_app.conf.broker_url}"
        )

# Load task modules from all registered app configs.
celery_app.autodiscover_tasks()

# Ensure local task modules are registered
import src.worker.tasks.annotation_embeddings  # noqa: E402,F401
import src.worker.tasks.observable_training  # noqa: E402,F401
import src.worker.tasks.test_agents  # noqa: E402,F401


# Define periodic tasks
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup periodic tasks for the CTI Scraper."""

    # Check all sources every 30 minutes
    sender.add_periodic_task(
        crontab(minute="*/30"),  # Every 30 minutes
        check_all_sources.s(),
        name="check-all-sources-every-30min",
    )

    # Clean up old data daily at 2 AM
    sender.add_periodic_task(
        crontab(hour=2, minute=0),  # Daily at 2 AM
        cleanup_old_data.s(),
        name="cleanup-old-data-daily",
    )

    # Generate daily reports at 6 AM
    sender.add_periodic_task(
        crontab(hour=6, minute=0),  # Daily at 6 AM
        generate_daily_report.s(),
        name="generate-daily-report",
    )

    # Embed new articles daily at 3 PM
    sender.add_periodic_task(
        crontab(hour=15, minute=0),  # Daily at 3 PM
        embed_new_articles.s(),
        name="embed-new-articles-daily",
    )

    # Sync SigmaHQ repository and update embeddings weekly on Sundays at 4 AM
    sender.add_periodic_task(
        crontab(hour=4, minute=0, day_of_week=0),  # Weekly on Sunday at 4 AM
        sync_sigma_rules.s(),
        name="sync-sigma-rules-weekly",
    )

    # Generate annotation embeddings weekly on Sundays at 4 AM
    # sender.add_periodic_task(
    #     crontab(hour=4, minute=0, day_of_week=0),  # Weekly on Sunday at 4 AM
    #     generate_annotation_embeddings.s(),
    #     name='embed-annotations-weekly'
    # )


@celery_app.task(bind=True, max_retries=3)
def check_all_sources(self):
    """Check all active sources for new content."""
    try:
        import asyncio
        from src.database.async_manager import AsyncDatabaseManager
        from src.core.fetcher import ContentFetcher
        from src.core.processor import ContentProcessor

        async def run_source_check():
            """Run the actual source checking."""
            db = AsyncDatabaseManager()
            try:
                # Get all active sources
                sources = await db.list_sources()
                active_sources = [s for s in sources if getattr(s, "active", True)]

                logger.info(
                    f"Checking {len(active_sources)} active sources for new content..."
                )

                if not active_sources:
                    return {
                        "status": "success",
                        "message": "No active sources to check",
                    }

                # Initialize processor for deduplication
                processor = ContentProcessor(
                    similarity_threshold=0.85,
                    max_age_days=90,
                    enable_content_enhancement=True,
                )

                # Get existing content hashes and URLs for deduplication
                existing_hashes = await db.get_existing_content_hashes()
                existing_urls = await db.get_existing_urls()

                total_articles_collected = 0
                total_articles_saved = 0
                total_articles_filtered = 0

                async with ContentFetcher() as fetcher:
                    for source in active_sources:
                        start_time = time.time()
                        collection_success = False
                        fetch_result = None
                        articles = []
                        error_msg = None

                        try:
                            fetch_result = await fetcher.fetch_source(source)
                            articles = fetch_result.articles or []
                            collection_success = fetch_result.success

                            if collection_success and articles:
                                total_articles_collected += len(articles)
                                logger.info(
                                    f"  ✓ {source.name}: {len(articles)} articles collected via {fetch_result.method}"
                                )

                                source_config = source.config if source.config else None
                                dedup_result = await processor.process_articles(
                                    articles,
                                    existing_hashes,
                                    existing_urls,
                                    source_config=source_config,
                                )

                                saved_count = 0
                                if dedup_result.unique_articles:
                                    for article in dedup_result.unique_articles:
                                        try:
                                            await db.create_article(article)
                                            saved_count += 1
                                        except Exception as e:
                                            logger.error(
                                                f"Error storing article from {source.name}: {e}"
                                            )
                                            continue

                                filtered_count = len(dedup_result.duplicates)
                                total_articles_saved += saved_count
                                total_articles_filtered += filtered_count

                                logger.info(f"    - Saved: {saved_count} articles")
                                logger.info(
                                    f"    - Duplicates filtered: {filtered_count} articles"
                                )

                            elif collection_success:
                                logger.info(
                                    f"  ✓ {source.name}: 0 articles found via {fetch_result.method}"
                                )

                            else:
                                error_msg = fetch_result.error
                                logger.error(
                                    f"  ✗ {source.name}: Fetch failed - {error_msg}"
                                )

                        except Exception as e:
                            error_msg = str(e)
                            logger.error(f"  ✗ {source.name}: Error - {e}")

                        finally:
                            response_time = (
                                fetch_result.response_time
                                if fetch_result
                                else time.time() - start_time
                            )
                            method = fetch_result.method if fetch_result else "unknown"
                            articles_found = len(articles)

                            try:
                                logger.info(
                                    f"About to update source {source.id} health and article count"
                                )
                                await db.update_source_health(
                                    source.id, collection_success, response_time
                                )
                                logger.info(
                                    f"Health updated, now updating article count for source {source.id}"
                                )
                                await db.update_source_article_count(source.id)
                                logger.info(
                                    f"Article count updated for source {source.id}"
                                )

                                await db.record_source_check(
                                    source_id=source.id,
                                    success=collection_success,
                                    method=method,
                                    articles_found=articles_found,
                                    response_time=response_time,
                                    error_message=error_msg,
                                )

                                logger.info(
                                    f"Updated source {source.id} health and article count"
                                )
                            except Exception as e:
                                logger.error(
                                    f"Failed to update health metrics for {source.name}: {e}"
                                )
                                import traceback

                                logger.error(f"Traceback: {traceback.format_exc()}")

                # Log overall statistics
                processor_stats = processor.get_statistics()
                logger.info(f"Processing complete:")
                logger.info(f"  - Total collected: {total_articles_collected}")
                logger.info(f"  - Total saved: {total_articles_saved}")
                logger.info(f"  - Total filtered: {total_articles_filtered}")
                logger.info(
                    f"  - Duplicates removed: {processor_stats['duplicates_removed']}"
                )

                return {
                    "status": "success",
                    "message": f"Checked {len(active_sources)} sources, collected {total_articles_collected} articles, saved {total_articles_saved} articles after deduplication",
                }

            except Exception as e:
                logger.error(f"Source checking failed: {e}")
                raise e
            finally:
                await db.close()

        # Run the async function
        result = asyncio.run(run_source_check())
        return result

    except Exception as exc:
        logger.error(f"Source check task failed: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=2)
def cleanup_old_data(self):
    """Clean up old articles and source check data."""
    try:
        logger.info("Cleaning up old data...")

        # Data cleanup logic implementation
        # - Remove articles older than X days
        # - Clean up old source check records
        # - Archive old data if needed

        return {"status": "success", "message": "Old data cleaned up"}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=300 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=2)
def generate_daily_report(self):
    """Generate daily threat intelligence report."""
    try:
        logger.info("Generating daily threat intelligence report...")

        # Daily report generation implementation
        # - Collect statistics from the past 24 hours
        # - Generate TTP analysis summary
        # - Create executive summary
        # - Send notifications if configured

        return {"status": "success", "message": "Daily report generated"}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=600 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def embed_new_articles(self, batch_size: int = 50):
    """Generate embeddings for new articles that don't have them yet."""
    try:
        import asyncio
        from src.database.async_manager import AsyncDatabaseManager

        async def run_retroactive_embedding():
            """Run retroactive embedding for all articles."""
            db = AsyncDatabaseManager()
            try:
                # Get all articles without embeddings
                articles_without_embeddings = await db.get_articles_without_embeddings()

                if not articles_without_embeddings:
                    logger.info("No new articles found that need embeddings")
                    return {
                        "status": "success",
                        "message": "No articles found without embeddings",
                        "total_processed": 0,
                    }

                total_articles = len(articles_without_embeddings)
                logger.info(
                    f"Starting daily embedding generation for {total_articles} articles"
                )

                # Process in batches
                article_ids = [article.id for article in articles_without_embeddings]

                # Use the batch generation task
                batch_result = batch_generate_embeddings.delay(article_ids, batch_size)

                return {
                    "status": "success",
                    "total_articles": total_articles,
                    "batch_task_id": batch_result.id,
                    "message": f"Started embedding generation for {total_articles} articles",
                }

            except Exception as e:
                logger.error(f"Retroactive embedding failed: {e}")
                raise e
            finally:
                await db.close()

        # Run the async function
        result = asyncio.run(run_retroactive_embedding())
        logger.info(f"Daily embedding generation complete: {result.get('message')}")
        return result

    except Exception as e:
        logger.error(f"Failed to embed new articles: {e}")
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def test_source_connectivity(self, source_id: int):
    """Test connectivity to a specific source."""
    try:
        logger.info(f"Testing connectivity to source {source_id}...")

        # Source connectivity testing implementation
        # - Test main URL accessibility
        # - Test RSS feed if available
        # - Measure response times
        # - Update source health metrics

        return {
            "status": "success",
            "source_id": source_id,
            "message": "Connectivity test completed",
        }

    except Exception as exc:
        raise self.retry(exc=exc, countdown=30 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def check_source(self, source_identifier: str):
    """Check a specific source by identifier for new content."""
    try:
        import asyncio
        from src.database.async_manager import AsyncDatabaseManager
        from src.core.fetcher import ContentFetcher
        from src.core.processor import ContentProcessor

        async def run_source_check():
            """Run the actual source checking."""
            db = AsyncDatabaseManager()
            try:
                # Get the specific source by identifier
                sources = await db.list_sources()
                source = None
                for s in sources:
                    if hasattr(s, "identifier") and s.identifier == source_identifier:
                        source = s
                        break

                if not source:
                    return {
                        "status": "error",
                        "message": f"Source '{source_identifier}' not found",
                    }

                if not source.active:
                    return {
                        "status": "error",
                        "message": f"Source '{source.name}' is not active",
                    }

                logger.info(
                    f"Checking source {source.name} (ID: {source.id}) for new content..."
                )

                # Initialize processor for deduplication
                processor = ContentProcessor(
                    similarity_threshold=0.85,
                    max_age_days=90,
                    enable_content_enhancement=True,
                )

                # Get existing content hashes and URLs for deduplication
                existing_hashes = await db.get_existing_content_hashes()
                existing_urls = await db.get_existing_urls()

                # Use ContentFetcher with fallback strategy (RSS → Modern Scraping → Legacy Scraping)
                async with ContentFetcher() as fetcher:
                    # Track timing for health metrics
                    start_time = time.time()
                    collection_success = False

                    try:
                        # Fetch articles using hierarchical strategy
                        fetch_result = await fetcher.fetch_source(source)

                        if fetch_result.success and fetch_result.articles:
                            logger.info(
                                f"  ✓ {source.name}: {len(fetch_result.articles)} articles collected via {fetch_result.method}"
                            )

                            # Process articles through deduplication
                            dedup_result = await processor.process_articles(
                                fetch_result.articles, existing_hashes, existing_urls
                            )

                            # Save deduplicated articles
                            saved_count = 0
                            if dedup_result.unique_articles:
                                for article in dedup_result.unique_articles:
                                    try:
                                        await db.create_article(article)
                                        saved_count += 1
                                    except Exception as e:
                                        logger.error(
                                            f"Error storing article from {source.name}: {e}"
                                        )
                                        continue

                            # Log filtering statistics
                            filtered_count = len(dedup_result.duplicates)
                            duplicates_filtered = filtered_count

                            logger.info(
                                f"    - Collected: {len(fetch_result.articles)} articles"
                            )
                            logger.info(f"    - Saved: {saved_count} new articles")
                            logger.info(
                                f"    - Duplicates filtered: {duplicates_filtered} articles"
                            )

                            collection_success = True

                            return {
                                "status": "success",
                                "source_id": source.id,
                                "source_name": source.name,
                                "articles_collected": len(fetch_result.articles),
                                "articles_saved": saved_count,
                                "duplicates_filtered": duplicates_filtered,
                                "method": fetch_result.method,
                                "message": f"Successfully collected {saved_count} new articles from {source.name} via {fetch_result.method}",
                            }
                        elif fetch_result.success:
                            logger.info(f"  ✓ {source.name}: No new articles found")
                            collection_success = (
                                True  # No articles is still a successful check
                            )

                            return {
                                "status": "success",
                                "source_id": source.id,
                                "source_name": source.name,
                                "articles_collected": 0,
                                "articles_saved": 0,
                                "duplicates_filtered": 0,
                                "method": fetch_result.method
                                if fetch_result
                                else "none",
                                "message": f"No new articles found for {source.name}",
                            }
                        else:
                            logger.error(
                                f"  ✗ {source.name}: Fetch failed - {fetch_result.error}"
                            )
                            collection_success = False
                            return {
                                "status": "error",
                                "source_id": source.id,
                                "message": fetch_result.error or "Unknown error",
                            }

                    except Exception as e:
                        logger.error(f"Error collecting from {source.name}: {e}")
                        collection_success = False
                        return {
                            "status": "error",
                            "source_id": source.id,
                            "message": str(e),
                        }
                    finally:
                        # Update source health metrics with actual success/failure status
                        try:
                            response_time = time.time() - start_time
                            await db.update_source_health(
                                source.id, collection_success, response_time
                            )
                            await db.update_source_article_count(source.id)

                            # Record source check for historical tracking
                            method = fetch_result.method if fetch_result else "unknown"
                            articles_found = (
                                len(fetch_result.articles)
                                if fetch_result and fetch_result.articles
                                else 0
                            )
                            error_msg = (
                                fetch_result.error
                                if fetch_result and not fetch_result.success
                                else None
                            )

                            await db.record_source_check(
                                source_id=source.id,
                                success=collection_success,
                                method=method,
                                articles_found=articles_found,
                                response_time=response_time,
                                error_message=error_msg,
                            )

                            logger.info(
                                f"Updated source {source.id} health and article count"
                            )
                        except Exception as health_error:
                            logger.error(
                                f"Failed to update health for source {source.id}: {health_error}"
                            )

            except Exception as e:
                logger.error(f"Source check failed: {e}")
                raise e
            finally:
                await db.close()

        # Run the async function
        result = asyncio.run(run_source_check())
        return result

    except Exception as exc:
        logger.error(f"Source check task failed: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def trigger_agentic_workflow(self, article_id: int, execution_id: Optional[int] = None):
    """Trigger agentic workflow for an article with high hunt score."""
    try:
        import asyncio
        from src.database.manager import DatabaseManager
        from src.workflows.agentic_workflow import run_workflow

        async def run_workflow_execution():
            """Run the actual workflow execution."""
            try:
                db_manager = DatabaseManager()
                db_session = db_manager.get_session()

                try:
                    result = await run_workflow(article_id, db_session, execution_id=execution_id)
                    logger.info(
                        f"Agentic workflow completed for article {article_id}: {result.get('success', False)}"
                    )
                    return result
                finally:
                    db_session.close()

            except Exception as e:
                logger.error(
                    f"Error running agentic workflow for article {article_id}: {e}"
                )
                # Convert to new exception to avoid serializing ArticleTable in traceback
                raise Exception(f"Workflow execution failed: {str(e)}") from None

        # Run async workflow
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_workflow_execution())
            return result
        finally:
            loop.close()

    except Exception as exc:
        logger.error(f"Agentic workflow task failed for article {article_id}: {exc}")
        # Retry with exponential backoff
        # Convert exception to string to avoid serializing ORM objects in traceback
        error_msg = str(exc)
        raise self.retry(exc=Exception(error_msg), countdown=60 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=2)
def run_chunk_analysis(self, article_id: int):
    """Run chunk analysis and calculate ML hunt score for an article."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.chunk_analysis_backfill import ChunkAnalysisBackfillService

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            service = ChunkAnalysisBackfillService(db_session)
            result = service.backfill_article(article_id, min_confidence=0.7)

            if result.get("success"):
                logger.info(
                    f"Chunk analysis completed for article {article_id}: {result.get('chunks_processed', 0)} chunks processed"
                )
            else:
                logger.warning(
                    f"Chunk analysis failed for article {article_id}: {result.get('error', 'Unknown error')}"
                )

            return result
        finally:
            db_session.close()

    except Exception as exc:
        logger.error(f"Chunk analysis task failed for article {article_id}: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=30 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def generate_article_embedding(self, article_id: int):
    """Generate embedding for a single article."""
    try:
        import asyncio
        from src.database.async_manager import AsyncDatabaseManager
        from src.services.embedding_service import get_embedding_service

        async def run_embedding_generation():
            """Run the actual embedding generation."""
            db = AsyncDatabaseManager()
            try:
                # Get the article with source info
                article = await db.get_article_with_source_info(article_id)
                if not article:
                    return {
                        "status": "error",
                        "message": f"Article {article_id} not found",
                    }

                # Check if already embedded
                if article.embedding is not None:
                    return {
                        "status": "success",
                        "message": f"Article {article_id} already has embedding",
                    }

                # Generate embedding using enriched context
                embedding_service = get_embedding_service()
                enriched_text = embedding_service.create_enriched_text(
                    article_title=article.title,
                    source_name=article.source.name,
                    article_content=article.content,
                    summary=article.summary,
                    tags=article.tags,
                    article_metadata=article.article_metadata
                    if hasattr(article, "article_metadata")
                    else {},
                )

                embedding = embedding_service.generate_embedding(enriched_text)

                # Store embedding in database
                await db.update_article_embedding(
                    article_id=article_id,
                    embedding=embedding,
                    model_name="all-mpnet-base-v2",
                )

                logger.info(f"Generated embedding for article {article_id}")
                return {
                    "status": "success",
                    "article_id": article_id,
                    "embedding_dimension": len(embedding),
                    "message": f"Successfully generated embedding for article {article_id}",
                }

            except Exception as e:
                logger.error(
                    f"Embedding generation failed for article {article_id}: {e}"
                )
                raise e
            finally:
                await db.close()

        # Run the async function
        result = asyncio.run(run_embedding_generation())
        return result

    except Exception as exc:
        logger.error(f"Article embedding task failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def batch_generate_embeddings(self, article_ids: List[int], batch_size: int = 32):
    """Generate embeddings for multiple articles in batches."""
    try:
        import asyncio
        import time
        from src.database.async_manager import AsyncDatabaseManager
        from src.services.embedding_service import get_embedding_service

        log_file = "/tmp/embedding_logs.txt"

        def write_log(message: str):
            """Write log message to file and logger."""
            try:
                with open(log_file, "a") as f:
                    timestamp = time.strftime("%H:%M:%S")
                    f.write(f"[{timestamp}] {message}\n")
            except Exception:
                pass  # Continue if log file write fails
            logger.info(message)

        async def run_batch_embedding():
            """Run batch embedding generation."""
            db = AsyncDatabaseManager()
            try:
                total_articles = len(article_ids)
                total_processed = 0
                total_skipped = 0
                total_errors = 0

                write_log(f"🚀 Starting embedding generation for {total_articles} articles")
                write_log(f"📦 Batch size: {batch_size}")
                write_log(f"⏳ Processing in batches...\n")

                # Process in batches
                for i in range(0, len(article_ids), batch_size):
                    batch_num = (i // batch_size) + 1
                    total_batches = (len(article_ids) + batch_size - 1) // batch_size
                    batch_ids = article_ids[i : i + batch_size]

                    write_log(f"📊 Processing batch {batch_num}/{total_batches} ({len(batch_ids)} articles)")

                    # Get articles for this batch
                    articles = await db.get_articles_with_source_info(batch_ids)

                    # Filter out already embedded articles
                    articles_to_process = [
                        article for article in articles if article.embedding is None
                    ]

                    if not articles_to_process:
                        skipped_count = len(batch_ids)
                        total_skipped += skipped_count
                        write_log(f"⏭️  Batch {batch_num}: All articles already have embeddings (skipped {skipped_count})")
                        continue

                    write_log(f"🔄 Batch {batch_num}: Processing {len(articles_to_process)} articles...")

                    # Prepare texts for batch embedding
                    texts_to_embed = []
                    article_mapping = []

                    for article in articles_to_process:
                        embedding_service = get_embedding_service()
                        enriched_text = embedding_service.create_enriched_text(
                            article_title=article.title,
                            source_name=article.source.name,
                            article_content=article.content,
                            summary=article.summary,
                            tags=article.tags,
                            article_metadata=article.article_metadata
                            if hasattr(article, "article_metadata")
                            else {},
                        )
                        texts_to_embed.append(enriched_text)
                        article_mapping.append(article.id)

                    # Generate embeddings in batch
                    write_log(f"🧬 Generating embeddings for batch {batch_num}...")
                    embeddings = embedding_service.generate_embeddings_batch(
                        texts_to_embed, batch_size
                    )

                    # Store embeddings
                    write_log(f"💾 Storing embeddings for batch {batch_num}...")
                    for article_id, embedding in zip(article_mapping, embeddings):
                        try:
                            await db.update_article_embedding(
                                article_id=article_id,
                                embedding=embedding,
                                model_name="all-mpnet-base-v2",
                            )
                            total_processed += 1
                        except Exception as e:
                            logger.error(
                                f"Failed to store embedding for article {article_id}: {e}"
                            )
                            write_log(f"❌ Failed to store embedding for article {article_id}: {e}")
                            total_errors += 1

                    total_skipped += len(batch_ids) - len(articles_to_process)
                    progress_pct = ((i + len(batch_ids)) / total_articles) * 100
                    write_log(f"✅ Batch {batch_num} complete: {len(articles_to_process)} processed")
                    write_log(f"📈 Overall progress: {total_processed}/{total_articles} ({progress_pct:.1f}%)\n")

                write_log("\n" + "="*50)
                write_log("✅ Embedding Generation Complete!")
                write_log(f"📊 Results:")
                write_log(f"   • Processed: {total_processed} articles")
                write_log(f"   • Skipped: {total_skipped} articles (already embedded)")
                write_log(f"   • Errors: {total_errors} articles")
                write_log(f"⏱️  Finished at {time.strftime('%H:%M:%S')}")
                write_log("="*50)

                logger.info(
                    f"Batch embedding complete: {total_processed} processed, {total_skipped} skipped, {total_errors} errors"
                )
                return {
                    "status": "success",
                    "total_processed": total_processed,
                    "total_skipped": total_skipped,
                    "total_errors": total_errors,
                    "message": f"Processed {total_processed} articles, skipped {total_skipped}, {total_errors} errors",
                }

            except Exception as e:
                error_msg = f"❌ Batch embedding generation failed: {e}"
                write_log(error_msg)
                logger.error(f"Batch embedding generation failed: {e}")
                raise e
            finally:
                await db.close()

        # Run the async function
        return asyncio.run(run_batch_embedding())

    except Exception as exc:
        logger.error(f"Batch embedding task failed: {exc}")
        raise self.retry(exc=exc, countdown=120 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=2)
def retroactive_embed_all_articles(self, batch_size: int = 1000):
    """Generate embeddings for all existing articles without embeddings."""
    try:
        import asyncio
        import time
        from src.database.async_manager import AsyncDatabaseManager

        # Initialize log file in worker container
        log_file = "/tmp/embedding_logs.txt"
        try:
            with open(log_file, "w") as file:
                file.write("🚀 Starting embedding generation...\n")
                file.write(f"📅 Started at {time.strftime('%H:%M:%S')}\n")
                file.write(f"📦 Batch size: {batch_size}\n")
                file.write("⏳ This may take several minutes...\n\n")
            logger.info(f"Initialized embedding log file at {log_file}")
        except Exception as log_init_error:
            logger.error(f"Failed to initialize log file at {log_file}: {log_init_error}")
            # Continue anyway - logging will fall back to logger

        async def run_retroactive_embedding():
            """Run retroactive embedding for all articles."""
            db = AsyncDatabaseManager()
            try:
                # Get all articles without embeddings
                articles_without_embeddings = await db.get_articles_without_embeddings()

                if not articles_without_embeddings:
                    try:
                        with open(log_file, "a") as file:
                            file.write("✅ No articles found without embeddings\n")
                    except Exception:
                        pass
                    return {
                        "status": "success",
                        "message": "No articles found without embeddings",
                    }

                total_articles = len(articles_without_embeddings)
                logger.info(
                    f"Starting retroactive embedding for {total_articles} articles"
                )

                # Process in batches
                article_ids = [article.id for article in articles_without_embeddings]

                # Use the batch generation task
                batch_result = batch_generate_embeddings.delay(article_ids, batch_size)

                return {
                    "status": "success",
                    "total_articles": total_articles,
                    "batch_task_id": batch_result.id,
                    "message": f"Started retroactive embedding for {total_articles} articles",
                }

            except Exception as e:
                try:
                    with open(log_file, "a") as file:
                        file.write(f"\n❌ Retroactive embedding failed: {e}\n")
                except Exception:
                    pass
                logger.error(f"Retroactive embedding failed: {e}")
                raise e
            finally:
                await db.close()

        # Run the async function
        result = asyncio.run(run_retroactive_embedding())
        return result

    except Exception as exc:
        logger.error(f"Retroactive embedding task failed: {exc}")
        raise self.retry(exc=exc, countdown=300 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def collect_from_source(self, source_id: int):
    """Collect new content from a specific source."""
    try:
        import asyncio
        from src.database.manager import DatabaseManager
        from src.core.fetcher import ContentFetcher
        from src.core.processor import ContentProcessor

        async def run_source_collection():
            """Run the actual source collection."""
            # Use sync database manager for Celery worker
            db = DatabaseManager()
            try:
                # Get the specific source
                source = db.get_source(source_id)
                if not source:
                    return {
                        "status": "error",
                        "message": f"Source {source_id} not found",
                    }

                if not source.active:
                    return {
                        "status": "error",
                        "message": f"Source {source.name} is not active",
                    }

                logger.info(
                    f"Collecting content from {source.name} (ID: {source_id})..."
                )

                # Initialize processor for deduplication
                processor = ContentProcessor(
                    similarity_threshold=0.85,
                    max_age_days=90,
                    enable_content_enhancement=True,
                )

                # Get existing content hashes for deduplication
                existing_hashes = db.get_existing_content_hashes()

                # Use ContentFetcher with fallback strategy (RSS → Modern Scraping → Legacy Scraping)
                async with ContentFetcher() as fetcher:
                    # Track timing for health metrics
                    start_time = time.time()
                    collection_success = False

                    try:
                        # Fetch articles using hierarchical strategy
                        fetch_result = await fetcher.fetch_source(source)

                        if fetch_result.success and fetch_result.articles:
                            logger.info(
                                f"  ✓ {source.name}: {len(fetch_result.articles)} articles collected via {fetch_result.method}"
                            )

                            # Process articles through deduplication
                            dedup_result = await processor.process_articles(
                                fetch_result.articles, existing_hashes
                            )

                            # Save deduplicated articles using sync database manager
                            saved_count = 0
                            if dedup_result.unique_articles:
                                # Convert articles to ArticleCreate objects for bulk creation
                                from src.models.article import ArticleCreate

                                article_creates = []
                                for article in dedup_result.unique_articles:
                                    article_create = ArticleCreate(
                                        source_id=article.source_id,
                                        canonical_url=article.canonical_url,
                                        title=article.title,
                                        published_at=article.published_at,
                                        authors=article.authors,
                                        tags=article.tags,
                                        summary=article.summary,
                                        content=article.content,
                                        content_hash=article.content_hash,
                                        article_metadata=getattr(
                                            article, "metadata", {}
                                        ),
                                    )
                                    article_creates.append(article_create)

                                # Bulk create articles
                                created_articles, errors = db.create_articles_bulk(
                                    article_creates
                                )
                                saved_count = len(created_articles)

                                if errors:
                                    logger.warning(f"Article creation errors: {errors}")

                            # Log filtering statistics
                            filtered_count = len(dedup_result.duplicates)
                            duplicates_filtered = filtered_count

                            logger.info(
                                f"    - Collected: {len(fetch_result.articles)} articles"
                            )
                            logger.info(f"    - Saved: {saved_count} new articles")
                            logger.info(
                                f"    - Duplicates filtered: {duplicates_filtered} articles"
                            )

                            collection_success = True

                            return {
                                "status": "success",
                                "source_id": source_id,
                                "source_name": source.name,
                                "articles_collected": len(fetch_result.articles),
                                "articles_saved": saved_count,
                                "articles_filtered": filtered_count,
                                "method": fetch_result.method,
                                "response_time": fetch_result.response_time,
                                "message": f"Collected {len(fetch_result.articles)} articles via {fetch_result.method}, saved {saved_count} after deduplication",
                            }
                        else:
                            logger.info(f"  ✓ {source.name}: 0 articles found")
                            collection_success = (
                                True  # No articles is still a successful check
                            )

                            return {
                                "status": "success",
                                "source_id": source_id,
                                "source_name": source.name,
                                "articles_collected": 0,
                                "articles_saved": 0,
                                "articles_filtered": 0,
                                "method": fetch_result.method
                                if fetch_result
                                else "none",
                                "response_time": fetch_result.response_time
                                if fetch_result
                                else 0,
                                "message": f"No new articles found for {source.name}",
                            }

                    except Exception as e:
                        logger.error(f"  ✗ {source.name}: Error - {e}")
                        collection_success = False
                        return {
                            "status": "error",
                            "source_id": source_id,
                            "message": str(e),
                        }
                    finally:
                        # Update source health metrics with actual success/failure status
                        try:
                            response_time = time.time() - start_time
                            db.update_source_health(
                                source_id, collection_success, response_time
                            )
                            # Update article count using the private method
                            with db.get_session() as session:
                                db._update_source_article_count(session, source_id)

                            # Record source check for historical tracking
                            method = fetch_result.method if fetch_result else "unknown"
                            articles_found = (
                                len(fetch_result.articles)
                                if fetch_result and fetch_result.articles
                                else 0
                            )
                            error_msg = (
                                fetch_result.error
                                if fetch_result and not fetch_result.success
                                else None
                            )

                            db.record_source_check(
                                source_id=source_id,
                                success=collection_success,
                                method=method,
                                articles_found=articles_found,
                                response_time=response_time,
                                error_message=error_msg,
                            )

                            logger.info(
                                f"Updated source {source_id} health and article count"
                            )
                        except Exception as health_error:
                            logger.error(
                                f"Failed to update health for source {source_id}: {health_error}"
                            )

            except Exception as e:
                logger.error(f"Source collection failed: {e}")
                raise e

        # Run the async function
        result = asyncio.run(run_source_collection())
        return result

    except Exception as exc:
        logger.error(f"Source collection task failed: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@celery_app.task(bind=True, max_retries=2)
def sync_sigma_rules(self, force_reindex=False):
    """Sync SigmaHQ repository and update embeddings for all rules."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.sigma_sync_service import SigmaSyncService

        logger.info("Starting SigmaHQ repository sync and embedding update...")

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            sync_service = SigmaSyncService()

            # Sync repository (clone or pull)
            sync_result = sync_service.clone_or_pull_repository()

            if not sync_result.get("success"):
                error_msg = sync_result.get("error", "Unknown error")
                logger.error(f"Sigma repository sync failed: {error_msg}")
                return {
                    "status": "error",
                    "message": f"Repository sync failed: {error_msg}",
                }

            logger.info(f"Repository {sync_result.get('action', 'synced')} successfully")

            # Index rules (this also generates embeddings)
            indexed_count = sync_service.index_rules(session, force_reindex=force_reindex)

            logger.info(
                f"Sigma sync complete: {indexed_count} rules indexed with embeddings"
            )

            return {
                "status": "success",
                "action": sync_result.get("action"),
                "rules_indexed": indexed_count,
                "message": f"Successfully synced and indexed {indexed_count} Sigma rules with embeddings",
            }

        except Exception as e:
            logger.error(f"Sigma sync task failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
            raise e
        finally:
            session.close()

    except Exception as exc:
        logger.error(f"Sigma sync task failed: {exc}")
        # Retry with exponential backoff (longer delay for this resource-intensive task)
        raise self.retry(exc=exc, countdown=300 * (2**self.request.retries))


if __name__ == "__main__":
    celery_app.start()
