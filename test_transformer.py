#!/usr/bin/env python3
"""
Test invoice transformer with edge cases.
"""
from src.services.invoice_transformer import transform_invoice

# Test with minimal data (edge case)
minimal_response = {
    'fullText': [],
    'seller': {'name': 'Test Seller', 'gstin': None, 'address': None},
    'buyer': None,
    'invoice': {'number': {'value': 'INV-001'}, 'date': {'raw': None}},
    'lines': [
        {
            'description': {'value': 'Test Item'},
            'qty': {'value': 5, 'unit': None},  # None unit - this was causing the error
            'unitPrice': {'value': 100.0},
            'gstRate': {'value': 0.18},
            'hsn': None
        }
    ],
    'totals': {
        'net': 500.0,
        'tax': 90.0,
        'gross': 590.0,
        'cgst': 45.0,
        'sgst': 45.0,
        'roundOffDelta': 0.0
    }
}

print("Testing invoice transformer with edge cases...")
try:
    result = transform_invoice(minimal_response)
    print("✅ Transform successful!")
    print(f"Items: {len(result['items'])}")
    if result['items']:
        print(f"First item: {result['items'][0]}")
        print(f"Quantity: {result['items'][0]['quantity']}")
        print(f"Per: {result['items'][0]['per']}")
except Exception as e:
    print(f"❌ Transform failed: {e}")
    import traceback
    traceback.print_exc()
