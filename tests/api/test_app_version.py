"""The FastAPI app's reported version must come from the single source of
truth (src.__version__, sourced from pyproject.toml), not a hardcoded literal
that can drift out of sync.
"""

from src import __version__


def test_app_version_matches_package_version():
    from src.web.modern_main import app

    assert app.version == __version__
