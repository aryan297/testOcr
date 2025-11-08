#!/usr/bin/env python3
"""
Test spatial parser with bounding box geometry.
"""
from src.services.spatial_parser import (
    tokens_from_fulltext,
    group_tokens_into_rows,
    find_header_row,
    parse_ocr_fulltext
)

# Sample OCR response with bounding boxes
sample_ocr = {
    'fullText': [
        # Header area
        {'text': 'Invoice No.: 297', 'bbox': [[100, 50], [250, 50], [250, 70], [100, 70]], 'confidence': 0.95},
        {'text': 'Date: 20-08-2025', 'bbox': [[300, 50], [450, 50], [450, 70], [300, 70]], 'confidence': 0.93},
        
        # Seller area
        {'text': 'For: RANG MAHAL', 'bbox': [[100, 100], [300, 100], [300, 120], [100, 120]], 'confidence': 0.96},
        {'text': 'GSTIN: 10CKXPK7984A1ZV', 'bbox': [[100, 130], [350, 130], [350, 150], [100, 150]], 'confidence': 0.94},
        
        # Buyer area
        {'text': 'Bill To', 'bbox': [[100, 180], [180, 180], [180, 200], [100, 200]], 'confidence': 0.97},
        {'text': 'SHREE RAM IRON', 'bbox': [[100, 210], [280, 210], [280, 230], [100, 230]], 'confidence': 0.95},
        {'text': 'GSTIN Number: 10FVYPK2595A1ZG', 'bbox': [[100, 240], [400, 240], [400, 260], [100, 260]], 'confidence': 0.93},
        {'text': 'Contact No: +917779886449', 'bbox': [[100, 270], [350, 270], [350, 290], [100, 290]], 'confidence': 0.92},
        
        # Table header
        {'text': '#', 'bbox': [[100, 320], [120, 320], [120, 340], [100, 340]], 'confidence': 0.98},
        {'text': 'Item name', 'bbox': [[130, 320], [250, 320], [250, 340], [130, 340]], 'confidence': 0.96},
        {'text': 'HSN', 'bbox': [[260, 320], [320, 320], [320, 340], [260, 340]], 'confidence': 0.97},
        {'text': 'Quantity', 'bbox': [[330, 320], [420, 320], [420, 340], [330, 340]], 'confidence': 0.95},
        {'text': 'Unit Price', 'bbox': [[430, 320], [530, 320], [530, 340], [430, 340]], 'confidence': 0.94},
        {'text': 'Amount', 'bbox': [[540, 320], [620, 320], [620, 340], [540, 340]], 'confidence': 0.96},
        
        # Item row
        {'text': '1', 'bbox': [[100, 350], [120, 350], [120, 370], [100, 370]], 'confidence': 0.99},
        {'text': 'NATURAL GYPSUM CALCINED PLASTER', 'bbox': [[130, 350], [380, 350], [380, 370], [130, 370]], 'confidence': 0.93},
        {'text': '2520', 'bbox': [[260, 350], [310, 350], [310, 370], [260, 370]], 'confidence': 0.97},
        {'text': '149 Bag', 'bbox': [[330, 350], [400, 350], [400, 370], [330, 370]], 'confidence': 0.94},
        {'text': '₹ 263.00', 'bbox': [[430, 350], [510, 350], [510, 370], [430, 370]], 'confidence': 0.95},
        {'text': '₹ 39,187.00', 'bbox': [[540, 350], [640, 350], [640, 370], [540, 370]], 'confidence': 0.96},
        {'text': '(5.0%)', 'bbox': [[650, 350], [700, 350], [700, 370], [650, 370]], 'confidence': 0.92},
        
        # Totals area
        {'text': 'Sub Total ₹ 39,187.00', 'bbox': [[100, 420], [350, 420], [350, 440], [100, 440]], 'confidence': 0.94},
        {'text': 'SGST@2.5% ₹ 979.68', 'bbox': [[100, 450], [300, 450], [300, 470], [100, 470]], 'confidence': 0.93},
        {'text': 'CGST@2.5% ₹ 979.68', 'bbox': [[100, 480], [300, 480], [300, 500], [100, 500]], 'confidence': 0.93},
        {'text': 'Round off - ₹ 0.35', 'bbox': [[100, 510], [280, 510], [280, 530], [100, 530]], 'confidence': 0.91},
        {'text': 'Total ₹ 41,146.00', 'bbox': [[100, 540], [300, 540], [300, 560], [100, 560]], 'confidence': 0.95},
        {'text': 'Invoice Amount In Words', 'bbox': [[100, 580], [350, 580], [350, 600], [100, 600]], 'confidence': 0.94},
        {'text': 'Forty One Thousand One Hundred and Forty Six Rupees only', 'bbox': [[100, 610], [600, 610], [600, 630], [100, 630]], 'confidence': 0.92},
    ]
}

print("=" * 70)
print("Testing Spatial Parser (Bounding Box Geometry)")
print("=" * 70)

# Test 1: Token extraction
print("\n1. Token Extraction:")
tokens = tokens_from_fulltext(sample_ocr['fullText'])
print(f"   Total tokens: {len(tokens)}")
print(f"   First token: {tokens[0]['text']} at ({tokens[0]['cx']:.1f}, {tokens[0]['cy']:.1f})")

# Test 2: Row grouping
print("\n2. Row Grouping:")
rows = group_tokens_into_rows(tokens, y_tol=14.0)
print(f"   Total rows: {len(rows)}")
for i, row in enumerate(rows[:5]):
    print(f"   Row {i}: {' '.join(t['text'] for t in row)}")

# Test 3: Header detection
print("\n3. Header Detection:")
header_idx = find_header_row(rows)
if header_idx is not None:
    print(f"   Header found at row {header_idx}")
    print(f"   Header text: {' '.join(t['text'] for t in rows[header_idx])}")
else:
    print("   ❌ Header not found")

# Test 4: Full parsing
print("\n4. Full Parsing:")
result = parse_ocr_fulltext(sample_ocr)

print(f"\n📄 Invoice:")
print(f"   Number: {result['invoice'].get('invoiceNumber')}")
print(f"   Date: {result['invoice'].get('invoiceDate')}")

print(f"\n🏢 Seller:")
print(f"   Name: {result['seller'].get('name')}")
print(f"   GSTIN: {result['seller'].get('gstin')}")

print(f"\n👤 Buyer:")
print(f"   Name: {result['buyer'].get('name')}")
print(f"   GSTIN: {result['buyer'].get('gstin')}")
print(f"   Contact: {result['buyer'].get('contact')}")

print(f"\n📦 Items ({len(result['items'])}):")
for idx, item in enumerate(result['items'], 1):
    print(f"   {idx}. {item.get('description')}")
    print(f"      HSN: {item.get('hsn')}, Qty: {item.get('quantity')}")
    print(f"      Rate: ₹{item.get('unitPrice')}, Amount: ₹{item.get('taxableValue')}")
    print(f"      GST: {item.get('gstRate')}%")

print(f"\n💰 Totals:")
print(f"   Sub Total: ₹{result['totals'].get('subTotal')}")
print(f"   SGST: ₹{result['totals'].get('sgst')}")
print(f"   CGST: ₹{result['totals'].get('cgst')}")
print(f"   Round Off: ₹{result['totals'].get('roundOff')}")
print(f"   Total: ₹{result['totals'].get('totalAmount')}")

print("\n" + "=" * 70)
print("Validation:")
print("=" * 70)

# Validate results
checks = [
    ("Invoice Number", result['invoice'].get('invoiceNumber') == '297'),
    ("Invoice Date", result['invoice'].get('invoiceDate') == '20-08-2025'),
    ("Seller GSTIN", result['seller'].get('gstin') == '10CKXPK7984A1ZV'),
    ("Buyer GSTIN", result['buyer'].get('gstin') == '10FVYPK2595A1ZG'),
    ("Items Count", len(result['items']) >= 1),
    ("Total Amount", result['totals'].get('totalAmount') == 41146.00),
]

passed = sum(1 for _, check in checks if check)
total = len(checks)

for name, check in checks:
    status = "✅" if check else "❌"
    print(f"{status} {name}")

print(f"\n{'✅' if passed == total else '⚠️'} Passed {passed}/{total} checks")
print("=" * 70)
