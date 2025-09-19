import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime

from src.ai_pipeline import AIProcessor
from src.models import FileMetadata, DocumentType

class TestAIProcessor:
    
    def setup_method(self):
        self.processor = AIProcessor()
        self.sample_metadata = FileMetadata(
            file_name="test.txt",
            file_size=1000,
            mime_type="text/plain",
            file_hash="abc123",
            upload_timestamp=datetime.now()
        )
    
    def test_detect_pii(self):
        """Test PII detection functionality."""
        text = """
        Contact John Doe at john.doe@email.com or call (555) 123-4567.
        His SSN is 123-45-6789 and credit card is 4532 1234 5678 9012.
        Address: 123 Main Street, Anytown, USA
        """
        
        pii_data = self.processor.detect_pii(text)
        
        assert "email" in pii_data
        assert "john.doe@email.com" in pii_data["email"]
        
        assert "phone" in pii_data
        assert any("555" in phone for phone in pii_data["phone"])
        
        assert "ssn" in pii_data
        assert "123-45-6789" in pii_data["ssn"]
        
        assert "credit_card" in pii_data
    
    def test_estimate_cost(self):
        """Test cost estimation for different models."""
        text = "This is a sample text " * 100  # ~400 characters = ~100 tokens
        
        gpt4_cost = self.processor._estimate_cost(text, "gpt-4o")
        gpt3_cost = self.processor._estimate_cost(text, "gpt-3.5-turbo")
        claude_cost = self.processor._estimate_cost(text, "claude-3-sonnet")
        
        assert gpt4_cost > gpt3_cost  # GPT-4 should be more expensive
        assert gpt4_cost > 0
        assert claude_cost > 0
    
    def test_document_schemas(self):
        """Test that document schemas are properly defined."""
        assert DocumentType.INVOICE in self.processor.document_schemas
        assert DocumentType.RESUME in self.processor.document_schemas
        assert DocumentType.CONTRACT in self.processor.document_schemas
        
        invoice_schema = self.processor.document_schemas[DocumentType.INVOICE]
        assert "vendor_name" in invoice_schema
        assert "total_amount" in invoice_schema
        assert "invoice_date" in invoice_schema
        
        resume_schema = self.processor.document_schemas[DocumentType.RESUME]
        assert "full_name" in resume_schema
        assert "email" in resume_schema
        assert "experience" in resume_schema
    
    def test_pii_detection_no_pii(self):
        """Test PII detection with text containing no PII."""
        text = "This is a simple document about technology and innovation."
        
        pii_data = self.processor.detect_pii(text)
        
        assert len(pii_data) == 0 or all(len(matches) == 0 for matches in pii_data.values())
    
    @pytest.mark.asyncio
    async def test_analyze_document_mock(self):
        """Test document analysis with mocked AI calls."""
        
        # Mock the AI processor methods
        self.processor._classify_and_summarize = AsyncMock(return_value={
            "summary": "This is a test invoice document.",
            "document_type": "invoice",
            "confidence": 0.95
        })
        
        self.processor._extract_structured_data = AsyncMock(return_value={
            "vendor_name": "Test Vendor",
            "total_amount": 1000.00,
            "invoice_number": "INV-001"
        })
        
        text = "Sample invoice text content"
        
        analysis = await self.processor.analyze_document(text, self.sample_metadata)
        
        assert analysis.document_type == DocumentType.INVOICE
        assert analysis.confidence == 0.95
        assert analysis.summary == "This is a test invoice document."
        assert "vendor_name" in analysis.extracted_fields
        assert analysis.extracted_fields["vendor_name"] == "Test Vendor"
        assert analysis.processing_time > 0