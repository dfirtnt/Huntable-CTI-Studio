#!/usr/bin/env python3
"""
Fix integration tests to use Pydantic models instead of dicts.
"""

import re
from pathlib import Path


def fix_file(file_path: Path):
    """Fix a single integration test file."""
    with open(file_path) as f:
        content = f.read()

    original_content = content

    # Add imports if not present
    if "from src.models.article import ArticleCreate" not in content:
        # Find the last import line
        lines = content.split("\n")
        last_import_idx = max(
            i for i, line in enumerate(lines) if line.startswith("import ") or line.startswith("from ")
        )
        lines.insert(last_import_idx + 1, "from src.models.article import ArticleCreate")
        lines.insert(last_import_idx + 2, "from src.utils.content import ContentProcessor")
        content = "\n".join(lines)

    # Add helper function if not present
    if "def create_test_article(" not in content:
        helper = '''
def create_test_article(title: str, content: str, canonical_url: str, source_id: int = 1) -> ArticleCreate:
    """Helper to create a test article with all required fields."""
    processor = ContentProcessor()
    content_hash = processor.compute_content_hash(content)
    return ArticleCreate(
        title=title,
        content=content,
        canonical_url=canonical_url,
        source_id=source_id,
        published_at=datetime.now(),
        content_hash=content_hash
    )

'''
        # Insert after last import, before first class
        lines = content.split("\n")
        class_idx = next(
            i
            for i, line in enumerate(lines)
            if line.strip().startswith("@pytest.mark.") or line.strip().startswith("class ")
        )
        lines.insert(class_idx, helper)
        content = "\n".join(lines)

    # Fix create_article calls
    pattern = r"article = await test_database_manager\.create_article\(\{([^}]+)\}\)"

    def replace_create_article(match):
        data_str = match.group(1)
        # Extract fields from the dict string
        fields = {}
        for line in data_str.split(","):
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().strip("\"'")
                value = value.strip().strip(",\"'")
                fields[key] = value

        # Build the replacement
        title = fields.get("title", '"Test Article"')
        content = fields.get("content", '"Content"')
        url = fields.get("canonical_url", '"https://test.example.com/test"')
        source_id = fields.get("source_id", "1")

        return f"        article = await test_database_manager.create_article(create_test_article(\n            title={title},\n            content={content},\n            canonical_url={url},\n            source_id={source_id}\n        ))"

    new_content = re.sub(pattern, replace_create_article, content)

    if new_content != original_content:
        with open(file_path, "w") as f:
            f.write(new_content)
        print(f"Fixed: {file_path}")
        return True
    return False


if __name__ == "__main__":
    integration_tests = [
        Path("tests/integration/test_annotation_feedback_integration.py"),
        Path("tests/integration/test_scoring_system_integration.py"),
        Path("tests/integration/test_content_pipeline_integration.py"),
    ]

    for test_file in integration_tests:
        if test_file.exists():
            fix_file(test_file)
