from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from enum import Enum

class DocumentType(str, Enum):
    INVOICE = "invoice"
    RESUME = "resume"
    CONTRACT = "contract"
    PURCHASE_ORDER = "purchase_order"
    EMAIL = "email"
    REPORT = "report"
    FORM = "form"
    UNKNOWN = "unknown"

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class FileMetadata(BaseModel):
    file_name: str
    file_size: int
    mime_type: str
    file_hash: str
    upload_timestamp: datetime
    pages: Optional[int] = None
    language: Optional[str] = None

class DocumentAnalysis(BaseModel):
    summary: str
    document_type: DocumentType
    confidence: float
    extracted_fields: Dict[str, Any]
    raw_text: str
    metadata: FileMetadata
    processing_time: float
    model_used: str
    cost_estimate: Optional[float] = None

class ProcessingRequest(BaseModel):
    file_path: str
    extract_pii: bool = True
    custom_schema: Optional[Dict[str, Any]] = None
    output_format: str = "json"

class ProcessingResponse(BaseModel):
    request_id: str
    status: ProcessingStatus
    analysis: Optional[DocumentAnalysis] = None
    error_message: Optional[str] = None
    created_at: datetime