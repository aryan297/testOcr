#!/usr/bin/env python3
"""
Minimal debug script to diagnose invoice parsing failures.
Shows: rows, header detection, column bounds, item candidates.
"""
import json
import re
from statistics import median

# Embedded test data from Sale_297
ocr_data = {
    'fullText': [
        {'text': 'Invoice No.: 297', 'bbox': [[100, 50], [200, 50], [200, 70], [100, 70]]},
        {'text': 'Date: 20-08-2025', 'bbox': [[100, 80], [200, 80], [200, 100], [100, 100]]},
        {'text': 'For: RANG MAHAL', 'bbox': [[100, 120], [250, 120], [250, 140], [100, 140]]},
        {'text': 'SHASTRI NAGAR MADHEPURA MADHEPURA', 'bbox': [[100, 150], [350, 150], [350, 170], [100, 170]]},
        {'text': 'GSTIN: 10CKXPK7984A1ZV', 'bbox': [[100, 180], [280, 180], [280, 200], [100, 200]]},
        {'text': 'Bill To', 'bbox': [[100, 220], [150, 220], [150, 240], [100, 240]]},
        {'text': 'SHREE RAM IRON', 'bbox': [[100, 250], [220, 250], [220, 270], [100, 270]]},
        {'text': 'RAHUL KUMAR, S/O RAJESH KUMAR', 'bbox': [[100, 280], [320, 280], [320, 300], [100, 300]]},
        {'text': 'AGRAWAL WARD NO-20, SUBHASH CHOWK, MADHEPURA', 'bbox': [[100, 310], [400, 310], [400, 330], [100, 330]]},
        {'text': 'Contact No: +917779886449', 'bbox': [[100, 340], [280, 340], [280, 360], [100, 360]]},
        {'text': 'GSTIN Number: 10FVYPK2595A1ZG', 'bbox': [[100, 370], [320, 370], [320, 390], [100, 390]]},
        {'text': '# Item name', 'bbox': [[100, 420], [200, 420], [200, 440], [100, 440]]},
        {'text': '1 NATURAL GYPSUM CALCINED PLASTER', 'bbox': [[100, 450], [380, 450], [380, 470], [100, 470]]},
        {'text': '2520', 'bbox': [[100, 480], [150, 480], [150, 500], [100, 500]]},
        {'text': '149 Bag', 'bbox': [[200, 480], [270, 480], [270, 500], [200, 500]]},
        {'text': '₹ 263.00', 'bbox': [[300, 480], [380, 480], [380, 500], [300, 500]]},
        {'text': '₹ 39,187.00', 'bbox': [[400, 480], [500, 480], [500, 500], [400, 500]]},
        {'text': '(5.0%)', 'bbox': [[520, 480], [580, 480], [580, 500], [520, 500]]},
        {'text': 'Invoice Amount In Words', 'bbox': [[100, 530], [300, 530], [300, 550], [100, 550]]},
        {'text': 'Forty One Thousand One Hundred and Forty Six Rupees only', 'bbox': [[100, 560], [500, 560], [500, 580], [100, 580]]},
        {'text': 'Sub Total ₹ 39,187.00', 'bbox': [[100, 610], [280, 610], [280, 630], [100, 630]]},
        {'text': 'SGST@2.5% ₹ 979.68', 'bbox': [[100, 640], [250, 640], [250, 660], [100, 660]]},
        {'text': 'CGST@2.5% ₹ 979.68', 'bbox': [[100, 670], [250, 670], [250, 690], [100, 690]]},
        {'text': 'Round off - ₹ 0.35', 'bbox': [[100, 700], [230, 700], [230, 720], [100, 720]]},
        {'text': 'Total ₹ 41,146.00', 'bbox': [[100, 730], [250, 730], [250, 750], [100, 750]]},
        {'text': 'Total 149', 'bbox': [[100, 760], [180, 760], [180, 780], [100, 780]]},
    ]
}

fullText = ocr_data.get('fullText', [])

# --- Step 1: Tokenize with geometry ---
def bbox_center(bbox):
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (sum(xs)/len(xs), sum(ys)/len(ys))

def bbox_left(bbox):
    return min(p[0] for p in bbox)

tokens = []
for idx, b in enumerate(fullText):
    txt = b.get('text', '').strip()
    bbox = b.get('bbox')
    if not txt or not bbox:
        continue
    cx, cy = bbox_center(bbox)
    tokens.append({
        'text': txt,
        'cx': cx,
        'cy': cy,
        'left': bbox_left(bbox),
        'bbox': bbox,
        'conf': b.get('conf', 1.0),
        'idx': idx
    })

# Detect page breaks
page_num = 0
prev_cy = -1
for t in tokens:
    if prev_cy > 0 and t['cy'] < prev_cy - 1000:
        page_num += 1
    t['page'] = page_num
    prev_cy = t['cy']

tokens.sort(key=lambda t: (t.get('page', 0), t['cy'], t['left']))

print(f"✓ Tokens: {len(tokens)}")
print(f"✓ Pages detected: {page_num + 1}")

# --- Step 2: Group into rows ---
def group_rows(tokens, y_tol=20.0):
    rows = []
    for t in tokens:
        if not rows:
            rows.append([t])
            continue
        med = median([x['cy'] for x in rows[-1]])
        if abs(t['cy'] - med) <= y_tol:
            rows[-1].append(t)
        else:
            rows.append([t])
    for r in rows:
        r.sort(key=lambda x: x['left'])
    return rows

rows = group_rows(tokens, y_tol=20.0)
print(f"✓ Rows: {len(rows)}\n")

# --- Step 3: Show first 40 rows with positions ---
print("=" * 80)
print("FIRST 40 ROWS (with left positions)")
print("=" * 80)
for i, row in enumerate(rows[:40]):
    lefts = [f"{t['left']:.0f}" for t in row[:6]]
    row_text = " ".join(t['text'] for t in row)
    print(f"Row {i:2d} | lefts:[{','.join(lefts)}] | {row_text[:70]}")

# --- Step 4: Header detection (soft) ---
print("\n" + "=" * 80)
print("HEADER DETECTION")
print("=" * 80)

HEADER_KEYWORDS = ["description", "hsn", "quantity", "qty", "rate", "amount", "unit price", "taxable"]

def find_header_soft(rows):
    # Strategy 1: keyword scoring
    for i, row in enumerate(rows[:30]):
        text = " ".join(t['text'].lower() for t in row)
        score = sum(1 for k in HEADER_KEYWORDS if k in text)
        if score >= 2:
            print(f"  ✓ Header found at row {i} (keyword score: {score})")
            print(f"    Text: {text}")
            return i
    
    # Strategy 2: anchor labels
    for i, row in enumerate(rows[:40]):
        text = " ".join(t['text'].lower() for t in row)
        if "description of goods" in text or "item name" in text:
            print(f"  ✓ Header found at row {i} (anchor match)")
            print(f"    Text: {text}")
            return i
    
    # Strategy 3: any HSN/Quantity/Rate
    for i, row in enumerate(rows[:50]):
        text = " ".join(t['text'].lower() for t in row)
        if "hsn" in text or "quantity" in text or "rate" in text:
            print(f"  ✓ Header found at row {i} (weak anchor)")
            print(f"    Text: {text}")
            return i
    
    print("  ✗ No header found!")
    return None

header_idx = find_header_soft(rows)

if header_idx is None:
    print("\n❌ FAILED: No header detected. Check rows above for header-like text.")
    exit(1)

# --- Step 5: Compute column bounds ---
print("\n" + "=" * 80)
print("COLUMN BOUNDS")
print("=" * 80)

def compute_safe_bounds(header_row, expand_px=12):
    xs = sorted(t['left'] for t in header_row)
    if not xs:
        return [(-1e6, 1e6)]
    
    print(f"  Header token lefts: {[f'{x:.0f}' for x in xs]}")
    
    mids = [(a + b) / 2.0 for a, b in zip(xs, xs[1:])]
    print(f"  Midpoints: {[f'{m:.0f}' for m in mids]}")
    
    bounds = []
    left = -1e6
    for m in mids:
        bounds.append((left - expand_px, m + expand_px))
        left = m
    bounds.append((left - expand_px, 1e6))
    
    # Merge tiny bounds
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
    
    print(f"  Final bounds (after merge): {[(f'{l:.0f}', f'{r:.0f}') for l, r in merged]}")
    return merged

header_row = rows[header_idx]
bounds = compute_safe_bounds(header_row)

# --- Step 6: Parse first 15 item candidates ---
print("\n" + "=" * 80)
print("ITEM CANDIDATES (first 15 rows after header)")
print("=" * 80)

def assign_cols(row, bounds):
    cols = [[] for _ in bounds]
    for t in row:
        cx = t['cx']
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
    return " ".join(t['text'] for t in col).strip()

def extract_amount_from_col(col):
    txt = col_text(col)
    # Require decimal or thousands grouping
    m = re.findall(r"\d{1,3}(?:,\d{3})*(?:\.\d{2})", txt)
    if not m:
        m = re.findall(r"\d+\.\d{2}", txt)
    if not m:
        return None
    return m[-1]

for row_idx, row in enumerate(rows[header_idx + 1:header_idx + 16], header_idx + 1):
    line_text = " ".join(t['text'].lower() for t in row)
    
    # Check for totals marker
    if re.search(r"\b(total|sub total|amount chargeable|round off|tax amount|invoice amount in words)\b", line_text, re.IGNORECASE):
        print(f"\nRow {row_idx:2d} | 🛑 TOTALS MARKER: {line_text[:60]}")
        break
    
    cols = assign_cols(row, bounds)
    
    # Find amount (rightmost numeric)
    amount = None
    amount_idx = None
    for idx in range(len(cols) - 1, -1, -1):
        a = extract_amount_from_col(cols[idx])
        if a is not None:
            amount = a
            amount_idx = idx
            break
    
    # Show columns
    col_texts = [col_text(c)[:15] for c in cols]
    print(f"\nRow {row_idx:2d} | Cols: {col_texts}")
    
    if amount:
        print(f"         | ✓ Amount found in col {amount_idx}: {amount}")
        
        # Unit price (col before amount)
        unit_price = extract_amount_from_col(cols[amount_idx - 1]) if amount_idx and amount_idx - 1 >= 0 else None
        if unit_price:
            print(f"         | ✓ Unit price in col {amount_idx - 1}: {unit_price}")
        
        # Quantity
        qty = None
        for i, c in enumerate(cols):
            ct = col_text(c)
            qm = re.search(r"(\d{1,6})\s*(pcs|bag|kg|nos|pieces)?", ct, re.IGNORECASE)
            if qm:
                qty = qm.group(1) + " " + (qm.group(2) or "PCS")
                print(f"         | ✓ Quantity in col {i}: {qty}")
                break
        
        # Description (leftmost non-numeric cols)
        desc_parts = []
        for i in range(0, amount_idx if amount_idx else len(cols)):
            txt = col_text(cols[i])
            if txt and not re.match(r"^\d+$", txt):
                desc_parts.append(txt)
        desc = " ".join(desc_parts).strip()
        if desc:
            print(f"         | ✓ Description: {desc[:50]}")
    else:
        print(f"         | ✗ No amount found (skipping)")

print("\n" + "=" * 80)
print("DEBUG COMPLETE")
print("=" * 80)
print("\nNext steps:")
print("1. If header_idx is wrong, adjust keyword list or search range")
print("2. If bounds look wrong, check header token positions")
print("3. If amounts aren't detected, check decimal format requirements")
print("4. If totals appear as items, verify totals-stop regex")
