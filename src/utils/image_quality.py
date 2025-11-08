import cv2
import numpy as np
import sys
import os

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config


def _focus_score(img):
    """Calculate focus score using variance of Laplacian."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _glare_ratio(img):
    """Calculate ratio of overexposed pixels."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float((gray > 250).sum()) / gray.size


def _deskew_angle(img):
    """Detect skew angle using minimum area rectangle."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    coords = np.column_stack(np.where(gray < 250))
    if coords.size == 0:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    return -(90 + angle) if angle < -45 else -angle


def assess_quality(img_bgr, content_type: str | None = None):
    """
    Assess image quality and determine if it should be rejected.
    
    Args:
        img_bgr: BGR image array
        content_type: Content type of the file (e.g., "application/pdf", "image/png")
    
    Returns:
        Dictionary with quality metrics and reject flag
    """
    h, w = img_bgr.shape[:2]
    focus = _focus_score(img_bgr)
    glare = _glare_ratio(img_bgr)
    angle = _deskew_angle(img_bgr)
    
    is_pdf = (content_type == "application/pdf")
    
    # PDFs are usually crisp after rasterization; be more lenient
    min_edge_threshold = 1400 if is_pdf else 1600
    focus_threshold = 50.0 if is_pdf else config.MIN_FOCUS
    glare_threshold = 0.12 if is_pdf else config.MAX_GLARE
    
    min_edge_ok = max(h, w) >= min_edge_threshold
    focus_ok = focus >= focus_threshold
    glare_ok = glare <= glare_threshold
    
    # Only reject if REJECT_IF_BAD_QUALITY is enabled and quality is poor
    reject = config.REJECT_IF_BAD_QUALITY and not (min_edge_ok and focus_ok and glare_ok)
    
    return {
        "focus": focus,
        "glare": glare,
        "skewDeg": angle,
        "resolution": [w, h],
        "reject": bool(reject),
        "content_type": content_type
    }

