from typing import Optional

# Required header fields
REQUIRED_HEADER = [
    "invoice_type", "ntn_cnic", "buyer_seller_name",
    "destination_address", "sale_type", "total_retail_price"
]

# Required item fields
REQUIRED_ITEM = [
    "hs_code", "product_code", "product_description",
    "rate", "uom", "quantity", "value_excl_st",
    "sales_tax", "retail_price", "total_values"
]

VALID_INVOICE_TYPES = [1, 2, 3, 4]


def validate_invoice(header: dict, items: list) -> dict:
    """
    Returns { valid: bool, errors: [str] }
    Plain English errors — not FBR's cryptic codes.
    """
    errors = []

    # Header checks
    for field in REQUIRED_HEADER:
        if not header.get(field) and header.get(field) != 0:
            errors.append(f"Missing required field: {field.replace('_', ' ').title()}")

    if header.get("invoice_type") not in VALID_INVOICE_TYPES:
        errors.append("Invoice Type must be 1 (Purchase), 2 (Sale), 3 (Debit Note), or 4 (Credit Note)")

    if not items:
        errors.append("Invoice must have at least one item")

    # Item checks
    for i, item in enumerate(items, 1):
        row = f"Row {i}"
        for field in REQUIRED_ITEM:
            if not item.get(field) and item.get(field) != 0:
                errors.append(f"{row}: Missing '{field.replace('_', ' ').title()}'")

        # HS Code must be exactly 8 characters
        hs = str(item.get("hs_code") or "")
        if hs and len(hs.replace(".", "")) != 8:
            errors.append(f"{row}: HS Code must be 8 digits (got '{hs}')")

        # Numeric checks
        for num_field in ["quantity", "rate", "value_excl_st", "retail_price"]:
            val = item.get(num_field)
            if val is not None:
                try:
                    if float(val) < 0:
                        errors.append(f"{row}: {num_field.replace('_', ' ').title()} cannot be negative")
                except (ValueError, TypeError):
                    errors.append(f"{row}: {num_field.replace('_', ' ').title()} must be a number")

        # Total values sanity check
        try:
            expected = float(item.get("value_excl_st") or 0) + float(item.get("sales_tax") or 0)
            actual = float(item.get("total_values") or 0)
            if abs(expected - actual) > 1:  # allow 1 rupee rounding
                errors.append(
                    f"{row}: Total Values ({actual}) doesn't match "
                    f"Value Excl. ST + Sales Tax ({expected:.2f})"
                )
        except (ValueError, TypeError):
            pass

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }
