"""
Annotation Embedding Generation Tasks

Celery tasks for generating embeddings for article annotations.
"""

import logging
from typing import List, Dict, Any

# Import celery_app after it's defined
from src.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def generate_annotation_embeddings(self):
    """Generate embeddings for all annotations that don't have them yet."""
    try:
        import asyncio
        from src.database.async_manager import AsyncDatabaseManager
        from src.services.embedding_service import get_embedding_service
        
        async def run_annotation_embedding():
            """Run annotation embedding generation."""
            db = AsyncDatabaseManager()
            try:
                # Get annotations without embeddings
                annotations = await db.get_annotations_without_embeddings()
                
                if not annotations:
                    logger.info("No annotations found that need embeddings")
                    return {"status": "success", "message": "No annotations to embed"}
                
                logger.info(f"Found {len(annotations)} annotations that need embeddings")
                
                embedding_service = get_embedding_service()
                embedded_count = 0
                
                # Process annotations in batches
                batch_size = 32
                for i in range(0, len(annotations), batch_size):
                    batch = annotations[i:i + batch_size]
                    
                    for annotation in batch:
                        try:
                            # Generate embedding for the annotation text
                            embedding = embedding_service.generate_embedding(
                                annotation.selected_text
                            )
                            
                            # Update the annotation with the embedding
                            await db.update_annotation_embedding(
                                annotation_id=annotation.id,
                                embedding=embedding,
                                model_name='all-mpnet-base-v2'
                            )
                            
                            embedded_count += 1
                            logger.debug(f"Generated embedding for annotation {annotation.id}")
                            
                        except Exception as e:
                            logger.error(f"Failed to embed annotation {annotation.id}: {e}")
                            continue
                    
                    # Small delay between batches
                    await asyncio.sleep(0.5)
                
                logger.info(f"Successfully generated embeddings for {embedded_count} annotations")
                return {
                    "status": "success",
                    "message": f"Generated embeddings for {embedded_count} annotations",
                    "total_processed": embedded_count
                }
                
            except Exception as e:
                logger.error(f"Annotation embedding generation failed: {e}")
                raise e
            finally:
                await db.close()
        
        # Run the async function
        result = asyncio.run(run_annotation_embedding())
        return result
        
    except Exception as exc:
        logger.error(f"Annotation embedding task failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def generate_single_annotation_embedding(self, annotation_id: int):
    """Generate embedding for a single annotation."""
    try:
        import asyncio
        from src.database.async_manager import AsyncDatabaseManager
        
        async def run_single_annotation_embedding():
            """Run single annotation embedding generation."""
            db = AsyncDatabaseManager()
            try:
                # Get the annotation
                annotation = await db.get_annotation_by_id(annotation_id)
                if not annotation:
                    return {"status": "error", "message": f"Annotation {annotation_id} not found"}
                
                # Check if already embedded
                if annotation.embedding is not None:
                    return {"status": "success", "message": f"Annotation {annotation_id} already has embedding"}
                
                # Generate embedding
                embedding_service = get_embedding_service()
                embedding = embedding_service.generate_embedding(annotation.selected_text)
                
                # Store embedding in database
                await db.update_annotation_embedding(
                    annotation_id=annotation_id,
                    embedding=embedding,
                    model_name="all-mpnet-base-v2"
                )
                
                logger.info(f"Generated embedding for annotation {annotation_id}")
                return {
                    "status": "success",
                    "annotation_id": annotation_id,
                    "embedding_dimension": len(embedding),
                    "message": f"Successfully generated embedding for annotation {annotation_id}"
                }
                
            except Exception as e:
                logger.error(f"Single annotation embedding generation failed for annotation {annotation_id}: {e}")
                raise e
            finally:
                await db.close()
        
        # Run the async function
        result = asyncio.run(run_single_annotation_embedding())
        return result
        
    except Exception as exc:
        logger.error(f"Single annotation embedding task failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def batch_generate_annotation_embeddings(self, annotation_ids: List[int], batch_size: int = 32):
    """Generate embeddings for multiple annotations in batches."""
    try:
        import asyncio
        from src.database.async_manager import AsyncDatabaseManager
        
        async def run_batch_annotation_embedding():
            """Run batch annotation embedding generation."""
            db = AsyncDatabaseManager()
            try:
                total_processed = 0
                total_skipped = 0
                total_errors = 0
                
                # Process in batches
                for i in range(0, len(annotation_ids), batch_size):
                    batch_ids = annotation_ids[i:i + batch_size]
                    
                    # Get annotations for this batch
                    annotations = await db.get_annotations_by_ids(batch_ids)
                    
                    # Filter out already embedded annotations
                    annotations_to_process = [
                        annotation for annotation in annotations 
                        if annotation.embedding is None
                    ]
                    
                    if not annotations_to_process:
                        total_skipped += len(batch_ids)
                        continue
                    
                    # Prepare texts for batch embedding
                    texts_to_embed = []
                    annotation_mapping = []
                    
                    for annotation in annotations_to_process:
                        texts_to_embed.append(annotation.selected_text)
                        annotation_mapping.append(annotation.id)
                    
                    # Generate embeddings in batch
                    embedding_service = get_embedding_service()
                    embeddings = embedding_service.generate_embeddings_batch(texts_to_embed, batch_size)
                    
                    # Store embeddings
                    for annotation_id, embedding in zip(annotation_mapping, embeddings):
                        try:
                            await db.update_annotation_embedding(
                                annotation_id=annotation_id,
                                embedding=embedding,
                                model_name="all-mpnet-base-v2"
                            )
                            total_processed += 1
                        except Exception as e:
                            logger.error(f"Failed to store embedding for annotation {annotation_id}: {e}")
                            total_errors += 1
                    
                    total_skipped += len(batch_ids) - len(annotations_to_process)
                
                logger.info(f"Batch annotation embedding complete: {total_processed} processed, {total_skipped} skipped, {total_errors} errors")
                return {
                    "status": "success",
                    "total_processed": total_processed,
                    "total_skipped": total_skipped,
                    "total_errors": total_errors
                }
                
            except Exception as e:
                logger.error(f"Batch annotation embedding generation failed: {e}")
                raise e
            finally:
                await db.close()
        
        # Run the async function
        result = asyncio.run(run_batch_annotation_embedding())
        return result
        
    except Exception as exc:
        logger.error(f"Batch annotation embedding task failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
