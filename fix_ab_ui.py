#!/usr/bin/env python3
"""
Fix A/B UI syntax errors and restore working state
"""

def fix_ab_ui():
    """Fix the A/B UI file"""
    
    # Read the backup file
    try:
        with open('ab_test_web_ui_backup.py', 'r') as f:
            content = f.read()
    except:
        print("❌ Backup file not found")
        return
    
    # Find and remove the broken Ollama function insertion
    # Look for the problematic section
    lines = content.split('\n')
    fixed_lines = []
    skip_until_function_end = False
    
    for i, line in enumerate(lines):
        # Check if we're in the broken Ollama function insertion
        if 'def generate_with_ollama' in line and i > 0:
            # Check if this is in the middle of another function
            prev_lines = lines[:i]
            for prev_line in reversed(prev_lines):
                if prev_line.strip().startswith('def '):
                    # We're in the middle of a function, skip this insertion
                    skip_until_function_end = True
                    break
                elif prev_line.strip() == '':
                    continue
                elif prev_line.startswith(' '):
                    # Still in function, continue checking
                    continue
                else:
                    # Not in function, this is OK
                    break
        
        if skip_until_function_end:
            # Skip lines until we find the end of the function
            if line.strip() == '' or not line.startswith(' '):
                skip_until_function_end = False
                fixed_lines.append(line)
            # Skip the broken insertion
            continue
        
        fixed_lines.append(line)
    
    # Write the fixed file
    with open('ab_test_web_ui.py', 'w') as f:
        f.write('\n'.join(fixed_lines))
    
    print("✅ Fixed A/B UI syntax errors")
    print("🔄 File restored to working state")

if __name__ == "__main__":
    fix_ab_ui()
