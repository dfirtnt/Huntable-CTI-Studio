"""PDF Processing Service for Threat Intelligence Reports.

This module handles PDF file processing, text extraction, and threat intelligence
content analysis for uploaded threat reports.
"""

import logging
import os
import tempfile
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import hashlib

try:
    import PyPDF2
    import pdfplumber
except ImportError:
    PyPDF2 = None
    pdfplumber = None

logger = logging.getLogger(__name__)


@dataclass
class PDFProcessingResult:
    """Result of PDF processing with metadata."""
    success: bool
    text_content: str
    page_count: int
    file_size: int
    processing_time: float
    metadata: Dict[str, Any]
    error_message: Optional[str] = None


class PDFProcessor:
    """
    PDF processor for threat intelligence reports.
    
    Supports multiple extraction methods:
    1. pdfplumber - Better for complex layouts and tables
    2. PyPDF2 - Fallback for basic text extraction
    """
    
    def __init__(self):
        """Initialize the PDF processor."""
        if not PyPDF2 or not pdfplumber:
            logger.warning("PDF processing libraries not available. Install PyPDF2 and pdfplumber.")
    
    def extract_text_pdfplumber(self, file_path: str) -> Tuple[str, int]:
        """
        Extract text using pdfplumber (preferred method).
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Tuple of (extracted_text, page_count)
        """
        try:
            text_content = ""
            page_count = 0
            
            with pdfplumber.open(file_path) as pdf:
                page_count = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text_content += f"\n--- Page {page_num + 1} ---\n"
                            text_content += page_text
                    except Exception as e:
                        logger.warning(f"Error extracting text from page {page_num + 1}: {e}")
                        continue
            
            return text_content.strip(), page_count
            
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            raise
    
    def extract_text_pypdf2(self, file_path: str) -> Tuple[str, int]:
        """
        Extract text using PyPDF2 (fallback method).
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Tuple of (extracted_text, page_count)
        """
        try:
            text_content = ""
            
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                page_count = len(pdf_reader.pages)
                
                for page_num, page in enumerate(pdf_reader.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text_content += f"\n--- Page {page_num + 1} ---\n"
                            text_content += page_text
                    except Exception as e:
                        logger.warning(f"Error extracting text from page {page_num + 1}: {e}")
                        continue
            
            return text_content.strip(), page_count
            
        except Exception as e:
            logger.error(f"PyPDF2 extraction failed: {e}")
            raise
    
    def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        Extract metadata from PDF file.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary containing PDF metadata
        """
        metadata = {
            'file_name': os.path.basename(file_path),
            'file_size': os.path.getsize(file_path),
            'created_at': datetime.now().isoformat(),
            'file_hash': self._calculate_file_hash(file_path)
        }
        
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                # Extract PDF metadata
                if pdf_reader.metadata:
                    pdf_meta = pdf_reader.metadata
                    metadata.update({
                        'pdf_title': pdf_meta.get('/Title', ''),
                        'pdf_author': pdf_meta.get('/Author', ''),
                        'pdf_subject': pdf_meta.get('/Subject', ''),
                        'pdf_creator': pdf_meta.get('/Creator', ''),
                        'pdf_producer': pdf_meta.get('/Producer', ''),
                        'pdf_creation_date': str(pdf_meta.get('/CreationDate', '')),
                        'pdf_modification_date': str(pdf_meta.get('/ModDate', ''))
                    })
                
                metadata['page_count'] = len(pdf_reader.pages)
                
        except Exception as e:
            logger.warning(f"Error extracting PDF metadata: {e}")
            metadata['page_count'] = 0
        
        return metadata
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of the file."""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating file hash: {e}")
            return ""
    
    async def process_pdf(self, file_path: str, filename: str) -> PDFProcessingResult:
        """
        Process a PDF file and extract threat intelligence content.
        
        Args:
            file_path: Path to the uploaded PDF file
            filename: Original filename
            
        Returns:
            PDFProcessingResult with extracted content and metadata
        """
        import time
        start_time = time.time()
        
        try:
            if not PyPDF2 or not pdfplumber:
                return PDFProcessingResult(
                    success=False,
                    text_content="",
                    page_count=0,
                    file_size=0,
                    processing_time=time.time() - start_time,
                    metadata={},
                    error_message="PDF processing libraries not available"
                )
            
            # Extract metadata
            metadata = self.extract_metadata(file_path)
            metadata['original_filename'] = filename
            
            # Try pdfplumber first (better for complex layouts)
            text_content = ""
            page_count = 0
            
            try:
                text_content, page_count = self.extract_text_pdfplumber(file_path)
                metadata['extraction_method'] = 'pdfplumber'
                logger.info(f"Successfully extracted text using pdfplumber: {len(text_content)} characters from {page_count} pages")
            except Exception as e:
                logger.warning(f"pdfplumber failed, trying PyPDF2: {e}")
                try:
                    text_content, page_count = self.extract_text_pypdf2(file_path)
                    metadata['extraction_method'] = 'pypdf2'
                    logger.info(f"Successfully extracted text using PyPDF2: {len(text_content)} characters from {page_count} pages")
                except Exception as e2:
                    logger.error(f"Both PDF extraction methods failed: {e2}")
                    raise e2
            
            # Validate extracted content
            if not text_content or len(text_content.strip()) < 100:
                return PDFProcessingResult(
                    success=False,
                    text_content=text_content,
                    page_count=page_count,
                    file_size=metadata['file_size'],
                    processing_time=time.time() - start_time,
                    metadata=metadata,
                    error_message="Insufficient text content extracted from PDF"
                )
            
            processing_time = time.time() - start_time
            
            return PDFProcessingResult(
                success=True,
                text_content=text_content,
                page_count=page_count,
                file_size=metadata['file_size'],
                processing_time=processing_time,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"PDF processing failed: {e}")
            return PDFProcessingResult(
                success=False,
                text_content="",
                page_count=0,
                file_size=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                processing_time=time.time() - start_time,
                metadata={},
                error_message=str(e)
            )
    
    def is_valid_pdf(self, file_path: str) -> bool:
        """
        Check if the file is a valid PDF.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if valid PDF, False otherwise
        """
        try:
            with open(file_path, 'rb') as file:
                # Check PDF header
                header = file.read(4)
                if header != b'%PDF':
                    return False
                
                # Try to read with PyPDF2
                file.seek(0)
                pdf_reader = PyPDF2.PdfReader(file)
                # Just check if we can get page count
                len(pdf_reader.pages)
                return True
                
        except Exception:
            return False


# Global instance
pdf_processor = PDFProcessor()
