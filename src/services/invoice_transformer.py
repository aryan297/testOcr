"""
Invoice Transformer - Converts raw OCR response to structured invoice format.
Uses robust anchor-based extraction with flexible regex patterns.
"""
import re
from typing import Dict, Any, List, Optional


def regex_get(pattern: str, text: str, flags=re.IGNORECASE) -> Optional[str]:
    """Extract text using regex pattern."""
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def normalize_amount(s: str) -> Optional[float]:
    """Normalize amount string to float."""
    if not s:
        return None
    s = s.replace('₹', '').replace(',', '').strip()
    s = re.sub(r'[^\d\.\-]', '', s)
    try:
        return round(float(s), 2)
    except:
        return None


def get_full_text_string(full_text: List[Dict]) -> str:
    """Convert fullText array to single string, preserving reading order."""
    if not full_text:
        return ""
    
    # Sort by y-coordinate (top to bottom), then x-coordinate (left to right)
    sorted_tokens = sorted(
        full_text,
        key=lambda t: (t.get('bbox', [[0, 0]])[0][1], t.get('bbox', [[0, 0]])[0][0])
    )
    
    # Join with spaces
    return " ".join(token.get('text', '') for token in sorted_tokens)


def extract_invoice_header(full_text_str: str) -> Dict[str, Any]:
    """Extract invoice header using flexible regex patterns."""
    header = {}
    
    # Invoice number - handle variations: "Invoice No.", "Invoice No:", "Invoice No.-"
    header['invoiceNumber'] = regex_get(r"Invoice\s*No\.?\s*[:\.\-]?\s*([A-Za-z0-9\/\-]+)", full_text_str)
    
    # Invoice date - handle "Date:", "Dated:", "Date -", etc.
    header['invoiceDate'] = regex_get(r"\b(?:Date|Dated)\s*[:\.\-]?\s*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})", full_text_str)
    
    # Place of supply
    header['placeOfSupply'] = regex_get(r"Place\s*of\s*Supply\s*[:\.\-]?\s*([^\n\r]+)", full_text_str)
    
    # Reference number and date
    header['referenceNo'] = regex_get(r"Reference\s*No\.?\s*[:\.\-]?\s*([A-Za-z0-9\/\-]+)", full_text_str)
    header['referenceDate'] = regex_get(r"Reference.*?([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})", full_text_str)
    
    # IRN (long alphanumeric hash)
    header['irn'] = regex_get(r"\bIRN\s*[:\.\-]?\s*([a-f0-9\-]{10,})", full_text_str)
    
    # Acknowledgement
    ack_no = regex_get(r"Ack(?:nowledge)?(?:ment)?\s*(?:No\.?)?\s*[:\.\-]?\s*([0-9]+)", full_text_str)
    ack_date = regex_get(r"Ack\s*Date\s*[:\.\-]?\s*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})", full_text_str)
    
    if ack_no:
        header['acknowledgement'] = {
            'ackNo': ack_no,
            'ackDate': ack_date
        }
    else:
        header['acknowledgement'] = None
    
    return header


def extract_seller(full_text_str: str) -> Dict[str, Any]:
    """Extract seller information using flexible patterns."""
    seller = {}
    
    # Try "For:" pattern (common in many invoices)
    seller_block = regex_get(
        r"(For:.*?)(?:Authorized\s*Signatory|Bill\s*To|Invoice\s*Details)",
        full_text_str,
        flags=re.IGNORECASE | re.DOTALL
    )
    
    if seller_block:
        seller['raw'] = seller_block
        # Extract name after "For:"
        name = regex_get(r"For\s*[:\-]?\s*([A-Z &\.\w\/]+)", seller_block)
        if name:
            seller['name'] = name
    else:
        # Fallback: try "M/s" pattern
        seller_block = regex_get(
            r'(M/s\s+.*?)(?:Buyer|Bill\s*To|GSTIN/UIN)',
            full_text_str,
            flags=re.IGNORECASE | re.DOTALL
        )
        if seller_block:
            seller['raw'] = seller_block
            name = regex_get(r'M/s\s+([^\n]+)', seller_block)
            if name:
                seller['name'] = name
    
    # Extract GSTIN (first occurrence is usually seller)
    gstin = regex_get(r"GSTIN\s*[:\.\-]?\s*([A-Z0-9]{15})", full_text_str)
    if gstin:
        seller['gstin'] = gstin
    
    # Extract state
    state_match = re.search(
        r"State\s*Name\s*[:\-]?\s*([A-Za-z\s]+),?\s*Code\s*[:\-]?\s*([0-9]{2})",
        full_text_str,
        re.IGNORECASE
    )
    if state_match:
        seller['state'] = state_match.group(1).strip()
        seller['stateCode'] = state_match.group(2)
    
    # Extract unit
    unit = regex_get(r"Unit\s+of\s+([^\n]+)", full_text_str)
    if unit:
        seller['unit'] = unit
    
    return seller


def extract_buyer(full_text_str: str) -> Dict[str, Any]:
    """Extract buyer information using flexible patterns."""
    buyer = {}
    
    # Block after 'Bill To' up to 'Invoice Details' or 'Invoice No'
    buyer_match = re.search(
        r"Bill\s*To(.*?)(?:Invoice\s*Details|Invoice\s*No|Invoice\s*No\.)",
        full_text_str,
        flags=re.IGNORECASE | re.DOTALL
    )
    
    if buyer_match:
        block = buyer_match.group(1).strip()
        buyer['raw'] = " ".join(block.split())
        
        # Name (first non-empty line)
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if lines:
            buyer['name'] = lines[0]
            
            # Find contact and GSTIN
            for ln in lines:
                if re.search(r'GSTIN', ln, re.IGNORECASE):
                    g = re.search(r"GSTIN.*?([A-Z0-9]{15})", ln, re.IGNORECASE)
                    if g:
                        buyer['gstin'] = g.group(1)
                if re.search(r'Contact', ln, re.IGNORECASE) or re.search(r'\+?\d{7,}', ln):
                    buyer['contact'] = re.sub(r'Contact\s*No\.?:?\s*', '', ln, flags=re.IGNORECASE).strip()
    else:
        # Fallback: find 'GSTIN Number:' block (second GSTIN is usually buyer)
        all_gstins = re.findall(r"GSTIN.*?([A-Z0-9]{15})", full_text_str, re.IGNORECASE)
        if len(all_gstins) > 1:
            buyer['gstin'] = all_gstins[1]
    
    return buyer


def extract_entity(entity_data: Dict, full_text: List[Dict], entity_type='seller') -> Dict[str, Any]:
    """Extract seller or buyer information."""
    if not entity_data:
        return {}
    
    name = entity_data.get('name') or ''
    gstin = entity_data.get('gstin') or ''
    address = entity_data.get('address') or ''
    
    # Extract state and code from address or fullText
    state = None
    state_code = None
    
    # Look for "State Name : Bihar, Code : 10" pattern
    for token in full_text:
        text = token.get('text', '')
        state_match = re.search(r'State Name\s*:\s*([^,]+),\s*Code\s*:\s*(\d{2})', text, re.I)
        if state_match:
            state = state_match.group(1).strip()
            state_code = state_match.group(2)
            break
        # Alternative pattern
        state_match = re.search(r'([A-Za-z]+),\s*Code\s*:\s*(\d{2})', text)
        if state_match:
            state = state_match.group(1).strip()
            state_code = state_match.group(2)
    
    # Extract unit (for seller)
    unit = None
    if entity_type == 'seller':
        for token in full_text:
            text = token.get('text', '')
            if 'Unit of' in text:
                unit = text
                break
    
    # Extract contact (for buyer)
    contact = None
    if entity_type == 'buyer':
        for token in full_text:
            text = token.get('text', '')
            if 'S/O' in text or 's/o' in text.lower():
                contact = text
                break
    
    result = {
        'name': name,
        'address': address,
        'gstin': gstin,
        'state': state,
        'stateCode': state_code
    }
    
    if unit:
        result['unit'] = unit
    if contact:
        result['contact'] = contact
    
    return result


def extract_line_items(full_text_str: str) -> List[Dict[str, Any]]:
    """Extract line items using flexible heuristic parsing."""
    items = []
    
    # Isolate the item table between common headings
    table_match = re.search(
        r"#\s*Item\s*name.*?(?:Invoice\s*Amount\s*In\s*Words|Total\s+₹|Sub\s*Total)",
        full_text_str,
        flags=re.IGNORECASE | re.DOTALL
    )
    
    if not table_match:
        # Fallback: search for 'Quantity Unit Price' or 'Description of Goods'
        table_match = re.search(
            r"(?:Quantity\s*Unit\s*Price|Description\s*of\s*Goods).*?(?:Invoice\s*Amount\s*In\s*Words|Total\s+₹|Sub\s*Total)",
            full_text_str,
            flags=re.IGNORECASE | re.DOTALL
        )
    
    if not table_match:
        return items
    
    block = table_match.group(0)
    
    # Split by lines and parse heuristically
    lines = [ln.strip() for ln in block.split('\n') if ln.strip()]
    
    row = {}
    for ln in lines:
        # Start of a new item if we see a line starting with a number
        if re.match(r"^\d+\b", ln):
            # Flush previous row
            if row:
                items.append(row)
                row = {}
            # Remove leading index
            ln2 = re.sub(r"^\d+\s*", "", ln)
            row['description'] = ln2
            continue
        
        # Detect HSN (4-8 digit code)
        h = re.search(r"\b(\d{4,8})\b", ln)
        if h and 'hsn' not in row:
            row['hsn'] = h.group(1)
        
        # Detect quantity with unit like '149 Bag' or '13 PCS'
        q = re.search(r"(\d{1,6})\s*(PCS|Bag|BAG|KG|Kg|Nos|NOS|Bag(?:s)?)", ln, flags=re.IGNORECASE)
        if q and 'quantity' not in row:
            row['quantity'] = f"{q.group(1)} {q.group(2).upper()}"
        
        # Detect unit price or amount (₹)
        amt = re.search(r"₹\s*([0-9\.,]+)", ln)
        if amt:
            candidate = normalize_amount(amt.group(1))
            # If item already has 'unitPrice' absent → set unitPrice; else if taxable missing -> set taxable
            if 'unitPrice' not in row:
                row['unitPrice'] = candidate
            elif 'taxableValue' not in row:
                row['taxableValue'] = candidate
        
        # Detect percent GST inside parentheses like (5.0%)
        gstm = re.search(r"\(?([0-9]{1,2}(?:\.[0-9])?)\s*%\)?", ln)
        if gstm and 'gstRate' not in row:
            row['gstRate'] = float(gstm.group(1))
    
    # Flush last row
    if row:
        items.append(row)
    
    # Post-normalize common fields & convert strings to numbers
    for it in items:
        if 'unitPrice' in it and isinstance(it['unitPrice'], str):
            it['unitPrice'] = normalize_amount(it['unitPrice'])
        if 'taxableValue' in it and isinstance(it['taxableValue'], str):
            it['taxableValue'] = normalize_amount(it['taxableValue'])
        # Set default GST rate if missing
        if 'gstRate' not in it:
            it['gstRate'] = 18.0  # Default 18%
        # Split GST into CGST/SGST
        if 'gstRate' in it:
            it['cgstRatePct'] = it['gstRate'] / 2
            it['sgstRatePct'] = it['gstRate'] / 2
    
    return items


def extract_items(ocr_response: Dict) -> List[Dict[str, Any]]:
    """Extract line items from OCR response."""
    lines = ocr_response.get('lines', [])
    full_text = ocr_response.get('fullText', [])
    
    items = []
    
    # Build a map of descriptions to find better matches
    description_map = {}
    for token in full_text:
        text = token.get('text', '')
        # Look for product codes/names
        if re.match(r'^[A-Z0-9\s\.]+$', text) and len(text) > 3 and len(text) < 30:
            description_map[text] = token
    
    for idx, line in enumerate(lines):
        desc = line.get('description', {}).get('value', '') or ''
        qty_obj = line.get('qty', {}) or {}
        qty_val = qty_obj.get('value', 0) or 0
        qty_unit = qty_obj.get('unit') or 'PCS'
        
        # Try to find better description from fullText
        better_desc = desc
        for key in description_map:
            if key in desc or desc in key:
                better_desc = key
                break
        
        # Extract rate and taxable value
        rate = line.get('unitPrice', {}).get('value', 0.0) or 0.0
        
        # Calculate taxable value (qty * rate)
        taxable_value = qty_val * rate
        
        # Get GST rates
        gst_rate = line.get('gstRate', {}).get('value', 0.0) or 0.0
        cgst_rate = int(gst_rate * 100 / 2) if gst_rate else 9
        sgst_rate = cgst_rate
        
        # Get HSN
        hsn = line.get('hsn') or '48239019'  # Default HSN
        
        # Ensure qty_unit is not None
        if not qty_unit:
            qty_unit = 'PCS'
        
        # Ensure description is not empty
        if not better_desc:
            better_desc = f"Item {idx + 1}"
        
        item = {
            'slNo': idx + 1,
            'description': better_desc,
            'quantity': f"{int(qty_val)} {qty_unit.upper()}",
            'rate': float(rate),
            'per': qty_unit.upper(),
            'taxableValue': round(taxable_value, 2),
            'hsn': str(hsn),
            'cgstRate': cgst_rate,
            'sgstRate': sgst_rate
        }
        
        items.append(item)
    
    return items


def extract_totals_from_text(full_text_str: str) -> Dict[str, Any]:
    """Extract totals using flexible patterns."""
    totals = {}
    
    # Sub Total
    sub_total = regex_get(r"Sub\s*Total\s*₹?\s*([0-9\.,]+)", full_text_str)
    totals['subTotal'] = normalize_amount(sub_total) if sub_total else None
    
    # SGST
    sgst = regex_get(r"SGST@[\d\.]*%?\s*₹?\s*([0-9\.,]+)", full_text_str)
    totals['sgst'] = normalize_amount(sgst) if sgst else None
    
    # CGST
    cgst = regex_get(r"CGST@[\d\.]*%?\s*₹?\s*([0-9\.,]+)", full_text_str)
    totals['cgst'] = normalize_amount(cgst) if cgst else None
    
    # Round off (can be negative)
    round_off = regex_get(r"Round\s*[Oo]ff\s*[-]?\s*₹?\s*([0-9\.,\-]+)", full_text_str)
    totals['roundOff'] = normalize_amount(round_off) if round_off else 0.0
    
    # Total amount
    total = regex_get(r"Total\s*₹\s*([0-9\.,]+)", full_text_str)
    if not total:
        total = regex_get(r"Total\s*([0-9\.,]+)", full_text_str)
    totals['totalAmount'] = normalize_amount(total) if total else None
    
    # Total quantity
    totals['totalQty'] = regex_get(r"Total\s+([0-9]+\s*(?:PCS|Bag|BAG|KG|Nos)?)", full_text_str)
    
    # Taxable value (from sub total or explicit field)
    if not totals.get('subTotal'):
        taxable = regex_get(r"Taxable\s*Value\s*₹?\s*([0-9\.,]+)", full_text_str)
        totals['taxableValue'] = normalize_amount(taxable) if taxable else None
    else:
        totals['taxableValue'] = totals['subTotal']
    
    # Total tax
    if totals.get('cgst') and totals.get('sgst'):
        totals['totalTax'] = totals['cgst'] + totals['sgst']
    else:
        totals['totalTax'] = None
    
    # Amount in words
    totals['totalInWords'] = regex_get(
        r"Invoice\s*Amount\s*In\s*Words(?:\s*[:\-\n])*\s*(.+?)(?:Terms\s*And\s*Conditions|Sub\s*Total|For\s*:)",
        full_text_str,
        flags=re.IGNORECASE | re.DOTALL
    )
    
    # Tax in words (if present)
    totals['taxInWords'] = regex_get(
        r"Tax\s*Amount\s*\(in\s*words\)\s*:?\s*INR\s+([^\.]+)",
        full_text_str
    )
    
    return totals


def extract_totals(ocr_response: Dict) -> Dict[str, Any]:
    """Extract totals and summary information."""
    totals_obj = ocr_response.get('totals', {}) or {}
    full_text = ocr_response.get('fullText', []) or []
    
    # Get values from structured totals (handle None values)
    net = totals_obj.get('net') or 0.0
    tax = totals_obj.get('tax') or 0.0
    gross = totals_obj.get('gross') or 0.0
    cgst = totals_obj.get('cgst') or 0.0
    sgst = totals_obj.get('sgst') or 0.0
    round_off = totals_obj.get('roundOffDelta') or 0.0
    
    # Extract total quantity
    total_qty = None
    for token in full_text:
        text = token.get('text', '')
        qty_match = re.search(r'(\d+)\s*(PCS|pcs)', text)
        if qty_match and 'Total' in full_text[max(0, full_text.index(token) - 1)].get('text', ''):
            total_qty = f"{qty_match.group(1)} {qty_match.group(2).upper()}"
            break
    
    # Extract amount in words
    total_in_words = None
    tax_in_words = None
    
    for token in full_text:
        text = token.get('text', '')
        if 'INR' in text and 'Only' in text:
            if 'Thousand' in text and not 'Hundred' in text:
                tax_in_words = text
            else:
                total_in_words = text
    
    return {
        'roundOff': round_off,
        'totalQty': total_qty,
        'totalAmount': gross,
        'taxableValue': net,
        'cgst': cgst,
        'sgst': sgst,
        'totalTax': tax,
        'totalInWords': total_in_words,
        'taxInWords': tax_in_words
    }


def extract_meta(ocr_response: Dict) -> Dict[str, Any]:
    """Extract metadata."""
    full_text = ocr_response.get('fullText', [])
    
    # Check if computer generated
    is_computer_generated = any(
        'Computer Generated' in token.get('text', '')
        for token in full_text
    )
    
    # Extract document type
    doc_type = 'Tax Invoice'
    for token in full_text:
        if 'Invoice' in token.get('text', ''):
            doc_type = token.get('text', 'Tax Invoice')
            break
    
    # Extract signatory
    signatory = None
    for token in full_text:
        text = token.get('text', '')
        if 'M/s' in text or 'for' in text.lower():
            signatory = text
    
    return {
        'documentType': doc_type,
        'isComputerGenerated': is_computer_generated,
        'authorisedSignatory': signatory
    }


def transform_invoice(ocr_response: Dict) -> Dict[str, Any]:
    """
    Transform raw OCR response to structured invoice format.
    
    Uses spatial parsing (bounding box geometry) for robust table extraction,
    with fallback to regex-based extraction.
    
    Args:
        ocr_response: Raw OCR response from /ocr/parse endpoint
    
    Returns:
        Structured invoice dictionary
    """
    try:
        full_text_tokens = ocr_response.get('fullText', []) or []
        
        # Try optimized extractor first (geometry + heuristics)
        try:
            from src.services.invoice_extractor import extract_invoice_structured
            print("Using optimized invoice extractor...")
            result = extract_invoice_structured(ocr_response)
            
            # Debug: show what was extracted
            print(f"Extractor returned: {len(result.get('items', []))} items")
            if result.get('items'):
                for i, item in enumerate(result['items'][:3], 1):
                    print(f"  Item {i}: desc={item.get('description')}, hsn={item.get('hsn')}, qty={item.get('quantity')}, taxable={item.get('taxableValue')}")
            
            # If extractor found items, use it
            if result.get('items'):
                print(f"✓ Using geometry extractor result")
                return result
            else:
                print("⚠ Extractor found no items, falling back to regex parser...")
        except Exception as e:
            print(f"Extractor failed: {e}, falling back to regex parser...")
            import traceback
            traceback.print_exc()
        
        # Fallback to regex-based extraction
        full_text_str = get_full_text_string(full_text_tokens)
        
        # Log full text for debugging (first 500 chars)
        print(f"Full text preview: {full_text_str[:500]}...")
        
        # Extract using flexible anchor-based methods
        invoice_info = extract_invoice_header(full_text_str)
        seller_info = extract_seller(full_text_str)
        buyer_info = extract_buyer(full_text_str)
        items = extract_line_items(full_text_str)
        totals = extract_totals_from_text(full_text_str)
        meta = extract_meta(ocr_response)
        
        return {
            'invoice': invoice_info,
            'seller': seller_info,
            'buyer': buyer_info,
            'items': items,
            'totals': totals,
            'meta': meta
        }
        
    except Exception as e:
        # Log error and return minimal structure
        print(f"Error transforming invoice: {e}")
        import traceback
        traceback.print_exc()
        return {
            'invoice': {},
            'seller': {},
            'buyer': {},
            'items': [],
            'totals': {},
            'meta': {},
            'error': str(e)
        }
