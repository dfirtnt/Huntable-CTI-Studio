#!/usr/bin/env python3
"""
Simple article exporter for the CTI Scraper database.
"""
import sys
import json
import csv
from pathlib import Path
from datetime import datetime
from rich.console import Console

# Add src to path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from database.manager import DatabaseManager

console = Console()

def export_articles(format_type='json', output_file=None, limit=50):
    """Export collected articles."""
    
    # Initialize database
    db_manager = DatabaseManager()
    db_manager.create_tables()
    
    console.print(f"\n📤 [bold blue]Exporting Articles ({format_type.upper()})[/bold blue]\n")
    
    try:
        session = db_manager.get_session()
        
        # Get articles
        articles = db_manager.list_articles()
        
        if not articles:
            console.print("❌ [red]No articles found in database[/red]")
            return
        
        # Limit articles if needed
        if limit and len(articles) > limit:
            articles = articles[:limit]
            console.print(f"📊 [yellow]Limiting to {limit} articles[/yellow]")
        
        console.print(f"📊 [green]Exporting {len(articles)} articles[/green]")
        
        # Prepare data
        if format_type.lower() == 'json':
            export_data = []
            for article in articles:
                article_data = {
                    'id': article.id,
                    'source_id': article.source_id,
                    'canonical_url': article.canonical_url,
                    'title': article.title,
                    'published_at': article.published_at.isoformat() if article.published_at else None,
                    'modified_at': article.modified_at.isoformat() if article.modified_at else None,
                    'authors': article.authors,
                    'tags': article.tags,
                    'summary': article.summary,
                    'content_length': len(article.content),
                    'content_preview': article.content[:500] + "..." if len(article.content) > 500 else article.content,
                    'content_hash': article.content_hash,
                    'metadata': getattr(article, 'metadata', {}) if hasattr(article, 'metadata') else {},
                    'discovered_at': article.discovered_at.isoformat() if hasattr(article, 'discovered_at') and article.discovered_at else None,
                    'processing_status': getattr(article, 'processing_status', 'unknown') if hasattr(article, 'processing_status') else 'unknown'
                }
                export_data.append(article_data)
            
            # Save to file
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                console.print(f"✅ [green]Exported to {output_file}[/green]")
            else:
                # Print first few articles
                console.print(f"\n📄 [bold yellow]Sample Articles (JSON):[/bold yellow]\n")
                print(json.dumps(export_data[:3], indent=2, ensure_ascii=False))
                
        elif format_type.lower() == 'csv':
            if output_file:
                with open(output_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    # Write header
                    writer.writerow([
                        'ID', 'Source ID', 'Title', 'URL', 'Published', 'Authors', 'Tags', 
                        'Content Length', 'Content Hash', 'Quality Score'
                    ])
                    
                    # Write data
                    for article in articles:
                        quality_score = getattr(article, 'metadata', {}).get('quality_score', 'N/A') if hasattr(article, 'metadata') else 'N/A'
                        writer.writerow([
                            article.id,
                            article.source_id,
                            article.title,
                            article.canonical_url,
                            article.published_at.isoformat() if article.published_at else '',
                            ', '.join(article.authors) if article.authors else '',
                            ', '.join(article.tags) if article.tags else '',
                            len(article.content),
                            article.content_hash,
                            quality_score
                        ])
                
                console.print(f"✅ [green]Exported to {output_file}[/green]")
            else:
                console.print(f"\n📊 [bold yellow]Sample Articles (CSV format):[/bold yellow]\n")
                print("ID,Source ID,Title,URL,Published,Authors,Tags,Content Length,Content Hash,Quality Score")
                for article in articles[:5]:
                    quality_score = getattr(article, 'metadata', {}).get('quality_score', 'N/A') if hasattr(article, 'metadata') else 'N/A'
                    print(f"{article.id},{article.source_id},\"{article.title}\",{article.canonical_url},{article.published_at.isoformat() if article.published_at else ''},{', '.join(article.authors) if article.authors else ''},{', '.join(article.tags) if article.tags else ''},{len(article.content)},{article.content_hash},{quality_score}")
        
    except Exception as e:
        console.print(f"❌ [red]Error exporting articles:[/red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
    
    finally:
        try:
            session.close()
            db_manager.engine.dispose()
        except:
            pass

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Export CTI Scraper articles')
    parser.add_argument('--format', choices=['json', 'csv'], default='json', help='Export format')
    parser.add_argument('--output', help='Output file path')
    parser.add_argument('--limit', type=int, default=50, help='Limit number of articles')
    
    args = parser.parse_args()
    
    export_articles(args.format, args.output, args.limit)
