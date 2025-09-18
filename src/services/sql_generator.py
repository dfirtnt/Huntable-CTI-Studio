"""
SQL Generation Service using Local LLM for natural language to SQL conversion.
"""

import os
import json
import httpx
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SQLGenerator:
    """Generate SQL queries from natural language using Phi-3 Mini (optimized for speed)."""
    
    def __init__(self):
        self.ollama_url = os.getenv('LLM_API_URL', 'http://ollama:11434')
        self.model = os.getenv('LLM_MODEL', 'phi3:mini')  # Switched to faster, smaller model
        self.schema_context = self._build_schema_context()
    
    def _build_schema_context(self) -> str:
        """Build comprehensive database schema context for the LLM."""
        return """
Database Schema for CTI Scraper:

ARTICLES table:
- id (integer, primary key)
- source_id (integer, foreign key to sources.id)
- canonical_url (text)
- title (text)
- published_at (timestamp)
- modified_at (timestamp)
- authors (json)
- tags (json)
- content (text)
- content_hash (varchar(64))
- article_metadata (json) - contains threat_hunting_score, highlighted_text, etc.
- discovered_at (timestamp)
- processing_status (varchar(50))
- word_count (integer)
- created_at (timestamp)
- updated_at (timestamp)
- simhash (numeric(20,0))
- simhash_bucket (integer)
- summary (text)

SOURCES table:
- id (integer, primary key)
- identifier (varchar(255), unique)
- name (varchar(500))
- url (text)
- rss_url (text)
- tier (integer) - 1=premium, 2=standard, 3=basic
- weight (double precision)
- check_frequency (integer)
- active (boolean)
- config (json)
- last_check (timestamp)
- last_success (timestamp)
- consecutive_failures (integer)
- total_articles (integer)
- success_rate (double precision)
- average_response_time (double precision)
- created_at (timestamp)
- updated_at (timestamp)
- user_polling_frequency (integer)
- user_lookback_days (integer)
- last_manual_poll (timestamp)
- manual_poll_enabled (boolean)
- lookback_days (integer)

ARTICLE_ANNOTATIONS table:
- id (integer, primary key)
- article_id (integer, foreign key to articles.id)
- annotation_type (varchar(50))
- annotation_data (json)
- created_at (timestamp)
- updated_at (timestamp)

TEXT_HIGHLIGHTS table:
- id (integer, primary key)
- article_id (integer, foreign key to articles.id)
- highlight_type (varchar(50))
- highlight_data (json)
- created_at (timestamp)

Common query patterns:
- Join articles with sources: JOIN sources s ON a.source_id = s.id
- Filter by date: WHERE published_at >= NOW() - INTERVAL '30 days'
- Access JSON metadata: article_metadata->>'threat_hunting_score'
- Search content: WHERE content ILIKE '%keyword%'
- Count articles: COUNT(a.id) as article_count
- Group by source: GROUP BY s.id, s.name
- Order by score: ORDER BY (article_metadata->>'threat_hunting_score')::float DESC
"""
    
    async def generate_sql(self, natural_language_query: str) -> Dict[str, Any]:
        """
        Generate SQL query from natural language using Mistral 7B.
        
        Args:
            natural_language_query: User's question in natural language
            
        Returns:
            Dict containing SQL query, explanation, and metadata
        """
        # Try simple pattern matching first
        simple_sql = self._try_simple_patterns(natural_language_query)
        if simple_sql:
            return {
                "success": True,
                "sql": simple_sql,
                "raw_response": simple_sql,
                "model_used": "pattern_matching",
                "timestamp": datetime.now().isoformat()
            }
        
        # Fall back to LLM generation
        prompt = self._build_sql_prompt(natural_language_query)
        
        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"Generating SQL with Ollama at {self.ollama_url} using model {self.model}")
                
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.0,  # Deterministic SQL generation
                            "num_predict": 100,  # Reduced from 200 for faster generation
                            "stop": ["```", "---", "Explanation:", "To get", "Here is", "You can", "The query", "This query"]
                        }
                    },
                    timeout=30.0  # Reduced timeout for faster failure
                )
                
                logger.info(f"Ollama response status: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    generated_text = result.get("response", "").strip()
                    logger.info(f"Generated text length: {len(generated_text)}")
                    
                    # Extract SQL from the response
                    sql_query = self._extract_sql_from_response(generated_text)
                    
                    # If no SQL extracted, fall back to simple pattern matching
                    if sql_query is None:
                        simple_sql = self._try_simple_patterns(natural_language_query)
                        if simple_sql:
                            return {
                                "success": True,
                                "sql": simple_sql,
                                "raw_response": f"Fallback pattern matching: {simple_sql}",
                                "model_used": "pattern_matching_fallback",
                                "timestamp": datetime.now().isoformat()
                            }
                        else:
                            return {
                                "success": False,
                                "error": "Could not generate valid SQL from query. Please try rephrasing your question.",
                                "sql": None,
                                "raw_response": generated_text
                            }
                    
                    return {
                        "success": True,
                        "sql": sql_query,
                        "raw_response": generated_text,
                        "model_used": self.model,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    error_text = response.text
                    logger.error(f"Ollama API error: {response.status_code} - {error_text}")
                    return {
                        "success": False,
                        "error": f"API error: {response.status_code} - {error_text}",
                        "sql": None
                    }
                    
        except Exception as e:
            logger.error(f"SQL generation error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "sql": None
            }
    
    def _try_simple_patterns(self, query: str) -> Optional[str]:
        """Try to match common query patterns."""
        query_lower = query.lower()
        
        # System status check
        if any(phrase in query_lower for phrase in ['is this thing on', 'is it working', 'system status', 'database status']):
            return "SELECT COUNT(*) as total_articles, COUNT(DISTINCT source_id) as active_sources FROM articles"
        
        # Count articles
        if any(word in query_lower for word in ['how many', 'count', 'number of']) and 'article' in query_lower:
            return "SELECT COUNT(*) as article_count FROM articles"
        
        # Recent articles
        if any(word in query_lower for word in ['recent', 'latest', 'new']) and 'article' in query_lower:
            return "SELECT a.title, s.name as source, a.published_at FROM articles a JOIN sources s ON a.source_id = s.id ORDER BY a.published_at DESC LIMIT 100"
        
        # Articles by source
        if 'source' in query_lower and ('top' in query_lower or 'by' in query_lower):
            return "SELECT s.name, COUNT(a.id) as article_count FROM sources s JOIN articles a ON s.id = a.source_id GROUP BY s.id, s.name ORDER BY article_count DESC LIMIT 100"
        
        # Threat hunting scores
        if 'threat' in query_lower and 'score' in query_lower:
            return "SELECT a.title, s.name as source, (a.article_metadata->>'threat_hunting_score')::float as threat_score FROM articles a JOIN sources s ON a.source_id = s.id WHERE a.article_metadata->>'threat_hunting_score' IS NOT NULL ORDER BY threat_score DESC LIMIT 100"
        
        # Articles with specific keywords
        if 'contain' in query_lower or 'about' in query_lower or 'from the last' in query_lower or 'show me' in query_lower:
            # Extract potential keywords from the query - look for capitalized words (likely proper nouns)
            words = query_lower.split()
            keywords = []
            for word in words:
                if len(word) > 3 and word not in ['articles', 'about', 'contain', 'that', 'with', 'from', 'this', 'that', 'last', 'days', 'weeks', 'months', 'show', 'me']:
                    # Check if original query has this word capitalized (likely a proper noun)
                    original_words = query.split()
                    for orig_word in original_words:
                        if orig_word.lower() == word and orig_word[0].isupper():
                            keywords.append(word)
                            break
                    # If no capitalized version found, use the word as-is for common threat terms
                    if not keywords or keywords[-1] != word:
                        if word in ['ransomware', 'malware', 'apt', 'phishing', 'trojan', 'virus', 'backdoor', 'rootkit', 'botnet', 'cryptocurrency', 'bitcoin', 'ethereum']:
                            keywords.append(word)
            
            if keywords:
                keyword = keywords[0]
                # Check if query mentions time period
                if 'last' in query_lower and ('days' in query_lower or 'weeks' in query_lower or 'months' in query_lower):
                    if 'days' in query_lower:
                        return f"SELECT a.title, s.name as source, a.published_at FROM articles a JOIN sources s ON a.source_id = s.id WHERE a.content ILIKE '%{keyword}%' AND a.published_at >= NOW() - INTERVAL '30 days' ORDER BY a.published_at DESC LIMIT 100"
                    elif 'weeks' in query_lower:
                        return f"SELECT a.title, s.name as source, a.published_at FROM articles a JOIN sources s ON a.source_id = s.id WHERE a.content ILIKE '%{keyword}%' AND a.published_at >= NOW() - INTERVAL '1 week' ORDER BY a.published_at DESC LIMIT 100"
                    elif 'months' in query_lower:
                        return f"SELECT a.title, s.name as source, a.published_at FROM articles a JOIN sources s ON a.source_id = s.id WHERE a.content ILIKE '%{keyword}%' AND a.published_at >= NOW() - INTERVAL '3 months' ORDER BY a.published_at DESC LIMIT 100"
                else:
                    return f"SELECT a.title, s.name as source, a.published_at FROM articles a JOIN sources s ON a.source_id = s.id WHERE a.content ILIKE '%{keyword}%' ORDER BY a.published_at DESC LIMIT 100"
        
        return None
    
    def _build_sql_prompt(self, query: str) -> str:
        """Build the prompt for SQL generation."""
        return f"""Generate a PostgreSQL SQL query for: {query}

Database schema:
- articles(id, title, content, published_at, source_id, article_metadata)
- sources(id, name, active)

Rules:
- Only output the SQL query
- Use SELECT statements only
- No explanations or comments
- Use proper PostgreSQL syntax

Query:"""
    
    def _extract_sql_from_response(self, response: str) -> str:
        """Extract SQL query from the LLM response."""
        # Look for SQL between ```sql and ``` markers
        if "```sql" in response:
            start = response.find("```sql") + 6
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()
        
        # Look for SQL between ``` and ``` markers
        if "```" in response:
            parts = response.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        
        # Look for SELECT statement in the response
        lines = response.split('\n')
        for line in lines:
            if line.strip().upper().startswith('SELECT'):
                return line.strip()
        
        # If no SQL found, fall back to simple pattern matching
        # This prevents returning explanatory text that contains forbidden keywords
        return None
    
    async def explain_query(self, sql: str, results: List[Dict], user_question: str) -> str:
        """
        Generate a natural language explanation of the query results.
        
        Args:
            sql: The SQL query that was executed
            results: The query results
            user_question: Original user question
            
        Returns:
            Natural language explanation
        """
        # Simple explanation for pattern matching queries (fast)
        if "COUNT(*)" in sql.upper():
            count = results[0].get('article_count', results[0].get('total_articles', 0))
            return f"The query result indicates that there are {count:,} articles available in the database."
        
        if "ILIKE" in sql.upper() and "ORDER BY" in sql.upper():
            count = len(results)
            keyword = sql.split("ILIKE '%")[1].split("%'")[0] if "ILIKE '%" in sql else "the specified keyword"
            return f"Found {count} articles containing '{keyword}' in their content, ordered by publication date."
        
        if "JOIN" in sql.upper() and "ORDER BY" in sql.upper():
            count = len(results)
            return f"Retrieved {count} articles with source information, ordered by publication date."
        
        # Fall back to LLM for complex queries
        prompt = f"""Explain these query results briefly:

Question: {user_question}
Results: {json.dumps(results[:5], indent=2)}

Provide a concise summary (2-3 sentences max):"""
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,  # Concise, factual explanations
                            "num_predict": 256
                        }
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get("response", "").strip()
                else:
                    return f"Error generating explanation: {response.status_code}"
                    
        except Exception as e:
            logger.error(f"Explanation generation error: {e}")
            return f"Error generating explanation: {str(e)}"
