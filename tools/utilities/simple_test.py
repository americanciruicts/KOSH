#!/usr/bin/env python3
"""Simple test to check if GPT-4o can extract data from the employee roster."""

import openai
import json
import asyncio
import os

async def test_gpt4o_extraction():
    # Use the same API key from the container
    client = openai.AsyncOpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
    
    # Sample employee roster text (similar to OCR output)
    text = """
    No. Name Service No Job Title Signature
    01 W.D. Ranjan Puyguolla 008249 Tech. Mgr/OR&M [signed]
    02 H.C. Jayaweera 008301 T.M./OR&M [signed]
    03 H.P.D. Lakmadasa 008293 T.M./SYSOP [signed]
    """
    
    system_prompt = """You are a data extraction expert. Extract ALL structured information from this employee roster.

Return a JSON object with:
- employees: array of employee objects with name, service_no, job_title
- document_type: type of document
- total_count: number of employees

Example:
{
    "employees": [
        {"name": "John Smith", "service_no": "12345", "job_title": "Engineer"}
    ],
    "document_type": "Employee Roster",
    "total_count": 1
}"""
    
    user_prompt = f"Extract structured data from this employee roster:\n\n{text}"
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=2000
        )
        
        result = response.choices[0].message.content
        print("GPT-4o Response:")
        print(result)
        
        # Try to parse as JSON
        try:
            parsed = json.loads(result)
            print("\nParsed JSON:")
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError as e:
            print(f"\nJSON Parse Error: {e}")
            print("Raw response was not valid JSON")
            
    except Exception as e:
        print(f"API Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_gpt4o_extraction())