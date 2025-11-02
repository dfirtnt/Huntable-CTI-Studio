"""
Workflow Trigger Service for agentic workflow.

Handles triggering the agentic workflow when articles with high hunt scores are created or updated.
"""

import logging
from typing import Optional
from sqlalchemy.orm import Session

from src.database.models import ArticleTable, AgenticWorkflowConfigTable, AgenticWorkflowExecutionTable
from src.worker.celery_app import trigger_agentic_workflow

logger = logging.getLogger(__name__)


class WorkflowTriggerService:
    """Service for triggering agentic workflow on articles."""
    
    def __init__(self, db_session: Session):
        """Initialize workflow trigger service with database session."""
        self.db = db_session
    
    def get_active_config(self) -> Optional[AgenticWorkflowConfigTable]:
        """Get the active workflow configuration."""
        try:
            config = self.db.query(AgenticWorkflowConfigTable).filter(
                AgenticWorkflowConfigTable.is_active == True
            ).order_by(
                AgenticWorkflowConfigTable.version.desc()
            ).first()
            
            if not config:
                # Create default config if none exists
                config = AgenticWorkflowConfigTable(
                    min_hunt_score=97.0,
                    ranking_threshold=6.0,
                    similarity_threshold=0.5,
                    version=1,
                    is_active=True,
                    description="Default configuration"
                )
                self.db.add(config)
                self.db.commit()
                logger.info("Created default agentic workflow configuration")
            
            return config
            
        except Exception as e:
            logger.error(f"Error getting workflow config: {e}")
            return None
    
    def should_trigger_workflow(self, article: ArticleTable) -> bool:
        """
        Check if workflow should be triggered for an article.
        
        Args:
            article: Article to check
        
        Returns:
            True if workflow should be triggered
        """
        try:
            config = self.get_active_config()
            if not config:
                return False
            
            # Get hunt score from article metadata
            hunt_score = article.article_metadata.get('threat_hunting_score', 0) if article.article_metadata else 0
            
            # Check if score meets threshold
            if hunt_score < config.min_hunt_score:
                logger.debug(f"Article {article.id} hunt score {hunt_score} below threshold {config.min_hunt_score}")
                return False
            
            # Check if workflow already running or completed for this article
            existing_execution = self.db.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.article_id == article.id,
                AgenticWorkflowExecutionTable.status.in_(['pending', 'running'])
            ).first()
            
            if existing_execution:
                logger.debug(f"Article {article.id} already has active workflow execution")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking if workflow should trigger for article {article.id}: {e}")
            return False
    
    def trigger_workflow(self, article_id: int) -> bool:
        """
        Trigger agentic workflow for an article.
        
        Args:
            article_id: ID of article to process
        
        Returns:
            True if workflow was triggered successfully
        """
        try:
            article = self.db.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                logger.error(f"Article {article_id} not found")
                return False
            
            if not self.should_trigger_workflow(article):
                return False
            
            # Create execution record
            config = self.get_active_config()
            execution = AgenticWorkflowExecutionTable(
                article_id=article_id,
                status='pending',
                config_snapshot={
                    'min_hunt_score': config.min_hunt_score,
                    'ranking_threshold': config.ranking_threshold,
                    'similarity_threshold': config.similarity_threshold,
                    'config_id': config.id,
                    'config_version': config.version
                } if config else None
            )
            self.db.add(execution)
            self.db.commit()
            self.db.refresh(execution)
            
            logger.info(f"Triggering agentic workflow for article {article_id} (execution_id: {execution.id})")
            
            # Dispatch Celery task
            trigger_agentic_workflow.delay(article_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error triggering workflow for article {article_id}: {e}")
            return False

