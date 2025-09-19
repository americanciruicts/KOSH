#!/usr/bin/env python3
"""Test script to debug the dynamic extraction."""

import asyncio
import sys
sys.path.append('/Users/khashsarrafi/Projects/revestData')

from src.ai_pipeline import AIProcessor
from src.models import FileMetadata
from datetime import datetime

async def test_extraction():
    processor = AIProcessor()
    
    # Test with simple employee roster text
    text = """EMPLOYEE ROSTER - TECHNICAL DEPARTMENT

No. | Name                    | Service No | Job Title      | Signature
----|-------------------------|------------|----------------|----------
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
    
    print("Testing dynamic extraction...")
    
    # Test extraction
    try:
        result = await processor._extract_structured_data(text, "form", "gpt-4o")
        print(f"Extraction result: {result}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test full analysis
    try:
        analysis = await processor.analyze_document(text, metadata, "gpt-4o")
        print(f"Full analysis extracted_fields: {analysis.extracted_fields}")
    except Exception as e:
        print(f"Full analysis error: {e}")

if __name__ == "__main__":
    asyncio.run(test_extraction())