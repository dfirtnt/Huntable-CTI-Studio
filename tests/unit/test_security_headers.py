"""Contract for the security response headers, including CSP.

The app shipped with no security headers at all. These pin the two properties
that are easy to lose silently:

1. The ENFORCED policy stays restricted to directives the app complies with.
   Promoting a directive out of Report-Only without doing the migration work
   would break pages at runtime, and a CSP failure is invisible server-side --
   the browser just refuses to run something and the page quietly half-works.
2. Every third-party script carries Subresource Integrity. The Tailwind CDN
   removal left three siblings unpinned, one of them pairing an UNVERSIONED
   jsdelivr URL with a version-specific hash -- which breaks the moment
   upstream publishes a new latest.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.web.security.headers import (
    ENFORCED_CSP,
    REPORT_ONLY_CSP,
    SECURITY_HEADERS,
    SecurityHeadersMiddleware,
)

pytestmark = pytest.mark.unit

TEMPLATE_DIR = Path("src/web/templates")

EXTERNAL_SCRIPT_PATTERN = re.compile(r"<script\b[^>]*\bsrc=\"(?P<url>https?://[^\"]+)\"[^>]*>")


class TestEnforcedPolicyStaysSafe:
    def test_enforced_policy_carries_the_non_breaking_directives(self) -> None:
        for directive in ("object-src 'none'", "base-uri 'self'", "frame-ancestors 'none'", "form-action 'self'"):
            assert directive in ENFORCED_CSP, f"{directive} missing from the enforced policy"

    def test_enforced_policy_does_not_restrict_scripts_yet(self) -> None:
        """script-src/default-src in the ENFORCED policy would break 341 inline
        handlers and 26 inline script blocks. That migration is Phase 2; until
        it lands, these belong in Report-Only only."""
        assert "script-src" not in ENFORCED_CSP
        assert "default-src" not in ENFORCED_CSP
        assert "style-src" not in ENFORCED_CSP

    def test_report_only_policy_actually_constrains_scripts(self) -> None:
        """Otherwise Report-Only measures nothing and the phase-2 surface stays unknown."""
        assert "script-src 'self'" in REPORT_ONLY_CSP
        assert "'unsafe-inline'" not in REPORT_ONLY_CSP.split("style-src")[0], (
            "script-src must not allow inline; that is the whole point of the measurement"
        )

    def test_both_headers_are_sent(self) -> None:
        assert SECURITY_HEADERS["Content-Security-Policy"] == ENFORCED_CSP
        assert SECURITY_HEADERS["Content-Security-Policy-Report-Only"] == REPORT_ONLY_CSP

    def test_supporting_headers_present(self) -> None:
        assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
        assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"
        assert "Referrer-Policy" in SECURITY_HEADERS

    def test_hsts_is_not_set_from_the_app(self) -> None:
        """Pinning HSTS against a plain-HTTP dev host is a footgun with no benefit;
        it belongs with the TLS-terminating deployment config."""
        assert not any(h.lower() == "strict-transport-security" for h in SECURITY_HEADERS)


class TestSubresourceIntegrity:
    def _external_scripts(self) -> list[tuple[str, str]]:
        found = []
        for template in sorted(TEMPLATE_DIR.rglob("*.html")):
            for match in EXTERNAL_SCRIPT_PATTERN.finditer(template.read_text(encoding="utf-8")):
                found.append((template.name, match.group(0)))
        return found

    def test_scan_is_not_vacuous(self) -> None:
        assert len(self._external_scripts()) >= 4, "regex likely broke; it should find the CDN scripts"

    def test_every_external_script_has_integrity(self) -> None:
        offenders = [(name, tag[:110]) for name, tag in self._external_scripts() if "integrity=" not in tag]

        assert not offenders, (
            "Third-party script loaded with no Subresource Integrity. A compromised CDN then gets "
            f"arbitrary JS into an authenticated operator session. Offenders: {offenders}"
        )

    def test_no_integrity_hash_on_an_unversioned_url(self) -> None:
        """An unversioned URL serves whatever upstream calls latest, so a pinned
        hash stops matching on the next publish and the script silently fails to
        load -- a broken page with no server-side signal."""
        offenders = []
        for name, tag in self._external_scripts():
            if "integrity=" not in tag:
                continue
            url = EXTERNAL_SCRIPT_PATTERN.search(tag).group("url")
            if not re.search(r"[@/]\d+\.\d+\.\d+", url):
                offenders.append((name, url))

        assert not offenders, f"integrity hash pinned against an unversioned URL: {offenders}"


class TestMiddlewareIsRegistered:
    """The policy constants above are inert unless the middleware is actually wired in.

    Without this, deleting the add_middleware call in modern_main leaves every
    other test in this file green while the app serves no security headers at all.
    """

    def _middleware_classes(self) -> list:
        from src.web.modern_main import app

        return [m.cls for m in app.user_middleware]

    def test_security_headers_middleware_is_installed(self) -> None:
        assert SecurityHeadersMiddleware in self._middleware_classes(), (
            "SecurityHeadersMiddleware is not registered; the app serves no CSP."
        )

    def test_security_headers_middleware_is_outermost(self) -> None:
        """Outermost means headers reach authorization denials and error pages --
        exactly the responses an unauthenticated caller can reach. add_middleware
        registers outermost-last, so user_middleware lists it first."""
        classes = self._middleware_classes()
        assert classes[0] is SecurityHeadersMiddleware, (
            f"SecurityHeadersMiddleware must be outermost, got order: {[c.__name__ for c in classes]}"
        )
