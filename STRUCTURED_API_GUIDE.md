# Structured Invoice API Guide

## Overview

The `/ocr/parse/structured` endpoint provides a **clean, business-friendly** invoice format that's easier to integrate with your applications. It wraps the standard OCR endpoint and transforms the response into a structured schema.

## Endpoint

```
POST /ocr/parse/structured
```

## Key Differences

### Standard `/ocr/parse` Response
- Raw OCR output with bounding boxes
- Technical field names
- Nested confidence scores
- Full text array with all tokens
- Designed for OCR analysis

### Structured `/ocr/parse/structured` Response
- Clean business data
- Simple field names
- Flat structure
- No technical metadata
- Designed for business applications

## Request

```bash
curl -X POST http://localhost:8080/ocr/parse/structured \
  -F "file=@invoice.pdf" \
  -F "lang=en"
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| file | File | Yes | Invoice image (PNG/JPEG) or PDF |
| lang | String | No | OCR language code (default: "en") |

## Response Schema

```json
{
  "invoice": {
    "invoiceNumber": "string",
    "invoiceDate": "string",
    "acknowledgement": {
      "ackNo": "string",
      "ackDate": "string"
    },
    "irn": "string",
    "referenceNo": "string",
    "referenceDate": "string"
  },
  "seller": {
    "name": "string",
    "unit": "string",
    "address": "string",
    "gstin": "string",
    "state": "string",
    "stateCode": "string"
  },
  "buyer": {
    "name": "string",
    "contact": "string",
    "address": "string",
    "gstin": "string",
    "state": "string",
    "stateCode": "string"
  },
  "items": [
    {
      "slNo": 1,
      "description": "string",
      "quantity": "string",
      "rate": 0.0,
      "per": "string",
      "taxableValue": 0.0,
      "hsn": "string",
      "cgstRate": 0,
      "sgstRate": 0
    }
  ],
  "totals": {
    "roundOff": 0.0,
    "totalQty": "string",
    "totalAmount": 0.0,
    "taxableValue": 0.0,
    "cgst": 0.0,
    "sgst": 0.0,
    "totalTax": 0.0,
    "totalInWords": "string",
    "taxInWords": "string"
  },
  "meta": {
    "documentType": "string",
    "isComputerGenerated": false,
    "authorisedSignatory": "string"
  }
}
```

## Example Response

```json
{
  "invoice": {
    "invoiceNumber": "TPS/25-26/3050",
    "invoiceDate": "23-Oct-25",
    "acknowledgement": {
      "ackNo": "182520552950613",
      "ackDate": "24-Oct-25"
    },
    "irn": "b45b5c5dd32ab1f2a403c923cba57cfebd17047ebcf63937092db8c93037c841",
    "referenceNo": "3606",
    "referenceDate": "23-Oct-25"
  },
  "seller": {
    "name": "M/s Tajpuria Sales",
    "unit": "Unit of Shree Ram Sales LLP",
    "address": "Circle No-20A, Ward No-38, Koyal Kothi, Ram Krishna Path, Kadam Kuan, Patna-800003",
    "gstin": "10ADAFS2028K1ZI",
    "state": "Bihar",
    "stateCode": "10"
  },
  "buyer": {
    "name": "Shree Ram Iron (Madhepura)",
    "contact": "Rahul Kumar, S/O Rajesh Kumar",
    "address": "Agrawal, Ward No-20, Subhash, Chowk, Madhepura, Madhepura",
    "gstin": "10FVYPK2595A1ZG",
    "state": "Bihar",
    "stateCode": "10"
  },
  "items": [
    {
      "slNo": 1,
      "description": "HG 8341",
      "quantity": "2 PCS",
      "rate": 755.00,
      "per": "PCS",
      "taxableValue": 1279.66,
      "hsn": "48239019",
      "cgstRate": 9,
      "sgstRate": 9
    },
    {
      "slNo": 2,
      "description": "GLOSS 7204",
      "quantity": "2 PCS",
      "rate": 514.00,
      "per": "PCS",
      "taxableValue": 871.18,
      "hsn": "48239019",
      "cgstRate": 9,
      "sgstRate": 9
    },
    {
      "slNo": 3,
      "description": "White MT .072mm",
      "quantity": "13 PCS",
      "rate": 365.00,
      "per": "PCS",
      "taxableValue": 4021.16,
      "hsn": "48239019",
      "cgstRate": 9,
      "sgstRate": 9
    }
  ],
  "totals": {
    "roundOff": 0.04,
    "totalQty": "17 PCS",
    "totalAmount": 7460.00,
    "taxableValue": 6322.00,
    "cgst": 568.98,
    "sgst": 568.98,
    "totalTax": 1137.96,
    "totalInWords": "INR Seven Thousand Four Hundred Sixty Only",
    "taxInWords": "INR One Thousand One Hundred Thirty Seven and Ninety Six paise Only"
  },
  "meta": {
    "documentType": "Tax Invoice",
    "isComputerGenerated": true,
    "authorisedSignatory": "M/s Tajpuria Sales"
  }
}
```

## Field Descriptions

### Invoice Section

| Field | Type | Description |
|-------|------|-------------|
| invoiceNumber | string | Invoice number (e.g., "TPS/25-26/3050") |
| invoiceDate | string | Invoice date (e.g., "23-Oct-25") |
| acknowledgement.ackNo | string | E-invoice acknowledgement number |
| acknowledgement.ackDate | string | E-invoice acknowledgement date |
| irn | string | Invoice Reference Number (IRN) for e-invoicing |
| referenceNo | string | Reference/PO number |
| referenceDate | string | Reference/PO date |

### Seller Section

| Field | Type | Description |
|-------|------|-------------|
| name | string | Seller company name |
| unit | string | Business unit (if applicable) |
| address | string | Complete seller address |
| gstin | string | Seller GSTIN |
| state | string | Seller state name |
| stateCode | string | Seller state code (2 digits) |

### Buyer Section

| Field | Type | Description |
|-------|------|-------------|
| name | string | Buyer company name |
| contact | string | Contact person details |
| address | string | Complete buyer address |
| gstin | string | Buyer GSTIN |
| state | string | Buyer state name |
| stateCode | string | Buyer state code (2 digits) |

### Items Section

| Field | Type | Description |
|-------|------|-------------|
| slNo | integer | Serial number |
| description | string | Item description |
| quantity | string | Quantity with unit (e.g., "13 PCS") |
| rate | float | Rate per unit |
| per | string | Unit of measurement (e.g., "PCS", "KG") |
| taxableValue | float | Taxable amount (qty × rate) |
| hsn | string | HSN/SAC code |
| cgstRate | integer | CGST rate percentage |
| sgstRate | integer | SGST rate percentage |

### Totals Section

| Field | Type | Description |
|-------|------|-------------|
| roundOff | float | Round-off amount |
| totalQty | string | Total quantity (e.g., "17 PCS") |
| totalAmount | float | Grand total amount |
| taxableValue | float | Total taxable value |
| cgst | float | Total CGST amount |
| sgst | float | Total SGST amount |
| totalTax | float | Total tax (CGST + SGST) |
| totalInWords | string | Total amount in words |
| taxInWords | string | Tax amount in words |

### Meta Section

| Field | Type | Description |
|-------|------|-------------|
| documentType | string | Document type (e.g., "Tax Invoice") |
| isComputerGenerated | boolean | Whether invoice is computer generated |
| authorisedSignatory | string | Authorised signatory name |

## Use Cases

### 1. **ERP Integration**

```python
import requests

def import_invoice_to_erp(file_path):
    with open(file_path, 'rb') as f:
        response = requests.post(
            'http://localhost:8080/ocr/parse/structured',
            files={'file': f}
        )
    
    invoice_data = response.json()
    
    # Direct mapping to ERP fields
    erp_invoice = {
        'invoice_no': invoice_data['invoice']['invoiceNumber'],
        'invoice_date': invoice_data['invoice']['invoiceDate'],
        'vendor_gstin': invoice_data['seller']['gstin'],
        'vendor_name': invoice_data['seller']['name'],
        'total_amount': invoice_data['totals']['totalAmount'],
        'tax_amount': invoice_data['totals']['totalTax'],
        'line_items': [
            {
                'description': item['description'],
                'qty': item['quantity'],
                'rate': item['rate'],
                'amount': item['taxableValue']
            }
            for item in invoice_data['items']
        ]
    }
    
    return erp_invoice
```

### 2. **Accounting Software**

```python
def create_accounting_entry(invoice_data):
    """Create accounting entry from structured invoice."""
    
    # Debit entries (purchases)
    debits = []
    for item in invoice_data['items']:
        debits.append({
            'account': 'Purchases',
            'amount': item['taxableValue'],
            'description': item['description']
        })
    
    # Tax entries
    debits.append({
        'account': 'CGST Input',
        'amount': invoice_data['totals']['cgst']
    })
    debits.append({
        'account': 'SGST Input',
        'amount': invoice_data['totals']['sgst']
    })
    
    # Credit entry (payable)
    credits = [{
        'account': 'Accounts Payable',
        'amount': invoice_data['totals']['totalAmount'],
        'party': invoice_data['seller']['name'],
        'gstin': invoice_data['seller']['gstin']
    }]
    
    return {
        'voucher_type': 'Purchase',
        'date': invoice_data['invoice']['invoiceDate'],
        'reference': invoice_data['invoice']['invoiceNumber'],
        'debits': debits,
        'credits': credits
    }
```

### 3. **GST Return Filing**

```python
def prepare_gst_return_data(invoice_data):
    """Prepare data for GST return filing."""
    
    return {
        'gstin': invoice_data['seller']['gstin'],
        'invoice_number': invoice_data['invoice']['invoiceNumber'],
        'invoice_date': invoice_data['invoice']['invoiceDate'],
        'invoice_value': invoice_data['totals']['totalAmount'],
        'place_of_supply': invoice_data['seller']['stateCode'],
        'reverse_charge': 'N',
        'invoice_type': 'Regular',
        'taxable_value': invoice_data['totals']['taxableValue'],
        'cgst_amount': invoice_data['totals']['cgst'],
        'sgst_amount': invoice_data['totals']['sgst'],
        'igst_amount': 0.0,
        'irn': invoice_data['invoice'].get('irn')
    }
```

### 4. **Invoice Validation**

```python
def validate_invoice(invoice_data):
    """Validate invoice data."""
    
    errors = []
    
    # Check GSTIN format
    if not re.match(r'^\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]$', 
                    invoice_data['seller']['gstin']):
        errors.append('Invalid seller GSTIN format')
    
    # Check totals
    calculated_total = sum(item['taxableValue'] for item in invoice_data['items'])
    if abs(calculated_total - invoice_data['totals']['taxableValue']) > 0.01:
        errors.append('Taxable value mismatch')
    
    # Check tax calculation
    calculated_tax = invoice_data['totals']['cgst'] + invoice_data['totals']['sgst']
    if abs(calculated_tax - invoice_data['totals']['totalTax']) > 0.01:
        errors.append('Tax calculation mismatch')
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }
```

## Comparison: Standard vs Structured

### Standard `/ocr/parse`

**Pros**:
- Complete OCR data with confidence scores
- Bounding boxes for spatial analysis
- Full text array for custom extraction
- Detailed quality metrics

**Cons**:
- Complex nested structure
- Requires post-processing
- Technical field names
- Large response size

**Use when**:
- You need OCR confidence scores
- You want to extract custom fields
- You need bounding box coordinates
- You're building OCR analysis tools

### Structured `/ocr/parse/structured`

**Pros**:
- Clean, flat structure
- Business-friendly field names
- Ready for ERP/accounting integration
- Smaller response size

**Cons**:
- No confidence scores
- No bounding boxes
- Fixed schema
- Less flexibility

**Use when**:
- Integrating with ERP/accounting software
- Building business applications
- You don't need OCR metadata
- You want simple, clean data

## Error Handling

The structured endpoint returns the same error codes as the standard endpoint:

| Code | Description |
|------|-------------|
| 200 | Success |
| 413 | File too large |
| 415 | Unsupported file type |
| 422 | No text detected |
| 500 | Internal server error |

## Performance

- **Processing time**: Same as standard endpoint (~5-7 seconds)
- **Response size**: ~50% smaller than standard endpoint
- **Accuracy**: Same as standard endpoint (uses same OCR engine)

## Best Practices

1. **Use structured endpoint for business apps**: If you're building ERP, accounting, or business applications
2. **Use standard endpoint for analysis**: If you need OCR confidence, bounding boxes, or custom extraction
3. **Validate data**: Always validate GSTIN, totals, and tax calculations
4. **Handle missing fields**: Some fields may be null if not found in invoice
5. **Cache responses**: Cache structured responses to avoid re-processing

## Migration from Standard Endpoint

If you're currently using `/ocr/parse`, here's how to migrate:

```python
# Before (standard endpoint)
response = requests.post('http://localhost:8080/ocr/parse', files={'file': f})
data = response.json()

invoice_number = data['invoice']['number']['value']
seller_name = data['seller']['name']
total = data['totals']['gross']

# After (structured endpoint)
response = requests.post('http://localhost:8080/ocr/parse/structured', files={'file': f})
data = response.json()

invoice_number = data['invoice']['invoiceNumber']
seller_name = data['seller']['name']
total = data['totals']['totalAmount']
```

## Support

For issues or questions:
- Check Swagger UI: http://localhost:8080/docs
- Review standard endpoint: `/ocr/parse`
- Check logs for errors
