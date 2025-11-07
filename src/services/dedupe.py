from ..utils.hashing import sha256_bytes, perceptual_hash


def compute_hashes(image_bgr, raw_bytes):
    """Compute SHA256 and perceptual hash for duplicate detection."""
    return {
        "sha256": sha256_bytes(raw_bytes),
        "phash": perceptual_hash(image_bgr)
    }

