import cv2
import numpy as np
import torch
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from PIL import Image
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config


_TROCR_PROCESSOR = None
_TROCR_MODEL = None


def get_trocr_model():
    """Lazy load TrOCR model and processor."""
    global _TROCR_PROCESSOR, _TROCR_MODEL
    if _TROCR_PROCESSOR is None or _TROCR_MODEL is None:
        _TROCR_PROCESSOR = TrOCRProcessor.from_pretrained(config.TROCR_MODEL)
        _TROCR_MODEL = VisionEncoderDecoderModel.from_pretrained(config.TROCR_MODEL)
        if torch.cuda.is_available() and config.OCR_USE_GPU.lower() == "true":
            _TROCR_MODEL = _TROCR_MODEL.cuda()
    return _TROCR_PROCESSOR, _TROCR_MODEL


def is_handwritten(image_crop):
    """
    Detect if a text region contains handwriting.
    
    Uses edge density, stroke width variation, and texture analysis.
    Returns confidence score (0-1), higher = more likely handwritten.
    """
    if image_crop is None or image_crop.size == 0:
        return 0.0
    
    # Convert to grayscale
    if len(image_crop.shape) == 3:
        gray = cv2.cvtColor(image_crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = image_crop
    
    # Resize to standard size for consistent analysis
    h, w = gray.shape
    if h < 20 or w < 20:
        return 0.0
    
    # Feature 1: Edge density (handwriting has more irregular edges)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.sum(edges > 0) / (h * w)
    
    # Feature 2: Stroke width variation (handwriting varies more)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    dist_transform = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    stroke_widths = dist_transform[dist_transform > 0]
    stroke_variation = np.std(stroke_widths) if len(stroke_widths) > 0 else 0
    
    # Feature 3: Contour irregularity
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    irregularity = 0.0
    if contours:
        for cnt in contours:
            if len(cnt) > 5:
                area = cv2.contourArea(cnt)
                perimeter = cv2.arcLength(cnt, True)
                if perimeter > 0:
                    circularity = 4 * np.pi * area / (perimeter * perimeter)
                    irregularity += (1 - circularity)
        irregularity /= len(contours)
    
    # Combine features (tuned thresholds)
    score = 0.0
    if edge_density > 0.15:
        score += 0.3
    if stroke_variation > 2.0:
        score += 0.4
    if irregularity > 0.5:
        score += 0.3
    
    return min(score, 1.0)


def ocr_with_trocr(image_crop):
    """
    Run TrOCR on a handwritten text region.
    
    Returns (text, confidence).
    """
    try:
        processor, model = get_trocr_model()
        
        # Convert BGR to RGB PIL Image
        if len(image_crop.shape) == 3:
            rgb = cv2.cvtColor(image_crop, cv2.COLOR_BGR2RGB)
        else:
            rgb = cv2.cvtColor(image_crop, cv2.COLOR_GRAY2RGB)
        pil_img = Image.fromarray(rgb)
        
        # Process
        pixel_values = processor(pil_img, return_tensors="pt").pixel_values
        if torch.cuda.is_available() and config.OCR_USE_GPU.lower() == "true":
            pixel_values = pixel_values.cuda()
        
        # Generate
        generated_ids = model.generate(pixel_values)
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        
        # TrOCR doesn't provide confidence directly, use a heuristic
        # based on text length and model certainty
        confidence = 0.75 if len(generated_text) > 0 else 0.0
        
        return generated_text, confidence
    except Exception as e:
        print(f"TrOCR failed: {e}")
        return "", 0.0


def enhance_token_with_handwriting_detection(token, image_bgr):
    """
    Check if a token is handwritten and re-OCR with TrOCR if needed.
    
    Args:
        token: OCR token dict with text, conf, bbox
        image_bgr: Full image in BGR format
    
    Returns:
        Enhanced token with potentially updated text and confidence
    """
    if not config.ENABLE_HANDWRITING_DETECTION:
        return token
    
    bbox = token.get("bbox")
    if not bbox or len(bbox) < 4:
        return token
    
    # Extract crop
    try:
        pts = np.array(bbox, dtype=np.int32)
        x, y, w, h = cv2.boundingRect(pts)
        
        # Add padding
        pad = 5
        x = max(0, x - pad)
        y = max(0, y - pad)
        w = min(image_bgr.shape[1] - x, w + 2*pad)
        h = min(image_bgr.shape[0] - y, h + 2*pad)
        
        crop = image_bgr[y:y+h, x:x+w]
        
        # Check if handwritten
        hw_score = is_handwritten(crop)
        
        if hw_score > config.HANDWRITING_THRESHOLD:
            # Re-OCR with TrOCR
            trocr_text, trocr_conf = ocr_with_trocr(crop)
            
            if trocr_text and trocr_conf > token.get("conf", 0.0):
                # Use TrOCR result
                token["text"] = trocr_text
                token["conf"] = trocr_conf
                token["handwritten"] = True
                token["hw_score"] = hw_score
    except Exception as e:
        print(f"Handwriting detection failed: {e}")
    
    return token
