# OCR Service - FastAPI + PaddleOCR + PP-Structure

A production-ready OCR microservice for extracting structured data from invoice images and PDFs.

## Features

- **Invoice Parsing**: Extracts line items, header fields, and totals from invoices
- **Quality Assessment**: Checks image focus, glare, and skew before processing
- **PP-Structure Table Extraction**: Uses PaddleOCR's PP-Structure for advanced table detection with per-cell OCR
- **Handwriting Detection**: Automatically detects handwritten text regions
- **TrOCR Fallback**: Uses Microsoft TrOCR for improved handwriting recognition
- **Duplicate Detection**: SHA256 and perceptual hashing for duplicate detection
- **Structured Output**: Returns JSON with bounding boxes, confidences, and computed totals
- **PDF Support**: Rasterizes PDFs at 300 DPI using pypdfium2 (no PyMuPDF compilation issues)

## Project Structure

```
ocr-fastapi/
├── app.py                 # FastAPI application
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker container definition
├── Makefile              # Build and run commands
├── README.md             # This file
├── src/
│   ├── __init__.py
│   ├── logging_conf.py   # Structured JSON logging
│   ├── schemas.py        # Pydantic models
│   ├── utils/
│   │   ├── image_quality.py  # Quality assessment
│   │   ├── preproc.py        # Image preprocessing
│   │   ├── hashing.py        # Hash computation
│   │   └── pdf.py            # PDF rasterization
│   └── services/
│       ├── ocr_engine.py           # PaddleOCR + PP-Structure wrapper
│       ├── handwriting_detector.py # Handwriting detection + TrOCR
│       ├── layout_parser.py        # Header/layout parsing
│       ├── table_extract.py        # Table extraction (PP-Structure + heuristics)
│       ├── postprocess.py          # Response building
│       ├── reconcile.py            # Totals reconciliation
│       └── dedupe.py               # Duplicate detection
└── tests/
    ├── test_health.py        # Health check tests
    └── test_parse_smoke.py   # Smoke tests
```

## Installation

### Prerequisites

- Python 3.11
- Docker (optional)

### Local Setup

1. Clone the repository:
```bash
cd ocr-fastapi
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` file from `.env.example`:
```bash
cp .env.example .env
```

5. Run the application:
```bash
make run
# Or directly:
uvicorn app:app --reload --port 8080
```

## Configuration

Edit `.env` file to configure:

### Basic Settings
- `APP_PORT`: Server port (default: 8080)
- `APP_WORKERS`: Number of worker processes (default: 2)
- `OCR_LANG`: OCR language (default: en)
- `OCR_USE_GPU`: Enable GPU (default: false)
- `MAX_UPLOAD_MB`: Maximum upload size in MB (default: 12)
- `MAX_PAGES`: Maximum PDF pages to process (default: 2)
- `MIN_FOCUS`: Minimum focus score (default: 80)
- `MAX_GLARE`: Maximum glare ratio (default: 0.08)
- `REJECT_IF_BAD_QUALITY`: Reject low-quality images (default: true)
- `DEBUG`: Enable debug mode (default: false)

### PP-Structure Settings
- `USE_PP_STRUCTURE`: Enable PP-Structure for table detection (default: true)
- `TABLE_STRUCTURE_MODEL`: Table structure model language (default: en)

### Handwriting Detection Settings
- `ENABLE_HANDWRITING_DETECTION`: Enable handwriting detection (default: true)
- `HANDWRITING_THRESHOLD`: Confidence threshold for handwriting detection (default: 0.6)
- `TROCR_MODEL`: TrOCR model to use (default: microsoft/trocr-base-handwritten)

## API Documentation

### Swagger UI

Once the service is running, you can access the interactive Swagger UI documentation at:

- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc
- **OpenAPI Schema**: http://localhost:8080/openapi.json

The Swagger UI provides:
- Interactive API testing
- Request/response examples
- Schema definitions
- Try-it-out functionality for all endpoints

## API Endpoints

### POST /ocr/parse

Parse an invoice image or PDF (detailed OCR response).

### POST /ocr/parse/structured

Parse an invoice and return clean, business-friendly format (recommended for integrations).

# Or test locally
source venv/bin/activate
uvicorn app:app --reload --port 8080

**Request:**
- `file`: Multipart file (PNG/JPEG/PDF)
- `return_visual`: Optional boolean (default: false)
- `lang`: Optional language code (default: en)

**Response:**
```json
{
  "meta": {
    "ocrConfidence": 0.85,
    "quality": {
      "focus": 120.5,
      "glare": 0.02,
      "skewDeg": 0.1,
      "resolution": [1800, 1200]
    },
    "duplicateLikely": false,
    "uploadHash": "sha256...",
    "phash": "abcd1234"
  },
  "seller": {
    "name": "ABC Corp",
    "gstin": "29ABCDE1234F1Z5",
    "address": "123 Main St, City, State 12345",
    "confidence": 0.9,
    "bbox": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
  },
  "buyer": {
    "name": "XYZ Ltd",
    "gstin": "07FGHIJ5678K2Z9",
    "address": "456 Oak Ave, Town, State 67890",
    "confidence": 0.8,
    "bbox": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
  },
  "invoice": {
    "number": {"value": "INV-2456", "confidence": 0.9, ...},
    "date": {"value": "2025-11-04", ...},
    "placeOfSupply": "DL"
  },
  "lines": [
    {
      "rowId": "r1",
      "description": {"value": "Birla Cement 50kg", ...},
      "hsn": "2523",
      "qty": {"value": 40.0, "unit": "bag", ...},
      "unitPrice": {"value": 345.0, ...},
      "gstRate": {"value": 0.18, ...},
      "computed": {"net": 13800.0, "tax": 2484.0, "gross": 16284.0}
    }
  ],
  "totals": {
    "net": 13800.0,
    "tax": 2484.0,
    "gross": 16284.0,
    "cgst": 1242.0,
    "sgst": 1242.0,
    "igst": 0.0,
    "confidence": 0.8,
    "reconciled": true,
    "roundOffDelta": 0.0
  },
  "warnings": [],
  "fullText": [
    {
      "text": "ABC Corp",
      "confidence": 0.95,
      "bbox": [[100, 50], [200, 50], [200, 80], [100, 80]],
      "handwritten": false
    },
    {
      "text": "123 Main St",
      "confidence": 0.92,
      "bbox": [[100, 85], [220, 85], [220, 110], [100, 110]]
    }
    // ... all extracted text with positions
  ]
}
```

### GET /ocr/health

Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "modelsLoaded": true,
  "uptimeSec": 3600
}
```

### GET /ocr/version

Get version information.

**Response:**
```json
{
  "opencv": "4.10.0",
  "paddleocr": "2.7.0.3",
  "pillow": "10.4.0",
  "numpy": "1.26.4"
}
```

### POST /ocr/debug/visualize

Visualize OCR results with bounding boxes (requires DEBUG=true).

**Request:**
- `file`: Multipart file (PNG/JPEG/PDF)

**Response:**
PNG image with overlaid bounding boxes and confidence scores.

## Docker

### Build
```bash
make build
# Or:
docker build -t ocr-fastapi:local .
```

### Run
```bash
make serve
# Or:
docker run -p 8080:8080 ocr-fastapi:local
```

## Testing

Run tests:
```bash
make test
# Or:
pytest -q
```

## Usage Example

```python
import requests

# Parse an invoice
with open("invoice.png", "rb") as f:
    files = {"file": ("invoice.png", f, "image/png")}
    data = {"return_visual": "false", "lang": "en"}
    response = requests.post("http://localhost:8080/ocr/parse", files=files, data=data)
    result = response.json()
    
    print(f"Seller: {result['seller']['name']}")
    print(f"Invoice Number: {result['invoice']['number']['value']}")
    print(f"Total: {result['totals']['gross']}")
    for line in result['lines']:
        print(f"  {line['description']['value']}: {line['qty']['value']} {line['qty']['unit']}")
```

## Performance

- **Processing Time**: 
  - ~2-3 seconds per invoice on CPU (for 1800px images, basic OCR)
  - ~4-6 seconds with PP-Structure enabled
  - +1-2 seconds per handwritten cell with TrOCR
- **Accuracy**: 
  - Header fields: ~80%+ on clean samples
  - Numeric fields: ~90%+ on clean samples
  - Table extraction: ~85%+ with PP-Structure (vs ~70% with heuristics)
  - Handwritten text: ~75%+ with TrOCR (vs ~50% with standard OCR)

## Limitations

- Processes up to MAX_PAGES of PDFs (default: 2)
- Table extraction works best with clear table structures
- Requires images with minimum 1600px on longest edge (configurable)
- GPU support requires CUDA setup
- TrOCR model downloads ~500MB on first run
- Handwriting detection adds processing time per detected cell

## License

MIT

