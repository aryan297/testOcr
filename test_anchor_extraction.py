#!/usr/bin/env python3
"""
Test anchor-based extraction with sample invoice text.
"""
from src.services.invoice_transformer import (
    get_full_text_string,
    extract_invoice_header,
    extract_parties,
    parse_entity_block,
    extract_line_items,
    extract_totals_from_text
)

# Sample full text from the invoice
sample_text = """
M/s Tajpuria Sales
Unit of Shree Ram Sales LLP
Circle No-20A, Ward No-38 Koyal Kothi
Ram Krishna Path
Kadam Kuan
Patna-800003
GSTIN/UIN: 10ADAFS2028K1ZI
State Name : Bihar, Code : 10

Buyer (Bill to)
Shree Ram Iron(Madhepura)
RAHUL KUMAR, S/O RAJESH KUMAR
AGRAWAL, WARD NO-20, SUBHASH
CHOWK, MADHEPURA
MADHEPURA
GSTIN/UIN: 10FVYPK2595A1ZG
State Name : Bihar, Code : 10

Invoice No. TPS/25-26/3050
Dated 23-Oct-25
Ack Date : 24-Oct-25
Reference No. & Date. 3606 dt. 23-Oct-25

Description of Goods
1 HG 8341 48239019 2 PCS 755.00 1279.66
2 GLOSS 7204 48239019 2 PCS 514.00 871.18
3 White MT .072mm 48239019 13 PCS 365.00 4021.16
Freight & Cartage Outward (Gst) 150.00

Total ₹ 7,460.00 17 PCS

HSN/SAC Taxable Value CGST SGST Total
48239019 6,322.00 568.98 568.98 1,137.96
Total 6,322.00 568.98 568.98 1,137.96

Round Off 0.04

Amount Chargeable (in words)
INR Seven Thousand Four Hundred Sixty Only

Tax Amount (in words) : INR One Thousand One Hundred Thirty Seven and Ninety Six paise Only
"""

print("=" * 60)
print("Testing Anchor-Based Extraction")
print("=" * 60)

# Test 1: Invoice Header
print("\n1. Invoice Header:")
header = extract_invoice_header(sample_text)
print(f"   Invoice Number: {header.get('invoiceNumber')}")
print(f"   Invoice Date: {header.get('invoiceDate')}")
print(f"   Reference No: {header.get('referenceNo')}")
print(f"   Reference Date: {header.get('referenceDate')}")

# Test 2: Seller/Buyer Extraction
print("\n2. Seller/Buyer Extraction:")
seller_block, buyer_block = extract_parties(sample_text)
print(f"   Seller Block Length: {len(seller_block)} chars")
print(f"   Buyer Block Length: {len(buyer_block)} chars")

seller = parse_entity_block(seller_block, 'seller')
print(f"\n   Seller Name: {seller.get('name')}")
print(f"   Seller GSTIN: {seller.get('gstin')}")
print(f"   Seller State: {seller.get('state')}")
print(f"   Seller Unit: {seller.get('unit')}")

buyer = parse_entity_block(buyer_block, 'buyer')
print(f"\n   Buyer Name: {buyer.get('name')}")
print(f"   Buyer GSTIN: {buyer.get('gstin')}")
print(f"   Buyer Contact: {buyer.get('contact')}")

# Test 3: Line Items
print("\n3. Line Items:")
items = extract_line_items(sample_text)
print(f"   Total Items: {len(items)}")
for item in items:
    print(f"   - {item.get('description')}: {item.get('quantity')} @ {item.get('rate')} = {item.get('taxableValue')}")

# Test 4: Totals
print("\n4. Totals:")
totals = extract_totals_from_text(sample_text)
print(f"   Total Amount: {totals.get('totalAmount')}")
print(f"   Total Qty: {totals.get('totalQty')}")
print(f"   Taxable Value: {totals.get('taxableValue')}")
print(f"   CGST: {totals.get('cgst')}")
print(f"   SGST: {totals.get('sgst')}")
print(f"   Total Tax: {totals.get('totalTax')}")
print(f"   Round Off: {totals.get('roundOff')}")

print("\n" + "=" * 60)
print("✅ All tests completed!")
print("=" * 60)
