from .reconcile import recompute_and_summarize, reconcile_totals, split_tax_breakdown
from ..utils.hashing import sha256_bytes, perceptual_hash
from ..schemas import MetaInfo, QualityMetrics, TotalsInfo, Warning


def avg_conf(rows):
    """Calculate average confidence across all fields in rows."""
    vals = []
    for r in rows:
        for field_name in ["description", "qty", "unitPrice", "gstRate"]:
            field = getattr(r, field_name, None)
            if field and hasattr(field, "confidence"):
                vals.append(field.confidence)
    return round(sum(vals) / len(vals), 3) if vals else 0.0


def generate_warnings(header, rows, quality):
    """Generate warnings for low confidence fields or quality issues."""
    warnings = []
    
    # Quality warnings
    if quality.get("focus", 0) < 80:
        warnings.append(Warning(code="LOW_FOCUS", score=quality.get("focus", 0)))
    if quality.get("glare", 0) > 0.08:
        warnings.append(Warning(code="HIGH_GLARE", score=quality.get("glare", 0)))
    
    # Field confidence warnings
    if header.get("invoice", {}).get("number", {}).get("confidence", 1.0) < 0.7:
        warnings.append(Warning(
            code="LOW_CONF_FIELD",
            field="invoice.number",
            score=header.get("invoice", {}).get("number", {}).get("confidence", 0.0)
        ))
    
    for i, row in enumerate(rows):
        if row.qty.confidence < 0.6:
            warnings.append(Warning(
                code="LOW_CONF_FIELD",
                field=f"lines[{i}].qty",
                score=row.qty.confidence
            ))
        if row.unitPrice.confidence < 0.6:
            warnings.append(Warning(
                code="LOW_CONF_FIELD",
                field=f"lines[{i}].unitPrice",
                score=row.unitPrice.confidence
            ))
    
    return warnings


def build_response(header, table, quality, hashes, raw_bytes=None, image_bgr=None, extracted_totals=None):
    """Build the final OCR response."""
    rows = table.get("rows", [])
    
    # Recompute totals from line items
    computed_totals = recompute_and_summarize(rows)
    
    # Map "taxable" to "net" in extracted_totals for consistency
    if extracted_totals and "taxable" in extracted_totals:
        extracted_totals["net"] = extracted_totals["taxable"]
    
    # Use extracted totals if available (from page 2), otherwise use computed
    # Extracted totals are more accurate as they come directly from the document
    if extracted_totals:
        totals_dict = {
            "net": extracted_totals.get("net", computed_totals["net"]),
            "tax": extracted_totals.get("tax", computed_totals["tax"]),
            "gross": extracted_totals.get("gross", computed_totals["gross"]),
            "cgst": extracted_totals.get("cgst", 0.0),
            "sgst": extracted_totals.get("sgst", 0.0),
            "igst": extracted_totals.get("igst", 0.0)
        }
        
        # If tax breakdown not in extracted, split from total tax
        if not any(k in extracted_totals for k in ["cgst", "sgst", "igst"]):
            place_of_supply = header.get("invoice", {}).get("placeOfSupply")
            totals_dict = split_tax_breakdown(totals_dict, place_of_supply)
    else:
        # No extracted totals, use computed and split tax
        place_of_supply = header.get("invoice", {}).get("placeOfSupply")
        totals_dict = split_tax_breakdown(computed_totals, place_of_supply)
    
    # Reconcile: compare computed vs extracted to find discrepancies
    reconciled, round_off = reconcile_totals(computed_totals, extracted_totals or {})
    
    # Use extracted round_off if available, otherwise use computed delta
    if extracted_totals and "round_off" in extracted_totals:
        round_off = extracted_totals["round_off"]
    
    # Build totals info
    totals_info = TotalsInfo(
        net=totals_dict.get("net", 0.0),
        tax=totals_dict.get("tax", 0.0),
        gross=totals_dict.get("gross", 0.0),
        cgst=totals_dict.get("cgst", 0.0),
        sgst=totals_dict.get("sgst", 0.0),
        igst=totals_dict.get("igst", 0.0),
        confidence=0.8,
        reconciled=reconciled,
        roundOffDelta=round_off
    )
    
    # Build meta info
    quality_metrics = QualityMetrics(
        focus=quality.get("focus", 0.0),
        glare=quality.get("glare", 0.0),
        skewDeg=quality.get("skewDeg", 0.0),
        resolution=quality.get("resolution", [0, 0])
    )
    
    meta = MetaInfo(
        ocrConfidence=avg_conf(rows),
        quality=quality_metrics,
        duplicateLikely=False,  # Could be set from database lookup
        uploadHash=hashes.get("sha256", ""),
        phash=hashes.get("phash", "")
    )
    
    # Generate warnings
    warnings = generate_warnings(header, rows, quality)
    
    # Build seller/buyer info
    from ..schemas import EntityInfo, InvoiceInfo, InvoiceNumber, InvoiceDate
    
    seller_data = header.get("seller", {})
    buyer_data = header.get("buyer", {})
    invoice_data = header.get("invoice", {})
    
    seller = EntityInfo(
        name=seller_data.get("name"),
        gstin=seller_data.get("gstin"),
        address=seller_data.get("address"),
        confidence=seller_data.get("confidence", 0.0),
        bbox=seller_data.get("bbox")
    ) if seller_data.get("name") or seller_data.get("gstin") else None
    
    buyer = EntityInfo(
        name=buyer_data.get("name"),
        gstin=buyer_data.get("gstin"),
        address=buyer_data.get("address"),
        confidence=buyer_data.get("confidence", 0.0),
        bbox=buyer_data.get("bbox")
    ) if buyer_data.get("name") or buyer_data.get("gstin") else None
    
    inv_num_data = invoice_data.get("number", {})
    inv_date_data = invoice_data.get("date", {})
    
    invoice = InvoiceInfo(
        number=InvoiceNumber(
            value=inv_num_data.get("value"),
            confidence=inv_num_data.get("confidence", 0.0),
            bbox=inv_num_data.get("bbox"),
            alt=inv_num_data.get("alt", [])
        ),
        date=InvoiceDate(
            value=inv_date_data.get("value"),
            confidence=inv_date_data.get("confidence", 0.0),
            raw=inv_date_data.get("raw")
        ),
        placeOfSupply=invoice_data.get("placeOfSupply")
    ) if invoice_data else None
    
    # Convert Pydantic models to dicts for validation
    def to_dict(obj):
        """Convert Pydantic model to dict."""
        if obj is None:
            return None
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        return obj
    
    # Extract full text from all tokens
    from ..schemas import FullTextToken
    all_tokens = header.get("allTokens", [])
    full_text_tokens = []
    for token in all_tokens:
        full_text_tokens.append(FullTextToken(
            text=token.get("text", ""),
            confidence=token.get("conf", 0.0),
            bbox=token.get("bbox", []),
            handwritten=token.get("handwritten"),
            hw_score=token.get("hw_score")
        ))
    
    return {
        "meta": to_dict(meta),
        "seller": to_dict(seller),
        "buyer": to_dict(buyer),
        "invoice": to_dict(invoice),
        "lines": [to_dict(r) for r in rows],
        "totals": to_dict(totals_info),
        "warnings": [to_dict(w) for w in warnings],
        "fullText": [to_dict(t) for t in full_text_tokens]
    }

