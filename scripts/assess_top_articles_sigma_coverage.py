#!/usr/bin/env python3
"""
Sigma Coverage Assessment for Top Articles

Runs Sigma similarity matching against the top 25 articles by hunt score
and reports coverage breakdown (covered/extend/new).
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.services.sigma_matching_service import SigmaMatchingService
from src.services.sigma_coverage_service import SigmaCoverageService
from sqlalchemy import desc
from src.database.models import ArticleTable


def main():
    """Assess Sigma coverage for top 25 articles."""
    print("🔍 Sigma Coverage Assessment for Top 25 Articles")
    print("=" * 60)
    
    db_manager = DatabaseManager()
    session = db_manager.get_session()
    
    try:
        # Get top 25 articles by hunt score
        print("\n📊 Fetching top 25 articles by hunt score...")
        from sqlalchemy import text
        
        # Use raw SQL to query hunt scores from JSON metadata
        articles_query = text("""
            SELECT id, title, canonical_url, published_at, article_metadata
            FROM articles
            WHERE article_metadata->>'threat_hunting_score' IS NOT NULL
              AND (article_metadata->>'threat_hunting_score')::float > 0
            ORDER BY (article_metadata->>'threat_hunting_score')::float DESC
            LIMIT 25
        """)
        
        result = session.execute(articles_query)
        rows = result.fetchall()
        
        articles = []
        for row in rows:
            hunt_score = row.article_metadata.get('threat_hunting_score') if row.article_metadata else 0
            articles.append({
                'id': row.id,
                'title': row.title,
                'canonical_url': row.canonical_url,
                'published_at': row.published_at,
                'hunt_score': hunt_score
            })
        
        print(f"Found {len(articles)} articles with hunt scores\n")
        
        if not articles:
            print("❌ No articles with hunt scores found.")
            return
        
        # Initialize services
        matching_service = SigmaMatchingService(session)
        coverage_service = SigmaCoverageService(session)
        
        # Track results
        total_assessments = 0
        coverage_summary = {
            'covered': 0,
            'extend': 0,
            'new': 0,
            'no_matches': 0
        }
        
        article_results = []
        
        # Assess each article
        for idx, article in enumerate(articles, 1):
            print(f"[{idx}/{len(articles)}] Processing Article {article['id']}: {article['title'][:60]}")
            print(f"   Hunt Score: {article['hunt_score']}")
            
            # Get matches
            matches = matching_service.match_article_to_rules(
                article_id=article['id'],
                threshold=0.0,  # Get all matches
                limit=10
            )
            
            total_assessments += 1
            article_coverage = {'covered': 0, 'extend': 0, 'new': 0}
            
            if not matches:
                coverage_summary['no_matches'] += 1
                print(f"   ⚠️  No Sigma matches found")
            else:
                # Process matches and classify coverage
                for match in matches:
                    # Get the rule
                    from src.database.models import SigmaRuleTable
                    rule = session.query(SigmaRuleTable).filter_by(
                        rule_id=match['rule_id']
                    ).first()
                    
                    if rule:
                        # Classify coverage
                        classification = coverage_service.classify_match(
                            article_id=article['id'],
                            sigma_rule=rule,
                            similarity_score=match['similarity_score']
                        )
                        
                        status = classification['coverage_status']
                        if status in article_coverage:
                            article_coverage[status] += 1
                
                # Update summary
                for status in ['covered', 'extend', 'new']:
                    coverage_summary[status] += article_coverage[status]
                
                # Print results
                if article_coverage['covered'] > 0:
                    print(f"   ✅ Covered: {article_coverage['covered']}")
                if article_coverage['extend'] > 0:
                    print(f"   ⚡ Extend: {article_coverage['extend']}")
                if article_coverage['new'] > 0:
                    print(f"   ✨ New: {article_coverage['new']}")
                
                if article_coverage['covered'] == 0 and article_coverage['extend'] == 0 and article_coverage['new'] == 0:
                    print(f"   📊 Total matches: {len(matches)} (all unclassified)")
            
            article_results.append({
                'article_id': article['id'],
                'title': article['title'],
                'hunt_score': article['hunt_score'],
                'coverage': article_coverage,
                'total_matches': len(matches)
            })
            print()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📈 COVERAGE SUMMARY")
        print("=" * 60)
        print(f"Total Articles Assessed: {total_assessments}")
        print()
        print("Coverage Breakdown:")
        print(f"  ✅ Covered: {coverage_summary['covered']} rules")
        print(f"  ⚡ Extend:  {coverage_summary['extend']} rules")
        print(f"  ✨ New:     {coverage_summary['new']} rules")
        print(f"  ⚠️  No matches: {coverage_summary['no_matches']} articles")
        print()
        
        # Articles breakdown
        print("=" * 60)
        print("📋 TOP ARTICLES BY COVERAGE STATUS")
        print("=" * 60)
        
        # Group articles by coverage status
        well_covered = [a for a in article_results if a['coverage']['covered'] > 0]
        partial_cover = [a for a in article_results if a['coverage']['extend'] > 0 and a['coverage']['covered'] == 0]
        new_rules_needed = [a for a in article_results if a['coverage']['covered'] == 0 and a['coverage']['extend'] == 0]
        
        print(f"\n✅ Well Covered ({len(well_covered)} articles):")
        for a in well_covered[:5]:
            print(f"   ID {a['article_id']}: {a['hunt_score']} - {a['coverage']['covered']} covered")
        
        print(f"\n⚡ Need Extension ({len(partial_cover)} articles):")
        for a in partial_cover[:5]:
            print(f"   ID {a['article_id']}: {a['hunt_score']} - {a['coverage']['extend']} to extend")
        
        print(f"\n✨ Need New Rules ({len(new_rules_needed)} articles):")
        for a in new_rules_needed[:5]:
            print(f"   ID {a['article_id']}: {a['hunt_score']} - {a['total_matches']} matches, all new")
        
    finally:
        session.close()


if __name__ == "__main__":
    main()

