import frappe


def find_matching_company(supplier_name):
    """
    Check whether the supplier extracted from the customer PO
    (the party the PO is addressed to) matches one of our
    ERPNext Companies.

    Returns:
        dict: {"name": str, "match_confidence": float} or None
    """

    if not supplier_name:
        return None

    supplier_name = supplier_name.strip()

    # 1. Exact company_name match - highest confidence
    company = frappe.db.get_value(
        "Company",
        {"company_name": supplier_name},
        "name"
    )

    if company:
        return {
            "name": company,
            "match_confidence": 100.0
        }

    # 2. Exact match on the Company document name
    company = frappe.db.exists("Company", supplier_name)

    if company:
        return {
            "name": company,
            "match_confidence": 95.0
        }

    # 3. Case-insensitive LIKE match - unique match only
    companies = frappe.get_all(
        "Company",
        filters={
            "company_name": ["like", f"%{supplier_name}%"]
        },
        fields=["name", "company_name"],
        limit=10
    )

    # Never guess between multiple companies
    if len(companies) == 1:
        return {
            "name": companies[0].name,
            "match_confidence": 80.0
        }

    return None
