# PO AI Automation — Application and Processing Guide

## 1. Purpose

AI PO Automation is a Frappe/ERPNext app that reads a customer Purchase Order
(PO), extracts its header and line-item data with Google Gemini, checks the
customer, supplier/company, and items against ERPNext records, and creates a
draft Sales Order when validation succeeds.

The app's main workflow is implemented in
`po_ai_automation/api.py` (`process_po`). The AI extracts information; ERPNext
master-data lookups determine whether the extracted customer, company, and item
codes can be used.

## 2. Main doctypes

### AI PO Processing

This is the parent document and the user's entry point. A record is named with
the `AI-PO-.#####` naming pattern and requires a PO attachment.

| Field | Purpose |
|---|---|
| PO Attachment | Source PO file. Processing expects a PDF that can be read by PyMuPDF. |
| Customer | Link to the matched ERPNext Customer. |
| PO Supplier (Our Company) | Supplier name extracted from the PO; expected to identify our ERPNext Company. |
| Customer PO Number | Customer's PO number from the document. |
| PO Date / Delivery Date | Extracted dates. If no delivery date is supplied, the document validation sets it to today. |
| Currency | Link to ERPNext Currency. The extracted value is assigned only if that Currency exists. |
| PO Items | Child rows containing extracted item information and match results. |
| AI Confidence | Overall score from 0 to 100. It is not a pass/fail threshold. |
| Status | Processing outcome, for example Received, Processing, Failed, or SO Created. |
| Validation Status | Overall validation result, such as Not Validated, Passed, or Failed. |
| Error Message | Validation errors or a general processing failure message. |
| Matched Company | ERPNext Company matched to the PO supplier. |
| Sales Order | Link to the Sales Order created after validation. |
| Raw AI Response | JSON extracted from the PO, retained for review/troubleshooting. |

### AI PO Item

This is the child table used by the PO Items field.

| Field | Purpose |
|---|---|
| PO Item Description | Full description extracted from the PO, stored as Long Text; display/reference only and not validated for length. Existing sites must run `bench migrate` to update the DocType and database column. |
| ERPNext Item | Link to the matched ERPNext Item. |
| Customer Item Code | The customer's item/reference code extracted from the PO. |
| Qty, UOM, Rate, Amount | Extracted line-item values. |
| Our Selling Price | Informational price from the selling Price List configured in Selling Settings, when one unambiguous applicable price is found. |
| Match Confidence | Confidence assigned to the successful item-code lookup. |
| Validation Status | Per-row result: Matched or Failed. |

## 3. User workflow

1. Create an **AI PO Processing** record and attach the customer's PO PDF or
   image.
2. After an attachment is selected, the form saves the record and starts the
   same PO processing workflow automatically.
3. The **Process PO** button remains available on saved records. It asks for
   confirmation before running the workflow again, for example after fixing
   master data or when a manual retry is needed.
4. The server reads the attachment, extracts fields, saves the raw AI JSON, and
   runs validation.
5. The extracted fields and child item rows are saved on the AI PO Processing
   record whether item validation passes or fails.
6. If validation fails, review the error message, extracted values, and item
   rows; correct the source/master data as needed and use **Process PO** to
   retry.
7. If validation passes, the app creates a draft Sales Order and links it back
   to the AI PO Processing record.

The client uses a progress/freeze message while the server call runs and
reloads the form after success.

## 4. File processing and AI extraction

`services/pdf_service.py` extracts selectable text from each PDF page. JPEG,
PNG, WebP, HEIC, and HEIF attachments are sent directly to the vision extractor.

- If any page text is available, the app treats the PDF as a digital/text PDF
  and sends its extracted text to `services/llm_service.py`.
- If no page text is available, it treats the PDF as scanned and sends rendered
  page images to `services/vision_service.py`.
- Image attachments bypass PDF parsing and are sent directly to
  `services/vision_service.py`.
- Both extraction paths use the Gemini API and the `gemini-3.6-flash` model.
  The API key must be configured as `gemini_api_key` in the Frappe site's
  `site_config.json`.

The expected extracted JSON includes:

- Header: `customer_name`, `customer_gstin`, `supplier_name`,
  `supplier_gstin`, `po_number`, `po_date`, `delivery_date`, `currency`, and
  `grand_total`.
- Each item: `description`, `item_code`, `qty`, `uom`, `rate`, and `amount`.

`item_code` means the customer's own item/part/reference code as printed on the
PO; it is not assumed to be the ERPNext item code. Both extraction prompts ask
the model to return `null` when a value cannot be determined. PO item
descriptions are retained accurately for display, but are not used to select
or validate ERPNext Items. If AI leaves `item_code` empty, the processing flow
also checks the description for an explicitly labeled code (for example
`Model- FL001A-0800LV3` or `Part No: ABC-123`) and copies only that code into
`item_code`. Unlabeled strings are not treated as item codes.

## 5. Validation rules

Validation is implemented in `services/validation_service.py`. Validation
errors prevent Sales Order creation.

### Customer

The extracted customer name is matched by
`services/customer_service.py`:

1. Exact `Customer.customer_name` match: 100 confidence.
2. A single partial `LIKE` match: 80 confidence.
3. If the name lookup has no unique match, exact GSTIN lookup checks the
   Customer's `gstin` or `tax_id` field when present: 100 confidence.
4. No unique name or GSTIN match: no customer match and validation fails.

The returned ERPNext Customer document name is used as the resolved customer.
This customer is also used for customer-specific item-reference matching.
If the name lookup has no unique match, validation tries an exact GSTIN match
against the Customer's `gstin` or `tax_id` field when present. GSTIN matching
must identify exactly one record; ambiguous matches are rejected.

### Supplier / our Company

The extracted supplier is interpreted as the company receiving the customer's
PO—our company. `services/company_service.py` checks:

1. Exact `Company.company_name`: 100 confidence.
2. Exact Company document name: 95 confidence.
3. A single partial `LIKE` match: 80 confidence.
4. If the name lookup has no unique match, exact GSTIN lookup checks the
   Company's `gstin` or `tax_id` field when present: 100 confidence.
5. No unique name or GSTIN match: no company match and validation fails.

A missing supplier also fails validation. The matched Company is used as the
Sales Order company. If the supplier name has no unique match, validation
tries the supplier GSTIN against the Company's `gstin` or `tax_id` field when
present. GSTIN matching must identify exactly one Company.

### Required PO information

Validation requires:

- A matched customer.
- A supplier name that matches an ERPNext Company.
- A PO number.
- A PO date.
- A currency value.
- At least one item.

Delivery date is not required by the validation service. At document save,
`AI PO Processing.validate()` sets it to today's date if it is empty and warns
the user. It also warns if the delivery date is earlier than the PO date; this
is a warning, not a blocking validation error in that method.

### Item matching — exact decision order

For every extracted PO line, validation uses only the customer `item_code`
field. Before validation, that field may be populated from an explicitly
labeled model/part/reference code found in the extracted description. The
description itself is never sent to the item matcher:

1. **Exact ERPNext item-code lookup**: match `Item.item_code` exactly. A match
   is assigned 95 confidence.
2. **Customer reference fallback**: only if step 1 does not match, search the
   Item Customer Detail child table for the exact pair:
   - `customer_name` = resolved ERPNext Customer document name
   - `ref_code` = extracted customer item code

   Exactly one distinct parent Item is required; that match is assigned 85
   confidence. Zero matches or multiple distinct Items are treated as no match.
3. **Failure**: if neither lookup matches, that item gets `Failed` status and
   an item-code error is added to the validation errors. The item may still be
   displayed with its extracted description and other extracted values.

**Item descriptions are not a matching fallback.** An item cannot pass
validation just because its description resembles an ERPNext Item. If the PO
has no item code, both code-based lookup paths fail and that line fails
validation.

This code-first rule is specifically the validation behavior. A legacy/general
description helper remains in `services/item_service.py`, but the PO validation
workflow does not call it.

### Other item fields

The validation service does not check the correctness or presence of quantity,
UOM, rate, or amount. These values are extracted and passed through. When
populating the AI PO child table, the app clears an extracted UOM that does not
exist as an ERPNext UOM. ERPNext Sales Order validation may impose additional
requirements when the Sales Order is inserted.

### AI Confidence

The app calculates a score from 0 to 100; it is a confidence indicator, not a
threshold that independently blocks processing:

| Component | Maximum points |
|---|---:|
| Presence of extracted header values (customer, supplier, PO number, PO date, delivery date, currency, grand total) | 70 |
| Customer match confidence | 15 |
| Company match confidence | 5 |
| Average item match confidence | 20 |

Item points are based on the code/reference match confidence for each
validated item. A failed item contributes a zero match confidence to the
average.

## 6. Status and error behavior

The main server flow updates statuses as follows:

| Situation | Status | Validation Status |
|---|---|---|
| Processing begins | Processing | Existing value until validation completes |
| Validation errors | Failed | Failed |
| Validation succeeds and Sales Order is created | SO Created | Passed |
| Unexpected exception | Failed (update is attempted) | Failed (update is attempted) |

On validation failure, the app saves the extracted response and item rows,
joins validation errors into **Error Message**, commits the failure state, and
returns a `validation_failed` result. It does not create a Sales Order.

On unexpected processing exceptions, the app logs a traceback in Error Log,
attempts to mark the record Failed, and raises a user-facing error directing
the user to Error Log. The general error message does not include the full
traceback.

## 7. Sales Order creation

After validation succeeds, `services/sales_order_service.py` creates and
inserts a Sales Order with:

- The matched Customer and Company.
- Customer PO number and PO date.
- Extracted currency.
- Extracted delivery date, or today's date if missing.
- One Sales Order item row for each matched item, using the matched ERPNext
  Item, extracted quantity, and extracted PO rate.

The app does not replace the customer's PO rate with the informational
**Our Selling Price** value shown on the AI PO child row.

Additional ERPNext setup behavior:

- The Sales Order fills an empty `company_address` with the matched Company's
  primary linked Address when one is available. ERPNext uses this address to
  fetch Company GSTIN for the transaction; the PO's extracted GSTIN is used
  only for matching and is not copied into the Sales Order.
- If the delivery date is earlier than today, the Sales Order transaction date
  is set to the PO date.
- Sales taxes are resolved in this order: `po_sales_taxes_charges_template`
  from `site_config.json`, a matching ERPNext Tax Rule, the Company's default
  enabled tax template, then another enabled template for that Company.
- A stock-item warehouse is resolved in this order: `po_source_warehouse`
  from `site_config.json`, an Item Default for the Company, then an active
  non-group Company warehouse (preferring a name containing "store"). If a
  stock item still has no warehouse, Sales Order creation raises an error.
- The Sales Order is inserted as a draft. Its name is saved to the AI PO
  Processing record after creation.

## 8. Configuration and operational checklist

Before processing real POs, verify:

- The Gemini API key is configured as `gemini_api_key` in the site's
  `site_config.json`.
- Customer records have names that the PO can identify uniquely.
- The PO supplier resolves to the correct ERPNext Company.
- Each PO item has the customer's item/reference code printed on it, or a
  corresponding customer-specific reference exists in the Item's Customer
  Details (`ref_code`) table.
- Extracted currencies and UOMs exist in ERPNext.
- The Company has a suitable tax template and stock-item warehouse, or the
  appropriate optional site configuration values are set.
- The user has access to AI PO Processing and the required ERPNext master
  records.

When a PO fails, check the saved **Raw AI Response** first to determine whether
the value was extracted correctly. Then compare it with ERPNext Customer,
Company, Item, and Item Customer Detail data. Item descriptions will not fix an
item-code mismatch.

## 9. Important implementation files

| File | Responsibility |
|---|---|
| `po_ai_automation/api.py` | Whitelisted `process_po` workflow, persistence, statuses, and error handling. |
| `po_ai_automation/ai_po_automation/doctype/ai_po_processing/` | Parent doctype model, form script, and schema. |
| `po_ai_automation/ai_po_automation/doctype/ai_po_item/` | PO item child doctype schema. |
| `po_ai_automation/services/pdf_service.py` | PDF text extraction and digital/scanned classification. |
| `po_ai_automation/services/llm_service.py` | Text-PDF extraction with Gemini. |
| `po_ai_automation/services/vision_service.py` | Scanned-PDF and image extraction with Gemini Vision. |
| `po_ai_automation/services/validation_service.py` | Required-field checks, master matching, item decision path, and confidence. |
| `po_ai_automation/services/customer_service.py` | Customer lookup. |
| `po_ai_automation/services/company_service.py` | Supplier-to-Company lookup. |
| `po_ai_automation/services/item_service.py` | Exact item-code and customer-reference lookups, plus selling-price lookup. |
| `po_ai_automation/services/sales_order_service.py` | Sales Order creation, taxes, and warehouse selection. |
