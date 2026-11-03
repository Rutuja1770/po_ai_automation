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


def find_item_by_code(item_code):
    """
    Find an ERPNext Item using an exact ERPNext item code.

    Returns the Item name and match confidence, or None.
    """

    if not item_code:
        return None

    item_code = str(item_code).strip()

    if not item_code:
        return None

    item = frappe.db.get_value(
        "Item",
        {"item_code": item_code},
        "name"
    )

    if item:
        return {
            "name": item,
            "match_confidence": 95.0
        }

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


def find_item_by_customer_ref(item_code, customer):
    """
    Find an ERPNext Item via the Item -> Customer Details
    table (ref_code) for the given customer.

    Only exact customer_name + ref_code rows are considered.
    Never guesses between multiple matching Items.

    Returns:
        dict: {"name": str, "match_confidence": float} or None
    """

    if not item_code or not customer:
        return None

    item_code = str(item_code).strip()

    if not item_code:
        return None

    rows = frappe.get_all(
        "Item Customer Detail",
        filters={
            "parenttype": "Item",
            "customer_name": customer,
            "ref_code": item_code,
        },
        fields=["parent"],
    )

    parents = {row.parent for row in rows}

    # Never blindly select between multiple matches
    if len(parents) != 1:
        return None

    return {
        "name": parents.pop(),
        "match_confidence": 85.0,
    }


def get_standard_selling_price(item_code, currency=None, uom=None):
    """
    Return an item's generic selling price from the selling Price List
    configured in Selling Settings when exactly one currently applicable
    price exists.
    """

    if not item_code or not currency:
        return None

    price_list_name = frappe.db.get_single_value(
        "Selling Settings",
        "selling_price_list",
    )

    if not price_list_name:
        return None

    price_lists = frappe.get_all(
        "Price List",
        filters={
            "name": price_list_name,
            "selling": 1,
            "enabled": 1,
        },
        fields=["name", "currency"],
        limit=1,
    )

    if not price_lists:
        return None

    price_list = price_lists[0]

    if price_list.currency != currency:
        return None

    today = frappe.utils.getdate()
    prices = frappe.get_all(
        "Item Price",
        filters={
            "item_code": item_code,
            "price_list": price_list.name,
            "selling": 1,
        },
        fields=[
            "price_list_rate",
            "currency",
            "uom",
            "valid_from",
            "valid_upto",
            "customer",
            "supplier",
        ],
    )

    applicable_prices = []

    for price in prices:
        if price.customer or price.supplier:
            continue

        if price.currency != currency:
            continue

        if price.valid_from and frappe.utils.getdate(price.valid_from) > today:
            continue

        if price.valid_upto and frappe.utils.getdate(price.valid_upto) < today:
            continue

        if uom:
            if price.uom not in (uom, None, ""):
                continue
        elif price.uom:
            continue

        applicable_prices.append(price)

    if uom:
        exact_uom_prices = [
            price for price in applicable_prices if price.uom == uom
        ]
        if exact_uom_prices:
            applicable_prices = exact_uom_prices

    if len(applicable_prices) != 1:
        return None

    return applicable_prices[0].price_list_rate
