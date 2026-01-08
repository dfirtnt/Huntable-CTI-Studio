#!/usr/bin/env python3
"""
Generate JSON with filtered content and raw LLM responses for cmdextract eval articles.

Output JSON format:
[
    {
        "filtered_content": "...",
        "raw_llm_response": "..."
    },
    ...
]

Usage:
    python3 scripts/generate_cmdextract_eval_csv.py --output outputs/cmdextract_eval_data.json
"""

import os
import sys
import json
import yaml
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urlunparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable, AgenticWorkflowExecutionTable, AgenticWorkflowConfigTable
from src.services.llm_service import LLMService
from src.utils.content_filter import ContentFilter
from sqlalchemy import desc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """Normalize URL for matching."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))


def load_eval_articles() -> List[Dict[str, Any]]:
    """Load cmdline eval articles from config."""
    config_path = project_root / "config" / "eval_articles.yaml"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    subagents = config.get("subagents", {})
    cmdline_articles = subagents.get("cmdline", [])
    
    if not cmdline_articles:
        raise ValueError("No cmdline eval articles found in config")
    
    logger.info(f"Loaded {len(cmdline_articles)} cmdline eval articles from config")
    return cmdline_articles


def find_article_by_url(db_session, url: str) -> Optional[ArticleTable]:
    """Find article in database by URL."""
    # Try exact match first
    article = db_session.query(ArticleTable).filter(
        ArticleTable.canonical_url == url
    ).first()
    
    if article:
        return article
    
    # Try normalized match
    normalized = normalize_url(url)
    article = db_session.query(ArticleTable).filter(
        ArticleTable.canonical_url.like(f"{normalized}%")
    ).first()
    
    return article


def get_filtered_content(article: ArticleTable, junk_filter_threshold: float = 0.8) -> str:
    """Apply junk filter to article content."""
    content_filter = ContentFilter()
    hunt_score = article.article_metadata.get('threat_hunting_score', 0) if article.article_metadata else 0
    
    filter_result = content_filter.filter_content(
        article.content,
        min_confidence=junk_filter_threshold,
        hunt_score=hunt_score,
        article_id=article.id
    )
    
    return filter_result.filtered_content or article.content


def get_existing_raw_response(article: ArticleTable, db_session) -> Optional[str]:
    """Get raw LLM response from latest workflow execution if available."""
    try:
        # Find latest completed workflow execution for this article
        execution = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.article_id == article.id,
            AgenticWorkflowExecutionTable.status == 'completed'
        ).order_by(
            desc(AgenticWorkflowExecutionTable.completed_at)
        ).first()
        
        if not execution or not execution.extraction_result:
            return None
        
        extraction_result = execution.extraction_result
        
        # Try to get raw_response from cmdline subresults first (most specific)
        subresults = extraction_result.get("subresults", {})
        cmdline_result = subresults.get("cmdline", {})
        if cmdline_result:
            raw_data = cmdline_result.get("raw", {})
            if isinstance(raw_data, dict):
                raw_response = raw_data.get("raw_response")
                if raw_response:
                    logger.info(f"Found raw_response in cmdline subresults for article {article.id}")
                    return raw_response
        
        # Fallback: try top-level raw_response
        raw_response = extraction_result.get("raw_response")
        if raw_response:
            logger.info(f"Found raw_response in top-level extraction_result for article {article.id}")
            return raw_response
        
        return None
        
    except Exception as e:
        logger.warning(f"Error getting existing raw response for article {article.id}: {e}")
        return None


async def get_raw_llm_response(
    article: ArticleTable,
    filtered_content: str,
    db_session,
    llm_service: LLMService,
    use_existing: bool = True
) -> str:
    """Get raw LLM response from existing execution or run fresh extraction."""
    # Try to get existing result first
    if use_existing:
        existing_response = get_existing_raw_response(article, db_session)
        if existing_response:
            logger.info(f"Using existing raw_response for article {article.id}")
            return existing_response
        logger.info(f"No existing raw_response found for article {article.id}, running fresh extraction")
    
    # Run fresh extraction
    try:
        # Get CmdlineExtract prompt config from database
        try:
            # Try to get active workflow config directly from database
            active_config = db_session.query(AgenticWorkflowConfigTable).filter(
                AgenticWorkflowConfigTable.is_active == True
            ).order_by(
                desc(AgenticWorkflowConfigTable.version)
            ).first()
            
            if not active_config or not active_config.agent_prompts:
                # Fallback: create a minimal config with default CmdlineExtract prompt
                logger.warning("No active workflow config found, using default CmdlineExtract prompt")
                prompt_config = {
                    "prompt": "Extract Windows command-line observables from the article.",
                    "instructions": "Output valid JSON with cmdline_items array and count field.",
                    "model": llm_service.model_extract or "qwen/qwen2.5-coder-14b"
                }
            else:
                # Get CmdlineExtract prompt from config
                # Try multiple possible keys (CmdlineExtract, ExtractAgent, ExtractAgentSettings)
                agent_prompts = active_config.agent_prompts or {}
                cmdline_prompt_config = (
                    agent_prompts.get("CmdlineExtract") or
                    agent_prompts.get("ExtractAgent") or
                    agent_prompts.get("ExtractAgentSettings")
                )
                
                if not cmdline_prompt_config:
                    raise ValueError(
                        "CmdlineExtract/ExtractAgent prompt not found in workflow config. "
                        f"Available agents: {list(agent_prompts.keys())}"
                    )
                
                prompt_config = {
                    "prompt": cmdline_prompt_config.get("prompt", ""),
                    "instructions": cmdline_prompt_config.get("instructions", ""),
                    "model": cmdline_prompt_config.get("model", llm_service.model_extract)
                }
        except Exception as e:
            logger.warning(f"Could not get prompt config from workflow: {e}, using defaults")
            prompt_config = {
                "prompt": "Extract Windows command-line observables from the article.",
                "instructions": "Output valid JSON with cmdline_items array and count field.",
                "model": llm_service.model_extract or "qwen/qwen2.5-coder-14b"
            }
        
        # Run extraction
        extraction_result = await llm_service.run_extraction_agent(
            agent_name="CmdlineExtract",
            content=filtered_content,
            title=article.title,
            url=article.canonical_url,
            prompt_config=prompt_config,
            qa_prompt_config=None,  # Skip QA for simplicity
            max_retries=1,  # Single attempt
            execution_id=None,
            model_name=prompt_config.get("model"),
            temperature=0.0,
            use_hybrid_extractor=False,  # Force LLM usage to get raw response
        )
        
        # Extract raw response
        raw_response = extraction_result.get("raw_response", "")
        
        if not raw_response:
            # Fallback: try to reconstruct from result
            raw_response = str(extraction_result)
            logger.warning(f"No raw_response in extraction result for article {article.id}, using string representation")
        
        return raw_response
        
    except Exception as e:
        logger.error(f"Error getting raw LLM response for article {article.id}: {e}", exc_info=True)
        return f"ERROR: {str(e)}"


async def process_article(
    article_def: Dict[str, Any],
    db_session,
    llm_service: LLMService,
    junk_filter_threshold: float = 0.8,
    use_existing_results: bool = True
) -> Optional[Dict[str, str]]:
    """Process a single eval article."""
    url = article_def.get("url")
    if not url:
        logger.warning("Article definition missing URL, skipping")
        return None
    
    logger.info(f"Processing article: {url[:60]}...")
    
    # Find article in database
    article = find_article_by_url(db_session, url)
    if not article:
        logger.warning(f"Article not found in database: {url}")
        return {
            "filtered_content": f"ARTICLE NOT FOUND: {url}",
            "raw_llm_response": "N/A"
        }
    
    # Get filtered content
    try:
        filtered_content = get_filtered_content(article, junk_filter_threshold)
    except Exception as e:
        logger.error(f"Error filtering content for article {article.id}: {e}")
        filtered_content = f"ERROR FILTERING: {str(e)}"
    
    # Get raw LLM response
    try:
        raw_response = await get_raw_llm_response(
            article, 
            filtered_content, 
            db_session, 
            llm_service,
            use_existing=use_existing_results
        )
    except Exception as e:
        logger.error(f"Error getting raw LLM response for article {article.id}: {e}")
        raw_response = f"ERROR: {str(e)}"
    
    return {
        "filtered_content": filtered_content,
        "raw_llm_response": raw_response
    }


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Generate CSV with filtered content and raw LLM responses for cmdextract eval articles"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="outputs/cmdextract_eval_data.json",
        help="Output JSON file path (default: outputs/cmdextract_eval_data.json)"
    )
    parser.add_argument(
        "--junk-filter-threshold",
        type=float,
        default=0.8,
        help="Junk filter threshold (default: 0.8)"
    )
    parser.add_argument(
        "--use-existing",
        action="store_true",
        default=True,
        help="Use existing eval run results if available (default: True)"
    )
    parser.add_argument(
        "--force-fresh",
        action="store_true",
        help="Force fresh extraction even if existing results are available"
    )
    
    args = parser.parse_args()
    
    # Load eval articles
    eval_articles = load_eval_articles()
    
    # Initialize services
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    llm_service = LLMService()
    
    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Determine if we should use existing results
    use_existing = args.use_existing and not args.force_fresh
    
    if use_existing:
        logger.info("Will use existing eval run results when available")
    else:
        logger.info("Will run fresh extractions for all articles")
    
    # Process all articles
    results = []
    success_count = 0
    error_count = 0
    existing_count = 0
    
    for i, article_def in enumerate(eval_articles, 1):
        url = article_def.get("url", "unknown")
        logger.info(f"Processing article {i}/{len(eval_articles)}: {url[:60]}...")
        
        try:
            result = await process_article(
                article_def,
                db_session,
                llm_service,
                args.junk_filter_threshold,
                use_existing_results=use_existing
            )
            if result:
                results.append(result)
                # Check if it was successful (not an error message)
                if not result["raw_llm_response"].startswith("ERROR"):
                    success_count += 1
                    # Check if we used existing result (indicated by log message or response length)
                    # For now, we'll track this separately - existing results are typically longer
                    # This is a heuristic; we could add a flag to track this more precisely
                else:
                    error_count += 1
            else:
                error_count += 1
        except Exception as e:
            logger.error(f"Error processing article {url}: {e}", exc_info=True)
            results.append({
                "filtered_content": f"ERROR PROCESSING: {url}",
                "raw_llm_response": f"ERROR: {str(e)}"
            })
            error_count += 1
    
    # Write JSON output
    logger.info(f"Writing {len(results)} results to {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        # Write as JSON array with proper indentation for readability
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Print summary
    logger.info("=" * 60)
    logger.info(f"✅ JSON generated: {output_path}")
    logger.info(f"   Total items: {len(results)}")
    logger.info(f"   Successful: {success_count}")
    logger.info(f"   Errors: {error_count}")
    if use_existing:
        logger.info(f"   (Used existing results when available)")
    logger.info("=" * 60)
    
    db_session.close()


if __name__ == "__main__":
    asyncio.run(main())
