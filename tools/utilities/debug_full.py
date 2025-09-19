#!/usr/bin/env python3
import asyncio
import sys
import os
sys.path.append('/app')

from src.ai_pipeline import AIProcessor

async def test_full():
    processor = AIProcessor()
    
    text = """EMPLOYEE ROSTER - TECHNICAL DEPARTMENT

No. | Name                    | Service No | Job Title      | Signature
01  | W.D. Ranjan Puyguolla  | 008249     | Tech. Mgr/OR&M | [signed]
02  | H.C. Jayaweera         | 008301     | T.M./OR&M      | [signed]
03  | H.P.D. Lakmadasa       | 008293     | T.M./SYSOP     | [signed]"""
    
    system_prompt = """You are a data extraction expert. Extract ALL structured information from the document.

For employee rosters: Extract employee names, IDs, titles, departments
For invoices: Extract vendor info, amounts, dates, line items
For contracts: Extract parties, dates, terms, clauses
For any document: Extract whatever structured data exists

You MUST respond with ONLY a valid JSON object. No explanations, no markdown, no ```json blocks.

Required format:
{
    "document_type": "Employee Roster|Invoice|Contract|Form|Report",
    "entries": [
        {"name": "John Smith", "id": "123", "title": "Manager"}
    ],
    "totals": {
        "count": 1
    },
    "metadata": {
        "department": "extracted if available"
    }
}"""
    
    user_prompt = f"Extract all structured data from this document:\n\n{text}"
    
    print("Testing full extraction pipeline...")
    try:
        # Test the OpenAI call
        response = await processor._call_openai(system_prompt, user_prompt, "gpt-4o")
        print(f"Raw OpenAI response: {response}")
        
        # Test the JSON parsing
        def extract_json_from_response(response_text):
            """Extract JSON from various response formats."""
            clean_text = response_text.strip()
            
            # Remove markdown code blocks
            if clean_text.startswith('```json'):
                clean_text = clean_text[7:]
            elif clean_text.startswith('```'):
                clean_text = clean_text[3:]
            
            if clean_text.endswith('```'):
                clean_text = clean_text[:-3]
            
            clean_text = clean_text.strip()
            
            import json
            try:
                return json.loads(clean_text)
            except json.JSONDecodeError:
                # Try to find JSON object in the text
                import re
                json_match = re.search(r'\{.*\}', clean_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                raise
        
        parsed = extract_json_from_response(response)
        print(f"Parsed JSON: {parsed}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_full())