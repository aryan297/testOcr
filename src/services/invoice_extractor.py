"""
Production Invoice Extractor - Optimized geometry + heuristics parser.
Single-function entry point: extract_invoice_structured(ocr_json)
"""
import re
from statistics import median
from typing import List, Dict, Any, Optional


# ---------------- Utilities ----------------
def bbox_center(bbox):
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def bbox_left(bbox):
    return min(p[0] for p in bbox)


def bbox_top(bbox):
    return min(p[1] for p in bbox)


def normalize_amount(s):
    if s is None:
        return None
    s = str(s).replace('₹', '').replace(',', '').strip()
    s = re.sub(r'[^\d\.\-]', '', s)
    try:
        return round(float(s), 2)
    except:
        return None


def token_conf(token):
    return token.get("conf") or token.get("confidence") or 1.0


# ---------------- Tokenize fullText (geometry-aware) ----------------
def tokens_from_fulltext(fullText: List[Dict]) -> List[Dict]:
    """
    Convert fullText to tokens with spatial coordinates.
    Handles multi-page documents by detecting page breaks.
    """
    toks = []
    for idx, b in enumerate(fullText):
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
            "conf": token_conf(b),
            "idx": idx  # Preserve original order
        })
    
    # Detect page breaks (large y-jumps backwards indicate new page)
    page_num = 0
    prev_cy = -1
    for t in toks:
        if prev_cy > 0 and t["cy"] < prev_cy - 1000:  # Large backward jump = new page
            page_num += 1
        t["page"] = page_num
        prev_cy = t["cy"]
    
    # Sort by page, then y, then x
    toks.sort(key=lambda t: (t.get("page", 0), t["cy"], t["left"]))
    return toks


# ---------------- Group tokens into rows ----------------
def group_rows(tokens: List[Dict], y_tol=14.0) -> List[List[Dict]]:
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


# ---------------- Find header row (soft scoring) ----------------
HEADER_KEYWORDS = ["description", "hsn", "quantity", "qty", "rate", "amount", "unit price", "taxable"]


def find_header_soft(rows):
    """
    Soft header detection with multiple fallback strategies.
    Returns: (header_idx, start_parse_idx)
    - header_idx: row to use for column bounds
    - start_parse_idx: row to start parsing from
    """
    # Strategy 1: Keyword scoring (require 3+ tokens for valid header)
    for i, row in enumerate(rows[:30]):
        text = " ".join(t["text"].lower() for t in row)
        score = sum(1 for k in HEADER_KEYWORDS if k in text)
        if score >= 2 and len(row) >= 3:
            return (i, i + 1)  # Normal: use header for bounds, parse from next row
    
    # Strategy 2: Look for "Quantity" or "HSN" keywords (more specific than "Description of Goods")
    for i, row in enumerate(rows[:50]):
        text = " ".join(t["text"].lower() for t in row)
        # Prioritize "Quantity" or "HSN/SAC" as stronger header indicators
        if "quantity" in text or "hsn/sac" in text or "hsn code" in text:
            # Look ahead for first row with 3+ numeric tokens (actual data)
            for j in range(i + 1, min(i + 10, len(rows))):
                row_text = " ".join(t["text"] for t in rows[j])
                # Count numeric tokens (amounts/quantities)
                numeric_count = len(re.findall(r'\d+\.\d{2}|\d+\s*(?:PCS|Bag|KG)', row_text, re.I))
                if numeric_count >= 2 and len(rows[j]) >= 3:
                    # Use data row for columns, but start parsing from row after header (to capture descriptions)
                    parse_start = i + 1
                    print(f"  ⚠ Found header keyword at row {i}, using data row {j} for columns, parsing from row {parse_start}")
                    return (j, parse_start)
            # If no good data row found, use next row after header
            if len(row) >= 3:
                return (i, i + 1)
    
    # Strategy 2b: Fallback to "Description of Goods" or "Item name"
    for i, row in enumerate(rows[:40]):
        text = " ".join(t["text"].lower() for t in row)
        if "description of goods" in text or "item name" in text:
            # Look ahead for multi-token data row
            for j in range(i + 1, min(i + 8, len(rows))):
                if len(rows[j]) >= 4:
                    # Start parsing from row after header to capture descriptions
                    parse_start = i + 1
                    print(f"  ⚠ Header label at row {i}, inferring columns from row {j}, parsing from row {parse_start}")
                    return (j, parse_start)
            return (i, i + 1)
    
    # Strategy 3: Look for first row with 3+ decimal amounts (likely data row)
    for i, row in enumerate(rows[10:50], 10):
        row_text = " ".join(t["text"] for t in row)
        # Count decimal amounts
        amounts = re.findall(r'\d+\.\d{2}', row_text)
        if len(amounts) >= 3 and len(row) >= 3:
            print(f"  ⚠ Found data row {i} with {len(amounts)} amounts, using for column inference")
            return (i, i)
    
    # Strategy 4: First row with 4+ tokens after row 8 (likely data row)
    for i, row in enumerate(rows[8:50], 8):
        if len(row) >= 4:
            print(f"  ⚠ Using first multi-token row {i} as header proxy")
            return (i, i)
    
    return (None, None)


# ---------------- Compute column bounds from header ----------------
def compute_bounds(header_row, expand_px=12):
    """Compute column bounds with safety checks for incomplete headers."""
    xs = [t["left"] for t in header_row]
    
    # If header has < 3 tokens, it's incomplete - return single column
    if len(xs) < 3:
        print(f"  ⚠ Header has only {len(xs)} tokens - using single column fallback")
        return [(-1e6, 1e6)]
    
    xs_sorted = sorted(xs)
    mids = []
    for a, b in zip(xs_sorted, xs_sorted[1:]):
        mids.append((a + b) / 2.0)
    
    bounds = []
    left = -1e6
    for m in mids:
        bounds.append((left - expand_px, m + expand_px))
        left = m
    bounds.append((left - expand_px, 1e6))
    
    # Merge tiny bounds (< 60px width)
    merged = []
    for l, r in bounds:
        if not merged:
            merged.append((l, r))
            continue
        pl, pr = merged[-1]
        if (r - l) < 60:
            merged[-1] = (pl, r)
        else:
            merged.append((l, r))
    
    return merged


def assign_cols(row, bounds):
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
            dists = [abs(cx - (l + r) / 2.0) for (l, r) in bounds]
            cols[dists.index(min(dists))].append(t)
    return cols


def col_text(col):
    return " ".join(t["text"] for t in col).strip()


def extract_amount_from_col(col):
    txt = col_text(col)
    # Exclude percentages
    if re.search(r"%|\bpercent\b", txt, re.IGNORECASE):
        return None
    m = re.findall(r"[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})", txt)
    if not m:
        m = re.findall(r"\d+\.\d+", txt)
    if not m:
        return None
    return normalize_amount(m[-1])


# ---------------- Detect if table is transposed (items as columns) ----------------
def parse_transposed_table(rows, start_idx, bounds):
    """
    Parse transposed table where items are columns, not rows.
    Each row represents a field (quantity, rate, amount, etc.)
    """
    items = []
    
    # Collect field rows (look backwards for HSN row before start_idx)
    field_rows = {}
    
    # Look backwards up to 10 rows for HSN and descriptions
    desc_candidates = []
    for row in rows[max(0, start_idx - 10):start_idx]:
        line_text = " ".join(t["text"].lower() for t in row)
        if "hsn" in line_text and len(row) >= 3:
            field_rows['hsn'] = row
        # Collect potential description rows (rows with 3+ tokens before HSN row)
        elif len(row) >= 3 and 'hsn' not in field_rows:
            # Check if row has item-like text (not header keywords)
            if not any(kw in line_text for kw in ["invoice", "buyer", "seller", "gstin", "state name", "bill to"]):
                desc_candidates.append(row)
    
    # Look forward for other fields
    for row in rows[start_idx:min(start_idx + 30, len(rows))]:
        line_text = " ".join(t["text"].lower() for t in row)
        
        # Stop at totals
        if re.search(r"\b(total|sub total|amount chargeable)\b", line_text, re.IGNORECASE):
            break
        
        # Identify field type
        if "quantity" in line_text or "qty" in line_text:
            field_rows['quantity'] = row
        elif "rate" in line_text and len(row) >= 3:
            if 'rate' not in field_rows:
                field_rows['rate'] = row
        elif "amount" in line_text and len(row) >= 3:
            field_rows['amount'] = row
        elif "hsn" in line_text:
            # HSN row might have 4 tokens (3 HSN codes + "HSN/SAC" label)
            if len(row) >= 3:
                field_rows['hsn'] = row
        # Check if row contains quantities (numbers with units)
        elif len(row) >= 3 and 'quantity' not in field_rows:
            row_text = " ".join(t["text"] for t in row)
            qty_matches = re.findall(r'\d+\s*(?:PCS|Bag|KG|Nos|pcs|bag)', row_text, re.I)
            if len(qty_matches) >= 2:
                field_rows['quantity'] = row
        elif len(row) >= 3:
            # Check if row has multiple amounts (likely data row)
            row_text = " ".join(t["text"] for t in row)
            amounts = re.findall(r'\d+\.\d{2}', row_text)
            if len(amounts) >= 2:
                # Guess field type based on values
                avg_val = sum(float(a) for a in amounts) / len(amounts)
                if avg_val > 100 and 'amount' not in field_rows:
                    field_rows['amount'] = row
                elif avg_val < 100 and 'rate' not in field_rows:
                    field_rows['rate'] = row
    
    # Determine number of columns from quantity or rate row
    num_cols = 0
    if 'quantity' in field_rows:
        num_cols = len(field_rows['quantity'])
    elif 'rate' in field_rows:
        num_cols = len(field_rows['rate'])
    elif 'amount' in field_rows:
        num_cols = len(field_rows['amount'])
    
    if num_cols == 0:
        return []
    
    print(f"    Transposed table: {num_cols} items (columns), fields: {list(field_rows.keys())}")
    
    # Extract each column as an item
    for col_idx in range(num_cols):
        item = {
            'description': None,
            'hsn': None,
            'quantity': None,
            'unitPrice': None,
            'taxableValue': None
        }
        
        # Extract description from candidate rows (match by column position)
        if desc_candidates and col_idx < len(desc_candidates):
            # Get tokens from description row that align with this column
            desc_row = desc_candidates[col_idx] if col_idx < len(desc_candidates) else desc_candidates[0]
            if col_idx < len(desc_row):
                desc_text = desc_row[col_idx]['text']
                # Clean up description
                desc_text = re.sub(r'\b(State Name|GSTIN|Buyer|Bill to|Ram Krishna Path|M/s)\b.*', '', desc_text, flags=re.I)
                item['description'] = desc_text.strip() if desc_text.strip() else None
        
        # Extract quantity
        if 'quantity' in field_rows and col_idx < len(field_rows['quantity']):
            qty_text = field_rows['quantity'][col_idx]['text']
            item['quantity'] = qty_text
        
        # Extract rate (unit price)
        if 'rate' in field_rows and col_idx < len(field_rows['rate']):
            rate_text = field_rows['rate'][col_idx]['text']
            item['unitPrice'] = normalize_amount(rate_text)
        
        # Extract amount (taxable value)
        if 'amount' in field_rows and col_idx < len(field_rows['amount']):
            amt_text = field_rows['amount'][col_idx]['text']
            item['taxableValue'] = normalize_amount(amt_text)
        
        # Extract HSN
        if 'hsn' in field_rows and col_idx < len(field_rows['hsn']):
            hsn_text = field_rows['hsn'][col_idx]['text']
            m = re.search(r'(\d{4,8})', hsn_text)
            item['hsn'] = m.group(1) if m else None
        
        # Only add if has amount or rate
        if item['taxableValue'] or item['unitPrice']:
            items.append(item)
    
    return items


def is_transposed_table(rows, start_idx, end_idx):
    """
    Check if table is transposed (items as columns instead of rows).
    Look for consistent column positions across multiple rows with different field types.
    """
    if end_idx - start_idx < 3:
        return False
    
    # Get column positions from rows with 3+ tokens (look further ahead)
    col_positions = []
    for row in rows[start_idx:min(start_idx + 15, end_idx)]:
        if len(row) >= 3:
            lefts = [t['left'] for t in row]
            col_positions.append(lefts)
            # Stop after finding 5 multi-token rows
            if len(col_positions) >= 5:
                break
    
    if len(col_positions) < 2:
        return False
    
    # Check if column positions are consistent (within 20px)
    first_cols = col_positions[0]
    matches_found = 0
    for cols in col_positions[1:]:
        if len(cols) != len(first_cols):
            continue
        # Check if positions match
        matches = sum(1 for a, b in zip(first_cols, cols) if abs(a - b) < 20)
        if matches >= len(first_cols) * 0.8:  # 80% match
            matches_found += 1
    
    # Require at least 2 matching rows
    return matches_found >= 2


# ---------------- Parse table rows using header ----------------
def parse_table(rows, header_idx, start_parse_idx):
    """
    Parse table rows with multi-row item merging.
    - header_idx: row to use for computing column bounds
    - start_parse_idx: row to start parsing from
    """
    items = []
    header_row = rows[header_idx]
    bounds = compute_bounds(header_row)
    
    # Check if table is transposed (items as columns)
    is_transposed = is_transposed_table(rows, start_parse_idx, min(start_parse_idx + 20, len(rows)))
    print(f"  Transposed table check: {is_transposed}")
    if is_transposed:
        print(f"  ⚠ Detected transposed table (items as columns)")
        return parse_transposed_table(rows, start_parse_idx, bounds)
    
    # Buffer for multi-row items
    pending_desc_rows = []
    
    for row in rows[start_parse_idx:]:
        line_text = " ".join(t["text"].lower() for t in row)
        if re.search(r"\b(total|sub total|amount chargeable|round off|tax amount)\b", line_text, re.IGNORECASE):
            break
        
        cols = assign_cols(row, bounds)
        
        # Find amount (last numeric column)
        amount = None
        amount_idx = None
        for idx in range(len(cols) - 1, -1, -1):
            a = extract_amount_from_col(cols[idx])
            if a is not None:
                amount = a
                amount_idx = idx
                break
        
        # If no amount found, buffer this row as potential description
        if amount is None:
            # Only buffer if row has text content
            row_text = " ".join(t["text"] for t in row).strip()
            if row_text and not re.match(r"^\d+$", row_text):  # Not just a number
                pending_desc_rows.append(row)
            continue
        
        # Unit price (column before amount)
        unit_price = extract_amount_from_col(cols[amount_idx - 1]) if amount_idx and amount_idx - 1 >= 0 else None
        
        # Quantity search (prefer explicit units, skip HSN-like codes)
        qty = None
        qty_candidates = []
        for c in cols:
            ct = col_text(c)
            qm = re.search(r"(\d{1,6})\s*(pcs|bag|kg|nos|pieces|units?)", ct, re.IGNORECASE)
            if qm:
                # Prioritize quantities with explicit units
                has_unit = qm.group(2) is not None
                qty_candidates.append((qm.group(1) + (" " + (qm.group(2) or "PCS")).strip(), has_unit))
        
        # Pick quantity with unit if available, otherwise first match
        if qty_candidates:
            qty_candidates.sort(key=lambda x: x[1], reverse=True)  # Sort by has_unit
            qty = qty_candidates[0][0].strip()
            # Ensure space before unit
            qty = re.sub(r"(\d)([A-Za-z])", r"\1 \2", qty)
        
        # Description: merge pending rows + current row's leftmost columns
        desc_parts = []
        
        # Add buffered description rows
        if pending_desc_rows:
            print(f"    Merging {len(pending_desc_rows)} pending description rows")
        for pending_row in pending_desc_rows:
            pending_text = " ".join(t["text"] for t in pending_row).strip()
            # Clean up row numbers like "1 DESCRIPTION"
            pending_text = re.sub(r"^\d+\s+", "", pending_text)
            if pending_text:
                desc_parts.append(pending_text)
                print(f"      Added: {pending_text}")
        
        # Add description from current row (leftmost columns until numeric)
        numeric_col_idx = None
        for i, c in enumerate(cols):
            if extract_amount_from_col(c) is not None or re.search(r"\d{4,8}", col_text(c)):
                numeric_col_idx = i
                break
        
        last_desc_idx = numeric_col_idx if numeric_col_idx is not None else len(cols)
        for i in range(0, last_desc_idx):
            txt = col_text(cols[i])
            if txt and not re.match(r"^\d+$", txt):  # Skip pure numbers
                desc_parts.append(txt)
        
        description = " ".join(desc_parts).strip()
        
        # Clear buffer after using it
        pending_desc_rows = []
        
        # HSN
        hsn = None
        for c in cols:
            m = re.search(r"\b(\d{4,8})\b", col_text(c))
            if m:
                hsn = m.group(1)
                break
        
        item = {
            "description": description or None,
            "hsn": hsn,
            "quantity": qty,
            "unitPrice": unit_price,
            "taxableValue": amount
        }
        items.append(item)
    
    return items


# ---------------- Fallback line parser if header missing ----------------
def parse_items_fallback(rows):
    lines = [" ".join(t["text"] for t in r).strip() for r in rows if r]
    filtered = [ln for ln in lines if len(ln) > 1]
    items = []
    i = 0
    
    while i < len(filtered):
        ln = filtered[i]
        if re.search(r"\b(Sub\s*Total|Total|Round Off|Amount Chargeable|Tax Amount)\b", ln, re.IGNORECASE):
            break
        
        # Attempt single-line parse
        it = parse_item_from_line(ln)
        if it:
            items.append(it)
            i += 1
            continue
        
        # Merge with next line(s)
        merged = ln
        j = 1
        merged_item = None
        while j <= 2 and i + j < len(filtered):
            merged = merged + " " + filtered[i + j]
            merged_item = parse_item_from_line(merged)
            if merged_item:
                items.append(merged_item)
                break
            j += 1
        
        if merged_item:
            i += j
            continue
        i += 1
    
    return items


def parse_item_from_line(s):
    s = s.replace("₹", " ").replace(",", " ")
    qty_m = re.search(r"(\d{1,6})\s*(PCS|Bag|KG|Nos|Pcs|pcs)?\b", s, re.IGNORECASE)
    amounts = re.findall(r"([0-9]+\.[0-9]{2})", s)
    hsn_m = re.search(r"\b(\d{4,8})\b", s)
    
    if amounts and qty_m:
        taxable = amounts[-1]
        up = amounts[-2] if len(amounts) >= 2 else None
        desc = s
        desc = re.sub(re.escape(taxable), '', desc)
        if up:
            desc = re.sub(re.escape(up), '', desc)
        desc = re.sub(qty_m.group(0), '', desc)
        desc = re.sub(r"\s{2,}", " ", desc).strip()
        
        item = {
            "description": desc or None,
            "hsn": hsn_m.group(1) if hsn_m else None,
            "quantity": qty_m.group(1) + (" " + (qty_m.group(2) or "")).strip(),
            "unitPrice": normalize_amount(up) if up else None,
            "taxableValue": normalize_amount(taxable)
        }
        
        gst_m = re.search(r"@?\s*([0-9]{1,2}(?:\.[0-9])?)\s*%", s)
        if gst_m:
            item["gstRatePct"] = float(gst_m.group(1))
        return item
    return None


# ---------------- Extract totals from bottom lines ----------------
def extract_totals(rows):
    bottom_lines = [" ".join(t["text"] for t in r) for r in rows[-14:]]
    bt = "\n".join(bottom_lines)
    out = {}
    
    m = re.search(r"Sub\s*Total\s*[:\s]*₹?\s*([0-9\.,]+)", bt, re.IGNORECASE)
    out['subTotal'] = normalize_amount(m.group(1)) if m else None
    
    m = re.search(r"CGST@?[\d\.]*%?\s*[:\s]*₹?\s*([0-9\.,]+)", bt, re.IGNORECASE)
    out['cgst'] = normalize_amount(m.group(1)) if m else None
    
    m = re.search(r"SGST@?[\d\.]*%?\s*[:\s]*₹?\s*([0-9\.,]+)", bt, re.IGNORECASE)
    out['sgst'] = normalize_amount(m.group(1)) if m else None
    
    m = re.search(r"Round\s*Off\s*[:\s\-]*₹?\s*([0-9\.]+)", bt, re.IGNORECASE)
    out['roundOff'] = normalize_amount(m.group(1)) if m else 0.0
    
    # Match "Total" but not "Sub Total"
    m = re.search(r"(?<!Sub\s)Total\s*[:\s]*₹?\s*([0-9\.,]+)", bt, re.IGNORECASE)
    out['totalAmount'] = normalize_amount(m.group(1)) if m else None
    
    m = re.search(r"Total\s+([0-9]+\s*(?:PCS|Bag|KG|Nos)?)", bt, re.IGNORECASE)
    out['totalQty'] = m.group(1) if m else None
    
    m = re.search(r"(Amount Chargeable \(in words\)|Invoice Amount In Words)(?:[:\s\n-]*)\s*(.+?)(?:\n|$)", bt, re.IGNORECASE | re.DOTALL)
    out['totalInWords'] = m.group(2).strip() if m else None
    
    return out


# ---------------- Post-processor to fix common mapping errors ----------------
def clean_description(s):
    """Remove header/footer noise from descriptions."""
    if not s:
        return None
    # Remove common header/footer patterns
    s = re.sub(r'\b(HSN/SAC|Invoice No\.?|Tax Invoice|This is a Computer Generated Invoice|continued to page number|E\.&\s*O\.E|GSTIN|Amount Chargeable)\b.*', '', s, flags=re.I)
    s = re.sub(r'Invoice No\.?\s*[:\-]?\s*\w+', '', s, flags=re.I)
    s = re.sub(r'\s{2,}', ' ', s).strip()
    # Drop isolated short tokens
    parts = [p.strip() for p in re.split(r'[\n\r]+| {2,}', s) if p.strip()]
    return ' '.join(parts) if parts else None


def try_fix_unit_tax(item):
    """Fix swapped unitPrice/taxableValue using sanity checks."""
    up = normalize_amount(item.get('unitPrice'))
    tx = normalize_amount(item.get('taxableValue'))
    qty = 0
    if item.get('quantity'):
        m = re.search(r'(\d+)', str(item['quantity']))
        qty = int(m.group(1)) if m else 0
    
    # If unitPrice missing and taxable present & qty -> compute unit price
    if (not up or up == 0) and tx and qty > 0:
        item['unitPrice'] = round(tx / qty, 2)
        return item
    
    # If both present but unitPrice * qty ≈ taxable -> ok
    if up and tx and qty > 0:
        if abs(up * qty - tx) / (tx + 1e-6) < 0.05:
            return item
    
    # If unitPrice > taxable * 2 and qty>0 -> likely swapped
    if up and tx and qty > 0 and up > tx * 2:
        item['unitPrice'], item['taxableValue'] = tx, up
        return item
    
    return item


def recompute_totals_from_items(result):
    """Recompute totals from items if totalAmount is implausible."""
    total_taxable = 0.0
    total_qty = 0
    for it in result.get('items', []):
        tv = normalize_amount(it.get('taxableValue'))
        if tv:
            total_taxable += tv
        q = it.get('quantity')
        if q:
            mm = re.search(r'(\d+)', str(q))
            total_qty += int(mm.group(1)) if mm else 0
    
    totals = result.get('totals', {})
    if total_taxable > 0 and (not totals.get('totalAmount') or totals.get('totalAmount') < 100):
        totals['totalAmount'] = round(total_taxable, 2)
    if total_qty > 0 and not totals.get('totalQty'):
        totals['totalQty'] = f"{total_qty} PCS"
    result['totals'] = totals
    return result


def postprocess_extracted(result: Dict[str, Any], fullText: List[Dict] = None) -> Dict[str, Any]:
    """
    Post-process extracted data to fix common mapping errors:
    - Clean descriptions (remove header/footer bleed)
    - Normalize amounts
    - Swap unitPrice/taxableValue if reversed
    - Recompute totals if obviously wrong
    - Clean invoice header fields
    """
    # Normalize invoice header - reject single-word invoice numbers
    inv = result.get('invoice', {})
    if inv.get('invoiceNumber') and not re.search(r'\d', inv['invoiceNumber']):
        inv['invoiceNumber'] = None
    for k in ['invoiceDate', 'referenceNo', 'referenceDate']:
        if inv.get(k) in ['', 'Dated', 'Date', 'No', 'Number', None]:
            inv[k] = None
    
    # Normalize seller/buyer names
    if result.get('seller', {}).get('name'):
        result['seller']['name'] = re.sub(r'\s{2,}', ' ', result['seller']['name']).strip()
    if result.get('buyer', {}).get('name'):
        result['buyer']['name'] = re.sub(r'\s{2,}', ' ', result['buyer']['name']).strip()
    
    # Fix items - use dedicated functions
    clean_items = []
    for it in result.get('items', []):
        # Clean description
        orig_desc = it.get('description')
        it['description'] = clean_description(orig_desc or '')
        
        # Fix unit/tax swap
        it = try_fix_unit_tax(it)
        
        # Clean HSN
        hsn = it.get('hsn')
        if hsn and isinstance(hsn, str):
            m = re.search(r'(\d{4,8})', hsn)
            it['hsn'] = m.group(1) if m else None
        
        # Keep item even if description is None (as long as it has other data)
        if it.get('taxableValue') or it.get('unitPrice') or it.get('hsn'):
            clean_items.append(it)
    
    result['items'] = clean_items
    
    print(f"  Post-processor: {len(clean_items)} items after cleaning")
    
    # Recompute totals from items
    result = recompute_totals_from_items(result)
    
    # If totalAmount still < 50, likely parsed wrong (e.g., '17' from '17 PCS')
    if result['totals'].get('totalAmount') and result['totals']['totalAmount'] < 50:
        result = recompute_totals_from_items(result)
    
    result['invoice'] = inv
    return result


# ---------------- Main extraction function ----------------
def extract_invoice_structured(ocr_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point for invoice extraction.
    Uses geometry-based parsing with text heuristics fallback.
    """
    fullText = ocr_json.get("fullText", [])
    tokens = tokens_from_fulltext(fullText)
    rows = group_rows(tokens, y_tol=16.0)  # Tune for mobile photos
    
    # Debug: show first 15 rows
    print(f"\n=== Invoice Extractor Debug ===")
    print(f"Total tokens: {len(tokens)}, Total rows: {len(rows)}")
    
    # Only print detailed rows if explicitly debugging (check env var or config)
    import os
    if os.getenv('DEBUG_INVOICE_PARSER', '').lower() in ('1', 'true', 'yes'):
        print(f"\nFirst 30 rows (with geometry):")
        for i, row in enumerate(rows[:30]):
            lefts = [f"{t['left']:.0f}" for t in row[:6]]
            med_y = median([t['cy'] for t in row]) if row else 0
            row_text = " ".join(t["text"] for t in row)
            print(f"  Row {i:2d} y={med_y:4.0f} lefts=[{','.join(lefts)}] | {row_text[:100]}")
    
    header_result = find_header_soft(rows)
    header_idx, start_parse_idx = header_result if isinstance(header_result, tuple) else (header_result, None)
    items = []
    
    if header_idx is not None and start_parse_idx is not None:
        print(f"\n✓ Using row {header_idx} for column bounds, parsing from row {start_parse_idx}")
        header_text = " ".join(t["text"] for t in rows[header_idx])
        print(f"  Header: {header_text}")
        items = parse_table(rows, header_idx, start_parse_idx)
        print(f"  Table parser returned {len(items)} items")
    else:
        print(f"\n❌ Header detection failed (header_idx={header_idx}, start_parse_idx={start_parse_idx})")
    
    if not items:
        print("\n⚠ No items from header parser, using fallback...")
        items = parse_items_fallback(rows)
        print(f"  Fallback parser returned {len(items)} items")
    
    print(f"\n✓ Extracted {len(items)} items (before post-processing)")
    for i, item in enumerate(items[:5], 1):
        desc = item.get('description') or 'N/A'
        desc_preview = desc[:50] if isinstance(desc, str) else str(desc)
        print(f"  {i}. {desc_preview}")
        print(f"      HSN: {item.get('hsn')}, Qty: {item.get('quantity')}, Rate: ₹{item.get('unitPrice')}, Taxable: ₹{item.get('taxableValue')}")
    
    # Build seller/buyer from top/middle blocks
    # Use only page 0 tokens for cleaner extraction
    page_0_rows = [r for r in rows if all(t.get("page", 0) == 0 for t in r)]
    if not page_0_rows:
        page_0_rows = rows  # Fallback if no page info
    
    # Top: first 5 rows (seller info)
    # Mid: rows 5-20 (buyer info + table header)
    # Bottom: last 14 rows (totals)
    top = "\n".join(" ".join(t["text"] for t in r) for r in page_0_rows[:5])
    mid = "\n".join(" ".join(t["text"] for t in r) for r in page_0_rows[5:min(25, len(page_0_rows))])
    bottom = "\n".join(" ".join(t["text"] for t in r) for r in rows[-14:])
    
    seller = {}
    # Look for M/s or For: pattern, but extract only the name part
    m = re.search(r"(?:M\/s|For\s*:?)\s*([A-Za-z0-9 &\.\-]{3,50})", top, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        # Clean up - stop at newline or next label
        name = name.split('\n')[0].split('Invoice')[0].split('Dated')[0].strip()
        seller["name"] = name
    
    # First GSTIN is usually seller
    gst = re.search(r"GSTIN[^A-Z0-9]*([A-Z0-9]{15})", top, re.IGNORECASE)
    if gst:
        seller["gstin"] = gst.group(1)
    
    buyer = {}
    # Look for "Bill To" or "Buyer" section
    mm = re.search(r"(?:Bill\s*To|Buyer\s*\(Bill\s*to\))[\s:\-]*(.{10,500}?)(?:Invoice\s*No|HSN|Description\s*of\s*Goods|#\s*Item)", mid, re.IGNORECASE | re.DOTALL)
    if mm:
        block = mm.group(1).strip()
        # Extract first line as name
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if lines:
            # First meaningful line is usually the name
            buyer["name"] = lines[0]
        
        # Find GSTIN in buyer block (try multiple patterns)
        g = re.search(r"GSTIN(?:\s*Number)?[^A-Z0-9]*([A-Z0-9]{15})", block, re.IGNORECASE)
        if g:
            buyer["gstin"] = g.group(1)
        
        # Find contact
        ph = re.search(r"(\+?\d[\d\-\s]{8,})", block)
        if ph:
            buyer["contact"] = ph.group(1).strip()
    else:
        # Fallback: find second GSTIN
        all_gsts = re.findall(r"GSTIN[^A-Z0-9]*([A-Z0-9]{15})", top + mid, re.IGNORECASE)
        if len(all_gsts) > 1:
            buyer["gstin"] = all_gsts[1]
    
    totals = extract_totals(rows)
    print(f"\n✓ Totals (before post-processing): SubTotal={totals.get('subTotal')}, Total={totals.get('totalAmount')}, Qty={totals.get('totalQty')}")
    
    # Invoice header fields from top
    inv = {
        "invoiceNumber": None,
        "invoiceDate": None,
        "placeOfSupply": None,
        "referenceNo": None,
        "referenceDate": None,
        "irn": None,
        "acknowledgement": None
    }
    
    # Invoice number - stricter pattern (requires digits, rejects plain words)
    m = re.search(
        r"(?:Invoice\s*(?:No\.?|Number|#)\s*[:\-\s]*)?([A-Z0-9]{2,}\d{1,}[A-Z0-9\-\/]*)",
        top + mid, re.IGNORECASE
    )
    if m:
        candidate = m.group(1).strip()
        # Allow only if contains digits and is not a plain word
        if re.search(r'\d', candidate) and len(candidate) > 2:
            # Reject common false positives
            if candidate.lower() not in ["dated", "date", "no", "number", "delivery"]:
                inv["invoiceNumber"] = candidate
        else:
            inv["invoiceNumber"] = None
    
    # Invoice date - robust patterns (handles multiple formats)
    date_pat = r"([0-9]{1,2}[\/\-\s][0-9]{1,2}[\/\-\s][0-9]{2,4}|[0-9]{1,2}[- ](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[- ]\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})"
    m2 = re.search(r"(?:Dated|Date|Dt\.?)\s*[:\-]?\s*" + date_pat, top + mid, re.IGNORECASE)
    if m2:
        inv["invoiceDate"] = m2.group(1).strip()
    
    pos = re.search(r"Place\s+of\s+Supply\s*[:\.\-]?\s*([^\n\r]+)", top, re.IGNORECASE)
    if pos:
        inv["placeOfSupply"] = pos.group(1).strip()
    
    ref = re.search(r"Reference\s*No\.?\s*[:\.\-]?\s*([A-Za-z0-9\/\-]+)", top + mid, re.IGNORECASE)
    if ref:
        inv["referenceNo"] = ref.group(1)
    
    # Final assembly
    out = {
        "invoice": inv,
        "seller": seller,
        "buyer": buyer,
        "items": items,
        "totals": totals,
        "meta": {
            "documentType": "Tax Invoice" if "Tax Invoice" in top + mid + bottom else "Invoice",
            "isComputerGenerated": "Computer Generated" in top + mid + bottom or "This is a Computer Generated Invoice" in top + mid + bottom,
            "authorisedSignatory": None
        }
    }
    
    # Apply post-processing to clean up common mapping errors
    out = postprocess_extracted(out, fullText)
    
    return out
