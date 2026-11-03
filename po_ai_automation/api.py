# import frappe

# from po_ai_automation.services.pdf_service import (
#     extract_text_from_pdf
# )

# from po_ai_automation.services.llm_service import (
#     extract_po_data
# )

# from po_ai_automation.services.vision_service import (
#     extract_po_data_from_scanned_pdf
# )

# from po_ai_automation.services.validation_service import (
#     validate_po_data
# )

# from po_ai_automation.services.sales_order_service import (
#     create_sales_order
# )


# @frappe.whitelist()
# def process_po(docname):

#     doc = frappe.get_doc(
#         "AI PO Processing",
#         docname
#     )

#     if not doc.po_attachment:
#         frappe.throw(
#             "Please upload a PO attachment first."
#         )

#     try:

#         # --------------------------------
#         # Step 1: Processing
#         # --------------------------------

#         doc.status = "Processing"
#         doc.error_message = ""

#         doc.save(
#             ignore_permissions=True
#         )

#         # --------------------------------
#         # Step 2: Get attached file
#         # --------------------------------

#         file_doc = frappe.get_doc(
#             "File",
#             {
#                 "file_url": doc.po_attachment
#             }
#         )

#         file_path = file_doc.get_full_path()

#         # --------------------------------
#         # Step 3: Detect PDF type
#         # --------------------------------

#         pdf_result = extract_text_from_pdf(
#             file_path
#         )

#         # --------------------------------
#         # Step 4: AI Processing
#         # --------------------------------

#         if not pdf_result["is_text_pdf"]:

#             # ================================
#             # SCANNED PDF
#             # ================================

#             po_data = extract_po_data_from_scanned_pdf(
#                 file_path
#             )

#         else:

#             # ================================
#             # DIGITAL PDF
#             # ================================

#             extracted_text = pdf_result["text"]

#             po_data = extract_po_data(
#                 extracted_text
#             )

#         # --------------------------------
#         # Step 5: Save AI response
#         # --------------------------------

#         doc.raw_ai_response = frappe.as_json(
#             po_data,
#             indent=2
#         )

#         # --------------------------------
#         # Step 6: Validate PO
#         # --------------------------------

#         validation_result = validate_po_data(
#             po_data
#         )

#         # --------------------------------
#         # Step 7: Check validation
#         # --------------------------------

#         if not validation_result["valid"]:

#             doc.status = "Failed"

#             doc.error_message = "\n".join(
#                 validation_result["errors"]
#             )

#             doc.save(
#                 ignore_permissions=True
#             )

#             return {
#                 "status": "validation_failed",
#                 "errors": validation_result["errors"],
#                 "data": po_data
#             }

#         # --------------------------------
#         # Step 8: Create Sales Order Draft
#         # --------------------------------

#         sales_order_name = create_sales_order(
#             po_data,
#             validation_result
#         )

#         # --------------------------------
#         # Step 9: Save final status
#         # --------------------------------

#         doc.status = "Extracted"

#         doc.error_message = ""

#         doc.save(
#             ignore_permissions=True
#         )

#         # --------------------------------
#         # Step 10: Return result
#         # --------------------------------

#         return {
#             "status": "success",
#             "data": po_data,
#             "validation": validation_result,
#             "sales_order": sales_order_name
#         }

#     except Exception:

#         frappe.log_error(
#             frappe.get_traceback(),
#             "AI PO Processing Error"
#         )

#         doc.status = "Failed"

#         doc.error_message = (
#             "PO processing failed. "
#             "Please check Error Log."
#         )

#         doc.save(
#             ignore_permissions=True
#         )

#         frappe.throw(
#             "PO processing failed. "
#             "Please check Error Log."
#         )


import mimetypes

import frappe

from po_ai_automation.services.pdf_service import (
    extract_text_from_pdf
)

from po_ai_automation.services.llm_service import (
    extract_po_data
)

from po_ai_automation.services.vision_service import (
    extract_po_data_from_visual_file
)

from po_ai_automation.services.extraction_utils import (
    populate_item_codes_from_descriptions
)

from po_ai_automation.services.validation_service import (
    validate_po_data
)

from po_ai_automation.services.item_service import (
    get_standard_selling_price
)

from po_ai_automation.services.sales_order_service import (
    create_sales_order
)


@frappe.whitelist()
def process_po(docname):

    # --------------------------------------------------
    # Get AI PO Processing document
    # --------------------------------------------------

    doc = frappe.get_doc(
        "AI PO Processing",
        docname
    )

    if not doc.po_attachment:
        frappe.throw(
            "Please upload a PO attachment first."
        )

    try:

        # ==================================================
        # STEP 1: PROCESSING
        # ==================================================

        frappe.db.set_value(
            "AI PO Processing",
            docname,
            {
                "status": "Processing",
                "error_message": ""
            },
            update_modified=False
        )

        # ==================================================
        # STEP 2: GET ATTACHED FILE
        # ==================================================

        file_doc = frappe.get_doc(
            "File",
            {
                "file_url": doc.po_attachment
            }
        )

        file_path = file_doc.get_full_path()

        # ==================================================
        # STEP 3: DETECT FILE TYPE AND EXTRACT PO DATA
        # ==================================================

        file_name = file_doc.file_name or doc.po_attachment
        mime_type = mimetypes.guess_type(file_name)[0]

        if mime_type and mime_type.startswith("image/"):
            po_data = extract_po_data_from_visual_file(
                file_path,
                mime_type=mime_type,
            )
        else:
            pdf_result = extract_text_from_pdf(file_path)

            if not pdf_result["is_text_pdf"]:
                po_data = extract_po_data_from_visual_file(
                    file_path,
                    mime_type="application/pdf",
                )
            else:
                po_data = extract_po_data(
                    pdf_result["text"]
                )

        po_data = populate_item_codes_from_descriptions(
            po_data
        )

        # ==================================================
        # STEP 5: SAVE AI RESPONSE
        # ==================================================

        frappe.db.set_value(
            "AI PO Processing",
            docname,
            "raw_ai_response",
            frappe.as_json(
                po_data,
                indent=2
            ),
            update_modified=False
        )

        # ==================================================
        # STEP 6: VALIDATE CUSTOMER + ITEMS
        # ==================================================

        validation_result = validate_po_data(
            po_data
        )

        # ==================================================
        # STEP 6B: SAVE EXTRACTED DATA, PO ITEMS,
        #          AI CONFIDENCE
        # ==================================================

        po_doc = frappe.get_doc(
            "AI PO Processing",
            docname
        )

        po_doc.raw_ai_response = frappe.as_json(
            po_data,
            indent=2
        )

        po_doc.customer = validation_result["customer"]

        po_doc.supplier_name = po_data.get(
            "supplier_name"
        )

        po_doc.matched_company = validation_result.get(
            "company"
        )

        po_doc.customer_po_number = po_data.get(
            "po_number"
        )

        # Only set Link fields when the master exists
        currency = po_data.get("currency")

        if currency and not frappe.db.exists(
            "Currency",
            currency
        ):
            currency = None

        po_doc.currency = currency

        po_doc.po_date = po_data.get("po_date")

        po_doc.delivery_date = po_data.get("delivery_date")

        po_doc.ai_confidence = validation_result[
            "confidence"
        ]

        # --------------------------------
        # Rebuild PO Items child table
        # --------------------------------

        po_doc.po_items = []

        for item in validation_result["items"]:

            uom = item.get("uom")

            if uom and not frappe.db.exists("UOM", uom):
                uom = None

            po_doc.append(
                "po_items",
                {
                    "po_item_description": (
                        item.get("description")
                    ),
                    "item_code": item.get("erpnext_item"),
                    "customer_item_code": item.get(
                        "item_code"
                    ),
                    "qty": item.get("qty"),
                    "uom": uom,
                    "rate": item.get("rate"),
                    "our_selling_price": get_standard_selling_price(
                        item.get("erpnext_item"),
                        currency=po_doc.currency,
                        uom=uom,
                    ),
                    "amount": item.get("amount"),
                    "match_confidence": item.get(
                        "match_confidence"
                    ),
                    "validation_status": item.get(
                        "validation_status"
                    ),
                }
            )

        po_doc.save(
            ignore_permissions=True
        )

        # ==================================================
        # STEP 7: VALIDATION FAILED
        # ==================================================

        if not validation_result["valid"]:

            error_message = "\n".join(
                validation_result["errors"]
            )

            frappe.db.set_value(
                "AI PO Processing",
                docname,
                {
                    "status": "Failed",
                    "validation_status": "Failed",
                    "error_message": error_message
                },
                update_modified=False
            )

            frappe.db.commit()

            return {
                "status": "validation_failed",
                "errors": validation_result["errors"],
                "data": po_data
            }

        # ==================================================
        # STEP 8: VALIDATION PASSED
        # ==================================================

        frappe.db.set_value(
            "AI PO Processing",
            docname,
            {
                "validation_status": "Passed",
                "error_message": ""
            },
            update_modified=False
        )

        # ==================================================
        # STEP 9: CREATE SALES ORDER
        # ==================================================

        sales_order_name = create_sales_order(
            po_data,
            validation_result
        )

        # ==================================================
        # STEP 10: UPDATE FINAL STATUS
        # ==================================================

        frappe.db.set_value(
            "AI PO Processing",
            docname,
            {
                "status": "SO Created",
                "validation_status": "Passed",
                "sales_order": sales_order_name,
                "error_message": ""
            },
            update_modified=False
        )

        # ==================================================
        # STEP 11: COMMIT
        # ==================================================

        frappe.db.commit()

        # ==================================================
        # STEP 12: RETURN RESULT
        # ==================================================

        return {
            "status": "success",
            "data": po_data,
            "validation": validation_result,
            "sales_order": sales_order_name
        }

    except Exception as e:

        # --------------------------------------------------
        # LOG ERROR
        # --------------------------------------------------

        frappe.log_error(
            frappe.get_traceback(),
            "AI PO Processing Error"
        )

        # --------------------------------------------------
        # UPDATE DOCUMENT AS FAILED
        # --------------------------------------------------

        try:

            frappe.db.set_value(
                "AI PO Processing",
                docname,
                {
                    "status": "Failed",
                    "validation_status": "Failed",
                    "error_message": (
                        f"PO processing failed: {e}"
                    )
                },
                update_modified=False
            )

            frappe.db.commit()

        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "AI PO Processing Failure Status Update Error"
            )

        # --------------------------------------------------
        # SHOW ERROR
        # --------------------------------------------------

        frappe.throw(
            f"PO processing failed: {e}"
        )
# import frappe

# from po_ai_automation.services.pdf_service import (
#     extract_text_from_pdf
# )

# from po_ai_automation.services.llm_service import (
#     extract_po_data
# )

# from po_ai_automation.services.vision_service import (
#     extract_po_data_from_scanned_pdf
# )


# @frappe.whitelist()
# def process_po(docname):

#     doc = frappe.get_doc(
#         "AI PO Processing",
#         docname
#     )

#     if not doc.po_attachment:
#         frappe.throw(
#             "Please upload a PO attachment first."
#         )

#     try:
#         # --------------------------------
#         # Step 1: Processing
#         # --------------------------------

#         doc.status = "Processing"
#         doc.error_message = ""

#         doc.save(
#             ignore_permissions=True
#         )

#         # --------------------------------
#         # Step 2: Get attached file
#         # --------------------------------

#         file_doc = frappe.get_doc(
#             "File",
#             {
#                 "file_url": doc.po_attachment
#             }
#         )

#         file_path = file_doc.get_full_path()

#         # --------------------------------
#         # Step 3: Detect PDF type
#         # --------------------------------

#         pdf_result = extract_text_from_pdf(
#             file_path
#         )

#         # --------------------------------
#         # Step 4: AI Processing
#         # --------------------------------

#         if not pdf_result["is_text_pdf"]:

#             # ================================
#             # SCANNED PDF
#             # ================================

#             po_data = extract_po_data_from_scanned_pdf(
#                 file_path
#             )

#         else:

#             # ================================
#             # DIGITAL PDF
#             # ================================

#             extracted_text = pdf_result["text"]

#             po_data = extract_po_data(
#                 extracted_text
#             )

#         # --------------------------------
#         # Step 5: Save AI response
#         # --------------------------------

#         doc.raw_ai_response = frappe.as_json(
#             po_data,
#             indent=2
#         )

#         doc.status = "Extracted"

#         doc.save(
#             ignore_permissions=True
#         )

#         return {
#             "status": "success",
#             "data": po_data
#         }

#     except Exception:

#         frappe.log_error(
#             frappe.get_traceback(),
#             "AI PO Processing Error"
#         )

#         doc.status = "Failed"

#         doc.error_message = (
#             "PO processing failed. "
#             "Please check Error Log."
#         )

#         doc.save(
#             ignore_permissions=True
#         )

#         frappe.throw(
#             "PO processing failed. "
#             "Please check Error Log."
#         )
