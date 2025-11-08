#!/usr/bin/env python3
"""
Test with Sale_297_20-08-2025.pdf example data.
"""
from src.services.invoice_transformer import transform_invoice

# Simulated OCR response for Sale_297_20-08-2025.pdf
sale_297_response = {
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

print("=" * 70)
print("Testing Sale_297_20-08-2025.pdf Extraction")
print("=" * 70)

result = transform_invoice(sale_297_response)

print("\n📄 Invoice Header:")
print(f"   Invoice Number: {result['invoice'].get('invoiceNumber')}")
print(f"   Invoice Date: {result['invoice'].get('invoiceDate')}")
print(f"   Place of Supply: {result['invoice'].get('placeOfSupply')}")

print("\n🏢 Seller:")
print(f"   Name: {result['seller'].get('name')}")
print(f"   GSTIN: {result['seller'].get('gstin')}")
print(f"   State: {result['seller'].get('state')}")

print("\n👤 Buyer:")
print(f"   Name: {result['buyer'].get('name')}")
print(f"   GSTIN: {result['buyer'].get('gstin')}")
print(f"   Contact: {result['buyer'].get('contact')}")

print("\n📦 Items:")
for idx, item in enumerate(result['items'], 1):
    print(f"   {idx}. {item.get('description')}")
    print(f"      HSN: {item.get('hsn')}")
    print(f"      Qty: {item.get('quantity')}")
    print(f"      Rate: ₹{item.get('unitPrice')}")
    print(f"      Taxable Value: ₹{item.get('taxableValue')}")
    print(f"      GST: {item.get('gstRate')}%")

print("\n💰 Totals:")
print(f"   Sub Total: ₹{result['totals'].get('subTotal')}")
print(f"   SGST: ₹{result['totals'].get('sgst')}")
print(f"   CGST: ₹{result['totals'].get('cgst')}")
print(f"   Round Off: ₹{result['totals'].get('roundOff')}")
print(f"   Total Amount: ₹{result['totals'].get('totalAmount')}")
print(f"   Total Qty: {result['totals'].get('totalQty')}")
print(f"   In Words: {result['totals'].get('totalInWords')}")

print("\n" + "=" * 70)
print("Expected vs Actual:")
print("=" * 70)
print(f"Invoice Number: Expected='297', Actual='{result['invoice'].get('invoiceNumber')}'")
print(f"Invoice Date: Expected='20-08-2025', Actual='{result['invoice'].get('invoiceDate')}'")
print(f"Total Amount: Expected='41146.00', Actual='{result['totals'].get('totalAmount')}'")
print(f"Items Count: Expected='1', Actual='{len(result['items'])}'")

if result['invoice'].get('invoiceNumber') == '297':
    print("\n✅ Invoice number extraction: PASS")
else:
    print("\n❌ Invoice number extraction: FAIL")

if result['invoice'].get('invoiceDate') == '20-08-2025':
    print("✅ Invoice date extraction: PASS")
else:
    print("❌ Invoice date extraction: FAIL")

if result['totals'].get('totalAmount') == 41146.00:
    print("✅ Total amount extraction: PASS")
else:
    print("❌ Total amount extraction: FAIL")

print("\n" + "=" * 70)
