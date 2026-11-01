"""Huntable CTI Studio package.

The version string is sourced from pyproject.toml via importlib.metadata so
there is exactly one place to bump on release: pyproject.toml.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path


def _version_from_pyproject() -> str:
    """Read the version from the checkout's pyproject.toml, or return the sentinel."""
    try:
        import tomllib

        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        with pyproject.open("rb") as fh:
            return str(tomllib.load(fh)["project"]["version"])
    except Exception:
        return "0.0.0+unknown"


try:
    __version__ = _pkg_version("cti-scraper")
except PackageNotFoundError:
    # Package not installed (e.g. the Docker images run from a mounted source
    # tree). Read pyproject.toml; fall back to a sentinel callers can detect.
    __version__ = _version_from_pyproject()

__all__ = ["__version__"]
