"""
PDF upload and processing endpoint.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pypdf
from fastapi import APIRouter, File, HTTPException, UploadFile

from src.database.async_manager import async_db_manager
from src.utils.content import ContentCleaner, ThreatHuntingScorer
from src.web.dependencies import logger

router = APIRouter(tags=["PDF"])


@router.post("/api/pdf/upload")
async def api_pdf_upload(file: UploadFile = File(...)):
    """API endpoint for uploading and processing PDF threat reports."""
    try:
        from src.models.article import ArticleCreate

        if not file:
            raise HTTPException(status_code=400, detail="No file provided")

        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        file_content = await file.read()
        if len(file_content) > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=400, detail="File too large. Maximum size is 50MB."
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name

        try:
            logger.info("Processing PDF: %s", file.filename)

            text_content = ""
            with open(temp_file_path, "rb") as pdf_file:
                pdf_reader = pypdf.PdfReader(pdf_file)
                page_count = len(pdf_reader.pages)

                for page_num, page in enumerate(pdf_reader.pages, 1):
                    text_content += f"--- Page {page_num} ---\n"
                    text_content += (page.extract_text() or "") + "\n\n"

            if not text_content.strip():
                raise HTTPException(
                    status_code=400, detail="Could not extract text from PDF"
                )

            content_hash = ContentCleaner.calculate_content_hash(
                f"PDF Report: {file.filename}", text_content
            )

            from src.database.models import SourceTable
            from sqlalchemy import select
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy.exc import IntegrityError

            manual_source_id = None

            # First, try to get existing manual source
            async with async_db_manager.get_session() as session:
                manual_source = await session.execute(
                    select(SourceTable).where(SourceTable.identifier == "manual")
                )
                manual_source_obj = manual_source.scalar_one_or_none()
                if manual_source_obj:
                    manual_source_id = int(manual_source_obj.id)

            # If not found, create it using atomic INSERT ... ON CONFLICT
            if not manual_source_id:
                async with async_db_manager.get_session() as session:
                    try:
                        # Use PostgreSQL INSERT ... ON CONFLICT DO NOTHING for atomic upsert
                        now = datetime.now()
                        stmt = (
                            pg_insert(SourceTable)
                            .values(
                                identifier="manual",
                                name="Manual",
                                url="manual://uploaded",
                                rss_url=None,
                                check_frequency=3600,
                                lookback_days=180,
                                active=False,
                                config={},
                                consecutive_failures=0,
                                total_articles=0,
                                average_response_time=0.0,
                                created_at=now,
                                updated_at=now,
                            )
                            .on_conflict_do_nothing(index_elements=["identifier"])
                        )

                        await session.execute(stmt)
                        await session.commit()

                        # Query again to get the source (handles race conditions)
                        manual_source = await session.execute(
                            select(SourceTable).where(
                                SourceTable.identifier == "manual"
                            )
                        )
                        manual_source_obj = manual_source.scalar_one_or_none()

                        if manual_source_obj:
                            manual_source_id = manual_source_obj.id
                            logger.info(
                                f"Created or found manual source with ID: {manual_source_id}"
                            )
                        else:
                            raise HTTPException(
                                status_code=500, detail="Failed to create manual source"
                            )

                    except IntegrityError as exc:
                        logger.warning(
                            f"IntegrityError creating manual source (likely race condition): {exc}"
                        )
                        # Try to find it again in case another process created it
                        manual_source = await session.execute(
                            select(SourceTable).where(
                                SourceTable.identifier == "manual"
                            )
                        )
                        manual_source_obj = manual_source.scalar_one_or_none()
                        if manual_source_obj:
                            manual_source_id = manual_source_obj.id
                            logger.info(
                                f"Found manual source after IntegrityError with ID: {manual_source_id}"
                            )
                        else:
                            raise HTTPException(
                                status_code=500,
                                detail="Failed to create manual source - database constraint violation",
                            )
                    except Exception as exc:
                        logger.error(f"Error creating manual source: {exc}")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to get or create manual source: {exc}",
                        )

            if not manual_source_id:
                raise HTTPException(
                    status_code=500, detail="Failed to get or create manual source"
                )

            article_data = ArticleCreate(
                title=f"PDF Report: {file.filename}",
                content=text_content,
                canonical_url=f"pdf://{file.filename}",
                published_at=datetime.now(),
                source_id=manual_source_id,
                content_hash=content_hash,
                summary=text_content[:500] if text_content else None,
            )

            current_metadata = article_data.article_metadata.copy()

            try:
                created_article = await async_db_manager.create_article(article_data)

                if not created_article:
                    from src.database.models import ArticleTable

                    async with async_db_manager.get_session() as session:
                        existing_article = await session.execute(
                            select(ArticleTable).where(
                                ArticleTable.content_hash == content_hash
                            )
                        )
                        existing = existing_article.scalar_one_or_none()

                        if existing:
                            raise HTTPException(
                                status_code=400,
                                detail=(
                                    "Duplicate PDF detected. This file has already been uploaded as "
                                    f"Article ID {existing.id}: '{existing.title}'"
                                ),
                            )
                        raise HTTPException(
                            status_code=500,
                            detail="Failed to create article in database. Please try again or contact support.",
                        )

                article_id = created_article.id

            except HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("Database error during PDF upload: %s", exc)
                raise HTTPException(
                    status_code=500, detail=f"Database error: {exc}"
                ) from exc

            try:
                threat_hunting_result = (
                    ThreatHuntingScorer.score_threat_hunting_content(
                        article_data.title, text_content
                    )
                )
                current_metadata.update(threat_hunting_result)

                from src.models.article import ArticleUpdate

                update_data = ArticleUpdate(article_metadata=current_metadata)
                await async_db_manager.update_article(article_id, update_data)

                score = threat_hunting_result.get("threat_hunting_score", 0)
                logger.info(
                    "PDF processed successfully: Article ID %s, Score: %s",
                    article_id,
                    score,
                )

                # Get threshold from workflow config
                from src.database.manager import DatabaseManager
                from src.database.models import AgenticWorkflowConfigTable
                db_manager = DatabaseManager()
                db_session = db_manager.get_session()
                try:
                    config = db_session.query(AgenticWorkflowConfigTable).filter(
                        AgenticWorkflowConfigTable.is_active == True
                    ).order_by(
                        AgenticWorkflowConfigTable.version.desc()
                    ).first()
                    threshold = config.auto_trigger_hunt_score_threshold if config and hasattr(config, 'auto_trigger_hunt_score_threshold') else 60.0
                finally:
                    db_session.close()

                # Check if workflow should be triggered
                # Only trigger if RegexHuntScore > threshold
                if score > threshold:
                    try:
                        from src.worker.celery_app import trigger_agentic_workflow

                        trigger_agentic_workflow.delay(article_id)
                        logger.info(
                            f"Triggered agentic workflow for PDF article {article_id} (hunt_score: {score} > {threshold})"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to trigger workflow for PDF article {article_id}: {e}"
                        )
                else:
                    logger.debug(
                        f"Skipping workflow trigger for PDF article {article_id} (hunt_score: {score} <= {threshold})"
                    )

            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to generate threat hunting score for PDF: %s", exc
                )

            return {
                "success": True,
                "article_id": article_id,
                "filename": file.filename,
                "page_count": page_count,
                "file_size": len(file_content),
                "content_length": len(text_content),
                "threat_hunting_score": current_metadata.get(
                    "threat_hunting_score", "Not calculated"
                ),
            }

        finally:
            try:
                os.unlink(temp_file_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to delete temporary file: %s", exc)

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("PDF upload error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
