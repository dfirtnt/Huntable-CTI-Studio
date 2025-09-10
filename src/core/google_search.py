"""Google Custom Search API integration for threat intelligence discovery."""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import urlparse
import httpx

from src.models.article import ArticleCreate
from src.models.source import Source
from src.utils.http import HTTPClient
from src.utils.content import ContentCleaner, DateExtractor, MetadataExtractor

logger = logging.getLogger(__name__)


class GoogleSearchResult:
    """Represents a single Google Search result."""
    
    def __init__(self, result_data: Dict[str, Any]):
        self.title = result_data.get('title', '')
        self.link = result_data.get('link', '')
        self.snippet = result_data.get('snippet', '')
        self.display_link = result_data.get('displayLink', '')
        self.formatted_url = result_data.get('formattedUrl', '')
        self.pagemap = result_data.get('pagemap', {})
        
        # Extract publication date if available
        self.published_at = self._extract_published_date()
    
    def _extract_published_date(self) -> Optional[datetime]:
        """Extract publication date from pagemap or snippet."""
        try:
            # Try to get date from pagemap
            if 'metatags' in self.pagemap:
                metatags = self.pagemap['metatags'][0] if self.pagemap['metatags'] else {}
                
                # Common date fields
                date_fields = [
                    'article:published_time',
                    'article:modified_time', 
                    'pubdate',
                    'date',
                    'dc.date.issued'
                ]
                
                for field in date_fields:
                    if field in metatags:
                        date_str = metatags[field]
                        parsed_date = DateExtractor.parse_date(date_str)
                        if parsed_date:
                            return parsed_date
            
            # Fallback: try to extract from snippet
            if self.snippet:
                parsed_date = DateExtractor.extract_date_from_text(self.snippet)
                if parsed_date:
                    return parsed_date
                    
        except Exception as e:
            logger.debug(f"Failed to extract date from search result: {e}")
        
        return None


class GoogleSearchAPI:
    """Google Custom Search API client."""
    
    def __init__(self, api_key: str, search_engine_id: str):
        self.api_key = api_key
        self.search_engine_id = search_engine_id
        self.base_url = "https://www.googleapis.com/customsearch/v1"
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def search(
        self, 
        query: str, 
        num_results: int = 10,
        date_restrict: Optional[str] = None,
        site_restrict: Optional[List[str]] = None,
        exclude_terms: Optional[List[str]] = None
    ) -> List[GoogleSearchResult]:
        """
        Perform Google Custom Search.
        
        Args:
            query: Search query string
            num_results: Number of results to return (max 10 per request)
            date_restrict: Date restriction (e.g., 'd1' for past day, 'm1' for past month)
            site_restrict: List of sites to restrict search to
            exclude_terms: List of terms to exclude from search
            
        Returns:
            List of GoogleSearchResult objects
        """
        # Build search query
        search_query = query
        
        if site_restrict:
            site_query = " OR ".join([f"site:{site}" for site in site_restrict])
            search_query = f"({query}) AND ({site_query})"
        
        if exclude_terms:
            exclude_query = " ".join([f"-{term}" for term in exclude_terms])
            search_query = f"{search_query} {exclude_query}"
        
        params = {
            'key': self.api_key,
            'cx': self.search_engine_id,
            'q': search_query,
            'num': min(num_results, 10),  # Google API max is 10 per request
            'fields': 'items(title,link,snippet,displayLink,formattedUrl,pagemap)'
        }
        
        if date_restrict:
            params['dateRestrict'] = date_restrict
        
        try:
            logger.info(f"Google Search API query: {search_query}")
            response = await self.http_client.get(self.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            for item in data.get('items', []):
                try:
                    result = GoogleSearchResult(item)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to parse search result: {e}")
                    continue
            
            logger.info(f"Google Search returned {len(results)} results")
            return results
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.error("Google Search API quota exceeded or invalid credentials")
            elif e.response.status_code == 400:
                logger.error(f"Invalid Google Search API request: {e.response.text}")
            else:
                logger.error(f"Google Search API HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Google Search API error: {e}")
            raise
    
    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()


class GoogleSearchFetcher:
    """Fetches threat intelligence articles via Google Custom Search."""
    
    def __init__(self, http_client: HTTPClient):
        self.http_client = http_client
        self.google_api: Optional[GoogleSearchAPI] = None
    
    async def fetch_source(self, source: Source) -> List[ArticleCreate]:
        """
        Fetch articles from Google Search based on source configuration.
        
        Args:
            source: Source configuration with Google Search settings
            
        Returns:
            List of ArticleCreate objects
        """
        logger.info(f"Starting Google Search fetch for {source.name}")
        
        search_config = source.config.get('search_config', {})
        
        # Initialize Google API if not already done
        if not self.google_api:
            api_key = search_config.get('api_key')
            search_engine_id = search_config.get('search_engine_id')
            
            if not api_key or not search_engine_id:
                logger.error(f"Missing Google Search API credentials for {source.name}")
                return []
            
            self.google_api = GoogleSearchAPI(api_key, search_engine_id)
        
        try:
            # Get search parameters
            queries = search_config.get('queries', [search_config.get('query', 'threat intelligence')])
            max_results = search_config.get('max_results', 20)
            date_range = search_config.get('date_range', 'past_month')
            site_restrictions = search_config.get('site_restrictions', [])
            exclude_domains = search_config.get('exclude_domains', [])
            
            # Convert date range to Google API format
            date_restrict = self._convert_date_range(date_range)
            
            all_results = []
            
            # Execute multiple queries
            for query in queries:
                try:
                    results = await self.google_api.search(
                        query=query,
                        num_results=min(max_results // len(queries), 10),
                        date_restrict=date_restrict,
                        site_restrict=site_restrictions,
                        exclude_terms=exclude_domains
                    )
                    all_results.extend(results)
                    
                    # Rate limiting between queries
                    await asyncio.sleep(1.0)
                    
                except Exception as e:
                    logger.error(f"Google Search query failed for '{query}': {e}")
                    continue
            
            # Convert results to articles
            articles = []
            for result in all_results:
                try:
                    article = await self._convert_to_article(result, source)
                    if article:
                        articles.append(article)
                except Exception as e:
                    logger.error(f"Failed to convert search result to article: {e}")
                    continue
            
            logger.info(f"Google Search fetch completed: {len(articles)} articles from {source.name}")
            return articles
            
        except Exception as e:
            logger.error(f"Google Search fetch failed for {source.name}: {e}")
            return []
    
    def _convert_date_range(self, date_range: str) -> Optional[str]:
        """Convert date range string to Google API format."""
        mapping = {
            'past_day': 'd1',
            'past_week': 'w1', 
            'past_month': 'm1',
            'past_year': 'y1'
        }
        return mapping.get(date_range)
    
    async def _convert_to_article(self, result: GoogleSearchResult, source: Source) -> Optional[ArticleCreate]:
        """Convert Google Search result to ArticleCreate object."""
        try:
            # Validate URL
            if not result.link or not result.title:
                return None
            
            # Skip certain domains if configured
            exclude_domains = source.config.get('search_config', {}).get('exclude_domains', [])
            parsed_url = urlparse(result.link)
            if any(domain in parsed_url.netloc for domain in exclude_domains):
                return None
            
            # Extract content from the page
            content = await self._extract_page_content(result.link)
            
            if not content:
                # Fallback to snippet
                content = result.snippet
            
            # Extract metadata
            metadata = {
                'google_search': {
                    'query_used': 'N/A',  # Could track this if needed
                    'snippet': result.snippet,
                    'display_link': result.display_link,
                    'formatted_url': result.formatted_url
                },
                'extraction_method': 'google_search',
                'source_type': 'google_search'
            }
            
            # Extract additional metadata from content
            if content and len(content) > 100:  # Only if we have substantial content
                metadata_extractor = MetadataExtractor()
                additional_metadata = metadata_extractor.extract_metadata(content)
                metadata.update(additional_metadata)
            
            # Create article
            article = ArticleCreate(
                source_id=source.id,
                canonical_url=result.link,
                title=result.title,
                published_at=result.published_at or datetime.utcnow(),
                authors=[],  # Google Search doesn't provide author info
                tags=[],     # Could be extracted from content
                summary=result.snippet,
                content=content,
                metadata=metadata
            )
            
            return article
            
        except Exception as e:
            logger.error(f"Failed to convert search result to article: {e}")
            return None
    
    async def _extract_page_content(self, url: str) -> Optional[str]:
        """Extract content from the target page."""
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            
            # Use ContentCleaner to extract text
            cleaner = ContentCleaner()
            content = cleaner.html_to_text(response.text)
            
            # Return content if substantial
            if content and len(content.strip()) > 200:
                return content
            
        except Exception as e:
            logger.debug(f"Failed to extract content from {url}: {e}")
        
        return None
    
    async def close(self):
        """Close Google API client."""
        if self.google_api:
            await self.google_api.close()
