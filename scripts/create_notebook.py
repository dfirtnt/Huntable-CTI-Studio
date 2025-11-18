#!/usr/bin/env python3
"""
Create the complete Jupyter notebook for CommandLine observables testing.
"""

import json
from pathlib import Path

def create_notebook():
    """Create complete notebook with all cells."""
    
    cells = []
    
    # Cell 1: Title
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "# CommandLine Observables Testing\n",
            "\n",
            "Test different models (LLMs and embedding models) for counting CommandLine observables in CTI articles.\n",
            "\n",
            "**Scope**: Only CommandLinePatterns category\n",
            "\n",
            "**Model Types**:\n",
            "- LLM models: LMStudio, Anthropic, OpenAI\n",
            "- Embedding models: CTI-BERT (pattern-based extraction with semantic validation)"
        ]
    })
    
    # Cell 2: Setup
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": ["## 1. Setup and Imports"]
    })
    
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "import sys\n",
            "import os\n",
            "import json\n",
            "import asyncio\n",
            "import re\n",
            "from pathlib import Path\n",
            "from typing import Dict, List, Any, Optional\n",
            "from datetime import datetime\n",
            "import pandas as pd\n",
            "import httpx\n",
            "\n",
            "# Add project root to path\n",
            "project_root = Path().resolve().parent\n",
            "if str(project_root) not in sys.path:\n",
            "    sys.path.insert(0, str(project_root))\n",
            "\n",
            "from src.database.manager import DatabaseManager\n",
            "from src.database.models import ArticleTable\n",
            "from src.utils.content_filter import ContentFilter\n",
            "from src.services.llm_service import LLMService\n",
            "\n",
            "print(f\"Project root: {project_root}\")\n",
            "print(f\"Python path includes: {project_root in sys.path}\")"
        ]
    })
    
    # Cell 3: Configuration
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": ["## 2. Configuration"]
    })
    
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# LLM Model configurations\n",
            "LLM_MODELS = {\n",
            "    # LMStudio models\n",
            "    'deepseek-r1-qwen3-8b': {\n",
            "        'model_name': 'deepseek/deepseek-r1-0528-qwen3-8b',\n",
            "        'provider': 'lmstudio',\n",
            "        'description': 'DeepSeek R1 Qwen3 8B (reasoning)'\n",
            "    },\n",
            "    'mistral-7b': {\n",
            "        'model_name': 'mistralai/mistral-7b-instruct-v0.3',\n",
            "        'provider': 'lmstudio',\n",
            "        'description': 'Mistral 7B Instruct'\n",
            "    },\n",
            "    'qwen2-7b': {\n",
            "        'model_name': 'qwen2-7b-instruct',\n",
            "        'provider': 'lmstudio',\n",
            "        'description': 'Qwen2 7B Instruct'\n",
            "    },\n",
            "    'llama-3.1-8b': {\n",
            "        'model_name': 'meta-llama-3.1-8b-instruct',\n",
            "        'provider': 'lmstudio',\n",
            "        'description': 'Llama 3.1 8B Instruct'\n",
            "    },\n",
            "    'granite-4-h-tiny': {\n",
            "        'model_name': 'bm/granite-4-h-tiny',\n",
            "        'provider': 'lmstudio',\n",
            "        'description': 'Granite 4H Tiny'\n",
            "    },\n",
            "    \n",
            "    # Anthropic models\n",
            "    'claude-sonnet-4-5': {\n",
            "        'model_name': 'claude-sonnet-4-5',\n",
            "        'provider': 'anthropic',\n",
            "        'description': 'Claude Sonnet 4.5'\n",
            "    },\n",
            "    'claude-haiku-4-5': {\n",
            "        'model_name': 'claude-haiku-4-5',\n",
            "        'provider': 'anthropic',\n",
            "        'description': 'Claude Haiku 4.5'\n",
            "    },\n",
            "    \n",
            "    # OpenAI models\n",
            "    'gpt-4o-mini': {\n",
            "        'model_name': 'gpt-4o-mini',\n",
            "        'provider': 'openai',\n",
            "        'description': 'GPT-4o Mini'\n",
            "    },\n",
            "    'gpt-5-mini': {\n",
            "        'model_name': 'gpt-5-mini',\n",
            "        'provider': 'openai',\n",
            "        'description': 'GPT-5 Mini'\n",
            "    },\n",
            "    'gpt-5.1': {\n",
            "        'model_name': 'gpt-5.1',\n",
            "        'provider': 'openai',\n",
            "        'description': 'GPT-5.1'\n",
            "    }\n",
            "}\n",
            "\n",
            "# Embedding model configurations\n",
            "EMBEDDING_MODELS = {\n",
            "    'cti-bert': {\n",
            "        'model_name': 'ibm-research/CTI-BERT',\n",
            "        'description': 'CTI-BERT (pattern + embedding validation)'\n",
            "    }\n",
            "}\n",
            "\n",
            "# Test parameters\n",
            "TEMPERATURE = 0.0\n",
            "SEED = 42\n",
            "JUNK_FILTER_THRESHOLD = 0.8\n",
            "\n",
            "print(f\"Available LLM models: {len(LLM_MODELS)}\")\n",
            "print(f\"Available embedding models: {len(EMBEDDING_MODELS)}\")"
        ]
    })
    
    # Cell 4: Select Articles
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": ["## 3. Select Articles to Test"]
    })
    
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Option 1: Select by article IDs\n",
            "ARTICLE_IDS = [1937, 1909, 1866, 1860, 1794]  # Modify this list\n",
            "\n",
            "# Option 2: Select by URLs (uncomment and modify)\n",
            "# ARTICLE_URLS = [\n",
            "#     \"https://thedfirreport.com/2025/08/05/from-bing-search-to-ransomware-bumblebee-and-adaptixc2-deliver-akira/\",\n",
            "#     # Add more URLs here\n",
            "# ]\n",
            "\n",
            "# Load articles from database\n",
            "db_manager = DatabaseManager()\n",
            "db_session = db_manager.get_session()\n",
            "\n",
            "articles = []\n",
            "try:\n",
            "    if 'ARTICLE_IDS' in locals() and ARTICLE_IDS:\n",
            "        for article_id in ARTICLE_IDS:\n",
            "            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()\n",
            "            if article:\n",
            "                articles.append({\n",
            "                    'id': article.id,\n",
            "                    'title': article.title,\n",
            "                    'url': article.canonical_url,\n",
            "                    'content': article.content or \"\"\n",
            "                })\n",
            "    elif 'ARTICLE_URLS' in locals() and ARTICLE_URLS:\n",
            "        for url in ARTICLE_URLS:\n",
            "            article = db_session.query(ArticleTable).filter(ArticleTable.canonical_url == url).first()\n",
            "            if article:\n",
            "                articles.append({\n",
            "                    'id': article.id,\n",
            "                    'title': article.title,\n",
            "                    'url': article.canonical_url,\n",
            "                    'content': article.content or \"\"\n",
            "                })\n",
            "finally:\n",
            "    db_session.close()\n",
            "\n",
            "print(f\"Loaded {len(articles)} articles:\")\n",
            "for article in articles:\n",
            "    print(f\"  [{article['id']}] {article['title'][:60]}...\")"
        ]
    })
    
    # Cell 5: Select Models
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": ["## 4. Select Models to Test"]
    })
    
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Select which LLM models to test (modify this list)\n",
            "LLM_MODELS_TO_TEST = [\n",
            "    'gpt-4o-mini',\n",
            "    'claude-sonnet-4-5',\n",
            "    'deepseek-r1-qwen3-8b',\n",
            "    'mistral-7b',\n",
            "    # Add more model keys from LLM_MODELS dict above\n",
            "]\n",
            "\n",
            "# Select which embedding models to test (modify this list)\n",
            "EMBEDDING_MODELS_TO_TEST = [\n",
            "    'cti-bert',\n",
            "    # Add more embedding models if available\n",
            "]\n",
            "\n",
            "# Validate models\n",
            "invalid_llm = [m for m in LLM_MODELS_TO_TEST if m not in LLM_MODELS]\n",
            "invalid_embedding = [m for m in EMBEDDING_MODELS_TO_TEST if m not in EMBEDDING_MODELS]\n",
            "\n",
            "if invalid_llm:\n",
            "    print(f\"⚠️  Invalid LLM models: {invalid_llm}\")\n",
            "    print(f\"Available LLM models: {list(LLM_MODELS.keys())}\")\n",
            "if invalid_embedding:\n",
            "    print(f\"⚠️  Invalid embedding models: {invalid_embedding}\")\n",
            "    print(f\"Available embedding models: {list(EMBEDDING_MODELS.keys())}\")\n",
            "\n",
            "if not invalid_llm and not invalid_embedding:\n",
            "    print(f\"✅ Testing {len(LLM_MODELS_TO_TEST)} LLM models and {len(EMBEDDING_MODELS_TO_TEST)} embedding models:\")\n",
            "    for model_key in LLM_MODELS_TO_TEST:\n",
            "        config = LLM_MODELS[model_key]\n",
            "        print(f\"  LLM: {model_key} - {config['description']} ({config['provider']})\")\n",
            "    for model_key in EMBEDDING_MODELS_TO_TEST:\n",
            "        config = EMBEDDING_MODELS[model_key]\n",
            "        print(f\"  Embedding: {model_key} - {config['description']}\")"
        ]
    })
    
    # Continue with remaining cells - I'll add the key functions
    # For brevity, I'll reference the standalone script for the full function implementations
    
    # Add a cell that imports from the standalone script
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## 5. Load Functions\n",
            "\n",
            "The functions are available in `scripts/test_commandline_observables_standalone.py`.\n",
            "You can either:\n",
            "1. Import them from the script\n",
            "2. Copy the function code into cells below"
        ]
    })
    
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Option 1: Import from standalone script\n",
            "# Uncomment to use:\n",
            "# import sys\n",
            "# sys.path.insert(0, str(project_root / 'scripts'))\n",
            "# from test_commandline_observables_standalone import (\n",
            "#     count_commandline_with_llm,\n",
            "#     count_commandline_with_ctibert\n",
            "# )\n",
            "\n",
            "# Option 2: Copy functions from standalone script into cells below\n",
            "print(\"Functions should be defined in cells below or imported from standalone script\")"
        ]
    })
    
    # Add placeholder cells for the functions
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## 6. LLM-Based CommandLine Counting Function\n",
            "\n",
            "Copy the `count_commandline_with_llm` function from `scripts/test_commandline_observables_standalone.py` into this cell."
        ]
    })
    
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Paste count_commandline_with_llm function here\n",
            "# See scripts/test_commandline_observables_standalone.py for full implementation"
        ]
    })
    
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## 7. CTI-BERT Pattern-Based CommandLine Counting Function\n",
            "\n",
            "Copy the `count_commandline_with_ctibert` function from `scripts/test_commandline_observables_standalone.py` into this cell."
        ]
    })
    
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Paste count_commandline_with_ctibert function here\n",
            "# See scripts/test_commandline_observables_standalone.py for full implementation"
        ]
    })
    
    # Add run tests cell
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": ["## 8. Run Tests"]
    })
    
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Run tests for all article-model combinations\n",
            "results = []\n",
            "\n",
            "# Test LLM models\n",
            "for article in articles:\n",
            "    for model_key in LLM_MODELS_TO_TEST:\n",
            "        print(f\"Testing Article {article['id']} with LLM {model_key}...\", end=\" \")\n",
            "        \n",
            "        result = await count_commandline_with_llm(\n",
            "            article_content=article['content'],\n",
            "            model_key=model_key,\n",
            "            temperature=TEMPERATURE,\n",
            "            seed=SEED,\n",
            "            junk_filter_threshold=JUNK_FILTER_THRESHOLD,\n",
            "            article_id=article['id']\n",
            "        )\n",
            "        \n",
            "        results.append({\n",
            "            'article_id': article['id'],\n",
            "            'article_title': article['title'],\n",
            "            'article_url': article['url'],\n",
            "            'model_key': model_key,\n",
            "            'model_description': LLM_MODELS[model_key]['description'],\n",
            "            'model_type': 'llm',\n",
            "            'provider': LLM_MODELS[model_key]['provider'],\n",
            "            'commandline_count': result.get('count'),\n",
            "            'parse_success': result.get('parse_success', False),\n",
            "            'error': result.get('error'),\n",
            "            'raw_response': result.get('raw_response', '')[:200],\n",
            "            'usage': result.get('usage', {})\n",
            "        })\n",
            "        \n",
            "        status = \"✅\" if result.get('parse_success') else \"❌\"\n",
            "        count = result.get('count', 'N/A')\n",
            "        print(f\"{status} Count: {count}\")\n",
            "\n",
            "# Test embedding models\n",
            "for article in articles:\n",
            "    for model_key in EMBEDDING_MODELS_TO_TEST:\n",
            "        print(f\"Testing Article {article['id']} with Embedding {model_key}...\", end=\" \")\n",
            "        \n",
            "        result = count_commandline_with_ctibert(\n",
            "            article_content=article['content'],\n",
            "            model_key=model_key,\n",
            "            junk_filter_threshold=JUNK_FILTER_THRESHOLD,\n",
            "            article_id=article['id'],\n",
            "            use_embedding_validation=True\n",
            "        )\n",
            "        \n",
            "        results.append({\n",
            "            'article_id': article['id'],\n",
            "            'article_title': article['title'],\n",
            "            'article_url': article['url'],\n",
            "            'model_key': model_key,\n",
            "            'model_description': EMBEDDING_MODELS[model_key]['description'],\n",
            "            'model_type': 'embedding',\n",
            "            'provider': 'cti-bert',\n",
            "            'commandline_count': result.get('count'),\n",
            "            'validated_count': result.get('validated_count'),\n",
            "            'confidence': result.get('confidence'),\n",
            "            'parse_success': result.get('parse_success', False),\n",
            "            'error': result.get('error'),\n",
            "            'raw_matches': result.get('raw_matches', []),\n",
            "            'usage': {}\n",
            "        })\n",
            "        \n",
            "        status = \"✅\" if result.get('parse_success') else \"❌\"\n",
            "        count = result.get('count', 'N/A')\n",
            "        confidence = result.get('confidence', 'N/A')\n",
            "        print(f\"{status} Count: {count} (confidence: {confidence})\")\n",
            "\n",
            "print(f\"\\n✅ Completed {len(results)} tests\")"
        ]
    })
    
    # Add display results cells
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": ["## 9. Display Results"]
    })
    
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Create DataFrame for easy viewing\n",
            "df = pd.DataFrame(results)\n",
            "\n",
            "# Separate LLM and embedding results\n",
            "llm_df = df[df['model_type'] == 'llm'].copy()\n",
            "embedding_df = df[df['model_type'] == 'embedding'].copy()\n",
            "\n",
            "# Pivot table for LLM models\n",
            "if len(llm_df) > 0:\n",
            "    llm_pivot = llm_df.pivot_table(\n",
            "        index=['article_id', 'article_title'],\n",
            "        columns='model_description',\n",
            "        values='commandline_count',\n",
            "        aggfunc='first'\n",
            "    )\n",
            "    \n",
            "    print(\"\\n\" + \"=\"*80)\n",
            "    print(\"LLM MODELS - COMMANDLINE COUNTS BY ARTICLE\")\n",
            "    print(\"=\"*80)\n",
            "    display(llm_pivot)\n",
            "\n",
            "# Pivot table for embedding models\n",
            "if len(embedding_df) > 0:\n",
            "    embedding_pivot = embedding_df.pivot_table(\n",
            "        index=['article_id', 'article_title'],\n",
            "        columns='model_description',\n",
            "        values='commandline_count',\n",
            "        aggfunc='first'\n",
            "    )\n",
            "    \n",
            "    print(\"\\n\" + \"=\"*80)\n",
            "    print(\"EMBEDDING MODELS - COMMANDLINE COUNTS BY ARTICLE\")\n",
            "    print(\"=\"*80)\n",
            "    display(embedding_pivot)\n",
            "\n",
            "# Combined comparison\n",
            "if len(llm_df) > 0 and len(embedding_df) > 0:\n",
            "    combined_pivot = df.pivot_table(\n",
            "        index=['article_id', 'article_title'],\n",
            "        columns='model_description',\n",
            "        values='commandline_count',\n",
            "        aggfunc='first'\n",
            "    )\n",
            "    \n",
            "    print(\"\\n\" + \"=\"*80)\n",
            "    print(\"COMBINED COMPARISON - ALL MODELS\")\n",
            "    print(\"=\"*80)\n",
            "    display(combined_pivot)"
        ]
    })
    
    # Add export cell
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": ["## 10. Export Results"]
    })
    
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Export results to JSON\n",
            "output_dir = project_root / \"outputs\" / \"notebook_results\"\n",
            "output_dir.mkdir(parents=True, exist_ok=True)\n",
            "\n",
            "timestamp = datetime.now().strftime(\"%Y%m%d_%H%M%S\")\n",
            "output_file = output_dir / f\"commandline_observables_{timestamp}.json\"\n",
            "\n",
            "export_data = {\n",
            "    'timestamp': timestamp,\n",
            "    'test_config': {\n",
            "        'temperature': TEMPERATURE,\n",
            "        'seed': SEED,\n",
            "        'junk_filter_threshold': JUNK_FILTER_THRESHOLD,\n",
            "        'llm_models_tested': LLM_MODELS_TO_TEST,\n",
            "        'embedding_models_tested': EMBEDDING_MODELS_TO_TEST,\n",
            "        'article_ids': [a['id'] for a in articles]\n",
            "    },\n",
            "    'results': results\n",
            "}\n",
            "\n",
            "with open(output_file, 'w') as f:\n",
            "    json.dump(export_data, f, indent=2)\n",
            "\n",
            "print(f\"✅ Results exported to: {output_file}\")\n",
            "\n",
            "# Also export as CSV\n",
            "csv_file = output_dir / f\"commandline_observables_{timestamp}.csv\"\n",
            "df.to_csv(csv_file, index=False)\n",
            "print(f\"✅ CSV exported to: {csv_file}\")"
        ]
    })
    
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "name": "python",
                "version": "3.9.0"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    return notebook

if __name__ == "__main__":
    notebook = create_notebook()
    
    output_path = Path("notebooks/test_commandline_observables.ipynb")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(notebook, f, indent=1)
    
    print(f"✅ Notebook created at: {output_path}")
    print(f"   Total cells: {len(notebook['cells'])}")
    print("\nNote: The function cells (6 and 7) need to be populated with code from")
    print("      scripts/test_commandline_observables_standalone.py")

