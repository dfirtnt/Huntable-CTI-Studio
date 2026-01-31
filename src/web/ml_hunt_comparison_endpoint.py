"""API endpoint for ML vs Hunt scoring comparison."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from src.database.manager import get_db
from src.services.chunk_analysis_service import ChunkAnalysisService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/ml-hunt-comparison", response_class=HTMLResponse)
async def ml_hunt_comparison_page():
    """Serve the ML vs Hunt scoring comparison page."""
    try:
        with open("src/web/templates/ml_hunt_comparison.html") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="ML Hunt comparison page not found") from e


@router.get("/api/ml-hunt-comparison/stats")
async def get_model_comparison_stats(
    model_version: str | None = Query(None, description="Filter by specific model version"),
    db: Session = Depends(get_db),
):
    """Get comparison statistics for model versions."""
    try:
        service = ChunkAnalysisService(db)
        stats = service.get_model_comparison_stats(model_version)
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Error getting model comparison stats: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/ml-hunt-comparison/results")
async def get_chunk_analysis_results(
    article_id: int | None = Query(None, description="Filter by article ID"),
    model_version: str | None = Query(None, description="Filter by model version"),
    hunt_score_min: float | None = Query(None, description="Minimum hunt score"),
    hunt_score_max: float | None = Query(None, description="Maximum hunt score"),
    ml_prediction: bool | None = Query(None, description="ML prediction filter"),
    hunt_prediction: bool | None = Query(None, description="Hunt prediction filter"),
    agreement: bool | None = Query(None, description="Agreement filter (True=agree, False=disagree)"),
    limit: int = Query(100, ge=1, le=1000, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
):
    """Get chunk analysis results with filtering."""
    try:
        service = ChunkAnalysisService(db)
        results = service.get_chunk_analysis_results(
            article_id=article_id,
            model_version=model_version,
            hunt_score_min=hunt_score_min,
            hunt_score_max=hunt_score_max,
            ml_prediction=ml_prediction,
            hunt_prediction=hunt_prediction,
            agreement=agreement,
            limit=limit,
            offset=offset,
        )
        return {"success": True, "results": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Error getting chunk analysis results: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/ml-hunt-comparison/model-versions")
async def get_available_model_versions(db: Session = Depends(get_db)):
    """Get list of available model versions."""
    try:
        service = ChunkAnalysisService(db)
        versions = service.get_available_model_versions()
        return {"success": True, "model_versions": versions}
    except Exception as e:
        logger.error(f"Error getting model versions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/ml-hunt-comparison/summary")
async def get_comparison_summary(db: Session = Depends(get_db)):
    """Get summary statistics for the comparison."""
    try:
        service = ChunkAnalysisService(db)

        # Get overall stats
        all_stats = service.get_model_comparison_stats()
        model_versions = service.get_available_model_versions()

        # Get recent results count
        recent_results = service.get_chunk_analysis_results(limit=1)
        total_results = len(service.get_chunk_analysis_results(limit=10000))  # Get approximate count

        summary = {
            "total_model_versions": len(model_versions),
            "total_chunk_analyses": total_results,
            "model_versions": model_versions,
            "overall_stats": all_stats,
            "last_updated": recent_results[0]["created_at"] if recent_results else None,
        }

        return {"success": True, "summary": summary}
    except Exception as e:
        logger.error(f"Error getting comparison summary: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
