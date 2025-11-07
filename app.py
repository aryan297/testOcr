from fastapi import FastAPI, UploadFile, File, Form, HTTPException, status
from fastapi.responses import JSONResponse, Response
from fastapi.openapi.utils import get_openapi
from pydantic import ValidationError
from src.schemas import OCRResponse
from src.utils.pdf import rasterize_pdf_if_needed
from src.utils.image_quality import assess_quality
from src.utils.preproc import enhance_image, upscale_if_needed, deskew_image
from src.services.ocr_engine import get_ocr, ocr_tokens
from src.services.table_extract import extract_table
from src.services.layout_parser import parse_header_blocks
from src.services.postprocess import build_response
from src.services.dedupe import compute_hashes
from src.logging_conf import setup_logging
import config
import time
import cv2
from typing import Dict, Any


app = FastAPI(
    title="OCR Service API",
    description="""
    A production-ready OCR microservice for extracting structured data from invoice images and PDFs.
    
    ## Features
    
    * **Invoice Parsing**: Extracts line items, header fields, and totals from invoices
    * **Quality Assessment**: Checks image focus, glare, and skew before processing
    * **Table Extraction**: Uses PP-Structure and heuristics to parse tabular data
    * **Duplicate Detection**: SHA256 and perceptual hashing for duplicate detection
    * **Structured Output**: Returns JSON with bounding boxes, confidences, and computed totals
    
    ## Supported Formats
    
    * Images: PNG, JPEG
    * Documents: PDF (first page processed by default)
    """,
    version="1.0.0",
    terms_of_service="https://example.com/terms/",
    contact={
        "name": "OCR Service Support",
        "email": "support@example.com",
    },
    license_info={
        "name": "MIT",
    },
    tags_metadata=[
        {
            "name": "Health",
            "description": "Health check and service status endpoints",
        },
        {
            "name": "OCR",
            "description": "OCR parsing endpoints for invoice extraction",
        },
        {
            "name": "Debug",
            "description": "Debug and visualization endpoints (requires DEBUG mode)",
        },
    ]
)

logger = setup_logging()
start_ts = time.time()


def custom_openapi():
    """Custom OpenAPI schema generator."""
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get(
    "/ocr/health",
    tags=["Health"],
    summary="Health Check",
    description="Check the health status of the OCR service and verify if models are loaded",
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "modelsLoaded": True,
                        "uptimeSec": 3600
                    }
                }
            }
        }
    }
)
def health():
    """
    Health check endpoint.
    
    Returns:
        - status: Service status (always "ok" if endpoint is reachable)
        - modelsLoaded: Whether OCR models are loaded and ready
        - uptimeSec: Service uptime in seconds
    """
    try:
        ocr = get_ocr()
        is_warm = ocr is not None
    except:
        is_warm = False
    return {
        "status": "ok",
        "modelsLoaded": is_warm,
        "uptimeSec": int(time.time() - start_ts)
    }


@app.get(
    "/ocr/version",
    tags=["Health"],
    summary="Version Information",
    description="Get version information for all dependencies",
    response_model=Dict[str, str],
    responses={
        200: {
            "description": "Version information",
            "content": {
                "application/json": {
                    "example": {
                        "opencv": "4.10.0",
                        "paddleocr": "2.7.0.3",
                        "pillow": "10.4.0",
                        "numpy": "1.26.4"
                    }
                }
            }
        }
    }
)
def version():
    """
    Version information endpoint.
    
    Returns version numbers for:
        - OpenCV
        - PaddleOCR
        - Pillow (PIL)
        - NumPy
    """
    import cv2
    import paddleocr
    from PIL import Image
    import numpy
    return {
        "opencv": cv2.__version__,
        "paddleocr": paddleocr.__version__,
        "pillow": Image.__version__,
        "numpy": numpy.__version__
    }


@app.post(
    "/ocr/debug/visualize",
    tags=["Debug"],
    summary="Visualize OCR Results",
    description="""
    Debug endpoint to visualize OCR results with bounding boxes overlaid on the image.
    
    **Requires DEBUG mode to be enabled** in the configuration.
    
    Returns a PNG image with:
    - Green bounding boxes around detected text
    - Text labels with confidence scores
    """,
    responses={
        200: {
            "description": "Visualized image with OCR bounding boxes",
            "content": {
                "image/png": {}
            }
        },
        403: {
            "description": "Debug mode is disabled",
            "content": {
                "application/json": {
                    "example": {"detail": "Debug mode disabled"}
                }
            }
        },
        415: {
            "description": "Unsupported file type",
            "content": {
                "application/json": {
                    "example": {"detail": "Only PNG/JPEG/PDF supported"}
                }
            }
        }
    }
)
async def visualize(file: UploadFile = File(..., description="Image or PDF file to process")):
    """
    Visualize OCR results with bounding boxes.
    
    This endpoint processes the uploaded file, runs OCR, and returns an image
    with bounding boxes drawn around detected text regions along with confidence scores.
    """
    if not config.DEBUG:
        raise HTTPException(status_code=403, detail="Debug mode disabled")
    
    if file.content_type not in {"image/png", "image/jpeg", "application/pdf"}:
        raise HTTPException(status_code=415, detail="Only PNG/JPEG/PDF supported")
    
    raw = await file.read()
    pages_bgr = rasterize_pdf_if_needed(raw, file.content_type)
    image_bgr = pages_bgr[0]
    
    # Enhance image
    image_bgr = enhance_image(image_bgr)
    image_bgr = upscale_if_needed(image_bgr)
    
    # Run OCR
    ocr = get_ocr()
    tokens = ocr_tokens(ocr, image_bgr)
    
    # Draw bounding boxes
    import numpy as np
    vis = image_bgr.copy()
    for token in tokens:
        bbox = token.get("bbox", [])
        if bbox:
            pts = np.array(bbox, np.int32)
            cv2.polylines(vis, [pts], True, (0, 255, 0), 2)
            # Add text
            text = f"{token['text']} ({token['conf']:.2f})"
            cv2.putText(vis, text, (int(bbox[0][0]), int(bbox[0][1]) - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    
    # Convert to PNG
    _, buffer = cv2.imencode('.png', vis)
    return Response(content=buffer.tobytes(), media_type="image/png")


@app.post(
    "/ocr/parse",
    tags=["OCR"],
    summary="Parse Invoice",
    description="""
    Main OCR parsing endpoint for extracting structured data from invoice images or PDFs.
    
    This endpoint:
    1. Validates image quality (focus, glare, resolution)
    2. Preprocesses the image (enhancement, upscaling, deskewing)
    3. Runs OCR to extract text with bounding boxes and confidence scores
    4. Parses header fields (seller, buyer, invoice number, date)
    5. Extracts table data (line items with quantities, prices, GST rates)
    6. Computes totals and reconciles with extracted values
    7. Returns structured JSON response
    
    **Supported file formats**: PNG, JPEG, PDF
    **Maximum file size**: Configurable via MAX_UPLOAD_MB (default: 12MB)
    **Minimum resolution**: 1600px on longest edge (configurable)
    """,
    response_model=OCRResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Successfully parsed invoice",
            "content": {
                "application/json": {
                    "example": {
                        "meta": {
                            "ocrConfidence": 0.85,
                            "quality": {
                                "focus": 120.5,
                                "glare": 0.02,
                                "skewDeg": 0.1,
                                "resolution": [1800, 1200]
                            },
                            "duplicateLikely": False,
                            "uploadHash": "sha256...",
                            "phash": "abcd1234"
                        },
                        "seller": {
                            "name": "ABC Corp",
                            "gstin": "29ABCDE1234F1Z5",
                            "confidence": 0.9,
                            "bbox": [[100, 50], [300, 50], [300, 100], [100, 100]]
                        },
                        "buyer": {
                            "name": "XYZ Ltd",
                            "gstin": "07FGHIJ5678K2Z9",
                            "confidence": 0.8,
                            "bbox": [[400, 50], [600, 50], [600, 100], [400, 100]]
                        },
                        "invoice": {
                            "number": {
                                "value": "INV-2456",
                                "confidence": 0.9,
                                "bbox": [[700, 50], [900, 50], [900, 100], [700, 100]],
                                "alt": []
                            },
                            "date": {
                                "value": "2025-11-04",
                                "confidence": 0.85,
                                "raw": "04/11/25"
                            },
                            "placeOfSupply": "DL"
                        },
                        "lines": [
                            {
                                "rowId": "r1",
                                "description": {
                                    "value": "Birla Cement 50kg",
                                    "confidence": 0.9,
                                    "bbox": [[100, 200], [400, 200], [400, 250], [100, 250]],
                                    "alts": None
                                },
                                "hsn": "2523",
                                "qty": {
                                    "value": 40.0,
                                    "unit": "bag",
                                    "confidence": 0.95,
                                    "bbox": [[500, 200], [600, 200], [600, 250], [500, 250]]
                                },
                                "unitPrice": {
                                    "value": 345.0,
                                    "confidence": 0.9,
                                    "bbox": [[650, 200], [750, 200], [750, 250], [650, 250]]
                                },
                                "gstRate": {
                                    "value": 0.18,
                                    "confidence": 0.85,
                                    "bbox": [[800, 200], [900, 200], [900, 250], [800, 250]]
                                },
                                "computed": {
                                    "net": 13800.0,
                                    "tax": 2484.0,
                                    "gross": 16284.0
                                }
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
                            "reconciled": True,
                            "roundOffDelta": 0.0
                        },
                        "warnings": []
                    }
                }
            }
        },
        413: {
            "description": "File too large",
            "content": {
                "application/json": {
                    "example": {"detail": "File too large. Max size: 12MB"}
                }
            }
        },
        415: {
            "description": "Unsupported file type",
            "content": {
                "application/json": {
                    "example": {"detail": "Only PNG/JPEG/PDF supported"}
                }
            }
        },
        422: {
            "description": "No text detected in image",
            "content": {
                "application/json": {
                    "example": {"detail": "No text detected in image"}
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Internal server error: ..."}
                }
            }
        }
    }
)
async def parse(
    file: UploadFile = File(
        ...,
        description="Invoice image (PNG/JPEG) or PDF file to process",
        example="invoice.png"
    ),
    return_visual: bool = Form(
        False,
        description="Return visualization image (not yet implemented)",
        example=False
    ),
    lang: str = Form(
        "en",
        description="OCR language code (e.g., 'en', 'hi')",
        example="en"
    )
):
    """
    Parse an invoice image or PDF and extract structured data.
    
    This is the main endpoint for invoice OCR processing. It handles:
    - Image quality validation
    - OCR text extraction
    - Layout parsing (headers, tables)
    - Data extraction (line items, totals)
    - Quality metrics and warnings
    
    Args:
        file: The invoice image or PDF file
        return_visual: Whether to return visualization (future feature)
        lang: Language code for OCR (default: 'en')
    
    Returns:
        OCRResponse: Structured JSON with extracted invoice data
    
    Raises:
        HTTPException: For various error conditions (file size, format, quality, etc.)
    """
    if file.content_type not in {"image/png", "image/jpeg", "application/pdf"}:
        raise HTTPException(
            status_code=415,
            detail="Only PNG/JPEG/PDF supported"
        )
    
    # Check file size
    raw = await file.read()
    file_size_mb = len(raw) / (1024 * 1024)
    if file_size_mb > config.MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {config.MAX_UPLOAD_MB}MB"
        )
    
    try:
        # Rasterize PDF or load image
        pages_bgr = rasterize_pdf_if_needed(raw, file.content_type)
        image_bgr = pages_bgr[0]  # First page only for now
        
        # Assess quality
        quality = assess_quality(image_bgr)
        
        if quality["reject"]:
            logger.warning("Image rejected due to quality issues", extra={"quality": quality})
            from src.schemas import MetaInfo, QualityMetrics, Warning
            return OCRResponse(
                meta=MetaInfo(
                    ocrConfidence=0.0,
                    quality=QualityMetrics(**quality),
                    duplicateLikely=False,
                    uploadHash="",
                    phash=""
                ),
                seller=None,
                buyer=None,
                invoice=None,
                lines=[],
                totals=None,
                warnings=[Warning(code="BAD_QUALITY")]
            )
        
        # Preprocess
        image_bgr = enhance_image(image_bgr)
        image_bgr = upscale_if_needed(image_bgr)
        skew_angle = quality.get("skewDeg", 0.0)
        if abs(skew_angle) > 0.5:
            image_bgr = deskew_image(image_bgr, skew_angle)
        
        # Run OCR
        ocr = get_ocr()
        tokens = ocr_tokens(ocr, image_bgr)
        
        if not tokens:
            logger.warning("No tokens extracted from image")
            raise HTTPException(
                status_code=422,
                detail="No text detected in image"
            )
        
        # Parse layout
        header = parse_header_blocks(tokens, image_bgr)
        
        # Extract table
        table = extract_table(tokens, image_bgr)
        
        # Compute hashes
        hashes = compute_hashes(image_bgr, raw)
        
        # Build response
        resp_dict = build_response(header, table, quality, hashes, raw, image_bgr)
        
        try:
            return OCRResponse.model_validate(resp_dict)
        except ValidationError as e:
            logger.exception("Validation error", extra={"errors": str(e)})
            raise HTTPException(
                status_code=500,
                detail=f"Response validation failed: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during OCR", extra={"error": str(e)})
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.APP_PORT)

