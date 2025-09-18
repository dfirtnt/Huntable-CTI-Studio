#!/usr/bin/env python3
"""
Simple OpenAI API key test script
"""

import os
import sys
import getpass
from openai import OpenAI

def test_openai_key():
    """Test OpenAI API key by making a simple completion request"""
    
    # Get API key from environment or prompt user
    api_key = os.getenv('OPENAI_API_KEY') or os.getenv('CUSTOMGPT_API_KEY')
    
    if not api_key:
        print("No OpenAI API key found in environment variables")
        api_key = getpass.getpass("Enter your OpenAI API key: ").strip()
        
        if not api_key:
            print("❌ No API key provided")
            return False
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=api_key)
        
        # Test with a simple completion
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": "Say 'Hello, API key is working!' and nothing else."}
            ],
            max_tokens=50,
            temperature=0
        )
        
        print("✅ OpenAI API key is valid!")
        print(f"Response: {response.choices[0].message.content}")
        return True
        
    except Exception as e:
        print(f"❌ API key test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_openai_key()
    sys.exit(0 if success else 1) 