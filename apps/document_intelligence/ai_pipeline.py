import json
import time
import logging
import re
from typing import Dict, Any, Optional, Tuple
import openai
import anthropic
from pydantic import BaseModel

from .models import DocumentType, DocumentAnalysis, FileMetadata
from .config import settings

logger = logging.getLogger(__name__)

class AIProcessor:
    """AI pipeline for document analysis using OpenAI and Anthropic models."""
    
    def __init__(self):
        self.openai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
        
        # No more hardcoded schemas - dynamic extraction for all document types!
    
    async def analyze_document(self, text: str, metadata: FileMetadata, model: str = "gpt-4o") -> DocumentAnalysis:
        """Analyze document text using AI and extract structured data."""
        start_time = time.time()
        
        try:
            # Step 1: Document classification and summarization
            logger.info("Step 1: Starting classification and summarization")
            classification_result = await self._classify_and_summarize(text, model)
            logger.info(f"Classification result: {classification_result}")
            
            # Step 2: Extract structured fields based on document type
            logger.info("Step 2: Starting structured data extraction")
            try:
                extracted_fields = await self._extract_structured_data(
                    text, 
                    classification_result["document_type"], 
                    model
                )
                logger.info(f"Extracted fields keys: {list(extracted_fields.keys()) if extracted_fields else 'Empty'}")
            except Exception as e:
                logger.error(f"Extraction failed: {str(e)}")
                extracted_fields = {"extraction_error": str(e)}
            
            processing_time = time.time() - start_time
            
            return DocumentAnalysis(
                summary=classification_result["summary"],
                document_type=DocumentType(classification_result["document_type"]),
                confidence=classification_result["confidence"],
                extracted_fields=extracted_fields,
                raw_text=text,
                metadata=metadata,
                processing_time=processing_time,
                model_used=model,
                cost_estimate=self._estimate_cost(text, model)
            )
            
        except Exception as e:
            logger.error(f"AI analysis failed: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
    
    async def _classify_and_summarize(self, text: str, model: str) -> Dict[str, Any]:
        """Classify document type and generate summary."""
        
        system_prompt = """You are a document analysis expert. Analyze the provided document text and return a JSON response with:
1. A concise 200-300 word summary
2. Document classification (invoice, resume, contract, purchase_order, email, report, form, or unknown)
3. Confidence score (0.0-1.0)

Classification guidelines:
- "form" for employee rosters, attendance sheets, sign-in sheets, registration forms, applications, or any structured data collection document
- "invoice" for billing documents with amounts and line items
- "resume" for career/employment documents
- "contract" for legal agreements
- "purchase_order" for procurement documents
- "report" for analytical or informational documents
- "email" for electronic correspondence
- "unknown" only if the document type cannot be determined

Respond ONLY with valid JSON in this format:
{
    "summary": "Document summary here...",
    "document_type": "form",
    "confidence": 0.95
}"""

        user_prompt = f"""Analyze this document:

{text[:8000]}...

Provide classification and summary in JSON format."""

        if model.startswith("gpt") and self.openai_client:
            response = await self._call_openai(system_prompt, user_prompt, model)
        elif model.startswith("claude") and self.anthropic_client:
            response = await self._call_anthropic(system_prompt, user_prompt, model)
        else:
            raise ValueError(f"Model {model} not available or API key not configured")
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return {
                "summary": response[:300] + "...",
                "document_type": "unknown",
                "confidence": 0.5
            }
    
    async def _extract_structured_data(self, text: str, doc_type: str, model: str) -> Dict[str, Any]:
        """Dynamically extract structured fields from any document."""
        
        logger.info(f"Starting dynamic extraction for document type: {doc_type}")
        
        system_prompt = """You are a data extraction expert. Extract ALL structured information from the document.

IMPORTANT: This text may come from OCR (image scanning) so it might have OCR errors. Be intelligent about interpreting garbled text:
- "W.D. Ranjan Puyguolla" might appear as "WD Ranjan Puyguolla" or "W.D.Ranjan" 
- Service numbers like "008249" might appear as "008249" or "OOB249"
- Job titles like "Tech. Mgr/OR&M" might appear as "Tech Mgr OR&M"

For employee rosters: Extract employee names, service numbers, job titles, departments
For invoices: Extract vendor info, amounts, dates, line items  
For contracts: Extract parties, dates, terms, clauses
For forms/tables: Extract all structured data in rows/columns

You MUST respond with ONLY a valid JSON object. No explanations, no markdown, no ```json blocks.

Required format:
{
    "document_type": "Employee Roster|Invoice|Contract|Form|Report",
    "entries": [
        {"name": "John Smith", "service_no": "123", "job_title": "Manager"}
    ],
    "totals": {
        "count": 1
    },
    "metadata": {
        "department": "extracted if available"
    }
}"""

        user_prompt = f"""Extract all structured data from this document:

{text[:6000]}..."""

        if model.startswith("gpt") and self.openai_client:
            response = await self._call_openai(system_prompt, user_prompt, model)
        elif model.startswith("claude") and self.anthropic_client:
            response = await self._call_anthropic(system_prompt, user_prompt, model)
        else:
            return {}
        
        logger.info(f"Raw OpenAI response: {response}")
        
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
            
            try:
                return json.loads(clean_text)
            except json.JSONDecodeError:
                # Try to find JSON object in the text
                json_match = re.search(r'\{.*\}', clean_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                raise
        
        try:
            parsed_response = extract_json_from_response(response)
            logger.info(f"Successfully parsed structured data: {list(parsed_response.keys())}")
            return parsed_response
        except Exception as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Raw response: {response}")
            return {"raw_extraction": response, "extraction_error": str(e)}
    
    async def _call_openai(self, system_prompt: str, user_prompt: str, model: str) -> str:
        """Call OpenAI API."""
        try:
            response = await self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API call failed: {str(e)}")
            raise
    
    async def _call_anthropic(self, system_prompt: str, user_prompt: str, model: str) -> str:
        """Call Anthropic API."""
        try:
            response = await self.anthropic_client.messages.create(
                model=model,
                max_tokens=2000,
                temperature=0.1,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API call failed: {str(e)}")
            raise
    
    def _estimate_cost(self, text: str, model: str) -> float:
        """Estimate API call cost based on token count and model."""
        # Rough token estimation: 1 token ≈ 4 characters
        token_count = len(text) // 4
        
        # Approximate costs per 1K tokens (as of 2024)
        costs = {
            "gpt-4o": 0.005,
            "gpt-4": 0.03,
            "gpt-3.5-turbo": 0.001,
            "claude-3-sonnet": 0.003,
            "claude-3-haiku": 0.0003
        }
        
        cost_per_1k = costs.get(model, 0.005)
        return (token_count / 1000) * cost_per_1k
    
    def detect_pii(self, text: str) -> Dict[str, Any]:
        """Detect and flag PII in document text."""
        import re
        
        pii_patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
            "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
            "address": r'\b\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b'
        }
        
        detected_pii = {}
        for pii_type, pattern in pii_patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                detected_pii[pii_type] = matches
        
        return detected_pii