#!/usr/bin/env python3
"""
Quick script to manually trigger agentic workflow for an article.

Usage:
    python trigger_workflow.py <article_id>
    
Uses the FastAPI endpoint, so no local dependencies required.
"""

import sys
import requests
import os

if len(sys.argv) < 2:
    print("Usage: python trigger_workflow.py <article_id>")
    sys.exit(1)

article_id = int(sys.argv[1])

# Get API URL from environment or use default
api_url = os.getenv("API_URL", "http://localhost:8001")
endpoint = f"{api_url}/api/workflow/articles/{article_id}/trigger"

print(f"Triggering workflow for article {article_id}...")

try:
    response = requests.post(endpoint, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ {data.get('message', 'Workflow triggered successfully')}")
        if 'execution_id' in data:
            print(f"   Execution ID: {data['execution_id']}")
    elif response.status_code == 404:
        print(f"❌ Article {article_id} not found")
    elif response.status_code == 400:
        error = response.json()
        print(f"❌ {error.get('detail', 'Failed to trigger workflow')}")
    else:
        print(f"❌ Error: HTTP {response.status_code}")
        try:
            error = response.json()
            print(f"   {error.get('detail', 'Unknown error')}")
        except:
            print(f"   {response.text[:200]}")
            
except requests.exceptions.ConnectionError:
    print(f"❌ Cannot connect to API at {api_url}")
    print(f"   Make sure the FastAPI server is running")
    print(f"   Set API_URL environment variable if using different URL")
except requests.exceptions.Timeout:
    print(f"❌ Request timed out. API may be slow or unavailable.")
except Exception as e:
    print(f"❌ Error: {e}")

