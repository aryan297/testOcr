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


def assess_quality(img_bgr):
    """Assess image quality and determine if it should be rejected."""
    h, w = img_bgr.shape[:2]
    focus = _focus_score(img_bgr)
    glare = _glare_ratio(img_bgr)
    angle = _deskew_angle(img_bgr)
    
    reject = config.REJECT_IF_BAD_QUALITY and (
        max(h, w) < 1600 or focus < config.MIN_FOCUS or glare > config.MAX_GLARE
    )
    
    return {
        "focus": focus,
        "glare": glare,
        "skewDeg": angle,
        "resolution": [w, h],
        "reject": bool(reject)
    }

