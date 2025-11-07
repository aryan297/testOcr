GST_ALLOWED = {0, 0.05, 0.12, 0.18, 0.28}


def compute_line_totals(qty, rate, gst):
    """Compute net, tax, and gross for a line item."""
    net = round(qty * rate, 2)
    tax = round(net * gst, 2)
    gross = round(net + tax, 2)
    return net, tax, gross


def recompute_and_summarize(rows):
    """Recompute line totals and summarize into grand totals."""
    totals = {
        "net": 0.0,
        "tax": 0.0,
        "gross": 0.0,
        "cgst": 0.0,
        "sgst": 0.0,
        "igst": 0.0
    }
    
    for r in rows:
        qty_val = float(r.qty.value) if r.qty.value else 0.0
        price_val = float(r.unitPrice.value) if r.unitPrice.value else 0.0
        gst_val = float(r.gstRate.value) if r.gstRate.value else 0.0
        
        n, t, g = compute_line_totals(qty_val, price_val, gst_val)
        
        # Update line computed totals
        r.computed.net = n
        r.computed.tax = t
        r.computed.gross = g
        
        totals["net"] += n
        totals["tax"] += t
        totals["gross"] += g
    
    # Round all totals
    for k in totals:
        totals[k] = round(totals[k], 2)
    
    return totals


def reconcile_totals(computed_totals, extracted_totals, tolerance=1.0):
    """Reconcile computed totals with extracted totals from document."""
    reconciled = True
    round_off_delta = 0.0
    
    if extracted_totals:
        extracted_gross = extracted_totals.get("gross", 0.0)
        computed_gross = computed_totals.get("gross", 0.0)
        round_off_delta = round(extracted_gross - computed_gross, 2)
        
        if abs(round_off_delta) > tolerance:
            reconciled = False
    
    return reconciled, round_off_delta


def detect_special_lines(tokens, image_bgr):
    """Detect discount, round-off, freight lines."""
    special_lines = []
    
    for t in tokens:
        text_lower = t["text"].lower()
        if any(keyword in text_lower for keyword in ["discount", "disc"]):
            special_lines.append({"type": "discount", "token": t})
        elif any(keyword in text_lower for keyword in ["round off", "roundoff", "round-off"]):
            special_lines.append({"type": "round_off", "token": t})
        elif any(keyword in text_lower for keyword in ["freight", "transport", "shipping"]):
            special_lines.append({"type": "freight", "token": t})
    
    return special_lines


def split_tax_breakdown(totals, place_of_supply):
    """Split tax into CGST/SGST or IGST based on place of supply."""
    tax = totals.get("tax", 0.0)
    
    # Simplified: if same state, use CGST/SGST (50-50), else IGST
    # In practice, this should be determined from seller/buyer addresses
    if place_of_supply:
        # Assume intra-state if place of supply matches (simplified logic)
        # For now, default to IGST split
        totals["igst"] = tax
        totals["cgst"] = 0.0
        totals["sgst"] = 0.0
    else:
        # Default to CGST/SGST split
        totals["cgst"] = round(tax / 2, 2)
        totals["sgst"] = round(tax / 2, 2)
        totals["igst"] = 0.0
    
    return totals

