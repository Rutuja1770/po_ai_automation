import re

import frappe

from po_ai_automation.services.gstin_service import (
    find_master_by_gstin,
)


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

    normalized_supplier = normalize_company_name(supplier_name)
    if normalized_supplier:
        companies = frappe.get_all(
            "Company",
            fields=["name", "company_name"],
        )
        matches = {
            company.name
            for company in companies
            if normalize_company_name(company.company_name) == normalized_supplier
            or normalize_company_name(company.name) == normalized_supplier
        }

        if len(matches) == 1:
            return {
                "name": matches.pop(),
                "match_confidence": 90.0,
            }

    return None


def normalize_company_name(name):
    if not name:
        return ""

    normalized = str(name).strip().lower()
    normalized = re.sub(r"\bprivate\s+limited\b", "pvt ltd", normalized)
    normalized = re.sub(r"\bpvt\.?\s*limited\b", "pvt ltd", normalized)
    normalized = re.sub(r"\bpvt\b", "pvt", normalized)
    normalized = re.sub(r"\blimited\b", "ltd", normalized)
    return re.sub(r"[^a-z0-9]", "", normalized)


def find_company_by_gstin(gstin):
    """Find an ERPNext Company by an exact GSTIN when uniquely matched."""

    return find_master_by_gstin("Company", gstin)


def find_company_for_po(supplier_name, gstin):
    """Try GSTIN first, then use the existing name match as a fallback."""

    if gstin and str(gstin).strip():
        company = find_company_by_gstin(gstin)

        if company:
            return company

    return find_matching_company(supplier_name)
