"""Accessibility baseline for the Jinja templates.

The `a11y` marker and the `run_tests.py a11y` suite both existed before this file
did, with zero tests carrying the marker -- so `run_tests.py a11y` collected
nothing and the runner reported failure on an empty set. These are the baseline
it was waiting for.

Deliberately static: they parse the template sources rather than driving a
browser, so they need no dev server, no Playwright, and no database, and they
run inside the marker-based `a11y` suite (which skips Playwright entirely) as
well as the normal unit suite.

Scope is the checks that can be decided from source alone and that a reviewer
would treat as non-negotiable: every image has alt text, every form control has
an accessible name, every control is reachable, and the page shell carries its
language and landmarks. Contrast ratios, focus order, and screen-reader
behaviour need a rendered page and belong in the Playwright UI tier.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

pytestmark = [pytest.mark.unit, pytest.mark.a11y]

_REPO = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO / "src" / "web" / "templates"
_BASE = _TEMPLATE_DIR / "base.html"

# Controls that never surface to assistive tech and so need no accessible name.
_EXEMPT_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image"}

_FOCUSABLE_TAGS = ["a", "button", "input", "select", "textarea"]

# Tailwind's `hidden` utility and inline display:none both remove an element from
# the focus order, which is what makes an aria-hidden wrapper harmless there.
_DISPLAY_HIDDEN_CLASSES = {"hidden"}


def _describe(el) -> str:
    element_id = el.get("id", "(no id)")
    return f"<{el.name} id={element_id}>"


def _is_display_hidden(el) -> bool:
    if el.has_attr("hidden"):
        return True
    if _DISPLAY_HIDDEN_CLASSES.intersection(el.get("class") or []):
        return True
    style = (el.get("style") or "").replace(" ", "").lower()
    return "display:none" in style


def _templates() -> list[Path]:
    return sorted(_TEMPLATE_DIR.glob("*.html"))


def _soup(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")


def _has_accessible_name(el, soup: BeautifulSoup) -> bool:
    """Mirror the accessible-name computation a screen reader actually performs.

    Order matters less than coverage here: any one of these produces a name, so a
    control satisfying none of them is announced as an unlabelled control.
    """
    for attr in ("aria-label", "aria-labelledby", "title"):
        if (el.get(attr) or "").strip():
            return True
    element_id = el.get("id")
    if element_id and soup.find("label", attrs={"for": element_id}):
        return True
    if el.find_parent("label"):
        return True
    # placeholder is a weak last resort -- it disappears on input and is not a
    # substitute for a label, but it does yield a name, so it is not a failure.
    return bool((el.get("placeholder") or "").strip())


def _ids(paths: list[Path]) -> list[str]:
    return [p.name for p in paths]


class TestTemplateInventory:
    """Guard the guard: these tests are worthless if they scan nothing."""

    def test_templates_are_discovered(self):
        found = _templates()
        assert len(found) >= 20, f"expected the full template set, found {len(found)}: {_ids(found)}"

    def test_base_template_exists(self):
        assert _BASE.is_file(), f"{_BASE} is the shell every page extends; it must exist"


class TestPageShell:
    """base.html carries the landmarks and language every page inherits."""

    def test_html_element_declares_a_language(self):
        html = _soup(_BASE).find("html")
        assert html is not None, "base.html must have an <html> element"
        lang = (html.get("lang") or "").strip()
        assert lang, "<html> must declare lang; screen readers pick pronunciation from it"

    def test_page_has_a_title_block(self):
        assert _soup(_BASE).find("title") is not None, "base.html must define a <title>"

    def test_navigation_landmark_is_labelled(self):
        navs = _soup(_BASE).find_all("nav")
        assert navs, "base.html must expose a <nav> landmark"
        assert any((n.get("aria-label") or "").strip() for n in navs), (
            "at least one <nav> must carry aria-label so it is distinguishable in a landmark list"
        )

    def test_main_landmark_is_present(self):
        assert _soup(_BASE).find("main") is not None, (
            "base.html must wrap page content in <main> so assistive tech can skip the chrome"
        )


class TestImages:
    @pytest.mark.parametrize("template", _templates(), ids=_ids(_templates()))
    def test_every_image_has_an_alt_attribute(self, template: Path):
        """alt must be present. An empty alt is valid and means 'decorative'."""
        missing = [str(img)[:120] for img in _soup(template).find_all("img") if img.get("alt") is None]
        assert missing == [], f"{template.name}: {len(missing)} <img> without an alt attribute: {missing}"


class TestFormControls:
    @pytest.mark.parametrize("template", _templates(), ids=_ids(_templates()))
    def test_every_form_control_has_an_accessible_name(self, template: Path):
        soup = _soup(template)
        unnamed = []
        for el in soup.find_all(["input", "select", "textarea"]):
            if (el.get("type") or "").lower() in _EXEMPT_INPUT_TYPES:
                continue
            if not _has_accessible_name(el, soup):
                unnamed.append(_describe(el))
        assert unnamed == [], (
            f"{template.name}: {len(unnamed)} control(s) announced as unlabelled: {unnamed}. "
            "Add aria-label, or a <label for=...> pointing at the control's id."
        )


class TestInteractiveElements:
    @pytest.mark.parametrize("template", _templates(), ids=_ids(_templates()))
    def test_no_positive_tabindex(self, template: Path):
        """A positive tabindex reorders the whole page's focus sequence, not just its own."""
        offenders = []
        for el in _soup(template).find_all(attrs={"tabindex": True}):
            raw = (el.get("tabindex") or "").strip()
            try:
                if int(raw) > 0:
                    offenders.append(f"<{el.name} tabindex={raw}>")
            except ValueError:
                offenders.append(f"<{el.name} tabindex={raw!r} (not an integer)>")
        assert offenders == [], (
            f"{template.name}: positive/invalid tabindex breaks natural focus order: {offenders}. Use 0 or -1."
        )

    @pytest.mark.parametrize("template", _templates(), ids=_ids(_templates()))
    def test_aria_hidden_is_never_set_on_a_focusable_control(self, template: Path):
        """aria-hidden over a still-focusable control creates a focus trap.

        The failure mode is a control a sighted keyboard user can tab to but a
        screen reader refuses to announce. Display-hidden subtrees are exempt on
        purpose: `display:none` already removes them from the focus order, so
        aria-hidden there is redundant rather than harmful.
        """
        offenders = []
        for el in _soup(template).find_all(attrs={"aria-hidden": "true"}):
            if _is_display_hidden(el):
                continue
            focusable = el.find_all(_FOCUSABLE_TAGS)
            if el.name in _FOCUSABLE_TAGS:
                focusable = [el, *focusable]
            trapped = [
                f
                for f in focusable
                if (f.get("type") or "").lower() != "hidden"
                and not f.has_attr("disabled")
                and not _is_display_hidden(f)
            ]
            if trapped:
                described = [_describe(f) for f in trapped]
                offenders.append(
                    f"<{el.name} aria-hidden=true> wrapping {len(trapped)} focusable element(s): {described}"
                )
        assert offenders == [], f"{template.name}: {offenders}"
