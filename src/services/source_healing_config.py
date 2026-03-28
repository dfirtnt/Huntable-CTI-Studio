"""Configuration loader for Source Auto-Healing settings."""

import logging
from dataclasses import dataclass

from src.database.manager import DatabaseManager
from src.database.models import AppSettingsTable

logger = logging.getLogger(__name__)

# AppSettingsTable keys for source healing
HEALING_KEYS = {
    "enabled": "SOURCE_HEALING_ENABLED",
    "threshold": "SOURCE_HEALING_THRESHOLD",
    "max_attempts": "SOURCE_HEALING_MAX_ATTEMPTS",
    "check_interval_hours": "SOURCE_HEALING_CHECK_INTERVAL",
    "provider": "SOURCE_HEALING_PROVIDER",
    "model": "SOURCE_HEALING_MODEL",
    "api_key": "SOURCE_HEALING_API_KEY",
}


@dataclass
class SourceHealingConfig:
    """Source auto-healing settings resolved from AppSettingsTable."""

    enabled: bool = False
    threshold: int = 100
    max_attempts: int = 5
    check_interval_hours: int = 1
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str | None = None

    @classmethod
    def load(cls) -> "SourceHealingConfig":
        """Load healing config from AppSettingsTable using a synchronous DB session.

        Follows the same pattern as LLMService._load_workflow_provider_settings().
        """
        raw: dict[str, str | None] = {}
        db_session = None
        try:
            db_manager = DatabaseManager()
            db_session = db_manager.get_session()
            query = db_session.query(AppSettingsTable).filter(AppSettingsTable.key.in_(HEALING_KEYS.values()))
            for row in query:
                raw[row.key] = row.value
        except Exception as exc:
            logger.warning("Unable to load source healing settings from AppSettings: %s", exc)
        finally:
            if db_session:
                db_session.close()

        def _bool(key: str, default: bool) -> bool:
            val = raw.get(HEALING_KEYS[key])
            if val is None:
                return default
            return str(val).strip().lower() == "true"

        def _int(key: str, default: int) -> int:
            val = raw.get(HEALING_KEYS[key])
            if val is None:
                return default
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        def _str(key: str, default: str) -> str:
            val = raw.get(HEALING_KEYS[key])
            if val is None or not str(val).strip():
                return default
            return str(val).strip()

        api_key_raw = raw.get(HEALING_KEYS["api_key"])
        api_key = str(api_key_raw).strip() if api_key_raw and str(api_key_raw).strip() else None

        return cls(
            enabled=_bool("enabled", False),
            threshold=max(_int("threshold", 100), 1),
            max_attempts=max(_int("max_attempts", 5), 1),
            check_interval_hours=max(_int("check_interval_hours", 1), 1),
            provider=_str("provider", "openai"),
            model=_str("model", "gpt-4o-mini"),
            api_key=api_key,
        )
