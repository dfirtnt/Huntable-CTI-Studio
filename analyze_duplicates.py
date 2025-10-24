#!/usr/bin/env python3
"""
Comprehensive Duplicate Article Analysis Tool

This script performs a robust analysis to identify potentially duplicate articles
using multiple detection methods:
1. Exact duplicates (content hash, canonical URL)
2. Near-duplicates (SimHash similarity)
3. Title similarity analysis
4. Content similarity analysis
5. Cross-source duplicate detection
"""

import os
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple, Set
from collections import defaultdict, Counter
import hashlib
import re
from difflib import SequenceMatcher

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from database.async_manager import AsyncDatabaseManager
from database.models import ArticleTable, SourceTable
from utils.simhash import simhash_calculator
import asyncio
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DuplicateAnalyzer:
    """Comprehensive duplicate detection and analysis."""
    
    def __init__(self):
        self.db_manager = AsyncDatabaseManager()
        self.results = {
            'exact_duplicates': {'content_hash': [], 'canonical_url': []},
            'near_duplicates': [],
            'title_similarities': [],
            'content_similarities': [],
            'cross_source_duplicates': [],
            'summary': {
                'total_articles': 0,
                'exact_duplicates_count': 0,
                'near_duplicates_count': 0,
                'title_similarities_count': 0,
                'content_similarities_count': 0,
                'cross_source_duplicates_count': 0,
                'analysis_timestamp': datetime.now().isoformat()
            }
        }
    
    async def analyze_all_duplicates(self) -> Dict[str, Any]:
        """Run comprehensive duplicate analysis."""
        logger.info("Starting comprehensive duplicate analysis...")
        
        async with self.db_manager.get_session() as session:
            # Get all articles
            articles = await self._get_all_articles(session)
            self.results['summary']['total_articles'] = len(articles)
            
            logger.info(f"Analyzing {len(articles)} articles for duplicates...")
            
            # 1. Exact duplicates by content hash
            await self._analyze_content_hash_duplicates(session, articles)
            
            # 2. Exact duplicates by canonical URL
            await self._analyze_url_duplicates(session, articles)
            
            # 3. Near-duplicates using SimHash
            await self._analyze_simhash_duplicates(session, articles)
            
            # 4. Title similarity analysis
            await self._analyze_title_similarities(session, articles)
            
            # 5. Content similarity analysis
            await self._analyze_content_similarities(session, articles)
            
            # 6. Cross-source duplicate detection
            await self._analyze_cross_source_duplicates(session, articles)
            
            # Update summary counts
            self._update_summary_counts()
            
        logger.info("Duplicate analysis completed.")
        return self.results
    
    async def _get_all_articles(self, session) -> List[ArticleTable]:
        """Get all articles from database."""
        from sqlalchemy import select
        result = await session.execute(select(ArticleTable))
        return result.scalars().all()
    
    async def _analyze_content_hash_duplicates(self, session, articles: List[ArticleTable]):
        """Find exact duplicates by content hash."""
        logger.info("Analyzing content hash duplicates...")
        
        hash_groups = defaultdict(list)
        for article in articles:
            if article.content_hash:
                hash_groups[article.content_hash].append(article)
        
        duplicates = []
        for content_hash, article_group in hash_groups.items():
            if len(article_group) > 1:
                duplicates.append({
                    'content_hash': content_hash,
                    'count': len(article_group),
                    'articles': [
                        {
                            'id': a.id,
                            'title': a.title,
                            'canonical_url': a.canonical_url,
                            'source_id': a.source_id,
                            'published_at': a.published_at.isoformat() if a.published_at else None,
                            'created_at': a.created_at.isoformat() if a.created_at else None
                        }
                        for a in article_group
                    ]
                })
        
        self.results['exact_duplicates']['content_hash'] = sorted(duplicates, key=lambda x: x['count'], reverse=True)
        logger.info(f"Found {len(duplicates)} content hash duplicate groups")
    
    async def _analyze_url_duplicates(self, session, articles: List[ArticleTable]):
        """Find exact duplicates by canonical URL."""
        logger.info("Analyzing URL duplicates...")
        
        url_groups = defaultdict(list)
        for article in articles:
            if article.canonical_url:
                url_groups[article.canonical_url].append(article)
        
        duplicates = []
        for url, article_group in url_groups.items():
            if len(article_group) > 1:
                duplicates.append({
                    'canonical_url': url,
                    'count': len(article_group),
                    'articles': [
                        {
                            'id': a.id,
                            'title': a.title,
                            'content_hash': a.content_hash,
                            'source_id': a.source_id,
                            'published_at': a.published_at.isoformat() if a.published_at else None,
                            'created_at': a.created_at.isoformat() if a.created_at else None
                        }
                        for a in article_group
                    ]
                })
        
        self.results['exact_duplicates']['canonical_url'] = sorted(duplicates, key=lambda x: x['count'], reverse=True)
        logger.info(f"Found {len(duplicates)} URL duplicate groups")
    
    async def _analyze_simhash_duplicates(self, session, articles: List[ArticleTable]):
        """Find near-duplicates using SimHash."""
        logger.info("Analyzing SimHash near-duplicates...")
        
        # Group articles by SimHash bucket
        bucket_groups = defaultdict(list)
        for article in articles:
            if article.simhash_bucket is not None and article.simhash is not None:
                bucket_groups[article.simhash_bucket].append(article)
        
        near_duplicates = []
        threshold = 3  # Hamming distance threshold
        
        for bucket_id, bucket_articles in bucket_groups.items():
            if len(bucket_articles) > 1:
                # Compare all pairs in the bucket
                for i, article1 in enumerate(bucket_articles):
                    for j, article2 in enumerate(bucket_articles[i+1:], i+1):
                        try:
                            # Convert to int for comparison
                            simhash1 = int(article1.simhash) if article1.simhash else 0
                            simhash2 = int(article2.simhash) if article2.simhash else 0
                            
                            distance = simhash_calculator.hamming_distance(simhash1, simhash2)
                            
                            if distance <= threshold:
                                near_duplicates.append({
                                    'bucket_id': bucket_id,
                                    'hamming_distance': distance,
                                    'article1': {
                                        'id': article1.id,
                                        'title': article1.title,
                                        'canonical_url': article1.canonical_url,
                                        'source_id': article1.source_id,
                                        'simhash': str(simhash1)
                                    },
                                    'article2': {
                                        'id': article2.id,
                                        'title': article2.title,
                                        'canonical_url': article2.canonical_url,
                                        'source_id': article2.source_id,
                                        'simhash': str(simhash2)
                                    }
                                })
                        except Exception as e:
                            logger.warning(f"Error comparing SimHash for articles {article1.id} and {article2.id}: {e}")
        
        self.results['near_duplicates'] = sorted(near_duplicates, key=lambda x: x['hamming_distance'])
        logger.info(f"Found {len(near_duplicates)} near-duplicate pairs")
    
    async def _analyze_title_similarities(self, session, articles: List[ArticleTable]):
        """Find articles with similar titles."""
        logger.info("Analyzing title similarities...")
        
        similarities = []
        threshold = 0.8  # Similarity threshold
        
        for i, article1 in enumerate(articles):
            for j, article2 in enumerate(articles[i+1:], i+1):
                if article1.title and article2.title:
                    similarity = SequenceMatcher(None, article1.title.lower(), article2.title.lower()).ratio()
                    
                    if similarity >= threshold:
                        similarities.append({
                            'similarity_score': similarity,
                            'article1': {
                                'id': article1.id,
                                'title': article1.title,
                                'canonical_url': article1.canonical_url,
                                'source_id': article1.source_id
                            },
                            'article2': {
                                'id': article2.id,
                                'title': article2.title,
                                'canonical_url': article2.canonical_url,
                                'source_id': article2.source_id
                            }
                        })
        
        self.results['title_similarities'] = sorted(similarities, key=lambda x: x['similarity_score'], reverse=True)
        logger.info(f"Found {len(similarities)} title similarity pairs")
    
    async def _analyze_content_similarities(self, session, articles: List[ArticleTable]):
        """Find articles with similar content (first 1000 chars)."""
        logger.info("Analyzing content similarities...")
        
        similarities = []
        threshold = 0.85  # Similarity threshold
        content_length = 1000  # Compare first 1000 characters
        
        for i, article1 in enumerate(articles):
            for j, article2 in enumerate(articles[i+1:], i+1):
                if article1.content and article2.content:
                    content1 = article1.content[:content_length].lower()
                    content2 = article2.content[:content_length].lower()
                    
                    similarity = SequenceMatcher(None, content1, content2).ratio()
                    
                    if similarity >= threshold:
                        similarities.append({
                            'similarity_score': similarity,
                            'article1': {
                                'id': article1.id,
                                'title': article1.title,
                                'canonical_url': article1.canonical_url,
                                'source_id': article1.source_id,
                                'content_preview': article1.content[:200] + "..."
                            },
                            'article2': {
                                'id': article2.id,
                                'title': article2.title,
                                'canonical_url': article2.canonical_url,
                                'source_id': article2.source_id,
                                'content_preview': article2.content[:200] + "..."
                            }
                        })
        
        self.results['content_similarities'] = sorted(similarities, key=lambda x: x['similarity_score'], reverse=True)
        logger.info(f"Found {len(similarities)} content similarity pairs")
    
    async def _analyze_cross_source_duplicates(self, session, articles: List[ArticleTable]):
        """Find duplicates across different sources."""
        logger.info("Analyzing cross-source duplicates...")
        
        # Group by normalized title and content hash
        title_groups = defaultdict(list)
        content_groups = defaultdict(list)
        
        for article in articles:
            if article.title:
                # Normalize title (remove special chars, lowercase)
                normalized_title = re.sub(r'[^\w\s]', '', article.title.lower().strip())
                title_groups[normalized_title].append(article)
            
            if article.content_hash:
                content_groups[article.content_hash].append(article)
        
        cross_source_duplicates = []
        
        # Check title groups for cross-source duplicates
        for normalized_title, article_group in title_groups.items():
            if len(article_group) > 1:
                sources = set(a.source_id for a in article_group)
                if len(sources) > 1:  # Different sources
                    cross_source_duplicates.append({
                        'type': 'title',
                        'normalized_title': normalized_title,
                        'source_count': len(sources),
                        'sources': list(sources),
                        'articles': [
                            {
                                'id': a.id,
                                'title': a.title,
                                'canonical_url': a.canonical_url,
                                'source_id': a.source_id,
                                'published_at': a.published_at.isoformat() if a.published_at else None
                            }
                            for a in article_group
                        ]
                    })
        
        # Check content hash groups for cross-source duplicates
        for content_hash, article_group in content_groups.items():
            if len(article_group) > 1:
                sources = set(a.source_id for a in article_group)
                if len(sources) > 1:  # Different sources
                    cross_source_duplicates.append({
                        'type': 'content_hash',
                        'content_hash': content_hash,
                        'source_count': len(sources),
                        'sources': list(sources),
                        'articles': [
                            {
                                'id': a.id,
                                'title': a.title,
                                'canonical_url': a.canonical_url,
                                'source_id': a.source_id,
                                'published_at': a.published_at.isoformat() if a.published_at else None
                            }
                            for a in article_group
                        ]
                    })
        
        self.results['cross_source_duplicates'] = sorted(cross_source_duplicates, key=lambda x: x['source_count'], reverse=True)
        logger.info(f"Found {len(cross_source_duplicates)} cross-source duplicate groups")
    
    def _update_summary_counts(self):
        """Update summary statistics."""
        self.results['summary']['exact_duplicates_count'] = (
            len(self.results['exact_duplicates']['content_hash']) +
            len(self.results['exact_duplicates']['canonical_url'])
        )
        self.results['summary']['near_duplicates_count'] = len(self.results['near_duplicates'])
        self.results['summary']['title_similarities_count'] = len(self.results['title_similarities'])
        self.results['summary']['content_similarities_count'] = len(self.results['content_similarities'])
        self.results['summary']['cross_source_duplicates_count'] = len(self.results['cross_source_duplicates'])
    
    def generate_report(self) -> str:
        """Generate a comprehensive duplicate analysis report."""
        report = []
        report.append("# Duplicate Article Analysis Report")
        report.append(f"Generated: {self.results['summary']['analysis_timestamp']}")
        report.append("")
        
        # Summary
        summary = self.results['summary']
        report.append("## Summary")
        report.append(f"- **Total Articles**: {summary['total_articles']}")
        report.append(f"- **Exact Duplicates**: {summary['exact_duplicates_count']} groups")
        report.append(f"- **Near Duplicates**: {summary['near_duplicates_count']} pairs")
        report.append(f"- **Title Similarities**: {summary['title_similarities_count']} pairs")
        report.append(f"- **Content Similarities**: {summary['content_similarities_count']} pairs")
        report.append(f"- **Cross-Source Duplicates**: {summary['cross_source_duplicates_count']} groups")
        report.append("")
        
        # Exact duplicates by content hash
        if self.results['exact_duplicates']['content_hash']:
            report.append("## Exact Duplicates (Content Hash)")
            for dup in self.results['exact_duplicates']['content_hash'][:10]:  # Top 10
                report.append(f"### Hash: {dup['content_hash'][:16]}... ({dup['count']} articles)")
                for article in dup['articles']:
                    report.append(f"- ID {article['id']}: {article['title'][:80]}...")
                report.append("")
        
        # Exact duplicates by URL
        if self.results['exact_duplicates']['canonical_url']:
            report.append("## Exact Duplicates (Canonical URL)")
            for dup in self.results['exact_duplicates']['canonical_url'][:10]:  # Top 10
                report.append(f"### URL: {dup['canonical_url'][:80]}... ({dup['count']} articles)")
                for article in dup['articles']:
                    report.append(f"- ID {article['id']}: {article['title'][:80]}...")
                report.append("")
        
        # Near duplicates
        if self.results['near_duplicates']:
            report.append("## Near Duplicates (SimHash)")
            for dup in self.results['near_duplicates'][:10]:  # Top 10
                report.append(f"### Hamming Distance: {dup['hamming_distance']}")
                report.append(f"- ID {dup['article1']['id']}: {dup['article1']['title'][:60]}...")
                report.append(f"- ID {dup['article2']['id']}: {dup['article2']['title'][:60]}...")
                report.append("")
        
        # Title similarities
        if self.results['title_similarities']:
            report.append("## Title Similarities")
            for sim in self.results['title_similarities'][:10]:  # Top 10
                report.append(f"### Similarity: {sim['similarity_score']:.2f}")
                report.append(f"- ID {sim['article1']['id']}: {sim['article1']['title'][:60]}...")
                report.append(f"- ID {sim['article2']['id']}: {sim['article2']['title'][:60]}...")
                report.append("")
        
        # Cross-source duplicates
        if self.results['cross_source_duplicates']:
            report.append("## Cross-Source Duplicates")
            for dup in self.results['cross_source_duplicates'][:10]:  # Top 10
                report.append(f"### {dup['type'].title()} ({dup['source_count']} sources)")
                for article in dup['articles']:
                    report.append(f"- ID {article['id']} (Source {article['source_id']}): {article['title'][:60]}...")
                report.append("")
        
        return "\n".join(report)
    
    def save_results(self, filename: str = None):
        """Save analysis results to JSON file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"duplicate_analysis_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        logger.info(f"Results saved to {filename}")
        return filename


async def main():
    """Main execution function."""
    analyzer = DuplicateAnalyzer()
    
    try:
        # Run analysis
        results = await analyzer.analyze_all_duplicates()
        
        # Generate and print report
        report = analyzer.generate_report()
        print(report)
        
        # Save results
        json_file = analyzer.save_results()
        
        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"duplicate_analysis_report_{timestamp}.md"
        with open(report_file, 'w') as f:
            f.write(report)
        
        logger.info(f"Report saved to {report_file}")
        logger.info(f"JSON results saved to {json_file}")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
