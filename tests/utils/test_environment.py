"""Test environment validation and safety guards."""

import os
import warnings
from typing import Optional


def assert_test_environment():
    """Ensure tests never target production database or use cloud LLM APIs without authorization.
    
    This guard function is invoked at pytest bootstrap and Celery initialization
    to prevent accidental production database access or cloud API usage.
    
    Raises:
        RuntimeError: If test environment is not properly configured
    """
    # Check APP_ENV
    if os.getenv("APP_ENV") != "test":
        raise RuntimeError("Tests must run with APP_ENV=test")
    
    # REQUIRE TEST_DATABASE_URL - never fall back to DATABASE_URL
    test_db_url = os.getenv("TEST_DATABASE_URL")
    if not test_db_url:
        raise RuntimeError(
            "TEST_DATABASE_URL must be set for tests. "
            "Never use DATABASE_URL in test environment."
        )
    
    # Explicitly reject DATABASE_URL if it's set (security check)
    prod_db_url = os.getenv("DATABASE_URL")
    if prod_db_url:
        # Only allow if DATABASE_URL itself points to a test database
        if "test" not in prod_db_url.lower():
            raise RuntimeError(
                f"DATABASE_URL is set to non-test database: {prod_db_url}. "
                "Tests must use TEST_DATABASE_URL only."
            )
        # If DATABASE_URL points to test, warn but allow (for compatibility)
        warnings.warn(
            "DATABASE_URL is set in test environment. Use TEST_DATABASE_URL instead.",
            RuntimeWarning
        )
    
    # Check TEST_DATABASE_URL contains "test"
    if "test" not in test_db_url.lower():
        raise RuntimeError(
            f"TEST_DATABASE_URL must contain 'test' in database name: {test_db_url}"
        )
    
    # Never use production database name
    if "cti_scraper" in test_db_url and "test" not in test_db_url:
        raise RuntimeError(
            f"Cannot use production database 'cti_scraper' in tests: {test_db_url}"
        )
    
    # API Key Safety: Prohibit cloud LLM API keys without explicit authorization
    cloud_llm_keys = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "CHATGPT_API_KEY": os.getenv("CHATGPT_API_KEY"),
    }
    
    present_keys = [key for key, value in cloud_llm_keys.items() if value]
    
    if present_keys:
        allow_cloud_llm = os.getenv("ALLOW_CLOUD_LLM_IN_TESTS", "false").lower() in ("true", "1", "yes")
        
        if not allow_cloud_llm:
            raise RuntimeError(
                f"Cloud LLM API keys detected in test environment: {', '.join(present_keys)}. "
                "Tests are prohibited from using cloud LLM APIs to prevent accidental costs. "
                "If you explicitly need cloud LLM APIs in tests, set ALLOW_CLOUD_LLM_IN_TESTS=true. "
                "Use local LLM (LMSTUDIO_API_URL) or mocks for testing instead."
            )
        else:
            warnings.warn(
                f"Cloud LLM API keys are enabled in tests: {', '.join(present_keys)}. "
                "This may incur API costs. Ensure this is intentional.",
                UserWarning
            )
