"""Tests for scripts/backfill_image_ocr.py — pure helpers + factored transform.

Step 1 tests (spec-mandated):
    test_detect_basis_async_raw_sha256
    test_detect_basis_sync_title_content
    test_detect_basis_unknown_returns_none
    test_basis_stable_across_retry
    test_recompute_hash_matches_basis
    test_append_dedupes_against_existing_markers

Step 4 tests (factored-function integration, no real DB needed):
    test_compute_article_update_no_blocks_basis_async
    test_compute_article_update_basis_unknown_skips
    test_compute_article_update_collision_skips
    test_compute_article_update_idempotent_no_double_append
    test_compute_article_update_upsert_flag_true
    test_compute_article_update_no_simhash_buckets_write
    test_compute_article_update_metadata_keys
    test_existing_basis_in_metadata_cached
"""

import hashlib

import pytest

from scripts.backfill_image_ocr import (
    ArticleUpdateIntent,
    append_ocr_plaintext,
    compute_article_update,
    detect_hash_basis,
    recompute_hash,
)
from src.services.vision_ocr_service import OcrStatus
from src.utils.content import ContentCleaner

# ---------------------------------------------------------------------------
# Step 1 — pure helper tests (spec-mandated, TDD-first)
# ---------------------------------------------------------------------------


def test_detect_basis_async_raw_sha256():
    content, title = "body text", "Title"
    stored = hashlib.sha256(content.encode()).hexdigest()
    assert detect_hash_basis(stored, title, content) == "async_raw"


def test_detect_basis_sync_title_content():
    content, title = "body text", "Title"
    stored = ContentCleaner.calculate_content_hash(title, content)
    assert detect_hash_basis(stored, title, content) == "sync"


def test_detect_basis_unknown_returns_none():
    assert detect_hash_basis("deadbeef" * 8, "T", "c") is None


def test_basis_stable_across_retry():
    """Detection is by stored-hash comparison, NOT content_hashes-row existence.
    Simulate a retry by calling detect_hash_basis a second time after what would
    be the upsert (content_hashes row now exists for an async article).  The
    function must still return 'async_raw', not flip to 'sync' or None.
    """
    content, title = "body text", "Title"
    stored = hashlib.sha256(content.encode()).hexdigest()
    # First call (pre-upsert)
    assert detect_hash_basis(stored, title, content) == "async_raw"
    # Second call (post-upsert — function has no visibility of the DB row, which
    # is the whole point: it must not rely on row-existence)
    assert detect_hash_basis(stored, title, content) == "async_raw"


def test_recompute_hash_matches_basis():
    content, title = "new body", "T"
    assert recompute_hash("async_raw", title, content) == hashlib.sha256(content.encode()).hexdigest()
    assert recompute_hash("sync", title, content) == ContentCleaner.calculate_content_hash(title, content)


def test_append_dedupes_against_existing_markers():
    base = "text\n[Image OCR: https://s.test/a.png]\nold"
    out = append_ocr_plaintext(
        base,
        [
            ("[Image OCR: https://s.test/a.png]", "dup"),
            ("[Image OCR: https://s.test/b.png]", "new"),
        ],
    )
    assert out.count("[Image OCR: https://s.test/a.png]") == 1
    assert "[Image OCR: https://s.test/b.png]" in out


# ---------------------------------------------------------------------------
# Step 4 — factored-function (compute_article_update) tests
# ---------------------------------------------------------------------------
# These tests exercise the pure per-row transform without a real DB or network.
# The spec says "at minimum test the per-article transform function in isolation".
# ---------------------------------------------------------------------------

def _make_async_row(content="article body text", title="A Title"):
    """Return (stored_hash, content, title) where hash is on the async_raw basis."""
    stored_hash = hashlib.sha256(content.encode()).hexdigest()
    return stored_hash, content, title


def _make_sync_row(content="article body text", title="A Title"):
    stored_hash = ContentCleaner.calculate_content_hash(title, content)
    return stored_hash, content, title


def test_compute_article_update_no_blocks_basis_async():
    """No OCR blocks → content unchanged but hash recomputed on async_raw basis,
    upsert_content_hash is True, simhash computed."""
    stored_hash, content, title = _make_async_row()
    intent = compute_article_update(
        article_id=1,
        title=title,
        content=content,
        stored_content_hash=stored_hash,
        article_metadata={},
        ocr_blocks=[],
        ocr_status=OcrStatus.skipped_no_images,
        original_img_urls=[],
        processed_img_urls=[],
        error_counts={},
        existing_hash_basis=None,
        collision_content_hash=None,
    )
    assert not intent.skipped
    assert intent.basis == "async_raw"
    # With no blocks the content is unchanged, so the hash should stay the same
    assert intent.new_content_hash == stored_hash
    assert intent.upsert_content_hash is True
    assert intent.new_simhash_bucket >= 0  # computed (not 0 from skip path)
    assert "ocr_status" in intent.new_metadata
    assert intent.new_metadata["ocr_content_hash_basis"] == "async_raw"


def test_compute_article_update_basis_unknown_skips():
    """Unknown basis (neither raw sha256 nor sync hash) → skip + report."""
    stored_hash = "0" * 64  # garbage — matches neither basis
    intent = compute_article_update(
        article_id=99,
        title="T",
        content="some content",
        stored_content_hash=stored_hash,
        article_metadata={},
        ocr_blocks=[("[Image OCR: https://x.com/i.png]", "text")],
        ocr_status=OcrStatus.completed,
        original_img_urls=["https://x.com/i.png"],
        processed_img_urls=["https://x.com/i.png"],
        error_counts={},
        existing_hash_basis=None,
        collision_content_hash=None,
    )
    assert intent.skipped
    assert "99" in intent.skip_reason  # article_id mentioned


def test_compute_article_update_collision_skips():
    """Collision detected → skip + report, original content/hash unchanged."""
    stored_hash, content, title = _make_async_row()
    intent = compute_article_update(
        article_id=5,
        title=title,
        content=content,
        stored_content_hash=stored_hash,
        article_metadata={},
        ocr_blocks=[("[Image OCR: https://x.com/i.png]", "some text")],
        ocr_status=OcrStatus.completed,
        original_img_urls=["https://x.com/i.png"],
        processed_img_urls=["https://x.com/i.png"],
        error_counts={},
        existing_hash_basis=None,
        collision_content_hash="aabbccdd" * 8,  # signals collision detected by caller
    )
    assert intent.skipped
    assert "collides" in intent.skip_reason.lower()
    # Original content and hash preserved
    assert intent.new_content == content
    assert intent.new_content_hash == stored_hash


def test_compute_article_update_idempotent_no_double_append():
    """Re-running append_ocr_plaintext with a URL already in content must not
    double-append the block.  compute_article_update delegates to append_ocr_plaintext
    which dedupes — verify end-to-end."""
    url = "https://cdn.example.com/img.png"
    marker = f"[Image OCR: {url}]"
    ocr_text = "some extracted text"
    # Simulate content already containing this block (from a prior run)
    existing_content = f"article body\n\n{marker}\n{ocr_text}"
    stored_hash = hashlib.sha256(existing_content.encode()).hexdigest()

    intent = compute_article_update(
        article_id=7,
        title="T",
        content=existing_content,
        stored_content_hash=stored_hash,
        article_metadata={"ocr_processed_img_urls": [url]},
        ocr_blocks=[(marker, ocr_text)],  # same block again
        ocr_status=OcrStatus.completed,
        original_img_urls=[url],
        processed_img_urls=[url],
        error_counts={},
        existing_hash_basis="async_raw",
        collision_content_hash=None,
    )
    assert not intent.skipped
    # Marker must appear exactly once
    assert intent.new_content.count(marker) == 1


def test_compute_article_update_upsert_flag_true():
    """upsert_content_hash must be True whenever the update is not skipped,
    so that both async (no CH row) and sync (existing CH row) articles are handled."""
    stored_hash, content, title = _make_sync_row()
    intent = compute_article_update(
        article_id=3,
        title=title,
        content=content,
        stored_content_hash=stored_hash,
        article_metadata={},
        ocr_blocks=[("[Image OCR: https://x.com/a.jpg]", "words words")],
        ocr_status=OcrStatus.completed,
        original_img_urls=["https://x.com/a.jpg"],
        processed_img_urls=["https://x.com/a.jpg"],
        error_counts={},
        existing_hash_basis=None,
        collision_content_hash=None,
    )
    assert not intent.skipped
    assert intent.upsert_content_hash is True
    assert intent.basis == "sync"


def test_compute_article_update_no_simhash_buckets_write():
    """The update intent must NOT carry a simhash_buckets write intent.
    (simhash_buckets table is never written by any ingest path; backfill mirrors that.)
    compute_article_update produces simhash/simhash_bucket COLUMNS (on ArticleTable)
    but has no field for a simhash_buckets TABLE row — verify the dataclass has no
    such field."""
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(ArticleUpdateIntent)}
    # These should be present (column updates)
    assert "new_simhash" in field_names
    assert "new_simhash_bucket" in field_names
    # This must NOT be present (table insert, never written)
    assert "simhash_buckets" not in field_names
    assert "insert_simhash_bucket" not in field_names
    assert "upsert_simhash_bucket" not in field_names


def test_compute_article_update_metadata_keys():
    """Result metadata must include all required OCR tracking keys plus basis."""
    stored_hash, content, title = _make_async_row()
    intent = compute_article_update(
        article_id=42,
        title=title,
        content=content,
        stored_content_hash=stored_hash,
        article_metadata={"some_existing_key": "value"},
        ocr_blocks=[("[Image OCR: https://i.example.com/p.png]", "text here")],
        ocr_status=OcrStatus.completed,
        original_img_urls=["https://i.example.com/p.png"],
        processed_img_urls=["https://i.example.com/p.png"],
        error_counts={"decode_failed": 0, "tesseract_error": 0, "timeout": 0, "fetch_failed": 0},
        existing_hash_basis=None,
        collision_content_hash=None,
    )
    required_keys = {
        "ocr_status", "ocr_image_count", "ocr_ran_at",
        "original_img_urls", "ocr_processed_img_urls", "ocr_error_counts",
        "ocr_content_hash_basis", "word_count", "content_length",
    }
    assert required_keys.issubset(intent.new_metadata.keys())
    # Existing metadata merged in, not dropped
    assert intent.new_metadata.get("some_existing_key") == "value"
    assert intent.new_metadata["ocr_content_hash_basis"] == "async_raw"


def test_existing_basis_in_metadata_cached():
    """If metadata already has 'ocr_content_hash_basis' from a prior run,
    detect_hash_basis must NOT be re-called (content may have changed after
    the first backfill).  compute_article_update uses the cached value."""
    # Use a stored_hash that does NOT match the content on either basis —
    # simulating content that changed after the first backfill wrote basis.
    stored_hash = "aaaa" * 16  # neither basis matches
    content, title = "modified content after first backfill", "Title"
    # But metadata carries the basis from the first run
    intent = compute_article_update(
        article_id=8,
        title=title,
        content=content,
        stored_content_hash=stored_hash,
        article_metadata={"ocr_content_hash_basis": "async_raw"},
        ocr_blocks=[("[Image OCR: https://img.test/x.png]", "ocr")],
        ocr_status=OcrStatus.completed,
        original_img_urls=["https://img.test/x.png"],
        processed_img_urls=["https://img.test/x.png"],
        error_counts={},
        existing_hash_basis="async_raw",  # caller passes cached value
        collision_content_hash=None,
    )
    # Must NOT skip (cached basis avoids the None detection)
    assert not intent.skipped
    assert intent.basis == "async_raw"


# ---------------------------------------------------------------------------
# P1 regression — --allow-refetch must keep the HTTP client open through OCR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refetch_keeps_client_open_for_image_fetch(monkeypatch):
    """Regression: _ocr_refetch previously closed the client (async-with exit) before
    ocr_article_images ran, so every refetched image fetch hit a closed client. The
    OCR call must run while the client is still open."""
    import io as _io

    from PIL import Image

    from scripts import backfill_image_ocr as B
    from src.services.vision_ocr_service import OcrConfig, OcrResult

    buf = _io.BytesIO()
    Image.new("RGB", (320, 240), "white").save(buf, format="PNG")
    png = buf.getvalue()

    class _FakeResp:
        text = (
            "<html><body><article><p>" + "w " * 30
            + "<img src='https://s.test/a.png'></p></article></body></html>"
        )

    class _FakeClient:
        def __init__(self):
            self.closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            self.closed = True

        async def get(self, url, **kw):
            return _FakeResp()

    fake = _FakeClient()
    monkeypatch.setattr(B, "_build_safe_client", lambda config: fake)

    async def _stream_check(client, url, config):
        assert not client.closed, "client closed before image fetch (P1 regression)"
        return png

    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", _stream_check)
    monkeypatch.setattr("src.services.vision_ocr_service.ocr_image_bytes",
                        lambda *a, **k: OcrResult(text="REFETCHED", error="ok"))

    blocks, *_ = await B._ocr_refetch("https://s.test/p", OcrConfig(), set(), None)
    assert blocks and blocks[0][1] == "REFETCHED"
