"""Contract tests for ContentFilter.chunk_content().

Locks down the chunker's invariants so we don't regress:
- No duplicate-end chunks (the "overlap-only tail" bug fixed 2026-05-21)
- Every emitted chunk extends past the previous chunk's end
- Overlap is preserved between consecutive chunks
- No infinite loops
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))


@pytest.fixture(scope="module")
def cf():
    from src.utils.content_filter import ContentFilter

    return ContentFilter()


class TestNoOverlapOnlyChunks:
    """The chunker must NOT emit chunks whose end equals the previous chunk's end.

    Such chunks are pure overlap with the previous chunk and contain no new
    content (the only reason this happened: the sentence-boundary search
    returned the same boundary that terminated the previous chunk). They
    pollute training data with duplicates and waste inference compute.
    """

    def test_no_duplicate_end_positions(self, cf) -> None:
        # Build content where the sentence boundary at position ~1000 will be
        # found again when the next chunk's window starts at 800 (1000 - overlap).
        # Repeat the pattern several times to ensure the bug would surface
        # at multiple section boundaries.
        section = "A" * 950 + ". " + "B" * 50 + "\n\n"
        content = section * 10

        chunks = cf.chunk_content(content, chunk_size=1000, overlap=200)
        ends = [end for _, end, _ in chunks]

        assert len(ends) == len(set(ends)), (
            "Chunker emitted multiple chunks ending at the same position. "
            f"Ends: {ends}. "
            "This means duplicate 'overlap-only' chunks slipped through."
        )

    def test_each_chunk_extends_past_previous_end(self, cf) -> None:
        content = ("Sentence ending here. " * 200) + ("Another sentence. " * 200)

        chunks = cf.chunk_content(content, chunk_size=1000, overlap=200)

        for i in range(1, len(chunks)):
            prev_end = chunks[i - 1][1]
            curr_end = chunks[i][1]
            assert curr_end > prev_end, (
                f"Chunk {i} (end={curr_end}) does not extend past "
                f"chunk {i - 1} (end={prev_end}) — duplicate-tail bug regression."
            )


class TestChunkSizeBounds:
    """Soft contract on chunk sizes for downstream model quality."""

    def test_no_chunks_smaller_than_overlap(self, cf) -> None:
        """A chunk smaller than `overlap` is pure overlap with no new content.
        After fixing the duplicate-end bug, this should be unreachable except
        for the very final chunk (which may be a natural short tail)."""
        content = "Sentence one. Sentence two. " * 500

        chunks = cf.chunk_content(content, chunk_size=1000, overlap=200)
        # All but possibly the final chunk should be > overlap
        for i, (start, end, _) in enumerate(chunks[:-1]):
            length = end - start
            assert length > 200, (
                f"Non-final chunk {i} has length {length} <= overlap (200). Likely the overlap-only-tail bug regressed."
            )

    def test_chunks_never_exceed_chunk_size(self, cf) -> None:
        content = "X" * 5000
        chunks = cf.chunk_content(content, chunk_size=1000, overlap=200)
        for i, (start, end, _) in enumerate(chunks):
            assert end - start <= 1000, f"Chunk {i} length {end - start} exceeds chunk_size 1000"


class TestProgressInvariants:
    """The chunker must always make forward progress."""

    def test_no_infinite_loop_on_pathological_input(self, cf) -> None:
        # Content full of sentence boundaries every few chars — pathological
        # for the sentence-boundary chunker.
        content = ". " * 5000

        # If this hangs, the test framework will kill it. Just assert it returns.
        chunks = cf.chunk_content(content, chunk_size=1000, overlap=200)
        assert len(chunks) > 0
        # And every start position must be strictly increasing
        starts = [start for start, _, _ in chunks]
        assert starts == sorted(starts)
        assert len(starts) == len(set(starts)), "Duplicate start positions"

    def test_empty_content_returns_empty(self, cf) -> None:
        assert cf.chunk_content("") == []

    def test_short_content_single_chunk(self, cf) -> None:
        content = "Short article content."
        chunks = cf.chunk_content(content, chunk_size=1000, overlap=200)
        assert len(chunks) == 1
        assert chunks[0][2].strip() == content.strip()


class TestOverlapPreservation:
    """Consecutive chunks should overlap (when content is long enough)."""

    def test_consecutive_chunks_overlap(self, cf) -> None:
        content = "X" * 5000
        chunks = cf.chunk_content(content, chunk_size=1000, overlap=200)
        # When content has no sentence boundaries, each non-final chunk
        # should end at start+1000 and the next should start at end-overlap.
        for i in range(1, len(chunks) - 1):
            prev_end = chunks[i - 1][1]
            curr_start = chunks[i][0]
            assert curr_start < prev_end, (
                f"Chunk {i} starts at {curr_start} but previous ended at {prev_end} — no overlap, content gap risk."
            )
