#!/usr/bin/env python3
import asyncio
import sys
import os
sys.path.append('/app')

from src.ai_pipeline import AIProcessor

async def test_extraction():
    processor = AIProcessor()
    
    text = """EMPLOYEE ROSTER - TECHNICAL DEPARTMENT

No. | Name                    | Service No | Job Title      | Signature
01  | W.D. Ranjan Puyguolla  | 008249     | Tech. Mgr/OR&M | [signed]
02  | H.C. Jayaweera         | 008301     | T.M./OR&M      | [signed]
03  | H.P.D. Lakmadasa       | 008293     | T.M./SYSOP     | [signed]"""
    
    print("Testing extraction...")
    try:
        result = await processor._extract_structured_data(text, "form", "gpt-4o")
        print(f"SUCCESS: {result}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_extraction())