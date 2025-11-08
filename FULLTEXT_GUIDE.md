# Full Text Extraction Guide

## Overview

The OCR service now returns **all extracted text** from your invoices in the `fullText` field, not just the structured invoice fields. This gives you complete access to every word, address, note, and detail detected in the document.

## What's New

### 1. **fullText Field**
Every API response now includes a `fullText` array containing all OCR tokens with:
- Text content
- Confidence score
- Bounding box coordinates
- Handwriting detection metadata (if enabled)

### 2. **Address Extraction**
Seller and buyer entities now include an `address` field that captures address information near their names/GSTINs.

## Response Structure

```json
{
  "meta": { ... },
  "seller": {
    "name": "ABC Corporation",
    "gstin": "29ABCDE1234F1Z5",
    "address": "123 Main Street, Building A, Floor 2, City, State 560001",
    "confidence": 0.9,
    "bbox": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
  },
  "buyer": {
    "name": "XYZ Limited",
    "gstin": "07FGHIJ5678K2Z9",
    "address": "456 Oak Avenue, Suite 100, Town, State 110001",
    "confidence": 0.8,
    "bbox": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
  },
  "invoice": { ... },
  "lines": [ ... ],
  "totals": { ... },
  "warnings": [ ... ],
  "fullText": [
    {
      "text": "ABC Corporation",
      "confidence": 0.95,
      "bbox": [[100, 50], [300, 50], [300, 80], [100, 80]],
      "handwritten": false,
      "hw_score": null
    },
    {
      "text": "123 Main Street",
      "confidence": 0.92,
      "bbox": [[100, 85], [280, 85], [280, 110], [100, 110]]
    },
    {
      "text": "Building A",
      "confidence": 0.90,
      "bbox": [[100, 115], [200, 115], [200, 140], [100, 140]]
    },
    {
      "text": "GSTIN: 29ABCDE1234F1Z5",
      "confidence": 0.93,
      "bbox": [[100, 145], [350, 145], [350, 170], [100, 170]]
    },
    // ... every single text element from the document
  ]
}
```

## Use Cases

### 1. **Extract Complete Addresses**

```python
import requests

response = requests.post(
    'http://localhost:8080/ocr/parse',
    files={'file': open('invoice.pdf', 'rb')}
)
result = response.json()

# Get seller address from structured field
seller_address = result['seller']['address']
print(f"Seller Address: {seller_address}")

# Or reconstruct from fullText tokens
seller_bbox = result['seller']['bbox']
# Find all tokens near seller bbox
nearby_tokens = [
    token for token in result['fullText']
    if is_near(token['bbox'], seller_bbox)
]
```

### 2. **Search for Specific Text**

```python
# Find all tokens containing "PAN"
pan_tokens = [
    token for token in result['fullText']
    if 'PAN' in token['text'].upper()
]

# Find all tokens with low confidence
low_conf_tokens = [
    token for token in result['fullText']
    if token['confidence'] < 0.7
]
```

### 3. **Extract Custom Fields**

```python
import re

# Find email addresses
emails = []
for token in result['fullText']:
    if re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', token['text']):
        emails.append(token['text'])

# Find phone numbers
phones = []
for token in result['fullText']:
    if re.search(r'\b\d{10}\b|\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', token['text']):
        phones.append(token['text'])

# Find PAN numbers
pans = []
for token in result['fullText']:
    if re.search(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b', token['text']):
        pans.append(token['text'])
```

### 4. **Reconstruct Document Layout**

```python
# Sort tokens by position (top to bottom, left to right)
sorted_tokens = sorted(
    result['fullText'],
    key=lambda t: (t['bbox'][0][1], t['bbox'][0][0])  # Sort by y, then x
)

# Group into lines (tokens with similar y-coordinates)
lines = []
current_line = []
current_y = None
threshold = 20  # pixels

for token in sorted_tokens:
    y = token['bbox'][0][1]
    if current_y is None or abs(y - current_y) < threshold:
        current_line.append(token['text'])
        current_y = y if current_y is None else (current_y + y) / 2
    else:
        lines.append(' '.join(current_line))
        current_line = [token['text']]
        current_y = y

if current_line:
    lines.append(' '.join(current_line))

# Print reconstructed document
for line in lines:
    print(line)
```

### 5. **Identify Handwritten Sections**

```python
# Find all handwritten text
handwritten = [
    token for token in result['fullText']
    if token.get('handwritten', False)
]

print(f"Found {len(handwritten)} handwritten tokens:")
for token in handwritten:
    print(f"  - {token['text']} (confidence: {token['confidence']:.2f}, hw_score: {token['hw_score']:.2f})")
```

### 6. **Extract Notes/Comments**

```python
# Find tokens in bottom 20% of document (often contains notes)
max_y = max(token['bbox'][0][1] for token in result['fullText'])
notes_threshold = max_y * 0.8

notes = [
    token['text'] for token in result['fullText']
    if token['bbox'][0][1] > notes_threshold
]

print("Notes/Comments:", ' '.join(notes))
```

## Bounding Box Format

Each token's `bbox` is an array of 4 points (clockwise from top-left):

```json
{
  "bbox": [
    [x1, y1],  // Top-left
    [x2, y2],  // Top-right
    [x3, y3],  // Bottom-right
    [x4, y4]   // Bottom-left
  ]
}
```

### Helper Functions

```python
def get_bbox_center(bbox):
    """Get center point of bounding box."""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (sum(xs) / len(xs), sum(ys) / len(ys))

def get_bbox_area(bbox):
    """Calculate area of bounding box."""
    width = bbox[1][0] - bbox[0][0]
    height = bbox[2][1] - bbox[1][1]
    return width * height

def is_near(bbox1, bbox2, threshold=100):
    """Check if two bounding boxes are near each other."""
    center1 = get_bbox_center(bbox1)
    center2 = get_bbox_center(bbox2)
    distance = ((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)**0.5
    return distance < threshold

def tokens_in_region(tokens, x1, y1, x2, y2):
    """Get all tokens within a rectangular region."""
    result = []
    for token in tokens:
        center = get_bbox_center(token['bbox'])
        if x1 <= center[0] <= x2 and y1 <= center[1] <= y2:
            result.append(token)
    return result
```

## Performance Considerations

- **fullText array size**: Can be large for multi-page documents (100-500 tokens per page)
- **Network transfer**: Adds ~10-50KB to response size
- **Processing time**: No additional overhead (tokens already extracted)

### Optimization Tips

1. **Filter on server side** (future enhancement):
   ```python
   # Request only specific regions
   response = requests.post(
       'http://localhost:8080/ocr/parse',
       files={'file': f},
       data={'include_full_text': 'true', 'region': 'header'}
   )
   ```

2. **Client-side filtering**:
   ```python
   # Only keep high-confidence tokens
   filtered = [t for t in result['fullText'] if t['confidence'] > 0.8]
   ```

3. **Compress response**:
   ```python
   response = requests.post(
       'http://localhost:8080/ocr/parse',
       files={'file': f},
       headers={'Accept-Encoding': 'gzip'}
   )
   ```

## Comparison: Before vs After

### Before (v1.x)
```json
{
  "seller": {
    "name": "ABC Corp",
    "gstin": "29ABCDE1234F1Z5"
  }
}
```
❌ Missing: Address, phone, email, other details

### After (v2.0)
```json
{
  "seller": {
    "name": "ABC Corp",
    "gstin": "29ABCDE1234F1Z5",
    "address": "123 Main St, City, State 560001"
  },
  "fullText": [
    {"text": "ABC Corp", "confidence": 0.95, "bbox": [...]},
    {"text": "123 Main St", "confidence": 0.92, "bbox": [...]},
    {"text": "City, State 560001", "confidence": 0.90, "bbox": [...]},
    {"text": "Phone: +91-1234567890", "confidence": 0.88, "bbox": [...]},
    {"text": "Email: info@abccorp.com", "confidence": 0.91, "bbox": [...]}
  ]
}
```
✅ Complete: All text with positions and confidence

## Best Practices

1. **Use structured fields first**: For standard invoice fields (seller, buyer, totals), use the structured fields
2. **Use fullText for custom extraction**: For non-standard fields (PAN, email, notes), use fullText
3. **Validate with confidence scores**: Filter tokens with confidence < 0.7 for critical data
4. **Combine with bounding boxes**: Use spatial information to group related tokens
5. **Handle handwriting**: Check `handwritten` flag for special processing

## Examples

### Complete Address Extraction

```python
def extract_complete_address(result, entity_type='seller'):
    """Extract complete address for seller or buyer."""
    entity = result[entity_type]
    if not entity:
        return None
    
    # Get entity bbox
    entity_bbox = entity['bbox']
    if not entity_bbox:
        return entity.get('address')  # Fallback to structured address
    
    # Find all tokens near entity (within 200px)
    nearby = []
    entity_center = get_bbox_center(entity_bbox)
    
    for token in result['fullText']:
        token_center = get_bbox_center(token['bbox'])
        distance = ((entity_center[0] - token_center[0])**2 + 
                   (entity_center[1] - token_center[1])**2)**0.5
        
        if distance < 200:
            nearby.append((token_center[1], token['text']))  # (y_pos, text)
    
    # Sort by y-position and join
    nearby.sort()
    address_parts = [text for _, text in nearby]
    
    # Filter out entity name and GSTIN
    address_parts = [
        part for part in address_parts
        if part != entity['name'] and 
           (not entity['gstin'] or entity['gstin'] not in part)
    ]
    
    return ', '.join(address_parts)

# Usage
seller_address = extract_complete_address(result, 'seller')
buyer_address = extract_complete_address(result, 'buyer')
```

## Troubleshooting

### Issue: fullText is empty
**Solution**: Check if OCR detected any text. Look at `meta.ocrConfidence` and `warnings`.

### Issue: Missing expected text
**Solution**: Check image quality. Low confidence tokens might be filtered. Lower threshold or check original tokens.

### Issue: Duplicate text in fullText
**Solution**: This is expected for multi-page PDFs. Filter by page or use unique text.

### Issue: Incorrect bounding boxes
**Solution**: Bounding boxes are in image coordinates. If image was preprocessed (rotated, scaled), boxes reflect final coordinates.

## Future Enhancements

- [ ] Page-level fullText grouping
- [ ] Confidence-based filtering option
- [ ] Region-based extraction (header, body, footer)
- [ ] Text block grouping (paragraphs, sections)
- [ ] OCR language detection per token
- [ ] Reading order optimization
