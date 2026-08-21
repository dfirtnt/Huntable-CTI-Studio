"""Regression checks for external resources loaded by the base template."""

from pathlib import Path

from bs4 import BeautifulSoup

BASE_TEMPLATE = Path("src/web/templates/base.html")


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
