import io
import numpy as np
from PIL import Image
import pypdfium2 as pdfium
import cv2
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config


def rasterize_pdf_if_needed(raw: bytes, content_type: str):
    """Rasterize PDF to images or convert image bytes to BGR array."""
    if content_type != "application/pdf":
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        return [cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)]
    
    pdf = pdfium.PdfDocument(io.BytesIO(raw))
    scale = 300/72.0  # ~300 DPI
    pages_bgr = []
    for i in range(min(len(pdf), config.MAX_PAGES)):
        page = pdf[i]
        pil_img = page.render(scale=scale, rotation=0).to_pil()
        pages_bgr.append(cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR))
    return pages_bgr

