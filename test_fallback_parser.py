#!/usr/bin/env python3
"""
Test fallback parser for invoices without clear headers.
"""
from src.services.spatial_parser import (
    parse_item_from_text_line,
    parse_items_fallback_by_lines,
    tokens_from_fulltext,
    group_tokens_into_rows
)

print("=" * 70)
print("Testing Fallback Parser (Line-by-Line Heuristics)")
print("=" * 70)

# Test 1: Single line parsing
print("\n1. Single Line Parsing:")
test_lines = [
    "1 NATURAL GYPSUM CALCINED PLASTER 2520 149 Bag 263.00 39187.00 (5.0%)",
    "HG 8341 48239019 2 PCS 755.00 1279.66",
    "White MT .072mm 48239019 13 PCS 365.00 4021.16",
    "Freight & Cartage Outward (Gst) 150.00",
]

for line in test_lines:
    item = parse_item_from_text_line(line)
    if item:
        print(f"   ✅ {line[:50]}...")
        print(f"      → {item['description']}: {item.get('quantity')} @ ₹{item.get('unitPrice')} = ₹{item.get('taxableValue')}")
    else:
        print(f"   ❌ {line[:50]}... (no match)")

# Test 2: Multi-line parsing
print("\n2. Multi-Line Parsing:")
sample_ocr = {
    'fullText': [
        {'text': 'Invoice No.: 297', 'bbox': [[100, 50], [250, 50], [250, 70], [100, 70]]},
        {'text': 'Date: 20-08-2025', 'bbox': [[300, 50], [450, 50], [450, 70], [300, 70]]},
        {'text': 'For: RANG MAHAL', 'bbox': [[100, 100], [300, 100], [300, 120], [100, 120]]},
        {'text': 'Bill To', 'bbox': [[100, 150], [180, 150], [180, 170], [100, 170]]},
        {'text': 'SHREE RAM IRON', 'bbox': [[100, 180], [280, 180], [280, 200], [100, 200]]},
        {'text': '1', 'bbox': [[100, 250], [120, 250], [120, 270], [100, 270]]},
        {'text': 'NATURAL GYPSUM CALCINED PLASTER', 'bbox': [[130, 250], [400, 250], [400, 270], [130, 270]]},
        {'text': '2520', 'bbox': [[100, 280], [150, 280], [150, 300], [100, 300]]},
        {'text': '149 Bag', 'bbox': [[200, 280], [280, 280], [280, 300], [200, 300]]},
        {'text': '263.00', 'bbox': [[300, 280], [370, 280], [370, 300], [300, 300]]},
        {'text': '39187.00', 'bbox': [[400, 280], [490, 280], [490, 300], [400, 300]]},
        {'text': '(5.0%)', 'bbox': [[500, 280], [560, 280], [560, 300], [500, 300]]},
        {'text': 'Sub Total 39187.00', 'bbox': [[100, 350], [300, 350], [300, 370], [100, 370]]},
        {'text': 'Total 41146.00', 'bbox': [[100, 400], [250, 400], [250, 420], [100, 420]]},
    ]
}

tokens = tokens_from_fulltext(sample_ocr['fullText'])
rows = group_tokens_into_rows(tokens, y_tol=14.0)
items = parse_items_fallback_by_lines(rows)

print(f"   Found {len(items)} items:")
for idx, item in enumerate(items, 1):
    print(f"   {idx}. {item.get('description')}")
    print(f"      HSN: {item.get('hsn')}, Qty: {item.get('quantity')}")
    print(f"      Rate: ₹{item.get('unitPrice')}, Amount: ₹{item.get('taxableValue')}")
    if item.get('gstRate'):
        print(f"      GST: {item.get('gstRate')}%")

# Test 3: Wrapped description (multi-line item)
print("\n3. Wrapped Description Test:")
wrapped_ocr = {
    'fullText': [
        {'text': 'Item 1:', 'bbox': [[100, 100], [150, 100], [150, 120], [100, 120]]},
        {'text': 'NATURAL GYPSUM', 'bbox': [[100, 130], [250, 130], [250, 150], [100, 150]]},
        {'text': 'CALCINED PLASTER', 'bbox': [[100, 160], [250, 160], [250, 180], [100, 180]]},
        {'text': '2520 149 Bag 263.00 39187.00', 'bbox': [[100, 190], [400, 190], [400, 210], [100, 210]]},
        {'text': 'Total', 'bbox': [[100, 250], [150, 250], [150, 270], [100, 270]]},
    ]
}

tokens2 = tokens_from_fulltext(wrapped_ocr['fullText'])
rows2 = group_tokens_into_rows(tokens2, y_tol=14.0)
items2 = parse_items_fallback_by_lines(rows2)

print(f"   Found {len(items2)} items:")
for idx, item in enumerate(items2, 1):
    print(f"   {idx}. {item.get('description')}")
    print(f"      Qty: {item.get('quantity')}, Amount: ₹{item.get('taxableValue')}")

print("\n" + "=" * 70)
print("Validation:")
print("=" * 70)

# Validate
checks = [
    ("Single line parsing", parse_item_from_text_line(test_lines[0]) is not None),
    ("Multi-line parsing", len(items) >= 1),
    ("Wrapped description", len(items2) >= 1),
    ("HSN extraction", items[0].get('hsn') == '2520' if items else False),
    ("Quantity extraction", '149' in (items[0].get('quantity') or '') if items else False),
    ("Amount extraction", items[0].get('taxableValue') == 39187.00 if items else False),
]

passed = sum(1 for _, check in checks if check)
total = len(checks)

for name, check in checks:
    status = "✅" if check else "❌"
    print(f"{status} {name}")

print(f"\n{'✅' if passed == total else '⚠️'} Passed {passed}/{total} checks")
print("=" * 70)
