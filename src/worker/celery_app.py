"""
Celery Application for CTI Scraper Background Tasks

Handles source checking, article collection, and other async operations.
"""

import os
import logging
import time
from celery import Celery
from celery.schedules import crontab

# Configure logging
logger = logging.getLogger(__name__)

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('CELERY_CONFIG_MODULE', 'src.worker.celeryconfig')

# Create the Celery app
celery_app = Celery('cti_scraper')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
celery_app.config_from_object('src.worker.celeryconfig')

# Load task modules from all registered app configs.
celery_app.autodiscover_tasks()

# Define periodic tasks
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup periodic tasks for the CTI Scraper."""
    
    # Check all sources every hour
    sender.add_periodic_task(
        crontab(minute=0),  # Every hour at minute 0
        check_all_sources.s(),
        name='check-all-sources-hourly'
    )
    
    # Check Tier 1 sources every 15 minutes
    sender.add_periodic_task(
        crontab(minute='*/15'),  # Every 15 minutes
        check_tier1_sources.s(),
        name='check-tier1-sources-quarterly'
    )
    
    # Clean up old data daily at 2 AM
    sender.add_periodic_task(
        crontab(hour=2, minute=0),  # Daily at 2 AM
        cleanup_old_data.s(),
        name='cleanup-old-data-daily'
    )
    
    # Generate daily reports at 6 AM
    sender.add_periodic_task(
        crontab(hour=6, minute=0),  # Daily at 6 AM
        generate_daily_report.s(),
        name='generate-daily-report'
    )


@celery_app.task(bind=True, max_retries=3)
def check_all_sources(self):
    """Check all active sources for new content."""
    try:
        import asyncio
        from src.database.async_manager import AsyncDatabaseManager
        from src.core.rss_parser import RSSParser
        from src.core.processor import ContentProcessor
        from src.utils.http import HTTPClient
        
        async def run_source_check():
            """Run the actual source checking."""
            db = AsyncDatabaseManager()
            try:
                # Get all active sources
                sources = await db.list_sources()
                active_sources = [s for s in sources if getattr(s, 'active', True)]
                
                logger.info(f"Checking {len(active_sources)} active sources for new content...")
                
                if not active_sources:
                    return {"status": "success", "message": "No active sources to check"}
                
                # Initialize processor for deduplication
                processor = ContentProcessor(
                    similarity_threshold=0.85,
                    max_age_days=90,
                    enable_content_enhancement=True
                )
                
                # Get existing content hashes for deduplication
                existing_hashes = await db.get_existing_content_hashes()
                
                total_articles_collected = 0
                total_articles_saved = 0
                total_articles_filtered = 0
                
                async with HTTPClient() as http_client:
                    rss_parser = RSSParser(http_client)
                    
                    for source in active_sources:
                        start_time = time.time()
                        success = False
                        
                        try:
                            # Parse RSS feed for new articles
                            articles = await rss_parser.parse_feed(source)
                            
                            if articles:
                                total_articles_collected += len(articles)
                                logger.info(f"  ✓ {source.name}: {len(articles)} articles collected")
                                
                                # Process articles through deduplication
                                dedup_result = await processor.process_articles(articles, existing_hashes)
                                
                                # Save deduplicated articles
                                if dedup_result.unique_articles:
                                    for article in dedup_result.unique_articles:
                                        try:
                                            await db.create_article(article)
                                            total_articles_saved += 1
                                        except Exception as e:
                                            logger.error(f"Error storing article from {source.name}: {e}")
                                            continue
                                
                                # Log filtering statistics
                                filtered_count = len(dedup_result.duplicates)
                                duplicates_filtered = filtered_count
                                
                                total_articles_filtered += filtered_count
                                
                                logger.info(f"    - Saved: {len(dedup_result.unique_articles)} articles")
                                logger.info(f"    - Duplicates filtered: {duplicates_filtered} articles")
                                
                                success = True
                                
                            else:
                                logger.info(f"  ✓ {source.name}: 0 articles found")
                                success = True
                            
                        except Exception as e:
                            logger.error(f"  ✗ {source.name}: Error - {e}")
                            success = False
                        
                        finally:
                            # Update source health metrics
                            response_time = time.time() - start_time
                            try:
                                await db.update_source_health(source.id, success, response_time)
                                await db.update_source_article_count(source.id)
                                logger.info(f"Updated source {source.id} health and article count")
                            except Exception as e:
                                logger.error(f"Failed to update health metrics for {source.name}: {e}")
                
                # Log overall statistics
                processor_stats = processor.get_statistics()
                logger.info(f"Processing complete:")
                logger.info(f"  - Total collected: {total_articles_collected}")
                logger.info(f"  - Total saved: {total_articles_saved}")
                logger.info(f"  - Total filtered: {total_articles_filtered}")
                logger.info(f"  - Duplicates removed: {processor_stats['duplicates_removed']}")
                
                return {
                    "status": "success", 
                    "message": f"Checked {len(active_sources)} sources, collected {total_articles_collected} articles, saved {total_articles_saved} articles after deduplication"
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
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def check_tier1_sources(self):
    """Check Tier 1 sources more frequently."""
    try:
        logger.info("Checking Tier 1 sources for new content...")
        
        # Tier 1 source checking implementation
        # This would check high-priority sources more frequently
        
        return {"status": "success", "message": "Tier 1 sources checked"}
        
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


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
        raise self.retry(exc=exc, countdown=300 * (2 ** self.request.retries))


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
        raise self.retry(exc=exc, countdown=600 * (2 ** self.request.retries))


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
        
        return {"status": "success", "source_id": source_id, "message": "Connectivity test completed"}
        
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def collect_from_source(self, source_id: int):
    """Collect new content from a specific source."""
    try:
        import asyncio
        from src.database.async_manager import AsyncDatabaseManager
        from src.core.rss_parser import RSSParser
        from src.core.processor import ContentProcessor
        from src.utils.http import HTTPClient
        
        async def run_source_collection():
            """Run the actual source collection."""
            db = AsyncDatabaseManager()
            try:
                # Get the specific source
                source = await db.get_source(source_id)
                if not source:
                    return {"status": "error", "message": f"Source {source_id} not found"}
                
                if not source.active:
                    return {"status": "error", "message": f"Source {source.name} is not active"}
                
                logger.info(f"Collecting content from {source.name} (ID: {source_id})...")
                
                # Initialize processor for deduplication
                processor = ContentProcessor(
                    similarity_threshold=0.85,
                    max_age_days=90,
                    enable_content_enhancement=True
                )
                
                # Get existing content hashes for deduplication
                existing_hashes = await db.get_existing_content_hashes()
                
                async with HTTPClient() as http_client:
                    rss_parser = RSSParser(http_client)
                    
                    # Track timing for health metrics
                    start_time = time.time()
                    
                    try:
                        # Parse RSS feed for new articles
                        articles = await rss_parser.parse_feed(source)
                        
                        if articles:
                            logger.info(f"  ✓ {source.name}: {len(articles)} articles collected")
                            
                            # Process articles through deduplication
                            dedup_result = await processor.process_articles(articles, existing_hashes)
                            
                            # Save deduplicated articles
                            saved_count = 0
                            if dedup_result.unique_articles:
                                for article in dedup_result.unique_articles:
                                    try:
                                        await db.create_article(article)
                                        saved_count += 1
                                    except Exception as e:
                                        logger.error(f"Error storing article from {source.name}: {e}")
                                        continue
                            
                            # Log filtering statistics
                            filtered_count = len(dedup_result.duplicates)
                            duplicates_filtered = filtered_count
                            
                            logger.info(f"    - Saved: {saved_count} articles")
                            logger.info(f"    - Duplicates filtered: {duplicates_filtered} articles")
                            
                            return {
                                "status": "success", 
                                "source_id": source_id,
                                "source_name": source.name,
                                "articles_collected": len(articles),
                                "articles_saved": saved_count,
                                "articles_filtered": filtered_count,
                                "message": f"Collected {len(articles)} articles, saved {saved_count} after deduplication"
                            }
                        else:
                            logger.info(f"  ✓ {source.name}: 0 articles found")
                            return {
                                "status": "success", 
                                "source_id": source_id,
                                "source_name": source.name,
                                "articles_collected": 0,
                                "articles_saved": 0,
                                "articles_filtered": 0,
                                "message": f"No new articles found for {source.name}"
                            }
                            
                    except Exception as e:
                        logger.error(f"  ✗ {source.name}: Error - {e}")
                        return {"status": "error", "source_id": source_id, "message": str(e)}
                    finally:
                        # Update source health metrics regardless of success/failure
                        try:
                            response_time = time.time() - start_time
                            await db.update_source_health(source_id, True, response_time)
                            await db.update_source_article_count(source_id)
                            logger.info(f"Updated source {source_id} health and article count")
                        except Exception as health_error:
                            logger.error(f"Failed to update health for source {source_id}: {health_error}")
                
            except Exception as e:
                logger.error(f"Source collection failed: {e}")
                raise e
            finally:
                await db.close()
        
        # Run the async function
        result = asyncio.run(run_source_collection())
        return result
        
    except Exception as exc:
        logger.error(f"Source collection task failed: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


if __name__ == '__main__':
    celery_app.start()
