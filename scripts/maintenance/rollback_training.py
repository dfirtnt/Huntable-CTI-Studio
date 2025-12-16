#!/usr/bin/env python3
"""
Rollback the last training run by:
1. Resetting used_for_training flags for annotations in that run
2. Updating the manifest to remove/archive the version
3. Optionally archiving the dataset/artifact files
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Ensure `src` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import text
from src.database.manager import DatabaseManager
from src.services.observable_training import _load_manifest, _get_paths


def rollback_last_training(observable_type: str = "CMD", archive: bool = True):
    """Rollback the last training run."""
    observable_type = observable_type.upper()
    
    # Get paths
    dataset_dir, artifact_dir, manifest_path = _get_paths(observable_type)
    
    # Load manifest
    manifest = _load_manifest(manifest_path)
    versions = manifest.get("versions", [])
    
    if not versions:
        print(f"❌ No training runs found for {observable_type}")
        return
    
    last_version = versions[0]
    version_id = last_version.get("version")
    dataset_path = Path(last_version.get("dataset_path"))
    artifact_path = Path(last_version.get("artifact_path"))
    annotation_count = last_version.get("annotation_count", 0)
    
    print("=" * 80)
    print("TRAINING ROLLBACK")
    print("=" * 80)
    print(f"\nLast training run:")
    print(f"  Version: {version_id}")
    print(f"  Created: {last_version.get('created_at')}")
    print(f"  Annotations: {annotation_count}")
    print(f"  Dataset: {dataset_path}")
    print(f"  Artifact: {artifact_path}")
    
    # Get annotation IDs from the dataset file
    if not dataset_path.exists():
        print(f"\n⚠️  Warning: Dataset file not found: {dataset_path}")
        annotation_ids = []
    else:
        annotation_ids = []
        with open(dataset_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    ann_id = record.get('annotation_id')
                    if ann_id:
                        annotation_ids.append(ann_id)
                except json.JSONDecodeError:
                    continue
        
        print(f"\n  Found {len(annotation_ids)} annotation IDs in dataset")
    
    if not annotation_ids:
        print("\n❌ No annotation IDs found to rollback")
        return
    
    # Reset used_for_training flags
    db_manager = DatabaseManager()
    session = db_manager.get_session()
    
    try:
        # Reset flags
        id_list_str = ",".join(str(id) for id in annotation_ids)
        reset_query = text(f"""
            UPDATE article_annotations 
            SET used_for_training = FALSE
            WHERE id IN ({id_list_str})
            AND used_for_training = TRUE
        """)
        
        result = session.execute(reset_query)
        session.commit()
        
        reset_count = result.rowcount
        print(f"\n✅ Reset used_for_training flag for {reset_count} annotation(s)")
        
        # Update manifest - remove the last version
        if len(versions) > 1:
            new_active_version = versions[1].get("version")
            manifest["active_version"] = new_active_version
            print(f"  Set active_version to: {new_active_version}")
        else:
            manifest["active_version"] = None
            print(f"  No previous version found, set active_version to None")
        
        # Remove the last version from manifest
        manifest["versions"] = versions[1:]  # Remove first (last) version
        
        # Archive files if requested
        if archive:
            archive_dir = artifact_dir / "archived"
            archive_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if dataset_path.exists():
                archive_dataset = archive_dir / f"{dataset_path.name}.rolled_back_{timestamp}"
                dataset_path.rename(archive_dataset)
                print(f"  Archived dataset: {archive_dataset}")
            
            if artifact_path.exists():
                archive_artifact = archive_dir / f"{artifact_path.name}.rolled_back_{timestamp}"
                artifact_path.rename(archive_artifact)
                print(f"  Archived artifact: {archive_artifact}")
        else:
            print(f"  Files not archived (archive=False)")
        
        # Save updated manifest
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"\n✅ Updated manifest: {manifest_path}")
        
        print(f"\n{'=' * 80}")
        print("ROLLBACK COMPLETE")
        print(f"{'=' * 80}")
        print(f"✅ Rolled back training run {version_id}")
        print(f"   Reset {reset_count} annotation flags")
        print(f"   Removed version from manifest")
        if archive:
            print(f"   Archived dataset and artifact files")
        
    except Exception as e:
        session.rollback()
        print(f"\n❌ Error during rollback: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rollback last training run")
    parser.add_argument("--observable-type", default="CMD", help="Observable type (default: CMD)")
    parser.add_argument("--no-archive", action="store_true", help="Don't archive files, just delete")
    args = parser.parse_args()
    
    rollback_last_training(args.observable_type, archive=not args.no_archive)


