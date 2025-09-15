#!/usr/bin/env python3
"""
Update A/B UI to use Ollama for fine-tuned models
"""

import re
import subprocess

def update_ab_ui_for_ollama():
    """Update A/B UI to use Ollama for fine-tuned models"""
    
    # Read the current file
    with open('ab_test_web_ui.py', 'r') as f:
        content = f.read()
    
    # Add subprocess import if not present
    if 'import subprocess' not in content:
        content = content.replace('import requests', 'import requests\nimport subprocess')
    
    # Add Ollama function after LMStudio function
    ollama_function = '''
def generate_with_ollama(prompt, model_name="phi3-cti-hunt", max_tokens=200):
    """Generate text using Ollama API"""
    try:
        result = subprocess.run(
            ["ollama", "run", model_name, prompt],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.error(f"Ollama generation error: {result.stderr}")
            return f"Ollama Error: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        logger.error("Ollama generation timed out")
        return "Ollama Error: Generation timed out"
    except Exception as e:
        logger.error(f"Ollama generation error: {str(e)}")
        return f"Ollama Error: {str(e)}"
'''
    
    # Insert after LMStudio function
    lmstudio_end = content.find('def generate_with_lmstudio')
    if lmstudio_end != -1:
        # Find end of LMStudio function
        lines = content[lmstudio_end:].split('\n')
        function_end = 0
        indent_level = None
        
        for i, line in enumerate(lines):
            if i == 0:
                continue
            if line.strip() == '':
                continue
            if indent_level is None and line.startswith(' '):
                indent_level = len(line) - len(line.lstrip())
            if indent_level is not None and line.strip() != '' and not line.startswith(' ' * indent_level):
                function_end = lmstudio_end + len('\n'.join(lines[:i]))
                break
        
        if function_end > 0:
            content = content[:function_end] + '\n' + ollama_function + content[function_end:]
    
    # Update routing logic
    old_pattern = r"if lmstudio_available:"
    new_pattern = r"if lmstudio_available and model_a == 'base':"
    content = re.sub(old_pattern, new_pattern, content)
    
    # Add Ollama routing for fine-tuned models
    old_elif = r"elif not load_model_if_needed\(model_a\):"
    new_elif = r"""elif 'phi3_cti_hunt' in model_a:
            update_progress('model_a', 'generating', 50, f'Using Ollama for {model_a}')
            results['model_a'] = generate_with_ollama(cti_text, 'phi3-cti-hunt')
            update_progress('model_a', 'completed', 100, 'Ollama generation complete')
        elif not load_model_if_needed(model_a):"""
    
    content = re.sub(old_elif, new_elif, content)
    
    # Write updated file
    with open('ab_test_web_ui.py', 'w') as f:
        f.write(content)
    
    print("✅ Updated A/B UI for Ollama integration")
    print("🚀 Base models → LMStudio (2.7s)")
    print("🔄 Fine-tuned models → Ollama (fast)")
    print("⚡ Expected performance: Fast inference for all models!")

if __name__ == "__main__":
    update_ab_ui_for_ollama()
