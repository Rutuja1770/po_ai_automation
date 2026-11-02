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

Use the table structure to correctly associate each value
with the corresponding item.

For EVERY line item extract:

- description
- qty
- uom
- rate
- amount

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
3. Do not depend on fixed field labels.
4. Do not assume a fixed document layout.
5. Do not invent information.
6. If information cannot be determined confidently, return null.
7. Return JSON only.
8. Do not return Markdown.
9. Do not return explanations.
10. Keep numeric values as numbers.
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
    "supplier_name": null,
    "po_number": null,
    "po_date": null,
    "delivery_date": null,
    "currency": null,
    "items": [
        {{
            "description": null,
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