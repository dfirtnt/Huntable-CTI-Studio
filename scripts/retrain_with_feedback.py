#!/usr/bin/env python3
"""
Script to retrain the ML model using collected user feedback.
Combines original training data with user feedback to improve model accuracy.
"""

import sys
import os
import pandas as pd
import argparse
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from utils.content_filter import ContentFilter

def load_feedback_data(feedback_file: str = "outputs/training_data/chunk_classification_feedback.csv"):
    """Load user feedback data from CSV file."""
    if not os.path.exists(feedback_file):
        print(f"⚠️  No feedback file found at {feedback_file}")
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(feedback_file)
        print(f"📊 Loaded {len(df)} feedback entries")
        return df
    except Exception as e:
        print(f"❌ Error loading feedback data: {e}")
        return pd.DataFrame()

def process_feedback_for_training(feedback_df: pd.DataFrame):
    """Process feedback data into training format."""
    if feedback_df.empty:
        return pd.DataFrame()
    
    # Filter for incorrect classifications (these are the ones we want to learn from)
    incorrect_feedback = feedback_df[feedback_df['is_correct'] == False]
    
    if incorrect_feedback.empty:
        print("✅ No incorrect classifications found in feedback")
        return pd.DataFrame()
    
    print(f"🔍 Found {len(incorrect_feedback)} incorrect classifications to learn from")
    
    # Create training examples from feedback
    training_examples = []
    
    for _, row in incorrect_feedback.iterrows():
        training_examples.append({
            'record_number': f"feedback_{row['chunk_id']}",
            'highlighted_text': row['chunk_text'],
            'classification': row['user_classification']
        })
    
    return pd.DataFrame(training_examples)

def combine_training_data(original_file: str, feedback_df: pd.DataFrame):
    """Combine original training data with feedback data."""
    # Load original training data
    if not os.path.exists(original_file):
        print(f"❌ Original training file not found: {original_file}")
        return None
    
    original_df = pd.read_csv(original_file)
    print(f"📚 Loaded {len(original_df)} original training examples")
    
    # Process feedback data
    feedback_training = process_feedback_for_training(feedback_df)
    
    if feedback_training.empty:
        print("ℹ️  No feedback data to add, using original training data only")
        return original_df
    
    # Combine datasets
    combined_df = pd.concat([original_df, feedback_training], ignore_index=True)
    
    # Update record numbers to be sequential
    combined_df['record_number'] = range(1, len(combined_df) + 1)
    
    print(f"🔄 Combined dataset: {len(combined_df)} total examples")
    print(f"   - Original: {len(original_df)}")
    print(f"   - Feedback: {len(feedback_training)}")
    
    return combined_df

def retrain_model_with_feedback(original_file: str = "outputs/training_data/combined_training_data.csv", 
                               feedback_file: str = "outputs/training_data/chunk_classification_feedback.csv",
                               output_file: str = "outputs/training_data/retrained_training_data.csv"):
    """Retrain the model using original data plus user feedback."""
    import shutil
    import asyncio
    from datetime import datetime
    
    print("🚀 Starting model retraining with user feedback...")
    print("=" * 60)
    
    # Load feedback data
    feedback_df = load_feedback_data(feedback_file)
    
    # Combine training data
    combined_df = combine_training_data(original_file, feedback_df)
    
    if combined_df is None:
        print("❌ Failed to prepare training data")
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
    
    if training_result and training_result.get('success'):
        print("✅ Model retraining completed successfully!")
        
        # Save new model version to database
        new_version_id = None
        try:
            from src.database.async_manager import AsyncDatabaseManager
            from src.utils.model_versioning import MLModelVersionManager
            
            db_manager = AsyncDatabaseManager()
            version_manager = MLModelVersionManager(db_manager)
            
            # Count feedback samples used
            feedback_count = len(feedback_df[feedback_df['is_correct'] == False]) if not feedback_df.empty else 0
            
            new_version_id = asyncio.run(version_manager.save_model_version(
                metrics=training_result,
                training_config={'original_file': original_file, 'feedback_file': feedback_file},
                feedback_count=feedback_count,
                model_file_path=current_model_path
            ))
            
            print(f"📊 Saved new model version: {new_version_id}")
            
            # Set the compared_with_version field for the new version
            if old_version_id and new_version_id:
                try:
                    # Update the new version to reference the old version
                    async def update_comparison_reference():
                        async with db_manager.get_session() as session:
                            from sqlalchemy import update
                            from src.database.models import MLModelVersionTable
                            await session.execute(
                                update(MLModelVersionTable)
                                .where(MLModelVersionTable.id == new_version_id)
                                .values(compared_with_version=old_version_id)
                            )
                            await session.commit()
                    
                    asyncio.run(update_comparison_reference())
                    print(f"📊 Set comparison reference: version {new_version_id} compares with version {old_version_id}")
                    
                    # Return comparison data for API response
                    training_result['comparison'] = True
                    training_result['new_version_id'] = new_version_id
                    training_result['old_version_id'] = old_version_id
                    
                except Exception as e:
                    print(f"⚠️  Could not set comparison reference: {e}")
                    # Still return the version IDs for the API to handle comparison
                    training_result['comparison'] = True
                    training_result['new_version_id'] = new_version_id
                    training_result['old_version_id'] = old_version_id
            
        except Exception as e:
            print(f"⚠️  Could not save model version or run comparison: {e}")
        
        # Run evaluation on test set
        print("\n🧪 Running evaluation on test set...")
        try:
            from utils.model_evaluation import ModelEvaluator
            
            evaluator = ModelEvaluator()
            eval_metrics = evaluator.evaluate_model(content_filter)
            
            print(f"✅ Evaluation complete!")
            print(f"   - Test Accuracy: {eval_metrics['accuracy']:.3f}")
            print(f"   - Precision (Huntable): {eval_metrics['precision_huntable']:.3f}")
            print(f"   - Precision (Not Huntable): {eval_metrics['precision_not_huntable']:.3f}")
            print(f"   - Recall (Huntable): {eval_metrics['recall_huntable']:.3f}")
            print(f"   - Recall (Not Huntable): {eval_metrics['recall_not_huntable']:.3f}")
            print(f"   - F1 Score (Huntable): {eval_metrics['f1_score_huntable']:.3f}")
            print(f"   - F1 Score (Not Huntable): {eval_metrics['f1_score_not_huntable']:.3f}")
            print(f"   - Misclassified: {eval_metrics['misclassified_count']}/{eval_metrics['total_eval_chunks']}")
            
            # Save evaluation metrics to model version
            try:
                from utils.model_versioning import MLModelVersionManager
                from database.async_manager import AsyncDatabaseManager
                import asyncio
                
                async def save_eval_metrics():
                    db_manager = AsyncDatabaseManager()
                    version_manager = MLModelVersionManager(db_manager)
                    latest_version = await version_manager.get_latest_version()
                    
                    if latest_version:
                        success = await version_manager.save_evaluation_metrics(latest_version.id, eval_metrics)
                        if success:
                            print(f"✅ Evaluation metrics saved to model version {latest_version.version_number}")
                        else:
                            print("⚠️  Failed to save evaluation metrics to database")
                    else:
                        print("⚠️  No model version found to save evaluation metrics")
                    
                    await db_manager.close()
                
                asyncio.run(save_eval_metrics())
                
            except Exception as e:
                print(f"⚠️  Could not save evaluation metrics: {e}")
                
        except Exception as e:
            print(f"⚠️  Could not run evaluation: {e}")
        
        # Show statistics
        if not feedback_df.empty:
            total_feedback = len(feedback_df)
            incorrect_feedback = len(feedback_df[feedback_df['is_correct'] == False])
            correct_feedback = len(feedback_df[feedback_df['is_correct'] == True])
            
            print(f"\n📊 Feedback Statistics:")
            print(f"   - Total feedback entries: {total_feedback}")
            print(f"   - Correct classifications: {correct_feedback}")
            print(f"   - Incorrect classifications: {incorrect_feedback}")
            print(f"   - Accuracy from feedback: {correct_feedback/total_feedback*100:.1f}%")
        
        return training_result
    else:
        print("❌ Model retraining failed")
        # Restore backup if training failed
        if backup_model_path and os.path.exists(backup_model_path):
            shutil.copy2(backup_model_path, current_model_path)
            print(f"🔄 Restored backup model from: {backup_model_path}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Retrain ML model with user feedback')
    parser.add_argument('--original', default='outputs/training_data/combined_training_data.csv',
                       help='Original training data file')
    parser.add_argument('--feedback', default='outputs/training_data/chunk_classification_feedback.csv',
                       help='User feedback data file')
    parser.add_argument('--output', default='outputs/training_data/retrained_training_data.csv',
                       help='Output file for combined training data')
    parser.add_argument('--verbose', action='store_true',
                       help='Verbose output')
    
    args = parser.parse_args()
    
    success = retrain_model_with_feedback(
        original_file=args.original,
        feedback_file=args.feedback,
        output_file=args.output
    )
    
    if success:
        print("\n🎉 Retraining completed successfully!")
        print("The model has been updated with user feedback.")
        print("Restart the web application to use the updated model.")
    else:
        print("\n💥 Retraining failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
