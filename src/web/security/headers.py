"""Security response headers, including Content Security Policy.

The app previously sent no security headers at all -- no CSP, no framing
control, no MIME-sniffing control. Escaping is the primary defence against the
DOM-XSS sinks in these templates; this module is the second layer for when a
sink is missed, which has happened more than once.

Two CSP headers are sent, and the split is the point:

**Enforced** carries only directives the app already complies with, so turning
it on cannot break a page. It is genuinely useful on its own -- `base-uri`
stops an injected `<base>` from repointing every relative URL on the page, and
`form-action` stops an injected form from posting operator data off-origin.
Neither depends on the inline-script problem below.

**Report-Only** carries the strict policy we cannot enforce yet. The blocker is
`script-src`: 26 inline `<script>` blocks (~22k lines) and 341 inline event
handler attributes. Nonces would authorise the blocks, but nothing authorises a
handler attribute -- allowing `onclick=` necessarily allows an injected
`onerror=`, which is exactly the payload the escaping fixes were about. Getting
real `script-src` coverage means migrating those handlers to addEventListener,
so Report-Only measures that surface instead of guessing at it.

`style-src` deliberately keeps 'unsafe-inline'. Inline styles are pervasive here
and far lower risk than script; reporting every `style=` attribute would bury
the script violations that actually matter.

HSTS is intentionally absent: the dev app is served over plain HTTP, and a
stray max-age pinned against localhost is a footgun with no benefit here. It
belongs with the TLS-terminating deployment config, not the app.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Third-party origins the app actually loads today. Kept explicit so a new CDN
# dependency shows up as a Report-Only violation rather than passing silently.
_SCRIPT_CDNS = "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com"
_STYLE_CDN = "https://fonts.googleapis.com"
_FONT_CDN = "https://fonts.gstatic.com"

ENFORCED_CSP = "; ".join(
    [
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    ]
)

REPORT_ONLY_CSP = "; ".join(
    [
        "default-src 'self'",
        f"script-src 'self' {_SCRIPT_CDNS}",
        f"style-src 'self' 'unsafe-inline' {_STYLE_CDN}",
        f"font-src 'self' {_FONT_CDN}",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    ]
)

SECURITY_HEADERS = {
    "Content-Security-Policy": ENFORCED_CSP,
    "Content-Security-Policy-Report-Only": REPORT_ONLY_CSP,
    # frame-ancestors supersedes this for modern browsers; kept for older ones.
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security headers to every response, including static files."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            # setdefault semantics: a route that deliberately set its own policy
            # (e.g. a sandboxed preview) keeps it.
            if header not in response.headers:
                response.headers[header] = value
        return response
