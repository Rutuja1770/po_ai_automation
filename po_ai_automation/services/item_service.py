import frappe


def find_item(description):
    """
    Find an ERPNext Item using the AI-extracted description.
    Returns the Item name or None.
    """

    match = find_item_with_confidence(description)

    if match:
        return match["name"]

    return None


def find_item_with_confidence(description):
    """
    Find an ERPNext Item and return the match confidence.

    Returns:
        dict: {"name": str, "match_confidence": float} or None
    """

    if not description:
        return None

    description = description.strip()

    # 1. Exact Item Name match - highest confidence
    item = frappe.db.get_value(
        "Item",
        {"item_name": description},
        "name"
    )

    if item:
        return {
            "name": item,
            "match_confidence": 100.0
        }

    # 2. Exact Item Code match
    item = frappe.db.get_value(
        "Item",
        {"item_code": description},
        "name"
    )

    if item:
        return {
            "name": item,
            "match_confidence": 95.0
        }

    # 3. Partial Item Name search
    items = frappe.get_all(
        "Item",
        filters={
            "item_name": ["like", f"%{description}%"]
        },
        fields=["name", "item_name"],
        limit=10
    )

    # Never blindly select between multiple matches
    if len(items) == 1:
        return {
            "name": items[0].name,
            "match_confidence": 80.0
        }

    return None
