"""Regression checks for external resources loaded by the base template."""

from pathlib import Path

from bs4 import BeautifulSoup

BASE_TEMPLATE = Path("src/web/templates/base.html")
TEMPLATES_DIR = Path("src/web/templates")

# Cross-origin <script src> hosts that are exempt from carrying `integrity`,
# with the reason SRI cannot be added there. Keep this list in sync with
# test_cors_incompatible_resources_do_not_use_sri above -- an entry here
# should exist because the host does not send access-control-allow-origin
# (SRI forces a CORS fetch, which then fails and blocks the script), not
# because adding the hash was merely inconvenient.
SCRIPT_SRI_EXEMPT_HOSTS: dict[str, str] = {}


def test_cors_incompatible_resources_do_not_use_sri() -> None:
    """CORS-incompatible resources must load without SRI attributes.

    `integrity` on a cross-origin subresource forces a CORS fetch, so a host that
    sends no `access-control-allow-origin` fails the fetch and the resource is
    blocked outright. fonts.googleapis.com also varies its response by user agent,
    which defeats a fixed hash independently.

    Previously this also guarded cdn.tailwindcss.com, which was the same CORS
    problem, not a dynamic-content one -- SRI was added there on 2026-07-17 and
    reverted three days later in cff9e7ba when it blocked the script and left every
    page unstyled. Tailwind is now built locally (tailwind.config.js, `make css`)
    and loaded from /static, so the entry is gone rather than relaxed.
    """
    soup = BeautifulSoup(BASE_TEMPLATE.read_text(encoding="utf-8"), "html.parser")
    resources = [
        soup.find("link", href=lambda value: value and value.startswith("https://fonts.googleapis.com/")),
    ]

    assert all(resource is not None for resource in resources)
    for resource in resources:
        assert resource is not None
        assert "integrity" not in resource.attrs
        assert "crossorigin" not in resource.attrs


def test_tailwind_is_served_locally_not_from_a_cdn() -> None:
    """The runtime Tailwind CDN script must not come back.

    It executed a 407KB unverified third-party compiler in an authenticated
    operator session on every page, and no CSP backstops it. Because the host
    cannot accept SRI, re-adding the tag is unfixable rather than merely untidy.
    """
    markup = BASE_TEMPLATE.read_text(encoding="utf-8")
    soup = BeautifulSoup(markup, "html.parser")

    # Asserted against parsed tags rather than the raw text: the template
    # explains the removal in a comment that names the host, and a bare substring
    # check flags that comment while an inert commented-out tag harms nothing.
    assert soup.find("script", src=lambda value: value and "tailwindcss.com" in value) is None
    assert soup.find("link", href=lambda value: value and "css/tailwind.css" in value) is not None


def test_cross_origin_scripts_carry_integrity_or_documented_reason() -> None:
    """Every cross-origin <script> across all templates must be pinned.

    An unversioned CDN URL paired with a version-specific integrity hash is a
    silent time bomb: it matches only until the CDN's "latest" resolution moves,
    at which point the hash mismatches, the browser blocks the script, and
    every page depending on it breaks with no console error a user would
    notice. ml_hunt_comparison.html:558 shipped exactly this bug (unversioned
    URL, chart.js 4.5.1 hash) until fixed here.

    Every <script src="https://..."> in every template must therefore either:
    - carry `integrity`, in which case the URL must be version-pinned (not
      just resolve to the pinned version today), or
    - have its host listed in SCRIPT_SRI_EXEMPT_HOSTS with a documented,
      CORS-based reason SRI cannot be added.
    """
    unpinned_hash: list[str] = []
    missing_integrity: list[str] = []

    for template_path in sorted(TEMPLATES_DIR.rglob("*.html")):
        soup = BeautifulSoup(template_path.read_text(encoding="utf-8"), "html.parser")
        for script in soup.find_all("script", src=True):
            src = script["src"]
            if not src.startswith(("http://", "https://")):
                continue  # same-origin (/static/...) -- not third-party

            location = f"{template_path}: {src}"
            host_exempt = any(host in src for host in SCRIPT_SRI_EXEMPT_HOSTS)

            if "integrity" not in script.attrs:
                if not host_exempt:
                    missing_integrity.append(location)
                continue

            if host_exempt:
                # Listed as CORS-incompatible yet carries integrity -- contradictory.
                missing_integrity.append(f"{location} (has integrity but host is listed SRI-exempt)")
                continue

            # A pinned hash next to an unversioned URL is the ml_hunt_comparison.html
            # bug: only jsdelivr's package URLs have this "@version/" pin shape, so
            # check specifically for the un-pinned form when the host is jsdelivr.
            if "cdn.jsdelivr.net/npm/" in src and "@" not in src.split("cdn.jsdelivr.net/npm/", 1)[1]:
                unpinned_hash.append(location)

    assert not unpinned_hash, (
        "Unversioned CDN URL(s) carrying a version-specific integrity hash "
        f"(will silently break on the next upstream release): {unpinned_hash}"
    )
    assert not missing_integrity, (
        f"Cross-origin <script> tag(s) missing integrity with no documented CORS exemption: {missing_integrity}"
    )
