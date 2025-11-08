"""
Spatial Invoice Parser - Uses bounding box geometry for robust table extraction.
Handles variable spacing and multi-column tables by analyzing token positions.
"""
import math
import re
from typing import List, Dict, Any, Tuple, Optional
from statistics import median


# ----------------------- 
# Helpers for bbox math
# ----------------------- 
def bbox_center(bbox: List[List[float]]) -> Tuple[float, float]:
    """Get center point of bounding box."""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def bbox_top(bbox: List[List[float]]) -> float:
    """Get top y-coordinate of bounding box."""
    return min(p[1] for p in bbox)


def bbox_left(bbox: List[List[float]]) -> float:
    """Get left x-coordinate of bounding box."""
    return min(p[0] for p in bbox)


def normalize_amount(s: Optional[str]) -> Optional[float]:
    """Normalize amount string to float."""
    if not s:
        return None
    s = str(s).replace('₹', '').replace(',', '').strip()
    s = re.sub(r'[^\d\.\-]', '', s)
    try:
        return round(float(s), 2)
    except:
        return None


# ----------------------- 
# Build tokens + spatial index
# ----------------------- 
def tokens_from_fulltext(fullText: List[Dict[str, Any]]) -> List[Dict]:
    """
    Turn OCR fullText blocks into token list with center x,y and original text.
    """
    tokens = []
    for b in fullText:
        txt = b.get("text", "").strip()
        bbox = b.get("bbox")
        if not txt or not bbox:
            continue
        cx, cy = bbox_center(bbox)
        left = bbox_left(bbox)
        tokens.append({
            "text": txt,
            "cx": cx,
            "cy": cy,
            "left": left,
            "bbox": bbox,
            "confidence": b.get("confidence", 0.9)
        })
    # Sort top->bottom then left->right to help row grouping
    tokens.sort(key=lambda t: (t["cy"], t["left"]))
    return tokens


# ----------------------- 
# Group tokens into rows by y proximity
# ----------------------- 
def group_tokens_into_rows(tokens: List[Dict], y_tol: float = 12.0) -> List[List[Dict]]:
    """
    Group tokens into rows by clustering cy values. y_tol is px tolerance.
    """
    rows = []
    for t in tokens:
        if not rows:
            rows.append([t])
            continue
        # Difference between this token's y and last row's median y
        last_row = rows[-1]
        last_ys = [tt["cy"] for tt in last_row]
        med = median(last_ys)
        if abs(t["cy"] - med) <= y_tol:
            last_row.append(t)
        else:
            rows.append([t])
    # Sort tokens in each row left->right
    for r in rows:
        r.sort(key=lambda x: x["left"])
    return rows


# ----------------------- 
# Find header row (common headers)
# ----------------------- 
HEADER_KEYWORDS = [
    "description", "description of goods", "item name", "hsn", "hsn/sac",
    "qty", "quantity", "rate", "unit price", "amount", "taxable", "amount (incl",
    "sl", "s.no", "sr.no"
]


def find_header_row(rows: List[List[Dict]]) -> Optional[int]:
    """
    Return the index of the row that most closely matches header keywords.
    """
    for i, row in enumerate(rows[:12]):  # Usually header near top quarter
        txt = " ".join([t["text"].lower() for t in row])
        score = sum(1 for k in HEADER_KEYWORDS if k in txt)
        if score >= 2:
            return i
    # Fallback: find any row containing 'hsn' or 'description' word
    for i, row in enumerate(rows[:18]):
        txt = " ".join([t["text"].lower() for t in row])
        if "hsn" in txt or "description" in txt or "quantity" in txt:
            return i
    return None


# ----------------------- 
# Determine column boundaries from header
# ----------------------- 
def compute_column_bounds_from_header(header_row: List[Dict]) -> List[Tuple[float, float]]:
    """
    Use header tokens x positions to create column boundaries.
    Returns list of (x_left, x_right) for each column.
    """
    # Header tokens left positions
    xs = [t["left"] for t in header_row]
    xs_sorted = sorted(xs)
    # Boundaries between tokens: midpoints
    mids = []
    for a, b in zip(xs_sorted, xs_sorted[1:]):
        mids.append((a + b) / 2.0)
    # Column boundaries: (-inf, mids[0]), (mids[0], mids[1]), ..., (mids[-1], +inf)
    bounds = []
    left = -1e6
    for m in mids:
        bounds.append((left, m))
        left = m
    bounds.append((left, 1e6))
    return bounds


# ----------------------- 
# Assign tokens to columns using bounds
# ----------------------- 
def assign_tokens_to_columns(row: List[Dict], bounds: List[Tuple[float, float]]) -> List[List[Dict]]:
    """Assign tokens to columns based on their x-position."""
    cols = [[] for _ in bounds]
    for t in row:
        cx = t["cx"]
        placed = False
        for idx, (l, r) in enumerate(bounds):
            if l <= cx <= r:
                cols[idx].append(t)
                placed = True
                break
        if not placed:
            # If not fit (rare), put in closest column by distance to center boundaries
            dists = [min(abs(cx - l), abs(cx - r)) for (l, r) in bounds]
            cols[dists.index(min(dists))].append(t)
    return cols


# ----------------------- 
# Parse numeric tokens into amounts
# ----------------------- 
def extract_amounts_from_col(col_tokens: List[Dict]) -> Optional[float]:
    """Extract numeric amount from column tokens."""
    if not col_tokens:
        return None
    txt = " ".join([t["text"] for t in col_tokens])
    # Find last numeric token (likely the amount)
    matches = re.findall(r"[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?", txt)
    if not matches:
        # Maybe bare numbers like 6322.00
        matches = re.findall(r"\d+\.\d+", txt)
    if not matches:
        return None
    candidate = matches[-1]
    return normalize_amount(candidate)


# ----------------------- 
# Build items table from rows using header bounds
# ----------------------- 
def parse_table_rows(rows: List[List[Dict]], header_idx: int) -> List[Dict]:
    """Parse table rows into structured items using column boundaries."""
    items = []
    header_row = rows[header_idx]
    bounds = compute_column_bounds_from_header(header_row)
    
    # Iterate rows below header until a totals marker is found
    for row in rows[header_idx + 1:]:
        txt_line = " ".join([t["text"].lower() for t in row])
        if re.search(r"\b(total|sub total|amount chargeable|round off|tax amount)\b", txt_line, re.IGNORECASE):
            break
        # If row is too short or blank skip
        if len(row) < 1:
            continue
        
        cols = assign_tokens_to_columns(row, bounds)
        num_cols = len(cols)
        
        # Find column with HSN-like numbers
        hsn = None
        for c in cols:
            ctxt = " ".join(t["text"] for t in c)
            m = re.search(r"\b(\d{4,8})\b", ctxt)
            if m:
                hsn = m.group(1)
                break
        
        # Find qty column (contains 'pcs' or numbers)
        qty = None
        qty_col_idx = None
        for idx, c in enumerate(cols):
            ctxt = " ".join(t["text"].lower() for t in c)
            if re.search(r"\bpcs\b|\bkg\b|\bbag\b|\bnos\b", ctxt) or re.search(r"\b\d+\b", ctxt):
                qty_col_idx = idx
                qty = ctxt
                break
        
        # Amount as last numeric column candidate
        amount = None
        amount_idx = None
        for idx in reversed(range(num_cols)):
            a = extract_amounts_from_col(cols[idx])
            if a is not None:
                amount = a
                amount_idx = idx
                break
        
        # Unit price: find numeric column near amount
        unit_price = None
        if amount is not None and amount_idx is not None:
            if amount_idx - 1 >= 0:
                unit_price = extract_amounts_from_col(cols[amount_idx - 1])
        
        # Description: combine left-most columns before qty or hsn
        desc_parts = []
        stop_idx = min([i for i in [qty_col_idx] if i is not None] + [num_cols])
        for i in range(0, stop_idx):
            desc_parts.append(" ".join(t["text"] for t in cols[i]))
        description = " ".join(p for p in desc_parts if p).strip()
        
        # If description empty, fallback to whole row text
        if not description:
            description = " ".join(t["text"] for t in row)
        
        # Extract GST rate from row
        gst_rate = None
        for c in cols:
            ctxt = " ".join(t["text"] for t in c)
            gstm = re.search(r"\(?([0-9]{1,2}(?:\.[0-9])?)\s*%\)?", ctxt)
            if gstm:
                gst_rate = float(gstm.group(1))
                break
        
        item = {
            "description": description if description else None,
            "hsn": hsn,
            "quantity": qty.strip() if qty else None,
            "unitPrice": unit_price,
            "taxableValue": amount,
            "gstRate": gst_rate
        }
        
        # Drop rows that have no numeric evidence (likely noise)
        if item["description"] and (item["taxableValue"] or item["unitPrice"] or item["hsn"]):
            # Split GST into CGST/SGST
            if gst_rate:
                item["cgstRatePct"] = gst_rate / 2
                item["sgstRatePct"] = gst_rate / 2
            else:
                item["cgstRatePct"] = 9.0  # Default
                item["sgstRatePct"] = 9.0
            items.append(item)
    
    return items


# ----------------------- 
# Extract top/bottom blocks (seller/buyer/totals)
# ----------------------- 
def extract_top_bottom_blocks(rows: List[List[Dict]]) -> Tuple[str, str, str]:
    """
    Return (top_text, middle_text, bottom_text)
    top_text: first ~8 rows joined (seller area)
    bottom_text: last ~12 rows joined (totals area)
    middle_text: everything in between (likely items / buyer)
    """
    top_n = min(8, len(rows))
    bottom_n = min(12, len(rows))
    top_text = "\n".join([" ".join(t["text"] for t in r) for r in rows[:top_n]])
    bottom_text = "\n".join([" ".join(t["text"] for t in r) for r in rows[-bottom_n:]]) if len(rows) >= bottom_n else ""
    middle_text = "\n".join([" ".join(t["text"] for t in r) for r in rows[top_n:len(rows) - bottom_n]])
    return top_text, middle_text, bottom_text


# ----------------------- 
# Totals extraction from bottom_text
# ----------------------- 
def extract_totals_from_text(bottom_text: str) -> Dict[str, Any]:
    """Extract totals using regex patterns."""
    t = {}
    
    # Sub Total
    m = re.search(r"Sub\s*Total\s*[:\s]*₹?\s*([0-9\.,-]+)", bottom_text, re.IGNORECASE)
    t['subTotal'] = normalize_amount(m.group(1)) if m else None
    
    # CGST
    m = re.search(r"CGST@?[\d\.]*%?\s*[:\s]*₹?\s*([0-9\.,-]+)", bottom_text, re.IGNORECASE)
    t['cgst'] = normalize_amount(m.group(1)) if m else None
    
    # SGST
    m = re.search(r"SGST@?[\d\.]*%?\s*[:\s]*₹?\s*([0-9\.,-]+)", bottom_text, re.IGNORECASE)
    t['sgst'] = normalize_amount(m.group(1)) if m else None
    
    # Round Off
    m = re.search(r"Round\s*Off\s*[:\s]*([0-9\.\-]+)", bottom_text, re.IGNORECASE)
    t['roundOff'] = normalize_amount(m.group(1)) if m else 0.0
    
    # Total Amount
    m = re.search(r"Total\s*[:\s]*₹?\s*([0-9\.,-]+)", bottom_text, re.IGNORECASE)
    t['totalAmount'] = normalize_amount(m.group(1)) if m else None
    
    # Total Qty
    m = re.search(r"Total\s+([0-9]+\s*(?:PCS|Bag|KG|Nos)?)", bottom_text, re.IGNORECASE)
    t['totalQty'] = m.group(1) if m else None
    
    # Amount in words
    m = re.search(r"(Amount Chargeable \(in words\)|Invoice Amount In Words)(?:[:\s\n-]*)\s*(.+?)(?:\n|$)", bottom_text, re.IGNORECASE | re.DOTALL)
    t['totalInWords'] = m.group(2).strip() if m else None
    
    # Tax in words
    m = re.search(r"Tax Amount \(in words\)\s*[:\s]*([A-Za-z0-9 ,.]+)", bottom_text, re.IGNORECASE)
    t['taxInWords'] = m.group(1).strip() if m else None
    
    # Taxable value
    if not t.get('subTotal'):
        m = re.search(r"Taxable\s*Value\s*[:\s]*₹?\s*([0-9\.,-]+)", bottom_text, re.IGNORECASE)
        t['taxableValue'] = normalize_amount(m.group(1)) if m else None
    else:
        t['taxableValue'] = t['subTotal']
    
    # Total tax
    if t.get('cgst') and t.get('sgst'):
        t['totalTax'] = t['cgst'] + t['sgst']
    
    return t


# ----------------------- 
# High-level parse function: main entry
# ----------------------- 
def parse_ocr_fulltext(ocr_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point for spatial parsing.
    Uses bounding box geometry to extract structured invoice data.
    """
    fullTextArr = ocr_json.get("fullText", [])
    tokens = tokens_from_fulltext(fullTextArr)
    rows = group_tokens_into_rows(tokens, y_tol=14.0)
    
    header_idx = find_header_row(rows)
    items = []
    if header_idx is not None:
        items = parse_table_rows(rows, header_idx)
    
    # Fallback: try to find 'Item name' keyword and attempt parsing below it
    if not items:
        for i, row in enumerate(rows):
            txt = " ".join(t["text"].lower() for t in row)
            if "item name" in txt or "description of goods" in txt:
                items = parse_table_rows(rows, i)
                if items:
                    break
    
    top_text, middle_text, bottom_text = extract_top_bottom_blocks(rows)
    totals = extract_totals_from_text(bottom_text + "\n" + middle_text)
    
    # Seller & buyer extraction from top area
    seller = {"raw": top_text}
    # Try to get seller name (M/s or For)
    m = re.search(r"(M\/s\s*[A-Za-z0-9 &\.\-]+|For\s*[:\-]?\s*[A-Za-z0-9 &\.\-]+)", top_text, re.IGNORECASE)
    if m:
        seller['name'] = m.group(0).strip()
    gst = re.search(r"(GSTIN[^0-9A-Z]*([A-Z0-9]{15}))", top_text, re.IGNORECASE)
    if gst:
        seller['gstin'] = gst.group(2)
    
    # Buyer: try find 'Bill To' block in middle_text
    buyer = {}
    m2 = re.search(r"(?:Bill\s*To|Buyer\s*\(Bill to\)|Buyer)[\s:\-]*\n?(.+?)(?:Invoice|HSN\/SAC|Description of Goods|Tax Invoice)", middle_text + "\n" + bottom_text, re.IGNORECASE | re.DOTALL)
    if m2:
        block = m2.group(1).strip()
        buyer['raw'] = " ".join(block.split())
        # First line likely name
        first_line = block.split('\n')[0].strip() if '\n' in block else block
        buyer['name'] = first_line
        # Find gstin & phone
        g = re.search(r"([A-Z0-9]{15})", block)
        if g:
            buyer['gstin'] = g.group(1)
        ph = re.search(r"(\+?\d[\d\-\s]{6,}\d)", block)
        if ph:
            buyer['contact'] = ph.group(1)
    else:
        # Fallback: find any GSTIN in fullText and attribute to buyer if not seller
        all_text = top_text + "\n" + middle_text + "\n" + bottom_text
        gst_all = re.findall(r"([A-Z0-9]{15})", all_text)
        if gst_all:
            seller_gstin = seller.get('gstin')
            for gcode in gst_all:
                if gcode != seller_gstin:
                    buyer['gstin'] = gcode
                    break
    
    # Assemble final
    result = {
        "invoice": {
            "invoiceNumber": None,
            "invoiceDate": None,
            "placeOfSupply": None,
            "referenceNo": None,
            "referenceDate": None,
            "irn": None,
            "acknowledgement": None
        },
        "seller": seller,
        "buyer": buyer,
        "items": items,
        "totals": totals,
        "meta": {
            "documentType": "Tax Invoice" if "Tax Invoice" in top_text + middle_text + bottom_text else "Invoice",
            "isComputerGenerated": "Computer Generated" in top_text + middle_text + bottom_text,
            "authorisedSignatory": None
        }
    }
    
    # Try to fill invoice header fields by searching top_text
    inv_no = re.search(r"Invoice\s*No\.?\s*[:\.\-]?\s*([A-Za-z0-9\/\-]+)", top_text, re.IGNORECASE)
    if inv_no:
        result['invoice']['invoiceNumber'] = inv_no.group(1)
    inv_dt = re.search(r"\b(?:Dated|Date)\b\s*[:\.\-]?\s*([0-9]{1,2}[-\/][A-Za-z0-9]{1,3}[-\/][0-9]{2,4})", top_text, re.IGNORECASE)
    if inv_dt:
        result['invoice']['invoiceDate'] = inv_dt.group(1)
    pos = re.search(r"Place\s+of\s+Supply\s*[:\.\-]?\s*([^\n\r]+)", top_text, re.IGNORECASE)
    if pos:
        result['invoice']['placeOfSupply'] = pos.group(1).strip()
    ref = re.search(r"Reference\s*No\.?\s*[:\.\-]?\s*([A-Za-z0-9\/\-]+)", top_text + middle_text, re.IGNORECASE)
    if ref:
        result['invoice']['referenceNo'] = ref.group(1)
    
    return result
