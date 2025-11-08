"""
Spatial Invoice Parser - Production-grade extraction using bounding box geometry.
Combines geometry-based table parsing with text heuristics for maximum robustness.

Architecture:
1. Tokenize fullText with bbox positions (cx, cy, left)
2. Group tokens into rows by y-proximity
3. Find header row (Description, HSN, Qty, etc.)
4. Compute column boundaries from header x-positions
5. Assign tokens to columns and extract items
6. Fallback to line-by-line parsing if header not found
"""
import re
from typing import List, Dict, Any, Optional
from statistics import median


# ----------------------- 
# Utilities
# ----------------------- 
def bbox_center(bbox):
    """Get center point of bounding box."""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def bbox_left(bbox):
    """Get left x-coordinate of bounding box."""
    return min(p[0] for p in bbox)


def bbox_top(bbox):
    """Get top y-coordinate of bounding box."""
    return min(p[1] for p in bbox)


def normalize_amount(s):
    """Normalize amount string to float."""
    if s is None:
        return None
    s = str(s).replace('₹', '').replace(',', '').strip()
    s = re.sub(r'[^\d\.\-]', '', s)
    try:
        return round(float(s), 2)
    except:
        return None


def token_conf(token):
    """Extract confidence from token (handles 'conf' or 'confidence' key)."""
    return token.get("conf") or token.get("confidence") or 1.0


# ----------------------- 
# Tokenize fullText (geometry-aware)
# ----------------------- 
def tokens_from_fulltext(fullText: List[Dict]) -> List[Dict]:
    """Convert OCR fullText to tokens with spatial coordinates."""
    toks = []
    for b in fullText:
        txt = b.get("text", "").strip()
        bbox = b.get("bbox")
        if not txt or not bbox:
            continue
        cx, cy = bbox_center(bbox)
        toks.append({
            "text": txt,
            "cx": cx,
            "cy": cy,
            "left": bbox_left(bbox),
            "bbox": bbox,
            "conf": token_conf(b)
        })
    toks.sort(key=lambda t: (t["cy"], t["left"]))
    return toks


# ----------------------- 
# Group tokens into rows
# ----------------------- 
def group_rows(tokens: List[Dict], y_tol=14.0) -> List[List[Dict]]:
    """Group tokens into rows by y-proximity."""
    rows = []
    for t in tokens:
        if not rows:
            rows.append([t])
            continue
        med = median([x["cy"] for x in rows[-1]])
        if abs(t["cy"] - med) <= y_tol:
            rows[-1].append(t)
        else:
            rows.append([t])
    for r in rows:
        r.sort(key=lambda x: x["left"])
    return rows


# ----------------------- 
# Find header row
# ----------------------- 
HEADER_KEYWORDS = ["description", "hsn", "hsn/sac", "quantity", "qty", "rate", "unit price", "amount", "taxable"]


def find_header(rows):
    """Find header row by keyword matching."""
    for i, row in enumerate(rows[:18]):
        text = " ".join(t["text"].lower() for t in row)
        score = sum(1 for k in HEADER_KEYWORDS if k in text)
        if score >= 2:
            return i
    # Fallback: any row containing 'hsn' or 'quantity'
    for i, row in enumerate(rows[:30]):
        txt = " ".join(t["text"].lower() for t in row)
        if "hsn" in txt or "quantity" in txt or "rate" in txt:
            return i
    return None


# ----------------------- 
# Compute column boundaries from header
# ----------------------- 
def compute_bounds(header_row):
    """Compute column boundaries from header token x-positions."""
    xs = [t["left"] for t in header_row]
    xs_sorted = sorted(xs)
    mids = []
    for a, b in zip(xs_sorted, xs_sorted[1:]):
        mids.append((a + b) / 2.0)
    bounds = []
    left = -1e6
    for m in mids:
        bounds.append((left, m))
        left = m
    bounds.append((left, 1e6))
    return bounds


def assign_cols(row, bounds):
    """Assign tokens to columns based on x-position."""
    cols = [[] for _ in bounds]
    for t in row:
        cx = t["cx"]
        placed = False
        for i, (l, r) in enumerate(bounds):
            if l <= cx <= r:
                cols[i].append(t)
                placed = True
                break
        if not placed:
            # Fallback: nearest bound
            dists = [abs(cx - (l + r) / 2.0) for (l, r) in bounds]
            cols[dists.index(min(dists))].append(t)
    return cols


def col_text(col):
    """Get text from column tokens."""
    return " ".join(t["text"] for t in col).strip()


def extract_amount_from_col(col):
    """Extract numeric amount from column."""
    txt = col_text(col)
    m = re.findall(r"[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})", txt)
    if not m:
        m = re.findall(r"\d+\.\d+", txt)
    if not m:
        return None
    return normalize_amount(m[-1])


# ----------------------- 
# Fallback parser when header not found
# ----------------------- 
def parse_item_from_text_line(ln: str) -> Optional[Dict]:
    """
    Try to extract item fields from a single text line using regex heuristics.
    Requires at least one decimal number (taxable amount) and a qty token.
    """
    # Normalize common separators
    s = ln.replace("₹", " ").replace(",", "")
    
    # Look for qty patterns e.g. '13 PCS', '149 Bag', '2 PCS'
    qty_m = re.search(r"(\d{1,6})\s*(PCS|Bag|KG|Nos|Pcs|BAG|PCS|KG|NOS)?\b", s, re.IGNORECASE)
    
    # Look for taxable/amount numbers: prefer numbers with 2 decimals
    amounts = re.findall(r"([0-9]+\.[0-9]{2})", s)
    
    # Look for HSN 4-8 digits
    hsn_m = re.search(r"\b(\d{4,8})\b", s)
    
    # If we have at least one decimal number and a qty: good candidate
    if amounts and qty_m:
        # Pick last decimal as taxableValue (common in Indian invoices)
        taxable_candidate = amounts[-1]
        unit_price_candidate = amounts[-2] if len(amounts) >= 2 else None
        
        desc = s
        # Remove numeric tokens for cleaner description
        desc = re.sub(r"\b" + re.escape(taxable_candidate) + r"\b", "", desc)
        if unit_price_candidate:
            desc = re.sub(r"\b" + re.escape(unit_price_candidate) + r"\b", "", desc)
        # Remove qty token
        desc = re.sub(qty_m.group(0), "", desc, flags=re.IGNORECASE).strip()
        
        # Remove HSN if present
        if hsn_m:
            desc = re.sub(r"\b" + hsn_m.group(1) + r"\b", "", desc)
        
        itm = {
            "description": re.sub(r"\s{2,}", " ", desc).strip() or None,
            "hsn": hsn_m.group(1) if hsn_m else None,
            "quantity": f"{qty_m.group(1)} {qty_m.group(2).upper()}" if qty_m.group(2) else qty_m.group(1),
            "unitPrice": normalize_amount(unit_price_candidate) if unit_price_candidate else None,
            "taxableValue": normalize_amount(taxable_candidate),
        }
        
        # GST percent if present
        gst_m = re.search(r"@?\s*([0-9]{1,2}(?:\.[0-9])?)\s*%", s)
        if gst_m:
            itm["gstRate"] = float(gst_m.group(1))
            itm["cgstRatePct"] = float(gst_m.group(1)) / 2
            itm["sgstRatePct"] = float(gst_m.group(1)) / 2
        
        return itm
    return None


def parse_items_fallback_by_lines(rows: List[List[Dict]]) -> List[Dict]:
    """
    Fallback when no header found. Iterates rows and forms logical 'line groups'
    by merging nearby lines that look like a single item (letters + numbers).
    """
    items = []
    # Convert rows to plain text lines
    txt_lines = [" ".join(t["text"] for t in r).strip() for r in rows if any(t.get("text") for t in r)]
    # Remove very short noise lines
    txt_lines = [ln for ln in txt_lines if len(ln) > 1]
    
    i = 0
    while i < len(txt_lines):
        ln = txt_lines[i]
        # If line contains big numeric sums or 'Sub Total' etc, stop
        if re.search(r"\b(Sub\s*Total|Total|Round Off|Amount Chargeable|Tax Amount)\b", ln, re.IGNORECASE):
            break
        
        # Heuristic: item block likely either:
        #  - single line with description + qty + unit + amount tokens
        #  - or description line(s) followed by a numeric line with qty/unit/price
        
        # Try single-line numeric parse first
        single = parse_item_from_text_line(ln)
        if single:
            items.append(single)
            i += 1
            continue
        
        # Else try to merge this line with next 1-2 lines to form an item
        merged = ln
        j = 1
        merged_item = None
        while j <= 2 and i + j < len(txt_lines):
            merged = merged + " " + txt_lines[i + j]
            merged_item = parse_item_from_text_line(merged)
            if merged_item:
                items.append(merged_item)
                break
            j += 1
        
        if merged_item:
            i += j + 1
            continue
        
        # No numeric evidence; consider it a description-only line, attach to next numeric line
        # If next line has numbers, merge current + next
        if i + 1 < len(txt_lines):
            combined = ln + " " + txt_lines[i + 1]
            combined_item = parse_item_from_text_line(combined)
            if combined_item:
                items.append(combined_item)
                i += 2
                continue
        
        # Fallback: skip line
        i += 1
    
    return items


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
    
    # Debug: log first few rows
    print(f"Total rows: {len(rows)}")
    for i, row in enumerate(rows[:10]):
        print(f"  Row {i}: {' '.join(t['text'] for t in row)}")
    
    header_idx = find_header_row(rows)
    items = []
    
    if header_idx is not None:
        print(f"Header found at row {header_idx}")
        items = parse_table_rows(rows, header_idx)
    else:
        print("Header not found, trying keyword search...")
    
    # Fallback 1: try to find 'Item name' keyword and attempt parsing below it
    if not items:
        for i, row in enumerate(rows):
            txt = " ".join(t["text"].lower() for t in row)
            if "item name" in txt or "description of goods" in txt:
                print(f"Found item keyword at row {i}")
                items = parse_table_rows(rows, i)
                if items:
                    break
    
    # Fallback 2: use line-by-line heuristic parser
    if not items:
        print("Using fallback line-by-line parser...")
        items = parse_items_fallback_by_lines(rows)
        print(f"Fallback parser found {len(items)} items")
    
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
