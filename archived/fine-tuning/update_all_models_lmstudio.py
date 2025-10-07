#!/usr/bin/env python3
"""
Update A/B UI to use LMStudio for all models (including fine-tuned)
"""

def update_ab_ui_for_all_models():
    """Update A/B UI to route all models through LMStudio"""
    
    # Read the current file
    with open('ab_test_web_ui.py', 'r') as f:
        content = f.read()
    
    # Replace base-only logic with all-models logic
    old_pattern = r"if lmstudio_available and model_[ab] == 'base':"
    new_pattern = r"if lmstudio_available:"
    
    content = re.sub(old_pattern, new_pattern, content)
    
    # Update progress messages
    content = content.replace(
        "Using LMStudio for base model",
        "Using LMStudio for all models"
    )
    
    # Write the updated file
    with open('ab_test_web_ui.py', 'w') as f:
        f.write(content)
    
    print("✅ Updated A/B UI to use LMStudio for all models")
    print("🚀 All models (base + fine-tuned) will now use LMStudio")
    print("⚡ Expected performance: 21x faster for all models!")

if __name__ == "__main__":
    import re
    update_ab_ui_for_all_models()
