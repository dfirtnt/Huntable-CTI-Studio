"""
Live smoke tests for the published GitHub Pages documentation site.

Marked ``docs`` — not in run_tests.py's normal matrix; run explicitly:

    APP_ENV=test TEST_DATABASE_URL=postgresql://test:test@localhost:5433/cti_scraper_test \
        pytest tests/smoke/test_docs_pages_smoke.py -m docs -v

(APP_ENV + TEST_DATABASE_URL satisfy the pytest_configure env guard; no DB
connection is actually made — these tests only perform external HTTP requests.)

Or via the docs-smoke CI workflow (triggered after every successful Docs deploy).
No local server required — hits the public GitHub Pages URL directly.
"""

import httpx
import pytest

_SITE_ROOT = "https://dfirtnt.github.io/Huntable-CTI-Studio"

# (URL path, required text snippets that must appear in the HTML response)
_PAGES = [
    (
        "/",
        (
            "Huntable CTI Studio",   # <title> and nav header
            "Reports to Rules",      # index.md tagline — stable anchor
        ),
    ),
    (
        "/europa/",
        (
            "Huntable CTI Studio",   # same site, /europa branch preview
        ),
    ),
]


@pytest.mark.docs
class TestDocsPagesSmoke:
    """Verify the published GitHub Pages site serves expected content, not a 404."""

    @pytest.mark.parametrize(
        "path, expected",
        _PAGES,
        ids=[path.strip("/") or "root" for path, _ in _PAGES],
    )
    def test_page_content(self, path: str, expected: tuple[str, ...]) -> None:
        url = f"{_SITE_ROOT}{path}"
        response = httpx.get(url, timeout=30.0, follow_redirects=True)

        assert response.status_code == 200, (
            f"{url} returned HTTP {response.status_code} — "
            "site may be 404 or GitHub Pages CDN not yet propagated"
        )
        for snippet in expected:
            assert snippet in response.text, (
                f"{url} missing expected text: {snippet!r}"
            )
