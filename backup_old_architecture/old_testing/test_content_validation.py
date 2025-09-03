#!/usr/bin/env python3
"""
Test the new content validation that rejects garbage content
"""

import sys
import os
sys.path.insert(0, 'src')

from utils.content import validate_content, _is_garbage_content, _has_compression_failure_indicators

def test_garbage_detection():
    """Test garbage content detection"""
    print("🧪 Testing Garbage Content Detection")
    print("=" * 50)
    
    # Test cases
    test_cases = [
        {
            "name": "Normal content",
            "content": "This is a normal article about cybersecurity threats and how to detect them.",
            "expected_garbage": False
        },
        {
            "name": "Garbage content (high special chars)",
            "content": "`E9 UI=) cwCz _9hvtYfL\" K rK]%A^Yww<4\\] q4gV(Q(W-Ms]nC:} YH`(PP > T0IFc4GSP-1",
            "expected_garbage": True
        },
        {
            "name": "Compression failure message",
            "content": "This article was collected from Red Canary but the content extraction failed due to website compression issues.",
            "expected_garbage": True
        },
        {
            "name": "Mixed content (some garbage)",
            "content": "This is a normal article about cybersecurity. `E9 UI=) cwCz _9hvtYfL\" K rK]%A^Yww<4\\] q4gV(Q(W-Ms]nC:} YH`(PP > T0IFc4GSP-1",
            "expected_garbage": True
        }
    ]
    
    for test_case in test_cases:
        print(f"\n📝 Testing: {test_case['name']}")
        print(f"Content: {test_case['content'][:50]}...")
        
        # Test garbage detection
        is_garbage = _is_garbage_content(test_case['content'])
        print(f"Garbage detected: {is_garbage} (expected: {test_case['expected_garbage']})")
        
        # Test compression failure detection
        has_failure = _has_compression_failure_indicators(test_case['content'])
        print(f"Compression failure detected: {has_failure}")
        
        # Test full validation
        issues = validate_content("Test Title", test_case['content'], "https://example.com")
        if issues:
            print(f"Validation issues: {issues}")
        else:
            print("✅ No validation issues")
        
        # Check if test passed
        if is_garbage == test_case['expected_garbage']:
            print("✅ Test passed")
        else:
            print("❌ Test failed")

def test_validation_integration():
    """Test how validation integrates with the full system"""
    print("\n🔗 Testing Validation Integration")
    print("=" * 50)
    
    # Test the actual validation function
    test_content = "`E9 UI=) cwCz _9hvtYfL\" K rK]%A^Yww<4\\] q4gV(Q(W-Ms]nC:} YH`(PP > T0IFc4GSP-1"
    
    print(f"Testing content: {test_content[:50]}...")
    
    issues = validate_content("Test Article", test_content, "https://example.com")
    
    print(f"Validation result: {issues}")
    
    if "Content appears to be garbage/compressed data" in issues:
        print("✅ Garbage content correctly rejected")
    else:
        print("❌ Garbage content not detected")

if __name__ == "__main__":
    test_garbage_detection()
    test_validation_integration()
    
    print("\n🎯 Summary:")
    print("The new validation should now:")
    print("• Reject articles with garbage content")
    print("• Reject articles with compression failure messages")
    print("• Allow only clean, readable content into the database")
