import numpy as np
import cv2
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config


def _detect_table_regions(image_bgr):
    """Detect table regions using morphology operations."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Horizontal and vertical lines
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    
    horizontal_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
    vertical_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)
    
    table_mask = cv2.addWeighted(horizontal_lines, 0.5, vertical_lines, 0.5, 0.0)
    
    contours, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    tables = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > 200 and h > 100:  # Filter small regions
            tables.append((x, y, w, h))
    
    return tables


def _snap_to_columns(tokens, n_columns=5):
    """Snap tokens to column centers using clustering."""
    if not tokens:
        return {}
    
    # Get x-centers of all tokens
    x_centers = []
    for t in tokens:
        bbox = t.get("bbox", [])
        if bbox:
            xs = [p[0] for p in bbox]
            x_center = sum(xs) / len(xs)
            x_centers.append((x_center, t))
    
    if not x_centers:
        return {}
    
    # Cluster x-centers
    from sklearn.cluster import KMeans
    X = np.array([[x] for x, _ in x_centers])
    kmeans = KMeans(n_clusters=min(n_columns, len(x_centers)), random_state=0).fit(X)
    
    # Map tokens to columns
    column_centers = sorted(kmeans.cluster_centers_.flatten())
    column_tokens = {i: [] for i in range(len(column_centers))}
    
    for (x_center, token), label in zip(x_centers, kmeans.labels_):
        # Find nearest column
        nearest = min(range(len(column_centers)), key=lambda i: abs(x_center - column_centers[i]))
        column_tokens[nearest].append(token)
    
    return column_tokens, column_centers


def _group_into_rows(tokens, row_threshold=30):
    """Group tokens into rows based on y-coordinates."""
    if not tokens:
        return []
    
    # Get y-centers
    y_centers = []
    for t in tokens:
        bbox = t.get("bbox", [])
        if bbox:
            ys = [p[1] for p in bbox]
            y_center = sum(ys) / len(ys)
            y_centers.append((y_center, t))
    
    y_centers.sort(key=lambda x: x[0])
    
    # Group into rows
    rows = []
    current_row = []
    current_y = None
    
    for y_center, token in y_centers:
        if current_y is None or abs(y_center - current_y) < row_threshold:
            current_row.append(token)
            current_y = y_center if current_y is None else (current_y + y_center) / 2
        else:
            if current_row:
                rows.append(current_row)
            current_row = [token]
            current_y = y_center
    
    if current_row:
        rows.append(current_row)
    
    return rows


def _parse_line_item(tokens, column_centers):
    """Parse a row of tokens into line item fields."""
    from src.schemas import OCRField, QtyField
    
    # If no column centers, use simple left-to-right ordering
    if not column_centers:
        # Just assign tokens in order
        all_tokens = tokens
        description_tokens = all_tokens[:len(all_tokens)//2] if len(all_tokens) > 2 else all_tokens[:1]
        qty_tokens = all_tokens[len(all_tokens)//2:len(all_tokens)//2+1] if len(all_tokens) > 2 else []
        price_tokens = all_tokens[len(all_tokens)//2+1:len(all_tokens)//2+2] if len(all_tokens) > 3 else []
        gst_tokens = all_tokens[len(all_tokens)//2+2:] if len(all_tokens) > 4 else []
        hsn_tokens = []
    else:
        # Map tokens to columns
        token_cols = {}
        for t in tokens:
            bbox = t.get("bbox", [])
            if bbox:
                xs = [p[0] for p in bbox]
                x_center = sum(xs) / len(xs)
                if column_centers:
                    nearest_col = min(range(len(column_centers)), key=lambda i: abs(x_center - column_centers[i]))
                    if nearest_col not in token_cols:
                        token_cols[nearest_col] = []
                    token_cols[nearest_col].append(t)
        
        # Extract fields (assuming: desc, hsn, qty, unit_price, gst_rate)
        description_tokens = token_cols.get(0, []) + token_cols.get(1, [])
        hsn_tokens = token_cols.get(1, []) if 1 in token_cols else []
        qty_tokens = token_cols.get(2, [])
        price_tokens = token_cols.get(3, [])
        gst_tokens = token_cols.get(4, [])
    
    def _extract_numeric(tokens, default=0.0):
        if not tokens:
            return OCRField(value=default, confidence=0.0)
        text = " ".join([t["text"] for t in tokens])
        # Clean and extract number
        import re
        nums = re.findall(r'[\d.]+', text.replace(",", ""))
        if nums:
            try:
                val = float(nums[0])
                conf = sum([t.get("conf", 0.5) for t in tokens]) / len(tokens)
                bbox = tokens[0].get("bbox")
                return OCRField(value=val, confidence=conf, bbox=bbox)
            except:
                pass
        return OCRField(value=default, confidence=0.3)
    
    def _extract_qty_with_unit(tokens, default=0.0):
        """Extract quantity value and unit."""
        if not tokens:
            return QtyField(value=default, confidence=0.0, unit=None)
        text = " ".join([t["text"] for t in tokens])
        # Extract number and unit
        import re
        # Try to find number
        nums = re.findall(r'[\d.]+', text.replace(",", ""))
        # Common units
        units = ["kg", "g", "bag", "piece", "pc", "pcs", "litre", "l", "ml", "meter", "m", "cm", "box", "carton"]
        unit = None
        for u in units:
            if u.lower() in text.lower():
                unit = u.lower()
                break
        
        val = default
        conf = 0.3
        bbox = None
        if nums:
            try:
                val = float(nums[0])
                conf = sum([t.get("conf", 0.5) for t in tokens]) / len(tokens)
                bbox = tokens[0].get("bbox")
            except:
                pass
        
        return QtyField(value=val, confidence=conf, bbox=bbox, unit=unit)
    
    def _extract_text(tokens):
        if not tokens:
            return OCRField(value="", confidence=0.0)
        text = " ".join([t["text"] for t in tokens])
        conf = sum([t.get("conf", 0.5) for t in tokens]) / len(tokens)
        # Combine bboxes
        all_bboxes = [t.get("bbox") for t in tokens if t.get("bbox")]
        bbox = None
        if all_bboxes:
            xs = [p[0] for b in all_bboxes for p in b]
            ys = [p[1] for b in all_bboxes for p in b]
            bbox = [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]
        return OCRField(value=text, confidence=conf, bbox=bbox)
    
    description = _extract_text(description_tokens)
    hsn = " ".join([t["text"] for t in hsn_tokens]) if hsn_tokens else None
    qty = _extract_qty_with_unit(qty_tokens)
    unit_price = _extract_numeric(price_tokens)
    gst_rate = _extract_numeric(gst_tokens, default=0.18)
    
    # Normalize GST rate (should be percentage like 18 -> 0.18)
    if gst_rate.value and gst_rate.value > 1:
        gst_rate.value = gst_rate.value / 100
    
    return {
        "description": description,
        "hsn": hsn,
        "qty": qty,
        "unitPrice": unit_price,
        "gstRate": gst_rate
    }


def extract_table(tokens, image_bgr):
    """Extract table structure and parse line items."""
    # Filter out header tokens (top 30% of image)
    h, w = image_bgr.shape[:2]
    header_threshold = h * 0.3
    
    table_tokens = []
    for t in tokens:
        bbox = t.get("bbox", [])
        if bbox:
            ys = [p[1] for p in bbox]
            y_center = sum(ys) / len(ys)
            if y_center > header_threshold:
                table_tokens.append(t)
    
    if not table_tokens:
        return {"rows": [], "columns": ["description", "qty", "unitPrice", "gstRate", "hsn"], "debug": {}}
    
    # Group into rows
    rows = _group_into_rows(table_tokens)
    
    # Determine column structure from first few rows
    sample_tokens = []
    for row in rows[:min(5, len(rows))]:
        sample_tokens.extend(row)
    
    if sample_tokens:
        _, column_centers = _snap_to_columns(sample_tokens, n_columns=5)
    else:
        column_centers = []
    
    # Parse each row
    line_items = []
    for i, row_tokens in enumerate(rows):
        # Skip header rows
        row_text = " ".join([t["text"] for t in row_tokens]).lower()
        if any(keyword in row_text for keyword in ["description", "qty", "amount", "total", "subtotal"]):
            continue
        
        item = _parse_line_item(row_tokens, column_centers)
        if item["description"].value and item["qty"].value:
            from src.schemas import OCRLine, ComputedTotals, QtyField
            from src.services.reconcile import compute_line_totals
            
            qty_val = item["qty"].value or 0.0
            price_val = item["unitPrice"].value or 0.0
            gst_val = item["gstRate"].value or 0.0
            
            net, tax, gross = compute_line_totals(qty_val, price_val, gst_val)
            
            # Ensure qty is a QtyField with unit
            qty_field = item["qty"]
            if not isinstance(qty_field, QtyField):
                qty_field = QtyField(
                    value=qty_field.value,
                    confidence=qty_field.confidence,
                    bbox=qty_field.bbox,
                    unit=getattr(qty_field, 'unit', None)
                )
            
            line_items.append(OCRLine(
                rowId=f"r{i+1}",
                description=item["description"],
                hsn=item["hsn"],
                qty=qty_field,
                unitPrice=item["unitPrice"],
                gstRate=item["gstRate"],
                computed=ComputedTotals(net=net, tax=tax, gross=gross)
            ))
    
    return {
        "rows": line_items,
        "columns": ["description", "hsn", "qty", "unitPrice", "gstRate"],
        "debug": {"num_rows": len(rows), "num_items": len(line_items)}
    }

