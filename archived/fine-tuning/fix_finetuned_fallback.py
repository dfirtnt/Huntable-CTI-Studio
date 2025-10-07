#!/usr/bin/env python3
"""
Fix A/B UI to fallback to HuggingFace for fine-tuned models not in LMStudio
"""

import re

def fix_finetuned_fallback():
    """Update A/B UI to fallback to HuggingFace for fine-tuned models"""
    
    # Read the current file
    with open('ab_test_web_ui.py', 'r') as f:
        content = f.read()
    
    # Define the new logic for model A
    new_logic_a = '''        # Check if model is available in LMStudio
        lmstudio_model_available = lmstudio_available and model_a == 'base'
        
        if lmstudio_model_available:
            # Use LMStudio for base model (much faster)
            update_progress('model_a', 'generating', 50, 'Using LMStudio for base model')
            results['model_a'] = generate_with_lmstudio(cti_text)
            update_progress('model_a', 'completed', 100, 'LMStudio generation complete')
        elif not load_model_if_needed(model_a):'''
    
    # Define the new logic for model B
    new_logic_b = '''            # Check if model is available in LMStudio
            lmstudio_model_available = lmstudio_available and model_b == 'base'
            
            if lmstudio_model_available:
                # Use LMStudio for base model (much faster)
                update_progress('model_b', 'generating', 50, 'Using LMStudio for base model')
                results['model_b'] = generate_with_lmstudio(cti_text)
                update_progress('model_b', 'completed', 100, 'LMStudio generation complete')
            elif not load_model_if_needed(model_b):'''
    
    # Replace the current logic
    old_pattern_a = r"if lmstudio_available:.*?elif not load_model_if_needed\(model_a\):"
    old_pattern_b = r"if lmstudio_available:.*?elif not load_model_if_needed\(model_b\):"
    
    content = re.sub(old_pattern_a, new_logic_a, content, flags=re.DOTALL)
    content = re.sub(old_pattern_b, new_logic_b, content, flags=re.DOTALL)
    
    # Write the updated file
    with open('ab_test_web_ui.py', 'w') as f:
        f.write(content)
    
    print("✅ Fixed A/B UI fallback logic")
    print("🚀 Base models → LMStudio (3s)")
    print("🔄 Fine-tuned models → HuggingFace (30s)")
    print("💡 To get 3s for fine-tuned: Convert to GGUF and load in LMStudio")

if __name__ == "__main__":
    fix_finetuned_fallback()
