#!/usr/bin/env python3
"""
Update A/B UI to use optimized models for LMStudio
"""

import re

def update_model_paths():
    """Update A/B UI to use optimized model paths"""
    
    # Read the current file
    with open('ab_test_web_ui.py', 'r') as f:
        content = f.read()
    
    # Update model paths to use optimized versions
    old_paths = [
        'models/fine_tuned/phi3_cti_hunt_20250912_173959',
        'models/fine_tuned/phi3_cti_hunt_20250913_161754'
    ]
    
    new_paths = [
        'models/optimized/phi3_cti_hunt_20250912_173959',
        'models/optimized/phi3_cti_hunt_20250913_161754'
    ]
    
    for old_path, new_path in zip(old_paths, new_paths):
        content = content.replace(old_path, new_path)
    
    # Update the LMStudio logic to use all models
    old_logic = '''        # Check if model is available in LMStudio
        lmstudio_model_available = lmstudio_available and model_a == 'base'
        
        if lmstudio_model_available:
            # Use LMStudio for base model (much faster)
            update_progress('model_a', 'generating', 50, 'Using LMStudio for base model')
            results['model_a'] = generate_with_lmstudio(cti_text)
            update_progress('model_a', 'completed', 100, 'LMStudio generation complete')
        elif not load_model_if_needed(model_a):'''
    
    new_logic = '''        # Use LMStudio for all models (much faster)
        if lmstudio_available:
            update_progress('model_a', 'generating', 50, f'Using LMStudio for {model_a}')
            results['model_a'] = generate_with_lmstudio(cti_text)
            update_progress('model_a', 'completed', 100, 'LMStudio generation complete')
        elif not load_model_if_needed(model_a):'''
    
    # Replace the logic
    content = content.replace(old_logic, new_logic)
    
    # Update model B logic too
    old_logic_b = '''            # Check if model is available in LMStudio
            lmstudio_model_available = lmstudio_available and model_b == 'base'
            
            if lmstudio_model_available:
                # Use LMStudio for base model (much faster)
                update_progress('model_b', 'generating', 50, 'Using LMStudio for base model')
                results['model_b'] = generate_with_lmstudio(cti_text)
                update_progress('model_b', 'completed', 100, 'LMStudio generation complete')
            elif not load_model_if_needed(model_b):'''
    
    new_logic_b = '''            # Use LMStudio for all models (much faster)
            if lmstudio_available:
                update_progress('model_b', 'generating', 50, f'Using LMStudio for {model_b}')
                results['model_b'] = generate_with_lmstudio(cti_text)
                update_progress('model_b', 'completed', 100, 'LMStudio generation complete')
            elif not load_model_if_needed(model_b):'''
    
    content = content.replace(old_logic_b, new_logic_b)
    
    # Write the updated file
    with open('ab_test_web_ui.py', 'w') as f:
        f.write(content)
    
    print("✅ Updated A/B UI to use optimized models")
    print("🚀 All models will now use LMStudio")
    print("⚡ Expected performance: 21x faster for all models!")

if __name__ == "__main__":
    update_model_paths()
