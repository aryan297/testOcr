import hashlib
from PIL import Image
import imagehash
import numpy as np
import cv2
import io


def sha256_bytes(b: bytes) -> str:
    """Compute SHA256 hash of bytes."""
    return hashlib.sha256(b).hexdigest()


def perceptual_hash(img_bgr) -> str:
    """Compute perceptual hash of image."""
    img = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    return str(imagehash.phash(img))

