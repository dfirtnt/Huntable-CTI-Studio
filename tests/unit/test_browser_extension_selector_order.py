import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[2]


def _extract_content_selectors(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    start = text.index("const contentSelectors = [")
    end = text.index("];", start)
    block = text[start:end]
    return re.findall(r"^\s*'([^']+)'", block, re.M)


def _choose_best_content_selector(html: str, selectors: list[str]) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    best_selector = None
    best_len = 0

    for selector in selectors:
        element = soup.select_one(selector)
        if not element:
            continue

        text_len = len(element.get_text(" ", strip=True))
        if text_len > best_len:
            best_len = text_len
            best_selector = selector

    return best_selector


@pytest.mark.parametrize(
    "relative_path",
    [
        "browser-extension/content.js",
        "browser-extension/popup.js",
    ],
)
def test_article_content_selectors_prefer_largest_article_container(relative_path: str) -> None:
    selectors = _extract_content_selectors(ROOT / relative_path)

    assert selectors.index(".content-column") < selectors.index(".content")
    assert selectors.index(".entry-content-wrapper") < selectors.index("main")
    assert selectors.index(".content-column") < selectors.index("main")

    dfir_like_html = """
    <html>
      <body>
        <main class="template-page content">Footer text only</main>
        <div class="content">
          <div class="entry-content-wrapper">
            <div class="content-column">"""
    dfir_like_html += "X " * 5000
    dfir_like_html += """</div>
          </div>
        </div>
      </body>
    </html>
    """

    unit42_like_html = """
    <html>
      <body>
        <main class="main">
          <div class="content">short content</div>
          <section class="body-wrap">"""
    unit42_like_html += "Y " * 4000
    unit42_like_html += """</section>
        </main>
      </body>
    </html>
    """

    assert _choose_best_content_selector(dfir_like_html, selectors) == ".content-column"
    assert _choose_best_content_selector(unit42_like_html, selectors) == "main"
