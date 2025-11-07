from paddleocr import PaddleOCR
import sys
import os
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config


_OCR = None


def get_ocr():
    """Get or initialize PaddleOCR instance (singleton)."""
    global _OCR
    if _OCR is None:
        _OCR = PaddleOCR(
            use_angle_cls=True,
            lang=config.OCR_LANG,
            det=True,
            rec=True,
            use_gpu=(config.OCR_USE_GPU.lower() == "true")
        )
    return _OCR


def ocr_tokens(ocr, image_bgr):
    """Run OCR on image and return tokens with text, confidence, and bounding box."""
    result = ocr.ocr(image_bgr, cls=True)
    tokens = []
    if result and result[0]:
        for box, (text, score) in result[0]:
            tokens.append({
                "text": text,
                "conf": float(score),
                "bbox": [[float(p[0]), float(p[1])] for p in box]
            })
    return tokens

