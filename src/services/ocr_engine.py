from paddleocr import PaddleOCR
import sys
import os
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config


_OCR = None
_STRUCTURE_OCR = None


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


def get_structure_ocr():
    """Get or initialize PP-Structure OCR for table detection."""
    global _STRUCTURE_OCR
    if _STRUCTURE_OCR is None and config.USE_PP_STRUCTURE:
        try:
            from paddleocr import PPStructure
            _STRUCTURE_OCR = PPStructure(
                table=True,
                ocr=True,
                show_log=False,
                lang=config.TABLE_STRUCTURE_MODEL,
                use_gpu=(config.OCR_USE_GPU.lower() == "true")
            )
        except Exception as e:
            print(f"Failed to initialize PP-Structure: {e}")
            _STRUCTURE_OCR = None
    return _STRUCTURE_OCR


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
    
    # Apply handwriting detection if enabled
    if config.ENABLE_HANDWRITING_DETECTION:
        from src.services.handwriting_detector import enhance_token_with_handwriting_detection
        tokens = [enhance_token_with_handwriting_detection(t, image_bgr) for t in tokens]
    
    return tokens


def extract_table_with_structure(image_bgr):
    """
    Extract table using PP-Structure.
    
    Returns structured table data with cells and their OCR results.
    """
    structure_ocr = get_structure_ocr()
    if structure_ocr is None:
        return None
    
    try:
        result = structure_ocr(image_bgr)
        
        # Parse PP-Structure output
        tables = []
        for item in result:
            if item.get('type') == 'table':
                table_data = {
                    'bbox': item.get('bbox'),
                    'cells': [],
                    'html': item.get('res', {}).get('html', '')
                }
                
                # Extract cell-level OCR
                cell_boxes = item.get('res', {}).get('cell_bbox', [])
                for cell_box in cell_boxes:
                    # Run OCR on each cell
                    x1, y1, x2, y2 = map(int, cell_box[:4])
                    cell_crop = image_bgr[y1:y2, x1:x2]
                    
                    if cell_crop.size > 0:
                        ocr = get_ocr()
                        cell_result = ocr.ocr(cell_crop, cls=True)
                        
                        cell_text = ""
                        cell_conf = 0.0
                        if cell_result and cell_result[0]:
                            texts = []
                            confs = []
                            for box, (text, score) in cell_result[0]:
                                texts.append(text)
                                confs.append(score)
                            cell_text = " ".join(texts)
                            cell_conf = sum(confs) / len(confs) if confs else 0.0
                        
                        # Check for handwriting in cell
                        if config.ENABLE_HANDWRITING_DETECTION and cell_text:
                            from src.services.handwriting_detector import is_handwritten, ocr_with_trocr
                            hw_score = is_handwritten(cell_crop)
                            if hw_score > config.HANDWRITING_THRESHOLD:
                                trocr_text, trocr_conf = ocr_with_trocr(cell_crop)
                                if trocr_text and trocr_conf > cell_conf:
                                    cell_text = trocr_text
                                    cell_conf = trocr_conf
                        
                        table_data['cells'].append({
                            'bbox': [x1, y1, x2, y2],
                            'text': cell_text,
                            'conf': cell_conf
                        })
                
                tables.append(table_data)
        
        return tables
    except Exception as e:
        print(f"PP-Structure extraction failed: {e}")
        return None

