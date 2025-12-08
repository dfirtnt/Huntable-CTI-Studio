"""
DEPRECATED: This module has been moved to archived/src/utils/gpt4o_optimizer.py.

This file is kept for backward compatibility only.
All new code should use src.utils.llm_optimizer instead.
"""

# Re-export everything from llm_optimizer for backward compatibility
from src.utils.llm_optimizer import (
    LLMOptimizer,
    optimize_article_content,
    estimate_llm_cost,
    estimate_gpt4o_cost,
    get_optimization_stats,
    llm_optimizer
)

# Backward compatibility aliases
GPT4oContentOptimizer = LLMOptimizer
gpt4o_optimizer = llm_optimizer

# Legacy method name for backward compatibility
from typing import Optional, Dict, Any

async def optimize_content_for_gpt4o(content: str, 
                                       min_confidence: float = 0.7,
                                       chunk_size: int = 1000,
                                       article_id: Optional[int] = None,
                                       store_analysis: bool = False) -> Dict[str, Any]:
    """Legacy method name - use LLMOptimizer.optimize_content instead."""
    return await llm_optimizer.optimize_content(
        content, min_confidence, chunk_size, article_id, store_analysis
    )

