# Document Intelligence System

A universal document intelligence platform that can process any file, analyze its content using AI, and extract structured data for use in downstream systems.

## 🚀 Features

- **Universal File Support**: PDF, Word, Excel, PowerPoint, images, HTML, ZIP, email, and more
- **Smart Text Extraction**: Advanced parsing with OCR fallback for locked/image-based documents  
- **AI-Powered Analysis**: Document classification, summarization, and structured data extraction
- **Multiple LLM Support**: OpenAI GPT-4o, Claude 3, and more
- **PII Detection**: Automatic detection and flagging of sensitive information
- **Multiple Interfaces**: CLI tool, REST API, and Docker deployment
- **Security First**: Input validation, file sanitization, and secure processing

## 📋 Supported Document Types

### File Formats
- **Documents**: PDF, DOCX, PPTX, HTML, TXT
- **Spreadsheets**: XLSX, CSV  
- **Images**: PNG, JPG, JPEG (with OCR)
- **Archives**: ZIP (recursive processing)
- **Email**: EML, MSG

### Document Types Detected
- Invoices (vendor, amounts, dates, line items)
- Resumes (experience, skills, education, contact info)
- Contracts (parties, terms, dates, clauses)
- Purchase Orders (items, vendors, amounts)
- Reports, Forms, and more

## 🛠 Quick Start

### 1. Setup Environment

```bash
git clone <repository>
cd revestData
cp .env.example .env
# Edit .env with your API keys
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run with Docker (Recommended)

```bash
docker-compose up -d
```

### 4. Use CLI Tool

```bash
# Process a single document
python cli.py process examples/sample_invoice.txt

# Process multiple files
python cli.py batch examples/

# Check configuration
python cli.py config

# Validate file compatibility
python cli.py validate examples/sample_resume.txt
```

### 5. Use REST API

```bash
# Start the API server
python main.py

# Upload and process document
curl -X POST "http://localhost:8000/upload" \
  -F "file=@examples/sample_invoice.txt" \
  -F "model=gpt-4o"

# Check processing status
curl "http://localhost:8000/status/{request_id}"

# Get results
curl "http://localhost:8000/results/{request_id}"
```

## 🔧 Configuration

Set these environment variables in `.env`:

```bash
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
DATABASE_URL=postgresql://user:pass@localhost:5432/docai
MAX_FILE_SIZE=50MB
```

## 📊 Example Output

```json
{
  "summary": "This is an invoice from TechSupply Corp to Acme Corporation for computer equipment and accessories totaling $15,271.38...",
  "document_type": "invoice",
  "confidence": 0.95,
  "extracted_fields": {
    "vendor_name": "TechSupply Corp",
    "invoice_number": "INV-2024-001", 
    "invoice_date": "2024-01-15",
    "total_amount": 15271.38,
    "line_items": [
      {"description": "Laptop Computers HP EliteBook", "qty": 10, "rate": 1200, "amount": 12000}
    ]
  },
  "processing_time": 3.2,
  "model_used": "gpt-4o",
  "cost_estimate": 0.0245
}
```

## 🧪 Testing

```bash
# Run test suite
pytest tests/

# Test specific module
pytest tests/test_parser.py -v

# Test with coverage
pytest --cov=src tests/
```

## 🔒 Security Features

- File type validation and size limits
- Input sanitization and malware scanning
- PII detection and redaction
- Secure temporary file handling
- API rate limiting and authentication

## 🏗 Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   File Upload   │    │   Document       │    │   AI Pipeline   │
│   • Validation  │───▶│   Parser         │───▶│   • OpenAI      │
│   • Storage     │    │   • Multi-format │    │   • Claude      │
│   • Security    │    │   • OCR Fallback │    │   • Analysis    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   REST API      │    │   CLI Interface  │    │   Output        │
│   • Endpoints   │    │   • Batch        │    │   • JSON        │
│   • Background  │    │   • Validation   │    │   • Structured  │
│   • Status      │    │   • Config       │    │   • Metadata    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 📚 API Reference

### Endpoints

- `POST /upload` - Upload and process document
- `GET /status/{id}` - Check processing status  
- `GET /results/{id}` - Get analysis results
- `GET /health` - Health check

### CLI Commands

- `process <file>` - Process single document
- `batch <directory>` - Process multiple files
- `validate <file>` - Check file compatibility
- `config` - Show configuration

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit pull request

## 📄 License

MIT License - see LICENSE file for details.