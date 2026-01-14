"""
Sigma Repository Sync Service

Syncs and indexes Sigma detection rules from the SigmaHQ repository.
Parses YAML rules, generates embeddings, and stores in database for semantic search.
"""

import logging
import os
import yaml
import json
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path

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
        
    def clone_or_pull_repository(self) -> Dict[str, Any]:
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
                    ["git", "pull"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode != 0:
                    raise Exception(f"Git pull failed: {result.stderr}")
                
                logger.info("Successfully pulled latest Sigma rules")
                return {
                    "success": True,
                    "action": "pulled",
                    "message": "Repository updated successfully"
                }
            else:
                logger.info("Cloning Sigma repository...")
                self.ensure_repo_dir()
                
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", 
                     "https://github.com/SigmaHQ/sigma.git", 
                     str(self.repo_path)],
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                
                if result.returncode != 0:
                    raise Exception(f"Git clone failed: {result.stderr}")
                
                logger.info("Successfully cloned Sigma repository")
                return {
                    "success": True,
                    "action": "cloned",
                    "message": "Repository cloned successfully"
                }
                
        except subprocess.TimeoutExpired:
            logger.error("Git operation timed out")
            raise Exception("Git operation timed out")
        except Exception as e:
            logger.error(f"Failed to sync Sigma repository: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_repo_commit_sha(self) -> Optional[str]:
        """Get the current commit SHA of the repository."""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.error(f"Failed to get commit SHA: {e}")
            return None
    
    def find_rule_files(self) -> List[Path]:
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
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                if file.endswith('.yml') or file.endswith('.yaml'):
                    rule_files.append(Path(root) / file)
        
        logger.info(f"Found {len(rule_files)} rule files")
        return rule_files
    
    def parse_rule_file(self, file_path: Path) -> Optional[Dict]:
        """
        Parse a single Sigma rule YAML file.
        
        Args:
            file_path: Path to the rule file
            
        Returns:
            Dictionary containing parsed rule data
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                rule_data = yaml.safe_load(f)
            
            if not rule_data or not isinstance(rule_data, dict):
                logger.debug(f"Invalid rule file: {file_path}")
                return None
            
            # Extract key fields
            parsed = {
                'rule_id': rule_data.get('id', str(uuid.uuid4())),
                'title': rule_data.get('title', ''),
                'description': rule_data.get('description', ''),
                'logsource': rule_data.get('logsource', {}),
                'detection': rule_data.get('detection', {}),
                'tags': rule_data.get('tags', []),
                'level': rule_data.get('level', ''),
                'status': rule_data.get('status', ''),
                'author': rule_data.get('author', ''),
                'date': rule_data.get('date', ''),
                'rule_references': rule_data.get('references', []),
                'false_positives': rule_data.get('falsepositives', []),
                'fields': rule_data.get('fields', []),
                'file_path': str(file_path.relative_to(self.repo_path)),
            }
            
            # Convert date to datetime if present
            if parsed['date']:
                try:
                    # Handle if it's already a date object
                    import datetime as dt
                    if isinstance(parsed['date'], dt.date):
                        parsed['date'] = datetime.combine(parsed['date'], dt.time.min)
                    elif isinstance(parsed['date'], datetime):
                        # Already a datetime, keep it
                        pass
                    elif isinstance(parsed['date'], str):
                        # Parse from string
                        parsed['date'] = datetime.strptime(parsed['date'], '%Y/%m/%d')
                    else:
                        parsed['date'] = None
                except (ValueError, AttributeError, TypeError):
                    parsed['date'] = None
            
            return parsed
            
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing rule file {file_path}: {e}")
            return None
    
    def create_rule_embedding_text(self, rule_data: Dict) -> str:
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
        import json
        parts = []
        
        # === SEMANTIC LAYER (20% weight total) ===
        # Title (repeat 1x for 10% weight)
        if rule_data.get('title'):
            parts.append(f"Title: {rule_data['title']}")
        
        # Description (repeat 1x for 10% weight)
        if rule_data.get('description'):
            parts.append(f"Description: {rule_data['description']}")
        
        # === CLASSIFICATION LAYER (10% weight) ===
        # Strip "attack." prefix from MITRE ATT&CK tags but keep technique identifiers
        # Example: "attack.t1059.001" -> "t1059.001", "attack.execution" -> "execution"
        # The "attack." prefix is classification metadata; technique IDs are detection-relevant
        tags = rule_data.get('tags', [])
        if tags:
            processed_tags = []
            for tag in tags:
                if tag.startswith('attack.'):
                    # Remove "attack." prefix, keep the technique identifier
                    processed_tags.append(tag[7:])  # len("attack.") = 7
                else:
                    # Keep non-attack tags as-is
                    processed_tags.append(tag)
            if processed_tags:
                parts.append(', '.join(processed_tags))
        
        # === PLATFORM LAYER (25% weight) ===
        # Logsource (repeat 5x for 25% weight)
        logsource = rule_data.get('logsource', {})
        if isinstance(logsource, dict) and logsource:
            logsource_str = json.dumps(logsource, separators=(',', ':'))
            parts.extend([f"Logsource: {logsource_str}"] * 5)
        
        # === BEHAVIORAL LAYER (45% weight) ===
        # Detection logic (repeat 9x for 45% weight)
        detection = rule_data.get('detection', {})
        if isinstance(detection, dict) and detection:
            # Serialize full detection logic including all patterns
            detection_str = json.dumps(detection, separators=(',', ':'))
            parts.extend([f"Detection: {detection_str}"] * 9)
        
        return ' '.join(parts)
    
    def create_title_embedding_text(self, rule_data: Dict) -> str:
        """Create embedding text for title section."""
        title = rule_data.get('title', '')
        return title if title else ""
    
    def create_description_embedding_text(self, rule_data: Dict) -> str:
        """Create embedding text for description section."""
        description = rule_data.get('description', '')
        return description if description else ""
    
    def create_tags_embedding_text(self, rule_data: Dict) -> str:
        """Create embedding text for tags section."""
        tags = rule_data.get('tags', [])
        if tags:
            # Strip "attack." prefix from MITRE ATT&CK tags but keep the technique identifiers
            # Example: "attack.t1059.001" -> "t1059.001", "attack.execution" -> "execution"
            processed_tags = []
            for tag in tags:
                if tag.startswith('attack.'):
                    # Remove "attack." prefix, keep the technique identifier
                    processed_tags.append(tag[7:])  # len("attack.") = 7
                else:
                    # Keep non-attack tags as-is
                    processed_tags.append(tag)
            if processed_tags:
                return ', '.join(processed_tags)
        return ""
    
    def create_logsource_embedding_text(self, rule_data: Dict) -> str:
        """Create embedding text for logsource section (normalized to generic format)."""
        logsource = rule_data.get('logsource', {})
        if isinstance(logsource, dict) and logsource:
            # Extract values only (no keys like "product:", "service:", "category:")
            parts = []
            if logsource.get('category'):
                parts.append(logsource['category'])
            if logsource.get('product'):
                parts.append(logsource['product'])
            if logsource.get('service'):
                parts.append(logsource['service'])
            return ' '.join(parts) if parts else ""
        return ""
    
    def create_detection_structure_embedding_text(self, rule_data: Dict) -> str:
        """Create embedding text for detection structure section."""
        from src.services.sigma_detection_analyzer import analyze_detection_structure
        
        detection = rule_data.get('detection', {})
        if not detection or not isinstance(detection, dict):
            return ""
        
        structure = analyze_detection_structure(detection)
        
        parts = []
        
        # Selection information (values only, no prefixes)
        if structure['selection_count'] > 0:
            parts.append(str(structure['selection_count']))
            if structure['selection_keys']:
                # Remove "selection" prefix from keys if present
                keys = [k.replace('selection', '').strip() if k.startswith('selection') else k for k in sorted(structure['selection_keys'])]
                parts.append(', '.join(keys))
        
        # Nesting depth (value only)
        if structure['max_nesting_depth'] > 0:
            parts.append(str(structure['max_nesting_depth']))
        
        # Boolean operators (values only)
        if structure['boolean_operators']:
            operators = ', '.join(sorted(structure['boolean_operators']))
            parts.append(operators)
        
        # Unrolled condition (value only)
        if structure['condition_unrolled']:
            parts.append(structure['condition_unrolled'])
        
        # Modifiers (values only)
        if structure['modifiers']:
            modifiers = ', '.join(sorted(structure['modifiers']))
            parts.append(modifiers)
        
        return ' '.join(parts) if parts else ""
    
    def create_detection_fields_embedding_text(self, rule_data: Dict) -> str:
        """Create embedding text for detection fields section."""
        from src.services.sigma_detection_analyzer import analyze_detection_fields
        
        detection = rule_data.get('detection', {})
        if not detection or not isinstance(detection, dict):
            return ""
        
        fields_analysis = analyze_detection_fields(detection)
        
        parts = []
        
        # Include detection values (no prefix)
        if fields_analysis['normalized_values']:
            values = fields_analysis['normalized_values'][:30]  # Limit to avoid too long strings
            values_str = ', '.join(values[:15])  # Show first 15 unique values
            parts.append(values_str)
        
        # Field names (with modifiers) - mentioned once for context (no prefix)
        if fields_analysis['field_names_with_modifiers']:
            all_fields = []
            for field in fields_analysis['field_names_with_modifiers']:
                all_fields.append(field)
                # High-signal fields get mentioned twice
                base_field = field.split('|')[0]
                if base_field in fields_analysis['high_signal_fields']:
                    all_fields.append(field)
            
            parts.append(', '.join(all_fields))
        
        # High-signal fields emphasis (context only, no prefix)
        if fields_analysis['high_signal_fields']:
            high_signal = ', '.join(set(fields_analysis['high_signal_fields']))
            parts.append(high_signal)
        
        return ' '.join(parts) if parts else ""
    
    def create_signature_embedding_text(self, rule_data: Dict) -> str:
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
        
        return ' '.join(parts) if parts else ""
    
    def create_section_embeddings_text(self, rule_data: Dict) -> Dict[str, str]:
        """
        Generate separate embedding text for each section.
        
        Args:
            rule_data: Parsed rule data
            
        Returns:
            Dictionary mapping section names to embedding text
        """
        return {
            'title': self.create_title_embedding_text(rule_data),
            'description': self.create_description_embedding_text(rule_data),
            'tags': self.create_tags_embedding_text(rule_data),
            'signature': self.create_signature_embedding_text(rule_data)
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
    
    def index_rules(self, db_session, force_reindex: bool = False) -> int:
        """
        Index all rules from the repository into the database.
        
        Args:
            db_session: SQLAlchemy session
            force_reindex: If True, reindex all rules even if they exist
            
        Returns:
            Number of rules indexed
        """
        from src.database.models import SigmaRuleTable
        from src.services.lmstudio_embedding_client import LMStudioEmbeddingClient
        
        logger.info("Starting Sigma rule indexing...")
        
        # Get existing rule IDs if not forcing reindex
        existing_rule_ids = set()
        if not force_reindex:
            existing_rule_ids = self.get_existing_rule_ids(db_session)
            logger.info(f"Found {len(existing_rule_ids)} existing rules")
        
        # Find all rule files
        rule_files = self.find_rule_files()
        
        # Get commit SHA
        commit_sha = self.get_repo_commit_sha()
        
        # Parse and index rules
        indexed_count = 0
        skipped_count = 0
        error_count = 0
        
        # Initialize LM Studio embedding client
        try:
            embedding_service = LMStudioEmbeddingClient()
            logger.info("LM Studio embedding client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize LM Studio embedding client: {e}")
            raise RuntimeError("LM Studio embedding client unavailable") from e
        
        for file_path in rule_files:
            try:
                # Parse rule
                rule_data = self.parse_rule_file(file_path)
                
                if not rule_data:
                    skipped_count += 1
                    continue
                
                rule_id = rule_data['rule_id']
                
                # Skip if already indexed (unless force reindex)
                if not force_reindex and rule_id in existing_rule_ids:
                    skipped_count += 1
                    continue
                
                # Generate embeddings using LM Studio
                # Generate main embedding (for backward compatibility)
                embedding_text = self.create_rule_embedding_text(rule_data)
                embedding = embedding_service.generate_embedding(embedding_text)
                
                # Generate section-based embeddings
                section_texts = self.create_section_embeddings_text(rule_data)
                
                # Generate embeddings for each section (batch for efficiency)
                section_texts_list = [
                    section_texts['title'],
                    section_texts['description'],
                    section_texts['tags'],
                    section_texts['signature']
                ]
                
                section_embeddings = embedding_service.generate_embeddings_batch(section_texts_list)
                
                # Handle cases where batch might return fewer embeddings than expected
                while len(section_embeddings) < 4:
                    section_embeddings.append([0.0] * 768)  # Zero vector for missing sections
                
                title_emb = section_embeddings[0] if section_embeddings[0] and len(section_embeddings[0]) == 768 else None
                description_emb = section_embeddings[1] if section_embeddings[1] and len(section_embeddings[1]) == 768 else None
                tags_emb = section_embeddings[2] if section_embeddings[2] and len(section_embeddings[2]) == 768 else None
                signature_emb = section_embeddings[3] if section_embeddings[3] and len(section_embeddings[3]) == 768 else None
                
                # For backward compatibility, store signature in all three fields
                logsource_emb = signature_emb
                detection_structure_emb = signature_emb
                detection_fields_emb = signature_emb
                
                # Store model name for tracking
                embedding_model_name = "intfloat/e5-base-v2"
                
                # Compute canonical fields for behavioral novelty assessment
                try:
                    from src.services.sigma_novelty_service import SigmaNoveltyService
                    novelty_service = SigmaNoveltyService(db_session=db_session)
                    canonical_rule = novelty_service.build_canonical_rule(rule_data)
                    
                    import json
                    from dataclasses import asdict
                    canonical_json = asdict(canonical_rule)
                    exact_hash = novelty_service.generate_exact_hash(canonical_rule)
                    canonical_text = novelty_service.generate_canonical_text(canonical_rule)
                    logsource_key = novelty_service.normalize_logsource(rule_data.get('logsource', {}))
                except Exception as e:
                    logger.warning(f"Failed to compute canonical fields for rule {rule_id}: {e}")
                    canonical_json = None
                    exact_hash = None
                    canonical_text = None
                    logsource_key = None
                
                # Create or update rule record (with no autoflush to prevent premature commits)
                with db_session.no_autoflush:
                    existing_rule = db_session.query(SigmaRuleTable).filter_by(rule_id=rule_id).first()
                    
                    if existing_rule:
                        # Update existing rule
                        for key, value in rule_data.items():
                            if key != 'rule_id':
                                setattr(existing_rule, key, value)
                        existing_rule.embedding = embedding
                        existing_rule.embedding_model = embedding_model_name
                        existing_rule.embedded_at = datetime.now()
                        existing_rule.repo_commit_sha = commit_sha
                        # Update section embeddings
                        existing_rule.title_embedding = title_emb
                        existing_rule.description_embedding = description_emb
                        existing_rule.tags_embedding = tags_emb
                        existing_rule.logsource_embedding = logsource_emb
                        existing_rule.detection_structure_embedding = detection_structure_emb
                        existing_rule.detection_fields_embedding = detection_fields_emb
                        # Update canonical fields
                        existing_rule.canonical_json = canonical_json
                        existing_rule.exact_hash = exact_hash
                        existing_rule.canonical_text = canonical_text
                        existing_rule.logsource_key = logsource_key
                    else:
                        # Create new rule
                        new_rule = SigmaRuleTable(
                            rule_id=rule_id,
                            title=rule_data['title'],
                            description=rule_data['description'],
                            logsource=rule_data['logsource'],
                            detection=rule_data['detection'],
                            tags=rule_data['tags'],
                            level=rule_data['level'],
                            status=rule_data['status'],
                            author=rule_data['author'],
                            date=rule_data['date'],
                            rule_references=rule_data['rule_references'],
                            false_positives=rule_data['false_positives'],
                            fields=rule_data['fields'],
                            file_path=rule_data['file_path'],
                            repo_commit_sha=commit_sha,
                            embedding=embedding,
                            embedding_model=embedding_model_name,
                            embedded_at=datetime.now(),
                            # Section embeddings
                            title_embedding=title_emb,
                            description_embedding=description_emb,
                            tags_embedding=tags_emb,
                            logsource_embedding=logsource_emb,
                            detection_structure_embedding=detection_structure_emb,
                            detection_fields_embedding=detection_fields_emb,
                            # Canonical fields
                            canonical_json=canonical_json,
                            exact_hash=exact_hash,
                            canonical_text=canonical_text,
                            logsource_key=logsource_key
                        )
                        db_session.add(new_rule)
                
                indexed_count += 1
                
                if indexed_count % 100 == 0:
                    logger.info(f"Indexed {indexed_count} rules...")
                    db_session.commit()
                    
            except Exception as e:
                logger.error(f"Error indexing rule file {file_path}: {e}")
                error_count += 1
                continue
        
        # Final commit
        db_session.commit()
        
        logger.info(f"Indexing complete: {indexed_count} indexed, {skipped_count} skipped, {error_count} errors")
        
        return indexed_count
    
    async def sync(self, db_session, force_reindex: bool = False) -> Dict[str, Any]:
        """
        Complete sync operation: clone/pull repo, index rules.
        
        Args:
            db_session: SQLAlchemy session
            force_reindex: If True, reindex all rules even if they exist
            
        Returns:
            Dictionary with sync results
        """
        try:
            # Sync repository
            sync_result = self.clone_or_pull_repository()
            
            if not sync_result['success']:
                return sync_result
            
            # Index rules
            indexed_count = self.index_rules(db_session, force_reindex=force_reindex)
            
            return {
                "success": True,
                "action": sync_result['action'],
                "rules_indexed": indexed_count,
                "message": f"Successfully synced and indexed {indexed_count} rules"
            }
            
        except Exception as e:
            logger.error(f"Sigma sync failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

