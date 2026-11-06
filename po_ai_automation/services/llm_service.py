import json
import frappe
import time
from google import genai

def extract_po_data(text):

    api_key = frappe.conf.get("gemini_api_key")

    if not api_key:
        raise Exception("Gemini API key is not configured.")

    client = genai.Client(api_key=api_key)

    # rest of your existing code...
# def extract_po_data(text):
#     """
#     Send extracted PO text to Gemini and return structured JSON.
#     """
#     api_key = frappe.conf.get("gemini_api_key")
#     # api_key = os.getenv("GEMINI_API_KEY")

#     if not api_key:
#         raise Exception("GEMINI_API_KEY is not configured.")

#     client = genai.Client(api_key=api_key)

    prompt = f"""
You are an expert AI system for understanding Customer Purchase Orders.

Your task is to analyze the ENTIRE Purchase Order and extract
structured information.

IMPORTANT:
Do NOT depend on fixed labels such as:

Customer:
Supplier:
PO Number:
PO Date:
Delivery Date:

Real-world Purchase Orders can have different layouts, labels,
headings, tables, addresses, abbreviations, or no explicit labels.

You must determine the meaning of information using the overall
document context, headings, addresses, tables, and relationships
between fields.

==================================================
CUSTOMER IDENTIFICATION
==================================================

Identify the BUYER / CUSTOMER who is issuing the Purchase Order.

The customer may appear under different headings or contexts,
for example:

- Buyer
- Bill To
- Sold To
- Purchaser
- Buying Company
- Ordered By
- Ship To
- Issued By
- Company name in the PO header
- M/s Company Name
- Buyer address

Do NOT assume that the first company name is the customer.

Determine which company is acting as the BUYER in the Purchase
Order.

Use the document's title, issuer letterhead/logo, buyer and
supplier blocks, addresses, and GSTINs together to determine
each party's role. On a Purchase Order, the company whose
branding/logo identifies the PO issuer is usually the
customer/buyer; do not label a company as the customer only
because its name or address is prominent or appears first.
The vendor/supplier block and its GSTIN identify the supplier.
Treat the logo as a role clue and cross-check it against the
PO context and party details.

If a GSTIN is printed for the buyer/customer, extract it as
customer_gstin. Keep it separate from supplier_gstin.

==================================================
SUPPLIER IDENTIFICATION
==================================================

Identify the SUPPLIER / VENDOR / SELLER who is receiving the
Purchase Order.

Possible indicators include:

- Supplier
- Vendor
- Seller
- Vendor Code
- Vendor Address
- From
- To
- Supplier details

Use the overall document context.

IMPORTANT:
Do not confuse the supplier with the customer.

Use the PO issuer's logo/letterhead and the separate party
blocks as cross-checks. The logo on a customer's Purchase
Order usually identifies the buyer/customer, not the vendor.
Keep that issuer separate from the supplier named in the
vendor/supplier block.

If a GSTIN is printed for the supplier/vendor, extract it as
supplier_gstin. Keep it separate from customer_gstin.

==================================================
PURCHASE ORDER NUMBER
==================================================

Identify the Purchase Order number.

Possible labels include:

- PO No
- PO Number
- Purchase Order No
- Purchase Order Number
- Order No
- Order Number
- Reference No
- Document No
- PO Reference

The actual PO number may appear anywhere in the document.

==================================================
PURCHASE ORDER DATE
==================================================

Identify the date on which the Purchase Order was issued.

Possible labels include:

- PO Date
- Order Date
- Date
- Issue Date
- Document Date

Do NOT confuse the PO date with the delivery date.

Return the date in YYYY-MM-DD format when the date can be
determined confidently.

==================================================
DELIVERY DATE
==================================================

Identify the requested/required delivery date.

Possible indicators include:

- Delivery Date
- Required Date
- Required Delivery Date
- Delivery Schedule
- Expected Delivery
- Due Date
- Dispatch Date

Do NOT confuse this with the PO date.

Return the date in YYYY-MM-DD format when possible.

==================================================
CURRENCY
==================================================

Identify the currency used for the Purchase Order.

Possible indicators include:

- INR
- USD
- EUR
- ₹
- $
- €
- Currency code
- Currency symbol

If the currency is not available or cannot be determined
confidently, return null.

==================================================
ITEM TABLE
==================================================

Identify the Purchase Order line-item table.

The table may use different column names.

Possible item description columns:

- Item
- Description
- Item Description
- Product
- Material
- Part
- Part Description
- Product Description
- Details

Possible quantity columns:

- Qty
- Quantity
- Ordered Qty
- Order Quantity

Possible UOM columns:

- UOM
- Unit
- Units
- Unit of Measure

Possible rate columns:

- Rate
- Unit Price
- Price
- Unit Rate
- Basic Rate

Possible amount columns:

- Amount
- Value
- Line Amount
- Line Total
- Total

Possible customer item code / reference columns:

- Item Code
- Customer Part No
- Part No
- Part Number
- Customer Code
- Ref Code
- Reference
- SKU
- Article No
- Material No
- Catalogue No
- Product Code

Use the table structure to correctly associate each value
with the corresponding item.

For EVERY line item extract:

- description
- item_code
- qty
- uom
- rate
- amount

item_code is the item identifier printed on the PO for that
line. It may be our ERPNext item code OR the customer's own
part/reference code. Extract the exact value as printed; do
not assume who assigned it. Read code columns (such as Item
Code, Code, Part No, Product Code, Customer Code, Ref Code,
SKU, Material No, or Article No) and associate each value
with the correct table row. It may also appear after an
explicit label in the description, for example
"Make - Renu, Model - FL001A-0800LV3". Do not return the
maker name or ordinary descriptive text as item_code. Preserve
letters, digits, hyphens, slashes, and leading zeros. Return
null only when that line has no printed item identifier.

Some POs put the item identifier in a column named
"Name of Product / Service" or similar without labeling it as
a code. If a row's product value is a compact code-like string
(for example "FP4070TN - E" or "FPEM-0808RP-A0401U-V2"),
extract that value as item_code as well as description. Do not
require an "Item Code" heading. Do not treat a full prose
description as a code just because it contains letters/numbers.

Return ALL line items.

==================================================
GRAND TOTAL
==================================================

Identify the final Purchase Order total.

Possible indicators include:

- Grand Total
- Total
- Total Amount
- Order Total
- Net Total
- Total Value
- Amount Payable
- Final Total

Do NOT confuse the grand total with:

- Subtotal
- Tax
- GST
- Discount
- Freight
- Shipping
- Individual item amount

==================================================
GENERAL EXTRACTION RULES
==================================================

1. Analyze the entire Purchase Order.
2. Use semantic meaning and document context.
3. Read the item-table headers and values. A compact code-like value under a product/service name column is also an item identifier even if that column is not labeled as a code.
4. Do not assume a fixed document layout.
5. Do not invent information.
6. If information cannot be determined confidently, return null.
7. Return JSON only.
8. Do not return Markdown.
9. Do not return explanations.
10. Keep numeric values as numbers and item_code values as strings.
11. Return all detected line items.
12. Preserve item descriptions accurately.
13. Normalize dates to YYYY-MM-DD when possible.
14. Do not confuse customer and supplier.
15. Do not confuse PO date and delivery date.
16. Do not confuse line amount with grand total.

==================================================
REQUIRED JSON FORMAT
==================================================

{{
    "customer_name": null,
    "customer_gstin": null,
    "supplier_name": null,
    "supplier_gstin": null,
    "po_number": null,
    "po_date": null,
    "delivery_date": null,
    "currency": null,
    "items": [
        {{
            "description": null,
            "item_code": null,
            "qty": null,
            "uom": null,
            "rate": null,
            "amount": null
        }}
    ],
    "grand_total": null
}}

==================================================
PURCHASE ORDER
==================================================

{text}
"""

    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )
            break

        except Exception as e:
            if attempt == max_retries - 1:
                raise

            time.sleep(2 ** attempt)
    # response = client.models.generate_content(
    #     model="gemini-3.6-flash",
    #     contents=prompt
    # )

    response_text = response.text.strip()

    # Remove Markdown JSON fences if Gemini returns them
    if response_text.startswith("```json"):
        response_text = response_text[7:]

    if response_text.startswith("```"):
        response_text = response_text[3:]

    if response_text.endswith("```"):
        response_text = response_text[:-3]

    response_text = response_text.strip()

    return json.loads(response_text)
# import json
# import os

# from google import genai


# def extract_po_data(text):
#     """
#     Send extracted PO text to Gemini and return structured JSON.
#     """

#     api_key = os.getenv("GEMINI_API_KEY")

#     if not api_key:
#         raise Exception("GEMINI_API_KEY is not configured.")

#     client = genai.Client(api_key=api_key)

#     prompt = f"""
# You are an AI system that extracts structured information
# from Customer Purchase Orders.

# Read the following Purchase Order text and extract:

# - customer_name
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

# Rules:

# 1. Return JSON only.
# 2. Do not add explanations.
# 3. Do not invent information.
# 4. If a value is not available, return null.
# 5. Keep numeric values as numbers.
# 6. Return items as an array.

# Required JSON format:

# {{
#     "customer_name": null,
#     "po_number": null,
#     "po_date": null,
#     "delivery_date": null,
#     "currency": null,
#     "items": [
#         {{
#             "description": null,
#             "qty": null,
#             "uom": null,
#             "rate": null,
#             "amount": null
#         }}
#     ],
#     "grand_total": null
# }}

# Purchase Order Text:

# {text}
# """
#     response = client.models.generate_content(
#     model="gemini-3.6-flash",
#     contents=prompt
#     )
#     # response = client.models.generate_content(
#     #     model="gemini-3.5-flash-lite",
#     #     contents=prompt
#     # )

#     response_text = response.text.strip()

#     # Remove markdown JSON fences if the model returns them
#     if response_text.startswith("```json"):
#         response_text = response_text[7:]

#     if response_text.startswith("```"):
#         response_text = response_text[3:]

#     if response_text.endswith("```"):
#         response_text = response_text[:-3]

#     response_text = response_text.strip()

#     return json.loads(response_text)