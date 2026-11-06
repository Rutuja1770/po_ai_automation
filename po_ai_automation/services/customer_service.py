import frappe

from po_ai_automation.services.gstin_service import (
    find_master_by_gstin,
)


def find_customer(customer_name):
    """
    Find an ERPNext Customer from the name extracted by AI.
    Returns the Customer name or None.
    """

    match = find_customer_with_confidence(customer_name)

    if match:
        return match["name"]

    return None


def find_customer_by_gstin(gstin):
    """Find an ERPNext Customer by an exact GSTIN when uniquely matched."""

    return find_master_by_gstin("Customer", gstin)


def find_customer_for_po(customer_name, gstin):
    """Try GSTIN first, then use the existing name match as a fallback."""

    if gstin and str(gstin).strip():
        customer = find_customer_by_gstin(gstin)

        if customer:
            return customer

    return find_customer_with_confidence(customer_name)


def find_customer_with_confidence(customer_name):
    """
    Find an ERPNext Customer and return the match confidence.

    Returns:
        dict: {"name": str, "match_confidence": float} or None
    """

    if not customer_name:
        return None

    customer_name = customer_name.strip()

    # 1. Exact match - highest confidence
    customer = frappe.db.get_value(
        "Customer",
        {"customer_name": customer_name},
        "name"
    )

    if customer:
        return {
            "name": customer,
            "match_confidence": 100.0
        }

    # 2. Case-insensitive LIKE match
    customers = frappe.get_all(
        "Customer",
        filters={
            "customer_name": ["like", f"%{customer_name}%"]
        },
        fields=["name", "customer_name"],
        limit=10
    )

    # Don't guess when multiple customers match
    if len(customers) == 1:
        return {
            "name": customers[0].name,
            "match_confidence": 80.0
        }

    return None
