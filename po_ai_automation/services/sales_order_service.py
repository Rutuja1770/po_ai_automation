import re

import frappe
from frappe.contacts.doctype.address.address import get_default_address


def create_sales_order(po_data, validation_result):

    if not validation_result["valid"]:
        frappe.throw(
            "PO validation failed. "
            "Sales Order was not created."
        )

    customer = validation_result["customer"]

    sales_order = frappe.new_doc("Sales Order")

    sales_order.customer = customer

    # --------------------------------
    # Our company (from PO supplier)
    # --------------------------------

    company = validation_result.get("company")

    if company:
        sales_order.company = company
        if not sales_order.get("company_address"):
            sales_order.company_address = get_default_address(
                "Company",
                company,
            )

    # Customer PO information
    if po_data.get("po_number"):
        sales_order.po_no = po_data.get("po_number")

    po_date = po_data.get("po_date")
    if po_date:
        sales_order.po_date = po_date

    # Currency
    if po_data.get("currency"):
        sales_order.currency = po_data.get("currency")
    # --------------------------------
    # Delivery Date
    # --------------------------------

    delivery_date = po_data.get("delivery_date") or frappe.utils.nowdate()
    sales_order.delivery_date = delivery_date

    if (
        po_date
        and frappe.utils.getdate(delivery_date)
        < frappe.utils.getdate(frappe.utils.nowdate())
    ):
        sales_order.transaction_date = po_date

    # --------------------------------
    # Taxes and Charges
    # --------------------------------
    # ERPNext only fetches the tax template in the UI when a
    # customer is selected. A server-side insert never runs
    # that logic, so resolve the template here explicitly.

    taxes_template = get_taxes_and_charges_template(
        company=company,
        customer=customer,
        posting_date=po_data.get("po_date"),
    )

    if taxes_template:

        sales_order.taxes_and_charges = taxes_template

        tax_rows = get_taxes_and_charges_rows(taxes_template)

        if tax_rows:
            sales_order.extend("taxes", tax_rows)

    # Items
    for item in validation_result["items"]:

        row = sales_order.append(
            "items",
            {}
        )

        row.item_code = item["erpnext_item"]
        row.qty = item["qty"]
        row.rate = item["rate"]

        # --------------------------------
        # Source warehouse for stock items
        # --------------------------------
        # ERPNext requires a warehouse on every stock item
        # row, so resolve it automatically here.

        row.warehouse = get_source_warehouse(
            company,
            item["erpnext_item"]
        )

        if not row.warehouse and frappe.get_cached_value(
            "Item",
            item["erpnext_item"],
            "is_stock_item"
        ):
            frappe.throw(
                f"Source warehouse required for stock item "
                f"{item['erpnext_item']}. Set "
                f"'po_source_warehouse' in site_config.json "
                f"or a default warehouse on the Item."
            )

    sales_order.insert(
        ignore_permissions=True
    )

    return sales_order.name


def get_source_warehouse(company=None, item_code=None):
    """
    Resolve the source warehouse for an SO item row.

    Priority:
    1. po_source_warehouse in site_config.json
    2. Item Default default_warehouse for this company
    3. Any active non-group Warehouse of the company
       (preferring one named like "Stores")
    """

    # 1. Explicit site-config override
    warehouse = frappe.conf.get("po_source_warehouse")

    if warehouse and frappe.db.exists("Warehouse", warehouse):
        return warehouse

    # 2. Item-level default warehouse
    if item_code and company:
        warehouse = frappe.db.get_value(
            "Item Default",
            {
                "parent": item_code,
                "parenttype": "Item",
                "company": company,
                "default_warehouse": ["is", "set"],
            },
            "default_warehouse"
        )

        if warehouse:
            return warehouse

    # 3. Company warehouse fallback
    return get_company_default_warehouse(company)


def get_company_default_warehouse(company=None):
    """
    Pick an active, non-group warehouse for the company.
    Prefers warehouses named like 'Stores'.
    """

    filters = {
        "is_group": 0,
        "disabled": 0,
    }

    if company:
        filters["company"] = company

    warehouses = frappe.get_all(
        "Warehouse",
        filters=filters,
        fields=["name"],
        order_by="name",
        limit=20
    )

    if not warehouses:
        return None

    # Prefer a warehouse that looks like a stores/ main warehouse
    for warehouse in warehouses:
        name = warehouse.name.lower()

        if "stores" in name or "store" in name:
            return warehouse.name

    return warehouses[0].name


def get_taxes_and_charges_template(
    company=None,
    customer=None,
    posting_date=None
):
    """
    Resolve the Sales Taxes and Charges Template for the SO.

    Priority:
    1. po_sales_taxes_charges_template in site_config.json
    2. ERPNext Tax Rule for this customer/company/date
       (standard ERPNext party.set_taxes logic)
    3. Default template of the company (is_default = 1)
    4. Any enabled template belonging to the company
    """

    # 1. Explicit site-config override
    template = frappe.conf.get(
        "po_sales_taxes_charges_template"
    )

    if template and frappe.db.exists(
        "Sales Taxes and Charges Template",
        template
    ):
        log_tax_resolution("site_config override", template)
        return template

    # 2. Tax Rule based template (customer / group / company)
    if company and customer:

        try:
            from erpnext.accounts.party import set_taxes

            template = set_taxes(
                party=customer,
                party_type="Customer",
                posting_date=posting_date or frappe.utils.nowdate(),
                company=company,
            )

        except Exception:
            template = None

        if template and frappe.db.exists(
            "Sales Taxes and Charges Template",
            template
        ):
            log_tax_resolution("Tax Rule", template)
            return template

    # 3. Default template for the company
    if company:

        template = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {
                "is_default": 1,
                "company": company,
                "disabled": 0,
            },
            "name"
        )

        if template:
            log_tax_resolution("company default (is_default)", template)
            return template

        # 4. Any enabled template of the company
        template = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {
                "company": company,
                "disabled": 0,
            },
            "name",
            order_by="creation asc"
        )

        if template:
            log_tax_resolution("first enabled company template", template)
            return template

    log_tax_resolution(
        "no template found",
        None,
        detail={
            "company": company,
            "customer": customer,
            "templates_exist": frappe.db.count(
                "Sales Taxes and Charges Template"
            ),
        },
    )

    return None


def log_tax_resolution(source, template, detail=None):
    """
    Log how (or whether) the tax template was resolved so
    missing taxes on created Sales Orders can be debugged.
    """

    message = (
        f"PO AI Taxes: source={source} "
        f"template={template}"
    )

    if detail:
        message += f" detail={detail}"

    frappe.logger("po_ai_automation").info(message)


def get_taxes_and_charges_rows(template_name):
    """
    Return template tax rows, dropping structurally duplicate GST rows.
    """

    if not template_name:
        return []

    from erpnext.controllers.accounts_controller import (
        get_taxes_and_charges
    )

    rows = get_taxes_and_charges(
        "Sales Taxes and Charges Template",
        template_name
    ) or []

    unique_rows = []
    seen_gst_rows = set()
    duplicate_gst_rows = []

    for row in rows:
        signature = get_gst_tax_row_signature(row)
        if signature is None:
            unique_rows.append(row)
            continue

        if signature in seen_gst_rows:
            duplicate_gst_rows.append(row)
            continue

        seen_gst_rows.add(signature)
        unique_rows.append(row)

    if duplicate_gst_rows:
        log_tax_resolution(
            "duplicate GST rows omitted",
            template_name,
            detail={
                "duplicate_rows": [
                    {
                        "account_head": get_tax_row_value(row, "account_head"),
                        "rate": get_tax_row_value(row, "rate"),
                        "charge_type": get_tax_row_value(row, "charge_type"),
                    }
                    for row in duplicate_gst_rows
                ],
            },
        )

    if not rows:
        log_tax_resolution(
            "template has no tax rows",
            template_name
        )

    return unique_rows


def get_gst_tax_row_signature(row):
    account_head = str(get_tax_row_value(row, "account_head") or "")
    gst_tax_type = str(get_tax_row_value(row, "gst_tax_type") or "").upper()

    if not gst_tax_type and not re.search(
        r"(?:^|[\s-])(IGST|CGST|SGST|UTGST)(?:$|[\s-])",
        account_head.upper(),
    ):
        return None

    return (
        account_head,
        gst_tax_type,
        get_tax_row_value(row, "charge_type"),
        get_tax_row_value(row, "rate"),
        get_tax_row_value(row, "row_id"),
        get_tax_row_value(row, "add_deduct_tax"),
        get_tax_row_value(row, "included_in_print_rate"),
        get_tax_row_value(row, "included_in_paid_amount"),
    )


def get_tax_row_value(row, fieldname):
    if isinstance(row, dict):
        return row.get(fieldname)

    return getattr(row, fieldname, None)
