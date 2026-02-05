"""
Export endpoints.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response

from src.database.async_manager import async_db_manager
from src.models.annotation import ANNOTATION_MODE_TYPES
from src.web.dependencies import logger

router = APIRouter(tags=["Export"])


@router.get("/api/export/annotations")
async def api_export_annotations():
    """Export all annotations to CSV."""
    try:
        async with async_db_manager.get_session() as session:
            from sqlalchemy import text

            query = text(
                """
                SELECT
                    ROW_NUMBER() OVER (ORDER BY aa.created_at) as record_number,
                    aa.selected_text as highlighted_text,
                    CASE
                        WHEN aa.annotation_type = 'huntable' THEN 'Huntable'
                        WHEN aa.annotation_type = 'not_huntable' THEN 'Not Huntable'
                        ELSE aa.annotation_type
                    END as classification,
                    aa.annotation_type,
                    aa.usage,
                    aa.used_for_training,
                    aa.context_before,
                    aa.context_after,
                    aa.confidence_score,
                    a.title as article_title,
                    aa.created_at as classification_date
                FROM article_annotations aa
                LEFT JOIN articles a ON aa.article_id = a.id
                ORDER BY aa.created_at
                """
            )

            result = await session.execute(query)
            annotations = result.fetchall()

        # Use newline='' so csv module controls line endings consistently.
        output = io.StringIO(newline="")
        writer = csv.writer(
            output,
            quoting=csv.QUOTE_ALL,
            lineterminator="\r\n",
            escapechar="\\",
        )
        writer.writerow(
            [
                "record_number",
                "highlighted_text",
                "classification",
                "annotation_mode",
                "annotation_type",
                "usage",
                "used_for_training",
                "confidence_score",
                "context_before",
                "context_after",
                "article_title",
                "classification_date",
            ]
        )

        annotation_type_mode_map = {
            annotation_type.lower(): mode.capitalize()
            for mode, types in ANNOTATION_MODE_TYPES.items()
            for annotation_type in types
        }

        for annotation in annotations:
            highlighted_text = annotation.highlighted_text or ""
            # Normalize Windows-style escapes and line endings for cleaner CSV output.
            highlighted_text = highlighted_text.replace("\\\\", "\\").replace("\r\n", "\n").replace("\r", "\n")
            annotation_type = (annotation.annotation_type or "").strip()
            annotation_mode = annotation_type_mode_map.get(annotation_type.lower(), "Custom")
            usage = annotation.usage or ""
            used_for_training = bool(annotation.used_for_training)
            confidence_score = annotation.confidence_score if annotation.confidence_score is not None else 0.0
            context_before = annotation.context_before or ""
            context_after = annotation.context_after or ""
            writer.writerow(
                [
                    annotation.record_number,
                    highlighted_text,
                    annotation.classification,
                    annotation_mode,
                    annotation_type,
                    usage,
                    used_for_training,
                    confidence_score,
                    context_before,
                    context_after,
                    annotation.article_title,
                    annotation.classification_date.isoformat() if annotation.classification_date else "",
                ]
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"annotations_{timestamp}.csv"

        # Prepend UTF-8 BOM so Excel reliably detects the encoding.
        csv_content = "\ufeff" + output.getvalue()
        output.close()

        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except Exception as exc:  # noqa: BLE001
        logger.error("Export annotations error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
