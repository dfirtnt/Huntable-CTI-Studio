"""Guard eval article fixtures against successful title-shell fetches."""

from __future__ import annotations

import json
import pathlib

import pytest


ROOT = pathlib.Path(__file__).parent.parent.parent
EVAL_DATA = ROOT / "config" / "eval_articles_data"
MIN_CONTENT_LENGTH = 2_000


def _fixture_articles() -> list[pytest.ParamSpecArgs]:
    params = []
    for path in sorted(EVAL_DATA.glob("*/articles.json")):
        fixture_set = path.parent.name
        for article in json.loads(path.read_text()):
            url = article["url"]
            params.append(pytest.param(fixture_set, url, article, id=f"{fixture_set}-{url}"))
    return params


@pytest.mark.unit
@pytest.mark.parametrize(("fixture_set", "url", "article"), _fixture_articles())
def test_eval_fixture_content_is_not_a_title_shell(
    fixture_set: str, url: str, article: dict
) -> None:
    """Every fixture must contain a real article body, not only its title."""
    content = article["content"]
    title = article["title"]

    assert len(content) >= MIN_CONTENT_LENGTH, (
        f"{fixture_set} fixture {url} has {len(content)} characters "
        f"(expected >= {MIN_CONTENT_LENGTH}); possible title-shell fetch."
    )
    assert content.strip() != title.strip(), (
        f"{fixture_set} fixture {url} content equals its title; possible title-shell fetch."
    )
