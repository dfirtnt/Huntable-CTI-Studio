#!/usr/bin/env python3
"""
Debug garbage content detection
"""

import sys
import os
sys.path.insert(0, 'src')

from utils.content import _is_garbage_content

def debug_content(content, name):
    print(f"\n🔍 Debugging: {name}")
    print(f"Content: {content}")
    print(f"Length: {len(content)}")
    
    # Count problematic characters
    problematic_chars = sum(1 for c in content if c in '[]{}|\\')
    total_chars = len(content)
    
    print(f"Problematic chars: {problematic_chars}")
    print(f"Total chars: {total_chars}")
    
    if total_chars > 0:
        ratio = problematic_chars / total_chars
        print(f"Ratio: {ratio:.3f}")
        print(f"Threshold: 0.1")
        print(f"Would trigger ratio: {ratio > 0.1}")
    
    # Check consecutive problematic characters
    consecutive_count = 0
    max_consecutive = 0
    consecutive_positions = []
    
    for i, char in enumerate(content):
        if char in '[]{}|\\':
            consecutive_count += 1
            if consecutive_count == 1:
                consecutive_positions.append(i)
        else:
            if consecutive_count > 0:
                if consecutive_count >= 3:
                    print(f"  Found {consecutive_count} consecutive at position {consecutive_positions[-1]}")
                consecutive_count = 0
                consecutive_positions = []
    
    # Check final sequence
    if consecutive_count >= 3:
        print(f"  Found {consecutive_count} consecutive at position {consecutive_positions[-1]}")
    
    print(f"Max consecutive: {max_consecutive}")
    print(f"Would trigger consecutive: {max_consecutive >= 3}")
    
    # Check each character
    print("Character analysis:")
    for i, char in enumerate(content):
        if char in '[]{}|\\':
            print(f"  Position {i}: '{char}' (problematic)")
    
    result = _is_garbage_content(content)
    print(f"Final result: {result}")

if __name__ == "__main__":
    normal_content = "This is a normal article about cybersecurity threats and how to detect them."
    garbage_content = "`E9 UI=) cwCz _9hvtYfL\" K rK]%A^Yww<4\\] q4gV(Q(W-Ms]nC:} YH`(PP > T0IFc4GSP-1"
    
    debug_content(normal_content, "Normal Content")
    debug_content(garbage_content, "Garbage Content")
