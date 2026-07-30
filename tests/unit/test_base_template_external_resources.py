"""Regression checks for external resources loaded by the base template."""

from pathlib import Path

from bs4 import BeautifulSoup

BASE_TEMPLATE = Path("src/web/templates/base.html")


def test_dynamic_cdn_resources_do_not_use_incompatible_sri() -> None:
    """Dynamic/CORS-incompatible resources must load without SRI attributes."""
    soup = BeautifulSoup(BASE_TEMPLATE.read_text(encoding="utf-8"), "html.parser")
    resources = [
        soup.find("link", href=lambda value: value and value.startswith("https://fonts.googleapis.com/")),
        soup.find("script", src=lambda value: value and value.startswith("https://cdn.tailwindcss.com/")),
    ]

    assert all(resource is not None for resource in resources)
    for resource in resources:
        assert resource is not None
        assert "integrity" not in resource.attrs
        assert "crossorigin" not in resource.attrs
