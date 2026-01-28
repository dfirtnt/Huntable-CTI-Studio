"""
Dashboard data endpoint.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import APIRouter

from src.database.async_manager import async_db_manager
from src.web.dependencies import logger

router = APIRouter(tags=["Dashboard"])


def _format_time_ago(timestamp):
    """Format timestamp as human-readable time ago string."""
    if not timestamp:
        return "Unknown"

    now = datetime.now()
    if isinstance(timestamp, str):
        # Parse timestamp - if it has timezone info, convert to local time
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            # Convert to local time and remove timezone info
            parsed = parsed.astimezone().replace(tzinfo=None)
        timestamp = parsed

    diff = now - timestamp
    minutes = int(diff.total_seconds() / 60)
    hours = int(diff.total_seconds() / 3600)
    days = int(diff.total_seconds() / 86400)

    if minutes < 1:
        return "Just now"
    if minutes < 60:
        return f"{minutes}m ago"
    if hours < 24:
        return f"{hours}h ago"
    return f"{days}d ago"


@router.get("/api/dashboard/data")
async def api_dashboard_data():
    """Get all dashboard data in one endpoint for efficient updates."""
    try:
        stats = await async_db_manager.get_database_stats()
        sources = await async_db_manager.list_sources()

        total_sources = len(sources)
        active_sources = len([source for source in sources if source.active])
        uptime = (active_sources / total_sources * 100) if total_sources > 0 else 0

        recent_articles = await async_db_manager.list_articles(limit=1000)
        daily_data: Dict[str, int] = {}
        hourly_data: Dict[str, int] = {}

        for i in range(10):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            daily_data[date] = 0

        for hour in range(24):
            hourly_data[f"{hour:02d}"] = 0

        for article in recent_articles:
            created_at_str = None
            if hasattr(article, "created_at"):
                created_at_str = article.created_at
            elif isinstance(article, dict) and "created_at" in article:
                created_at_str = article["created_at"]

            if created_at_str:
                try:
                    # Parse timestamp - if it has timezone info, convert to local time
                    parsed = datetime.fromisoformat(
                        str(created_at_str).replace("Z", "+00:00")
                    )
                    if parsed.tzinfo is not None:
                        # Convert to local time and remove timezone info
                        parsed = parsed.astimezone().replace(tzinfo=None)
                    created_at = parsed
                    date_key = created_at.strftime("%Y-%m-%d")
                    hour_key = created_at.strftime("%H")

                    if date_key in daily_data:
                        daily_data[date_key] += 1
                    if hour_key in hourly_data:
                        hourly_data[hour_key] += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to parse date %s: %s", created_at_str, exc)
                    continue

        failing_sources = []
        for source in sources:
            # Skip manual source from failure metrics
            if getattr(source, "identifier", "") == "manual":
                continue

            if not getattr(source, "active", True):
                last_success = getattr(source, "last_success", None)
                consecutive_failures = getattr(source, "consecutive_failures", 0)
                failing_sources.append(
                    {
                        "name": getattr(source, "name", "Unknown Source"),
                        "last_success": last_success.isoformat()
                        if last_success
                        else "Never",
                        "last_success_text": _format_time_ago(last_success),
                        "consecutive_failures": consecutive_failures,
                    }
                )

        async with async_db_manager.get_session() as session:
            recent_articles_query = """
                SELECT created_at, title 
                FROM articles 
                WHERE created_at > NOW() - INTERVAL '72 hours'
                ORDER BY created_at DESC 
                LIMIT 3
            """
            recent_checks_query = """
                SELECT check_time, success, method, articles_found, s.name as source_name
                FROM source_checks sc
                JOIN sources s ON sc.source_id = s.id
                WHERE check_time > NOW() - INTERVAL '72 hours'
                ORDER BY check_time DESC 
                LIMIT 3
            """

            from sqlalchemy import text

            recent_articles_result = await session.execute(text(recent_articles_query))
            recent_articles_rows = recent_articles_result.fetchall()

            recent_checks_result = await session.execute(text(recent_checks_query))
            recent_checks_rows = recent_checks_result.fetchall()

        recent_activities = []

        for article in recent_articles_rows:
            time_ago = _format_time_ago(article.created_at)
            recent_activities.append(
                {
                    "time_ago": time_ago,
                    "message": f"New article processed: {article.title[:50]}...",
                    "type": "article",
                    "color": "green",
                    "timestamp": article.created_at,
                }
            )

        for check in recent_checks_rows:
            time_ago = _format_time_ago(check.check_time)
            if check.success:
                message = f"Source health check: {check.source_name} ({check.articles_found} articles)"
                color = "green"
            else:
                message = f"Source check failed: {check.source_name}"
                color = "red"

            recent_activities.append(
                {
                    "time_ago": time_ago,
                    "message": message,
                    "type": "source_check",
                    "color": color,
                    "timestamp": check.check_time,
                }
            )

        recent_activities.sort(
            key=lambda item: item.get("timestamp", datetime.min), reverse=True
        )
        recent_activities = recent_activities[:4]

        async with async_db_manager.get_session() as session:
            from sqlalchemy import text

            avg_score_query = text(
                """
                SELECT AVG((article_metadata->>'threat_hunting_score')::float) as avg_score
                FROM articles 
                WHERE (article_metadata->>'threat_hunting_score')::float > 0
                """
            )
            avg_result = await session.execute(avg_score_query)
            avg_hunt_score = avg_result.scalar() or 0

            efficiency_query = text(
                """
                SELECT 
                    COUNT(CASE WHEN (article_metadata->>'threat_hunting_score')::float > 0 THEN 1 END) as scored_articles,
                    COUNT(*) as total_articles
                FROM articles
                """
            )
            efficiency_result = await session.execute(efficiency_query)
            efficiency_row = efficiency_result.fetchone()
            filter_efficiency = (
                round(
                    (
                        efficiency_row.scored_articles
                        / efficiency_row.total_articles
                        * 100
                    ),
                    1,
                )
                if efficiency_row.total_articles > 0
                else 0
            )

        top_articles = []
        async with async_db_manager.get_session() as session:
            from sqlalchemy import text

            top_query = text(
                """
                SELECT 
                    a.id,
                    a.title,
                    a.article_metadata,
                    a.published_at,
                    a.canonical_url,
                    s.name as source_name
                FROM articles a
                JOIN sources s ON a.source_id = s.id
                WHERE a.article_metadata->>'threat_hunting_score' IS NOT NULL
                  AND (a.article_metadata->>'threat_hunting_score')::float > 50
                  AND a.created_at >= NOW() - INTERVAL '7 days'
                ORDER BY a.published_at DESC
                LIMIT 10
                """
            )

            top_result = await session.execute(top_query)
            top_rows = top_result.fetchall()

        for db_article in top_rows:
            metadata = db_article.article_metadata or {}
            hunt_score = metadata.get("threat_hunting_score", 0)

            # Format publication date
            published_at_str = "Unknown"
            if db_article.published_at:
                if isinstance(db_article.published_at, datetime):
                    published_at_str = db_article.published_at.strftime("%Y-%m-%d")
                else:
                    published_at_str = str(db_article.published_at)[:10]

            top_articles.append(
                {
                    "id": db_article.id,
                    "title": db_article.title[:100] if db_article.title else "Untitled",
                    "hunt_score": round(hunt_score, 1),
                    "published_at": published_at_str,
                    "url": db_article.canonical_url,
                    "source_name": db_article.source_name
                    if hasattr(db_article, "source_name")
                    else "Unknown Source",
                }
            )

        return {
            "health": {
                "uptime": round(uptime, 1),
                "total_sources": total_sources,
                "avg_response_time": 1.42,
            },
            "volume": {"daily": daily_data, "hourly": hourly_data},
            "failing_sources": failing_sources[:10],
            "top_articles": top_articles,
            "recent_activities": recent_activities,
            "stats": {
                "total_articles": stats.get("total_articles", 0) if stats else 0,
                "active_sources": active_sources,
                "avg_hunt_score": round(float(avg_hunt_score), 1),
                "filter_efficiency": filter_efficiency,
            },
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Dashboard data error: %s", exc)
        return {
            "health": {"uptime": 0.0, "total_sources": 0, "avg_response_time": 0.0},
            "volume": {"daily": {"2025-01-01": 0}, "hourly": {"00": 0}},
            "failing_sources": [],
            "top_articles": [],
            "recent_activities": [],
            "stats": {
                "total_articles": 0,
                "active_sources": 0,
                "avg_hunt_score": 0,
                "filter_efficiency": 0,
            },
        }
