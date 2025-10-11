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
    
    # Train the model
    print("\n🤖 Training ML model...")
    filter_system = ContentFilter(model_path="/app/models/content_filter.pkl")
    
    success = filter_system.train_model(output_file)
    
    if success:
        print("✅ Model retraining completed successfully!")
        
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
        
        return True
    else:
        print("❌ Model retraining failed")
        return False

def main():
    parser = argparse.ArgumentParser(description='Retrain ML model with user feedback')
    parser.add_argument('--original', default='outputs/combined_training_data.csv',
                       help='Original training data file')
    parser.add_argument('--feedback', default='outputs/chunk_classification_feedback.csv',
                       help='User feedback data file')
    parser.add_argument('--output', default='outputs/retrained_training_data.csv',
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
