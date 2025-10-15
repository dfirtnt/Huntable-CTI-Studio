#!/usr/bin/env python3
"""
Analyze annotation_evals.csv to determine if it's suitable for evaluation.
Compares against training data to check for leakage and similarity.
"""

import pandas as pd
import sys
from difflib import SequenceMatcher
from src.database.manager import DatabaseManager

def text_similarity(text1, text2):
    """Calculate similarity ratio between two texts."""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

def main():
    # Load eval data
    print("Loading evaluation data...")
    eval_df = pd.read_csv('annotation_evals.csv')
    print(f"Found {len(eval_df)} evaluation samples")
    print(f"\nLabel distribution:")
    print(eval_df['classification'].value_counts())
    print()
    
    # Load training data from database
    print("Loading training data from database...")
    db_manager = DatabaseManager()
    db = db_manager.get_session()
    
    try:
        # Get all annotations (training data)
        query = """
        SELECT 
            a.id,
            a.chunk_text,
            a.label
        FROM annotations a
        WHERE a.chunk_text IS NOT NULL
        """
        
        training_data = pd.read_sql(query, db.bind)
        print(f"Found {len(training_data)} training samples")
        print(f"\nTraining label distribution:")
        print(training_data['label'].value_counts())
        print()
        
        # Analysis 1: Check for exact duplicates
        print("=" * 80)
        print("ANALYSIS 1: Checking for exact duplicates...")
        print("=" * 80)
        
        eval_texts = set(eval_df['highlighted_text'].str.strip().str.lower())
        training_texts = set(training_data['chunk_text'].str.strip().str.lower())
        
        exact_matches = eval_texts.intersection(training_texts)
        
        if exact_matches:
            print(f"⚠️  WARNING: Found {len(exact_matches)} EXACT DUPLICATES in training data!")
            print("These should be removed from eval set to avoid data leakage.")
            print("\nFirst 3 duplicates:")
            for i, text in enumerate(list(exact_matches)[:3]):
                print(f"\n{i+1}. {text[:200]}...")
        else:
            print("✅ No exact duplicates found - Good!")
        
        # Analysis 2: Check for high similarity matches
        print("\n" + "=" * 80)
        print("ANALYSIS 2: Checking for high similarity (>0.9) matches...")
        print("=" * 80)
        
        high_similarity_count = 0
        high_similarity_examples = []
        
        for eval_idx, eval_row in eval_df.iterrows():
            eval_text = eval_row['highlighted_text']
            max_similarity = 0
            most_similar_training = None
            
            for train_idx, train_row in training_data.iterrows():
                train_text = train_row['chunk_text']
                similarity = text_similarity(eval_text, train_text)
                
                if similarity > max_similarity:
                    max_similarity = similarity
                    most_similar_training = train_text
            
            if max_similarity > 0.9:
                high_similarity_count += 1
                if len(high_similarity_examples) < 3:
                    high_similarity_examples.append({
                        'eval_text': eval_text[:200],
                        'train_text': most_similar_training[:200],
                        'similarity': max_similarity
                    })
        
        if high_similarity_count > 0:
            print(f"⚠️  WARNING: Found {high_similarity_count} eval samples with >90% similarity to training data")
            print("These may cause overly optimistic evaluation results.")
            print("\nExamples:")
            for i, example in enumerate(high_similarity_examples):
                print(f"\n{i+1}. Similarity: {example['similarity']:.2%}")
                print(f"   Eval: {example['eval_text']}...")
                print(f"   Train: {example['train_text']}...")
        else:
            print("✅ No high-similarity matches found - Good!")
        
        # Analysis 3: Text length distribution
        print("\n" + "=" * 80)
        print("ANALYSIS 3: Text length distribution comparison...")
        print("=" * 80)
        
        eval_df['text_length'] = eval_df['highlighted_text'].str.len()
        training_data['text_length'] = training_data['chunk_text'].str.len()
        
        print("\nEvaluation set:")
        print(f"  Mean length: {eval_df['text_length'].mean():.0f} chars")
        print(f"  Median length: {eval_df['text_length'].median():.0f} chars")
        print(f"  Min/Max: {eval_df['text_length'].min()}/{eval_df['text_length'].max()} chars")
        
        print("\nTraining set:")
        print(f"  Mean length: {training_data['text_length'].mean():.0f} chars")
        print(f"  Median length: {training_data['text_length'].median():.0f} chars")
        print(f"  Min/Max: {training_data['text_length'].min()}/{training_data['text_length'].max()} chars")
        
        # Analysis 4: Label consistency check
        print("\n" + "=" * 80)
        print("ANALYSIS 4: Label distribution balance...")
        print("=" * 80)
        
        eval_huntable_pct = (eval_df['classification'] == 'Huntable').sum() / len(eval_df) * 100
        train_huntable_pct = (training_data['label'] == 'huntable').sum() / len(training_data) * 100
        
        print(f"\nEval set: {eval_huntable_pct:.1f}% Huntable")
        print(f"Training set: {train_huntable_pct:.1f}% huntable")
        
        if abs(eval_huntable_pct - train_huntable_pct) > 20:
            print(f"⚠️  WARNING: Label distribution differs by {abs(eval_huntable_pct - train_huntable_pct):.1f}%")
            print("Eval results may not reflect real-world performance.")
        else:
            print("✅ Label distributions are reasonably similar")
        
        # Final recommendation
        print("\n" + "=" * 80)
        print("FINAL RECOMMENDATION")
        print("=" * 80)
        
        issues = []
        if exact_matches:
            issues.append(f"- {len(exact_matches)} exact duplicates with training data")
        if high_similarity_count > 0:
            issues.append(f"- {high_similarity_count} samples with >90% similarity to training")
        if abs(eval_huntable_pct - train_huntable_pct) > 20:
            issues.append(f"- Label distribution differs significantly ({abs(eval_huntable_pct - train_huntable_pct):.1f}%)")
        
        if issues:
            print("\n⚠️  ISSUES FOUND:")
            for issue in issues:
                print(issue)
            print("\n❌ RECOMMENDATION: Clean up the eval set before using for evaluation")
            print("   - Remove exact duplicates")
            print("   - Consider removing high-similarity samples")
            print("   - Optionally rebalance label distribution")
        else:
            print("\n✅ RECOMMENDATION: This eval set looks suitable for evaluation!")
            print(f"   - {len(eval_df)} samples")
            print(f"   - No data leakage detected")
            print(f"   - Reasonable label distribution")
            print(f"   - Similar text characteristics to training data")
        
    finally:
        db.close()

if __name__ == '__main__':
    main()

