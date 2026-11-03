import json
import time

import fitz
import frappe

from google import genai


def extract_po_data_from_visual_file(file_path, mime_type=None):
    """
    Extract structured Purchase Order data from a scanned PDF or image
    using Gemini Vision.
    """

    # --------------------------------------------------
    # Step 1: Get Gemini API key
    # --------------------------------------------------

    api_key = frappe.conf.get("gemini_api_key")

    if not api_key:
        raise Exception(
            "Gemini API key is not configured in site_config.json."
        )

    # --------------------------------------------------
    # Step 2: Create Gemini client
    # --------------------------------------------------

    client = genai.Client(
        api_key=api_key
    )

    # --------------------------------------------------
    # Step 4: Prepare Gemini prompt
    # --------------------------------------------------

    prompt = """
You are an AI system that extracts structured information
from real-world Customer Purchase Orders.

Analyze the attached scanned Purchase Order carefully.

The Purchase Order may have different layouts, formats,
headers, addresses, tables and terminology.

Extract the following information:

- customer_name
- customer_gstin
- supplier_name
- supplier_gstin
- po_number
- po_date
- delivery_date
- currency
- items
- grand_total

For every item extract:

- description
- item_code
- qty
- uom
- rate
- amount

item_code is the customer's own part/reference code for the
item as written on the PO (e.g. Part No, Customer Code,
Ref Code, SKU, Article No). It is NOT our internal item
code. The code may be in a separate table column OR explicitly
included in the item description, for example
"Make - Renu, Model - FL001A-0800LV3". In that case extract
the value after labels such as Model, Model No, Part No,
Item Code, Customer Code, SKU, or Ref Code as item_code.
Do not return the maker name or ordinary descriptive text
as item_code. Return null only when no explicit item/reference
code is present anywhere for that line.


IMPORTANT CUSTOMER / SUPPLIER RULES:

1. Do NOT expect labels such as:
   "Customer:"
   "Supplier:"
   "Buyer:"
   "Vendor:"

2. Real Purchase Orders may not explicitly write
   "Customer" or "Supplier".

3. Determine the customer and supplier from the
   business context of the document.

4. Usually the company issuing the Purchase Order
   is the customer/buyer.

5. The company receiving the Purchase Order is usually
   the supplier/vendor.

6. Carefully analyze:
   - Company names
   - Bill To
   - Ship To
   - Vendor information
   - Supplier information
   - Buyer information
   - Addresses
   - Header
   - Footer
   - Contact information
   - Tax information

7. Do not confuse the supplier with the customer.

8. Do not invent a company name.

9. If the customer or supplier cannot be determined
   reliably, return null.

10. Extract the customer's GSTIN separately as customer_gstin
    and the supplier's GSTIN separately as supplier_gstin.
    Use document context to associate each number with the
    correct party. Return null if a party's GSTIN is not shown.


IMPORTANT DATE RULES:

1. Extract the actual PO date.
2. Extract the required delivery date if available.
3. Dates may appear in formats such as:
   - 21-07-2026
   - 21/07/2026
   - 21.07.2026
   - July 21, 2026
   - 2026-07-21

4. Return dates in this format:

   YYYY-MM-DD

5. If a date is not available, return null.


IMPORTANT ITEM RULES:

1. Extract every line item.
2. Do not skip items.
3. Preserve the item description as accurately as possible.
4. Quantity must be numeric.
5. Rate must be numeric.
6. Amount must be numeric.
7. UOM should be extracted exactly when available.
8. If a field is not available, return null.


IMPORTANT TOTAL RULES:

1. Extract the final Purchase Order grand total.
2. Do not calculate or invent the grand total if it
   is clearly available in the document.
3. If the grand total is unavailable, return null.


GENERAL RULES:

1. Return JSON only.
2. Do not return Markdown.
3. Do not add explanations.
4. Do not invent information.
5. If a value is unavailable, return null.
6. Keep numeric values as numbers.
7. Return items as an array.
8. Analyze all pages of the Purchase Order.


Return exactly this JSON structure:

{
    "customer_name": null,
    "customer_gstin": null,
    "supplier_name": null,
    "supplier_gstin": null,
    "po_number": null,
    "po_date": null,
    "delivery_date": null,
    "currency": null,
    "items": [
        {
            "description": null,
            "item_code": null,
            "qty": null,
            "uom": null,
            "rate": null,
            "amount": null
        }
    ],
    "grand_total": null
}
"""

    # --------------------------------------------------
    # Step 5: Convert PDF pages into images
    # --------------------------------------------------

    contents = [prompt]

    if mime_type and mime_type.startswith("image/"):
        if mime_type not in {
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/heic",
            "image/heif",
        }:
            raise ValueError(
                f"Unsupported image type: {mime_type}. "
                "Use JPEG, PNG, WebP, HEIC, or HEIF."
            )

        with open(file_path, "rb") as image_file:
            contents.append(
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": image_file.read(),
                    }
                }
            )
    else:
        try:
            pdf = fitz.open(file_path)
        except Exception as e:
            raise ValueError(f"Unable to open the uploaded PDF: {e}") from e

        try:
            for page in pdf:
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(2, 2),
                    alpha=False
                )

                contents.append(
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": pix.tobytes("png"),
                        }
                    }
                )
        except Exception as e:
            raise ValueError(f"Failed to convert PDF pages to images: {e}") from e
        finally:
            pdf.close()

    # --------------------------------------------------
    # Step 6: Send images to Gemini Vision
    # --------------------------------------------------

    max_retries = 3
    response = None

    for attempt in range(max_retries):

        try:

            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=contents
            )

            break

        except Exception as e:

            error_text = str(e)

            # Retry only temporary Gemini server errors
            is_temporary_error = (
                "503" in error_text
                or "UNAVAILABLE" in error_text
                or "500" in error_text
                or "502" in error_text
                or "504" in error_text
            )

            if not is_temporary_error:

                raise

            # Last attempt - stop retrying
            if attempt == max_retries - 1:

                frappe.log_error(
                    frappe.get_traceback(),
                    "Gemini Vision Final Error"
                )

                raise Exception(
                    "Gemini Vision service is temporarily "
                    "unavailable after multiple attempts. "
                    "Please try processing the PO again."
                )

            # Wait before retry
            wait_seconds = 5 * (attempt + 1)

            frappe.log_error(
                (
                    f"Gemini Vision returned a temporary "
                    f"server error.\n\n"
                    f"Attempt: {attempt + 1}/{max_retries}\n"
                    f"Retrying after: {wait_seconds} seconds\n\n"
                    f"Error:\n{error_text}"
                ),
                "Gemini Vision Retry"
            )

            time.sleep(
                wait_seconds
            )

    # --------------------------------------------------
    # Step 7: Validate Gemini response
    # --------------------------------------------------

    if response is None:

        raise Exception(
            "Gemini Vision did not return a response."
        )

    if not response.text:

        raise Exception(
            "Gemini Vision returned an empty response."
        )

    response_text = response.text.strip()

    # --------------------------------------------------
    # Step 8: Remove Markdown JSON fences
    # --------------------------------------------------

    if response_text.startswith("```json"):

        response_text = response_text[
            len("```json"):
        ]

    elif response_text.startswith("```"):

        response_text = response_text[
            len("```"):
        ]

    if response_text.endswith("```"):

        response_text = response_text[
            :-len("```")
        ]

    response_text = response_text.strip()

    # --------------------------------------------------
    # Step 9: Convert response into Python dictionary
    # --------------------------------------------------

    try:

        po_data = json.loads(
            response_text
        )

    except json.JSONDecodeError as e:

        frappe.log_error(
            (
                "Gemini returned invalid JSON.\n\n"
                f"Response:\n{response_text}\n\n"
                f"JSON Error:\n{str(e)}"
            ),
            "Gemini Vision JSON Error"
        )

        raise Exception(
            "Gemini returned an invalid JSON response."
        )

    # --------------------------------------------------
    # Step 10: Basic structure validation
    # --------------------------------------------------

    if not isinstance(po_data, dict):

        raise Exception(
            "Gemini response is not a JSON object."
        )

    if "items" not in po_data:

        po_data["items"] = []

    if not isinstance(po_data["items"], list):

        po_data["items"] = []

    # --------------------------------------------------
    # Step 11: Return structured PO data
    # --------------------------------------------------

    return po_data


def extract_po_data_from_scanned_pdf(pdf_path):
    """Keep the original scanned-PDF entry point available."""

    return extract_po_data_from_visual_file(
        pdf_path,
        mime_type="application/pdf",
    )
# import json
# import os

# import fitz
# import frappe

# from google import genai


# def extract_po_data_from_scanned_pdf(pdf_path):
#     """
#     Extract structured PO data from a scanned PDF
#     using Gemini Vision.
#     """

#     # Get Gemini API key from Frappe site configuration
#     api_key = frappe.conf.get("gemini_api_key")

#     if not api_key:
#         raise Exception("Gemini API key is not configured.")

#     client = genai.Client(api_key=api_key)

#     # Open scanned PDF
#     pdf = fitz.open(pdf_path)

#     contents = [
#         """
# You are an AI system that extracts structured information
# from a Customer Purchase Order.

# Analyze the attached scanned Purchase Order carefully.

# Extract:

# - customer_name
# - supplier_name
# - po_number
# - po_date
# - delivery_date
# - currency
# - items
# - grand_total

# For every item extract:

# - description
# - qty
# - uom
# - rate
# - amount

# Important rules:

# 1. Return JSON only.
# 2. Do not add explanations.
# 3. Do not invent information.
# 4. If a value is not available, return null.
# 5. Keep numeric values as numbers.
# 6. Return items as an array.
# 7. Identify the customer and supplier from the document context.
# 8. Do not expect labels such as "Customer:" or "Supplier:".
# 9. Use the company/address information shown in the PO.
# 10. Carefully analyze the PO header, addresses, tables, totals and other visible information.

# Return exactly this structure:

# {
#     "customer_name": null,
#     "supplier_name": null,
#     "po_number": null,
#     "po_date": null,
#     "delivery_date": null,
#     "currency": null,
#     "items": [
#         {
#             "description": null,
#             "qty": null,
#             "uom": null,
#             "rate": null,
#             "amount": null
#         }
#     ],
#     "grand_total": null
# }
# """
#     ]

#     # Convert PDF pages to images
#     for page in pdf:
#         pix = page.get_pixmap(
#             matrix=fitz.Matrix(2, 2)
#         )

#         image_bytes = pix.tobytes("png")

#         contents.append(
#             {
#                 "inline_data": {
#                     "mime_type": "image/png",
#                     "data": image_bytes,
#                 }
#             }
#         )

#     # Send PDF page images to Gemini Vision
#     response = client.models.generate_content(
#         model="gemini-3.6-flash",
#         contents=contents
#     )

#     response_text = response.text.strip()

#     # Remove markdown JSON fences if Gemini returns them
#     if response_text.startswith("```json"):
#         response_text = response_text[7:]

#     if response_text.startswith("```"):
#         response_text = response_text[3:]

#     if response_text.endswith("```"):
#         response_text = response_text[:-3]

#     response_text = response_text.strip()

#     return json.loads(response_text)
