from po_ai_automation.services.company_service import (
    find_company_by_gstin,
    find_matching_company
)
from po_ai_automation.services.customer_service import (
    find_customer_by_gstin,
    find_customer_with_confidence
)
from po_ai_automation.services.item_service import (
    find_item_by_code,
    find_item_by_customer_ref
)


def validate_po_data(po_data):

    errors = []

    # -------------------------
    # Customer
    # -------------------------

    customer_name = po_data.get("customer_name")

    customer_match = find_customer_with_confidence(customer_name)

    if not customer_match:
        customer_match = find_customer_by_gstin(
            po_data.get("customer_gstin")
        )

    customer = customer_match["name"] if customer_match else None

    if not customer:
        errors.append(
            f"Customer not found: {customer_name}"
        )

    # -------------------------
    # Supplier / Our Company
    # -------------------------
    #
    # The supplier on a customer PO is the party the PO is
    # addressed to - it must be one of OUR ERPNext Companies.
    # This confirms the PO is actually meant for us.

    supplier_name = po_data.get("supplier_name")

    company_match = find_matching_company(supplier_name)

    if not company_match:
        company_match = find_company_by_gstin(
            po_data.get("supplier_gstin")
        )

    if not supplier_name:
        if not company_match:
            errors.append(
                "Supplier / our company could not be "
                "determined from the PO."
            )

    elif not company_match:
        errors.append(
            "This PO does not appear to be for our company. "
            f"Supplier on PO does not match any Company: "
            f"{supplier_name}"
        )

    # -------------------------
    # PO Number
    # -------------------------

    if not po_data.get("po_number"):
        errors.append(
            "Customer PO Number is missing."
        )

    # -------------------------
    # PO Date
    # -------------------------

    if not po_data.get("po_date"):
        errors.append(
            "PO Date is missing."
        )

    # -------------------------
    # Currency
    # -------------------------

    if not po_data.get("currency"):
        errors.append(
            "Currency is missing."
        )

    # -------------------------
    # Items
    # -------------------------

    items = po_data.get("items") or []

    if not items:
        errors.append(
            "No items were found in the PO."
        )

    validated_items = []

    for index, item in enumerate(items, start=1):

        description = item.get("description")
        item_code = item.get("item_code")

        item_match = find_item_by_code(item_code)

        if not item_match:
            item_match = find_item_by_customer_ref(
                item_code,
                customer
            )

        if not item_match:
            errors.append(
                f"Item {index} not found for item code: "
                f"{item_code or 'not provided'}"
            )

        validated_items.append({
            "erpnext_item": (
                item_match["name"] if item_match else None
            ),
            "description": description,
            "item_code": item_code,
            "qty": item.get("qty"),
            "uom": item.get("uom"),
            "rate": item.get("rate"),
            "amount": item.get("amount"),
            "match_confidence": (
                item_match["match_confidence"]
                if item_match
                else 0.0
            ),
            "validation_status": (
                "Matched" if item_match else "Failed"
            ),
        })

    # -------------------------
    # Overall AI Confidence
    # -------------------------

    confidence = calculate_confidence(
        po_data,
        customer_match,
        company_match,
        validated_items
    )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "customer": customer,
        "customer_match_confidence": (
            customer_match["match_confidence"]
            if customer_match
            else 0.0
        ),
        "company": company_match["name"] if company_match else None,
        "company_match_confidence": (
            company_match["match_confidence"]
            if company_match
            else 0.0
        ),
        "items": validated_items,
        "confidence": confidence
    }


def calculate_confidence(
    po_data,
    customer_match,
    company_match,
    validated_items
):
    """
    Calculate an overall AI extraction + master match
    confidence score between 0 and 100.
    """

    # -------------------------
    # Extracted header fields (max 70)
    # -------------------------

    field_weights = {
        "customer_name": 15,
        "supplier_name": 10,
        "po_number": 10,
        "po_date": 10,
        "delivery_date": 5,
        "currency": 10,
        "grand_total": 10,
    }

    score = 0.0

    for fieldname, weight in field_weights.items():
        if po_data.get(fieldname):
            score += weight

    # -------------------------
    # Customer master match (max 15)
    # -------------------------

    if customer_match:
        score += 15 * (customer_match["match_confidence"] / 100)

    # -------------------------
    # Supplier / our company match (max 5)
    # -------------------------

    if company_match:
        score += 5 * (company_match["match_confidence"] / 100)

    # -------------------------
    # Item master matches (max 20)
    # -------------------------

    if validated_items:
        average_match = (
            sum(item["match_confidence"] for item in validated_items)
            / len(validated_items)
        )
        score += 20 * (average_match / 100)

    return round(min(score, 100.0), 2)
