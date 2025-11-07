import io
import numpy as np
from PIL import Image
import pdfplumber
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
    
    pages = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for i, page in enumerate(pdf.pages[:config.MAX_PAGES]):
            pil = page.to_image(resolution=300).original
            pages.append(cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR))
    return pages

