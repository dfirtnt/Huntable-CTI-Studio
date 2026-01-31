"""Rescore ML hunt scores command for CLI."""

import sys

import click
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from src.database.manager import DatabaseManager
from src.services.chunk_analysis_service import ChunkAnalysisService

from ..context import CLIContext
from ..utils import console

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.command()
@click.option("--article-id", type=int, help="Recalculate ML hunt score for specific article by ID")
@click.option("--force", is_flag=True, help="Force recalculation even if score exists")
@click.option("--dry-run", is_flag=True, help="Show what would be recalculated without saving")
@click.option(
    "--metric",
    type=click.Choice(
        ["weighted_average", "proportion_weighted", "confidence_sum_normalized", "top_percentile", "user_proposed"],
        case_sensitive=False,
    ),
    default="weighted_average",
    help="Metric calculation method (default: weighted_average)",
)
@click.option("--model-version", type=str, help="Filter by specific model version (uses latest if not specified)")
@pass_context
def rescore_ml(ctx: CLIContext, article_id: int, force: bool, dry_run: bool, metric: str, model_version: str):
    """Recalculate ML-based hunt scores for articles from chunk analysis results."""

    def _rescore_ml():
        db_manager = DatabaseManager()
        db = db_manager.get_session()

        try:
            service = ChunkAnalysisService(db)

            if article_id:
                # Recalculate for specific article
                console.print(f"🔄 Recalculating ML hunt score for article {article_id}...")

                from src.database.models import ArticleTable

                article = db.query(ArticleTable).filter(ArticleTable.id == article_id).first()

                if not article:
                    console.print(f"❌ Article {article_id} not found", style="red")
                    return

                if not force and article.article_metadata and "ml_hunt_score" in article.article_metadata:
                    console.print(
                        f"⚠️  Article {article_id} already has an ML hunt score. Use --force to override.",
                        style="yellow",
                    )
                    return

                # Calculate ML hunt score
                score_result = service.calculate_ml_hunt_score(article_id, model_version=model_version, metric=metric)

                if not score_result:
                    console.print(f"❌ No chunk analysis results found for article {article_id}", style="red")
                    console.print(
                        "   ML hunt scores require chunk analysis results. Run chunk analysis first.", style="yellow"
                    )
                    return

                console.print(f"✅ ML Hunt Score: {score_result['ml_hunt_score']:.2f}", style="green")
                console.print(f"   Metric: {score_result['metric']}")
                console.print(f"   Total Chunks: {score_result['total_chunks']}")
                console.print(
                    f"   Huntable Chunks: {score_result['huntable_chunks']} ({score_result['huntable_proportion'] * 100:.1f}%)"
                )
                console.print(f"   Avg Confidence: {score_result['avg_confidence']:.3f}")

                if not dry_run:
                    if service.update_article_ml_hunt_score(article_id, metric=metric, model_version=model_version):
                        console.print(f"✅ Article {article_id} updated successfully", style="green")
                    else:
                        console.print(f"❌ Failed to update article {article_id}", style="red")
                else:
                    console.print("🔍 Dry run - no changes saved", style="blue")
            else:
                # Recalculate for all articles with chunk analysis
                console.print("🔄 Recalculating ML hunt scores for all articles with chunk analysis...")

                from src.database.models import ArticleTable, ChunkAnalysisResultTable

                # Get all articles that have chunk analysis results
                articles_with_chunks_subq = db.query(ChunkAnalysisResultTable.article_id).distinct().subquery()
                article_ids = [row[0] for row in db.query(articles_with_chunks_subq.c.article_id).all()]

                if not article_ids:
                    console.print("ℹ️  No articles with chunk analysis results found", style="blue")
                    return

                articles = db.query(ArticleTable).filter(ArticleTable.id.in_(article_ids)).all()

                total_articles = len(articles)

                if total_articles == 0:
                    console.print("ℹ️  No articles with chunk analysis results found", style="blue")
                    return

                # Filter articles to recalculate
                if force:
                    articles_to_recalculate = articles
                    console.print(f"🔄 Force recalculating ML hunt scores for {total_articles} articles...")
                else:
                    articles_to_recalculate = [
                        a for a in articles if not a.article_metadata or "ml_hunt_score" not in a.article_metadata
                    ]
                    console.print(
                        f"🔄 Recalculating ML hunt scores for {len(articles_to_recalculate)} articles missing scores..."
                    )

                if not articles_to_recalculate:
                    console.print("✅ All articles already have ML hunt scores", style="green")
                    return

                success_count = 0
                error_count = 0
                skipped_count = 0

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task("Recalculating ML hunt scores...", total=len(articles_to_recalculate))

                    for i, article in enumerate(articles_to_recalculate, 1):
                        try:
                            # Calculate ML hunt score
                            score_result = service.calculate_ml_hunt_score(
                                article.id, model_version=model_version, metric=metric
                            )

                            if not score_result:
                                skipped_count += 1
                                progress.update(
                                    task,
                                    advance=1,
                                    description=f"Processed {i}/{len(articles_to_recalculate)} (skipped: {skipped_count})",
                                )
                                continue

                            if not dry_run:
                                if service.update_article_ml_hunt_score(
                                    article.id, metric=metric, model_version=model_version
                                ):
                                    success_count += 1
                                else:
                                    error_count += 1
                            else:
                                success_count += 1  # Count as success in dry-run

                            progress.update(
                                task, advance=1, description=f"Processed {i}/{len(articles_to_recalculate)}"
                            )

                        except Exception as e:
                            console.print(f"❌ Error processing article {article.id}: {e}", style="red")
                            error_count += 1
                            progress.update(task, advance=1)

                # Final summary
                console.print("\n" + "=" * 60)
                console.print("ML HUNT SCORE RECALCULATION COMPLETE!", style="bold green")
                console.print(f"Successfully updated: {success_count} articles", style="green")
                if skipped_count > 0:
                    console.print(f"Skipped (no chunks): {skipped_count} articles", style="yellow")
                console.print(f"Errors: {error_count} articles", style="red" if error_count > 0 else "green")
                console.print(f"Total processed: {success_count + error_count + skipped_count} articles")

                if dry_run:
                    console.print("🔍 Dry run - no changes saved", style="blue")

        except Exception as e:
            console.print(f"❌ Fatal error: {e}", style="red")
            import traceback

            traceback.print_exc()
            sys.exit(1)
        finally:
            db.close()

    _rescore_ml()
