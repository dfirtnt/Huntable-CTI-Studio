"""
Analytics endpoints for scraper and hunt metrics.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter

from src.database.async_manager import async_db_manager
from src.web.dependencies import logger

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/scraper/overview")
async def api_scraper_overview():
    """Get scraper overview metrics."""
    try:
        # Get ingestion analytics for today's data
        ingestion_data = await async_db_manager.get_ingestion_analytics()
        
        # Get today's articles count from daily trends
        today = datetime.now().date().strftime("%Y-%m-%d")
        articles_today = 0
        for trend in ingestion_data.get('daily_trends', []):
            if trend.get('date') == today:
                articles_today = trend.get('articles_count', 0)
                break
        
        # Get active sources count
        sources = await async_db_manager.list_sources()
        active_sources = len([s for s in sources if getattr(s, 'active', True)])
        
        # Calculate average response time (placeholder - would need actual timing data)
        avg_response_time = 250  # ms placeholder
        
        # Calculate error rate (placeholder - would need actual error tracking)
        error_rate = 2.5  # % placeholder
        
        return {
            "articles_today": articles_today,
            "active_sources": active_sources,
            "avg_response_time": avg_response_time,
            "error_rate": error_rate
        }
    except Exception as e:
        logger.error(f"Failed to get scraper overview: {e}")
        return {
            "articles_today": 0,
            "active_sources": 0,
            "avg_response_time": 0,
            "error_rate": 0
        }


@router.get("/scraper/collection-rate")
async def api_scraper_collection_rate():
    """Get collection rate data for the last 7 days."""
    try:
        # Get ingestion analytics data
        ingestion_data = await async_db_manager.get_ingestion_analytics()
        
        # Get last 7 days from daily trends
        daily_trends = ingestion_data.get('daily_trends', [])
        
        # Sort by date and take last 7 days
        sorted_trends = sorted(daily_trends, key=lambda x: x.get('date', ''))[-7:]
        
        labels = []
        values = []
        
        for trend in sorted_trends:
            date_str = trend.get('date', '')
            if date_str:
                # Convert YYYY-MM-DD to MM/DD format
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    labels.append(date_obj.strftime("%m/%d"))
                    values.append(trend.get('articles_count', 0))
                except ValueError:
                    continue
        
        return {
            "labels": labels,
            "values": values
        }
    except Exception as e:
        logger.error(f"Failed to get collection rate data: {e}")
        return {
            "labels": [],
            "values": []
        }


@router.get("/scraper/source-health")
async def api_scraper_source_health():
    """Get source health distribution data."""
    try:
        # Get sources and their health status
        sources = await async_db_manager.list_sources()
        
        healthy_count = 0
        warning_count = 0
        error_count = 0
        
        for source in sources:
            # Only count active sources
            if not getattr(source, 'active', True):
                continue
                
            # Simple health check based on last success
            last_success = getattr(source, 'last_success', None)
            if last_success:
                try:
                    # Handle both datetime objects and strings
                    if isinstance(last_success, datetime):
                        last_success_date = last_success.date()
                    elif isinstance(last_success, str):
                        # Handle different date formats
                        if last_success.endswith('Z'):
                            last_success_date = datetime.fromisoformat(last_success.replace('Z', '+00:00')).date()
                        else:
                            last_success_date = datetime.fromisoformat(last_success).date()
                    else:
                        error_count += 1
                        continue
                    
                    days_since_success = (datetime.now().date() - last_success_date).days
                    
                    if days_since_success <= 0:  # Same day or recent
                        healthy_count += 1
                    elif days_since_success <= 2:
                        warning_count += 1
                    else:
                        error_count += 1
                except (ValueError, AttributeError) as e:
                    logger.error(f"Date parsing error for {getattr(source, 'name', 'Unknown')}: {e}")
                    error_count += 1
            else:
                error_count += 1
        
        return {
            "labels": ["Healthy", "Warning", "Error"],
            "values": [healthy_count, warning_count, error_count]
        }
    except Exception as e:
        logger.error(f"Failed to get source health data: {e}")
        return {
            "labels": ["Healthy", "Warning", "Error"],
            "values": [0, 0, 0]
        }


@router.get("/scraper/source-performance")
async def api_scraper_source_performance():
    """Get detailed source performance data."""
    try:
        sources = await async_db_manager.list_sources()
        ingestion_data = await async_db_manager.get_ingestion_analytics()
        
        # Get source breakdown data
        source_breakdown = ingestion_data.get('source_breakdown', [])
        source_breakdown_dict = {item.get('source_name'): item for item in source_breakdown}
        
        performance_data = []
        for source in sources:
            # Only include active sources
            if not getattr(source, 'active', True):
                continue
                
            source_name = getattr(source, 'name', 'Unknown')
            
            # Get articles count for today from source breakdown
            articles_today = 0
            if source_name in source_breakdown_dict:
                articles_today = source_breakdown_dict[source_name].get('articles_count', 0)
            
            # Determine status
            last_success = getattr(source, 'last_success', None)
            status = "healthy"
            if last_success:
                try:
                    # Handle both datetime objects and strings
                    if isinstance(last_success, datetime):
                        last_success_date = last_success.date()
                    elif isinstance(last_success, str):
                        # Handle different date formats
                        if last_success.endswith('Z'):
                            last_success_date = datetime.fromisoformat(last_success.replace('Z', '+00:00')).date()
                        else:
                            last_success_date = datetime.fromisoformat(last_success).date()
                    else:
                        status = "error"
                        continue
                    
                    days_since_success = (datetime.now().date() - last_success_date).days
                    
                    if days_since_success > 2:
                        status = "error"
                    elif days_since_success > 0:
                        status = "warning"
                except (ValueError, AttributeError):
                    status = "error"
            
            performance_data.append({
                "name": source_name,
                "status": status,
                "articles_today": articles_today,
                "last_success": last_success or "Never",
                "error_rate": 0,  # Placeholder
                "avg_response": 200  # Placeholder
            })
        
        return {
            "sources": performance_data
        }
    except Exception as e:
        logger.error(f"Failed to get source performance data: {e}")
        return {
            "sources": []
        }


@router.get("/hunt/overview")
async def api_hunt_overview():
    """Get hunt scoring overview metrics."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get total articles count
            total_articles_query = text("SELECT COUNT(*) as count FROM articles")
            total_result = await session.execute(total_articles_query)
            total_articles = total_result.scalar()

            # Get average hunt score
            avg_score_query = text("""
                SELECT AVG((article_metadata->>'threat_hunting_score')::float) as avg_score
                FROM articles 
                WHERE (article_metadata->>'threat_hunting_score')::float > 0
            """)
            avg_result = await session.execute(avg_score_query)
            avg_hunt_score = avg_result.scalar() or 0

            # Get high quality articles (score > 50)
            high_quality_query = text("""
                SELECT COUNT(*) as count
                FROM articles 
                WHERE (article_metadata->>'threat_hunting_score')::float > 50
            """)
            high_quality_result = await session.execute(high_quality_query)
            high_quality_articles = high_quality_result.scalar() or 0

            # Get perfect matches (articles with perfect keyword matches)
            perfect_query = text("""
                SELECT COUNT(*) as count
                FROM articles 
                WHERE article_metadata::jsonb->'perfect_keyword_matches' IS NOT NULL
                   AND jsonb_array_length(article_metadata::jsonb->'perfect_keyword_matches') > 0
            """)
            perfect_result = await session.execute(perfect_query)
            perfect_matches = perfect_result.scalar() or 0

            # Get LOLBAS matches
            lolbas_query = text("""
                SELECT COUNT(*) as count
                FROM articles 
                WHERE article_metadata::jsonb->'lolbas_matches' IS NOT NULL
                   AND jsonb_array_length(article_metadata::jsonb->'lolbas_matches') > 0
            """)
            lolbas_result = await session.execute(lolbas_query)
            lolbas_matches = lolbas_result.scalar() or 0

            return {
                "total_articles": total_articles,
                "avg_hunt_score": round(float(avg_hunt_score), 2),
                "high_quality_articles": high_quality_articles,
                "perfect_matches": perfect_matches,
                "lolbas_matches": lolbas_matches
            }
    except Exception as e:
        logger.error(f"Failed to get hunt overview: {e}")
        return {
            "total_articles": 0,
            "avg_hunt_score": 0,
            "high_quality_articles": 0,
            "perfect_matches": 0,
            "lolbas_matches": 0
        }


@router.get("/hunt/score-distribution")
async def api_hunt_score_distribution():
    """Get hunt score distribution data."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get score distribution in buckets
            distribution_query = text("""
                SELECT 
                    CASE 
                        WHEN article_metadata->>'threat_hunting_score' IS NULL THEN 'Null'
                        WHEN (article_metadata->>'threat_hunting_score')::float = 0 THEN '0'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 0.1 AND 10 THEN '1-10'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 10.1 AND 25 THEN '11-25'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 25.1 AND 50 THEN '26-50'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 50.1 AND 75 THEN '51-75'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 75.1 AND 90 THEN '76-90'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 90.1 AND 99 THEN '91-99'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 99.1 AND 100 THEN '99-100'
                        WHEN (article_metadata->>'threat_hunting_score')::float = 100 THEN '100'
                        ELSE 'Unknown'
                    END as score_bucket,
                    COUNT(*) as count
                FROM articles 
                GROUP BY 
                    CASE 
                        WHEN article_metadata->>'threat_hunting_score' IS NULL THEN 'Null'
                        WHEN (article_metadata->>'threat_hunting_score')::float = 0 THEN '0'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 0.1 AND 10 THEN '1-10'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 10.1 AND 25 THEN '11-25'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 25.1 AND 50 THEN '26-50'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 50.1 AND 75 THEN '51-75'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 75.1 AND 90 THEN '76-90'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 90.1 AND 99 THEN '91-99'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 99.1 AND 100 THEN '99-100'
                        WHEN (article_metadata->>'threat_hunting_score')::float = 100 THEN '100'
                        ELSE 'Unknown'
                    END
                ORDER BY score_bucket
            """)
            
            result = await session.execute(distribution_query)
            rows = result.fetchall()
            
            labels = [row.score_bucket for row in rows]
            values = [row.count for row in rows]
            
            return {"labels": labels, "values": values}
    except Exception as e:
        logger.error(f"Failed to get score distribution: {e}")
        return {"labels": [], "values": []}


@router.get("/hunt/keyword-performance")
async def api_hunt_keyword_performance():
    """Get top performing keywords by match count."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get top keywords from perfect discriminators
            perfect_query = text("""
                SELECT 
                    keyword,
                    COUNT(*) as match_count
                FROM articles,
                     jsonb_array_elements(article_metadata::jsonb->'perfect_keyword_matches') as keyword
                WHERE article_metadata->'perfect_keyword_matches' IS NOT NULL
                GROUP BY keyword
                ORDER BY match_count DESC
                LIMIT 10
            """)
            
            result = await session.execute(perfect_query)
            rows = result.fetchall()
            
            labels = [row.keyword for row in rows]
            values = [row.match_count for row in rows]
            
            return {"labels": labels, "values": values}
    except Exception as e:
        logger.error(f"Failed to get keyword performance: {e}")
        return {"labels": [], "values": []}


@router.get("/hunt/keyword-analysis")
async def api_hunt_keyword_analysis():
    """Get detailed keyword analysis data."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get keyword analysis from all categories
            analysis_query = text("""
                SELECT 
                    'perfect' as category,
                    keyword::text,
                    COUNT(*) as match_count,
                    ROUND(AVG((article_metadata->>'threat_hunting_score')::float)::numeric, 1) as avg_score_impact,
                    CASE 
                        WHEN COUNT(*) > 10 THEN 95
                        WHEN COUNT(*) > 5 THEN 85
                        WHEN COUNT(*) > 2 THEN 75
                        ELSE 65
                    END as success_rate
                FROM articles,
                     jsonb_array_elements(article_metadata::jsonb->'perfect_keyword_matches') as keyword
                WHERE article_metadata::jsonb->'perfect_keyword_matches' IS NOT NULL
                GROUP BY keyword::text
                ORDER BY match_count DESC
                LIMIT 20
            """)
            
            result = await session.execute(analysis_query)
            rows = result.fetchall()
            
            keywords = [
                {
                    "category": row.category,
                    "keyword": row.keyword,
                    "match_count": row.match_count,
                    "avg_score_impact": row.avg_score_impact,
                    "success_rate": row.success_rate
                }
                for row in rows
            ]
            
            return {"keywords": keywords}
    except Exception as e:
        logger.error(f"Failed to get keyword analysis: {e}")
        return {"keywords": []}


@router.get("/hunt/score-trends")
async def api_hunt_score_trends():
    """Get hunt score trends over the last 30 days."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get daily average scores for last 30 days
            trends_query = text("""
                SELECT 
                    DATE(created_at) as date,
                    AVG((article_metadata->>'threat_hunting_score')::float) as avg_score
                FROM articles 
                WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
                  AND (article_metadata->>'threat_hunting_score')::float > 0
                GROUP BY DATE(created_at)
                ORDER BY date ASC
            """)
            
            result = await session.execute(trends_query)
            rows = result.fetchall()
            
            labels = [row.date.strftime('%Y-%m-%d') for row in rows]
            values = [round(float(row.avg_score), 1) for row in rows]
            
            return {"labels": labels, "values": values}
    except Exception as e:
        logger.error(f"Failed to get score trends: {e}")
        return {"labels": [], "values": []}


@router.get("/hunt/source-performance")
async def api_hunt_source_performance():
    """Get source performance by hunt score."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get top sources by average hunt score
            source_query = text("""
                SELECT 
                    s.name as source_name,
                    ROUND(AVG((a.article_metadata->>'threat_hunting_score')::float)::numeric, 1) as avg_score
                FROM sources s
                JOIN articles a ON s.id = a.source_id
                WHERE (a.article_metadata->>'threat_hunting_score')::float > 0
                GROUP BY s.id, s.name
                ORDER BY avg_score DESC
                LIMIT 8
            """)
            
            result = await session.execute(source_query)
            rows = result.fetchall()
            
            labels = [row.source_name for row in rows]
            values = [float(row.avg_score) for row in rows]
            
            return {"labels": labels, "values": values}
    except Exception as e:
        logger.error(f"Failed to get source performance: {e}")
        return {"labels": [], "values": []}


@router.get("/hunt/quality-distribution")
async def api_hunt_quality_distribution():
    """Get content quality distribution."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get quality distribution
            quality_query = text("""
                SELECT 
                    CASE 
                        WHEN article_metadata->>'threat_hunting_score' IS NULL THEN 'Unscored'
                        WHEN (article_metadata->>'threat_hunting_score')::float = 0 THEN 'Score 0'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 0.1 AND 25 THEN 'Score 1-25'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 25.1 AND 50 THEN 'Score 26-50'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 50.1 AND 75 THEN 'Score 51-75'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 75.1 AND 99 THEN 'Score 76-99'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 99.1 AND 100 THEN 'Score 99-100'
                        ELSE 'Unknown'
                    END as quality_level,
                    COUNT(*) as count
                FROM articles 
                GROUP BY 
                    CASE 
                        WHEN article_metadata->>'threat_hunting_score' IS NULL THEN 'Unscored'
                        WHEN (article_metadata->>'threat_hunting_score')::float = 0 THEN 'Score 0'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 0.1 AND 25 THEN 'Score 1-25'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 25.1 AND 50 THEN 'Score 26-50'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 50.1 AND 75 THEN 'Score 51-75'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 75.1 AND 99 THEN 'Score 76-99'
                        WHEN (article_metadata->>'threat_hunting_score')::float BETWEEN 99.1 AND 100 THEN 'Score 99-100'
                        ELSE 'Unknown'
                    END
                ORDER BY quality_level
            """)
            
            result = await session.execute(quality_query)
            rows = result.fetchall()
            
            labels = [row.quality_level for row in rows]
            values = [row.count for row in rows]
            
            return {"labels": labels, "values": values}
    except Exception as e:
        logger.error(f"Failed to get quality distribution: {e}")
        return {"labels": [], "values": []}


@router.get("/hunt/advanced-metrics")
async def api_hunt_advanced_metrics():
    """Get advanced hunt metrics."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get scoring efficiency
            efficiency_query = text("""
                SELECT 
                    COUNT(CASE WHEN (article_metadata->>'threat_hunting_score')::float > 0 THEN 1 END) as scored_articles,
                    COUNT(*) as total_articles
                FROM articles
            """)
            
            efficiency_result = await session.execute(efficiency_query)
            efficiency_row = efficiency_result.fetchone()
            scoring_efficiency = round((efficiency_row.scored_articles / efficiency_row.total_articles * 100), 1) if efficiency_row.total_articles > 0 else 0

            # Get average keywords per article
            keywords_query = text("""
                SELECT 
                    AVG(
                        COALESCE(jsonb_array_length(article_metadata::jsonb->'perfect_keyword_matches'), 0) +
                        COALESCE(jsonb_array_length(article_metadata::jsonb->'good_keyword_matches'), 0) +
                        COALESCE(jsonb_array_length(article_metadata::jsonb->'lolbas_matches'), 0)
                    ) as avg_keywords
                FROM articles 
                WHERE (article_metadata->>'threat_hunting_score')::float > 0
            """)
            
            keywords_result = await session.execute(keywords_query)
            avg_keywords = keywords_result.scalar() or 0

            # Get perfect match rate
            perfect_query = text("""
                SELECT 
                    COUNT(CASE WHEN (article_metadata->>'threat_hunting_score')::float = 100 THEN 1 END) as perfect_matches,
                    COUNT(CASE WHEN (article_metadata->>'threat_hunting_score')::float > 0 THEN 1 END) as scored_articles
                FROM articles
            """)
            
            perfect_result = await session.execute(perfect_query)
            perfect_row = perfect_result.fetchone()
            perfect_match_rate = round((perfect_row.perfect_matches / perfect_row.scored_articles * 100), 1) if perfect_row.scored_articles > 0 else 0

            return {
                "scoring_efficiency": scoring_efficiency,
                "avg_keywords_per_article": round(float(avg_keywords), 1),
                "perfect_match_rate": perfect_match_rate
            }
    except Exception as e:
        logger.error(f"Failed to get advanced metrics: {e}")
        return {
            "scoring_efficiency": 0,
            "avg_keywords_per_article": 0,
            "perfect_match_rate": 0
        }


@router.get("/hunt/recent-high-scores")
async def api_hunt_recent_high_scores():
    """Get recent high-score articles."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get recent high-score articles
            recent_query = text("""
                SELECT 
                    a.id,
                    a.title,
                    s.name as source_name,
                    (a.article_metadata->>'threat_hunting_score')::float as hunt_score,
                    a.created_at
                FROM articles a
                JOIN sources s ON a.source_id = s.id
                WHERE (a.article_metadata->>'threat_hunting_score')::float >= 75
                ORDER BY a.created_at DESC
                LIMIT 5
            """)
            
            result = await session.execute(recent_query)
            rows = result.fetchall()
            
            articles = [
                {
                    "id": row.id,
                    "title": row.title[:60] + "..." if len(row.title) > 60 else row.title,
                    "source_name": row.source_name,
                    "hunt_score": int(row.hunt_score),
                    "created_at": row.created_at.strftime('%Y-%m-%d') if row.created_at else 'Unknown'
                }
                for row in rows
            ]
            
            return {"articles": articles}
    except Exception as e:
        logger.error(f"Failed to get recent high scores: {e}")
        return {"articles": []}


@router.get("/hunt/performance-insights")
async def api_hunt_performance_insights():
    """Get performance insights and recommendations."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get top categories
            categories_query = text("""
                WITH category_counts AS (
                    SELECT 'Perfect Keywords' as category, COUNT(*) as count
                    FROM articles 
                    WHERE article_metadata->'perfect_keyword_matches' IS NOT NULL
                      AND jsonb_array_length(article_metadata::jsonb->'perfect_keyword_matches') > 0
                    
                    UNION ALL
                    
                    SELECT 'LOLBAS Matches' as category, COUNT(*) as count
                    FROM articles 
                    WHERE article_metadata->'lolbas_matches' IS NOT NULL
                      AND jsonb_array_length(article_metadata::jsonb->'lolbas_matches') > 0
                    
                    UNION ALL
                    
                    SELECT 'Good Keywords' as category, COUNT(*) as count
                    FROM articles 
                    WHERE article_metadata->'good_keyword_matches' IS NOT NULL
                      AND jsonb_array_length(article_metadata::jsonb->'good_keyword_matches') > 0
                )
                SELECT category, count
                FROM category_counts
                ORDER BY count DESC
            """)
            
            categories_result = await session.execute(categories_query)
            categories_rows = categories_result.fetchall()
            
            top_categories = [
                {"name": row.category, "count": row.count}
                for row in categories_rows
            ]

            # Generate recommendations based on data
            recommendations = [
                "Focus on sources with consistently high hunt scores for better threat intelligence quality",
                "Monitor keyword performance trends to identify emerging threat patterns",
                "Consider expanding LOLBAS keyword coverage for better attack technique detection",
                "Review low-scoring articles to improve content filtering accuracy"
            ]

            return {
                "top_categories": top_categories,
                "recommendations": recommendations
            }
    except Exception as e:
        logger.error(f"Failed to get performance insights: {e}")
        return {
            "top_categories": [],
            "recommendations": []
        }


@router.get("/hunt-demo/articles")
async def api_hunt_demo_articles():
    """Get articles data for demo visualizations."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get articles with all metadata for demo
            articles_query = text("""
                SELECT 
                    a.id,
                    a.title,
                    a.published_at,
                    a.word_count,
                    a.article_metadata,
                    a.source_id,
                    s.name as source_name
                FROM articles a
                JOIN sources s ON a.source_id = s.id
                WHERE a.article_metadata->>'threat_hunting_score' IS NOT NULL
                ORDER BY a.published_at DESC
                LIMIT 1000
            """)
            
            result = await session.execute(articles_query)
            articles = []
            
            for row in result.fetchall():
                articles.append({
                    "id": row.id,
                    "title": row.title,
                    "published_at": row.published_at.isoformat() if row.published_at else None,
                    "word_count": row.word_count,
                    "article_metadata": row.article_metadata or {},
                    "source_id": row.source_id,
                    "source_name": row.source_name
                })
            
            return {"articles": articles}
            
    except Exception as e:
        logger.error(f"Failed to get demo articles: {e}")
        return {"articles": []}


@router.get("/hunt-demo/sources")
async def api_hunt_demo_sources():
    """Get sources data for demo visualizations."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get sources with performance metrics
            sources_query = text("""
                SELECT 
                    s.id,
                    s.name,
                    s.identifier,
                    COUNT(a.id) as article_count,
                    AVG((a.article_metadata->>'threat_hunting_score')::float) as avg_hunt_score,
                    COUNT(CASE WHEN a.article_metadata->>'training_category' IS NOT NULL THEN 1 END) as classified_count
                FROM sources s
                LEFT JOIN articles a ON s.id = a.source_id
                WHERE s.active = true
                GROUP BY s.id, s.name, s.identifier
                ORDER BY article_count DESC
            """)
            
            result = await session.execute(sources_query)
            sources = []
            
            for row in result.fetchall():
                sources.append({
                    "id": row.id,
                    "name": row.name,
                    "identifier": row.identifier,
                    "article_count": row.article_count or 0,
                    "avg_hunt_score": float(row.avg_hunt_score) if row.avg_hunt_score else 0.0,
                    "classified_count": row.classified_count or 0
                })
            
            return {"sources": sources}
            
    except Exception as e:
        logger.error(f"Failed to get demo sources: {e}")
        return {"sources": []}


@router.get("/hunt-demo/keywords")
async def api_hunt_demo_keywords():
    """Get keyword analysis data for demo visualizations."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get keyword frequency and impact data
            keywords_query = text("""
                WITH keyword_stats AS (
                    SELECT 
                        keyword,
                        category,
                        COUNT(*) as frequency,
                        AVG((article_metadata->>'threat_hunting_score')::float) as avg_impact
                    FROM (
                        SELECT 
                            unnest(article_metadata->'perfect_keyword_matches') as keyword,
                            'perfect' as category,
                            article_metadata
                        FROM articles 
                        WHERE article_metadata->'perfect_keyword_matches' IS NOT NULL
                        
                        UNION ALL
                        
                        SELECT 
                            unnest(article_metadata->'good_keyword_matches') as keyword,
                            'good' as category,
                            article_metadata
                        FROM articles 
                        WHERE article_metadata->'good_keyword_matches' IS NOT NULL
                        
                        UNION ALL
                        
                        SELECT 
                            unnest(article_metadata->'lolbas_matches') as keyword,
                            'lolbas' as category,
                            article_metadata
                        FROM articles 
                        WHERE article_metadata->'lolbas_matches' IS NOT NULL
                        
                        UNION ALL
                        
                        SELECT 
                            unnest(article_metadata->'intelligence_matches') as keyword,
                            'intelligence' as category,
                            article_metadata
                        FROM articles 
                        WHERE article_metadata->'intelligence_matches' IS NOT NULL
                    ) keyword_data
                    GROUP BY keyword, category
                )
                SELECT 
                    keyword,
                    category,
                    frequency,
                    avg_impact
                FROM keyword_stats
                WHERE frequency > 1
                ORDER BY frequency DESC, avg_impact DESC
                LIMIT 100
            """)
            
            result = await session.execute(keywords_query)
            keywords = []
            
            for row in result.fetchall():
                keywords.append({
                    "keyword": row.keyword,
                    "category": row.category,
                    "frequency": row.frequency,
                    "avg_impact": float(row.avg_impact) if row.avg_impact else 0.0
                })
            
            return {"keywords": keywords}
            
    except Exception as e:
        logger.error(f"Failed to get demo keywords: {e}")
        return {"keywords": []}


@router.get("/hunt-demo/ml-models")
async def api_hunt_demo_ml_models():
    """Get ML model performance data for demo visualizations."""
    try:
        from sqlalchemy import text
        async with async_db_manager.get_session() as session:
            # Get ML model versions with performance metrics
            models_query = text("""
                SELECT 
                    version_number,
                    accuracy,
                    precision_huntable,
                    precision_not_huntable,
                    recall_huntable,
                    recall_not_huntable,
                    f1_score_huntable,
                    f1_score_not_huntable,
                    eval_accuracy,
                    eval_precision_huntable,
                    eval_precision_not_huntable,
                    eval_recall_huntable,
                    eval_recall_not_huntable,
                    eval_f1_score_huntable,
                    eval_f1_score_not_huntable,
                    trained_at
                FROM ml_model_versions
                ORDER BY version_number DESC
                LIMIT 10
            """)
            
            result = await session.execute(models_query)
            models = []
            
            for row in result.fetchall():
                models.append({
                    "version_number": row.version_number,
                    "accuracy": float(row.accuracy) if row.accuracy else 0.0,
                    "precision_huntable": float(row.precision_huntable) if row.precision_huntable else 0.0,
                    "precision_not_huntable": float(row.precision_not_huntable) if row.precision_not_huntable else 0.0,
                    "recall_huntable": float(row.recall_huntable) if row.recall_huntable else 0.0,
                    "recall_not_huntable": float(row.recall_not_huntable) if row.recall_not_huntable else 0.0,
                    "f1_score_huntable": float(row.f1_score_huntable) if row.f1_score_huntable else 0.0,
                    "f1_score_not_huntable": float(row.f1_score_not_huntable) if row.f1_score_not_huntable else 0.0,
                    "eval_accuracy": float(row.eval_accuracy) if row.eval_accuracy else 0.0,
                    "eval_precision_huntable": float(row.eval_precision_huntable) if row.eval_precision_huntable else 0.0,
                    "eval_precision_not_huntable": float(row.eval_precision_not_huntable) if row.eval_precision_not_huntable else 0.0,
                    "eval_recall_huntable": float(row.eval_recall_huntable) if row.eval_recall_huntable else 0.0,
                    "eval_recall_not_huntable": float(row.eval_recall_not_huntable) if row.eval_recall_not_huntable else 0.0,
                    "eval_f1_score_huntable": float(row.eval_f1_score_huntable) if row.eval_f1_score_huntable else 0.0,
                    "eval_f1_score_not_huntable": float(row.eval_f1_score_not_huntable) if row.eval_f1_score_not_huntable else 0.0,
                    "trained_at": row.trained_at.isoformat() if row.trained_at else None
                })
            
            return {"models": models}
            
    except Exception as e:
        logger.error(f"Failed to get demo ML models: {e}")
        return {"models": []}
