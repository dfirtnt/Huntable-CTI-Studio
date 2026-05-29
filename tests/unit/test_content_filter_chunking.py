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
    """Consecutive chunks should overlap by exactly `overlap` chars."""

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

    def test_hard_cut_fallback_produces_exactly_200_char_overlap(self, cf) -> None:
        """Hard-cut fallback preserves *exactly* the requested overlap.

        When find_sentence_boundaries returns a stuck boundary (≤ prev chunk end)
        and the guard falls back to start+chunk_size, the invariant is:

            next_start = prev_end - overlap
            new_end    = next_start + chunk_size   (hard cut)
            overlap    = prev_end - next_start = exactly `overlap`

        Asserting strict equality (not just > 0) catches partial regressions
        where the guard fires but lands the start at the wrong position.
        """
        # One clean sentence boundary at ~952, then dense content that forces
        # the hard-cut fallback on every subsequent chunk.
        section = "A" * 950 + ". "  # period at char ~952
        dense = "uuid-uuid-uuid-xxxx-uuid " * 60  # ~1500 chars, no terminators
        content = section + dense  # ~2452 chars total

        chunks = cf.chunk_content(content, chunk_size=1000, overlap=200)
        assert len(chunks) >= 2, "Need at least 2 chunks to verify overlap"

        for i in range(1, len(chunks)):
            prev_end = chunks[i - 1][1]
            curr_start = chunks[i][0]
            overlap_actual = prev_end - curr_start
            assert overlap_actual == 200, (
                f"Expected exactly 200-char overlap between chunk[{i - 1}] and chunk[{i}], "
                f"got {overlap_actual}. prev_end={prev_end}, curr_start={curr_start}. "
                "Hard-cut fallback may be landing start at the wrong position."
            )

    def test_overlap_maintained_across_multiple_consecutive_dense_sections(self, cf) -> None:
        """Overlap survives multiple alternating normal/dense sections.

        The 2026-05-26 bug could cascade: a stuck boundary in one dense region
        could corrupt the start-position state used by the next dense region.
        Three interleaved dense UUID blocks exercise this cascade.
        """
        normal = "Threat actor exploited CVE-2024-9999 via PowerShell. " * 18  # ~936 chars
        dense = "aaaa1111-bbbb-2222-cccc-3333dddd4444 SuspiciousProc " * 25  # ~1325 chars

        content = normal + dense + normal + dense + normal + dense + normal

        chunks = cf.chunk_content(content, chunk_size=1000, overlap=200)
        assert len(chunks) >= 4, "Need multiple chunks to verify cascade behaviour"

        bad_pairs = []
        for i in range(1, len(chunks)):
            prev_end = chunks[i - 1][1]
            curr_start = chunks[i][0]
            if prev_end <= curr_start:  # gap (zero or negative overlap)
                bad_pairs.append((i - 1, i, prev_end, curr_start))

        assert not bad_pairs, (
            "Content gaps found across multiple dense sections — "
            "zero-overlap bug may have cascaded between dense regions:\n"
            + "\n".join(f"  chunk[{a}] end={pe}  chunk[{b}] start={cs}  gap={cs - pe}" for a, b, pe, cs in bad_pairs)
        )

    def test_overlap_preserved_across_sentence_boundary_that_equals_prev_end(self, cf) -> None:
        """Regression test for the zero-overlap bug.

        When find_sentence_boundaries returns the same position that ended the
        previous chunk (common in dense content like UUID lists), the old code
        reset `start` to `chunks[-1][1]`, silently dropping the 200-char overlap.

        This produced pairs like:
            chunk[47]: 32369–33195  (overlap with 46 = 200 ✓)
            chunk[48]: 33195–34195  (overlap with 47 = 0  ✗)

        The fix: fall back to a hard character cut instead of resetting start.
        """
        # Simulate a dense UUID:Name list — no sentence terminators, so
        # find_sentence_boundaries repeatedly returns the previous chunk's end.
        uuid_entry = "abcdef12-3456-7890-abcd-ef1234567890 : Suspicious PowerShell Parameter Substring "
        dense = uuid_entry * 40  # ~3600 chars, no '.' or '\n' sentence breaks
        content = ("Normal sentence content here. " * 30) + dense + ("Normal sentence content here. " * 30)

        chunks = cf.chunk_content(content, chunk_size=1000, overlap=200)

        bad_pairs = []
        for i in range(1, len(chunks)):
            prev_end = chunks[i - 1][1]
            curr_start = chunks[i][0]
            overlap_actual = prev_end - curr_start
            if overlap_actual <= 0:
                bad_pairs.append((i - 1, i, prev_end, curr_start, overlap_actual))

        assert not bad_pairs, (
            "Zero-overlap (gap) pairs detected — sentence-boundary-stuck bug regressed:\n"
            + "\n".join(f"  chunk[{a}] end={pe}  chunk[{b}] start={cs}  overlap={ov}" for a, b, pe, cs, ov in bad_pairs)
        )
