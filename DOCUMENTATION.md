# AI PO Automation — Application Documentation

**App Name:** `po_ai_automation`
**Title:** AI PO Automation
**Publisher:** Assimilate
**Version:** 0.0.1
**Frappe Target:** version-16
**License:** MIT

---

## 1. Overview

AI PO Automation is a Frappe/ERPNext app that converts a **customer's Purchase Order (PDF)** into an **ERPNext Sales Order** automatically using **Google Gemini AI**.

### Workflow

```
Customer PO PDF (digital or scanned)
        │
        ▼
AI PO Processing DocType ── [Process PO] button
        │
        ▼
PDF Text Extraction (PyMuPDF)
        │
        ├── Has text layer? ──► Gemini LLM (text)      ── llm_service.py
        │
        └── No text (scanned)? ──► Gemini Vision (images) ── vision_service.py
        │
        ▼
Structured JSON (customer, PO#, dates, currency, items, totals)
        │
        ▼
Validation against ERPNext masters (Customer, Item)
        │
        ├── Failed ──► status = Failed, errors stored on doc
        │
        └── Passed ──► Draft Sales Order created & linked
```

---

## 2. Directory Structure

```
po_ai_automation/
├── pyproject.toml                     # App metadata (ruff config)
├── README.md
├── license.txt                        # MIT
├── DOCUMENTATION.md                   # This file
└── po_ai_automation/
    ├── __init__.py                    # __version__ = "0.0.1"
    ├── api.py                         # Orchestrator: process_po() endpoint
    ├── hooks.py                       # App metadata and Desk styling
    ├── modules.txt                    # Module: "AI PO Automation"
    ├── patches.txt                    # Empty (no patches)
    ├── ai_po_automation/              # Module directory
    │   └── doctype/
    │       ├── ai_po_processing/      # Main DocType
    │       │   ├── ai_po_processing.json
    │       │   ├── ai_po_processing.py   # Empty controller
    │       │   ├── ai_po_processing.js   # "Process PO" form button
    │       │   └── test_ai_po_processing.py  # Empty test scaffold
    │       └── ai_po_item/            # Child table DocType
    │           ├── ai_po_item.json
    │           └── ai_po_item.py      # Empty controller
    ├── services/                      # Business logic layer
    │   ├── pdf_service.py             # PDF text extraction & type detection
    │   ├── llm_service.py             # Gemini LLM extraction (digital POs)
    │   ├── vision_service.py          # Gemini Vision extraction (scanned POs)
    │   ├── customer_service.py        # Customer master matching
    │   ├── item_service.py            # Item master matching
    │   ├── validation_service.py      # PO data validation
    │   └── sales_order_service.py     # Sales Order creation
    ├── config/                        # Module configuration
    ├── patches/                       # Empty
    ├── public/
    │       └── css/ai_po_processing.css    # AI PO Processing form styles
    └── templates/                     # Empty
```

---

## 3. DocTypes

### 3.1 AI PO Processing (Main DocType)

- **Naming:** `AI-PO-.#####` (e.g., `AI-PO-00001`)
- **Permissions:** System Manager only
- **Controller:** empty (`pass`)

| Field | Type | Description |
|---|---|---|
| `po_attachment` | Attach (required) | Customer PO PDF file |
| `customer` | Link → Customer | Matched customer |
| `supplier_name` | Data | PO Supplier (Our Company) — as extracted by AI |
| `customer_po_number` | Data | Customer's PO number |
| `currency` | Link → Currency | PO currency |
| `status` | Select | `Received / Processing / Extracted / Validated / SO Created / Review Required / Failed / Completed` |
| `po_date` | Date | PO date |
| `delivery_date` | Date | Requested delivery date |
| `po_items` | Table → AI PO Item | Line items (child table) |
| `ai_confidence` | Percent | AI confidence score |
| `error_message` | Small Text | Validation/extraction errors |
| `validation_status` | Select | `Not Validated / Passed / Warning / Failed` |
| `sales_order` | Link → Sales Order | Created SO (output) |
| `matched_company` | Link → Company | Company matched from the PO supplier |
| `raw_ai_response` | Long Text | Pretty-printed Gemini JSON |

### 3.2 AI PO Item (Child Table)

| Field | Type | Description |
|---|---|---|
| `po_item_description` | Long Text | Full line item description from PO; no 140-character Data field limit. Existing sites must run `bench migrate` to update the DocType and database column. |
| `item_code` | Link → Item | Matched ERPNext item |
| `erpnext_item_description` | Long Text | Description copied from the matched ERPNext Item master; display-only |
| `customer_item_code` | Data | Customer's item code |
| `rate` | Currency | Unit rate extracted from the customer PO |
| `our_selling_price` | Currency | Generic selling price from the selling Price List configured in Selling Settings; blank if no single current price matches the PO currency and UOM |
| `match_confidence` | Percent | Item match confidence |
| `qty` | Float | Quantity |
| `uom` | Link → UOM | Unit of measure |
| `amount` | Currency | Line total |
| `validation_status` | Select | `Not Validated / Matched / Warning / Failed` |

---

## 4. API Endpoints

### `po_ai_automation.api.process_po(docname)` — `api.py`

- Whitelisted (`@frappe.whitelist()`), authentication required, sync HTTP call.
- **Inputs:** `docname` — name of an AI PO Processing document.
- **Steps:**
  1. Load doc; throw if `po_attachment` missing.
  2. Set `status = "Processing"`, clear `error_message`.
  3. Resolve File document → absolute file path.
  4. Extract PDF text (`pdf_service.extract_text_from_pdf`) and detect digital vs scanned.
  5. Branch: scanned → `vision_service.extract_po_data_from_scanned_pdf`; digital → `llm_service.extract_po_data`.
  6. Store raw Gemini JSON in `raw_ai_response`.
  7. `validation_service.validate_po_data` against Customer/Item masters.
  8. On validation failure → `status = "Failed"`, return errors.
  9. On success → `validation_service` passed → `sales_order_service.create_sales_order`.
  10. Set `status = "SO Created"`, link `sales_order`, commit, return success payload.
- **Error handling:** exceptions logged to Error Log (`AI PO Processing Error`), doc set to Failed, then `frappe.throw`.
- Uses `frappe.db.set_value` (bypasses controller events) and explicit `frappe.db.commit()`.

### AI PO Processing form

The existing DocType form presents a styled PO overview above its native
fields and item table. Processing, validation, and Sales Order behavior continue
to use the existing form and API workflow.

---

## 5. Services Layer

### 5.1 `pdf_service.py`
- `extract_text_from_pdf(file_path)` — opens PDF with **PyMuPDF (fitz)**, collects page text.
- Returns `{"is_text_pdf": bool, "text": str, "page_count": int}` — used as digital-vs-scanned detector (no OCR engine; scanned PDFs go to Vision).

### 5.2 `llm_service.py` (Digital POs)
- `extract_po_data(text)` — sends text + large extraction prompt to **Gemini** (`gemini-3.6-flash` via `google-genai` SDK).
- Prompt extracts: `customer_name`, `customer_gstin`, `supplier_name`, `supplier_gstin`, `po_number`, `po_date`, `delivery_date`, `currency`, `items[]` (description, PO item identifier `item_code`, qty, uom, rate, amount), `grand_total`; dates normalized to `YYYY-MM-DD`; nulls for unknowns; JSON-only output. Item identifiers may be ERPNext item codes or customer reference codes; code-column values are associated with their table rows.
- 3 retry attempts with exponential backoff (`2 ** attempt` seconds).
- Strips Markdown ```json fences before `json.loads`.

### 5.3 `vision_service.py` (Scanned POs)
- `extract_po_data_from_scanned_pdf(pdf_path)` — renders each PDF page at **2× scale** to PNG (`fitz.Matrix(2,2)`), sends inline images + prompt to **Gemini Vision**.
- Same JSON schema as text path.
- Uses the visible PO issuer logo/letterhead as an additional customer-role clue; a PO issuer logo normally identifies the buyer, while vendor details identify the supplier. Cross-checks both parties against their addresses and GSTINs instead of relying on company-block order/prominence.
- For digital/text PDFs where extracted roles appear reversed (the customer name resolves to our Company but the supplier does not), `process_po` runs this visual extraction as a role check and adopts the party fields only when both roles resolve to distinct ERPNext masters.
- 3 retries only for transient errors (503/500/502/504) with `5 * (attempt + 1)` second waits; failures logged to Error Log.
- Post-processing: JSON decode, ensures `items` list exists.

### 5.4 `customer_service.py`
- `find_customer(name)` — matching cascade: exact `customer_name` → case-insensitive `LIKE %name%` (limit 10) → **returns match only if exactly one** result (never guesses ambiguities).
- PO customer matching tries GSTIN first when present and falls back to the existing exact/unique-partial name lookup when GSTIN does not produce a unique match.

### 5.4a `company_service.py`
- PO supplier/company matching tries GSTIN first when present and falls back to the existing company-name lookup when GSTIN does not produce a unique match.

### 5.4b `gstin_service.py`
- `find_master_by_gstin(doctype, gstin)` — checks available `gstin` and `tax_id` fields on Customer/Company, normalizes the extracted value, and returns a match only when exactly one master record matches.

### 5.5 `item_service.py`
- `find_item(description)` — legacy/general helper: exact `item_name` → exact `item_code` → `LIKE %description%` (limit 10) → single-match only. PO validation does not call this helper.
- `find_item_by_code(item_code)` — exact ERPNext item-code match; used first for PO item validation.
- `find_item_by_customer_ref(item_code, customer)` — exact `Item Customer Detail.customer_name` + `ref_code` lookup; used only when the ERPNext item-code match fails.
- `get_standard_selling_price(item_code, currency, uom)` — reads the generic, current Item Price in the enabled selling Price List configured in Selling Settings (`selling_price_list`) without changing the customer PO rate; returns no value when the setting or price is missing or ambiguous.

### 5.6 `validation_service.py`
- `validate_po_data(po_data)` — verifies presence and validity of customer, **supplier (our company)**, PO number, date, currency, items; validates items by exact ERPNext item code, then by the resolved customer and customer reference code. Item description is retained for display and is not used to match or validate an item.
- **Supplier = our company check:** the supplier named on a customer PO is the party the PO is addressed to, so it must match one of our ERPNext **Companies** (`services/company_service.find_matching_company`: exact `company_name` = 100, exact docname = 95, unique partial = 80). If the PO's supplier matches no Company, validation fails with *"This PO does not appear to be for our company"* — preventing POs meant for other vendors from becoming Sales Orders. A missing supplier is also an error.
- Before validation, `correct_reversed_party_roles` first checks both extracted GSTINs against Company GSTINs. A Company GSTIN assigned to the customer is moved to the supplier side when the other party resolves to a Customer; a Company GSTIN already assigned to the supplier is kept there. The existing opposite-master role check remains for cases not resolved by GSTIN.
- **`ai_confidence` score (0–100):** extracted header fields (70: customer 15, supplier 10, po_number 10, po_date 10, delivery_date 5, currency 10, grand_total 10) + customer master match (15) + company match (5) + average item-code/customer-reference match (20).

### 5.7 `sales_order_service.py`
- `create_sales_order(po_data, validation_result)` — throws if validation failed; creates a **draft** Sales Order with `company` (from the PO supplier match), `customer`, `po_no`, `po_date`, `currency`, `delivery_date` and one row per validated item (`item_code`, `qty`, `rate`, `warehouse`); if delivery date is before today, sets `transaction_date` to the PO date, otherwise preserves ERPNext's default; `insert(ignore_permissions=True)`; returns SO name.
- When copying tax rows from the selected Sales Taxes and Charges Template, `get_taxes_and_charges_rows()` omits structurally identical duplicate GST rows (same GST account/type, charge type, rate, row basis, and inclusion flags) and logs the skipped rows. The source template should also be corrected in ERPNext.
- **Automatic taxes and charges:** ERPNext only fetches a tax template in the UI when a customer is selected — a server-side SO insert never runs that logic, so `get_taxes_and_charges_template()` resolves it and appends the template's tax rows before insert. Priority: (1) `po_sales_taxes_charges_template` in `site_config.json`, (2) standard ERPNext **Tax Rule** match (`party.set_taxes` for customer/company/date), (3) the company's default template (`is_default = 1`). Tax totals are then computed by ERPNext's normal validate flow.
- **Automatic warehouse:** ERPNext throws *"Source warehouse required for stock item"* if a stock item row has no warehouse, so `get_source_warehouse()` fills it automatically. Priority: (1) `po_source_warehouse` in `site_config.json`, (2) Item Default `default_warehouse` for the company, (3) any active non-group Company warehouse (preferring one named like "Stores"). If still none for a stock item, a clear error tells you which config to set.

---

## 6. Client Script

**`ai_po_processing.js`** (auto-loaded from DocType folder):

- On `refresh`: adds **"Process PO"** for saved documents and renders the PO overview in the form.
- Guards: requires `po_attachment`; asks confirmation.
- Calls `po_ai_automation.api.process_po` with `freeze: true` ("Processing Customer PO...").
- On success: green message + `frm.reload_doc()`.

---

## 7. Hooks & Scheduled Jobs

`hooks.py` includes the AI PO Processing stylesheet in Desk. Other hook sections
(scheduler_events, doc_events, fixtures, jinja, and background jobs) are not
configured. The AI pipeline runs synchronously inside the HTTP request.

---

## 8. Integrations

| Integration | Purpose | Configuration |
|---|---|---|
| **Google Gemini** (`google-genai` SDK) | LLM text extraction + Vision for scanned PDFs | `gemini_api_key` in `site_config.json`; model `gemini-3.6-flash` (hardcoded) |
| **PyMuPDF** (`fitz`) | PDF text extraction / digital-vs-scanned detection | Python package |

No other integrations (no OpenAI, email, WhatsApp, webhooks, external HTTP).

### Setup Requirements

1. Install dependencies manually (not declared in `pyproject.toml`):
   ```bash
   bench --site <site> pip install google-genai PyMuPDF
   ```
2. Add Gemini API key to `site_config.json`:
   ```json
   { "gemini_api_key": "<YOUR_KEY>" }
   ```
3. Install the app and migrate:
   ```bash
   bench get-app <repo-url> --branch version-16
   bench --site <site> install-app po_ai_automation
   bench --site <site> migrate
   ```

---

## 9. Tests & Patches

- **Tests:** `test_ai_po_processing.py` contains integration tests for extraction utilities, party/item matching, and Sales Order setup.
- **Patches:** none (`patches.txt` empty).

---

## 10. Status Lifecycle

```
Received (default)
   │
   ▼
Processing
   │
   ├──► Failed              (validation errors or exception)
   │
   └──► SO Created          (success, Sales Order linked)
```

> The options `Extracted`, `Validated`, `Review Required`, `Completed` exist on the DocType but are not set by the current code.

---

## 11. Known Gaps / Future Improvements

- **Child table populated:** `po_items` rows (with `match_confidence` and per-row `validation_status`), `ai_confidence`, `customer`, `customer_po_number`, `currency`, `po_date`, and `delivery_date` are saved on the AI PO Processing doc after extraction (API step 6B). Overall `ai_confidence` is computed in `validation_service.calculate_confidence` (header fields 65 + customer match 15 + item matches 20, scaled 0–100). Match confidences: exact customer/item name = 100, exact item code = 95, unique partial match = 80.
- **Synchronous processing:** long Gemini calls block the HTTP request; consider moving to a background job (`frappe.enqueue`) with realtime status updates.
- **Delivery date:** set on the SO header; ERPNext typically expects delivery dates on item rows — may need adjustment.
- **Item row fields:** `uom` and `amount` are not set on created SO items.
- **Dependencies undeclared:** `google-genai` and `PyMuPDF` should be added to `pyproject.toml`.
- **No item matching review flow:** ambiguous matches fail validation outright instead of routing to a "Review Required" state.
- **Dead code:** older commented-out iterations remain in `api.py`, `llm_service.py`, `vision_service.py`, `pdf_service.py`, and the DocType JS file.
