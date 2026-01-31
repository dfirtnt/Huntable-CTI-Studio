"""
CLI commands for Sigma rule management and matching.
"""

import logging

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from sqlalchemy import Float, cast

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable, SigmaRuleTable
from src.services.sigma_coverage_service import SigmaCoverageService
from src.services.sigma_matching_service import SigmaMatchingService
from src.services.sigma_sync_service import SigmaSyncService

logger = logging.getLogger(__name__)
console = Console()


@click.group(name="sigma")
def sigma_group():
    """Sigma rule management and matching commands."""
    pass


@sigma_group.command("sync")
@click.option("--force", is_flag=True, help="Force re-clone of repository")
def sync_repo(force: bool):
    """Sync Sigma rules repository."""
    console.print("[bold blue]Syncing Sigma rules repository...[/bold blue]")

    try:
        db_manager = DatabaseManager()
        session = db_manager.get_session()

        sync_service = SigmaSyncService()

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Syncing repository...", total=None)

            # Clone or pull repository
            result = sync_service.clone_or_pull_repository()

            if not result["success"]:
                console.print(f"[bold red]✗[/bold red] Failed: {result.get('error')}")
                return

            console.print(f"[bold green]✓[/bold green] Repository {result['action']}")
            progress.update(task, description="Complete")

        session.close()

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Sync failed: {e}")


@sigma_group.command("index")
@click.option("--force", is_flag=True, help="Force re-index all rules")
def index_rules(force: bool):
    """Index Sigma rules into database."""
    console.print("[bold blue]Indexing Sigma rules...[/bold blue]")

    try:
        db_manager = DatabaseManager()
        session = db_manager.get_session()

        sync_service = SigmaSyncService()

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Indexing rules...", total=None)

            indexed_count = sync_service.index_rules(session, force_reindex=force)

            progress.update(task, description=f"Indexed {indexed_count} rules")

        console.print(f"[bold green]✓[/bold green] Successfully indexed {indexed_count} rules")

        session.close()

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Indexing failed: {e}")


@sigma_group.command("match")
@click.argument("article_id", type=int)
@click.option("--threshold", default=0.7, help="Similarity threshold (0-1)")
@click.option("--save", is_flag=True, help="Save matches to database")
def match_article(article_id: int, threshold: float, save: bool):
    """Match a single article to Sigma rules."""
    console.print(f"[bold blue]Matching article {article_id} to Sigma rules...[/bold blue]")

    try:
        db_manager = DatabaseManager()
        session = db_manager.get_session()

        matching_service = SigmaMatchingService(session)
        coverage_service = SigmaCoverageService(session)

        # Match at article level
        article_matches = matching_service.match_article_to_rules(article_id, threshold=threshold)

        # Match at chunk level
        chunk_matches = matching_service.match_chunks_to_rules(article_id, threshold=threshold)

        # Combine and deduplicate
        all_matches = {}
        for match in article_matches + chunk_matches:
            rule_id = match["rule_id"]
            if rule_id not in all_matches or match["similarity"] > all_matches[rule_id]["similarity"]:
                all_matches[rule_id] = match

        if not all_matches:
            console.print("[yellow]No matching rules found[/yellow]")
            session.close()
            return

        # Display results
        table = Table(title=f"Matches for Article {article_id}")
        table.add_column("Rule ID", style="cyan")
        table.add_column("Title", style="green")
        table.add_column("Similarity", style="magenta")
        table.add_column("Level", style="yellow")
        table.add_column("Coverage", style="blue")

        for match in sorted(all_matches.values(), key=lambda x: x["similarity"], reverse=True)[:10]:
            # Classify coverage
            rule = session.query(SigmaRuleTable).filter_by(rule_id=match["rule_id"]).first()
            if rule:
                classification = coverage_service.classify_match(article_id, rule, match["similarity"])

                coverage_status = classification["coverage_status"]

                # Save if requested
                if save:
                    match_level = "chunk" if "chunk_id" in match else "article"
                    matching_service.store_match(
                        article_id=article_id,
                        sigma_rule_id=rule.id,
                        similarity_score=match["similarity"],
                        match_level=match_level,
                        chunk_id=match.get("chunk_id"),
                        coverage_status=coverage_status,
                        coverage_confidence=classification["coverage_confidence"],
                        coverage_reasoning=classification["coverage_reasoning"],
                        matched_discriminators=classification["matched_discriminators"],
                        matched_lolbas=classification["matched_lolbas"],
                        matched_intelligence=classification["matched_intelligence"],
                    )
            else:
                coverage_status = "unknown"

            table.add_row(
                match["rule_id"][:16],
                match["title"][:40],
                f"{match['similarity']:.3f}",
                match.get("level", "N/A"),
                coverage_status,
            )

        console.print(table)

        if save:
            console.print(f"[bold green]✓[/bold green] Saved {len(all_matches)} matches to database")

        session.close()

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Matching failed: {e}")


@sigma_group.command("match-all")
@click.option("--threshold", default=0.7, help="Similarity threshold (0-1)")
@click.option("--limit", default=None, type=int, help="Limit number of articles to process")
@click.option("--min-hunt-score", default=50, type=int, help="Minimum hunt score")
def match_all_articles(threshold: float, limit: int | None, min_hunt_score: int):
    """Match all articles to Sigma rules."""
    console.print("[bold blue]Matching all articles to Sigma rules...[/bold blue]")

    try:
        db_manager = DatabaseManager()
        session = db_manager.get_session()

        matching_service = SigmaMatchingService(session)
        coverage_service = SigmaCoverageService(session)

        # Get articles with embeddings and high hunt scores
        query = session.query(ArticleTable).filter(ArticleTable.embedding.isnot(None))

        # Filter by hunt score if specified
        query = query.filter(
            cast(ArticleTable.article_metadata["threat_hunting_score"].op("->>")("text"), Float) >= min_hunt_score
        )

        if limit:
            query = query.limit(limit)

        articles = query.all()

        console.print(f"Processing {len(articles)} articles...")

        matched_count = 0
        total_matches = 0

        with Progress(console=console) as progress:
            task = progress.add_task("Matching articles...", total=len(articles))

            for article in articles:
                try:
                    # Match article
                    article_matches = matching_service.match_article_to_rules(article.id, threshold=threshold, limit=5)

                    if article_matches:
                        matched_count += 1
                        total_matches += len(article_matches)

                        # Store matches with coverage classification
                        for match in article_matches:
                            rule = session.query(SigmaRuleTable).filter_by(rule_id=match["rule_id"]).first()

                            if rule:
                                classification = coverage_service.classify_match(article.id, rule, match["similarity"])

                                matching_service.store_match(
                                    article_id=article.id,
                                    sigma_rule_id=rule.id,
                                    similarity_score=match["similarity"],
                                    match_level="article",
                                    coverage_status=classification["coverage_status"],
                                    coverage_confidence=classification["coverage_confidence"],
                                    coverage_reasoning=classification["coverage_reasoning"],
                                    matched_discriminators=classification["matched_discriminators"],
                                    matched_lolbas=classification["matched_lolbas"],
                                    matched_intelligence=classification["matched_intelligence"],
                                )

                    progress.update(task, advance=1)

                except Exception as e:
                    logger.error(f"Error matching article {article.id}: {e}")
                    progress.update(task, advance=1)
                    continue

        console.print(f"[bold green]✓[/bold green] Matched {matched_count}/{len(articles)} articles")
        console.print(f"[bold green]✓[/bold green] Total {total_matches} matches stored")

        session.close()

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Batch matching failed: {e}")


@sigma_group.command("stats")
def show_stats():
    """Show Sigma rule index statistics."""
    try:
        db_manager = DatabaseManager()
        session = db_manager.get_session()

        # Count total rules
        total_rules = session.query(SigmaRuleTable).count()

        # Count rules with embeddings
        embedded_rules = session.query(SigmaRuleTable).filter(SigmaRuleTable.embedding.isnot(None)).count()

        # Count by status
        from sqlalchemy import func

        status_counts = (
            session.query(SigmaRuleTable.status, func.count(SigmaRuleTable.id)).group_by(SigmaRuleTable.status).all()
        )

        # Count by level
        level_counts = (
            session.query(SigmaRuleTable.level, func.count(SigmaRuleTable.id)).group_by(SigmaRuleTable.level).all()
        )

        # Count matches
        from src.database.models import ArticleSigmaMatchTable

        total_matches = session.query(ArticleSigmaMatchTable).count()

        # Display statistics
        table = Table(title="Sigma Rule Index Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green")

        table.add_row("Total Rules", str(total_rules))
        table.add_row("Rules with Embeddings", str(embedded_rules))
        table.add_row("Total Matches", str(total_matches))

        console.print(table)

        # Status breakdown
        if status_counts:
            status_table = Table(title="Rules by Status")
            status_table.add_column("Status", style="cyan")
            status_table.add_column("Count", style="green")

            for status, count in status_counts:
                status_table.add_row(status or "Unknown", str(count))

            console.print(status_table)

        # Level breakdown
        if level_counts:
            level_table = Table(title="Rules by Level")
            level_table.add_column("Level", style="cyan")
            level_table.add_column("Count", style="green")

            for level, count in level_counts:
                level_table.add_row(level or "Unknown", str(count))

            console.print(level_table)

        session.close()

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Stats failed: {e}")
