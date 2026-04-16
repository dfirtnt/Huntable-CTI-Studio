"""Helpers for constructing test database URLs."""

import os


def build_test_database_url(asyncpg: bool = True) -> str:
    """Build the test database URL from explicit test settings."""
    test_db_url = os.getenv("TEST_DATABASE_URL")
    if test_db_url:
        return test_db_url

    postgres_password = os.getenv("POSTGRES_PASSWORD")
    if not postgres_password:
        raise RuntimeError(
            "POSTGRES_PASSWORD must be set to build TEST_DATABASE_URL. "
            "Run ./setup.sh or export TEST_DATABASE_URL explicitly."
        )

    postgres_port = os.getenv("POSTGRES_PORT", "5433")
    scheme = "postgresql+asyncpg" if asyncpg else "postgresql"
    return f"{scheme}://cti_user:{postgres_password}@localhost:{postgres_port}/cti_scraper_test"
