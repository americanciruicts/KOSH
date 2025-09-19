#!/usr/bin/env python3
import asyncio
import sys
import os
sys.path.append('/app')

from src.ai_pipeline import AIProcessor

async def test_openai():
    processor = AIProcessor()
    
    print("Testing OpenAI call...")
    try:
        response = await processor._call_openai(
            "You are a helpful assistant", 
            "Extract names from this text: John Smith, Jane Doe", 
            "gpt-4o"
        )
        print(f"OpenAI Response: {response}")
    except Exception as e:
        print(f"OpenAI Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_openai())