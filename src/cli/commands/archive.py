"""Archive management commands for articles."""

import click
from typing import List, Optional
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from ...database.manager import DatabaseManager
from ...models.article import Article

console = Console()


@click.group()
def archive():
    """Archive management commands."""
    pass


@archive.command()
@click.option('--article-id', type=int, help='Archive specific article by ID')
@click.option('--source-id', type=int, help='Archive all articles from source')
@click.option('--dry-run', is_flag=True, help='Show what would be archived without making changes')
@click.option('--force', is_flag=True, help='Skip confirmation prompts')
def add(article_id: Optional[int], source_id: Optional[int], dry_run: bool, force: bool):
    """Archive articles (soft delete)."""
    db_manager = DatabaseManager()
    
    if not article_id and not source_id:
        console.print("[red]Error: Must specify either --article-id or --source-id[/red]")
        return
    
    try:
        if article_id:
            article = db_manager.get_article(article_id)
            if not article:
                console.print(f"[red]Article {article_id} not found[/red]")
                return
            
            if dry_run:
                console.print(f"[yellow]Would archive article {article_id}: {article.title[:50]}...[/yellow]")
                return
            
            if not force:
                if not Confirm.ask(f"Archive article {article_id}: {article.title[:50]}...?"):
                    return
            
            # Archive the article
            with db_manager.get_session() as session:
                from ...database.models import ArticleTable
                session.query(ArticleTable).filter(ArticleTable.id == article_id).update(
                    {'archived': True}
                )
                session.commit()
            
            console.print(f"[green]✅ Archived article {article_id}[/green]")
        
        elif source_id:
            # Get articles from source
            articles = db_manager.list_articles()
            source_articles = [a for a in articles if a.source_id == source_id]
            
            if not source_articles:
                console.print(f"[yellow]No articles found for source {source_id}[/yellow]")
                return
            
            if dry_run:
                console.print(f"[yellow]Would archive {len(source_articles)} articles from source {source_id}[/yellow]")
                return
            
            if not force:
                if not Confirm.ask(f"Archive {len(source_articles)} articles from source {source_id}?"):
                    return
            
            # Archive all articles from source
            with db_manager.get_session() as session:
                from ...database.models import ArticleTable
                session.query(ArticleTable).filter(ArticleTable.source_id == source_id).update(
                    {'archived': True}
                )
                session.commit()
            
            console.print(f"[green]✅ Archived {len(source_articles)} articles from source {source_id}[/green]")
    
    except Exception as e:
        console.print(f"[red]Error archiving articles: {e}[/red]")


@archive.command()
@click.option('--article-id', type=int, help='Unarchive specific article by ID')
@click.option('--source-id', type=int, help='Unarchive all articles from source')
@click.option('--dry-run', is_flag=True, help='Show what would be unarchived without making changes')
@click.option('--force', is_flag=True, help='Skip confirmation prompts')
def remove(article_id: Optional[int], source_id: Optional[int], dry_run: bool, force: bool):
    """Unarchive articles (restore from soft delete)."""
    db_manager = DatabaseManager()
    
    if not article_id and not source_id:
        console.print("[red]Error: Must specify either --article-id or --source-id[/red]")
        return
    
    try:
        if article_id:
            # Get archived article
            with db_manager.get_session() as session:
                from ...database.models import ArticleTable
                article = session.query(ArticleTable).filter(
                    ArticleTable.id == article_id,
                    ArticleTable.archived == True
                ).first()
                
                if not article:
                    console.print(f"[red]Archived article {article_id} not found[/red]")
                    return
                
                if dry_run:
                    console.print(f"[yellow]Would unarchive article {article_id}: {article.title[:50]}...[/yellow]")
                    return
                
                if not force:
                    if not Confirm.ask(f"Unarchive article {article_id}: {article.title[:50]}...?"):
                        return
                
                # Unarchive the article
                session.query(ArticleTable).filter(ArticleTable.id == article_id).update(
                    {'archived': False}
                )
                session.commit()
            
            console.print(f"[green]✅ Unarchived article {article_id}[/green]")
        
        elif source_id:
            # Get archived articles from source
            with db_manager.get_session() as session:
                from ...database.models import ArticleTable
                archived_articles = session.query(ArticleTable).filter(
                    ArticleTable.source_id == source_id,
                    ArticleTable.archived == True
                ).all()
                
                if not archived_articles:
                    console.print(f"[yellow]No archived articles found for source {source_id}[/yellow]")
                    return
                
                if dry_run:
                    console.print(f"[yellow]Would unarchive {len(archived_articles)} articles from source {source_id}[/yellow]")
                    return
                
                if not force:
                    if not Confirm.ask(f"Unarchive {len(archived_articles)} articles from source {source_id}?"):
                        return
                
                # Unarchive all articles from source
                session.query(ArticleTable).filter(ArticleTable.source_id == source_id).update(
                    {'archived': False}
                )
                session.commit()
            
            console.print(f"[green]✅ Unarchived {len(archived_articles)} articles from source {source_id}[/green]")
    
    except Exception as e:
        console.print(f"[red]Error unarchiving articles: {e}[/red]")


@archive.command()
@click.option('--limit', type=int, default=50, help='Number of archived articles to show')
def list(limit: int):
    """List archived articles."""
    db_manager = DatabaseManager()
    
    try:
        with db_manager.get_session() as session:
            from ...database.models import ArticleTable
            archived_articles = session.query(ArticleTable).filter(
                ArticleTable.archived == True
            ).order_by(ArticleTable.updated_at.desc()).limit(limit).all()
            
            if not archived_articles:
                console.print("[yellow]No archived articles found[/yellow]")
                return
            
            table = Table(title=f"Archived Articles (showing {len(archived_articles)})")
            table.add_column("ID", style="cyan")
            table.add_column("Title", style="white")
            table.add_column("Source ID", style="green")
            table.add_column("Archived At", style="yellow")
            
            for article in archived_articles:
                table.add_row(
                    str(article.id),
                    article.title[:60] + "..." if len(article.title) > 60 else article.title,
                    str(article.source_id),
                    article.updated_at.strftime("%Y-%m-%d %H:%M")
                )
            
            console.print(table)
    
    except Exception as e:
        console.print(f"[red]Error listing archived articles: {e}[/red]")


@archive.command()
@click.option('--force', is_flag=True, help='Skip confirmation prompt')
def cleanup(force: bool):
    """Show statistics about archived articles."""
    db_manager = DatabaseManager()
    
    try:
        with db_manager.get_session() as session:
            from ...database.models import ArticleTable
            total_articles = session.query(ArticleTable).count()
            archived_count = session.query(ArticleTable).filter(ArticleTable.archived == True).count()
            active_count = total_articles - archived_count
            
            console.print(f"[blue]Article Statistics:[/blue]")
            console.print(f"  Total articles: {total_articles}")
            console.print(f"  Active articles: {active_count}")
            console.print(f"  Archived articles: {archived_count}")
            console.print(f"  Archive percentage: {(archived_count/total_articles*100):.1f}%" if total_articles > 0 else "  Archive percentage: 0%")
    
    except Exception as e:
        console.print(f"[red]Error getting archive statistics: {e}[/red]")
