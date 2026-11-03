import re

import frappe


def find_master_by_gstin(doctype, gstin):
    """
    Find exactly one Customer or Company by an exact GSTIN/tax ID.
    """

    normalized_gstin = normalize_gstin(gstin)

    if not normalized_gstin:
        return None

    meta = frappe.get_meta(doctype)
    gstin_fields = [
        fieldname
        for fieldname in ("gstin", "tax_id")
        if meta.has_field(fieldname)
    ]

    matches = set()

    for fieldname in gstin_fields:
        rows = frappe.get_all(
            doctype,
            filters={fieldname: normalized_gstin},
            fields=["name"],
            limit=2,
        )
        matches.update(row.name for row in rows)

    if len(matches) != 1:
        return None

    return {
        "name": matches.pop(),
        "match_confidence": 100.0,
        "match_method": "gstin",
    }


def normalize_gstin(gstin):
    if not gstin:
        return ""

    return re.sub(r"[^A-Z0-9]", "", str(gstin).upper())
