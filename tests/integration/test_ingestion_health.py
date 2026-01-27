"""
Tests to verify that article ingestion is actually working.

These tests check for:
- Recent article discovery activity
- Source check activity
- Ingestion pipeline health
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import ArticleTable, SourceTable, SourceCheckTable


@pytest.mark.integration
class TestIngestionHealth:
    """
    Test that article ingestion is actually functioning.
    
    These tests verify:
    - Articles are being discovered recently (within 48 hours)
    - Active sources are being checked regularly
    - Source checks are succeeding
    - End-to-end ingestion pipeline health
    """
    
    @pytest.fixture
    def db_manager(self):
        """Get database manager instance."""
        return AsyncDatabaseManager()
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_recent_article_ingestion(self, db_manager: AsyncDatabaseManager):
        """
        Verify that articles have been discovered recently.
        
        This test checks if any articles were discovered in the last 48 hours.
        If no articles were discovered, it indicates ingestion may be broken.
        """
        async with db_manager.get_session() as session:
            # Check for articles discovered in the last 48 hours
            cutoff_time = datetime.utcnow() - timedelta(hours=48)
            
            recent_articles_query = select(func.count(ArticleTable.id)).where(
                and_(
                    ArticleTable.discovered_at >= cutoff_time,
                    ArticleTable.archived == False
                )
            )
            recent_count = await session.scalar(recent_articles_query)
            
            # Get total article count for context
            total_query = select(func.count(ArticleTable.id)).where(
                ArticleTable.archived == False
            )
            total_count = await session.scalar(total_query)
            
            # Get latest article discovery time
            latest_query = select(func.max(ArticleTable.discovered_at)).where(
                ArticleTable.archived == False
            )
            latest_discovery = await session.scalar(latest_query)
            
            # Assertions
            assert recent_count is not None, "Failed to query recent articles"
            assert total_count is not None, "Failed to query total articles"
            
            # If we have articles in the system, check recent activity
            if total_count > 0:
                if recent_count == 0:
                    # No recent articles - check how old the latest article is
                    if latest_discovery:
                        hours_ago = (datetime.utcnow() - latest_discovery).total_seconds() / 3600
                        pytest.fail(
                            f"Ingestion appears broken: No articles discovered in last 48 hours. "
                            f"Latest article was discovered {hours_ago:.1f} hours ago. "
                            f"Total articles in system: {total_count}"
                        )
                    else:
                        pytest.fail(
                            "Ingestion appears broken: No recent articles and no discovery timestamp found. "
                            f"Total articles in system: {total_count}"
                        )
                else:
                    # Recent activity found - verify it's actually recent
                    assert recent_count > 0, f"Expected recent articles but count is {recent_count}"
                    if latest_discovery:
                        hours_ago = (datetime.utcnow() - latest_discovery).total_seconds() / 3600
                        assert hours_ago < 48, (
                            f"Latest article discovery is {hours_ago:.1f} hours ago, "
                            f"but recent_count={recent_count} suggests recent activity. "
                            "Data inconsistency detected."
                        )
            else:
                # No articles at all - this might be a new system
                pytest.skip(
                    "No articles in database. This may be a new system. "
                    "Run ingestion manually to populate articles before running this test."
                )
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_active_sources_being_checked(self, db_manager: AsyncDatabaseManager):
        """
        Verify that active sources are being checked regularly.
        
        This test checks if active sources have been checked within their check_frequency window.
        """
        async with db_manager.get_session() as session:
            # Get all active sources
            active_sources_query = select(SourceTable).where(
                SourceTable.active == True
            )
            result = await session.execute(active_sources_query)
            active_sources = result.scalars().all()
            
            if not active_sources:
                pytest.skip("No active sources configured. Add sources to test ingestion health.")
            
            # Check each active source
            unchecked_sources = []
            stale_sources = []
            
            for source in active_sources:
                # Calculate expected check window (check_frequency + 50% buffer for scheduling)
                check_frequency_seconds = source.check_frequency or 3600
                max_allowed_age = check_frequency_seconds * 1.5
                cutoff_time = datetime.utcnow() - timedelta(seconds=max_allowed_age)
                
                if source.last_check is None:
                    unchecked_sources.append({
                        "name": source.name,
                        "identifier": source.identifier,
                        "reason": "Never checked"
                    })
                elif source.last_check < cutoff_time:
                    hours_ago = (datetime.utcnow() - source.last_check).total_seconds() / 3600
                    stale_sources.append({
                        "name": source.name,
                        "identifier": source.identifier,
                        "last_check": source.last_check.isoformat(),
                        "hours_ago": hours_ago,
                        "check_frequency_hours": check_frequency_seconds / 3600
                    })
            
            # Build failure message if needed
            if unchecked_sources or stale_sources:
                failure_parts = []
                
                if unchecked_sources:
                    failure_parts.append(
                        f"Sources never checked ({len(unchecked_sources)}): "
                        + ", ".join([s["name"] for s in unchecked_sources])
                    )
                
                if stale_sources:
                    failure_parts.append(
                        f"Sources with stale checks ({len(stale_sources)}): "
                        + ", ".join([
                            f"{s['name']} (last checked {s['hours_ago']:.1f}h ago, "
                            f"frequency: {s['check_frequency_hours']:.1f}h)"
                            for s in stale_sources
                        ])
                    )
                
                pytest.fail(
                    f"Ingestion health check failed - sources not being checked regularly:\n"
                    + "\n".join(failure_parts)
                )
            
            # All sources are being checked regularly
            assert len(active_sources) > 0, "Should have at least one active source"
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_source_check_success_rate(self, db_manager: AsyncDatabaseManager):
        """
        Verify that source checks are succeeding.
        
        This test checks the recent source check history to ensure checks are succeeding.
        """
        async with db_manager.get_session() as session:
            # Get source checks from the last 7 days
            cutoff_time = datetime.utcnow() - timedelta(days=7)
            
            recent_checks_query = select(SourceCheckTable).where(
                SourceCheckTable.check_time >= cutoff_time
            ).order_by(SourceCheckTable.check_time.desc())
            
            result = await session.execute(recent_checks_query)
            recent_checks = result.scalars().all()
            
            if not recent_checks:
                # Check if we have any sources at all
                sources_query = select(func.count(SourceTable.id))
                source_count = await session.scalar(sources_query)
                
                if source_count == 0:
                    pytest.skip("No sources configured. Add sources to test ingestion health.")
                else:
                    pytest.fail(
                        f"No source checks recorded in the last 7 days, but {source_count} sources exist. "
                        "Ingestion may be broken - sources are not being checked."
                    )
            
            # Calculate success rate
            total_checks = len(recent_checks)
            successful_checks = sum(1 for check in recent_checks if check.success)
            success_rate = (successful_checks / total_checks) * 100 if total_checks > 0 else 0
            
            # Get failure details if any
            failed_checks = [
                {
                    "source_id": check.source_id,
                    "time": check.check_time.isoformat(),
                    "error": check.error_message or "Unknown error"
                }
                for check in recent_checks if not check.success
            ]
            
            # Warn if success rate is low, but don't fail for occasional failures
            if success_rate < 50:
                pytest.fail(
                    f"Source check success rate is too low: {success_rate:.1f}% "
                    f"({successful_checks}/{total_checks} successful). "
                    f"Recent failures: {failed_checks[:5]}"  # Show first 5 failures
                )
            elif success_rate < 80:
                # Log warning but don't fail - some sources may be temporarily unavailable
                pytest.warns(
                    UserWarning,
                    f"Source check success rate is below 80%: {success_rate:.1f}% "
                    f"({successful_checks}/{total_checks} successful)"
                )
            
            # Verify we have some successful checks
            assert successful_checks > 0, (
                f"No successful source checks in the last 7 days. "
                f"Total checks: {total_checks}. Ingestion is likely broken."
            )
    
    @pytest.mark.integration
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_ingestion_pipeline_end_to_end(self, db_manager: AsyncDatabaseManager):
        """
        End-to-end test: Verify that ingestion pipeline components are functional.
        
        This test checks:
        1. Active sources exist
        2. Sources have been checked recently
        3. Articles have been discovered recently
        4. Source checks are succeeding
        """
        async with db_manager.get_session() as session:
            # 1. Check for active sources
            active_sources_query = select(func.count(SourceTable.id)).where(
                SourceTable.active == True
            )
            active_count = await session.scalar(active_sources_query)
            
            if active_count == 0:
                pytest.skip("No active sources configured. Cannot test ingestion pipeline.")
            
            # 2. Check for recent source checks (last 24 hours)
            check_cutoff = datetime.utcnow() - timedelta(hours=24)
            recent_checks_query = select(func.count(SourceCheckTable.id)).where(
                SourceCheckTable.check_time >= check_cutoff
            )
            recent_check_count = await session.scalar(recent_checks_query)
            
            # 3. Check for recent article discoveries (last 24 hours)
            article_cutoff = datetime.utcnow() - timedelta(hours=24)
            recent_articles_query = select(func.count(ArticleTable.id)).where(
                and_(
                    ArticleTable.discovered_at >= article_cutoff,
                    ArticleTable.archived == False
                )
            )
            recent_article_count = await session.scalar(recent_articles_query)
            
            # 4. Check for successful source checks (last 24 hours)
            successful_checks_query = select(func.count(SourceCheckTable.id)).where(
                and_(
                    SourceCheckTable.check_time >= check_cutoff,
                    SourceCheckTable.success == True
                )
            )
            successful_check_count = await session.scalar(successful_checks_query)
            
            # Build comprehensive health report
            health_report = {
                "active_sources": active_count,
                "recent_checks_24h": recent_check_count or 0,
                "recent_articles_24h": recent_article_count or 0,
                "successful_checks_24h": successful_check_count or 0,
            }
            
            # Determine health status
            issues = []
            
            if recent_check_count == 0:
                issues.append("No source checks in the last 24 hours")
            
            if successful_check_count == 0 and recent_check_count > 0:
                issues.append("No successful source checks in the last 24 hours")
            
            if recent_article_count == 0 and recent_check_count > 0:
                issues.append(
                    "Sources are being checked but no new articles discovered in last 24 hours. "
                    "This may indicate: (1) sources have no new content, (2) all content is filtered, "
                    "or (3) ingestion pipeline is broken."
                )
            
            if issues:
                pytest.fail(
                    f"Ingestion pipeline health check failed:\n"
                    + "\n".join(f"  - {issue}" for issue in issues)
                    + f"\n\nHealth report: {health_report}"
                )
            
            # All checks passed
            assert active_count > 0, "Should have active sources"
            assert recent_check_count is not None, "Should be able to query recent checks"
            assert recent_article_count is not None, "Should be able to query recent articles"
