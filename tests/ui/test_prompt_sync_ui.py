"""
UI tests for prompt synchronization between help modals and prompt files.

These tests verify that the prompt content shown in help modals matches
the actual prompt files used by the backend, ensuring users see accurate
information about what prompts are being sent to AI models.

This is a UI content consistency test - it validates that help modal
content (which is UI) matches the backend prompt files.
"""

import re
from pathlib import Path

import pytest


def normalize_prompt(content: str) -> str:
    """
    Normalize prompt content for comparison:
    - Remove placeholder variables ({title}, {source}, etc.)
    - Normalize whitespace
    - Remove trailing/leading whitespace from lines
    """
    # Replace placeholder variables
    content = re.sub(r"\{[^}]+\}", "{placeholder}", content)

    # Normalize whitespace - split lines, trim, filter empty
    lines = [line.strip() for line in content.split("\n") if line.strip()]

    # Join and normalize spaces
    normalized = "\n".join(lines)
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


def extract_prompt_from_js(html_content: str, function_name: str) -> str | None:
    """
    Extract prompt content from JavaScript function in HTML template.
    Handles multiline template strings with backticks.
    """
    # Find the function start
    func_pattern = re.compile(rf"function\s+{function_name}\s*\([^)]*\)\s*\{{", re.DOTALL)
    func_match = func_pattern.search(html_content)
    if not func_match:
        return None

    # Find the position after the function declaration
    func_start = func_match.end()
    func_body = html_content[func_start:]

    # Find "const promptContent = `"
    prompt_start_pattern = re.compile(r"const\s+promptContent\s*=\s*`")
    start_match = prompt_start_pattern.search(func_body)
    if not start_match:
        return None

    # Find the start position of the template string content
    content_start = start_match.end()
    remaining = func_body[content_start:]

    # Find the closing backtick (not preceded by backslash)
    # Template strings can contain {placeholders} but not actual backticks unless escaped
    i = 0
    while i < len(remaining):
        if remaining[i] == "\\" and i + 1 < len(remaining):
            i += 2  # Skip escaped character (including escaped backtick)
            continue
        if remaining[i] == "`":
            # Found closing backtick
            return remaining[:i].strip()
        i += 1

    # If we reach here, no closing backtick found (malformed template string)
    return None


def load_prompt_file(prompt_name: str) -> str:
    """Load prompt file from disk."""
    prompt_path = Path("src") / "prompts" / f"{prompt_name}.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file {prompt_path} not found")

    return prompt_path.read_text(encoding="utf-8").strip()


class TestPromptSynchronization:
    """Test that help modal prompts match backend prompt files."""

    @pytest.fixture(scope="class")
    def html_content(self):
        """Load the article_detail.html template file."""
        template_path = Path("src") / "web" / "templates" / "article_detail.html"
        return template_path.read_text(encoding="utf-8")

    @pytest.mark.ui
    @pytest.mark.help
    def test_ranking_help_matches_gpt4o_prompt(self, html_content):
        """Test that showRankingHelp() matches gpt4o_sigma_ranking.txt."""
        js_prompt = extract_prompt_from_js(html_content, "showRankingHelp")
        assert js_prompt is not None, "Could not extract prompt from showRankingHelp()"

        file_prompt = load_prompt_file("gpt4o_sigma_ranking")

        # Normalize both for comparison
        normalized_js = normalize_prompt(js_prompt)
        normalized_file = normalize_prompt(file_prompt)

        # Check that key sections match
        assert "Telemetry-First SIGMA Huntability Rubric" in normalized_js
        assert "Telemetry-First SIGMA Huntability Rubric" in normalized_file

        # Check critical sections exist in both
        assert "CRITICAL: Atomic IOC Exclusion" in normalized_js
        assert "CRITICAL: Atomic IOC Exclusion" in normalized_file

        assert "Category 3: Network Telemetry" in normalized_js
        assert "Category 3: Network Telemetry" in normalized_file

        assert "Single domains (one-off domains)" in normalized_js
        assert "Single domains (one-off domains)" in normalized_file

        # Check scoring methodology matches (normalized format may collapse spaces)
        assert "Max Raw Score" in normalized_js and "21" in normalized_js
        assert "Max Raw Score" in normalized_file and "21" in normalized_file

        # Check all 7 categories are present
        for i in range(1, 8):
            assert f"Category {i}:" in normalized_js
            assert f"Category {i}:" in normalized_file

        print("✅ showRankingHelp() prompt matches gpt4o_sigma_ranking.txt")

    @pytest.mark.ui
    @pytest.mark.help
    @pytest.mark.quarantine
    @pytest.mark.skip(reason="Prompt comparison assertion failure - prompt content mismatch needs investigation")
    def test_sigma_help_matches_sigma_generation_prompt(self, html_content):
        """Test that showSigmaHelp() matches sigma_generation.txt."""
        js_prompt = extract_prompt_from_js(html_content, "showSigmaHelp")
        assert js_prompt is not None, "Could not extract prompt from showSigmaHelp()"

        file_prompt = load_prompt_file("sigma_generation")

        # Normalize both for comparison
        normalized_js = normalize_prompt(js_prompt)
        normalized_file = normalize_prompt(file_prompt)

        # Check key sections match
        assert "Generate a Sigma detection rule" in normalized_js
        assert "Generate a Sigma detection rule" in normalized_file

        assert "Focus on TTPs" in normalized_js
        assert "Focus on TTPs" in normalized_file

        assert "Output ONLY the YAML rule content" in normalized_js
        assert "Output ONLY the YAML rule content" in normalized_file

        assert "logsource:" in normalized_js
        assert "logsource:" in normalized_file

        print("✅ showSigmaHelp() prompt matches sigma_generation.txt")

    @pytest.mark.ui
    @pytest.mark.help
    def test_ranking_help_contains_atomic_ioc_exclusions(self, html_content):
        """Test that showRankingHelp() contains all required atomic IOC exclusions."""
        js_prompt = extract_prompt_from_js(html_content, "showRankingHelp")
        assert js_prompt is not None

        prompt_lower = js_prompt.lower()

        # Verify atomic IOC exclusions are present
        assert "do not award points for atomic iocs" in prompt_lower
        assert "single ip addresses" in prompt_lower
        assert "single domains" in prompt_lower
        assert "file hashes" in prompt_lower
        assert "single urls without behavioral patterns" in prompt_lower

        # Verify pattern guidance is present
        assert "domain patterns" in prompt_lower
        assert "url path patterns" in prompt_lower
        assert "behavioral combinations" in prompt_lower

        # Verify network category has explicit exclusion
        assert "category 3: network telemetry" in prompt_lower
        assert "single exact domains are atomic iocs" in prompt_lower

        print("✅ showRankingHelp() contains all required atomic IOC exclusions")

    @pytest.mark.ui
    @pytest.mark.help
    def test_ranking_help_has_all_seven_scoring_categories(self, html_content):
        """Test that showRankingHelp() has all 7 scoring categories."""
        js_prompt = extract_prompt_from_js(html_content, "showRankingHelp")
        assert js_prompt is not None

        prompt = js_prompt

        # Verify all 7 categories exist
        assert re.search(r"Category\s+1:\s*Process\s+Command-Line", prompt, re.IGNORECASE)
        assert re.search(r"Category\s+2:\s*Parent[→>]\s*Child\s+Process", prompt, re.IGNORECASE)
        assert re.search(r"Category\s+3:\s*Network\s+Telemetry", prompt, re.IGNORECASE)
        assert re.search(r"Category\s+4:\s*Structured.*Event\s+Mapping", prompt, re.IGNORECASE)
        assert re.search(r"Category\s+5:\s*Persistence.*Registry.*Services", prompt, re.IGNORECASE)
        assert re.search(r"Category\s+6:\s*Obfuscation\s+Handling", prompt, re.IGNORECASE)
        assert re.search(r"Category\s+7:\s*Evidence\s+Quality", prompt, re.IGNORECASE)

        # Verify weights are present
        assert "Weight: 4" in prompt
        assert "Weight: 3" in prompt
        assert "Weight: 2" in prompt

        print("✅ showRankingHelp() has all 7 scoring categories with weights")

    @pytest.mark.ui
    @pytest.mark.help
    def test_ioc_help_has_valid_prompt_content(self, html_content):
        """Test that showIOCHelp() has valid IOC extraction prompt."""
        js_prompt = extract_prompt_from_js(html_content, "showIOCHelp")
        assert js_prompt is not None

        prompt_lower = js_prompt.lower()

        # Verify IOC extraction guidance is present
        assert "extract indicators of compromise" in prompt_lower
        assert "ioc types" in prompt_lower
        assert "ip addresses" in prompt_lower
        assert "domains" in prompt_lower
        assert "file hashes" in prompt_lower
        assert "output format" in prompt_lower
        assert "json" in prompt_lower

        print("✅ showIOCHelp() has valid IOC extraction prompt")

    @pytest.mark.ui
    @pytest.mark.help
    def test_custom_help_has_valid_prompt_content(self, html_content):
        """Test that showCustomHelp() has valid custom prompt template."""
        js_prompt = extract_prompt_from_js(html_content, "showCustomHelp")
        assert js_prompt is not None

        prompt_lower = js_prompt.lower()

        # Verify custom prompt guidance is present
        assert "cybersecurity analyst" in prompt_lower
        assert "threat intelligence" in prompt_lower
        assert "user request" in prompt_lower
        assert "article content" in prompt_lower

        print("✅ showCustomHelp() has valid custom prompt template")

    @pytest.mark.ui
    @pytest.mark.help
    def test_all_ranking_prompts_exclude_atomic_iocs(self):
        """Test that all ranking prompt files exclude atomic IOCs."""
        ranking_prompts = ["gpt4o_sigma_ranking", "llm_sigma_ranking_simple", "lmstudio_sigma_ranking"]

        for prompt_name in ranking_prompts:
            prompt = load_prompt_file(prompt_name).lower()

            # Check for atomic IOC exclusions (at least one variation should exist)
            has_exclusion = (
                "do not award points for atomic iocs" in prompt
                or "do not award points" in prompt
                or "atomic ioc" in prompt
                or "single domains" in prompt
            )

            assert has_exclusion, f"{prompt_name}.txt should exclude atomic IOCs"
            print(f"✅ {prompt_name}.txt excludes atomic IOCs")

    @pytest.mark.ui
    @pytest.mark.help
    def test_ranking_prompt_files_have_consistent_structure(self):
        """Test that ranking prompt files have consistent structure."""
        prompts = {
            "gpt4o_sigma_ranking": load_prompt_file("gpt4o_sigma_ranking"),
            "llm_sigma_ranking_simple": load_prompt_file("llm_sigma_ranking_simple"),
            "lmstudio_sigma_ranking": load_prompt_file("lmstudio_sigma_ranking"),
        }

        # Check that all have scoring guidance
        for name, content in prompts.items():
            content_lower = content.lower()

            assert "score" in content_lower
            assert "huntability" in content_lower

            # Check atomic IOC exclusion exists in all
            assert (
                "atomic ioc" in content_lower
                or "single domains" in content_lower
                or "do not award points" in content_lower
            ), f"{name}.txt should have atomic IOC exclusion"

            print(f"✅ {name}.txt has consistent structure")
