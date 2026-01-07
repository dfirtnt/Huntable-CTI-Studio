"""
Celery tasks for observable extractor training flows.
"""

from __future__ import annotations

import logging

from src.worker.celery_app import celery_app
from src.services.observable_training import (
    run_observable_training_job,
    SUPPORTED_OBSERVABLE_TYPES,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="observables.train_extractor",
)
def train_observable_extractor(self, observable_type: str = "CMD", train_model: bool = True):
    """Background task that trains an observable extractor and optionally trains a model."""
    try:
        observable_type = observable_type.upper()
        if observable_type not in SUPPORTED_OBSERVABLE_TYPES:
            raise ValueError(f"Unsupported observable type '{observable_type}'")
        result = run_observable_training_job(observable_type, train_model=train_model)
        logger.info(
            "%s extractor training completed with status %s (%s samples)",
            observable_type,
            result.get("status"),
            result.get("processed_count"),
        )
        if result.get("model_training", {}).get("success"):
            logger.info(
                "%s model training completed: %s",
                observable_type,
                result["model_training"].get("model_path")
            )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("Observable training (%s) failed: %s", observable_type, exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
