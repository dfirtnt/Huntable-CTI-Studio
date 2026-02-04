"""MkDocs build sanity check test."""

import subprocess
import sys
from pathlib import Path

import pytest


class TestMkDocsBuild:
    """Test that MkDocs documentation builds successfully."""

    @pytest.fixture
    def mkdocs_config_path(self):
        """Path to mkdocs.yml config file."""
        return Path("mkdocs.yml")

    def test_mkdocs_build_succeeds(self, mkdocs_config_path):
        """Test that mkdocs build succeeds (minimal sanity check).

        This is a minimal sanity check - it only validates that MkDocs
        can build the documentation without fatal errors. It does NOT validate
        documentation content or enforce strict mode (warnings are acceptable).
        """
        if not mkdocs_config_path.exists():
            pytest.skip(f"MkDocs config not found: {mkdocs_config_path}")

        # Run mkdocs build (without --strict to allow warnings)
        # This will fail only on fatal errors, not warnings
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs", "build"],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        # Assert build succeeded (warnings are acceptable for sanity check)
        assert result.returncode == 0, f"MkDocs build failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
