import frappe


def execute():
    frappe.reload_doc(
        "ai_po_automation",
        "doctype",
        "ai_po_item",
    )
    frappe.db.updatedb("AI PO Item")

    fieldtype = frappe.db.get_value(
        "DocField",
        {
            "parent": "AI PO Item",
            "fieldname": "po_item_description",
        },
        "fieldtype",
    )

    if fieldtype != "Long Text":
        frappe.throw(
            "AI PO Item.PO Item Description must be Long Text. "
            "Check the AI PO Item DocType definition."
        )
