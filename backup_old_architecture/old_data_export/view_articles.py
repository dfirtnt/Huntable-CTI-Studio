#!/usr/bin/env python3
"""
Quick article viewer for the CTI Scraper database.
"""
import sys
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

# Add src to path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from database.manager import DatabaseManager
from models.source import SourceFilter
from models.article import Article

console = Console()

def view_articles():
    """View collected articles with rich formatting."""
    
    # Initialize database
    db_manager = DatabaseManager()
    db_manager.create_tables()  # Ensure tables exist
    
    console.print("\n🔍 [bold blue]Viewing Collected Articles[/bold blue]\n")
    
    try:
        with db_manager.get_session() as session:
            # Get article count
            total_articles = db_manager.count_articles(session)
            console.print(f"📊 [green]Total Articles in Database:[/green] {total_articles}")
            
            if total_articles == 0:
                console.print("❌ [red]No articles found in database[/red]")
                console.print("💡 [yellow]Run a collection first with:[/yellow] ./threat-intel collect")
                return
            
            # Get sources
            sources = db_manager.get_sources(session, SourceFilter())
            console.print(f"📡 [green]Active Sources:[/green] {len([s for s in sources if s.active])}")
            
            # Show recent articles (last 7 days)
            recent_cutoff = datetime.utcnow() - timedelta(days=7)
            recent_articles = db_manager.get_articles(
                session, 
                limit=20,
                order_by="discovered_at"
            )
            
            if recent_articles:
                console.print(f"\n📰 [bold yellow]Recent Articles (Last 20):[/bold yellow]\n")
                
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("ID", style="dim", width=6)
                table.add_column("Source", style="cyan", width=15)
                table.add_column("Title", style="white", width=50)
                table.add_column("Published", style="green", width=12)
                table.add_column("Quality", style="yellow", width=8)
                table.add_column("Content Size", style="blue", width=12)
                
                # Get source names mapping
                source_map = {s.id: s.name for s in sources}
                
                for article in recent_articles:
                    # Truncate title if too long
                    title = article.title[:47] + "..." if len(article.title) > 50 else article.title
                    source_name = source_map.get(article.source_id, "Unknown")[:12]
                    
                    # Format published date
                    pub_date = article.published_at.strftime("%m/%d/%Y") if article.published_at else "Unknown"
                    
                    # Get quality score
                    quality = article.metadata.get('quality_score', 0.0) if hasattr(article, 'metadata') and article.metadata else 0.0
                    quality_str = f"{quality:.2f}"
                    
                    # Content size
                    content_size = f"{len(article.content):,} chars"
                    
                    table.add_row(
                        str(article.id),
                        source_name,
                        title,
                        pub_date,
                        quality_str,
                        content_size
                    )
                
                console.print(table)
                
                # Show sample article details
                if recent_articles:
                    sample = recent_articles[0]
                    console.print(f"\n📄 [bold green]Sample Article Details:[/bold green]\n")
                    
                    panel_content = f"""
[bold]Title:[/bold] {sample.title}
[bold]URL:[/bold] {sample.canonical_url}
[bold]Published:[/bold] {sample.published_at}
[bold]Authors:[/bold] {', '.join(sample.authors) if sample.authors else 'Unknown'}
[bold]Tags:[/bold] {', '.join(sample.tags[:5]) if sample.tags else 'None'}
[bold]Content Hash:[/bold] {sample.content_hash[:16]}...
[bold]Content Preview:[/bold] {sample.content[:200]}...
                    """
                    
                    console.print(Panel(panel_content, title="Article Sample", border_style="blue"))
            
            # Show source statistics
            console.print(f"\n📊 [bold yellow]Source Statistics:[/bold yellow]\n")
            
            source_table = Table(show_header=True, header_style="bold magenta")
            source_table.add_column("Source", style="cyan", width=25)
            source_table.add_column("Articles", style="green", width=10)
            source_table.add_column("Active", style="yellow", width=8)
            source_table.add_column("URL", style="blue", width=40)
            
            for source in sources:
                # Count articles for this source
                source_articles = db_manager.get_articles(
                    session,
                    source_id=source.id
                )
                article_count = len(source_articles) if source_articles else 0
                
                active_status = "✅ Yes" if source.active else "❌ No"
                url_display = source.url[:37] + "..." if len(source.url) > 40 else source.url
                
                source_table.add_row(
                    source.name,
                    str(article_count),
                    active_status,
                    url_display
                )
            
            console.print(source_table)
            
            # Export suggestions
            console.print(f"\n💡 [bold yellow]Export Options:[/bold yellow]")
            console.print("📄 JSON Export: [cyan]./threat-intel export --format json --output articles.json[/cyan]")
            console.print("📊 CSV Export:  [cyan]./threat-intel export --format csv --output articles.csv[/cyan]")
            console.print("🔍 Last 3 days: [cyan]./threat-intel export --days 3 --format json[/cyan]")
            console.print("🎯 Specific source: [cyan]./threat-intel export --source crowdstrike_blog --format csv[/cyan]")
            
    except Exception as e:
        console.print(f"❌ [red]Error viewing articles:[/red] {e}")
    
    finally:
        # Close database connections
        db_manager.engine.dispose()

if __name__ == "__main__":
    view_articles()
