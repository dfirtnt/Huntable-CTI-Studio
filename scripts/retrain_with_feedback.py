#!/usr/bin/env python3
"""
Script to retrain the ML model using collected user feedback.
Combines original training data with user feedback to improve model accuracy.
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from utils.content_filter import ContentFilter


def load_feedback_data():
    """Load user feedback data from database."""
    try:
        from database.manager import DatabaseManager
        from database.models import ChunkClassificationFeedbackTable

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            feedback_records = (
                session.query(ChunkClassificationFeedbackTable)
                .filter(ChunkClassificationFeedbackTable.used_for_training == False)
                .all()
            )

            if not feedback_records:
                print("⚠️  No unused feedback found in database")
                return pd.DataFrame()

            # Convert to DataFrame
            feedback_data = []
            for record in feedback_records:
                feedback_data.append(
                    {
                        "chunk_id": record.chunk_id,
                        "chunk_text": record.chunk_text,
                        "is_correct": record.is_correct,
                        "user_classification": record.user_classification,
                        "model_classification": record.model_classification,
                        "model_confidence": record.model_confidence,
                    }
                )

            df = pd.DataFrame(feedback_data)
            print(f"📊 Loaded {len(df)} feedback entries from database")
            return df

        finally:
            session.close()

    except Exception as e:
        print(f"❌ Error loading feedback data: {e}")
        return pd.DataFrame()


def load_annotation_data(include_all: bool = False):
    """Load annotation data from database.

    Args:
        include_all: When True, load all annotations regardless of used_for_training
                     flag (used in bootstrap mode when no baseline CSV exists).
    """
    try:
        # Use the existing database manager
        from database.manager import DatabaseManager

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            from sqlalchemy import text

            # In bootstrap mode, include already-used annotations too — they aren't
            # in the (missing) baseline CSV so they must come from the DB directly.
            used_filter = "" if include_all else "AND aa.used_for_training = FALSE"

            query = text(f"""
            SELECT
                ROW_NUMBER() OVER (ORDER BY aa.created_at) as record_number,
                aa.selected_text as highlighted_text,
                CASE
                    WHEN aa.annotation_type = 'huntable' THEN 'Huntable'
                    WHEN aa.annotation_type = 'not_huntable' THEN 'Not Huntable'
                    ELSE aa.annotation_type
                END as classification,
                aa.created_at as classification_date
            FROM article_annotations aa
            WHERE LENGTH(aa.selected_text) >= 950
            AND LENGTH(aa.selected_text) <= 1050
            {used_filter}
            ORDER BY aa.created_at
            """)

            result = session.execute(query)
            results = result.fetchall()

            if not results:
                print("⚠️  No annotation data found")
                return pd.DataFrame()

            # Convert to DataFrame
            annotations = []
            for row in results:
                annotations.append(
                    {
                        "record_number": f"annotation_{row[0]}",
                        "highlighted_text": row[1],
                        "classification": row[2],
                        "classification_date": str(row[3]) if row[3] else "",
                    }
                )

            df = pd.DataFrame(annotations)
            print(f"📊 Loaded {len(df)} annotation entries")
            return df

        finally:
            session.close()

    except Exception as e:
        print(f"❌ Error loading annotation data: {e}")
        return pd.DataFrame()


def mark_annotations_as_used():
    """Mark all annotations as used for training by setting used_for_training flag."""
    try:
        from database.manager import DatabaseManager

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            from sqlalchemy import text

            # Mark annotations as used for training
            query = text("""
            UPDATE article_annotations
            SET used_for_training = TRUE
            WHERE LENGTH(selected_text) >= 950
            AND used_for_training = FALSE
            """)

            result = session.execute(query)
            session.commit()

            updated_count = result.rowcount
            print(f"🏷️  Marked {updated_count} annotations as used for training")

        finally:
            session.close()

    except Exception as e:
        print(f"❌ Error marking annotations as used: {e}")


def process_feedback_for_training(feedback_df: pd.DataFrame):
    """Process feedback data into training format."""
    if feedback_df.empty:
        return pd.DataFrame()

    # Use ALL feedback (both correct and incorrect) for training
    # Correct feedback reinforces patterns, incorrect feedback corrects mistakes
    incorrect_feedback = feedback_df[feedback_df["is_correct"] == False]
    correct_feedback = feedback_df[feedback_df["is_correct"] == True]

    print("📊 Feedback breakdown:")
    print(f"   - Incorrect classifications: {len(incorrect_feedback)} (to correct mistakes)")
    print(f"   - Correct classifications: {len(correct_feedback)} (to reinforce patterns)")

    if incorrect_feedback.empty and correct_feedback.empty:
        print("⚠️  No feedback found")
        return pd.DataFrame()

    # Create training examples from all feedback
    training_examples = []

    # Add incorrect feedback (with user's correction)
    for _, row in incorrect_feedback.iterrows():
        training_examples.append(
            {
                "record_number": f"feedback_{row['chunk_id']}",
                "highlighted_text": row["chunk_text"],
                "classification": row["user_classification"],
            }
        )

    # Add correct feedback (reinforce model's prediction)
    for _, row in correct_feedback.iterrows():
        training_examples.append(
            {
                "record_number": f"feedback_{row['chunk_id']}",
                "highlighted_text": row["chunk_text"],
                "classification": row["model_classification"],  # Use model's classification since it was correct
            }
        )

    print(f"✅ Created {len(training_examples)} training examples from feedback")

    return pd.DataFrame(training_examples)


def mark_feedback_as_used():
    """Mark all feedback as used for training in database."""
    try:
        from database.manager import DatabaseManager

        db_manager = DatabaseManager()
        updated_count = db_manager.mark_chunk_feedback_as_used()
        print(f"🏷️  Marked {updated_count} feedback entries as used for training")

    except Exception as e:
        print(f"❌ Error marking feedback as used: {e}")


def combine_training_data(original_file: str, feedback_df: pd.DataFrame, annotation_df: pd.DataFrame = None):
    """Combine original training data with feedback and annotation data."""
    # Load original training data (optional — may not exist on first run)
    if os.path.exists(original_file):
        original_df = pd.read_csv(original_file)
        print(f"📚 Loaded {len(original_df)} original training examples")
    else:
        print(f"⚠️  Original training file not found: {original_file}")
        print("   Proceeding in bootstrap mode (feedback + annotation data only)")
        original_df = pd.DataFrame(columns=["record_number", "highlighted_text", "classification"])

    # Process feedback data
    feedback_training = process_feedback_for_training(feedback_df)

    # Process annotation data (treat as gold standard - all annotations are used)
    annotation_training = pd.DataFrame()
    if annotation_df is not None and not annotation_df.empty:
        annotation_training = annotation_df[["record_number", "highlighted_text", "classification"]].copy()
        print(f"📊 Loaded {len(annotation_training)} annotation examples")

    # Combine datasets
    datasets_to_combine = [original_df]

    if not feedback_training.empty:
        datasets_to_combine.append(feedback_training)

    if not annotation_training.empty:
        datasets_to_combine.append(annotation_training)

    combined_df = pd.concat(datasets_to_combine, ignore_index=True)

    # Update record numbers to be sequential
    combined_df["record_number"] = range(1, len(combined_df) + 1)

    print(f"🔄 Combined dataset: {len(combined_df)} total examples")
    print(f"   - Original: {len(original_df)}")
    if not feedback_training.empty:
        print(f"   - Feedback: {len(feedback_training)}")
    if not annotation_training.empty:
        print(f"   - Annotations: {len(annotation_training)}")

    return combined_df


def retrain_model_with_feedback(
    original_file: str = "outputs/training_data/combined_training_data.csv",
    output_file: str = "outputs/training_data/retrained_training_data.csv",
):
    """Retrain the model using original data plus user feedback and annotations."""
    import asyncio
    import shutil
    from datetime import datetime

    print("🚀 Starting model retraining with user feedback and annotations...")
    print("=" * 60)

    # Load feedback data
    feedback_df = load_feedback_data()

    # When the baseline CSV is absent we are in bootstrap mode — load all
    # annotations from DB (including already-used ones) since they aren't
    # represented in any CSV file yet.
    bootstrap_mode = not os.path.exists(original_file)
    annotation_df = load_annotation_data(include_all=bootstrap_mode)

    # Combine training data
    combined_df = combine_training_data(original_file, feedback_df, annotation_df)

    if combined_df is None or combined_df.empty:
        print("❌ No training data available (no feedback, annotations, or original file)")
        return False

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Save combined training data
    combined_df.to_csv(output_file, index=False)
    print(f"💾 Saved combined training data to: {output_file}")

    # Backup current model before retraining
    current_model_path = "/app/models/content_filter.pkl"
    backup_model_path = None
    old_version_id = None

    if os.path.exists(current_model_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_model_path = f"/app/models/content_filter_backup_{timestamp}.pkl"
        shutil.copy2(current_model_path, backup_model_path)
        print(f"💾 Backed up current model to: {backup_model_path}")

        # Get current model version for comparison
        try:
            from src.database.async_manager import AsyncDatabaseManager
            from src.utils.model_versioning import MLModelVersionManager

            db_manager = AsyncDatabaseManager()
            version_manager = MLModelVersionManager(db_manager)

            latest_version = asyncio.run(version_manager.get_latest_version())
            if latest_version:
                old_version_id = latest_version.id
                print(f"📊 Current model version: {latest_version.version_number}")
        except Exception as e:
            print(f"⚠️  Could not get current model version: {e}")

    # Train the model
    print("\n🤖 Training ML model...")
    filter_system = ContentFilter(model_path=current_model_path)

    training_result = filter_system.train_model(output_file)

    if training_result and training_result.get("success"):
        print("✅ Model retraining completed successfully!")

        # Mark annotations as used after successful retraining
        mark_annotations_as_used()

        # Mark feedback as used after successful retraining
        mark_feedback_as_used()

        # Save new model version to database
        new_version_id = None
        try:
            from src.database.async_manager import AsyncDatabaseManager
            from src.utils.model_versioning import MLModelVersionManager

            # Count feedback samples used (both correct and incorrect)
            feedback_count = len(feedback_df) if not feedback_df.empty else 0

            # Run all version-related DB work inside a single asyncio.run() so
            # the async engine lives and dies within one event loop — calling
            # asyncio.run() twice on the same AsyncDatabaseManager instance
            # would corrupt the connection pool.
            async def _save_version_and_artifact():
                db = AsyncDatabaseManager(pool_size=2, max_overflow=0)
                try:
                    vm = MLModelVersionManager(db)
                    version_id = await vm.save_model_version(
                        metrics=training_result,
                        _training_config={"original_file": original_file},
                        feedback_count=feedback_count,
                        model_file_path=current_model_path,
                    )
                    versioned_path = f"/app/models/content_filter_v{version_id}.pkl"
                    shutil.copy2(current_model_path, versioned_path)
                    await vm.set_version_artifact(version_id, versioned_path)
                    return version_id, versioned_path
                finally:
                    await db.close()

            new_version_id, versioned_artifact_path = asyncio.run(_save_version_and_artifact())

            print(f"📊 Saved new model version: {new_version_id}")
            print(f"💾 Saved versioned artifact: {versioned_artifact_path}")

            # Set the compared_with_version field for the new version
            if old_version_id and new_version_id:
                try:
                    async def update_comparison_reference():
                        from sqlalchemy import update

                        from src.database.models import MLModelVersionTable

                        db = AsyncDatabaseManager(pool_size=2, max_overflow=0)
                        try:
                            async with db.get_session() as session:
                                await session.execute(
                                    update(MLModelVersionTable)
                                    .where(MLModelVersionTable.id == new_version_id)
                                    .values(compared_with_version=old_version_id)
                                )
                                await session.commit()
                        finally:
                            await db.close()

                    asyncio.run(update_comparison_reference())
                    print(
                        f"📊 Set comparison reference: version {new_version_id} compares with version {old_version_id}"
                    )
                except Exception as e:
                    print(f"⚠️  Could not set comparison reference: {e}")

            # Automatically run backfill with new model
            print("\n🔄 Running automatic backfill with new model...")
            try:
                from src.database.manager import DatabaseManager
                from src.services.chunk_analysis_backfill import ChunkAnalysisBackfillService

                db_manager = DatabaseManager()
                sync_db = db_manager.get_session()
                try:
                    service = ChunkAnalysisBackfillService(sync_db)
                    backfill_results = service.backfill_all(min_hunt_score=50.0, min_confidence=0.7)
                    print(
                        f"✅ Backfill completed: {backfill_results.get('successful', 0)} successful, {backfill_results.get('failed', 0)} failed"
                    )
                finally:
                    sync_db.close()
            except Exception as e:
                print(f"⚠️  Backfill failed: {e}")

            # Return comparison data for API response
            training_result["comparison"] = True
            training_result["new_version_id"] = new_version_id
            training_result["old_version_id"] = old_version_id

        except Exception as e:
            print(f"⚠️  Could not save model version or run comparison: {e}")

        # Run evaluation on test set
        print("\n🧪 Running evaluation on test set...")
        eval_metrics = None

        # Try dedicated evaluator first (uses curated eval_set.csv)
        try:
            from src.utils.model_evaluation import ModelEvaluator

            evaluator = ModelEvaluator()
            eval_metrics = evaluator.evaluate_model(filter_system)
            print("✅ Evaluation complete (curated eval set)!")
            print(f"   - Misclassified: {eval_metrics['misclassified_count']}/{eval_metrics['total_eval_chunks']}")
        except (FileNotFoundError, ImportError) as e:
            print(f"   ℹ️  Curated eval set not available ({e})")
            print("   Falling back to training test-split metrics…")
        except Exception as e:
            print(f"⚠️  Evaluator failed: {e}")
            print("   Falling back to training test-split metrics…")

        # Fallback: use the training's own test-split metrics (80/20 split)
        if eval_metrics is None and training_result:
            eval_metrics = {
                "accuracy": training_result.get("accuracy", 0.0),
                "precision_huntable": training_result.get("precision_huntable", 0.0),
                "precision_not_huntable": training_result.get("precision_not_huntable", 0.0),
                "recall_huntable": training_result.get("recall_huntable", 0.0),
                "recall_not_huntable": training_result.get("recall_not_huntable", 0.0),
                "f1_score_huntable": training_result.get("f1_score_huntable", 0.0),
                "f1_score_not_huntable": training_result.get("f1_score_not_huntable", 0.0),
                "confusion_matrix": None,
            }
            print("✅ Using training test-split metrics for evaluation")

        if eval_metrics:
            print(f"   - Test Accuracy: {eval_metrics['accuracy']:.3f}")
            print(f"   - Precision (Huntable): {eval_metrics['precision_huntable']:.3f}")
            print(f"   - Recall (Huntable): {eval_metrics['recall_huntable']:.3f}")
            print(f"   - F1 Score (Huntable): {eval_metrics['f1_score_huntable']:.3f}")

            # Save evaluation metrics to the model version
            try:
                async def save_eval_metrics():
                    db = AsyncDatabaseManager(pool_size=2, max_overflow=0)
                    try:
                        vm = MLModelVersionManager(db)
                        latest = await vm.get_latest_version()
                        if latest:
                            success = await vm.save_evaluation_metrics(latest.id, eval_metrics)
                            if success:
                                print(f"✅ Evaluation metrics saved to model version {latest.version_number}")
                            else:
                                print("⚠️  Failed to save evaluation metrics to database")
                        else:
                            print("⚠️  No model version found to save evaluation metrics")
                    finally:
                        await db.close()

                asyncio.run(save_eval_metrics())

            except Exception as e:
                print(f"⚠️  Could not save evaluation metrics: {e}")
        else:
            print("⚠️  No evaluation metrics available")

        # Show statistics
        if not feedback_df.empty:
            total_feedback = len(feedback_df)
            incorrect_feedback = len(feedback_df[feedback_df["is_correct"] == False])
            correct_feedback = len(feedback_df[feedback_df["is_correct"] == True])

            print("\n📊 Feedback Statistics:")
            print(f"   - Total feedback entries: {total_feedback}")
            print(f"   - Correct classifications: {correct_feedback}")
            print(f"   - Incorrect classifications: {incorrect_feedback}")
            print(f"   - Accuracy from feedback: {correct_feedback / total_feedback * 100:.1f}%")
            print(f"   - Training examples created: {correct_feedback + incorrect_feedback}")

        return training_result
    if training_result and training_result.get("error"):
        print(f"❌ Model retraining failed: {training_result['error']}")
    else:
        print("❌ Model retraining failed")
    # Restore backup if training failed
    if backup_model_path and os.path.exists(backup_model_path):
        shutil.copy2(backup_model_path, current_model_path)
        print(f"🔄 Restored backup model from: {backup_model_path}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Retrain ML model with user feedback")
    parser.add_argument(
        "--original", default="outputs/training_data/combined_training_data.csv", help="Original training data file"
    )
    parser.add_argument(
        "--output",
        default="outputs/training_data/retrained_training_data.csv",
        help="Output file for combined training data",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    success = retrain_model_with_feedback(original_file=args.original, output_file=args.output)

    if success:
        print("\n🎉 Retraining completed successfully!")
        print("The model has been updated with user feedback.")
        print("Restart the web application to use the updated model.")
    else:
        print("\n💥 Retraining failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
