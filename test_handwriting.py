#!/usr/bin/env python3
"""
Quick test script for handwriting detection and TrOCR.
"""
import cv2
import numpy as np
from src.services.handwriting_detector import is_handwritten, ocr_with_trocr

# Create a simple test image with text
def create_test_image():
    img = np.ones((100, 300, 3), dtype=np.uint8) * 255
    cv2.putText(img, "Test Invoice", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    return img

if __name__ == "__main__":
    print("Testing handwriting detection...")
    
    test_img = create_test_image()
    hw_score = is_handwritten(test_img)
    print(f"Handwriting score: {hw_score:.2f}")
    
    if hw_score > 0.5:
        print("Detected as handwritten, running TrOCR...")
        text, conf = ocr_with_trocr(test_img)
        print(f"TrOCR result: '{text}' (confidence: {conf:.2f})")
    else:
        print("Detected as printed text")
    
    print("\nTest complete!")
