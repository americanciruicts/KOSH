import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import structlog

from src.config import settings
from src.models import ProcessingRequest, ProcessingResponse, ProcessingStatus
from src.doc_parser import DocumentParser
from src.ai_pipeline import AIProcessor

# Setup logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

app = FastAPI(
    title="Document Intelligence API",
    description="Universal document processing and AI analysis system",
    version="1.0.0"
)

# Initialize components
parser = DocumentParser()
ai_processor = AIProcessor()

# In-memory storage for demo (use database in production)
processing_jobs = {}

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/upload", response_model=ProcessingResponse)
async def upload_and_process(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    extract_pii: bool = True,
    model: str = "gpt-4o"
):
    """Upload and process a document."""
    
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    file_extension = Path(file.filename).suffix.lower().lstrip('.')
    if file_extension not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"File type {file_extension} not supported"
        )
    
    if file.size and file.size > settings.max_file_size:
        raise HTTPException(
            status_code=400, 
            detail=f"File too large. Max size: {settings.max_file_size} bytes"
        )
    
    # Generate request ID and save file
    request_id = str(uuid.uuid4())
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / f"{request_id}_{file.filename}"
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    # Create processing job
    job = ProcessingResponse(
        request_id=request_id,
        status=ProcessingStatus.PENDING,
        created_at=datetime.now()
    )
    processing_jobs[request_id] = job
    
    # Start background processing
    background_tasks.add_task(
        process_document_background, 
        request_id, 
        str(file_path), 
        extract_pii, 
        model
    )
    
    logger.info("Document uploaded for processing", 
                request_id=request_id, 
                filename=file.filename)
    
    return job

async def process_document_background(
    request_id: str, 
    file_path: str, 
    extract_pii: bool, 
    model: str
):
    """Background task to process document."""
    
    try:
        # Update status
        processing_jobs[request_id].status = ProcessingStatus.PROCESSING
        
        # Parse document
        logger.info("Starting document parsing", request_id=request_id)
        text, metadata = parser.parse_file(file_path)
        
        # AI analysis
        logger.info("Starting AI analysis", request_id=request_id, model=model)
        try:
            analysis = await ai_processor.analyze_document(text, metadata, model)
            logger.info("AI analysis completed successfully", request_id=request_id)
        except Exception as e:
            logger.error(f"AI analysis failed: {str(e)}", request_id=request_id)
            raise
        
        # PII detection if requested
        if extract_pii:
            pii_data = ai_processor.detect_pii(text)
            # Add PII to existing extracted fields instead of overwriting
            if analysis.extracted_fields:
                analysis.extracted_fields["detected_pii"] = pii_data
            else:
                analysis.extracted_fields = {"detected_pii": pii_data}
        
        # Save results
        output_dir = Path(settings.output_dir) / request_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save JSON output
        with open(output_dir / "analysis.json", "w") as f:
            json.dump(analysis.dict(), f, indent=2, default=str)
        
        # Update job with results
        processing_jobs[request_id].status = ProcessingStatus.COMPLETED
        processing_jobs[request_id].analysis = analysis
        
        logger.info("Document processing completed", 
                   request_id=request_id,
                   document_type=analysis.document_type,
                   confidence=analysis.confidence)
        
    except Exception as e:
        processing_jobs[request_id].status = ProcessingStatus.FAILED
        processing_jobs[request_id].error_message = str(e)
        
        logger.error("Document processing failed", 
                    request_id=request_id, 
                    error=str(e))
    
    finally:
        # Cleanup uploaded file
        try:
            os.unlink(file_path)
        except:
            pass

@app.get("/status/{request_id}", response_model=ProcessingResponse)
async def get_processing_status(request_id: str):
    """Get processing status for a request."""
    
    if request_id not in processing_jobs:
        raise HTTPException(status_code=404, detail="Request not found")
    
    return processing_jobs[request_id]

@app.get("/results/{request_id}")
async def get_results(request_id: str, format: str = "json"):
    """Get processing results in specified format."""
    
    if request_id not in processing_jobs:
        raise HTTPException(status_code=404, detail="Request not found")
    
    job = processing_jobs[request_id]
    
    if job.status != ProcessingStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Processing not completed")
    
    if format == "json":
        return job.analysis
    else:
        raise HTTPException(status_code=400, detail="Unsupported format")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now()}

@app.get("/")
async def root():
    """Serve the frontend interface."""
    return FileResponse('static/index.html')

@app.get("/test_upload.html")  
async def test_upload():
    """Serve the test upload page."""
    return FileResponse('test_upload.html')

@app.get("/api")
async def api_info():
    """API information endpoint."""
    return {
        "name": "Document Intelligence API",
        "version": "1.0.0",
        "endpoints": {
            "upload": "POST /upload - Upload and process document",
            "status": "GET /status/{request_id} - Check processing status", 
            "results": "GET /results/{request_id} - Get results",
            "health": "GET /health - Health check"
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower()
    )