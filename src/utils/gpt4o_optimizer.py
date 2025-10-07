"""
Integration module for content filtering with GPT-4o ranking.

This module integrates the content filter with the existing GPT-4o ranking
system to reduce costs by filtering out non-huntable content.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from src.utils.content_filter import ContentFilter, FilterResult

logger = logging.getLogger(__name__)

class GPT4oContentOptimizer:
    """
    Optimizes GPT-4o usage by filtering content before sending to the API.
    
    This class integrates with the existing GPT-4o ranking system to:
    1. Filter out non-huntable content chunks
    2. Provide cost estimates based on filtered content
    3. Maintain analysis quality while reducing costs
    """
    
    def __init__(self, model_path: Optional[str] = None):
        self.content_filter = ContentFilter(model_path)
        self.filter_stats = {
            'total_requests': 0,
            'total_cost_savings': 0.0,
            'total_tokens_saved': 0,
            'avg_cost_reduction': 0.0
        }
    
    async def optimize_content_for_gpt4o(self, content: str, 
                                       min_confidence: float = 0.7,
                                       chunk_size: int = 1000) -> Dict[str, Any]:
        """
        Optimize content for GPT-4o analysis by filtering non-huntable chunks.
        
        Args:
            content: Full article content
            min_confidence: Minimum confidence threshold for keeping chunks
            chunk_size: Size of chunks to analyze
            
        Returns:
            Dictionary with optimized content and metadata
        """
        try:
            # Load model if not already loaded
            if not self.content_filter.model:
                self.content_filter.load_model()
            
            # Filter content
            filter_result = self.content_filter.filter_content(
                content, min_confidence, chunk_size
            )
            
            # Calculate cost estimates
            original_tokens = len(content) // 4  # Rough estimate
            filtered_tokens = len(filter_result.filtered_content) // 4
            tokens_saved = original_tokens - filtered_tokens
            
            # GPT-4o pricing: $5.00 per 1M input tokens
            cost_savings = (tokens_saved / 1000000) * 5.00
            
            # Update stats
            self.filter_stats['total_requests'] += 1
            self.filter_stats['total_cost_savings'] += cost_savings
            self.filter_stats['total_tokens_saved'] += tokens_saved
            self.filter_stats['avg_cost_reduction'] = (
                self.filter_stats['total_cost_savings'] / self.filter_stats['total_requests']
            )
            
            logger.info(f"Content optimization completed. "
                       f"Tokens saved: {tokens_saved:,}, "
                       f"Cost savings: ${cost_savings:.4f}")
            
            return {
                'success': True,
                'original_content': content,
                'filtered_content': filter_result.filtered_content,
                'original_tokens': original_tokens,
                'filtered_tokens': filtered_tokens,
                'tokens_saved': tokens_saved,
                'cost_savings': cost_savings,
                'cost_reduction_percent': filter_result.cost_savings * 100,
                'is_huntable': filter_result.is_huntable,
                'confidence': filter_result.confidence,
                'removed_chunks': filter_result.removed_chunks,
                'chunks_removed': len(filter_result.removed_chunks),
                'chunks_kept': len(filter_result.filtered_content.split()) // (chunk_size // 10),  # Rough estimate
                'optimization_stats': self.filter_stats.copy()
            }
            
        except Exception as e:
            logger.error(f"Content optimization failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'original_content': content,
                'filtered_content': content,  # Fallback to original
                'original_tokens': len(content) // 4,
                'filtered_tokens': len(content) // 4,
                'tokens_saved': 0,
                'cost_savings': 0.0,
                'cost_reduction_percent': 0.0,
                'is_huntable': True,  # Assume huntable if filtering fails
                'confidence': 0.5,
                'removed_chunks': [],
                'chunks_removed': 0,
                'chunks_kept': 1,
                'optimization_stats': self.filter_stats.copy()
            }
    
    def get_cost_estimate(self, content: str, use_filtering: bool = True) -> Dict[str, Any]:
        """
        Get cost estimate for GPT-4o analysis with optional filtering.
        
        Args:
            content: Article content
            use_filtering: Whether to apply content filtering
            
        Returns:
            Cost estimation details
        """
        try:
            if use_filtering:
                # Get optimized content
                optimization_result = asyncio.run(
                    self.optimize_content_for_gpt4o(content)
                )
                
                if optimization_result['success']:
                    input_tokens = optimization_result['filtered_tokens']
                    cost_savings = optimization_result['cost_savings']
                else:
                    # Fallback to original content
                    input_tokens = len(content) // 4
                    cost_savings = 0.0
            else:
                input_tokens = len(content) // 4
                cost_savings = 0.0
            
            # GPT-4o pricing
            prompt_tokens = 1508  # From existing implementation
            total_input_tokens = input_tokens + prompt_tokens
            max_output_tokens = 2000
            
            input_cost = (total_input_tokens / 1000000) * 5.00
            output_cost = (max_output_tokens / 1000000) * 15.00
            total_cost = input_cost + output_cost
            
            return {
                'input_tokens': total_input_tokens,
                'output_tokens': max_output_tokens,
                'input_cost': input_cost,
                'output_cost': output_cost,
                'total_cost': total_cost,
                'cost_savings': cost_savings,
                'filtering_enabled': use_filtering,
                'estimated_content_tokens': input_tokens,
                'prompt_tokens': prompt_tokens
            }
            
        except Exception as e:
            logger.error(f"Cost estimation failed: {e}")
            # Fallback calculation
            input_tokens = len(content) // 4
            prompt_tokens = 1508
            total_input_tokens = input_tokens + prompt_tokens
            max_output_tokens = 2000
            
            input_cost = (total_input_tokens / 1000000) * 5.00
            output_cost = (max_output_tokens / 1000000) * 15.00
            total_cost = input_cost + output_cost
            
            return {
                'input_tokens': total_input_tokens,
                'output_tokens': max_output_tokens,
                'input_cost': input_cost,
                'output_cost': output_cost,
                'total_cost': total_cost,
                'cost_savings': 0.0,
                'filtering_enabled': False,
                'estimated_content_tokens': input_tokens,
                'prompt_tokens': prompt_tokens,
                'error': str(e)
            }
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get current optimization statistics."""
        return {
            'total_requests': self.filter_stats['total_requests'],
            'total_cost_savings': self.filter_stats['total_cost_savings'],
            'total_tokens_saved': self.filter_stats['total_tokens_saved'],
            'avg_cost_reduction': self.filter_stats['avg_cost_reduction'],
            'avg_tokens_saved_per_request': (
                self.filter_stats['total_tokens_saved'] / max(self.filter_stats['total_requests'], 1)
            ),
            'total_cost_savings_percent': (
                self.filter_stats['total_cost_savings'] / max(self.filter_stats['total_cost_savings'] + 0.01, 1) * 100
            )
        }

# Global optimizer instance
gpt4o_optimizer = GPT4oContentOptimizer()

# Convenience functions for integration
async def optimize_article_content(content: str, min_confidence: float = 0.7, 
                                 article_metadata: Optional[Dict[str, Any]] = None,
                                 content_hash: Optional[str] = None) -> Dict[str, Any]:
    """
    Optimize article content for GPT-4o analysis with smart chunk caching.
    
    Args:
        content: Full article content
        min_confidence: Minimum confidence threshold for keeping chunks
        article_metadata: Article metadata dict (for cache storage/retrieval)
        content_hash: Content hash for cache validation
        
    Returns:
        Dictionary with optimized content and metadata
    """
    # Check for cached chunks first
    if article_metadata and content_hash:
        cached_result = _get_cached_chunks(article_metadata, content_hash, min_confidence)
        if cached_result:
            logger.info(f"Using cached chunks for content optimization (cache hit)")
            return cached_result
    
    # Generate chunks if not cached
    result = await gpt4o_optimizer.optimize_content_for_gpt4o(content, min_confidence)
    
    # Store in cache if we have article metadata
    if article_metadata and content_hash and result['success']:
        _store_cached_chunks(article_metadata, content_hash, min_confidence, result)
        logger.info(f"Cached chunks for future use (cache miss)")
    
    return result

def _get_cached_chunks(article_metadata: Dict[str, Any], content_hash: str, 
                      min_confidence: float) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached chunks from article metadata if valid.
    
    Args:
        article_metadata: Article metadata dictionary
        content_hash: Current content hash for validation
        min_confidence: Confidence threshold for validation
        
    Returns:
        Cached optimization result or None if cache miss/invalid
    """
    try:
        cached_chunks = article_metadata.get('content_chunks')
        if not cached_chunks:
            return None
        
        # Validate cache
        if not _is_cache_valid(cached_chunks, content_hash, min_confidence):
            return None
        
        # Return cached result
        return {
            'success': True,
            'original_content': cached_chunks.get('original_content', ''),
            'filtered_content': cached_chunks.get('filtered_content', ''),
            'original_tokens': cached_chunks.get('original_tokens', 0),
            'filtered_tokens': cached_chunks.get('filtered_tokens', 0),
            'tokens_saved': cached_chunks.get('tokens_saved', 0),
            'cost_savings': cached_chunks.get('cost_savings', 0.0),
            'cost_reduction_percent': cached_chunks.get('cost_reduction_percent', 0.0),
            'is_huntable': cached_chunks.get('is_huntable', True),
            'confidence': cached_chunks.get('confidence', 0.5),
            'removed_chunks': cached_chunks.get('removed_chunks', []),
            'chunks_removed': cached_chunks.get('chunks_removed', 0),
            'chunks_kept': cached_chunks.get('chunks_kept', 1),
            'cached': True,
            'cache_hit': True
        }
        
    except Exception as e:
        logger.warning(f"Error retrieving cached chunks: {e}")
        return None

def _store_cached_chunks(article_metadata: Dict[str, Any], content_hash: str,
                        min_confidence: float, result: Dict[str, Any]) -> None:
    """
    Store optimization result in article metadata cache.
    
    Args:
        article_metadata: Article metadata dictionary (will be modified)
        content_hash: Content hash for validation
        min_confidence: Confidence threshold used
        result: Optimization result to cache
    """
    try:
        # Store cache entry
        article_metadata['content_chunks'] = {
            'content_hash': content_hash,
            'chunked_at': datetime.now().isoformat(),
            'min_confidence': min_confidence,
            'original_content': result.get('original_content', ''),
            'filtered_content': result.get('filtered_content', ''),
            'original_tokens': result.get('original_tokens', 0),
            'filtered_tokens': result.get('filtered_tokens', 0),
            'tokens_saved': result.get('tokens_saved', 0),
            'cost_savings': result.get('cost_savings', 0.0),
            'cost_reduction_percent': result.get('cost_reduction_percent', 0.0),
            'is_huntable': result.get('is_huntable', True),
            'confidence': result.get('confidence', 0.5),
            'removed_chunks': result.get('removed_chunks', []),
            'chunks_removed': result.get('chunks_removed', 0),
            'chunks_kept': result.get('chunks_kept', 1)
        }
        
        logger.debug(f"Cached chunks for content hash {content_hash[:8]}...")
        
    except Exception as e:
        logger.warning(f"Error storing cached chunks: {e}")

def _is_cache_valid(cached_chunks: Dict[str, Any], content_hash: str, 
                   min_confidence: float) -> bool:
    """
    Validate cached chunks for reuse.
    
    Args:
        cached_chunks: Cached chunks data
        content_hash: Current content hash
        min_confidence: Current confidence threshold
        
    Returns:
        True if cache is valid for reuse
    """
    try:
        # Check content hash
        if cached_chunks.get('content_hash') != content_hash:
            return False
        
        # Check confidence threshold (if different, need to re-filter)
        if cached_chunks.get('min_confidence') != min_confidence:
            return False
        
        # Check age (optional TTL - 7 days)
        chunked_at = cached_chunks.get('chunked_at')
        if chunked_at:
            try:
                cache_time = datetime.fromisoformat(chunked_at.replace('Z', '+00:00'))
                age = datetime.now() - cache_time.replace(tzinfo=None)
                if age > timedelta(days=7):
                    return False
            except (ValueError, TypeError):
                # If we can't parse the date, invalidate cache
                return False
        
        return True
        
    except Exception as e:
        logger.warning(f"Error validating cache: {e}")
        return False

def estimate_gpt4o_cost(content: str, use_filtering: bool = True) -> Dict[str, Any]:
    """Estimate GPT-4o cost with optional content filtering."""
    return gpt4o_optimizer.get_cost_estimate(content, use_filtering)

def get_optimization_stats() -> Dict[str, Any]:
    """Get current optimization statistics."""
    return gpt4o_optimizer.get_optimization_stats()
