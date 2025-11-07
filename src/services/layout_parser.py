import re
import numpy as np
from sklearn.cluster import DBSCAN


GSTIN_RE = re.compile(r'\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b')
DATE_RE = re.compile(r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b', re.I)
INV_RE = re.compile(r'\b(inv|invoice)\s*[:\-]?\s*([A-Z0-9\-\/]+)', re.I)
PLACE_OF_SUPPLY_RE = re.compile(r'\b(place\s+of\s+supply|pos)\s*[:\-]?\s*([A-Z]{2})\b', re.I)


def _get_bbox_center(bbox):
    """Get center point of bounding box."""
    if not bbox:
        return None
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _cluster_tokens_by_position(tokens, n_clusters=2):
    """Cluster tokens by spatial position to separate seller/buyer blocks."""
    centers = []
    for t in tokens:
        center = _get_bbox_center(t.get("bbox"))
        if center:
            centers.append(center)
    
    if len(centers) < 2:
        return [0] * len(tokens)
    
    X = np.array(centers)
    clustering = DBSCAN(eps=200, min_samples=2).fit(X)
    return clustering.labels_


def parse_header_blocks(tokens, image_bgr):
    """Parse header fields: seller, buyer, invoice number, date, place of supply."""
    texts = [t["text"] for t in tokens]
    joined = " | ".join(texts)
    
    # Extract GSTINs
    gstins = GSTIN_RE.findall(joined.upper())
    
    # Extract dates
    dates = DATE_RE.findall(joined)
    date_match = dates[0] if dates else None
    
    # Extract invoice number
    inv_match = INV_RE.search(joined, re.I)
    inv_number = inv_match.group(2) if inv_match else None
    inv_bbox = None
    inv_conf = 0.0
    if inv_match:
        # Find token containing invoice number
        for t in tokens:
            if inv_match.group(2).upper() in t["text"].upper():
                inv_bbox = t.get("bbox")
                inv_conf = t.get("conf", 0.7)
                break
    
    # Extract place of supply
    pos_match = PLACE_OF_SUPPLY_RE.search(joined, re.I)
    place_of_supply = pos_match.group(2) if pos_match else None
    
    # Cluster tokens to separate seller/buyer
    clusters = _cluster_tokens_by_position(tokens)
    seller_tokens = [t for i, t in enumerate(tokens) if clusters[i] == 0]
    buyer_tokens = [t for i, t in enumerate(tokens) if clusters[i] == 1] if len(set(clusters)) > 1 else []
    
    # Find seller/buyer names (first non-GSTIN text in each cluster)
    seller_name = None
    seller_bbox = None
    buyer_name = None
    buyer_bbox = None
    
    for t in seller_tokens:
        if t["text"].strip() and not GSTIN_RE.search(t["text"]):
            seller_name = t["text"]
            seller_bbox = t.get("bbox")
            break
    
    for t in buyer_tokens:
        if t["text"].strip() and not GSTIN_RE.search(t["text"]):
            buyer_name = t["text"]
            buyer_bbox = t.get("bbox")
            break
    
    # Find GSTIN bboxes
    seller_gstin_bbox = None
    buyer_gstin_bbox = None
    
    if gstins:
        for t in tokens:
            if gstins[0] in t["text"].upper():
                seller_gstin_bbox = t.get("bbox")
                break
    
    if len(gstins) > 1:
        for t in tokens:
            if gstins[1] in t["text"].upper():
                buyer_gstin_bbox = t.get("bbox")
                break
    
    # Find date bbox
    date_bbox = None
    date_conf = 0.0
    if date_match:
        for t in tokens:
            if date_match[0] in t["text"]:
                date_bbox = t.get("bbox")
                date_conf = t.get("conf", 0.7)
                break
    
    return {
        "seller": {
            "name": seller_name,
            "gstin": gstins[0] if gstins else None,
            "confidence": 0.8,
            "bbox": seller_bbox or seller_gstin_bbox
        },
        "buyer": {
            "name": buyer_name,
            "gstin": gstins[1] if len(gstins) > 1 else None,
            "confidence": 0.6,
            "bbox": buyer_bbox or buyer_gstin_bbox
        },
        "invoice": {
            "number": {
                "value": inv_number,
                "confidence": inv_conf,
                "bbox": inv_bbox,
                "alt": []
            },
            "date": {
                "value": _normalize_date(date_match[0]) if date_match else None,
                "confidence": date_conf,
                "raw": date_match[0] if date_match else None
            },
            "placeOfSupply": place_of_supply
        }
    }


def _normalize_date(date_str):
    """Normalize date string to YYYY-MM-DD format."""
    import datetime
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"]:
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except:
            continue
    return date_str

