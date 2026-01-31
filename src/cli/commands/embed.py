"""CLI command for embedding generation and management."""

import asyncio
import logging

import click

from ..context import CLIContext

pass_context = click.make_pass_decorator(CLIContext, ensure=True)
from src.services.rag_service import get_rag_service
from src.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@click.command()
@click.option("--batch-size", default=1000, help="Batch size for processing articles")
@click.option("--source-id", type=int, help="Only embed articles from specific source")
@click.option("--dry-run", is_flag=True, help="Show what would be processed without actually embedding")
@pass_context
def embed(ctx: CLIContext, batch_size: int, source_id: int | None, dry_run: bool):
    """Generate embeddings for articles."""

    async def run_embedding():
        """Run the embedding generation process."""
        try:
            rag_service = get_rag_service()

            # Get current embedding coverage
            stats = await rag_service.get_embedding_coverage()

            click.echo(f"Current embedding coverage: {stats['embedding_coverage_percent']}%")
            click.echo(f"Total articles: {stats['total_articles']}")
            click.echo(f"Embedded: {stats['embedded_count']}")
            click.echo(f"Pending: {stats['pending_embeddings']}")

            if stats["pending_embeddings"] == 0:
                click.echo("✅ All articles already have embeddings!")
                return

            if dry_run:
                click.echo(f"🔍 DRY RUN: Would process {stats['pending_embeddings']} articles")
                click.echo(f"   Batch size: {batch_size}")
                if source_id:
                    click.echo(f"   Filter: Source ID {source_id} only")
                return

            # Confirm before proceeding
            if not click.confirm(f"Generate embeddings for {stats['pending_embeddings']} articles?"):
                click.echo("Operation cancelled.")
                return

            # Start retroactive embedding task
            click.echo("🚀 Starting retroactive embedding generation...")

            # Submit the Celery task
            task = celery_app.send_task("src.worker.celery_app.retroactive_embed_all_articles", args=[batch_size])

            click.echo(f"✅ Task submitted: {task.id}")
            click.echo("📊 Monitor progress in Celery logs or web interface")
            click.echo("💡 Use 'celery -A src.worker.celery_app inspect active' to check status")

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            click.echo(f"❌ Error: {e}")
            raise click.Abort()
        finally:
            await rag_service.close()

    # Run the async function
    asyncio.run(run_embedding())


@click.command()
@click.option("--limit", default=10, help="Number of results to return")
@click.option("--threshold", default=0.7, help="Similarity threshold (0.0-1.0)")
@click.option("--source-id", type=int, help="Filter by source ID")
@pass_context
def search_semantic(ctx: CLIContext, limit: int, threshold: float, source_id: int | None):
    """Perform semantic search on articles."""

    query = click.prompt("Enter search query")

    async def run_search():
        """Run the semantic search."""
        try:
            rag_service = get_rag_service()

            # Perform search
            results = await rag_service.find_similar_articles(
                query=query, top_k=limit, threshold=threshold, source_id=source_id
            )

            if not results:
                click.echo("No similar articles found.")
                return

            click.echo(f"\n🔍 Found {len(results)} similar articles:\n")

            for i, result in enumerate(results, 1):
                click.echo(f"{i}. Similarity: {result['similarity']:.3f}")
                click.echo(f"   Source: {result['source_name']}")
                click.echo(f"   Title: {result['title'][:80]}...")
                click.echo(f"   Published: {result['published_at']}")
                click.echo(f"   Content: {result['content'][:200]}...")
                click.echo()

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            click.echo(f"❌ Error: {e}")
            raise click.Abort()
        finally:
            await rag_service.close()

    # Run the async function
    asyncio.run(run_search())


@click.command()
@pass_context
def embedding_stats(ctx: CLIContext):
    """Show embedding statistics and coverage."""

    async def show_stats():
        """Show embedding statistics."""
        try:
            rag_service = get_rag_service()

            stats = await rag_service.get_embedding_coverage()

            click.echo("📊 Embedding Statistics:")
            click.echo(f"   Total articles: {stats['total_articles']}")
            click.echo(f"   Embedded: {stats['embedded_count']}")
            click.echo(f"   Coverage: {stats['embedding_coverage_percent']}%")
            click.echo(f"   Pending: {stats['pending_embeddings']}")

            if stats.get("source_stats"):
                click.echo("\n📈 Source Coverage:")
                for source_stat in stats["source_stats"]:
                    click.echo(
                        f"   {source_stat['source_name']}: {source_stat['embedded_articles']}/{source_stat['total_articles']} ({source_stat['coverage_percent']}%)"
                    )

            if stats["pending_embeddings"] > 0:
                click.echo(
                    f"\n💡 Run 'embed' command to generate embeddings for {stats['pending_embeddings']} articles"
                )

        except Exception as e:
            logger.error(f"Failed to get embedding stats: {e}")
            click.echo(f"❌ Error: {e}")
            raise click.Abort()
        finally:
            await rag_service.close()

    # Run the async function
    asyncio.run(show_stats())


# Create the main embed command group
embed_group = click.Group("embed", help="Embedding management commands")
embed_group.add_command(embed)
embed_group.add_command(search_semantic, name="search")
embed_group.add_command(embedding_stats, name="stats")
