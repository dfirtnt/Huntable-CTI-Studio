"""
CLI commands for Sigma rule management and matching.
"""

import logging

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.database.manager import DatabaseManager
from src.database.models import SigmaRuleTable
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
    """Index Sigma rules into database (metadata + embeddings)."""
    console.print("[bold blue]Indexing Sigma rules...[/bold blue]")

    try:
        db_manager = DatabaseManager()
        session = db_manager.get_session()

        sync_service = SigmaSyncService()

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Indexing rules...", total=None)
            result = sync_service.index_rules(session, force_reindex=force)
            progress.update(task, description="Complete")

        console.print(f"[bold green]✓[/bold green] Metadata indexed: {result['metadata_indexed']}")
        console.print(f"[bold green]✓[/bold green] Embeddings indexed: {result['embeddings_indexed']}")
        if result.get("embedding_error"):
            console.print(f"[yellow]⚠ Embedding warning:[/yellow] {result['embedding_error']}")
        if result["metadata_errors"] > 0 or result["embeddings_errors"] > 0:
            console.print(
                f"[yellow]⚠ Errors:[/yellow] {result['metadata_errors']} metadata, "
                f"{result['embeddings_errors']} embedding"
            )

        session.close()

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Indexing failed: {e}")


@sigma_group.command("index-metadata")
@click.option("--force", is_flag=True, help="Force re-index all rules")
def index_metadata_cmd(force: bool):
    """Index Sigma rule metadata only (no embeddings)."""
    console.print("[bold blue]Indexing Sigma rule metadata...[/bold blue]")

    try:
        db_manager = DatabaseManager()
        session = db_manager.get_session()

        sync_service = SigmaSyncService()

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Indexing metadata...", total=None)
            result = sync_service.index_metadata(session, force_reindex=force)
            progress.update(task, description="Complete")

        console.print(
            f"[bold green]✓[/bold green] Metadata indexed: {result['metadata_indexed']}, "
            f"skipped: {result['skipped']}, errors: {result['errors']}"
        )

        session.close()

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Metadata indexing failed: {e}")


@sigma_group.command("index-customer-repo")
@click.option("--force", is_flag=True, help="Force re-index all customer rules")
@click.option("--no-embeddings", is_flag=True, help="Skip embedding generation (metadata only)")
def index_customer_repo_cmd(force: bool, no_embeddings: bool):
    """Index approved Sigma rules from the customer repo (SIGMA_REPO_PATH) so similarity search includes them."""
    from src.services.sigma_pr_service import SigmaPRService

    console.print("[bold blue]Indexing customer Sigma repo...[/bold blue]")

    try:
        pr_service = SigmaPRService()
        if not pr_service.repo_path.exists():
            console.print(f"[bold red]✗[/bold red] Customer repo path does not exist: {pr_service.repo_path}")
            return

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        sync_service = SigmaSyncService(repo_path=str(pr_service.repo_path))
        prefix = "cust-"

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Indexing customer rules (metadata)...", total=None)
            result = sync_service.index_metadata(
                session, force_reindex=force, rule_id_prefix=prefix
            )
            progress.update(task, description="Metadata complete")

        console.print(
            f"[bold green]✓[/bold green] Customer metadata: indexed={result['metadata_indexed']}, "
            f"skipped={result['skipped']}, errors={result['errors']}"
        )

        if not no_embeddings:
            from rich.progress import BarColumn, MofNCompleteColumn, TimeElapsedColumn, TimeRemainingColumn

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as prog:
                emb_task = prog.add_task("Embedding customer rules...", total=None)

                def on_progress(current, total):
                    if prog.tasks[emb_task].total is None:
                        prog.update(emb_task, total=total)
                    prog.update(emb_task, completed=current)

                emb_result = sync_service.index_embeddings(
                    session,
                    force_reindex=False,
                    progress_callback=on_progress,
                    rule_id_prefix=prefix,
                )
                prog.update(emb_task, description="Complete")
            console.print(
                f"[bold green]✓[/bold green] Embeddings: indexed={emb_result['embeddings_indexed']}, "
                f"skipped={emb_result['skipped']}, errors={emb_result['errors']}"
            )
        else:
            console.print("[dim]Skipped embeddings (--no-embeddings). Run 'sigma index-embeddings' to embed later.[/dim]")

        session.close()

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error("Customer repo indexing failed: %s", e)


@sigma_group.command("index-embeddings")
@click.option("--force", is_flag=True, help="Force regenerate all embeddings")
def index_embeddings_cmd(force: bool):
    """Generate embeddings for Sigma rules (uses local sentence-transformers)."""
    from rich.progress import BarColumn, MofNCompleteColumn, TimeElapsedColumn, TimeRemainingColumn

    console.print("[bold blue]Generating Sigma rule embeddings...[/bold blue]")

    try:
        db_manager = DatabaseManager()
        session = db_manager.get_session()

        sync_service = SigmaSyncService()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Embedding rules...", total=None)

            def on_progress(current, total):
                if progress.tasks[task].total is None:
                    progress.update(task, total=total)
                progress.update(task, completed=current)

            result = sync_service.index_embeddings(session, force_reindex=force, progress_callback=on_progress)
            progress.update(task, description="Complete")

        console.print(
            f"[bold green]✓[/bold green] Embeddings indexed: {result['embeddings_indexed']}, "
            f"skipped: {result['skipped']}, errors: {result['errors']}"
        )

        session.close()

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Embedding generation failed: {e}")


@sigma_group.command("recompute-semantics")
def recompute_semantics_cmd():
    """Recompute deterministic semantic fields (canonical_class, atoms, surface_score) for all indexed SigmaHQ rules."""
    console.print("[bold blue]Recomputing Sigma semantic precompute fields...[/bold blue]")

    try:
        from src.services.sigma_semantic_precompute import is_sigma_similarity_available, precompute_semantic_fields

        if not is_sigma_similarity_available():
            console.print("[bold red]✗[/bold red] sigma_similarity package not installed. Run: pip install -e sigma_semantic_similarity")
            return

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        rules = session.query(SigmaRuleTable).all()
        total = len(rules)
        console.print(f"Found {total} rules to process")

        processed = 0
        failures = 0
        unsupported = 0

        for rule in rules:
            rule_data = {
                "logsource": rule.logsource or {},
                "detection": rule.detection or {},
            }
            sem = precompute_semantic_fields(rule_data)
            if sem is None:
                unsupported += 1
                continue
            try:
                rule.canonical_class = sem["canonical_class"]
                rule.positive_atoms = sem["positive_atoms"]
                rule.negative_atoms = sem["negative_atoms"]
                rule.surface_score = sem["surface_score"]
                processed += 1
                if processed % 100 == 0:
                    session.commit()
                    console.print(f"  Processed {processed}...")
            except Exception as e:
                logger.warning("Failed to update rule %s: %s", rule.rule_id, e)
                failures += 1

        session.commit()
        session.close()

        console.print(f"[bold green]✓[/bold green] Total processed: {processed}")
        console.print(f"[yellow]  Unsupported (skipped): {unsupported}[/yellow]")
        if failures > 0:
            console.print(f"[red]  Failures: {failures}[/red]")

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error("Recompute semantics failed: %s", e)


@sigma_group.command("backfill-metadata")
def backfill_metadata_cmd():
    """Backfill canonical metadata for existing rules (no file system needed)."""
    console.print("[bold blue]Backfilling canonical metadata...[/bold blue]")

    try:
        from src.database.models import SigmaRuleTable

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        rules = session.query(SigmaRuleTable).filter(SigmaRuleTable.canonical_json.is_(None)).all()

        console.print(f"Found {len(rules)} rules needing canonical metadata")

        from dataclasses import asdict

        from src.services.sigma_novelty_service import SigmaNoveltyService

        novelty_service = SigmaNoveltyService(db_session=session)
        updated = 0

        for rule in rules:
            try:
                rule_data = {
                    "logsource": rule.logsource or {},
                    "detection": rule.detection or {},
                }
                canonical_rule = novelty_service.build_canonical_rule(rule_data)
                rule.canonical_json = asdict(canonical_rule)
                rule.exact_hash = novelty_service.generate_exact_hash(canonical_rule)
                rule.canonical_text = novelty_service.generate_canonical_text(canonical_rule)
                logsource_key, _ = novelty_service.normalize_logsource(rule_data["logsource"])
                rule.logsource_key = logsource_key
                updated += 1
                if updated % 100 == 0:
                    session.commit()
            except Exception as e:
                logger.error(f"Error backfilling rule {rule.rule_id}: {e}")

        session.commit()
        console.print(f"[bold green]✓[/bold green] Backfilled {updated} rules")
        session.close()

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Backfill failed: {e}")


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

        # Count customer-repo rules (included in similarity search)
        customer_rules = (
            session.query(SigmaRuleTable).filter(SigmaRuleTable.rule_id.startswith("cust-")).count()
        )

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
        table.add_row("From your repo (similarity search)", str(customer_rules))
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
