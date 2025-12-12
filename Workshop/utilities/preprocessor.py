"""
Text normalization and hard chunking utilities for span extraction.
"""

import re
from typing import List, Dict, Any


def strip_non_utf8(text: str) -> str:
    """Remove non-UTF8 artifacts."""
    return text.encode("utf-8", "ignore").decode("utf-8", "ignore")


def normalize_whitespace(text: str) -> str:
    """Collapse excessive whitespace while preserving single spaces."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def preprocess_text(text: str) -> str:
    """Apply UTF-8 cleanup and whitespace normalization."""
    return normalize_whitespace(strip_non_utf8(text))


def hard_chunk_text(
    text: str,
    tokenizer,
    max_length: int = 512,
) -> List[Dict[str, Any]]:
    """
    Deterministic, non-overlapping chunking by token count.

    - No stride or overlap.
    - Preserves absolute character offsets.
    - Uses tokenizer offsets to find chunk boundaries.
    """
    if not text:
        return []

    # Use raw tokens (no special tokens) to decide boundaries
    encoding = tokenizer(
        text,
        add_special_tokens=False,
        return_offsets_mapping=True,
        truncation=False,
    )
    offsets = encoding["offset_mapping"]
    if not offsets:
        return []

    # Leave room for model special tokens
    capacity = max_length - tokenizer.num_special_tokens_to_add(pair=False)
    capacity = max(capacity, 1)

    chunks: List[Dict[str, Any]] = []
    start_idx = 0
    while start_idx < len(offsets):
        end_idx = min(start_idx + capacity, len(offsets))
        chunk_offsets = offsets[start_idx:end_idx]
        chunk_start = chunk_offsets[0][0]
        chunk_end = chunk_offsets[-1][1]
        chunk_text = text[chunk_start:chunk_end]

        chunks.append(
            {
                "text": chunk_text,
                "start": chunk_start,
                "end": chunk_end,
                "token_range": (start_idx, end_idx),
                "token_count": end_idx - start_idx,
            }
        )
        start_idx = end_idx

    return chunks
