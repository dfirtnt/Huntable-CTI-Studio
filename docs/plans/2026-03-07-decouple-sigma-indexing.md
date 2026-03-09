# Decouple Sigma Indexing From LMStudio Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Decouple Sigma rule indexing from LMStudio so metadata/novelty work without embeddings, add a capability service for accurate warnings, and surface degradation metadata in the RAG API.

**Architecture:** Split `SigmaSyncService.index_rules()` into `index_metadata()` + `index_embeddings()`. Introduce `CapabilityService` as single source of truth for feature availability. Extend `/api/chat/rag` response with a `capabilities` block. Shell scripts consume capabilities via CLI.

**Tech Stack:** Python/FastAPI, SQLAlchemy, Click CLI, sentence-transformers, React (JSX), Bash shell scripts

**Design Doc:** `docs/plans/2026-03-07-decouple-sigma-indexing-design.md`

---

## Task 1: Extract `index_metadata()` from `SigmaSyncService`

**Files:**
- Modify: `src/services/sigma_sync_service.py:432-629`
- Test: `tests/services/test_sigma_sync_metadata.py` (create)

**Step 1: Write the failing test for metadata-only indexing**

```python
"""Tests for SigmaSyncService.index_metadata() — metadata phase only, no embeddings."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.sigma_sync_service import SigmaSyncService


@pytest.fixture
def sigma_repo(tmp_path):
    """Create a minimal sigma repo with one rule file."""
    rules_dir = tmp_path / "rules" / "windows"
    rules_dir.mkdir(parents=True)
    rule_file = rules_dir / "test_rule.yml"
    rule_file.write_text(
        """
title: Test Suspicious Process
id: 12345678-1234-1234-1234-123456789abc
status: test
description: Detects test suspicious process execution
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test.exe'
    condition: selection
level: medium
tags:
    - attack.execution
    - attack.t1059
"""
    )
    return tmp_path


@pytest.fixture
def sync_service(sigma_repo):
    return SigmaSyncService(repo_path=str(sigma_repo))


@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = None
    session.query.return_value.all.return_value = []
    session.no_autoflush = MagicMock()
    session.no_autoflush.__enter__ = MagicMock(return_value=None)
    session.no_autoflush.__exit__ = MagicMock(return_value=False)
    return session


class TestIndexMetadata:
    def test_indexes_metadata_without_embedding_dependency(self, sync_service, mock_db_session):
        """index_metadata must succeed without any embedding service."""
        result = sync_service.index_metadata(mock_db_session)

        assert result["metadata_indexed"] >= 1
        assert "errors" in result
        # Verify db_session.add was called (rule was persisted)
        assert mock_db_session.add.called or mock_db_session.commit.called

    def test_metadata_result_has_expected_keys(self, sync_service, mock_db_session):
        result = sync_service.index_metadata(mock_db_session)

        assert "metadata_indexed" in result
        assert "skipped" in result
        assert "errors" in result

    def test_metadata_computes_canonical_fields(self, sync_service, mock_db_session):
        """index_metadata should compute canonical novelty fields."""
        # Capture what gets added to the session
        added_objects = []
        mock_db_session.add.side_effect = lambda obj: added_objects.append(obj)

        sync_service.index_metadata(mock_db_session)

        assert len(added_objects) >= 1
        rule = added_objects[0]
        # Canonical fields should be populated
        assert rule.canonical_json is not None or rule.exact_hash is not None
        # Embedding fields should be None (metadata-only)
        assert rule.embedding is None

    def test_metadata_skips_existing_rules(self, sync_service, mock_db_session):
        """Should skip rules already in DB when force_reindex=False."""
        # Pretend the rule already exists
        mock_db_session.query.return_value.all.return_value = [
            ("12345678-1234-1234-1234-123456789abc",)
        ]

        result = sync_service.index_metadata(mock_db_session, force_reindex=False)
        assert result["skipped"] >= 1
        assert result["metadata_indexed"] == 0

    def test_metadata_reindexes_with_force(self, sync_service, mock_db_session):
        """force_reindex=True should update existing rules."""
        # Pretend the rule exists in DB
        existing_rule = MagicMock()
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = existing_rule
        mock_db_session.query.return_value.all.return_value = [
            ("12345678-1234-1234-1234-123456789abc",)
        ]

        result = sync_service.index_metadata(mock_db_session, force_reindex=True)
        assert result["metadata_indexed"] >= 1
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/test_sigma_sync_metadata.py -v`
Expected: FAIL — `SigmaSyncService` has no `index_metadata` method

**Step 3: Implement `index_metadata()`**

In `src/services/sigma_sync_service.py`, add after line 431 (before existing `index_rules`):

```python
    def index_metadata(self, db_session, force_reindex: bool = False) -> dict:
        """
        Index rule metadata and canonical fields only (no embeddings).

        Args:
            db_session: SQLAlchemy session
            force_reindex: If True, reindex all rules even if they exist

        Returns:
            Dict with metadata_indexed, skipped, errors counts
        """
        from src.database.models import SigmaRuleTable

        logger.info("Starting Sigma rule metadata indexing...")

        existing_rule_ids = set()
        if not force_reindex:
            existing_rule_ids = self.get_existing_rule_ids(db_session)
            logger.info(f"Found {len(existing_rule_ids)} existing rules")

        rule_files = self.find_rule_files()
        commit_sha = self.get_repo_commit_sha()

        metadata_indexed = 0
        skipped_count = 0
        error_count = 0

        for file_path in rule_files:
            try:
                rule_data = self.parse_rule_file(file_path)
                if not rule_data:
                    skipped_count += 1
                    continue

                rule_id = rule_data["rule_id"]

                if not force_reindex and rule_id in existing_rule_ids:
                    skipped_count += 1
                    continue

                # Compute canonical fields
                canonical_json = None
                exact_hash = None
                canonical_text = None
                logsource_key = None
                try:
                    from src.services.sigma_novelty_service import SigmaNoveltyService
                    from dataclasses import asdict

                    novelty_service = SigmaNoveltyService(db_session=db_session)
                    canonical_rule = novelty_service.build_canonical_rule(rule_data)
                    canonical_json = asdict(canonical_rule)
                    exact_hash = novelty_service.generate_exact_hash(canonical_rule)
                    canonical_text = novelty_service.generate_canonical_text(canonical_rule)
                    logsource_key, _ = novelty_service.normalize_logsource(
                        rule_data.get("logsource", {})
                    )
                except Exception as e:
                    logger.warning(f"Failed to compute canonical fields for rule {rule_id}: {e}")

                with db_session.no_autoflush:
                    existing_rule = (
                        db_session.query(SigmaRuleTable).filter_by(rule_id=rule_id).first()
                    )

                    if existing_rule:
                        for key, value in rule_data.items():
                            if key != "rule_id":
                                setattr(existing_rule, key, value)
                        existing_rule.repo_commit_sha = commit_sha
                        existing_rule.canonical_json = canonical_json
                        existing_rule.exact_hash = exact_hash
                        existing_rule.canonical_text = canonical_text
                        existing_rule.logsource_key = logsource_key
                    else:
                        new_rule = SigmaRuleTable(
                            rule_id=rule_id,
                            title=rule_data["title"],
                            description=rule_data["description"],
                            logsource=rule_data["logsource"],
                            detection=rule_data["detection"],
                            tags=rule_data["tags"],
                            level=rule_data["level"],
                            status=rule_data["status"],
                            author=rule_data["author"],
                            date=rule_data["date"],
                            rule_references=rule_data["rule_references"],
                            false_positives=rule_data["false_positives"],
                            fields=rule_data["fields"],
                            file_path=rule_data["file_path"],
                            repo_commit_sha=commit_sha,
                            canonical_json=canonical_json,
                            exact_hash=exact_hash,
                            canonical_text=canonical_text,
                            logsource_key=logsource_key,
                        )
                        db_session.add(new_rule)

                metadata_indexed += 1
                if metadata_indexed % 100 == 0:
                    logger.info(f"Metadata indexed {metadata_indexed} rules...")
                    db_session.commit()

            except Exception as e:
                logger.error(f"Error indexing metadata for rule file {file_path}: {e}")
                error_count += 1
                continue

        db_session.commit()
        logger.info(
            f"Metadata indexing complete: {metadata_indexed} indexed, "
            f"{skipped_count} skipped, {error_count} errors"
        )
        return {
            "metadata_indexed": metadata_indexed,
            "skipped": skipped_count,
            "errors": error_count,
        }
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/services/test_sigma_sync_metadata.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add tests/services/test_sigma_sync_metadata.py src/services/sigma_sync_service.py
git commit -m "feat: add index_metadata() for embedding-free Sigma indexing"
```

---

## Task 2: Extract `index_embeddings()` from `SigmaSyncService`

**Files:**
- Modify: `src/services/sigma_sync_service.py`
- Test: `tests/services/test_sigma_sync_embeddings.py` (create)

**Step 1: Write the failing test for embedding-only indexing**

```python
"""Tests for SigmaSyncService.index_embeddings() — embedding phase only."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.sigma_sync_service import SigmaSyncService


@pytest.fixture
def sync_service(tmp_path):
    return SigmaSyncService(repo_path=str(tmp_path))


@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.no_autoflush = MagicMock()
    session.no_autoflush.__enter__ = MagicMock(return_value=None)
    session.no_autoflush.__exit__ = MagicMock(return_value=False)
    return session


class TestIndexEmbeddings:
    @patch("src.services.sigma_sync_service.EmbeddingService")
    def test_generates_embeddings_for_rules_without_them(
        self, mock_emb_cls, sync_service, mock_db_session
    ):
        """Should generate embeddings for rules where embedding IS NULL."""
        # Create a mock rule with metadata but no embedding
        mock_rule = MagicMock()
        mock_rule.rule_id = "test-rule-1"
        mock_rule.embedding = None
        mock_rule.title = "Test Rule"
        mock_rule.description = "Test description"
        mock_rule.tags = ["attack.execution"]
        mock_rule.logsource = {"category": "process_creation", "product": "windows"}
        mock_rule.detection = {"selection": {"CommandLine|contains": "test"}, "condition": "selection"}

        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_rule]

        # Mock embedding service
        mock_emb_instance = MagicMock()
        mock_emb_instance.generate_embedding.return_value = [0.1] * 768
        mock_emb_instance.generate_embeddings_batch.return_value = [[0.1] * 768] * 4
        mock_emb_cls.return_value = mock_emb_instance

        result = sync_service.index_embeddings(mock_db_session)

        assert result["embeddings_indexed"] >= 1
        assert mock_emb_instance.generate_embedding.called

    @patch("src.services.sigma_sync_service.EmbeddingService")
    def test_result_has_expected_keys(self, mock_emb_cls, sync_service, mock_db_session):
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        mock_emb_cls.return_value = MagicMock()

        result = sync_service.index_embeddings(mock_db_session)

        assert "embeddings_indexed" in result
        assert "skipped" in result
        assert "errors" in result

    @patch("src.services.sigma_sync_service.EmbeddingService")
    def test_skips_rules_with_existing_embeddings(self, mock_emb_cls, sync_service, mock_db_session):
        """When force_reindex=False, rules with embeddings should be skipped."""
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        mock_emb_cls.return_value = MagicMock()

        result = sync_service.index_embeddings(mock_db_session, force_reindex=False)
        assert result["embeddings_indexed"] == 0

    def test_handles_embedding_service_failure_gracefully(self, sync_service, mock_db_session):
        """If EmbeddingService cannot load, return error result instead of raising."""
        with patch(
            "src.services.sigma_sync_service.EmbeddingService",
            side_effect=RuntimeError("Model not available"),
        ):
            result = sync_service.index_embeddings(mock_db_session)

        assert result["embeddings_indexed"] == 0
        assert result["errors"] > 0 or "error" in result
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/test_sigma_sync_embeddings.py -v`
Expected: FAIL — no `index_embeddings` method

**Step 3: Implement `index_embeddings()`**

Add to `src/services/sigma_sync_service.py` after `index_metadata()`. Also add import at top of file:

At the top of the file, after existing imports, add:
```python
from src.services.embedding_service import EmbeddingService
```

Then add the method:

```python
    def index_embeddings(self, db_session, force_reindex: bool = False) -> dict:
        """
        Generate embeddings for Sigma rules that lack them.

        Uses local sentence-transformers (intfloat/e5-base-v2), no LMStudio dependency.

        Args:
            db_session: SQLAlchemy session
            force_reindex: If True, regenerate embeddings for all rules

        Returns:
            Dict with embeddings_indexed, skipped, errors counts
        """
        from src.database.models import SigmaRuleTable

        logger.info("Starting Sigma rule embedding generation...")

        # Initialize local embedding service
        try:
            embedding_service = EmbeddingService(model_name="intfloat/e5-base-v2")
        except Exception as e:
            logger.error(f"Failed to initialize embedding service: {e}")
            return {"embeddings_indexed": 0, "skipped": 0, "errors": 1, "error": str(e)}

        # Get rules that need embeddings
        if force_reindex:
            rules = db_session.query(SigmaRuleTable).all()
        else:
            rules = (
                db_session.query(SigmaRuleTable)
                .filter(SigmaRuleTable.embedding.is_(None))
                .all()
            )

        logger.info(f"Found {len(rules)} rules needing embeddings")

        embeddings_indexed = 0
        error_count = 0
        embedding_model_name = "intfloat/e5-base-v2"

        for rule in rules:
            try:
                # Build rule_data dict from DB row for embedding text generation
                rule_data = {
                    "title": rule.title,
                    "description": rule.description,
                    "tags": rule.tags or [],
                    "logsource": rule.logsource or {},
                    "detection": rule.detection or {},
                }

                # Generate main embedding
                embedding_text = self.create_rule_embedding_text(rule_data)
                embedding = embedding_service.generate_embedding(embedding_text)

                # Generate section embeddings
                section_texts = self.create_section_embeddings_text(rule_data)
                section_texts_list = [
                    section_texts["title"],
                    section_texts["description"],
                    section_texts["tags"],
                    section_texts["signature"],
                ]
                section_embeddings = embedding_service.generate_embeddings_batch(
                    section_texts_list
                )

                while len(section_embeddings) < 4:
                    section_embeddings.append([0.0] * 768)

                title_emb = (
                    section_embeddings[0]
                    if section_embeddings[0] and len(section_embeddings[0]) == 768
                    else None
                )
                description_emb = (
                    section_embeddings[1]
                    if section_embeddings[1] and len(section_embeddings[1]) == 768
                    else None
                )
                tags_emb = (
                    section_embeddings[2]
                    if section_embeddings[2] and len(section_embeddings[2]) == 768
                    else None
                )
                signature_emb = (
                    section_embeddings[3]
                    if section_embeddings[3] and len(section_embeddings[3]) == 768
                    else None
                )

                # Update rule with embeddings
                rule.embedding = embedding
                rule.embedding_model = embedding_model_name
                rule.embedded_at = datetime.now()
                rule.title_embedding = title_emb
                rule.description_embedding = description_emb
                rule.tags_embedding = tags_emb
                rule.logsource_embedding = signature_emb
                rule.detection_structure_embedding = signature_emb
                rule.detection_fields_embedding = signature_emb

                embeddings_indexed += 1
                if embeddings_indexed % 100 == 0:
                    logger.info(f"Embedded {embeddings_indexed} rules...")
                    db_session.commit()

            except Exception as e:
                logger.error(f"Error generating embeddings for rule {rule.rule_id}: {e}")
                error_count += 1
                continue

        db_session.commit()
        skipped = len(rules) - embeddings_indexed - error_count
        logger.info(
            f"Embedding generation complete: {embeddings_indexed} indexed, "
            f"{skipped} skipped, {error_count} errors"
        )
        return {
            "embeddings_indexed": embeddings_indexed,
            "skipped": max(0, skipped),
            "errors": error_count,
        }
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/services/test_sigma_sync_embeddings.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add tests/services/test_sigma_sync_embeddings.py src/services/sigma_sync_service.py
git commit -m "feat: add index_embeddings() using local sentence-transformers"
```

---

## Task 3: Refactor `index_rules()` as orchestrator + update CLI

**Files:**
- Modify: `src/services/sigma_sync_service.py:432-629` (replace `index_rules`)
- Modify: `src/cli/sigma_commands.py:63-91` (update `index` command, add subcommands)
- Test: `tests/services/test_sigma_sync_orchestrator.py` (create)

**Step 1: Write the failing test for orchestrator**

```python
"""Tests for SigmaSyncService.index_rules() orchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.sigma_sync_service import SigmaSyncService


@pytest.fixture
def sync_service(tmp_path):
    return SigmaSyncService(repo_path=str(tmp_path))


class TestIndexRulesOrchestrator:
    def test_returns_dict_not_int(self, sync_service):
        """Orchestrator should return dict with both phases' results."""
        mock_session = MagicMock()
        with (
            patch.object(
                sync_service, "index_metadata",
                return_value={"metadata_indexed": 5, "skipped": 0, "errors": 0},
            ),
            patch.object(
                sync_service, "index_embeddings",
                return_value={"embeddings_indexed": 5, "skipped": 0, "errors": 0},
            ),
        ):
            result = sync_service.index_rules(mock_session)

        assert isinstance(result, dict)
        assert result["metadata_indexed"] == 5
        assert result["embeddings_indexed"] == 5

    def test_succeeds_partially_when_embeddings_fail(self, sync_service):
        """Should return partial success when metadata works but embeddings fail."""
        mock_session = MagicMock()
        with (
            patch.object(
                sync_service, "index_metadata",
                return_value={"metadata_indexed": 10, "skipped": 0, "errors": 0},
            ),
            patch.object(
                sync_service, "index_embeddings",
                side_effect=RuntimeError("Model unavailable"),
            ),
        ):
            result = sync_service.index_rules(mock_session)

        assert result["metadata_indexed"] == 10
        assert result["embeddings_indexed"] == 0
        assert "embedding_error" in result

    def test_backward_compat_int_return(self, sync_service):
        """For backward compatibility, index_rules_count() returns int."""
        mock_session = MagicMock()
        with (
            patch.object(
                sync_service, "index_metadata",
                return_value={"metadata_indexed": 5, "skipped": 0, "errors": 0},
            ),
            patch.object(
                sync_service, "index_embeddings",
                return_value={"embeddings_indexed": 5, "skipped": 0, "errors": 0},
            ),
        ):
            result = sync_service.index_rules(mock_session)

        # Backward compat: total count available
        assert result["metadata_indexed"] + result["embeddings_indexed"] >= 0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/test_sigma_sync_orchestrator.py -v`
Expected: FAIL — `index_rules` returns int, not dict

**Step 3: Replace `index_rules()` with orchestrator**

Replace the entire existing `index_rules` method (lines 432-629) in `src/services/sigma_sync_service.py`:

```python
    def index_rules(self, db_session, force_reindex: bool = False) -> dict:
        """
        Orchestrate metadata + embedding indexing.

        Runs metadata indexing first (always), then attempts embedding generation.
        Returns partial success if metadata succeeds but embeddings fail.

        Args:
            db_session: SQLAlchemy session
            force_reindex: If True, reindex all rules

        Returns:
            Dict with metadata_indexed, embeddings_indexed, embedding_error (if any)
        """
        logger.info("Starting Sigma rule indexing (orchestrator)...")

        # Phase 1: Metadata (always runs)
        metadata_result = self.index_metadata(db_session, force_reindex=force_reindex)

        # Phase 2: Embeddings (optional, graceful failure)
        embedding_result = {"embeddings_indexed": 0, "skipped": 0, "errors": 0}
        embedding_error = None
        try:
            embedding_result = self.index_embeddings(db_session, force_reindex=force_reindex)
        except Exception as e:
            embedding_error = str(e)
            logger.warning(f"Embedding generation failed (metadata still indexed): {e}")

        result = {
            "metadata_indexed": metadata_result["metadata_indexed"],
            "metadata_skipped": metadata_result["skipped"],
            "metadata_errors": metadata_result["errors"],
            "embeddings_indexed": embedding_result.get("embeddings_indexed", 0),
            "embeddings_skipped": embedding_result.get("skipped", 0),
            "embeddings_errors": embedding_result.get("errors", 0),
        }
        if embedding_error:
            result["embedding_error"] = embedding_error

        logger.info(
            f"Indexing complete: {result['metadata_indexed']} metadata, "
            f"{result['embeddings_indexed']} embeddings"
        )
        return result
```

Also update the `sync()` method (around line 631) to work with the new dict return:

```python
    async def sync(self, db_session, force_reindex: bool = False) -> dict[str, Any]:
        try:
            sync_result = self.clone_or_pull_repository()
            if not sync_result["success"]:
                return sync_result

            index_result = self.index_rules(db_session, force_reindex=force_reindex)

            return {
                "success": True,
                "action": sync_result["action"],
                "rules_indexed": index_result["metadata_indexed"],
                "embeddings_indexed": index_result.get("embeddings_indexed", 0),
                "message": (
                    f"Successfully synced: {index_result['metadata_indexed']} metadata, "
                    f"{index_result.get('embeddings_indexed', 0)} embeddings"
                ),
            }
        except Exception as e:
            logger.error(f"Sigma sync failed: {e}")
            return {"success": False, "error": str(e)}
```

**Step 4: Update CLI commands**

In `src/cli/sigma_commands.py`, replace the `index_rules` command (lines 63-91) and add new subcommands:

```python
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

        console.print(
            f"[bold green]✓[/bold green] Metadata indexed: {result['metadata_indexed']}"
        )
        console.print(
            f"[bold green]✓[/bold green] Embeddings indexed: {result['embeddings_indexed']}"
        )
        if result.get("embedding_error"):
            console.print(
                f"[yellow]⚠ Embedding warning:[/yellow] {result['embedding_error']}"
            )
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


@sigma_group.command("index-embeddings")
@click.option("--force", is_flag=True, help="Force regenerate all embeddings")
def index_embeddings_cmd(force: bool):
    """Generate embeddings for Sigma rules (uses local sentence-transformers)."""
    console.print("[bold blue]Generating Sigma rule embeddings...[/bold blue]")

    try:
        db_manager = DatabaseManager()
        session = db_manager.get_session()

        sync_service = SigmaSyncService()

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Generating embeddings...", total=None)
            result = sync_service.index_embeddings(session, force_reindex=force)
            progress.update(task, description="Complete")

        console.print(
            f"[bold green]✓[/bold green] Embeddings indexed: {result['embeddings_indexed']}, "
            f"skipped: {result['skipped']}, errors: {result['errors']}"
        )

        session.close()

    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Embedding generation failed: {e}")


@sigma_group.command("backfill-metadata")
def backfill_metadata_cmd():
    """Backfill canonical metadata for existing rules (no file system needed)."""
    console.print("[bold blue]Backfilling canonical metadata...[/bold blue]")

    try:
        from src.database.models import SigmaRuleTable

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        rules = (
            session.query(SigmaRuleTable)
            .filter(SigmaRuleTable.canonical_json.is_(None))
            .all()
        )

        console.print(f"Found {len(rules)} rules needing canonical metadata")

        from src.services.sigma_novelty_service import SigmaNoveltyService
        from dataclasses import asdict

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
```

**Step 5: Run tests to verify everything passes**

Run: `python -m pytest tests/services/test_sigma_sync_orchestrator.py tests/services/test_sigma_sync_metadata.py tests/services/test_sigma_sync_embeddings.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/services/sigma_sync_service.py src/cli/sigma_commands.py tests/services/test_sigma_sync_orchestrator.py
git commit -m "refactor: replace monolithic index_rules with metadata+embedding orchestrator

Split Sigma indexing into index_metadata() (always available) and
index_embeddings() (optional, local sentence-transformers).
Add CLI subcommands: sigma index-metadata, sigma index-embeddings,
sigma backfill-metadata."
```

---

## Task 4: Update Celery task for partial-success

**Files:**
- Modify: `src/worker/celery_app.py:1184-1236`
- Test: `tests/worker/test_sigma_celery_task.py` (create)

**Step 1: Write the failing test**

```python
"""Tests for sync_sigma_rules Celery task partial success."""

from unittest.mock import MagicMock, patch

import pytest


class TestSyncSigmaRulesTask:
    @patch("src.worker.celery_app.DatabaseManager")
    @patch("src.worker.celery_app.SigmaSyncService")
    def test_returns_success_with_partial_embeddings(self, mock_svc_cls, mock_db_cls):
        """Task should succeed when metadata works but embeddings have errors."""
        from src.worker.celery_app import sync_sigma_rules

        mock_session = MagicMock()
        mock_db_cls.return_value.get_session.return_value = mock_session

        mock_svc = MagicMock()
        mock_svc.clone_or_pull_repository.return_value = {"success": True, "action": "pulled"}
        mock_svc.index_rules.return_value = {
            "metadata_indexed": 100,
            "metadata_skipped": 0,
            "metadata_errors": 0,
            "embeddings_indexed": 0,
            "embeddings_skipped": 100,
            "embeddings_errors": 0,
            "embedding_error": "Model not available",
        }
        mock_svc_cls.return_value = mock_svc

        result = sync_sigma_rules(force_reindex=False)

        assert result["status"] == "success"
        assert result["rules_indexed"] == 100
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/worker/test_sigma_celery_task.py -v`
Expected: FAIL — current task expects int from `index_rules`

**Step 3: Update Celery task**

In `src/worker/celery_app.py`, replace the `sync_sigma_rules` task body (around lines 1185-1236):

```python
@celery_app.task(bind=True, max_retries=2)
def sync_sigma_rules(self, force_reindex=False):
    """Sync SigmaHQ repository and index rules (metadata always, embeddings optional)."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.sigma_sync_service import SigmaSyncService

        logger.info("Starting SigmaHQ repository sync...")

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            sync_service = SigmaSyncService()

            sync_result = sync_service.clone_or_pull_repository()

            if not sync_result.get("success"):
                error_msg = sync_result.get("error", "Unknown error")
                logger.error(f"Sigma repository sync failed: {error_msg}")
                return {
                    "status": "error",
                    "message": f"Repository sync failed: {error_msg}",
                }

            logger.info(f"Repository {sync_result.get('action', 'synced')} successfully")

            index_result = sync_service.index_rules(session, force_reindex=force_reindex)

            rules_indexed = index_result.get("metadata_indexed", 0)
            embeddings_indexed = index_result.get("embeddings_indexed", 0)

            if index_result.get("embedding_error"):
                logger.warning(
                    f"Sigma sync partial success: {rules_indexed} metadata indexed, "
                    f"embedding phase failed: {index_result['embedding_error']}"
                )

            logger.info(
                f"Sigma sync complete: {rules_indexed} metadata, {embeddings_indexed} embeddings"
            )

            return {
                "status": "success",
                "action": sync_result.get("action"),
                "rules_indexed": rules_indexed,
                "embeddings_indexed": embeddings_indexed,
                "embedding_error": index_result.get("embedding_error"),
                "message": (
                    f"Synced: {rules_indexed} metadata, {embeddings_indexed} embeddings"
                ),
            }

        except Exception as e:
            logger.error(f"Sigma sync task failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise e
        finally:
            session.close()

    except Exception as exc:
        logger.error(f"Sigma sync task failed: {exc}")
        raise self.retry(exc=exc, countdown=300 * (2 ** self.request.retries)) from exc
```

**Step 4: Run tests**

Run: `python -m pytest tests/worker/test_sigma_celery_task.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/worker/celery_app.py tests/worker/test_sigma_celery_task.py
git commit -m "fix: update Celery sigma task for partial-success semantics"
```

---

## Task 5: Create `CapabilityService`

**Files:**
- Create: `src/services/capability_service.py`
- Test: `tests/services/test_capability_service.py` (create)

**Step 1: Write the failing test**

```python
"""Tests for CapabilityService."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.capability_service import CapabilityService


@pytest.fixture
def capability_service():
    return CapabilityService()


class TestCapabilityService:
    def test_compute_returns_all_capability_keys(self, capability_service):
        with patch.object(capability_service, "_get_db_session", return_value=MagicMock()):
            result = capability_service.compute_capabilities()

        expected_keys = {
            "article_retrieval",
            "sigma_metadata_indexing",
            "sigma_embedding_indexing",
            "sigma_retrieval",
            "sigma_novelty_comparison",
            "llm_generation",
        }
        assert set(result.keys()) == expected_keys

    def test_each_capability_has_enabled_and_reason(self, capability_service):
        with patch.object(capability_service, "_get_db_session", return_value=MagicMock()):
            result = capability_service.compute_capabilities()

        for key, cap in result.items():
            assert "enabled" in cap, f"{key} missing 'enabled'"
            assert "reason" in cap, f"{key} missing 'reason'"
            assert isinstance(cap["enabled"], bool), f"{key} 'enabled' not bool"

    @patch("src.services.capability_service.os.getenv")
    def test_llm_generation_enabled_with_openai_key(self, mock_getenv, capability_service):
        def getenv_side_effect(key, default=""):
            if key == "OPENAI_API_KEY":
                return "sk-test-key"
            return default

        mock_getenv.side_effect = getenv_side_effect

        with patch.object(capability_service, "_get_db_session", return_value=MagicMock()):
            result = capability_service.compute_capabilities()

        assert result["llm_generation"]["enabled"] is True

    @patch("src.services.capability_service.os.getenv", return_value="")
    def test_llm_generation_disabled_without_keys(self, mock_getenv, capability_service):
        with patch.object(capability_service, "_get_db_session", return_value=MagicMock()):
            result = capability_service.compute_capabilities()

        assert result["llm_generation"]["enabled"] is False

    def test_sigma_retrieval_disabled_when_no_embedded_rules(self, capability_service):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.return_value = 0

        with patch.object(capability_service, "_get_db_session", return_value=mock_session):
            result = capability_service.compute_capabilities()

        assert result["sigma_retrieval"]["enabled"] is False
        assert "action" in result["sigma_retrieval"]

    def test_sigma_retrieval_enabled_when_embedded_rules_exist(self, capability_service):
        mock_session = MagicMock()
        # First count call: embedded rules (sigma_retrieval)
        # Second count call: canonical rules (sigma_novelty)
        mock_session.query.return_value.filter.return_value.count.side_effect = [100, 100]

        with patch.object(capability_service, "_get_db_session", return_value=mock_session):
            result = capability_service.compute_capabilities()

        assert result["sigma_retrieval"]["enabled"] is True
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/test_capability_service.py -v`
Expected: FAIL — module does not exist

**Step 3: Implement `CapabilityService`**

Create `src/services/capability_service.py`:

```python
"""
Capability Service

Single source of truth for feature availability.
Consumed by CLI, API, shell scripts, and frontend.
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CapabilityService:
    """Probes runtime state and returns capability flags."""

    def __init__(self, sigma_repo_path: str = "./data/sigma-repo"):
        self.sigma_repo_path = Path(sigma_repo_path)

    def _get_db_session(self):
        """Get a database session. Override in tests."""
        from src.database.manager import DatabaseManager

        db_manager = DatabaseManager()
        return db_manager.get_session()

    def compute_capabilities(self, db_session=None) -> dict[str, Any]:
        """
        Probe runtime state and return capability flags.

        Args:
            db_session: Optional SQLAlchemy session (creates one if not provided)

        Returns:
            Dict mapping capability names to status dicts
        """
        session = db_session or self._get_db_session()
        close_session = db_session is None

        try:
            return {
                "article_retrieval": self._check_article_retrieval(session),
                "sigma_metadata_indexing": self._check_sigma_metadata_indexing(),
                "sigma_embedding_indexing": self._check_sigma_embedding_indexing(),
                "sigma_retrieval": self._check_sigma_retrieval(session),
                "sigma_novelty_comparison": self._check_sigma_novelty(session),
                "llm_generation": self._check_llm_generation(),
            }
        finally:
            if close_session and hasattr(session, "close"):
                session.close()

    def _check_article_retrieval(self, session) -> dict:
        try:
            from src.database.models import ArticleTable

            count = session.query(ArticleTable).filter(
                ArticleTable.embedding.isnot(None)
            ).count()
            if count > 0:
                return {"enabled": True, "reason": f"{count} articles with embeddings available"}
            return {
                "enabled": False,
                "reason": "No articles with embeddings found",
                "action": "Run a workflow to ingest and embed articles",
            }
        except Exception as e:
            return {"enabled": False, "reason": f"Check failed: {e}"}

    def _check_sigma_metadata_indexing(self) -> dict:
        rules_path = self.sigma_repo_path / "rules"
        if rules_path.exists():
            return {"enabled": True, "reason": "Sigma repository available"}
        return {
            "enabled": False,
            "reason": "Sigma repository not cloned",
            "action": "Run sigma sync to clone the SigmaHQ repository",
        }

    def _check_sigma_embedding_indexing(self) -> dict:
        try:
            from src.services.embedding_service import EmbeddingService

            # Just check if the class can be instantiated (model download check)
            EmbeddingService(model_name="intfloat/e5-base-v2")
            return {"enabled": True, "reason": "Embedding model available"}
        except Exception as e:
            return {
                "enabled": False,
                "reason": f"Embedding model unavailable: {e}",
                "action": "Install sentence-transformers and download intfloat/e5-base-v2",
            }

    def _check_sigma_retrieval(self, session) -> dict:
        try:
            from src.database.models import SigmaRuleTable

            count = session.query(SigmaRuleTable).filter(
                SigmaRuleTable.embedding.isnot(None)
            ).count()
            if count > 0:
                return {
                    "enabled": True,
                    "reason": f"{count} Sigma rules with embeddings available",
                }
            return {
                "enabled": False,
                "reason": "No Sigma rules with embeddings found",
                "action": "Run sigma index-embeddings to enable Sigma rule retrieval in RAG",
            }
        except Exception as e:
            return {"enabled": False, "reason": f"Check failed: {e}"}

    def _check_sigma_novelty(self, session) -> dict:
        try:
            from src.database.models import SigmaRuleTable

            count = session.query(SigmaRuleTable).filter(
                SigmaRuleTable.canonical_json.isnot(None)
            ).count()
            if count > 0:
                return {
                    "enabled": True,
                    "reason": f"{count} Sigma rules with canonical metadata available",
                }
            return {
                "enabled": False,
                "reason": "No Sigma rules with canonical metadata found",
                "action": "Run sigma index-metadata or sigma backfill-metadata",
            }
        except Exception as e:
            return {"enabled": False, "reason": f"Check failed: {e}"}

    def _check_llm_generation(self) -> dict:
        openai_key = os.getenv("OPENAI_API_KEY", "")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        lmstudio_url = os.getenv("LMSTUDIO_API_URL", "")

        if openai_key:
            return {"enabled": True, "provider": "openai", "reason": "OpenAI API key configured"}
        if anthropic_key:
            return {
                "enabled": True,
                "provider": "anthropic",
                "reason": "Anthropic API key configured",
            }
        if lmstudio_url:
            return {
                "enabled": True,
                "provider": "lmstudio",
                "reason": "LMStudio API URL configured",
            }
        return {
            "enabled": False,
            "provider": "none",
            "reason": "No LLM provider configured",
            "action": "Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env",
        }
```

**Step 4: Run tests**

Run: `python -m pytest tests/services/test_capability_service.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/services/capability_service.py tests/services/test_capability_service.py
git commit -m "feat: add CapabilityService for runtime feature detection"
```

---

## Task 6: Add `/api/capabilities` endpoint + CLI command

**Files:**
- Modify: `src/web/routes/health.py`
- Modify: `src/cli/main.py`
- Create: `src/cli/commands/capabilities.py`
- Test: `tests/api/test_capabilities_api.py` (create)

**Step 1: Write the failing test**

```python
"""Tests for /api/capabilities endpoint."""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_capabilities():
    return {
        "article_retrieval": {"enabled": True, "reason": "100 articles available"},
        "sigma_metadata_indexing": {"enabled": True, "reason": "Repo available"},
        "sigma_embedding_indexing": {"enabled": True, "reason": "Model available"},
        "sigma_retrieval": {
            "enabled": False,
            "reason": "No embedded rules",
            "action": "Run sigma index-embeddings",
        },
        "sigma_novelty_comparison": {"enabled": True, "reason": "50 rules with metadata"},
        "llm_generation": {"enabled": True, "provider": "openai", "reason": "Key configured"},
    }


@pytest.mark.asyncio
async def test_capabilities_endpoint_returns_all_keys(mock_capabilities):
    with patch(
        "src.web.routes.health.CapabilityService"
    ) as mock_cls:
        mock_cls.return_value.compute_capabilities.return_value = mock_capabilities

        from src.web.modern_main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/capabilities")

    assert response.status_code == 200
    data = response.json()
    assert "article_retrieval" in data
    assert "sigma_retrieval" in data
    assert data["sigma_retrieval"]["enabled"] is False
    assert "action" in data["sigma_retrieval"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_capabilities_api.py -v`
Expected: FAIL — endpoint does not exist

**Step 3: Add endpoint to health.py**

Add at the end of `src/web/routes/health.py`:

```python
@router.get("/api/capabilities")
async def api_capabilities() -> dict[str, Any]:
    """Return runtime capability flags for all features."""
    try:
        from src.services.capability_service import CapabilityService

        service = CapabilityService()
        return service.compute_capabilities()
    except Exception as exc:
        logger.error("Capabilities check failed: %s", exc)
        return {"error": str(exc)}
```

**Step 4: Add CLI capabilities command**

Create `src/cli/commands/capabilities.py`:

```python
"""CLI command for checking runtime capabilities."""

import json
import logging

import click
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()


@click.group(name="capabilities")
def capabilities_group():
    """Check runtime feature capabilities."""
    pass


@capabilities_group.command("check")
@click.option("--json-output", "json_out", is_flag=True, help="Output as JSON")
def check_capabilities(json_out: bool):
    """Check which features are available in the current environment."""
    try:
        from src.services.capability_service import CapabilityService

        service = CapabilityService()
        caps = service.compute_capabilities()

        if json_out:
            click.echo(json.dumps(caps, indent=2))
            return

        table = Table(title="Runtime Capabilities")
        table.add_column("Capability", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Details", style="dim")
        table.add_column("Action", style="yellow")

        for name, cap in caps.items():
            status = "[green]Enabled[/green]" if cap["enabled"] else "[red]Disabled[/red]"
            table.add_row(
                name.replace("_", " ").title(),
                status,
                cap.get("reason", ""),
                cap.get("action", ""),
            )

        console.print(table)

    except Exception as e:
        if json_out:
            click.echo(json.dumps({"error": str(e)}))
        else:
            console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Capabilities check failed: {e}")
```

Register in `src/cli/main.py` — add import and registration:

```python
from .commands.capabilities import capabilities_group
# ... in the registration section:
cli.add_command(capabilities_group)
```

**Step 5: Run tests**

Run: `python -m pytest tests/api/test_capabilities_api.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/web/routes/health.py src/cli/commands/capabilities.py src/cli/main.py tests/api/test_capabilities_api.py
git commit -m "feat: add /api/capabilities endpoint and CLI capabilities command"
```

---

## Task 7: Add capabilities to RAG API response

**Files:**
- Modify: `src/web/routes/chat.py:230-644`
- Test: `tests/api/test_chat_capabilities.py` (create)

**Step 1: Write the failing test**

```python
"""Tests for capabilities block in /api/chat/rag response."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_caps_disabled():
    return {
        "article_retrieval": {"enabled": True, "reason": "OK"},
        "sigma_retrieval": {
            "enabled": False,
            "reason": "No embedded rules",
            "action": "Run sigma index-embeddings",
        },
        "llm_generation": {"enabled": True, "provider": "openai", "reason": "OK"},
    }


@pytest.mark.asyncio
async def test_rag_response_includes_capabilities(mock_caps_disabled):
    with (
        patch("src.web.routes.chat.CapabilityService") as mock_cap_cls,
        patch("src.web.routes.chat.get_rag_service") as mock_rag,
    ):
        mock_cap_cls.return_value.compute_capabilities.return_value = mock_caps_disabled

        mock_rag_svc = AsyncMock()
        mock_rag_svc.find_unified_results.return_value = {
            "articles": [],
            "rules": [],
            "total_articles": 0,
            "total_rules": 0,
        }
        mock_rag.return_value = mock_rag_svc

        from src.web.modern_main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/chat/rag",
                json={"message": "test query"},
            )

    assert response.status_code == 200
    data = response.json()
    assert "capabilities" in data
    assert data["capabilities"]["sigma_retrieval"]["enabled"] is False
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_chat_capabilities.py -v`
Expected: FAIL — no `capabilities` in response

**Step 3: Add capabilities to chat.py**

In `src/web/routes/chat.py`, at the top of `api_rag_chat()` (after the try block opens, around line 236), add:

```python
        # Compute capabilities for response metadata
        from src.services.capability_service import CapabilityService
        capability_service = CapabilityService()
        capabilities = capability_service.compute_capabilities()
        # Subset for RAG response (only relevant capabilities)
        rag_capabilities = {
            "article_retrieval": capabilities.get("article_retrieval", {}),
            "sigma_retrieval": capabilities.get("sigma_retrieval", {}),
            "llm_generation": capabilities.get("llm_generation", {}),
        }
```

Then in the return dict (around line 630), add the `capabilities` key:

```python
        return {
            "response": response,
            ...existing fields...
            "capabilities": rag_capabilities,
        }
```

**Step 4: Run tests**

Run: `python -m pytest tests/api/test_chat_capabilities.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/web/routes/chat.py tests/api/test_chat_capabilities.py
git commit -m "feat: add capabilities block to /api/chat/rag response"
```

---

## Task 8: Frontend capability banners in RAGChat.jsx

**Files:**
- Modify: `src/web/static/js/components/RAGChat.jsx`

**Step 1: Add capability state tracking**

Near the top of the `RAGChat` component (after existing state declarations around line 20), add:

```jsx
  const [capabilities, setCapabilities] = useState(null);
```

**Step 2: Fetch capabilities on mount**

Add a useEffect after the existing ones (around line 55):

```jsx
  // Fetch capabilities on mount
  useEffect(() => {
    fetch('/api/capabilities')
      .then(res => res.json())
      .then(data => setCapabilities(data))
      .catch(err => console.error('Failed to fetch capabilities:', err));
  }, []);
```

**Step 3: Update response handler to capture capabilities**

In the `handleSendMessage` function, where the RAG response is processed, update to capture capabilities from the response:

```jsx
        // Update capabilities from response if present
        if (data.capabilities) {
          setCapabilities(prev => ({ ...prev, ...data.capabilities }));
        }
```

**Step 4: Add capability banner component**

Before the return JSX (but inside the component), add a helper:

```jsx
  const renderCapabilityBanners = () => {
    if (!capabilities) return null;

    const banners = [];

    if (capabilities.sigma_retrieval && !capabilities.sigma_retrieval.enabled) {
      banners.push(
        <div key="sigma" className="bg-yellow-900/30 border border-yellow-700 text-yellow-200 px-4 py-2 rounded mb-2 text-sm">
          <strong>Sigma rule search unavailable:</strong> {capabilities.sigma_retrieval.reason}.
          {capabilities.sigma_retrieval.action && (
            <span className="ml-1 text-yellow-400">{capabilities.sigma_retrieval.action}</span>
          )}
        </div>
      );
    }

    if (capabilities.llm_generation && !capabilities.llm_generation.enabled) {
      banners.push(
        <div key="llm" className="bg-yellow-900/30 border border-yellow-700 text-yellow-200 px-4 py-2 rounded mb-2 text-sm">
          <strong>LLM generation unavailable:</strong> {capabilities.llm_generation.reason}.
          {capabilities.llm_generation.action && (
            <span className="ml-1 text-yellow-400">{capabilities.llm_generation.action}</span>
          )}
        </div>
      );
    }

    return banners.length > 0 ? <div className="mb-3">{banners}</div> : null;
  };
```

**Step 5: Render banners in the JSX**

In the component's return JSX, add `{renderCapabilityBanners()}` just above the messages list.

**Step 6: Commit**

```bash
git add src/web/static/js/components/RAGChat.jsx
git commit -m "feat: add capability warning banners to RAG chat UI"
```

---

## Task 9: Update shell scripts for capability-driven warnings

**Files:**
- Modify: `start.sh`
- Modify: `setup.sh`

**Step 1: Update `start.sh`**

Replace the hardcoded warning block (lines 70-103) with capability-driven output. After the service health checks pass (after line 150), add:

```bash
# --- Capability-driven warnings ---
echo ""
echo "Checking feature capabilities..."
CAP_JSON=$($DC run --rm cli python -m src.cli.main capabilities check --json-output 2>/dev/null || echo '{}')

if command -v python3 >/dev/null 2>&1; then
    _cap_enabled() {
        python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('$1',{}).get('enabled',''))" "$CAP_JSON" 2>/dev/null
    }
    _cap_reason() {
        python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('$1',{}).get('reason',''))" "$CAP_JSON" 2>/dev/null
    }
    _cap_action() {
        python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('$1',{}).get('action',''))" "$CAP_JSON" 2>/dev/null
    }

    sigma_ret=$(_cap_enabled sigma_retrieval)
    sigma_nov=$(_cap_enabled sigma_novelty_comparison)
    llm_gen=$(_cap_enabled llm_generation)

    if [ "$sigma_ret" = "False" ]; then
        echo "  ⚠️  Sigma rule search in RAG: unavailable ($(_cap_reason sigma_retrieval))"
        echo "     → $(_cap_action sigma_retrieval)"
    else
        echo "  ✅ Sigma rule search in RAG: available"
    fi

    if [ "$sigma_nov" = "False" ]; then
        echo "  ⚠️  Sigma novelty comparison: unavailable ($(_cap_reason sigma_novelty_comparison))"
    else
        echo "  ✅ Sigma novelty comparison: available"
    fi

    if [ "$llm_gen" = "False" ]; then
        echo "  ⚠️  LLM answer generation: unavailable ($(_cap_reason llm_generation))"
        echo "     → $(_cap_action llm_generation)"
    else
        echo "  ✅ LLM answer generation: available ($(_cap_reason llm_generation))"
    fi
else
    echo "  (python3 not found, skipping capability check)"
fi
echo ""
```

Keep the existing SKIP_SIGMA_INDEX logic for the actual sigma indexing step — it still makes sense to skip embedding generation on non-Apple-Silicon. But the **warnings** now come from capabilities.

**Step 2: Update `setup.sh`**

In `setup.sh`, after the Sigma sync/index section (around line 580), add the same capability check block.

Replace the hardcoded summary section at the end (around lines 634-660) to call capabilities.

**Step 3: Manually test**

Run: `./start.sh` in a test environment, verify warnings match `/api/capabilities` output.

**Step 4: Commit**

```bash
git add start.sh setup.sh
git commit -m "fix: replace hardcoded LMStudio warnings with capability-driven output"
```

---

## Task 10: Integration test — full degraded-mode flow

**Files:**
- Create: `tests/integration/test_sigma_decoupled_indexing.py`

**Step 1: Write integration test**

```python
"""Integration test: metadata-only indexing + capability reporting + RAG degradation."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.capability_service import CapabilityService
from src.services.sigma_sync_service import SigmaSyncService


@pytest.fixture
def sigma_repo(tmp_path):
    rules_dir = tmp_path / "rules" / "windows"
    rules_dir.mkdir(parents=True)
    rule_file = rules_dir / "test_rule.yml"
    rule_file.write_text(
        """
title: Test Process Execution
id: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
status: test
description: Test rule for integration testing
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'suspicious.exe'
    condition: selection
level: high
tags:
    - attack.execution
"""
    )
    return tmp_path


class TestDecoupledIndexingIntegration:
    def test_metadata_indexing_then_capability_check(self, sigma_repo):
        """Full flow: index metadata -> check capabilities -> verify sigma_retrieval disabled."""
        mock_session = MagicMock()
        mock_session.query.return_value.all.return_value = []
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_session.no_autoflush = MagicMock()
        mock_session.no_autoflush.__enter__ = MagicMock(return_value=None)
        mock_session.no_autoflush.__exit__ = MagicMock(return_value=False)

        added_objects = []
        mock_session.add.side_effect = lambda obj: added_objects.append(obj)

        # Phase 1: Index metadata only
        sync_service = SigmaSyncService(repo_path=str(sigma_repo))
        result = sync_service.index_metadata(mock_session)

        assert result["metadata_indexed"] == 1
        assert len(added_objects) == 1
        rule = added_objects[0]
        assert rule.embedding is None  # No embedding generated
        assert rule.title == "Test Process Execution"

        # Phase 2: Check capabilities
        # sigma_retrieval should be disabled (no embeddings)
        # sigma_novelty should be enabled (canonical fields populated)
        cap_service = CapabilityService(sigma_repo_path=str(sigma_repo))

        # Mock DB to reflect post-metadata-index state
        def mock_count_side_effect(*args, **kwargs):
            return 0  # No embedded rules

        mock_session.query.return_value.filter.return_value.count.return_value = 0
        caps = cap_service.compute_capabilities(db_session=mock_session)

        assert caps["sigma_retrieval"]["enabled"] is False
        assert "action" in caps["sigma_retrieval"]
        assert caps["sigma_metadata_indexing"]["enabled"] is True
```

**Step 2: Run test**

Run: `python -m pytest tests/integration/test_sigma_decoupled_indexing.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_sigma_decoupled_indexing.py
git commit -m "test: add integration test for decoupled sigma indexing flow"
```

---

## Task 11: Final verification and cleanup

**Step 1: Run full test suite for modified files**

```bash
python -m pytest tests/services/test_sigma_sync_metadata.py tests/services/test_sigma_sync_embeddings.py tests/services/test_sigma_sync_orchestrator.py tests/services/test_capability_service.py tests/api/test_capabilities_api.py tests/api/test_chat_capabilities.py tests/worker/test_sigma_celery_task.py tests/integration/test_sigma_decoupled_indexing.py -v
```

Expected: All PASS

**Step 2: Run existing sigma-related tests to verify no regressions**

```bash
python -m pytest tests/ -k "sigma" -v --timeout=60
```

Expected: All existing tests PASS (or identified failures are pre-existing)

**Step 3: Verify CLI commands work**

```bash
python -m src.cli.main sigma --help
python -m src.cli.main capabilities --help
```

Expected: Shows `index`, `index-metadata`, `index-embeddings`, `backfill-metadata` subcommands and `capabilities check` command.

**Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final cleanup for sigma indexing decoupling"
```

---

Plan complete and saved to `docs/plans/2026-03-07-decouple-sigma-indexing.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?