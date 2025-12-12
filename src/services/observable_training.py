"""
Utilities for managing observable extractor training workflows.

Each observable type (CMD, PROC_LINEAGE) maintains its own dataset directory,
artifact lineage, and active version metadata without requiring database
schema changes.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy import case, func, select, update

from src.database.async_manager import async_db_manager
from src.database.manager import DatabaseManager
from src.database.models import ArticleAnnotationTable

SUPPORTED_OBSERVABLE_TYPES = ["CMD", "PROC_LINEAGE"]
BASE_DATASET_DIR = Path("outputs/evaluation_data/observables")
BASE_ARTIFACT_DIR = Path("outputs/observables")
MANIFEST_FILENAME = "manifest.json"


async def get_observable_training_summary() -> Dict[str, Any]:
    """Return annotation counts, directories, and artifact metadata per observable."""
    counts = await _aggregate_counts()
    summary: Dict[str, Any] = {
        "supported_types": SUPPORTED_OBSERVABLE_TYPES,
        "types": {},
    }

    for observable_type in SUPPORTED_OBSERVABLE_TYPES:
        dataset_dir, artifact_dir, manifest_path = _get_paths(observable_type)
        manifest = _load_manifest(manifest_path)
        summary["types"][observable_type] = {
            "counts": counts.get(observable_type, {"total": 0, "used": 0, "unused": 0}),
            "dataset_directory": str(dataset_dir),
            "artifact_directory": str(artifact_dir),
            "active_version": manifest.get("active_version"),
            "recent_artifacts": manifest.get("versions", [])[:5],
            "latest_artifact": manifest.get("versions", [None])[0]
            if manifest.get("versions")
            else None,
        }

    summary["total_annotations"] = sum(
        info["counts"]["total"] for info in summary["types"].values()
    )
    return summary


def run_observable_training_job(observable_type: str) -> Dict[str, Any]:
    """Export unused annotations for the observable and create a new artifact."""
    observable_type = observable_type.upper()
    if observable_type not in SUPPORTED_OBSERVABLE_TYPES:
        raise ValueError(f"Unsupported observable type '{observable_type}'")

    dataset_dir, artifact_dir, manifest_path = _get_paths(observable_type)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    db_manager = DatabaseManager()
    session = db_manager.get_session()
    try:
        annotations_query = select(ArticleAnnotationTable).where(
            ArticleAnnotationTable.annotation_type == observable_type,
            ArticleAnnotationTable.used_for_training.is_(False),
        )
        annotations = session.execute(annotations_query).scalars().all()
        if not annotations:
            return {
                "status": "no_data",
                "processed_count": 0,
                "message": f"No unused {observable_type} annotations available.",
            }

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        dataset_path = dataset_dir / f"{observable_type.lower()}_{timestamp}.jsonl"
        _write_dataset(dataset_path, annotations, observable_type)

        artifact_path = artifact_dir / f"{observable_type.lower()}_{timestamp}.json"
        artifact_payload = {
            "version": timestamp,
            "created_at": datetime.utcnow().isoformat(),
            "annotation_type": observable_type,
            "annotation_count": len(annotations),
            "dataset_path": str(dataset_path),
            "artifact_path": str(artifact_path),
        }
        artifact_path.write_text(json.dumps(artifact_payload, indent=2), encoding="utf-8")

        annotation_ids = [annotation.id for annotation in annotations]
        session.execute(
            update(ArticleAnnotationTable)
            .where(ArticleAnnotationTable.id.in_(annotation_ids))
            .values(used_for_training=True)
        )
        session.commit()

        _update_manifest(manifest_path, artifact_payload)

        return {
            "status": "completed",
            "processed_count": len(annotations),
            "artifact_path": str(artifact_path),
            "dataset_path": str(dataset_path),
            "version": timestamp,
            "observable_type": observable_type,
        }
    finally:
        session.close()


def _get_paths(observable_type: str) -> Tuple[Path, Path, Path]:
    dataset_dir = BASE_DATASET_DIR / observable_type.lower()
    artifact_dir = BASE_ARTIFACT_DIR / observable_type.lower()
    manifest_path = artifact_dir / MANIFEST_FILENAME
    return dataset_dir, artifact_dir, manifest_path


async def _aggregate_counts() -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Dict[str, int]] = {
        observable: {"total": 0, "used": 0, "unused": 0}
        for observable in SUPPORTED_OBSERVABLE_TYPES
    }
    async with async_db_manager.get_session() as session:
        query = (
            select(
                ArticleAnnotationTable.annotation_type,
                func.count(ArticleAnnotationTable.id).label("total"),
                func.sum(
                    case(
                        (ArticleAnnotationTable.used_for_training.is_(False), 1),
                        else_=0,
                    )
                ).label("unused"),
            )
            .group_by(ArticleAnnotationTable.annotation_type)
            .order_by(ArticleAnnotationTable.annotation_type)
        )
        result = await session.execute(query)
        for annotation_type, total, unused in result.fetchall():
            if annotation_type not in counts:
                continue
            counts[annotation_type] = {
                "total": int(total or 0),
                "unused": int(unused or 0),
                "used": int(total or 0) - int(unused or 0),
            }
    return counts


def _write_dataset(
    dataset_path: Path, annotations: List[ArticleAnnotationTable], observable_type: str
) -> None:
    with dataset_path.open("w", encoding="utf-8") as dataset_file:
        for annotation in annotations:
            payload = {
                "annotation_id": annotation.id,
                "article_id": annotation.article_id,
                "observable_type": observable_type,
                "value": annotation.selected_text,
                "start_position": annotation.start_position,
                "end_position": annotation.end_position,
                "context_before": annotation.context_before,
                "context_after": annotation.context_after,
                "created_at": annotation.created_at.isoformat() if annotation.created_at else None,
            }
            dataset_file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_manifest(manifest_path: Path) -> Dict[str, Any]:
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"versions": [], "active_version": None}


def _update_manifest(manifest_path: Path, artifact_payload: Dict[str, Any]) -> None:
    manifest = _load_manifest(manifest_path)
    versions = manifest.get("versions", [])
    versions.insert(0, artifact_payload)
    manifest["versions"] = versions
    manifest["active_version"] = artifact_payload["version"]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
