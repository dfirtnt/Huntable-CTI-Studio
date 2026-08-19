"""Unit tests for mtime-derived static asset cache busting.

Regression context: templates hardcoded tokens like ``?v=20260729`` that only changed when
a human remembered to edit the date, and static responses carry no Cache-Control header. A
shipped JS fix therefore kept being served to returning browsers from cache and looked as
though it had never worked -- the prompt-loss fix reached a hard-reloaded tab and no one
else.
"""

import re
from pathlib import Path

import pytest

from src.web.dependencies import asset_url

pytestmark = pytest.mark.unit

TEMPLATE_DIR = Path("src/web/templates")
STATIC_ROOT = Path("src/web/static")


class TestAssetUrl:
    def test_token_is_the_file_mtime(self):
        target = STATIC_ROOT / "js/workflow/config.js"
        expected = int(target.stat().st_mtime)

        assert asset_url("js/workflow/config.js") == f"/static/js/workflow/config.js?v={expected}"

    def test_token_changes_when_the_file_changes(self, tmp_path, monkeypatch):
        asset = tmp_path / "app.js"
        asset.write_text("v1")
        monkeypatch.setattr("src.web.dependencies._STATIC_ROOT", tmp_path)

        first = asset_url("app.js")
        import os

        os.utime(asset, (0, 1_700_000_000))
        second = asset_url("app.js")

        assert first != second
        assert second.endswith("?v=1700000000")

    def test_token_is_stable_when_the_file_does_not_change(self):
        assert asset_url("js/workflow/config.js") == asset_url("js/workflow/config.js")

    def test_leading_slash_and_static_prefix_are_accepted(self):
        expected = asset_url("js/workflow/config.js")

        assert asset_url("/static/js/workflow/config.js") == expected
        assert asset_url("static/js/workflow/config.js") == expected

    def test_missing_asset_returns_plain_url_rather_than_raising(self):
        """A 404 should surface normally instead of being masked by an exception."""
        assert asset_url("js/does-not-exist.js") == "/static/js/does-not-exist.js"


class TestNoHardcodedCacheBusters:
    def test_no_template_hardcodes_a_version_token(self):
        """Hardcoded tokens go stale silently; every asset must route through asset_url."""
        pattern = re.compile(r'(?:src|href)="/static/[^"?]+\?v=\d+"')
        offenders = [
            f"{path.name}: {match}"
            for path in sorted(TEMPLATE_DIR.glob("*.html"))
            for match in pattern.findall(path.read_text())
        ]

        assert offenders == [], f"Hardcoded cache-busters found: {offenders}"

    def test_every_asset_url_argument_resolves_to_a_real_file(self):
        pattern = re.compile(r"asset_url\('([^']+)'\)")
        missing = [
            f"{path.name}: {ref}"
            for path in sorted(TEMPLATE_DIR.glob("*.html"))
            for ref in pattern.findall(path.read_text())
            if not (STATIC_ROOT / ref.lstrip("/")).exists()
        ]

        assert missing == [], f"asset_url references missing files: {missing}"
