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
                "sigma_customer_repo_indexed": self._check_sigma_customer_repo_indexed(session),
                "sigma_novelty_comparison": self._check_sigma_novelty(session),
                "llm_generation": self._check_llm_generation(),
            }
        finally:
            if close_session and hasattr(session, "close"):
                session.close()

    def _check_article_retrieval(self, session) -> dict:
        try:
            from src.database.models import ArticleTable

            count = session.query(ArticleTable).filter(ArticleTable.embedding.isnot(None)).count()
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

            count = session.query(SigmaRuleTable).filter(SigmaRuleTable.embedding.isnot(None)).count()
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

    def _check_sigma_customer_repo_indexed(self, session) -> dict:
        """Whether approved rules from the customer repo are indexed for similarity search (rule_id like 'cust-%')."""
        try:
            from sqlalchemy import func

            from src.database.models import SigmaRuleTable

            count = (
                session.query(func.count(SigmaRuleTable.id)).filter(SigmaRuleTable.rule_id.startswith("cust-")).scalar()
                or 0
            )
            if count > 0:
                return {
                    "enabled": True,
                    "count": count,
                    "reason": f"{count} rules from your repo included in similarity search",
                }
            return {
                "enabled": False,
                "count": 0,
                "reason": "Similarity search uses SigmaHQ only",
                "action": "Run sigma index-customer-repo to include your approved rules",
            }
        except Exception as e:
            return {"enabled": False, "reason": f"Check failed: {e}"}

    def _check_sigma_novelty(self, session) -> dict:
        try:
            from src.database.models import SigmaRuleTable

            count = session.query(SigmaRuleTable).filter(SigmaRuleTable.canonical_json.isnot(None)).count()
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
