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
        - MITRE Tags: 10% (only tags starting with attack.)
        - Detection: 45% (full JSON structure)
        - Logsource: 25% (platform/product info)
        
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
        # MITRE ATT&CK tags (repeat 1x for 10% weight)
        tags = rule_data.get('tags', [])
        if tags:
            attack_tags = [t for t in tags if t.startswith('attack.')]
            if attack_tags:
                parts.append(f"MITRE: {', '.join(attack_tags)}")
        
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
                
                # Generate embedding using LM Studio
                embedding_text = self.create_rule_embedding_text(rule_data)
                embedding = embedding_service.generate_embedding(embedding_text)
                
                # Store model name for tracking
                embedding_model_name = "intfloat/e5-base-v2"
                
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
                            embedded_at=datetime.now()
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

