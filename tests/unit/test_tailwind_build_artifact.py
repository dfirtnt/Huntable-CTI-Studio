"""Contract tests for the committed Tailwind stylesheet.

Tailwind moved from a runtime CDN compiler to a local build (commit 9daeff13).
The CDN generated every utility in the browser, so no class could ever be
"missing". A local build only emits classes it can FIND as literal strings while
scanning `content`, which converts a whole category of styling into something
that can silently disappear:

  * a class name assembled from a fragment (`` `bg-${c}-100` ``) is invisible to
    the scanner and needs a `safelist` entry;
  * a class held in a Python string is invisible unless `./src/**/*.py` is in
    `content`.

Neither failure raises anything. The page renders with the class ATTRIBUTE
present and no rule behind it, and the existing UI tests keep passing because
they assert on rendered HTML attributes, not on CSS. These tests close that gap
by checking the artifact itself.

They deliberately do NOT try to verify the whole app's class usage: templates
carry arbitrary-value classes and JS builds complete class strings dynamically,
so a blanket scan would be noisy without being more correct. What is pinned here
is exactly the part the scanner cannot see for itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

GENERATED_CSS = Path("src/web/static/css/tailwind.css")
TAILWIND_CONFIG = Path("tailwind.config.js")
KEYWORD_METADATA = Path("src/utils/keyword_resolution.py")

# Files whose `${statusColor}` interpolations the safelist has to cover.
FRAGMENT_CLASS_TEMPLATES = (
    Path("src/web/templates/article_detail.html"),
    Path("src/web/templates/sigma_similarity_test.html"),
)

TAILWIND_PALETTE = frozenset(
    [
        "slate",
        "gray",
        "zinc",
        "neutral",
        "stone",
        "red",
        "orange",
        "amber",
        "yellow",
        "lime",
        "green",
        "emerald",
        "teal",
        "cyan",
        "sky",
        "blue",
        "indigo",
        "violet",
        "purple",
        "fuchsia",
        "pink",
        "rose",
    ]
)

# `dark:bg-purple-800` -> `.dark\:bg-purple-800` in the emitted CSS.
_SELECTOR_ESCAPE = str.maketrans({":": r"\:", ".": r"\.", "[": r"\[", "]": r"\]", "/": r"\/"})

FRAGMENT_USAGE_PATTERN = re.compile(
    r"(?P<dark>dark:)?(?P<utility>text|bg|border|ring)-\$\{statusColor\}-(?P<shade>\d{2,3})"
)
STATUS_COLOR_VALUE_PATTERN = re.compile(r"statusColor\s*=\s*(?P<tail>[^;]{0,200});", re.DOTALL)
QUOTED_WORD_PATTERN = re.compile(r"'([a-z]+)'")


def _css() -> str:
    return GENERATED_CSS.read_text(encoding="utf-8")


def _class_is_generated(css: str, class_name: str) -> bool:
    """True when the stylesheet defines a rule for `class_name`.

    Matched as a whole selector token so `.bg-green-100` does not satisfy a
    lookup for `.bg-green-1`.
    """
    return re.search(r"\." + re.escape(class_name.translate(_SELECTOR_ESCAPE)) + r"(?![\w-])", css) is not None


def _declared_classes(source: str) -> set[str]:
    classes: set[str] = set()
    for match in re.finditer(r'_classes="([^"]+)"', source):
        classes.update(match.group(1).split())
    return classes


def _status_color_values(source: str) -> set[str]:
    """Every colour name `statusColor` can hold in one template."""
    values: set[str] = set()
    for match in STATUS_COLOR_VALUE_PATTERN.finditer(source):
        values.update(word for word in QUOTED_WORD_PATTERN.findall(match.group("tail")) if word in TAILWIND_PALETTE)
    return values


def _required_fragment_classes(source: str) -> set[str]:
    """Concrete class names the `${statusColor}` sites can produce at runtime.

    Derived from the source rather than hardcoded, so adding a new colour to the
    ternary -- or a new utility/shade to the markup -- makes this test demand
    safelist coverage for it instead of silently going unstyled.
    """
    values = _status_color_values(source)
    required: set[str] = set()
    for usage in FRAGMENT_USAGE_PATTERN.finditer(source):
        prefix = usage.group("dark") or ""
        for colour in values:
            required.add(f"{prefix}{usage.group('utility')}-{colour}-{usage.group('shade')}")
    return required


def test_generated_stylesheet_is_present_and_substantial() -> None:
    """Guard against every assertion below passing against an empty file."""
    assert GENERATED_CSS.exists(), f"{GENERATED_CSS} is missing -- run `make css` and commit the result."

    css = _css()
    assert len(css) > 20_000, f"{GENERATED_CSS} is {len(css)} bytes; a real build is far larger."
    assert _class_is_generated(css, "hidden"), "No `.hidden` rule -- the build did not emit core utilities."


def test_every_python_held_class_is_generated() -> None:
    """Classes that live only in Python must survive content scanning.

    src/utils/keyword_resolution.py carries the keyword-highlight palette on
    KEYWORD_CATEGORY_METADATA. They reach the DOM through
    render_highlighted_content and the keyword panel, never through a template
    literal, so they are only emitted because `./src/**/*.py` is in `content`.
    Drop that glob and the highlights lose their backgrounds app-wide.
    """
    declared = _declared_classes(KEYWORD_METADATA.read_text(encoding="utf-8"))
    assert len(declared) > 40, f"Expected the full keyword palette, found {len(declared)} -- parser likely broke."

    css = _css()
    missing = sorted(name for name in declared if not _class_is_generated(css, name))

    assert not missing, (
        "Tailwind classes declared in Python are absent from the generated stylesheet. "
        "Most likely `./src/**/*.py` was dropped from `content` in tailwind.config.js, or "
        "`make css` has not been re-run since these were added. "
        f"Missing: {missing}"
    )


SAFELIST_PATTERN_IN_CONFIG = re.compile(r"pattern:\s*/(?P<regex>.+?)/\s*,")
SAFELIST_VARIANTS_IN_CONFIG = re.compile(r"variants:\s*\[(?P<variants>[^\]]*)\]")


@pytest.mark.parametrize("template", FRAGMENT_CLASS_TEMPLATES, ids=lambda p: p.name)
def test_safelist_pattern_covers_every_fragment_assembled_class(template: Path) -> None:
    """The safelist must cover every class the `${statusColor}` sites can build.

    Asserted against the CONFIG, not against the emitted CSS. Every one of these
    classes currently also appears as a literal in 13-36 other files, so they
    would be emitted even with no safelist at all -- meaning an outcome-only
    check cannot detect the safelist being removed or narrowed. The safelist is
    what keeps these sites working if those incidental usages are ever edited
    away, so it is pinned directly.
    """
    source = template.read_text(encoding="utf-8")
    required = _required_fragment_classes(source)
    assert required, f"No ${{statusColor}} class usages parsed from {template} -- the pattern broke."

    config = TAILWIND_CONFIG.read_text(encoding="utf-8")
    pattern_match = SAFELIST_PATTERN_IN_CONFIG.search(config)
    assert pattern_match, (
        "No `safelist` pattern found in tailwind.config.js. "
        f"{template} assembles class names from a colour fragment, which the Tailwind scanner "
        "cannot see, so those classes need a safelist entry."
    )

    safelist = re.compile(pattern_match.group("regex"))
    variants = SAFELIST_VARIANTS_IN_CONFIG.search(config)
    dark_supported = bool(variants) and "dark" in variants.group("variants")

    uncovered = sorted(
        name
        for name in required
        if not (safelist.match(name.removeprefix("dark:")) and (dark_supported or not name.startswith("dark:")))
    )

    assert not uncovered, (
        f"The safelist in tailwind.config.js does not cover class names {template} can produce at "
        "runtime. This usually means a colour was added to the statusColor chain, or a new "
        "utility/shade was used in the markup, without widening the safelist pattern. "
        f"Uncovered: {uncovered}"
    )


@pytest.mark.parametrize("template", FRAGMENT_CLASS_TEMPLATES, ids=lambda p: p.name)
def test_fragment_assembled_classes_are_generated(template: Path) -> None:
    """The outcome the safelist exists to guarantee: the rules are really there."""
    source = template.read_text(encoding="utf-8")

    values = _status_color_values(source)
    assert values, f"No statusColor values parsed from {template} -- the pattern broke or the code moved."

    required = _required_fragment_classes(source)
    css = _css()
    missing = sorted(name for name in required if not _class_is_generated(css, name))

    assert not missing, (
        f"{template} builds these class names from a colour fragment at runtime, and no rule for "
        "them exists in the generated stylesheet -- those elements render unstyled. Cover them via "
        "`safelist` in tailwind.config.js and re-run `make css`. "
        f"Missing: {missing}"
    )


def test_content_globs_still_cover_the_non_obvious_sources() -> None:
    """The Python glob is load-bearing and non-standard; pin it explicitly.

    Asserted on the config rather than only on outcomes so the failure names the
    cause directly, instead of surfacing as a list of missing colour classes.
    """
    config = TAILWIND_CONFIG.read_text(encoding="utf-8")

    for glob in ("./src/web/templates/**/*.html", "./src/web/static/js/**/*.js", "./src/**/*.py"):
        assert glob in config, (
            f"`{glob}` is missing from `content` in tailwind.config.js. Every class found only in "
            "those files will be purged from the next build."
        )
