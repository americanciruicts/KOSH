import pytest
import tempfile
import os
from pathlib import Path

from src.doc_parser import DocumentParser
from src.models import FileMetadata

class TestDocumentParser:
    
    def setup_method(self):
        self.parser = DocumentParser()
    
    def test_parse_text_file(self):
        """Test parsing a simple text file."""
        content = "This is a test document with some text content."
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            text, metadata = self.parser.parse_file(temp_path)
            
            assert content in text
            assert isinstance(metadata, FileMetadata)
            assert metadata.file_name == os.path.basename(temp_path)
            assert metadata.mime_type == 'text/plain'
            assert metadata.file_size > 0
        finally:
            os.unlink(temp_path)
    
    def test_get_file_metadata(self):
        """Test metadata extraction."""
        content = "Test content for metadata"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            metadata = self.parser._get_file_metadata(temp_path)
            
            assert metadata.file_name == os.path.basename(temp_path)
            assert metadata.file_size == len(content.encode('utf-8'))
            assert metadata.mime_type == 'text/plain'
            assert len(metadata.file_hash) == 64  # SHA256 hash length
        finally:
            os.unlink(temp_path)
    
    def test_unsupported_file_type(self):
        """Test handling of unsupported file types."""
        with tempfile.NamedTemporaryFile(suffix='.xyz', delete=False) as f:
            f.write(b"binary content")
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError, match="Unsupported file type"):
                self.parser.parse_file(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_empty_file(self):
        """Test handling of empty files."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            temp_path = f.name
        
        try:
            text, metadata = self.parser.parse_file(temp_path)
            
            assert text == ""
            assert metadata.file_size == 0
        finally:
            os.unlink(temp_path)