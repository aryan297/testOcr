# Transposed Table Parser

## Problem
Some invoices have a **transposed layout** where:
- **Items are columns** (not rows)
- **Each row is a field type** (HSN, Quantity, Rate, Amount)

### Example Structure
```
Row 12: 48239019    48239019    48239019    <- HSN codes
Row 14: Quantity                             <- Field label
Row 15: 13 PCS      2 PCS       2 pCS       <- Quantities
Row 20: Rate                                 <- Field label  
Row 21: 365.00      514.00      755.00      <- Rates
Row 28: Amount                               <- Field label
Row 29: 4745.00     1028.00     1510.00     <- Amounts
```

This is the opposite of normal invoices where each row is an item.

## Solution

### 1. Transposed Table Detection
Added `is_transposed_table()` function that:
- Checks if column positions are consistent across multiple rows
- Requires 80% position match within 20px tolerance
- Looks at first 5 rows after header

### 2. Transposed Table Parser
Added `parse_transposed_table()` function that:
- Identifies field rows by keywords (quantity, rate, amount, hsn)
- Extracts each column as a separate item
- Maps fields correctly:
  - Column 0 → Item 1
  - Column 1 → Item 2
  - Column 2 → Item 3

### 3. Enhanced Header Detection
Updated `find_header_soft()` to:
- Prioritize "Quantity" and "HSN/SAC" keywords over "Description of Goods"
- Look ahead for first row with 3+ numeric tokens (actual data)
- Use data row for column inference instead of label row

## Implementation

### Detection Logic
```python
def is_transposed_table(rows, start_idx, end_idx):
    # Get column positions from first 5 rows
    col_positions = []
    for row in rows[start_idx:start_idx + 5]:
        if len(row) >= 3:
            col_positions.append([t['left'] for t in row])
    
    # Check if positions are consistent
    first_cols = col_positions[0]
    for cols in col_positions[1:]:
        matches = sum(1 for a, b in zip(first_cols, cols) if abs(a - b) < 20)
        if matches >= len(first_cols) * 0.8:  # 80% match
            return True
    return False
```

### Parsing Logic
```python
def parse_transposed_table(rows, start_idx, bounds):
    # Collect field rows
    field_rows = {}
    for row in rows[start_idx:start_idx + 30]:
        line_text = " ".join(t["text"].lower() for t in row)
        
        if "quantity" in line_text:
            field_rows['quantity'] = row
        elif "rate" in line_text and len(row) >= 3:
            field_rows['rate'] = row
        elif "amount" in line_text and len(row) >= 3:
            field_rows['amount'] = row
        elif "hsn" in line_text and len(row) >= 3:
            field_rows['hsn'] = row
    
    # Extract each column as an item
    num_cols = len(field_rows.get('quantity', []))
    items = []
    for col_idx in range(num_cols):
        item = {
            'quantity': field_rows['quantity'][col_idx]['text'] if 'quantity' in field_rows else None,
            'unitPrice': normalize_amount(field_rows['rate'][col_idx]['text']) if 'rate' in field_rows else None,
            'taxableValue': normalize_amount(field_rows['amount'][col_idx]['text']) if 'amount' in field_rows else None,
            'hsn': extract_hsn(field_rows['hsn'][col_idx]['text']) if 'hsn' in field_rows else None
        }
        items.append(item)
    
    return items
```

## Test Case: SR IRON Invoice

### Input Structure
```
Row 12: 48239019 48239019 48239019 HSN/SAC
Row 14: Quantity
Row 15: 13 PCS 2 PCS 2 pCS
Row 20: (Incl. of Tax) Rate
Row 21: 365.00 514.00 755.00
Row 22: Rate
Row 23: 309.32 435.59 639.83
Row 28: Amount
```

### Expected Output
```json
{
  "items": [
    {
      "description": null,
      "hsn": "48239019",
      "quantity": "13 PCS",
      "unitPrice": 365.00,
      "taxableValue": 4745.00
    },
    {
      "description": null,
      "hsn": "48239019",
      "quantity": "2 PCS",
      "unitPrice": 514.00,
      "taxableValue": 1028.00
    },
    {
      "description": null,
      "hsn": "48239019",
      "quantity": "2 pCS",
      "unitPrice": 755.00,
      "taxableValue": 1510.00
    }
  ]
}
```

## Limitations

1. **Description extraction**: Transposed tables often don't have descriptions in the table itself. Descriptions may be in a separate section above the table.

2. **Multiple rate rows**: If there are multiple "Rate" rows (like rows 21 and 23), the parser currently takes the first one. May need logic to determine which is the correct rate.

3. **Field identification**: Relies on keywords ("quantity", "rate", "amount"). If keywords are missing or in a different language, detection may fail.

## Future Enhancements

1. **Description extraction**: Look for description rows above the table (rows 2-7 in the example)
2. **Smart rate selection**: If multiple rate rows exist, use the one closest to the amount row
3. **Multi-language support**: Add keyword translations for Hindi, regional languages
4. **Confidence scoring**: Return lower confidence for transposed tables (less common format)
