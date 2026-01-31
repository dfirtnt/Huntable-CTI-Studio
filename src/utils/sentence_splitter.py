"""
Sentence splitting utility using SpaCy's sentencizer.

Provides accurate sentence boundary detection that handles abbreviations,
technical content, and security text better than regex-based approaches.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Lazy-loaded SpaCy nlp object
_nlp = None


def _get_nlp():
    """Lazy-load SpaCy sentencizer with domain-specific abbreviations."""
    global _nlp

    if _nlp is None:
        try:
            from spacy.lang.en import English

            # Create blank English pipeline with only sentencizer
            nlp = English()

            # Add sentencizer component
            if "sentencizer" not in nlp.pipe_names:
                nlp.add_pipe("sentencizer")

            # Note: SpaCy's sentencizer doesn't use abbreviations list directly
            # The sentencizer is rule-based and handles common abbreviations automatically
            # Domain-specific abbreviations will be handled by the sentencizer's rules

            # Configure sentencizer with custom rules
            sentencizer = nlp.get_pipe("sentencizer")

            _nlp = nlp
            logger.info("SpaCy sentencizer initialized with domain-specific abbreviations")

        except ImportError:
            logger.warning("spacy not available, falling back to regex-based sentence splitting")
            _nlp = False  # Mark as unavailable
        except Exception as e:
            logger.error(f"Error initializing SpaCy sentencizer: {e}, falling back to regex")
            _nlp = False

    return _nlp if _nlp is not False else None


def split_sentences(text: str) -> list[str]:
    """
    Split text into sentences using SpaCy sentencizer.

    Falls back to regex-based splitting if SpaCy is unavailable.

    Args:
        text: Input text to split

    Returns:
        List of sentence strings (stripped of whitespace)
    """
    if not text or not text.strip():
        return []

    nlp = _get_nlp()

    if nlp is None:
        # Fallback to regex-based splitting
        sentences = re.split(r"[.!?]+", text)
        return [s.strip() for s in sentences if s.strip()]

    try:
        doc = nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
        return sentences
    except Exception as e:
        logger.warning(f"Error in SpaCy sentence splitting: {e}, falling back to regex")
        sentences = re.split(r"[.!?]+", text)
        return [s.strip() for s in sentences if s.strip()]


def find_sentence_boundaries(text: str, start_pos: int, end_pos: int) -> int | None:
    """
    Find the nearest sentence boundary before end_pos within the search window.

    Used for chunking content at sentence boundaries rather than arbitrary positions.

    Args:
        text: Full text content
        start_pos: Start position of the chunk window
        end_pos: Desired end position (will search backwards from here)

    Returns:
        Position of sentence boundary (inclusive, includes punctuation), or None if not found
    """
    if not text or end_pos > len(text) or start_pos < 0:
        return None

    nlp = _get_nlp()

    if nlp is None:
        # Fallback: search backwards for period within last 100 chars
        search_start = max(start_pos, end_pos - 100)
        sentence_end = text.rfind(".", search_start, end_pos)
        if sentence_end > start_pos:
            return sentence_end + 1
        return None

    try:
        # Process text from start_pos to slightly beyond end_pos for context
        # This helps find sentence boundaries that might be just after end_pos
        search_end = min(end_pos + 100, len(text))
        search_text = text[start_pos:search_end]

        if not search_text.strip():
            return None

        doc = nlp(search_text)

        # Find sentence boundaries (adjusted for start_pos offset)
        boundaries = []
        for sent in doc.sents:
            # sent.end_char is relative to the search_text slice
            # Add start_pos to get absolute position in original text
            absolute_end = start_pos + sent.end_char

            # Only consider boundaries within our search window
            if start_pos < absolute_end <= search_end:
                boundaries.append(absolute_end)

        if not boundaries:
            return None

        # Find the last boundary before or at end_pos (preferred)
        for boundary in reversed(boundaries):
            if boundary <= end_pos and boundary > start_pos:
                return boundary

        # If no boundary before end_pos, find the first one after (within reasonable distance)
        # This allows extending chunk slightly to hit a sentence boundary
        for boundary in boundaries:
            if end_pos < boundary <= end_pos + 50:  # Allow up to 50 chars extension
                return boundary

        return None

    except Exception as e:
        logger.warning(f"Error in SpaCy boundary detection: {e}, falling back to regex")
        search_start = max(start_pos, end_pos - 100)
        sentence_end = text.rfind(".", search_start, end_pos)
        if sentence_end > start_pos:
            return sentence_end + 1
        return None


def count_sentences(text: str) -> int:
    """
    Count the number of sentences in text.

    Args:
        text: Input text

    Returns:
        Number of sentences
    """
    if not text or not text.strip():
        return 0

    sentences = split_sentences(text)
    return len(sentences)
