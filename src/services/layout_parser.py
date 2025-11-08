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
    
    # Store all tokens for full text extraction
    all_tokens = tokens
    
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
    
    # Extract seller and buyer addresses (tokens near their names/GSTINs)
    seller_address = _extract_address_near_entity(seller_tokens, seller_name, gstins[0] if gstins else None)
    buyer_address = _extract_address_near_entity(buyer_tokens, buyer_name, gstins[1] if len(gstins) > 1 else None)
    
    return {
        "seller": {
            "name": seller_name,
            "gstin": gstins[0] if gstins else None,
            "address": seller_address,
            "confidence": 0.8,
            "bbox": seller_bbox or seller_gstin_bbox
        },
        "buyer": {
            "name": buyer_name,
            "gstin": gstins[1] if len(gstins) > 1 else None,
            "address": buyer_address,
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
        },
        "allTokens": all_tokens  # Include all tokens for full text extraction
    }


def _extract_address_near_entity(entity_tokens, entity_name, gstin):
    """Extract address lines near an entity (seller/buyer)."""
    if not entity_tokens:
        return None
    
    # Collect all text from entity tokens, excluding name and GSTIN
    address_parts = []
    for t in entity_tokens:
        text = t["text"].strip()
        # Skip if it's the entity name or GSTIN
        if entity_name and text == entity_name:
            continue
        if gstin and gstin in text.upper():
            continue
        # Skip common labels
        if text.lower() in ["seller", "buyer", "bill to", "ship to", "from", "to"]:
            continue
        if text:
            address_parts.append(text)
    
    return " ".join(address_parts) if address_parts else None


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


def extract_totals_from_tokens(tokens, image_bgr):
    """
    Extract totals (net, tax, gross, round-off) from tokens.
    Typically found at the bottom of invoices.
    """
    import re
    
    totals = {}
    texts = [t["text"] for t in tokens]
    joined = " ".join(texts).lower()
    
    # Patterns for totals
    patterns = {
        "taxable": [r'taxable\s*(?:value|amount)?\s*[:\-]?\s*[₹rs.]?\s*([\d,]+\.?\d*)', r'total\s*before\s*tax\s*[:\-]?\s*[₹rs.]?\s*([\d,]+\.?\d*)'],
        "tax": [r'total\s*tax\s*[:\-]?\s*[₹rs.]?\s*([\d,]+\.?\d*)', r'gst\s*total\s*[:\-]?\s*[₹rs.]?\s*([\d,]+\.?\d*)'],
        "gross": [r'grand\s*total\s*[:\-]?\s*[₹rs.]?\s*([\d,]+\.?\d*)', r'total\s*[:\-]?\s*[₹rs.]?\s*[₹rs.]?\s*([\d,]+\.?\d*)'],
        "round_off": [r'round\s*(?:off|round)\s*[:\-]?\s*[₹rs.]?\s*([\d,]+\.?\d*)']
    }
    
    for key, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, joined, re.I)
            if match:
                try:
                    val_str = match.group(1).replace(",", "").replace("₹", "").replace("Rs.", "").replace("rs.", "").strip()
                    totals[key] = float(val_str)
                    break
                except:
                    continue
    
    # Look for CGST/SGST/IGST
    cgst_pattern = r'cgst\s*[:\-]?\s*[₹rs.]?\s*([\d,]+\.?\d*)'
    sgst_pattern = r'sgst\s*[:\-]?\s*[₹rs.]?\s*([\d,]+\.?\d*)'
    igst_pattern = r'igst\s*[:\-]?\s*[₹rs.]?\s*([\d,]+\.?\d*)'
    
    for pattern, key in [(cgst_pattern, "cgst"), (sgst_pattern, "sgst"), (igst_pattern, "igst")]:
        match = re.search(pattern, joined, re.I)
        if match:
            try:
                val_str = match.group(1).replace(",", "").replace("₹", "").replace("Rs.", "").replace("rs.", "").strip()
                totals[key] = float(val_str)
            except:
                continue
    
    return totals

