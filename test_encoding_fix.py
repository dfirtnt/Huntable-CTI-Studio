#!/usr/bin/env python3
"""
Test script to check if encoding fixes work on the corrupted text.
"""

import sys
import os
sys.path.insert(0, 'src')

from utils.content import ContentCleaner

def test_encoding_fix():
    # Test the corrupted text from your example
    corrupted_text = "SentinelBrowserNativeHost.exe , a legitimate SentinelOne executable, was launched from the user‚Äö√Ñ√¥s Downloads folder"
    
    print("Original corrupted text:")
    print(corrupted_text)
    print()
    
    # Test our content cleaner
    cleaned_text = ContentCleaner.clean_text_characters(corrupted_text)
    
    print("After ContentCleaner.clean_text_characters():")
    print(cleaned_text)
    print()
    
    # Check if the corruption is fixed
    if '‚Äö√Ñ√¥s' in cleaned_text:
        print("❌ CORRUPTION STILL PRESENT")
    else:
        print("✅ CORRUPTION REMOVED")
    
    # Test HTML cleaning too
    html_cleaned = ContentCleaner.html_to_text(corrupted_text)
    print("After ContentCleaner.html_to_text():")
    print(html_cleaned)
    print()
    
    # Test the specific pattern we saw in the database
    db_corrupted = "user‚Äö√Ñ√¥s Downloads folder"
    db_cleaned = ContentCleaner.clean_text_characters(db_corrupted)
    print("Database corruption test:")
    print(f"Original: {db_corrupted}")
    print(f"Cleaned: {db_cleaned}")

if __name__ == "__main__":
    test_encoding_fix()
