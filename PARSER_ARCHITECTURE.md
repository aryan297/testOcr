# Invoice Parser Architecture

## Overview

The OCR service uses a **three-tier parsing strategy** for maximum robustness across different invoice layouts:

```
┌─────────────────────────────────────────────────────────────┐
│                    OCR Response (fullText)                   │
│              [tokens with text + bbox + confidence]          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Tier 1: Spatial Parser (Geometry)               │
│  • Groups tokens into rows by y-coordinate                   │
│  • Finds header row (Description, HSN, Qty, etc.)            │
│  • Computes column boundaries from header x-positions        │
│  • Assigns tokens to columns by x-position                   │
│  • Extracts structured items                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (if items found)
                           SUCCESS
                              
                              │ (if no items)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│         Tier 2: Fallback Line Parser (Heuristics)            │
│  • Converts rows to text lines                               │
│  • Merges wrapped descriptions (multi-line items)            │
│  • Uses regex to find: qty + unit + amounts                  │
│  • Extracts items without header detection                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (if items found)
                           SUCCESS
                              
                              │ (if no items)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│           Tier 3: Regex Parser (Text Anchors)                │
│  • Converts fullText to single string                        │
│  • Uses flexible regex patterns with anchors                 │
│  • Extracts seller/buyer by position blocks                  │
│  • Finds totals by label patterns                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Structured Invoice JSON
```

## Tier 1: Spatial Parser (Primary)

**File**: `src/services/spatial_parser.py`

### How It Works

1. **Token Extraction**
   ```python
   tokens = [
       {"text": "Description", "cx": 150, "cy": 320, "left": 130, "bbox": [...]},
       {"text": "HSN", "cx": 290, "cy": 320, "left": 260, "bbox": [...]},
       ...
   ]
   ```

2. **Row Grouping** (by y-coordinate)
   ```python
   rows = group_tokens_into_rows(tokens, y_tol=14.0)
   # Groups tokens within 14px vertical distance
   ```

3. **Header Detection**
   ```python
   header_idx = find_header_row(rows)
   # Finds row with keywords: "description", "hsn", "quantity", etc.
   ```

4. **Column Boundaries** (from header x-positions)
   ```python
   bounds = compute_column_bounds_from_header(header_row)
   # bounds = [(-inf, 195), (195, 295), (295, 380), ...]
   ```

5. **Token-to-Column Assignment**
   ```python
   for row in rows[header_idx+1:]:
       cols = assign_tokens_to_columns(row, bounds)
       # cols[0] = description tokens
       # cols[1] = HSN tokens
       # cols[2] = quantity tokens
       # etc.
   ```

### Strengths
- ✅ Handles variable spacing
- ✅ Works with multi-column tables
- ✅ Robust to OCR spacing errors
- ✅ Stops at totals markers

### Limitations
- ❌ Requires detectable header row
- ❌ Fails if header split across rows
- ❌ Struggles with non-tabular layouts

## Tier 2: Fallback Line Parser (Secondary)

**File**: `src/services/spatial_parser.py` (functions: `parse_items_fallback_by_lines`, `parse_item_from_text_line`)

### How It Works

1. **Convert to Text Lines**
   ```python
   txt_lines = [" ".join(t["text"] for t in r) for r in rows]
   # ["Invoice No.: 297", "Date: 20-08-2025", "NATURAL GYPSUM...", ...]
   ```

2. **Line-by-Line Parsing**
   ```python
   for line in txt_lines:
       # Try single-line parse
       item = parse_item_from_text_line(line)
       if item:
           items.append(item)
       else:
           # Try merging with next 1-2 lines
           merged = line + " " + next_line
           item = parse_item_from_text_line(merged)
   ```

3. **Regex Heuristics**
   ```python
   # Requires: qty pattern + decimal amounts
   qty_m = re.search(r"(\d{1,6})\s*(PCS|Bag|KG|Nos)", line)
   amounts = re.findall(r"([0-9]+\.[0-9]{2})", line)
   
   if qty_m and amounts:
       # Extract item
   ```

### Strengths
- ✅ Works without header detection
- ✅ Handles wrapped descriptions
- ✅ Merges multi-line items
- ✅ Simple regex patterns

### Limitations
- ❌ Less accurate than spatial parser
- ❌ May miss items without clear patterns
- ❌ Sensitive to OCR errors in numbers

## Tier 3: Regex Parser (Tertiary)

**File**: `src/services/invoice_transformer.py`

### How It Works

1. **Convert to Single String**
   ```python
   full_text_str = get_full_text_string(full_text_tokens)
   # "Invoice No.: 297 Date: 20-08-2025 For: RANG MAHAL..."
   ```

2. **Anchor-Based Extraction**
   ```python
   # Invoice header
   inv_no = regex_get(r"Invoice\s*No\.?\s*[:\.\-]?\s*([A-Za-z0-9\/\-]+)", text)
   
   # Seller (by "For:" anchor)
   seller = regex_get(r"For\s*[:\-]?\s*([A-Z &\.\w\/]+)", text)
   
   # Buyer (by "Bill To" anchor)
   buyer = regex_get(r"Bill\s*To(.*?)(?:Invoice|HSN)", text)
   
   # Totals (by label patterns)
   total = regex_get(r"Total\s*₹?\s*([0-9\.,-]+)", text)
   ```

### Strengths
- ✅ Simple and fast
- ✅ Works for simple layouts
- ✅ Good for header/totals extraction

### Limitations
- ❌ Fragile with spacing variations
- ❌ Poor for complex tables
- ❌ Label bleed between sections

## Decision Flow

```python
def transform_invoice(ocr_response):
    # Try Tier 1: Spatial Parser
    result = spatial_parser.parse_ocr_fulltext(ocr_response)
    if result['items']:
        return result  # ✅ Success
    
    # Tier 2 is already included in spatial parser as fallback
    # (parse_items_fallback_by_lines is called internally)
    
    # Try Tier 3: Regex Parser
    result = regex_parser.extract_all(ocr_response)
    return result
```

## Tuning Parameters

### Spatial Parser

```python
# Row grouping tolerance (vertical distance in pixels)
y_tol = 14.0  # Default
# Increase for phone photos: 16-20
# Decrease for high-DPI scans: 10-12

# Header search range
for i, row in enumerate(rows[:12]):  # Search first 12 rows
# Increase if header is lower: rows[:18]
```

### Fallback Parser

```python
# Line merging window (how many lines to combine)
while j <= 2 and i + j < len(txt_lines):  # Merge up to 2 lines
# Increase for 3-line descriptions: j <= 3
```

### Regex Parser

```python
# Pattern flexibility
r"Invoice\s*No\.?\s*[:\.\-]?\s*([A-Za-z0-9\/\-]+)"
#         ^^^^^ optional spaces
#              ^^^^ optional punctuation
```

## Debugging

### 1. Check Row Grouping

```python
for i, row in enumerate(rows[:20]):
    print(f"Row {i}: {' '.join(t['text'] for t in row)}")
```

### 2. Check Header Detection

```python
header_idx = find_header_row(rows)
if header_idx:
    print(f"Header at row {header_idx}")
    print(f"Header text: {' '.join(t['text'] for t in rows[header_idx])}")
else:
    print("Header not found")
```

### 3. Check Column Boundaries

```python
if header_idx:
    bounds = compute_column_bounds_from_header(rows[header_idx])
    print(f"Column boundaries: {bounds}")
```

### 4. Check Fallback Parser

```python
txt_lines = [" ".join(t["text"] for t in r) for r in rows]
for i, line in enumerate(txt_lines[:30]):
    print(f"Line {i}: {line}")
    item = parse_item_from_text_line(line)
    if item:
        print(f"  → Parsed: {item}")
```

## Performance

| Parser | Speed | Accuracy | Use Case |
|--------|-------|----------|----------|
| Spatial | Fast | 90%+ | Structured tables with headers |
| Fallback | Fast | 75%+ | Simple invoices, wrapped text |
| Regex | Very Fast | 60%+ | Header/totals extraction |

## Best Practices

1. **Always use spatial parser first** - Most accurate for tables
2. **Log parser decisions** - Track which tier succeeded
3. **Tune y_tol per document type** - Phone photos vs scans
4. **Validate extracted items** - Check for required fields
5. **Collect failure cases** - Improve patterns iteratively

## Future Enhancements

- [ ] ML-based column detection
- [ ] Adaptive y_tol based on token density
- [ ] Multi-page table continuation
- [ ] Confidence scoring per field
- [ ] Auto-tuning based on success rate
