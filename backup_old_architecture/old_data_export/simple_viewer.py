#!/usr/bin/env python3
"""
Simple article viewer for the CTI Scraper database.
"""
import sys
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Add src to path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from database.manager import DatabaseManager
from models.source import SourceFilter
from models.article import ArticleFilter

console = Console()

def view_articles():
    """View collected articles with rich formatting."""
    
    # Initialize database
    db_manager = DatabaseManager()
    db_manager.create_tables()  # Ensure tables exist
    
    console.print("\n🔍 [bold blue]CTI Scraper - Collected Articles[/bold blue]\n")
    
    try:
        session = db_manager.get_session()
        
        # Get sources first
        sources = db_manager.list_sources()
        console.print(f"📡 [green]Total Sources Configured:[/green] {len(sources)}")
        active_sources = [s for s in sources if s.active]
        console.print(f"📡 [green]Active Sources:[/green] {len(active_sources)}")
        
        # Get all articles
        articles = db_manager.list_articles()
        console.print(f"📊 [green]Total Articles in Database:[/green] {len(articles)}")
        
        if len(articles) == 0:
            console.print("\n❌ [red]No articles found in database[/red]")
            console.print("💡 [yellow]Run a collection first with:[/yellow] ./threat-intel collect")
            
            # Show available sources
            if sources:
                console.print(f"\n📡 [bold yellow]Available Sources to Collect From:[/bold yellow]\n")
                
                source_table = Table(show_header=True, header_style="bold magenta")
                source_table.add_column("ID", style="dim", width=15)
                source_table.add_column("Name", style="cyan", width=25)
                source_table.add_column("Active", style="yellow", width=8)
                source_table.add_column("URL", style="blue", width=50)
                
                for source in sources:
                    active_status = "✅ Yes" if source.active else "❌ No"
                    source_table.add_row(
                        source.id,
                        source.name,
                        active_status,
                        source.url
                    )
                
                console.print(source_table)
            
            return
        
        # Show recent articles
        # Sort by discovered_at if available, otherwise by id
        recent_articles = sorted(articles, key=lambda x: x.discovered_at if hasattr(x, 'discovered_at') and x.discovered_at else datetime.min, reverse=True)[:20]
        
        console.print(f"\n📰 [bold yellow]Recent Articles (Last {len(recent_articles)}):[/bold yellow]\n")
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim", width=6)
        table.add_column("Source", style="cyan", width=15)
        table.add_column("Title", style="white", width=45)
        table.add_column("Published", style="green", width=12)
        table.add_column("Content Size", style="blue", width=12)
        
        # Create source name mapping
        source_map = {s.id: s.name for s in sources}
        
        for article in recent_articles:
            # Truncate title if too long
            title = article.title[:42] + "..." if len(article.title) > 45 else article.title
            source_name = source_map.get(str(article.source_id), "Unknown")[:12]
            
            # Format published date
            pub_date = article.published_at.strftime("%m/%d/%Y") if article.published_at else "Unknown"
            
            # Content size
            content_size = f"{len(article.content):,} chars"
            
            table.add_row(
                str(article.id),
                source_name,
                title,
                pub_date,
                content_size
            )
        
        console.print(table)
        
        # Show sample article details
        if recent_articles:
            sample = recent_articles[0]
            console.print(f"\n📄 [bold green]Sample Article Details:[/bold green]\n")
            
            metadata_info = ""
            if hasattr(sample, 'metadata') and sample.metadata:
                quality = sample.metadata.get('quality_score', 'N/A')
                metadata_info = f"\n[bold]Quality Score:[/bold] {quality}"
            
            panel_content = f"""
[bold]Title:[/bold] {sample.title}
[bold]URL:[/bold] {sample.canonical_url}
[bold]Published:[/bold] {sample.published_at}
[bold]Authors:[/bold] {', '.join(sample.authors) if sample.authors else 'Unknown'}
[bold]Tags:[/bold] {', '.join(sample.tags[:5]) if sample.tags else 'None'}
[bold]Content Hash:[/bold] {sample.content_hash[:16]}...{metadata_info}
[bold]Content Preview:[/bold] {sample.content[:200]}...
            """
            
            console.print(Panel(panel_content, title="Latest Article Sample", border_style="blue"))
        
        # Show source statistics
        console.print(f"\n📊 [bold yellow]Source Statistics:[/bold yellow]\n")
        
        source_table = Table(show_header=True, header_style="bold magenta")
        source_table.add_column("Source", style="cyan", width=25)
        source_table.add_column("Articles", style="green", width=10)
        source_table.add_column("Active", style="yellow", width=8)
        source_table.add_column("URL", style="blue", width=40)
        
        for source in sources:
            # Count articles for this source
            source_articles = [a for a in articles if str(a.source_id) == source.id]
            article_count = len(source_articles)
            
            active_status = "✅ Yes" if source.active else "❌ No"
            url_display = source.url[:37] + "..." if len(source.url) > 40 else source.url
            
            source_table.add_row(
                source.name,
                str(article_count),
                active_status,
                url_display
            )
        
        console.print(source_table)
        
        # Get database stats
        stats = db_manager.get_database_stats()
        console.print(f"\n📈 [bold yellow]Database Statistics:[/bold yellow]")
        for key, value in stats.items():
            console.print(f"   {key}: [cyan]{value}[/cyan]")
        
        # Export suggestions
        console.print(f"\n💡 [bold yellow]Export Options:[/bold yellow]")
        console.print("📄 JSON Export: [cyan]./threat-intel export --format json --output articles.json[/cyan]")
        console.print("📊 CSV Export:  [cyan]./threat-intel export --format csv --output articles.csv[/cyan]")
        console.print("🔍 Last 3 days: [cyan]./threat-intel export --days 3 --format json[/cyan]")
        console.print("🎯 Specific source: [cyan]./threat-intel export --source crowdstrike_blog --format csv[/cyan]")
        
    except Exception as e:
        console.print(f"❌ [red]Error viewing articles:[/red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
    
    finally:
        # Close database connections
        try:
            session.close()
            db_manager.engine.dispose()
        except:
            pass

if __name__ == "__main__":
    view_articles()
