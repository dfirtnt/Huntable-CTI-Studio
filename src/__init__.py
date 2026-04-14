"""Huntable CTI Studio package.

The version string is sourced from pyproject.toml via importlib.metadata so
there is exactly one place to bump on release: pyproject.toml.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("cti-scraper")
except PackageNotFoundError:
    # Package not installed (e.g. running from a source checkout without
    # `pip install -e .`). Fall back to a sentinel so callers can detect this.
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
