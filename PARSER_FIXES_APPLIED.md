# Invoice Parser Fixes Applied

## Summary
Applied surgical fixes to the geometry-based invoice parser to handle edge cases and improve accuracy.

## Fixes Applied

### 1. **Multi-Row Item Merging** ✅
- **Problem**: Items spanning multiple rows (description on one row, numeric data on another)
- **Solution**: Buffer rows without amounts as potential descriptions, merge with next row containing amount
- **Impact**: Handles invoices where item data is split across rows

### 2. **Smart Header Detection** ✅
- **Problem**: Single-token header labels (e.g., "# Item name") can't be used for column inference
- **Solution**: When header has < 3 tokens, look ahead for first multi-token data row to infer column positions
- **Impact**: Correctly handles minimal header labels

### 3. **Column Bounds Safety** ✅
- **Problem**: Headers with < 3 tokens create invalid column boundaries
- **Solution**: Return single-column fallback when header has insufficient tokens
- **Impact**: Prevents crashes and bogus column assignments

### 4. **Percentage Exclusion from Amounts** ✅
- **Problem**: GST percentages like "(5.0%)" were being extracted as amounts
- **Solution**: Exclude columns containing "%" from amount detection
- **Impact**: Correctly identifies taxable values vs tax rates

### 5. **Quantity Unit Prioritization** ✅
- **Problem**: HSN codes (e.g., "2520") were being extracted as quantities
- **Solution**: Prioritize quantities with explicit units (Bag, PCS, KG), add space before unit
- **Impact**: Correctly extracts "149 Bag" instead of "2520"

### 6. **Total vs Sub Total Disambiguation** ✅
- **Problem**: Regex matched "Sub Total" when looking for "Total"
- **Solution**: Use negative lookbehind `(?<!Sub\s)Total` to exclude "Sub Total"
- **Impact**: Correctly extracts final total (41,146) instead of subtotal (39,187)

### 7. **Round-Off Pattern Fix** ✅
- **Problem**: Pattern matched "-" as the round-off value
- **Solution**: Updated pattern to skip separators and match actual number
- **Impact**: Correctly extracts 0.35 instead of None

### 8. **Date Pattern Enhancement** ✅
- **Problem**: Only supported text months (Oct, Nov), not numeric (08, 09)
- **Solution**: Pattern now accepts both `20-Oct-2025` and `20-08-2025`
- **Impact**: Handles both date formats

## Test Results

### Sale_297 Invoice
```
✅ Invoice number: 297
✅ Invoice date: 20-08-2025
✅ Description: NATURAL GYPSUM CALCINED PLASTER
✅ HSN: 2520
✅ Quantity: 149 Bag
✅ Unit Price: ₹263.0
✅ Taxable Value: ₹39,187.0
✅ SGST: ₹979.68
✅ CGST: ₹979.68
✅ Round Off: ₹0.35
✅ Total: ₹41,146.0
```

## Architecture Improvements

### Before
- Single-row item parsing only
- Strict header requirements (3+ keywords)
- No percentage filtering
- Greedy regex patterns

### After
- Multi-row item merging with description buffering
- Adaptive header detection (label + data row inference)
- Smart amount detection (excludes percentages)
- Precise regex patterns with negative lookbehinds

## Files Modified
- `src/services/invoice_extractor.py` - Core extraction logic
- `debug_invoice_parse.py` - Debug script for troubleshooting

## Next Steps
These fixes handle the most common edge cases. For further improvements:
1. Add field-level confidence scores
2. Implement buyer/seller extraction enhancements
3. Add support for multi-page invoices with page breaks
4. Create validation rules for extracted data
