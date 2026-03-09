"""
Sigma Repository Sync Service

Syncs and indexes Sigma detection rules from the SigmaHQ repository.
Parses YAML rules, generates embeddings, and stores in database for semantic search.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class SigmaSyncService:
    """Service for syncing and indexing Sigma rules from SigmaHQ repository."""

    def __init__(self, repo_path: str = "./data/sigma-repo"):
        """
        Initialize the Sigma sync service.

        Args:
            repo_path: Path to the SigmaHQ repository directory
        """
        self.repo_path = Path(repo_path)
        self.rules_path = self.repo_path / "rules"

    def ensure_repo_dir(self):
        """Ensure the repository directory exists."""
        self.repo_path.mkdir(parents=True, exist_ok=True)

    def clone_or_pull_repository(self) -> dict[str, Any]:
        """
        Clone or pull the SigmaHQ repository.

        Returns:
            Dictionary with sync status and metadata
        """
        try:
            import subprocess

            # Check if repo exists
            if (self.repo_path / ".git").exists():
                logger.info("Sigma repository exists, pulling latest changes...")
                result = subprocess.run(
                    ["git", "pull"], cwd=self.repo_path, capture_output=True, text=True, timeout=300
                )

                if result.returncode != 0:
                    raise Exception(f"Git pull failed: {result.stderr}")

                logger.info("Successfully pulled latest Sigma rules")
                return {"success": True, "action": "pulled", "message": "Repository updated successfully"}
            logger.info("Cloning Sigma repository...")
            self.ensure_repo_dir()

            result = subprocess.run(
                ["git", "clone", "--depth", "1", "https://github.com/SigmaHQ/sigma.git", str(self.repo_path)],
                capture_output=True,
                text=True,
                timeout=600,
            )

            if result.returncode != 0:
                raise Exception(f"Git clone failed: {result.stderr}")

            logger.info("Successfully cloned Sigma repository")
            return {"success": True, "action": "cloned", "message": "Repository cloned successfully"}

        except subprocess.TimeoutExpired as e:
            logger.error("Git operation timed out")
            raise Exception("Git operation timed out") from e
        except Exception as e:
            logger.error(f"Failed to sync Sigma repository: {e}")
            return {"success": False, "error": str(e)}

    def get_repo_commit_sha(self) -> str | None:
        """Get the current commit SHA of the repository."""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=self.repo_path, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.error(f"Failed to get commit SHA: {e}")
            return None

    def find_rule_files(self) -> list[Path]:
        """
        Find all Sigma rule YAML files in the repository.

        Returns:
            List of Path objects to rule files
        """
        if not self.rules_path.exists():
            logger.error(f"Rules directory not found: {self.rules_path}")
            return []

        rule_files = []
        for root, dirs, files in os.walk(self.rules_path):
            # Skip hidden directories and common non-rule directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for file in files:
                if file.endswith(".yml") or file.endswith(".yaml"):
                    rule_files.append(Path(root) / file)

        logger.info(f"Found {len(rule_files)} rule files")
        return rule_files

    def parse_rule_file(self, file_path: Path) -> dict | None:
        """
        Parse a single Sigma rule YAML file.

        Args:
            file_path: Path to the rule file

        Returns:
            Dictionary containing parsed rule data
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                rule_data = yaml.safe_load(f)

            if not rule_data or not isinstance(rule_data, dict):
                logger.debug(f"Invalid rule file: {file_path}")
                return None

            # Extract key fields
            parsed = {
                "rule_id": rule_data.get("id", str(uuid.uuid4())),
                "title": rule_data.get("title", ""),
                "description": rule_data.get("description", ""),
                "logsource": rule_data.get("logsource", {}),
                "detection": rule_data.get("detection", {}),
                "tags": rule_data.get("tags", []),
                "level": rule_data.get("level", ""),
                "status": rule_data.get("status", ""),
                "author": rule_data.get("author", ""),
                "date": rule_data.get("date", ""),
                "rule_references": rule_data.get("references", []),
                "false_positives": rule_data.get("falsepositives", []),
                "fields": rule_data.get("fields", []),
                "file_path": str(file_path.relative_to(self.repo_path)),
            }

            # Convert date to datetime if present
            if parsed["date"]:
                try:
                    # Handle if it's already a date object
                    import datetime as dt

                    if isinstance(parsed["date"], dt.date):
                        parsed["date"] = datetime.combine(parsed["date"], dt.time.min)
                    elif isinstance(parsed["date"], datetime):
                        # Already a datetime, keep it
                        pass
                    elif isinstance(parsed["date"], str):
                        # Parse from string
                        parsed["date"] = datetime.strptime(parsed["date"], "%Y/%m/%d")
                    else:
                        parsed["date"] = None
                except (ValueError, AttributeError, TypeError):
                    parsed["date"] = None

            return parsed

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing rule file {file_path}: {e}")
            return None

    def create_rule_embedding_text(self, rule_data: dict) -> str:
        """
        Create enriched text for embedding from a rule.
        Uses a weighted hybrid approach combining semantic (title/description)
        and technical (tags/logsource/detection) content.

        Weight distribution (via repetition):
        - Title: 10%
        - Description: 10%
        - Tags: 10% (strips "attack." prefix from MITRE tags, keeps technique identifiers)
        - Detection: 45% (full JSON structure)
        - Logsource: 25% (platform/product info)

        Note: This method is maintained for backward compatibility (generating main sr.embedding).
        For new similarity searches, use create_section_embeddings_text() with standardized weights.

        Args:
            rule_data: Parsed rule data

        Returns:
            Enriched text string for embedding
        """
        parts = []

        # === SEMANTIC LAYER (20% weight total) ===
        # Title (repeat 1x for 10% weight)
        if rule_data.get("title"):
            parts.append(f"Title: {rule_data['title']}")

        # Description (repeat 1x for 10% weight)
        if rule_data.get("description"):
            parts.append(f"Description: {rule_data['description']}")

        # === CLASSIFICATION LAYER (10% weight) ===
        # Strip "attack." prefix from MITRE ATT&CK tags but keep technique identifiers
        # Example: "attack.t1059.001" -> "t1059.001", "attack.execution" -> "execution"
        # The "attack." prefix is classification metadata; technique IDs are detection-relevant
        tags = rule_data.get("tags", [])
        if tags:
            processed_tags = []
            for tag in tags:
                if tag.startswith("attack."):
                    # Remove "attack." prefix, keep the technique identifier
                    processed_tags.append(tag[7:])  # len("attack.") = 7
                else:
                    # Keep non-attack tags as-is
                    processed_tags.append(tag)
            if processed_tags:
                parts.append(", ".join(processed_tags))

        # === PLATFORM LAYER (25% weight) ===
        # Logsource (repeat 5x for 25% weight)
        logsource = rule_data.get("logsource", {})
        if isinstance(logsource, dict) and logsource:
            logsource_str = json.dumps(logsource, separators=(",", ":"))
            parts.extend([f"Logsource: {logsource_str}"] * 5)

        # === BEHAVIORAL LAYER (45% weight) ===
        # Detection logic (repeat 9x for 45% weight)
        detection = rule_data.get("detection", {})
        if isinstance(detection, dict) and detection:
            # Serialize full detection logic including all patterns
            detection_str = json.dumps(detection, separators=(",", ":"))
            parts.extend([f"Detection: {detection_str}"] * 9)

        return " ".join(parts)

    def create_title_embedding_text(self, rule_data: dict) -> str:
        """Create embedding text for title section."""
        title = rule_data.get("title", "")
        return title if title else ""

    def create_description_embedding_text(self, rule_data: dict) -> str:
        """Create embedding text for description section."""
        description = rule_data.get("description", "")
        return description if description else ""

    def create_tags_embedding_text(self, rule_data: dict) -> str:
        """Create embedding text for tags section."""
        tags = rule_data.get("tags", [])
        if tags:
            # Strip "attack." prefix from MITRE ATT&CK tags but keep the technique identifiers
            # Example: "attack.t1059.001" -> "t1059.001", "attack.execution" -> "execution"
            processed_tags = []
            for tag in tags:
                if tag.startswith("attack."):
                    # Remove "attack." prefix, keep the technique identifier
                    processed_tags.append(tag[7:])  # len("attack.") = 7
                else:
                    # Keep non-attack tags as-is
                    processed_tags.append(tag)
            if processed_tags:
                return ", ".join(processed_tags)
        return ""

    def create_logsource_embedding_text(self, rule_data: dict) -> str:
        """Create embedding text for logsource section (normalized to generic format)."""
        logsource = rule_data.get("logsource", {})
        if isinstance(logsource, dict) and logsource:
            # Extract values only (no keys like "product:", "service:", "category:")
            parts = []
            if logsource.get("category"):
                parts.append(logsource["category"])
            if logsource.get("product"):
                parts.append(logsource["product"])
            if logsource.get("service"):
                parts.append(logsource["service"])
            return " ".join(parts) if parts else ""
        return ""

    def create_detection_structure_embedding_text(self, rule_data: dict) -> str:
        """Create embedding text for detection structure section."""
        from src.services.sigma_detection_analyzer import analyze_detection_structure

        detection = rule_data.get("detection", {})
        if not detection or not isinstance(detection, dict):
            return ""

        structure = analyze_detection_structure(detection)

        parts = []

        # Selection information (values only, no prefixes)
        if structure["selection_count"] > 0:
            parts.append(str(structure["selection_count"]))
            if structure["selection_keys"]:
                # Remove "selection" prefix from keys if present
                keys = [
                    k.replace("selection", "").strip() if k.startswith("selection") else k
                    for k in sorted(structure["selection_keys"])
                ]
                parts.append(", ".join(keys))

        # Nesting depth (value only)
        if structure["max_nesting_depth"] > 0:
            parts.append(str(structure["max_nesting_depth"]))

        # Boolean operators (values only)
        if structure["boolean_operators"]:
            operators = ", ".join(sorted(structure["boolean_operators"]))
            parts.append(operators)

        # Unrolled condition (value only)
        if structure["condition_unrolled"]:
            parts.append(structure["condition_unrolled"])

        # Modifiers (values only)
        if structure["modifiers"]:
            modifiers = ", ".join(sorted(structure["modifiers"]))
            parts.append(modifiers)

        return " ".join(parts) if parts else ""

    def create_detection_fields_embedding_text(self, rule_data: dict) -> str:
        """Create embedding text for detection fields section."""
        from src.services.sigma_detection_analyzer import analyze_detection_fields

        detection = rule_data.get("detection", {})
        if not detection or not isinstance(detection, dict):
            return ""

        fields_analysis = analyze_detection_fields(detection)

        parts = []

        # Include detection values (no prefix)
        if fields_analysis["normalized_values"]:
            values = fields_analysis["normalized_values"][:30]  # Limit to avoid too long strings
            values_str = ", ".join(values[:15])  # Show first 15 unique values
            parts.append(values_str)

        # Field names (with modifiers) - mentioned once for context (no prefix)
        if fields_analysis["field_names_with_modifiers"]:
            all_fields = []
            for field in fields_analysis["field_names_with_modifiers"]:
                all_fields.append(field)
                # High-signal fields get mentioned twice
                base_field = field.split("|")[0]
                if base_field in fields_analysis["high_signal_fields"]:
                    all_fields.append(field)

            parts.append(", ".join(all_fields))

        # High-signal fields emphasis (context only, no prefix)
        if fields_analysis["high_signal_fields"]:
            high_signal = ", ".join(set(fields_analysis["high_signal_fields"]))
            parts.append(high_signal)

        return " ".join(parts) if parts else ""

    def create_signature_embedding_text(self, rule_data: dict) -> str:
        """Create combined embedding text for logsource and detection (signature)."""
        parts = []

        # Add logsource
        logsource_text = self.create_logsource_embedding_text(rule_data)
        if logsource_text:
            parts.append(logsource_text)

        # Add detection structure
        detection_structure_text = self.create_detection_structure_embedding_text(rule_data)
        if detection_structure_text:
            parts.append(detection_structure_text)

        # Add detection fields
        detection_fields_text = self.create_detection_fields_embedding_text(rule_data)
        if detection_fields_text:
            parts.append(detection_fields_text)

        return " ".join(parts) if parts else ""

    def create_section_embeddings_text(self, rule_data: dict) -> dict[str, str]:
        """
        Generate separate embedding text for each section.

        Args:
            rule_data: Parsed rule data

        Returns:
            Dictionary mapping section names to embedding text
        """
        return {
            "title": self.create_title_embedding_text(rule_data),
            "description": self.create_description_embedding_text(rule_data),
            "tags": self.create_tags_embedding_text(rule_data),
            "signature": self.create_signature_embedding_text(rule_data),
        }

    def get_existing_rule_ids(self, db_session) -> set:
        """
        Get set of existing rule IDs from database.

        Args:
            db_session: SQLAlchemy session

        Returns:
            Set of rule IDs
        """
        from src.database.models import SigmaRuleTable

        try:
            existing_rules = db_session.query(SigmaRuleTable.rule_id).all()
            return {rule[0] for rule in existing_rules}
        except Exception as e:
            logger.error(f"Error getting existing rule IDs: {e}")
            return set()

    def index_metadata(self, db_session, force_reindex: bool = False) -> dict[str, int]:
        """
        Index metadata and canonical fields for all rules — no embeddings.

        Parses YAML files, stores rule metadata columns, and computes canonical
        novelty fields (canonical_json, exact_hash, canonical_text, logsource_key).
        Embedding columns are left as None.

        Args:
            db_session: SQLAlchemy session
            force_reindex: If True, reindex all rules even if they exist

        Returns:
            Dictionary with metadata_indexed, skipped, and errors counts
        """
        from src.database.models import SigmaRuleTable

        logger.info("Starting Sigma rule metadata indexing...")

        # Get existing rule IDs if not forcing reindex
        existing_rule_ids = set()
        if not force_reindex:
            existing_rule_ids = self.get_existing_rule_ids(db_session)
            logger.info(f"Found {len(existing_rule_ids)} existing rules")

        # Find all rule files
        rule_files = self.find_rule_files()

        # Get commit SHA
        commit_sha = self.get_repo_commit_sha()

        # Allowlist of SigmaRuleTable columns that may be updated from rule_data
        _UPDATABLE_COLUMNS = frozenset(
            {
                "title",
                "description",
                "logsource",
                "detection",
                "tags",
                "level",
                "status",
                "author",
                "date",
                "rule_references",
                "false_positives",
                "fields",
                "file_path",
            }
        )

        # Initialize novelty service once (outside the loop)
        from dataclasses import asdict

        novelty_service = None
        try:
            from src.services.sigma_novelty_service import SigmaNoveltyService

            novelty_service = SigmaNoveltyService(db_session=db_session)
        except Exception as e:
            logger.warning(f"Failed to initialize SigmaNoveltyService; canonical fields will be skipped: {e}")

        # Parse and index rules
        indexed_count = 0
        skipped_count = 0
        error_count = 0

        for file_path in rule_files:
            try:
                # Parse rule
                rule_data = self.parse_rule_file(file_path)

                if not rule_data:
                    skipped_count += 1
                    continue

                rule_id = rule_data["rule_id"]

                # Skip if already indexed (unless force reindex)
                if not force_reindex and rule_id in existing_rule_ids:
                    skipped_count += 1
                    continue

                # Compute canonical fields for behavioral novelty assessment
                canonical_json = None
                exact_hash = None
                canonical_text = None
                logsource_key = None
                if novelty_service is not None:
                    try:
                        canonical_rule = novelty_service.build_canonical_rule(rule_data)
                        canonical_json = asdict(canonical_rule)
                        exact_hash = novelty_service.generate_exact_hash(canonical_rule)
                        canonical_text = novelty_service.generate_canonical_text(canonical_rule)
                        logsource_key, _ = novelty_service.normalize_logsource(rule_data.get("logsource", {}))
                    except Exception as e:
                        logger.warning(f"Failed to compute canonical fields for rule {rule_id}: {e}")

                # Create or update rule record (with no autoflush to prevent premature commits)
                with db_session.no_autoflush:
                    existing_rule = db_session.query(SigmaRuleTable).filter_by(rule_id=rule_id).first()

                    if existing_rule:
                        # Update existing rule metadata (allowlisted columns only)
                        for key, value in rule_data.items():
                            if key in _UPDATABLE_COLUMNS:
                                setattr(existing_rule, key, value)
                        existing_rule.repo_commit_sha = commit_sha
                        # Update canonical fields
                        existing_rule.canonical_json = canonical_json
                        existing_rule.exact_hash = exact_hash
                        existing_rule.canonical_text = canonical_text
                        existing_rule.logsource_key = logsource_key
                    else:
                        # Create new rule (embedding columns left as None)
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
                            # Canonical fields
                            canonical_json=canonical_json,
                            exact_hash=exact_hash,
                            canonical_text=canonical_text,
                            logsource_key=logsource_key,
                        )
                        db_session.add(new_rule)

                indexed_count += 1

                if indexed_count % 100 == 0:
                    logger.info(f"Metadata-indexed {indexed_count} rules...")
                    db_session.commit()

            except Exception as e:
                logger.error(f"Error indexing rule metadata for {file_path}: {e}")
                db_session.rollback()
                error_count += 1
                continue

        # Final commit
        db_session.commit()

        logger.info(
            f"Metadata indexing complete: {indexed_count} indexed, {skipped_count} skipped, {error_count} errors"
        )

        return {"metadata_indexed": indexed_count, "skipped": skipped_count, "errors": error_count}

    def index_embeddings(self, db_session, force_reindex: bool = False, progress_callback=None) -> dict:
        """
        Generate embeddings for Sigma rules that lack them.

        Uses local sentence-transformers (intfloat/e5-base-v2), no LMStudio dependency.

        Args:
            db_session: SQLAlchemy session
            force_reindex: If True, regenerate embeddings for all rules
            progress_callback: Optional callable(current, total) called after each rule

        Returns:
            Dict with embeddings_indexed, skipped, errors counts
        """
        from src.database.models import SigmaRuleTable

        logger.info("Starting Sigma rule embedding generation...")

        # Initialize local embedding service (lazy import to avoid breaking
        # metadata-only paths when sentence-transformers is unavailable)
        try:
            from src.services.embedding_service import EmbeddingService

            embedding_service = EmbeddingService(model_name="intfloat/e5-base-v2")
        except Exception as e:
            logger.error(f"Failed to initialize embedding service: {e}")
            return {"embeddings_indexed": 0, "skipped": 0, "errors": 1, "error": str(e)}

        # Get rules that need embeddings
        if force_reindex:
            rules = db_session.query(SigmaRuleTable).all()
        else:
            rules = db_session.query(SigmaRuleTable).filter(SigmaRuleTable.embedding.is_(None)).all()

        logger.info(f"Found {len(rules)} rules needing embeddings")

        embeddings_indexed = 0
        error_count = 0
        embedding_model_name = "intfloat/e5-base-v2"

        for rule in rules:
            try:
                rule_data = {
                    "title": rule.title,
                    "description": rule.description,
                    "tags": rule.tags or [],
                    "logsource": rule.logsource or {},
                    "detection": rule.detection or {},
                }

                embedding_text = self.create_rule_embedding_text(rule_data)
                embedding = embedding_service.generate_embedding(embedding_text)

                section_texts = self.create_section_embeddings_text(rule_data)
                section_embeddings = embedding_service.generate_embeddings_batch(
                    [
                        section_texts["title"],
                        section_texts["description"],
                        section_texts["tags"],
                        section_texts["signature"],
                    ]
                )

                while len(section_embeddings) < 4:
                    section_embeddings.append([0.0] * 768)

                def _valid(emb):
                    return emb if emb and len(emb) == 768 else None

                rule.embedding = embedding
                rule.embedding_model = embedding_model_name
                rule.embedded_at = datetime.now()
                rule.title_embedding = _valid(section_embeddings[0])
                rule.description_embedding = _valid(section_embeddings[1])
                rule.tags_embedding = _valid(section_embeddings[2])
                sig_emb = _valid(section_embeddings[3])
                rule.logsource_embedding = sig_emb
                rule.detection_structure_embedding = sig_emb
                rule.detection_fields_embedding = sig_emb

                embeddings_indexed += 1
                if progress_callback:
                    progress_callback(embeddings_indexed + error_count, len(rules))
                if embeddings_indexed % 100 == 0:
                    logger.info(f"Embedded {embeddings_indexed} rules...")
                    db_session.flush()

            except Exception as e:
                error_count += 1
                if progress_callback:
                    progress_callback(embeddings_indexed + error_count, len(rules))
                logger.error(f"Error generating embeddings for rule {rule.rule_id}: {e}")
                continue

        db_session.commit()
        skipped = len(rules) - embeddings_indexed - error_count
        logger.info(
            f"Embedding generation complete: {embeddings_indexed} indexed, {skipped} skipped, {error_count} errors"
        )
        return {
            "embeddings_indexed": embeddings_indexed,
            "skipped": max(0, skipped),
            "errors": error_count,
        }

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
            f"Indexing complete: {result['metadata_indexed']} metadata, {result['embeddings_indexed']} embeddings"
        )
        return result

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
