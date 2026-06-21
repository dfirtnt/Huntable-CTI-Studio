"""Content processing utilities."""

import hashlib

# Temporarily disabled due to Python 3 compatibility issues
# from readability import Document
import logging
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser

from .keyword_registry import build_hunt_scoring_keywords
from .sentence_splitter import split_sentences

logger = logging.getLogger(__name__)


class ContentCleaner:
    """Utility class for cleaning and normalizing content."""

    _MAIN_CONTENT_SELECTORS = (
        "article",
        '[role="main"]',
        "main",
        ".content",
        ".post-content",
        ".entry-content",
        ".blog-content",
        ".article-content",
        "#content",
    )

    @staticmethod
    def prepare_soup_for_selection(soup: BeautifulSoup) -> None:
        """In-place prune of unwanted tags and class/id-pattern elements.

        Decomposes navigation, UI chrome, and advertising elements from the
        soup tree so that subsequent content-selector queries only see article
        body content.  Safe to call more than once (idempotent: decomposed
        nodes are already gone on the second pass).
        """
        # Remove unwanted elements completely
        unwanted_tags = [
            "script",
            "style",
            "nav",
            "header",
            "footer",
            "aside",
            "advertisement",
            "menu",
            "sidebar",
            "breadcrumb",
            "pagination",
            "social",
            "share",
            "comment",
            "related",
            "widget",
            "promo",
            "banner",
            "ad",
            "popup",
            "modal",
            "overlay",
            "tracking",
            "form",
        ]

        for tag_name in unwanted_tags:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Remove elements by class/id patterns (common navigation/UI elements)
        unwanted_patterns = [
            "nav",
            "menu",
            "sidebar",
            "header",
            "footer",
            "breadcrumb",
            "pagination",
            "social",
            "share",
            "comment",
            "related",
            "widget",
            "promo",
            "banner",
            "ad",
            "popup",
            "modal",
            "overlay",
            "tracking",
            "subscribe",
            "newsletter",
            "follow",
            "like",
            "tweet",
            "facebook",
            "advertisement",
            "comments",
        ]

        for element in soup.find_all(
            attrs={"class": lambda x: x and any(p.lower() in str(x).lower() for p in unwanted_patterns)}
        ):
            element.decompose()
        for element in soup.find_all(
            attrs={"id": lambda x: x and any(p.lower() in str(x).lower() for p in unwanted_patterns)}
        ):
            element.decompose()

    @staticmethod
    def find_main_content_node(soup: BeautifulSoup) -> Tag | None:
        """Return the first _MAIN_CONTENT_SELECTORS node with >50 chars of text, else None."""
        for selector in ContentCleaner._MAIN_CONTENT_SELECTORS:
            node = soup.select_one(selector)
            if node and len(node.get_text(strip=True)) > 50:
                return node
        return None

    @staticmethod
    def clean_html(html: str) -> str:
        """Clean HTML content and extract readable text."""
        # Temporarily disabled readability due to Python 3 compatibility issues
        # Always use enhanced cleaning for now
        return ContentCleaner.enhanced_html_clean(html)

    @staticmethod
    def enhanced_html_clean(html: str) -> str:
        """Enhanced HTML cleaning that extracts clean text."""
        if not html:
            return ""
        soup = BeautifulSoup(html, "lxml")
        ContentCleaner.prepare_soup_for_selection(soup)
        main_content = ContentCleaner.find_main_content_node(soup)
        if main_content:
            return ContentCleaner.html_to_text(str(main_content))
        return ContentCleaner.html_to_text(str(soup))

    @staticmethod
    def basic_html_clean(html: str) -> str:
        """Basic HTML cleaning without readability (deprecated - use enhanced_html_clean)."""
        soup = BeautifulSoup(html, "lxml")

        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "advertisement"]):
            tag.decompose()

        # Remove attributes that might cause issues
        for tag in soup.find_all():
            tag.attrs = {k: v for k, v in tag.attrs.items() if k in ["href", "src", "alt", "title"]}

        return str(soup)

    @staticmethod
    def html_to_text(html: str) -> str:
        """Convert HTML to clean text with better formatting."""
        try:
            # Handle None and empty input
            if html is None:
                return ""
            if not html:
                return ""

            # Ensure we have clean text input
            if isinstance(html, bytes):
                html = html.decode("utf-8", errors="ignore")

            soup = BeautifulSoup(html, "lxml")

            # Add line breaks for block elements before extracting text
            for tag in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br"]):
                tag.insert_after("\n")

            # Extract text. strip=False is deliberate: the block-level "\n"
            # inserted above are whitespace-only and would be dropped by
            # strip=True. normalize_whitespace_keep_newlines() below collapses
            # the resulting extra spaces while preserving the block newlines.
            text = soup.get_text(separator=" ", strip=False)

            # Clean up whitespace and normalize (preserve block newlines so
            # command-line / multi-line artifacts stay segmentable downstream)
            text = ContentCleaner.normalize_whitespace_keep_newlines(text)

            # Remove non-printable characters
            text = ContentCleaner.clean_text_characters(text)

            return text
        except Exception as e:
            logger.warning(f"Error in html_to_text: {e}")
            # Fallback to simple text extraction
            return ContentCleaner.normalize_whitespace_keep_newlines(str(html))

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize whitespace in text."""
        # Replace multiple whitespace characters with single space
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def normalize_whitespace_keep_newlines(text: str) -> str:
        """Normalize whitespace while preserving newlines (block structure).

        Collapses runs of *horizontal* whitespace (spaces, tabs, carriage
        returns) to a single space but keeps ``\\n`` intact, so command-line and
        multi-line artifacts stay segmentable for downstream extractors. Trims
        horizontal space hugging each newline and caps blank-line runs at one.

        Use this for article *body* text. Titles/tags/authors should keep using
        :meth:`normalize_whitespace`, which flattens to a single line.
        """
        if not text:
            return ""
        # ``[^\S\n]`` = any whitespace that is NOT a newline (space/tab/\r/etc.)
        text = re.sub(r"[^\S\n]+", " ", text)
        # Drop spaces hugging newlines, then cap consecutive blank lines at one
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def clean_text_characters(text: str) -> str:
        """Clean text by removing non-printable and control characters."""
        try:
            # First, ensure we have proper UTF-8 encoding
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")

            # Remove Unicode replacement characters ()
            text = text.replace("\ufffd", "")

            # Remove control characters and other problematic characters
            # Keep only printable ASCII and common Unicode characters
            cleaned = "".join(
                char for char in text if (char.isprintable() or char.isspace()) and ord(char) < 65536
            )  # Basic Multilingual Plane

            # Remove any remaining problematic sequences
            cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", cleaned)

            # Fix common UTF-8 to Latin-1 corruption patterns
            # Fix possessive apostrophes: ‚Äö√Ñ√¥s -> 's
            cleaned = re.sub(r"‚Äö√Ñ√¥s", "'s", cleaned)
            cleaned = re.sub(r"‚Äö√Ñ√¥", "'", cleaned)

            # Additional cleanup for other encoding issues
            cleaned = re.sub(r"[^\x00-\x7F]+", " ", cleaned)  # Replace remaining non-ASCII with spaces

            return cleaned
        except Exception as e:
            logger.warning(f"Error cleaning text characters: {e}")
            # Fallback: remove only null bytes and common control chars
            return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

    @staticmethod
    def extract_summary(content: str, max_length: int = 500) -> str:
        """Extract summary from content."""
        # Convert HTML to text if needed
        if "<" in content and ">" in content:
            text = ContentCleaner.html_to_text(content)
        else:
            text = content

        # Normalize whitespace
        text = ContentCleaner.normalize_whitespace(text)

        # Find first complete sentence that doesn't exceed max_length
        sentences = split_sentences(text)
        summary = ""

        for sentence in sentences:
            if not sentence:
                continue

            test_summary = f"{summary} {sentence}".strip()
            if len(test_summary) <= max_length:
                summary = test_summary
            else:
                break

        # If no complete sentences fit, truncate at word boundary
        if not summary:
            words = text.split()
            summary = ""
            for word in words:
                test_summary = f"{summary} {word}".strip()
                if len(test_summary) <= max_length - 3:  # Leave room for "..."
                    summary = test_summary
                else:
                    break
            summary += "..."

        return summary

    @staticmethod
    def calculate_content_hash(title: str, content: str) -> str:
        """Calculate SHA256 hash of content for deduplication."""
        # Normalize content for hashing
        normalized_title = ContentCleaner.normalize_whitespace(title.lower())
        normalized_content = ContentCleaner.normalize_whitespace(ContentCleaner.html_to_text(content).lower())

        combined = f"{normalized_title}\n{normalized_content}".encode()
        return hashlib.sha256(combined).hexdigest()


class DateExtractor:
    """Utility class for extracting and parsing dates."""

    @staticmethod
    def parse_date(date_str: str) -> datetime | None:
        """Parse date string to datetime object."""
        if not date_str:
            return None

        try:
            # Handle common date formats
            date_str = date_str.strip()

            # Parse the date (may be timezone-aware)
            parsed_date = date_parser.parse(date_str)

            # Convert to timezone-naive datetime for database compatibility
            if parsed_date.tzinfo is not None:
                # Convert to UTC first, then remove timezone info
                parsed_date = parsed_date.astimezone().replace(tzinfo=None)

            return parsed_date

        except Exception as e:
            logger.debug(f"Failed to parse date '{date_str}': {e}")
            return None

    @staticmethod
    def extract_date_from_url(url: str) -> datetime | None:
        """Extract date from URL path if possible."""
        # Look for YYYY/MM/DD or YYYY-MM-DD patterns
        date_patterns = [
            r"(\d{4})/(\d{1,2})/(\d{1,2})",  # 2024/01/15
            r"(\d{4})-(\d{1,2})-(\d{1,2})",  # 2024-01-15
            r"(\d{4})(\d{2})(\d{2})",  # 20240115
        ]

        for pattern in date_patterns:
            match = re.search(pattern, url)
            if match:
                try:
                    year, month, day = map(int, match.groups())
                    return datetime(year, month, day)
                except ValueError:
                    continue

        return None


class MetadataExtractor:
    """Utility class for extracting metadata from HTML."""

    @staticmethod
    def extract_meta_tags(soup: BeautifulSoup) -> dict[str, str]:
        """Extract all meta tag content."""
        meta_data = {}

        # Standard meta tags
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property") or meta.get("http-equiv")
            content = meta.get("content")

            if name and content:
                meta_data[name.lower()] = content

        return meta_data

    @staticmethod
    def extract_opengraph(soup: BeautifulSoup) -> dict[str, str]:
        """Extract OpenGraph metadata."""
        og_data = {}

        for meta in soup.find_all("meta"):
            property_name = meta.get("property", "")
            if property_name.startswith("og:"):
                content = meta.get("content")
                if content:
                    key = property_name[3:]  # Remove 'og:' prefix
                    og_data[key] = content

        return og_data

    @staticmethod
    def extract_twitter_cards(soup: BeautifulSoup) -> dict[str, str]:
        """Extract Twitter Card metadata."""
        twitter_data = {}

        for meta in soup.find_all("meta"):
            name = meta.get("name", "")
            if name.startswith("twitter:"):
                content = meta.get("content")
                if content:
                    key = name[8:]  # Remove 'twitter:' prefix
                    twitter_data[key] = content

        return twitter_data

    @staticmethod
    def extract_canonical_url(soup: BeautifulSoup) -> str | None:
        """Extract canonical URL from link tag."""
        canonical = soup.find("link", {"rel": "canonical"})
        if canonical:
            return canonical.get("href")
        return None

    @staticmethod
    def extract_authors(soup: BeautifulSoup) -> list[str]:
        """Extract author information from various sources."""
        authors = []

        # Try meta tags first
        author_meta = soup.find("meta", {"name": "author"})
        if author_meta:
            content = author_meta.get("content", "")
            if content:
                # Split on common delimiters
                for delimiter in [",", ";", "&", " and "]:
                    if delimiter in content:
                        authors.extend([a.strip() for a in content.split(delimiter)])
                        break
                else:
                    authors.append(content.strip())

        # Try OpenGraph
        if not authors:
            og_author = soup.find("meta", {"property": "article:author"})
            if og_author:
                content = og_author.get("content", "").strip()
                if content:
                    authors.append(content)

        # Try structured data (basic)
        if not authors:
            # Look for author in JSON-LD or microdata
            author_elements = soup.find_all(attrs={"itemprop": "author"})
            for elem in author_elements:
                if elem.string:
                    authors.append(elem.string.strip())

        # Clean and deduplicate
        cleaned_authors = []
        for author in authors:
            author = author.strip()
            if author and author not in cleaned_authors:
                cleaned_authors.append(author)

        return cleaned_authors[:5]  # Limit to 5 authors

    @staticmethod
    def extract_tags(soup: BeautifulSoup) -> list[str]:
        """Extract tags/categories from various sources."""
        tags = set()

        # Meta keywords
        keywords_meta = soup.find("meta", {"name": "keywords"})
        if keywords_meta:
            content = keywords_meta.get("content", "")
            if content:
                tags.update([tag.strip() for tag in content.split(",") if tag.strip()])

        # OpenGraph tags
        og_tags = soup.find_all("meta", {"property": "article:tag"})
        for tag_meta in og_tags:
            content = tag_meta.get("content", "").strip()
            if content:
                tags.add(content)

        # Category meta
        category_meta = soup.find("meta", {"name": "category"})
        if category_meta:
            content = category_meta.get("content", "").strip()
            if content:
                tags.add(content)

        # Convert to sorted list and limit
        return sorted(list(tags))[:10]  # Limit to 10 tags


def validate_content(title: str, content: str, url: str, source_config: dict[str, Any] | None = None) -> list[str]:
    """
    Validate content and return list of issues.

    Args:
        title: Article title
        content: Article content
        url: Article URL
        source_config: Optional source configuration dict containing min_content_length

    Returns:
        List of validation issues (empty if valid)
    """
    issues = []

    if not title or not title.strip():
        issues.append("Missing or empty title")
    elif len(title.strip()) < 5:
        issues.append("Title too short")
    elif len(title.strip()) > 500:
        issues.append("Title too long")

    if not content or not content.strip():
        issues.append("Missing or empty content")
    else:
        # Check for garbage content patterns
        if _is_garbage_content(content):
            issues.append("Content appears to be garbage/compressed data")

        # Check for compression failure messages
        if _has_compression_failure_indicators(content):
            issues.append("Content indicates extraction failure")

        # Check for binary/control characters
        if any(ord(c) < 32 and c not in "\n\r\t" for c in content):
            issues.append("Content contains binary or control characters")

        # Check for unicode corruption
        if "\ufffd" in content or "\ufffd" in content:
            issues.append("Content contains unicode corruption indicators")

        text_content = ContentCleaner.html_to_text(content)
        content_length = len(text_content.strip())

        # Use source-specific minimum content length if configured
        min_length = 200  # Default minimum
        if source_config and "min_content_length" in source_config:
            min_length = source_config["min_content_length"]

        if content_length < min_length:
            issues.append(f"Content too short (minimum {min_length} chars, found {content_length})")

    if not url or not url.strip():
        issues.append("Missing URL")
    elif not url.startswith(("http://", "https://")):
        issues.append("Invalid URL format")

    return issues


def _is_garbage_content(content: str) -> bool:
    """
    Detect if content is garbage/compressed data.

    Returns:
        True if content appears to be garbage
    """
    if not content:
        return False

    # Convert to lowercase for analysis
    content_lower = content.lower()

    # Check for high ratio of problematic characters
    problematic_chars = sum(1 for c in content if c in "[]{}|\\")
    total_chars = len(content)

    if total_chars > 0:
        problematic_ratio = problematic_chars / total_chars
        if problematic_ratio > 0.15:  # Increase threshold to 15% problematic characters
            # High problematic ratio detected
            return True

    # Check for specific garbage patterns
    if "`E9 UI=" in content or "cwCz _9hvtYfL" in content:
        # Specific garbage patterns found
        return True

    # Check for consecutive problematic characters
    consecutive_count = 0
    max_consecutive = 0
    for char in content:
        if char in "[]{}|\\":
            consecutive_count += 1
            max_consecutive = max(max_consecutive, consecutive_count)
        else:
            consecutive_count = 0

    # Check final sequence
    if consecutive_count >= 3:
        max_consecutive = max(max_consecutive, consecutive_count)

    if max_consecutive >= 5:  # Increase threshold to 5 or more consecutive problematic chars
        # Too many consecutive problematic chars detected
        return True

    # Check for binary-like patterns (very permissive - only flag truly problematic sequences)
    binary_patterns = [
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\xFF]{10,}",  # Control characters and high-bit chars in long sequences
        r"[^\w\s\.\,\;\:\!\?\(\)\-\+\=\<\>\/\"\'\[\]\{\}\|\\\~\#\$\%\^\&\*\_\`\@]{15,}",  # Very long sequences of truly unusual chars
    ]

    for pattern in binary_patterns:
        matches = re.findall(pattern, content)
        if matches:
            # Binary pattern matches detected
            return True

    # Check for binary control characters (even in small amounts)
    if any(ord(c) < 32 and c not in "\n\r\t" for c in content):
        # Contains null bytes or other control characters (excluding common whitespace)
        return True

    # Check for compression artifacts
    compression_indicators = [
        "compression issues",
        "website compression",
        "content extraction failed",
        "failed due to website",
        "compression failed",
        "extraction disabled",
    ]

    if any(indicator in content_lower for indicator in compression_indicators):
        logger.debug("Compression indicators found")
        return True

    # Check for unicode replacement characters (corruption indicators)
    # U+FFFD is the unicode replacement character used when decoding fails
    if "\ufffd" in content or "\ufffd" in content:
        # Unicode replacement characters indicate corruption
        return True

    return False


def _has_compression_failure_indicators(content: str) -> bool:
    """
    Check if content contains indicators of extraction failure.

    Returns:
        True if content suggests extraction failed
    """
    if not content:
        return False

    content_lower = content.lower()

    # Patterns that indicate extraction failure
    failure_patterns = [
        "content extraction failed",
        "failed due to website compression",
        "extraction is disabled",
        "please visit the original article",
        "compression issues",
        "website compression issues",
        "full content extraction is disabled",
    ]

    return any(pattern in content_lower for pattern in failure_patterns)


# Hunt-scoring keyword sets are DERIVED from the faceted registry
# (config/keyword_registry.yaml) — the single source of truth (decision D-A). A byte-equal
# parity test (tests/test_keyword_registry.py) guards this projection against drift.
HUNT_SCORING_KEYWORDS = build_hunt_scoring_keywords()


class ThreatHuntingScorer:
    """Enhanced scoring for threat hunting and malware analysis content."""

    @staticmethod
    def score_threat_hunting_content(title: str, content: str) -> dict[str, Any]:
        """
        Score content for threat hunting quality using Windows malware keywords.

        Returns:
            Dict containing:
            - threat_hunting_score: float (0-100)
            - perfect_keyword_matches: List[str]
            - good_keyword_matches: List[str]
            - lolbas_matches: List[str]
            - intelligence_matches: List[str]
            - negative_matches: List[str]
        """
        if not content:
            return {
                "threat_hunting_score": 0.0,
                "perfect_keyword_matches": [],
                "good_keyword_matches": [],
                "lolbas_matches": [],
                "intelligence_matches": [],
                "negative_matches": [],
            }

        # Clean content for analysis
        clean_content = ContentCleaner.html_to_text(content).lower()
        title_lower = title.lower() if title else ""
        full_text = f"{title_lower} {clean_content}"

        # Find keyword matches
        perfect_matches = []
        good_matches = []
        lolbas_matches = []
        intelligence_matches = []

        # Check perfect discriminators
        for keyword in HUNT_SCORING_KEYWORDS["perfect_discriminators"]:
            if ThreatHuntingScorer._keyword_matches(keyword, full_text):
                perfect_matches.append(keyword)

        # Check good discriminators
        for keyword in HUNT_SCORING_KEYWORDS["good_discriminators"]:
            if ThreatHuntingScorer._keyword_matches(keyword, full_text):
                good_matches.append(keyword)

        # Check LOLBAS executables
        for executable in HUNT_SCORING_KEYWORDS["lolbas_executables"]:
            if ThreatHuntingScorer._keyword_matches(executable, full_text):
                lolbas_matches.append(executable)

        # Check intelligence indicators
        for indicator in HUNT_SCORING_KEYWORDS["intelligence_indicators"]:
            if ThreatHuntingScorer._keyword_matches(indicator, full_text):
                intelligence_matches.append(indicator)

        # Check negative indicators (penalize educational/marketing content)
        negative_matches = []
        for negative in HUNT_SCORING_KEYWORDS["negative_indicators"]:
            if ThreatHuntingScorer._keyword_matches(negative, full_text):
                negative_matches.append(negative)

        # Calculate scores using geometric series with 50% diminishing returns
        # Each successive match adds 50% of the previous increment
        # Formula: score = max_points * (1 - 0.5^n) where n = number of matches
        # This ensures scores approach but never reach the category maximum

        def geometric_score(matches: int, max_points: float) -> float:
            """Calculate score using geometric series that never reaches max."""
            if matches == 0:
                return 0.0
            # Score = max_points * (1 - 0.5^n)
            # As n increases, 0.5^n approaches 0, so score approaches max_points but never reaches it
            return max_points * (1.0 - (0.5**matches))

        # Perfect Discriminators: 75 points max (dominant weight for technical depth)
        perfect_score = geometric_score(len(perfect_matches), 75.0)

        # LOLBAS Executables: 10 points max (practical attack techniques)
        lolbas_score = geometric_score(len(lolbas_matches), 10.0)

        # Intelligence Indicators: 10 points max (core threat intelligence value)
        intelligence_score = geometric_score(len(intelligence_matches), 10.0)

        # Good Discriminators: 5 points max (supporting technical content)
        good_score = geometric_score(len(good_matches), 5.0)

        # Negative Penalties: 15 points max with 50% diminishing returns (same as positive categories)
        negative_penalty = geometric_score(len(negative_matches), 15.0)

        # Calculate base score (positive contributions)
        base_score = perfect_score + good_score + lolbas_score + intelligence_score

        threat_hunting_score = base_score - negative_penalty

        # Calculate final threat hunting score (0-100 range, but will never reach 100)
        # Theoretical max: 75 + 5 + 10 + 10 = 100, but geometric series ensures it never reaches 100
        # Cap at 99.9 to prevent rounding to 100.0
        threat_hunting_score = max(
            0.0,
            min(
                99.9,
                threat_hunting_score,
            ),
        )

        return {
            "threat_hunting_score": round(threat_hunting_score, 1),
            "perfect_keyword_matches": perfect_matches,
            "good_keyword_matches": good_matches,
            "lolbas_matches": lolbas_matches,
            "intelligence_matches": intelligence_matches,
            "negative_matches": negative_matches,
        }

    @staticmethod
    def _keyword_matches(keyword: str, text: str) -> bool:
        """
        Check if keyword matches in text using word boundaries or regex patterns.

        Args:
            keyword: Keyword to search for (can be regex pattern)
            text: Text to search in

        Returns:
            True if keyword is found with proper word boundaries or regex match
        """
        # Regex patterns for cmd.exe obfuscation techniques
        regex_patterns = [
            r"%[A-Za-z0-9_]+:~[0-9]+(,[0-9]+)?%",  # env-var substring access
            r"%[A-Za-z0-9_]+:[^=%%]+=[^%]*%",  # env-var string substitution
            r"![A-Za-z0-9_]+!",  # delayed expansion markers
            r"\bcmd(\.exe)?\s*/V(?::[^ \t/]+)?",  # /V:ON obfuscated variants
            r"\bset\s+[A-Za-z0-9_]+\s*=",  # multiple SET stages
            r"\bcall\s+(set|%[A-Za-z0-9_]+%|![A-Za-z0-9_]+!)",  # CALL invocation
            r"(%[^%]+%){4,}",  # adjacent env-var concatenation
            r"\bfor\s+/?[A-Za-z]*\s+%[A-Za-z]\s+in\s*\(",  # FOR loops
            r"![A-Za-z0-9_]+:~%[A-Za-z],1!",  # FOR-indexed substring extraction
            r"\bfor\s+/L\s+%[A-Za-z]\s+in\s*\([^)]+\)",  # reversal via /L
            r"%[A-Za-z0-9_]+:~-[0-9]+%|%[A-Za-z0-9_]+:~[0-9]+%",  # tail trimming
            r"%[A-Za-z0-9_]+:\*[^!%]+=!%",  # asterisk-based substitution
            r"[^\w](s\^+e\^*t|s\^*e\^+t)[^\w]",  # caret-obfuscated set
            r"[^\w](c\^+a\^*l\^*l|c\^*a\^+l\^*l|c\^*a\^*l\^+l)[^\w]",  # caret-obfuscated call
            r"[^\w]([a-z]\^+[a-z](\^+[a-z])*)[^\w]",  # caret-obfuscated commands (any length)
            r"%[^%]+%<[^>]*|set\s+[A-Za-z0-9_]+\s*=\s*[^&|>]*\|",  # stdin piping patterns
        ]

        # Check if keyword is a regex pattern
        if keyword in regex_patterns:
            return bool(re.search(keyword, text, re.IGNORECASE))

        # Get regex pattern for matching
        pattern = ThreatHuntingScorer._build_keyword_pattern(keyword)

        return bool(re.search(pattern, text, re.IGNORECASE))

    @staticmethod
    def _build_keyword_pattern(keyword: str) -> str:
        """
        Build regex pattern for keyword matching.
        Shared logic used by both scoring and highlighting.

        Args:
            keyword: Keyword to build pattern for

        Returns:
            Regex pattern string
        """
        # Escape special regex characters for literal matching
        escaped_keyword = re.escape(keyword)

        # For certain keywords, allow partial matches (like "hunting" in "threat hunting")
        partial_match_keywords = [
            "hunting",
            "detection",
            "monitor",
            "alert",
            "executable",
            "parent-child",
            "defender query",
        ]

        # For wildcard keywords, use prefix matching
        wildcard_keywords = ["spawn"]

        # For symbol keywords and path prefixes, don't use word boundaries
        symbol_keywords = [
            "==",
            "!=",
            "<=",
            ">=",
            "::",
            "-->",
            "->",
            "//",
            "--",
            "\\",
            "|",
            "C:\\",
            "D:\\",
        ]

        if keyword.lower() in partial_match_keywords:
            # Allow partial matches for these keywords
            return escaped_keyword
        if keyword.lower() in wildcard_keywords:
            # Allow wildcard matching (e.g., "spawn" matches "spawns", "spawning", "spawned")
            return escaped_keyword + r"\w*"
        if keyword in symbol_keywords:
            # For symbols, don't use word boundaries
            return escaped_keyword
        if keyword.startswith("-") or keyword.endswith("-"):
            # For keywords with leading/trailing hyphens, use letter boundaries instead of word boundaries
            return r"(?<![a-zA-Z])" + escaped_keyword + r"(?![a-zA-Z])"
        if keyword.startswith("."):
            # For extension-only keywords (like .exe, .dll, .bat, .ps1), only match when
            # they appear as actual file extensions (preceded by alphanumeric characters)
            # This prevents false positives when the extension doesn't appear in the content
            return r"[a-zA-Z0-9_]" + escaped_keyword + r"\b"
        if keyword.endswith(".exe"):
            # For .exe executables, always require .exe extension to avoid false positives
            # with common English words (e.g., "services", "system", "process")
            base_name = keyword[:-4]  # Remove .exe
            # For short base names (2-3 chars), allow without extension if followed by non-word char
            # This handles cases like "cmd" in command lines, but prevents matches in words
            if len(base_name) <= 3:
                # Match: base.exe OR base followed by non-word char (space, punctuation, etc.)
                return r"\b" + re.escape(base_name) + r"(\.exe\b|(?![a-zA-Z0-9]))"
            # For longer names, require .exe extension to prevent false positives
            # with common words (e.g., "services" in "cloud services")
            return r"\b" + re.escape(base_name) + r"\.exe\b"
        if keyword.endswith(".dll"):
            # For .dll files, match both with and without .dll extension
            base_name = keyword[:-4]  # Remove .dll
            # For short base names (2-3 chars), require either .dll extension or
            # ensure it's not part of a longer word by requiring non-word char after
            if len(base_name) <= 3:
                # Match: base.dll OR base followed by non-word char (space, punctuation, etc.)
                return r"\b" + re.escape(base_name) + r"(\.dll\b|(?![a-zA-Z0-9]))"
            # For longer names, use standard word boundary matching
            return r"\b" + re.escape(base_name) + r"(\.dll)?\b"
        if " " in keyword:
            # For multi-word phrases, ensure word boundaries at start and end
            # but allow flexible matching in the middle
            return r"\b" + escaped_keyword + r"\b"
        # Use word boundaries for other keywords
        return r"\b" + escaped_keyword + r"\b"


class ContentExtractor:
    """Extract content and metadata from HTML."""

    def __init__(self):
        self.soup = None

    def extract_title(self, html: str) -> str:
        """Extract title from HTML."""
        try:
            soup = BeautifulSoup(html, "lxml")

            # Try title tag first
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                return title_tag.string.strip()

            # Try h1 tag
            h1_tag = soup.find("h1")
            if h1_tag:
                return h1_tag.get_text(strip=True)

            # Try meta title
            meta_title = soup.find("meta", {"property": "og:title"})
            if meta_title and meta_title.get("content"):
                return meta_title.get("content").strip()

            return ""
        except Exception:
            return ""

    def extract_meta_description(self, html: str) -> str:
        """Extract meta description from HTML."""
        try:
            soup = BeautifulSoup(html, "lxml")

            # Try meta description
            meta_desc = soup.find("meta", {"name": "description"})
            if meta_desc and meta_desc.get("content"):
                return meta_desc.get("content").strip()

            # Try OpenGraph description
            og_desc = soup.find("meta", {"property": "og:description"})
            if og_desc and og_desc.get("content"):
                return og_desc.get("content").strip()

            return ""
        except Exception:
            return ""

    def extract_keywords(self, html: str) -> list[str]:
        """Extract keywords from HTML."""
        try:
            soup = BeautifulSoup(html, "lxml")

            # Try meta keywords
            meta_keywords = soup.find("meta", {"name": "keywords"})
            if meta_keywords and meta_keywords.get("content"):
                keywords = [k.strip() for k in meta_keywords.get("content").split(",")]
                return [k for k in keywords if k]

            return []
        except Exception:
            return []

    def extract_author(self, html: str) -> str:
        """Extract author from HTML."""
        try:
            soup = BeautifulSoup(html, "lxml")

            # Try meta author
            meta_author = soup.find("meta", {"name": "author"})
            if meta_author and meta_author.get("content"):
                return meta_author.get("content").strip()

            # Try OpenGraph author
            og_author = soup.find("meta", {"property": "article:author"})
            if og_author and og_author.get("content"):
                return og_author.get("content").strip()

            return ""
        except Exception:
            return ""

    def extract_published_date(self, html: str) -> str:
        """Extract published date from HTML."""
        try:
            soup = BeautifulSoup(html, "lxml")

            # Try meta published time (both property and name attributes)
            meta_date = soup.find("meta", {"property": "article:published_time"}) or soup.find(
                "meta", {"name": "article:published_time"}
            )
            if meta_date and meta_date.get("content"):
                return meta_date.get("content").strip()

            # Try time tag
            time_tag = soup.find("time")
            if time_tag and time_tag.get("datetime"):
                return time_tag.get("datetime").strip()

            return ""
        except Exception:
            return ""

    def extract_canonical_url(self, html: str) -> str:
        """Extract canonical URL from HTML."""
        try:
            soup = BeautifulSoup(html, "lxml")

            # Try canonical link
            canonical = soup.find("link", {"rel": "canonical"})
            if canonical and canonical.get("href"):
                return canonical.get("href").strip()

            return ""
        except Exception:
            return ""

    def extract_all_metadata(self, html: str) -> dict[str, Any]:
        """Extract all metadata from HTML."""
        return {
            "title": self.extract_title(html),
            "description": self.extract_meta_description(html),
            "keywords": self.extract_keywords(html),
            "author": self.extract_author(html),
            "published_date": self.extract_published_date(html),
            "canonical_url": self.extract_canonical_url(html),
        }


class TextNormalizer:
    """Normalize text content."""

    def __init__(self):
        self.unicode_map = {
            "“": '"',
            '"': '"',
            """: "'", """: "'",
            "–": "-",
            "—": "-",
            "…": "...",
            "©": "(c)",
            "®": "(r)",
            "™": "(tm)",
        }

    def normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace in text."""
        if not text:
            return ""

        # Replace multiple whitespace with single space
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def normalize_unicode(self, text: str) -> str:
        """Normalize Unicode characters."""
        if not text:
            return ""

        # Replace common Unicode characters
        for unicode_char, ascii_char in self.unicode_map.items():
            text = text.replace(unicode_char, ascii_char)

        # Additional Unicode normalization for accented characters
        import unicodedata

        # Normalize to NFD (decomposed form) and remove combining characters
        text = unicodedata.normalize("NFD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")

        return text

    def normalize_case(self, text: str) -> str:
        """Normalize text case."""
        if not text:
            return ""

        # Convert to lowercase
        return text.lower()

    def remove_special_characters(self, text: str) -> str:
        """Remove special characters from text."""
        if not text:
            return ""

        # Remove special characters but keep alphanumeric, spaces, and basic punctuation
        # Remove @#$%^&*()! and other special chars, keep only letters, numbers, spaces, and basic punctuation
        text = re.sub(r"[^\w\s\.\,\;\:\?]", " ", text)
        return self.normalize_whitespace(text)

    def normalize_text(self, text: str) -> str:
        """Comprehensive text normalization."""
        if not text:
            return ""

        # Apply all normalization steps in correct order
        text = self.normalize_unicode(text)
        text = self.remove_special_characters(text)
        text = self.normalize_whitespace(text)
        text = self.normalize_case(text)

        return text
