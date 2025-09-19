#!/usr/bin/env python3
import asyncio
import sys
import os
sys.path.append('/app')

# Test the analysis directly
from src.ai_pipeline import AIProcessor
from src.models import FileMetadata
from datetime import datetime

async def test_analysis():
    processor = AIProcessor()
    
    # Simple test data
    text = """EMPLOYEE ROSTER - TECHNICAL DEPARTMENT

No. | Name                    | Service No | Job Title      | Signature
01  | W.D. Ranjan Puyguolla  | 008249     | Tech. Mgr/OR&M | [signed]
02  | H.C. Jayaweera         | 008301     | T.M./OR&M      | [signed]
03  | H.P.D. Lakmadasa       | 008293     | T.M./SYSOP     | [signed]"""
    
    metadata = FileMetadata(
        file_name="test.txt",
        file_size=len(text),
        mime_type="text/plain",
        file_hash="test123",
        upload_timestamp=datetime.now()
    )
    
    try:
        print("Testing analysis...")
        result = await processor.analyze_document(text, metadata, "gpt-4o")
        print(f"SUCCESS!")
        print(f"Document Type: {result.document_type}")
        print(f"Confidence: {result.confidence}")
        print(f"Extracted Fields: {result.extracted_fields}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_analysis())