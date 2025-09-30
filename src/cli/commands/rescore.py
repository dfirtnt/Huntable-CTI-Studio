"""Rescore command for CLI."""

import asyncio
import sys
import os
from pathlib import Path
import click
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ..context import CLIContext, get_managers
from ..utils import console
from src.core.processor import ContentProcessor
from src.models.article import ArticleCreate

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.command()
@click.option('--article-id', type=int, help='Rescore specific article by ID')
@click.option('--force', is_flag=True, help='Force rescore even if score exists')
@click.option('--dry-run', is_flag=True, help='Show what would be rescored without saving')
@pass_context
def rescore(ctx: CLIContext, article_id: int, force: bool, dry_run: bool):
    """Rescore threat hunting scores for articles."""
    
    async def _rescore():
        db_manager, _, _ = await get_managers(ctx)
        
        try:
            if article_id:
                # Rescore specific article
                console.print(f"🔄 Rescoring article {article_id}...")
                
                article = await db_manager.get_article(article_id)
                if not article:
                    console.print(f"❌ Article {article_id} not found", style="red")
                    return
                
                if not force and article.article_metadata and 'threat_hunting_score' in article.article_metadata:
                    console.print(f"⚠️  Article {article_id} already has a score. Use --force to override.", style="yellow")
                    return
                
                # Create processor
                processor = ContentProcessor(enable_content_enhancement=True)
                
                # Create ArticleCreate object for processing
                article_create = ArticleCreate(
                    source_id=article.source_id,
                    canonical_url=article.canonical_url,
                    title=article.title,
                    content=article.content,
                    published_at=article.published_at,
                    article_metadata=article.article_metadata or {}
                )
                
                # Regenerate threat hunting score
                enhanced_metadata = await processor._enhance_metadata(article_create)
                
                if 'threat_hunting_score' in enhanced_metadata:
                    new_score = enhanced_metadata['threat_hunting_score']
                    console.print(f"✅ New threat hunting score: {new_score}", style="green")
                    
                    if not dry_run:
                        # Update the article in database
                        if not article.article_metadata:
                            article.article_metadata = {}
                        
                        # Update threat hunting score and keyword matches
                        article.article_metadata['threat_hunting_score'] = enhanced_metadata['threat_hunting_score']
                        article.article_metadata['perfect_keyword_matches'] = enhanced_metadata.get('perfect_keyword_matches', [])
                        article.article_metadata['good_keyword_matches'] = enhanced_metadata.get('good_keyword_matches', [])
                        article.article_metadata['lolbas_matches'] = enhanced_metadata.get('lolbas_matches', [])
                        
                        # Save the updated article
                        await db_manager.update_article(article.id, article)
                        console.print(f"✅ Article {article_id} updated successfully", style="green")
                    else:
                        console.print("🔍 Dry run - no changes saved", style="blue")
                else:
                    console.print("❌ No threat hunting score generated", style="red")
            else:
                # Rescore all articles
                console.print("🔄 Rescoring all articles...")
                
                articles = await db_manager.list_articles()
                total_articles = len(articles)
                
                if total_articles == 0:
                    console.print("ℹ️  No articles found to rescore", style="blue")
                    return
                
                # Filter articles to rescore
                if force:
                    articles_to_rescore = articles
                    console.print(f"🔄 Force rescoring all {total_articles} articles...")
                else:
                    articles_to_rescore = [
                        a for a in articles 
                        if not a.article_metadata or 'threat_hunting_score' not in a.article_metadata
                    ]
                    console.print(f"🔄 Rescoring {len(articles_to_rescore)} articles missing scores...")
                
                if not articles_to_rescore:
                    console.print("✅ All articles already have scores", style="green")
                    return
                
                # Create processor
                processor = ContentProcessor(enable_content_enhancement=True)
                
                success_count = 0
                error_count = 0
                
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console
                ) as progress:
                    task = progress.add_task("Rescoring articles...", total=len(articles_to_rescore))
                    
                    for i, article in enumerate(articles_to_rescore, 1):
                        try:
                            # Create ArticleCreate object for processing
                            article_create = ArticleCreate(
                                source_id=article.source_id,
                                canonical_url=article.canonical_url,
                                title=article.title,
                                content=article.content,
                                published_at=article.published_at,
                                article_metadata=article.article_metadata or {}
                            )
                            
                            # Regenerate threat hunting score
                            enhanced_metadata = await processor._enhance_metadata(article_create)
                            
                            if 'threat_hunting_score' in enhanced_metadata:
                                if not dry_run:
                                    # Update the article in database
                                    if not article.article_metadata:
                                        article.article_metadata = {}
                                    
                                    # Update threat hunting score and keyword matches
                                    article.article_metadata['threat_hunting_score'] = enhanced_metadata['threat_hunting_score']
                                    article.article_metadata['perfect_keyword_matches'] = enhanced_metadata.get('perfect_keyword_matches', [])
                                    article.article_metadata['good_keyword_matches'] = enhanced_metadata.get('good_keyword_matches', [])
                                    article.article_metadata['lolbas_matches'] = enhanced_metadata.get('lolbas_matches', [])
                                    
                                    # Save the updated article
                                    await db_manager.update_article(article.id, article)
                                
                                success_count += 1
                            else:
                                error_count += 1
                            
                            progress.update(task, advance=1, description=f"Processed {i}/{len(articles_to_rescore)} articles")
                            
                        except Exception as e:
                            console.print(f"❌ Error processing article {article.id}: {e}", style="red")
                            error_count += 1
                            progress.update(task, advance=1)
                
                # Final summary
                console.print("\n" + "=" * 60)
                console.print("RESCORING COMPLETE!", style="bold green")
                console.print(f"Successfully updated: {success_count} articles", style="green")
                console.print(f"Errors: {error_count} articles", style="red" if error_count > 0 else "green")
                console.print(f"Total processed: {success_count + error_count} articles")
                
                if dry_run:
                    console.print("🔍 Dry run - no changes saved", style="blue")
                
                # Verify results
                if not dry_run:
                    console.print("\nVerifying results...")
                    updated_articles = await db_manager.list_articles()
                    articles_with_score = sum(
                        1 for a in updated_articles 
                        if a.article_metadata and 'threat_hunting_score' in a.article_metadata
                    )
                    console.print(f"Articles with threat hunting scores: {articles_with_score}/{len(updated_articles)} ({articles_with_score/len(updated_articles)*100:.1f}%)")
        
        except Exception as e:
            console.print(f"❌ Fatal error: {e}", style="red")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    asyncio.run(_rescore())
