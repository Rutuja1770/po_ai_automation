// Copyright (c) 2026, Assimilate and contributors
// For license information, please see license.txt

// frappe.ui.form.on("AI PO Processing", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("AI PO Processing", {
    refresh(frm) {
        frm.$wrapper.addClass("po-ai-processing-form");
        render_form_dashboard(frm);

        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button("Process PO", () => {
            process_po(frm, true);
        });
    },

    po_attachment(frm) {
        render_form_dashboard(frm);

        if (!frm.doc.po_attachment || frm.__po_auto_processing) {
            return;
        }

        frm.__po_auto_processing = true;

        const start_processing = () => Promise.resolve()
            .then(() => process_po(frm, false))
            .then(
                () => {
                    frm.__po_auto_processing = false;
                },
                (error) => {
                    frm.__po_auto_processing = false;
                    frappe.msgprint({
                        title: __("PO Processing Failed"),
                        message: error.message || __("Unable to process the uploaded file."),
                        indicator: "red"
                    });
                }
            );

        if (frm.is_new() || frm.is_dirty()) {
            frm.save().then(
                start_processing,
                (error) => {
                    frm.__po_auto_processing = false;
                    frappe.msgprint({
                        title: __("Unable to Save PO"),
                        message: error.message || __("The PO could not be saved, so processing was not started."),
                        indicator: "red"
                    });
                }
            );
            return;
        }

        start_processing();
    },

    customer: render_form_dashboard,
    supplier_name: render_form_dashboard,
    customer_po_number: render_form_dashboard,
    status: render_form_dashboard,
    validation_status: render_form_dashboard,
    ai_confidence: render_form_dashboard,
    sales_order: render_form_dashboard,
    po_date: render_form_dashboard,
    delivery_date: render_form_dashboard,
    currency: render_form_dashboard,
    error_message: render_form_dashboard,
    po_items_add: render_form_dashboard,
    po_items_remove: render_form_dashboard
});

function render_form_dashboard(frm) {
    const $layout = frm.$wrapper.find(".form-layout");
    if (!$layout.length) {
        return;
    }

    const $formPage = $layout.children(".form-page").first();
    if (!$formPage.length) {
        return;
    }

    let $workspace = $layout.children(".po-ai-form-workspace");
    if (!$workspace.length) {
        $workspace = $(`
            <div class="po-ai-form-workspace">
                <header class="po-ai-workspace-hero">
                    <div class="po-ai-workspace-brand">
                        <span class="po-ai-workspace-mark">AI</span>
                        <div>
                            <span class="po-ai-form-eyebrow">${__("AI WORKSPACE")} / ${__("PURCHASE ORDERS")}</span>
                            <h1>${__("AI PO Processing")}</h1>
                            <p>${__("Review extracted purchase order details and validate with confidence.")}</p>
                        </div>
                    </div>
                    <span class="po-ai-workspace-tag">${__("Smart. Faster. Accurate.")}</span>
                </header>
                <section class="po-ai-workspace-metrics" aria-label="${__("Purchase order summary")}"></section>
                <div class="po-ai-workspace-top-grid">
                    <div class="po-ai-workspace-po"></div>
                    <div class="po-ai-workspace-validation"></div>
                </div>
                <div class="po-ai-workspace-items"></div>
                <div class="po-ai-workspace-bottom-grid">
                    <div class="po-ai-workspace-erp"></div>
                    <section class="po-ai-workspace-timeline po-ai-ui-card"></section>
                </div>
                <div class="po-ai-workspace-response"></div>
            </div>
        `);
        $workspace.insertBefore($formPage);
    }

    const sectionTargets = {
        po_information_section: ".po-ai-workspace-po",
        section_break_fpzn: ".po-ai-workspace-items",
        ai_processing_section: ".po-ai-workspace-validation",
        erpnext_result_section: ".po-ai-workspace-erp",
        ai_response_section: ".po-ai-workspace-response"
    };
    Object.entries(sectionTargets).forEach(([fieldname, target]) => {
        const $section = $layout.find(
            `.form-section[data-fieldname="${fieldname}"]`
        ).first();
        if ($section.length) {
            $workspace.find(target).append($section);
        }
    });

    const doc = frm.doc;
    const escape = (value) => frappe.utils.escape_html(String(value || ""));
    const status = doc.status || __("Received");
    const statusClass = status.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    const validationStatus = doc.validation_status || __("Not Validated");
    const confidence = doc.ai_confidence === null || doc.ai_confidence === undefined
        ? __("Not available")
        : `${Math.round(Number(doc.ai_confidence))}%`;
    const items = doc.po_items || [];
    const $poInformation = $workspace.find(
        '.po-ai-workspace-po .form-section[data-fieldname="po_information_section"]'
    );
    let $poSummary = $poInformation.find(".po-ai-po-summary-card");
    if (!$poSummary.length) {
        $poSummary = $('<div class="po-ai-po-summary-card"></div>');
        $poInformation.find(".section-body").prepend($poSummary);
    }

    const extractedPartyIds = get_extracted_party_ids(doc.raw_ai_response);
    const customerGstin = extractedPartyIds.customer_gstin;
    const supplierGstin = extractedPartyIds.supplier_gstin;
    const mismatchMessage = String(doc.error_message || "");
    const needsCustomerSelection = mismatchMessage.includes("Customer not matched:");
    const needsCompanySelection = mismatchMessage.includes(
        "Supplier / Our Company not matched:"
    );

    const $statusControl = $poInformation.find(
        '.frappe-control[data-fieldname="status"]'
    );
    $statusControl.attr("data-po-status", statusClass);

    const $poColumns = $poInformation.find(".section-body > .form-column");
    $poColumns
        .removeClass("po-ai-po-attachment-column")
        .filter((_, column) => $(column).find(
            '.frappe-control[data-fieldname="po_attachment"]'
        ).length > 0)
        .addClass("po-ai-po-attachment-column");

    $poInformation.find(
        '.frappe-control[data-fieldname="po_date"], .frappe-control[data-fieldname="delivery_date"]'
    ).closest(".form-column").addClass("po-ai-po-details-column");

    const $currencyControl = $poInformation.find(
        '.frappe-control[data-fieldname="currency"]'
    );
    $currencyControl.find(".control-input").attr(
        "data-po-currency",
        doc.currency === "INR" ? "₹" : (doc.currency || "")
    );

    $poSummary.html(`
        <div class="po-ai-po-summary-header">
            <div class="po-ai-po-summary-title">
                <div>
                    <h2>${__("Purchase order details")}</h2>
                    <p>${__("Extracted from uploaded document")}</p>
                </div>
            </div>
        </div>
        <div class="po-ai-po-parties">
            <div class="po-ai-po-party">
                <span class="po-ai-po-party-icon" aria-hidden="true">♙</span>
                <div>
                    <span class="po-ai-po-summary-label">${__("Customer")}</span>
                    <strong>${escape(doc.customer || __("Not available"))}</strong>
                    ${customerGstin
                        ? `<small>GSTIN ${escape(customerGstin)}</small>`
                        : ""}
                </div>
            </div>
            <div class="po-ai-po-party">
                <span class="po-ai-po-party-icon company" aria-hidden="true">▥</span>
                <div>
                    <span class="po-ai-po-summary-label">${__("Supplier / Our Company")}</span>
                    <strong>${escape(doc.matched_company || doc.supplier_name || __("Not available"))}</strong>
                    ${supplierGstin
                        ? `<small>GSTIN ${escape(supplierGstin)}</small>`
                        : ""}
                </div>
            </div>
        </div>
        <div class="po-ai-po-meta">
            ${po_summary_value(__("Customer PO Number"), doc.customer_po_number, "▣", escape)}
            ${po_summary_value(__("PO Date"), format_po_date(doc.po_date), "▦", escape)}
            ${po_summary_value(__("Currency"), doc.currency, "₹", escape)}
            ${po_summary_value(__("Delivery Date"), format_delivery_date(doc.delivery_date), "▱", escape)}
        </div>
        ${needsCustomerSelection || needsCompanySelection
            ? `<div class="po-ai-company-mismatch">
                <div>
                    <strong>${__("Customer / Supplier match required")}</strong>
                    <p>${escape(mismatchMessage)}</p>
                    <small>${__("Select each unmatched party. The PO will be validated again before a Sales Order is created.")}</small>
                </div>
                <button type="button" class="btn btn-primary btn-sm po-ai-select-company">
                    ${needsCustomerSelection && needsCompanySelection
                        ? __("Select Customer & Company")
                        : needsCustomerSelection
                            ? __("Select Customer")
                            : __("Select Company")}
                </button>
            </div>`
            : ""}
    `);
    $poSummary
        .off("click", ".po-ai-select-company")
        .on("click", ".po-ai-select-company", () => {
            select_parties_for_po(frm, needsCustomerSelection, needsCompanySelection);
        });

    const validationTone = ["Failed", "Warning"].includes(doc.validation_status)
        ? "warning"
        : doc.validation_status === "Passed"
            ? "success"
            : "neutral";
    const errorMessage = String(doc.error_message || "");
    const hasErrorMessage = Boolean(errorMessage.trim());
    const errorCount = hasErrorMessage
        ? errorMessage.split(/\r?\n/).filter(Boolean).length
        : 0;
    const $errorControl = $workspace.find(
        '.po-ai-workspace-validation .frappe-control[data-fieldname="error_message"]'
    );
    $errorControl.addClass("po-ai-error-control");
    $errorControl.find(".po-ai-view-error").remove();
    $errorControl.find(".control-input-wrapper").append(`
        <button
            type="button"
            class="btn btn-default po-ai-view-error"
            ${hasErrorMessage ? "" : "disabled"}
        >
            ${hasErrorMessage
                ? `${__("View Error")}${errorCount ? ` (${errorCount})` : ""}`
                : __("No Errors")}
        </button>
    `);
    $workspace
        .off("click.poAiViewError", ".po-ai-view-error")
        .on("click.poAiViewError", ".po-ai-view-error", () => {
            if (!errorMessage) {
                return;
            }

            frappe.msgprint({
                title: __("Error Details"),
                message: `<pre class="po-ai-error-dialog-content">${escape(errorMessage)}</pre>`,
                indicator: validationTone === "warning" ? "red" : "blue",
                wide: true
            });
        });

    $workspace.find(".po-ai-workspace-hero h1")
        .text(doc.name || __("AI PO Processing"));

    $workspace.find(".po-ai-workspace-metrics").html([
        metric_card(
            __("Processing Status"),
            status,
            __("Current purchase order"),
            statusClass
        ),
        metric_card(
            __("AI Confidence"),
            confidence,
            __("Extraction confidence"),
            "confidence"
        ),
        metric_card(
            __("PO Items"),
            String(items.length),
            __("Extracted line items"),
            "items"
        ),
        metric_card(
            __("Validation"),
            validationStatus,
            __("Current app-level result"),
            validationTone
        )
    ].join(""));

    $workspace.find(".po-ai-open-sales-order").remove();
    if (doc.sales_order) {
        $workspace.find(".po-ai-workspace-erp .section-body").append(`
            <a class="po-ai-open-sales-order" href="/app/sales-order/${encodeURIComponent(doc.sales_order)}">
                ${__("Open Sales Order")} <span aria-hidden="true">&nearr;</span>
            </a>
        `);
    }

    render_workflow($workspace, doc, escape);
    render_validation_summary($workspace, doc, escape);
}

function metric_card(label, value, note, tone) {
    const escape = (text) => frappe.utils.escape_html(String(text || ""));
    return `
        <article class="po-ai-metric-card">
            <span class="po-ai-metric-icon ${escape(tone)}" aria-hidden="true"></span>
            <div class="po-ai-metric-copy">
                <span>${escape(label)}</span>
                <strong>${escape(value)}</strong>
                <small>${escape(note)}</small>
            </div>
        </article>
    `;
}

function po_summary_value(label, value, icon, escape) {
    return `
        <div class="po-ai-po-meta-item">
            <span class="po-ai-po-meta-icon" aria-hidden="true">${escape(icon)}</span>
            <div>
                <span class="po-ai-po-summary-label">${escape(label)}</span>
                <strong>${escape(value || __("Not available"))}</strong>
            </div>
        </div>
    `;
}

function get_extracted_party_ids(raw_response) {
    if (!raw_response) {
        return { customer_gstin: "", supplier_gstin: "" };
    }

    try {
        const extracted = JSON.parse(raw_response);
        if (!extracted || typeof extracted !== "object") {
            return { customer_gstin: "", supplier_gstin: "" };
        }
        return {
            customer_gstin: extracted.customer_gstin || "",
            supplier_gstin: extracted.supplier_gstin || ""
        };
    } catch (error) {
        console.warn(__("Could not read the extracted GSTIN values."), error);
        return { customer_gstin: "", supplier_gstin: "" };
    }
}

function format_po_date(date) {
    return date ? frappe.datetime.str_to_user(date) : "";
}

function format_delivery_date(date) {
    if (!date) {
        return "";
    }
    return date === frappe.datetime.get_today()
        ? __("Today")
        : frappe.datetime.str_to_user(date);
}

function render_workflow($workspace, doc, escape) {
    const extracted = Boolean(doc.raw_ai_response);
    const validationDone = ["Passed", "Warning", "Failed"].includes(
        doc.validation_status
    );
    const steps = [
        {
            label: __("PO Uploaded"),
            detail: doc.po_attachment ? __("Source document is attached") : __("Waiting for a document"),
            done: Boolean(doc.po_attachment)
        },
        {
            label: __("Data Extracted"),
            detail: extracted ? __("Extracted data is saved") : __("Waiting for extraction"),
            done: extracted
        },
        {
            label: __("Validation"),
            detail: doc.validation_status || __("Not validated"),
            done: validationDone,
            current: ["Warning", "Failed"].includes(doc.validation_status)
        },
        {
            label: __("Sales Order"),
            detail: doc.sales_order || __("Not created"),
            done: Boolean(doc.sales_order)
        }
    ];

    $workspace.find(".po-ai-workspace-timeline").html(`
        <div class="po-ai-ui-card-heading">
            <span class="po-ai-ui-icon workflow">4</span>
            <h2>${__("Workflow")}</h2>
        </div>
        <ol class="po-ai-workflow-list">
            ${steps.map((step) => `
                <li class="${step.done ? "done" : ""} ${step.current ? "current" : ""}">
                    <span class="po-ai-workflow-dot">${step.done ? "✓" : ""}</span>
                    <div><strong>${escape(step.label)}</strong><small>${escape(step.detail)}</small></div>
                </li>
            `).join("")}
        </ol>
        <p class="po-ai-workflow-note">${__("Stages reflect the current record; processing history is not stored.")}</p>
    `);
}

function render_validation_summary($workspace, doc, escape) {
    const items = doc.po_items || [];
    const itemCodesMatched = items.length > 0 &&
        items.every((item) => item.validation_status === "Matched");
    const checks = [
        {
            label: __("Customer matched"),
            passed: Boolean(doc.customer)
        },
        {
            label: __("Company matched"),
            passed: Boolean(doc.matched_company)
        },
        {
            label: __("Item codes matched"),
            passed: itemCodesMatched
        },
        {
            label: __("PO number and date present"),
            passed: Boolean(doc.customer_po_number && doc.po_date)
        }
    ];
    const complete = doc.validation_status === "Passed" &&
        checks.every((check) => check.passed);
    const hasValidationRun = ["Passed", "Warning", "Failed"].includes(
        doc.validation_status
    );
    const title = complete
        ? __("Validation Complete")
        : hasValidationRun
            ? __("Validation Needs Attention")
            : __("Validation Pending");
    const description = complete
        ? __("All items are successfully matched and verified.")
        : hasValidationRun
            ? __("Review the failed checks and error details.")
            : __("Run PO processing to check customer, company, items, and PO details.");

    $workspace.find(
        ".po-ai-workspace-validation-summary, .po-ai-validation-checklist"
    ).remove();
    $workspace.find(".po-ai-workspace-validation").append(`
        <section class="po-ai-validation-checklist ${complete ? "complete" : hasValidationRun ? "needs-attention" : "pending"}" aria-live="polite">
            <div class="po-ai-validation-checklist-heading">
                <span class="po-ai-validation-checklist-icon" aria-hidden="true">${complete ? "✓" : hasValidationRun ? "!" : "…"}</span>
                <div>
                    <strong>${escape(title)}</strong>
                    <small>${escape(description)}</small>
                </div>
            </div>
            <ul>
                ${checks.map((check) => `
                    <li class="${check.passed ? "passed" : "not-passed"}">
                        <span aria-hidden="true">${check.passed ? "✓" : "○"}</span>
                        ${escape(check.label)}
                    </li>
                `).join("")}
            </ul>
        </section>
    `);
}

function process_po(frm, require_confirmation) {

    if (!frm.doc.po_attachment) {
        frappe.msgprint({
            title: "PO Attachment Required",
            message: "Please upload a Customer PO PDF or image first.",
            indicator: "red"
        });

        return Promise.resolve();
    }

    const start_processing = () => {
        frappe.show_alert({
            message: "PO processing started...",
            indicator: "blue"
        });

        return frappe.call({
            method: "po_ai_automation.api.process_po",
            args: {
                docname: frm.doc.name
            },
            freeze: true,
            freeze_message: "Processing Customer PO..."
        }).then(r => {

            if (r.message) {
                if (r.message.status === "company_confirmation_required") {
                    frm.reload_doc();
                    frappe.msgprint({
                        title: __("Customer / Supplier Match Required"),
                        message: frappe.utils.escape_html(r.message.message),
                        indicator: "orange"
                    });
                    return r;
                }

                const extractedData = r.message.data;
                const missingDeliveryDate = Boolean(
                    extractedData &&
                    !extractedData.delivery_date
                );

                frappe.msgprint({
                    title: missingDeliveryDate
                        ? __("PO Processing Completed — Review Delivery Date")
                        : __("PO Processing Completed"),
                    message: missingDeliveryDate
                        ? __(
                            "No delivery date was found in the PO. " +
                            "We set a default delivery date (today). " +
                            "Please change it according to your requirement."
                        )
                        : __("PO was processed successfully."),
                    indicator: missingDeliveryDate ? "orange" : "green"
                });

                frm.reload_doc();
            }

            return r;
        });
    };

    if (require_confirmation) {
        frappe.confirm(
            "Do you want to process this PO using AI?",
            start_processing
        );
        return Promise.resolve();
    }

    return start_processing();
}

function select_parties_for_po(frm, needsCustomerSelection, needsCompanySelection) {
    const fields = [];
    if (needsCustomerSelection) {
        fields.push({
            fieldname: "customer",
            fieldtype: "Link",
            label: __("Customer"),
            options: "Customer",
            reqd: 1
        });
    }
    if (needsCompanySelection) {
        fields.push({
            fieldname: "company",
            fieldtype: "Link",
            label: __("Our Company"),
            options: "Company",
            reqd: 1
        });
    }

    frappe.prompt(
        fields,
        values => {
            frappe.call({
                method: "po_ai_automation.api.create_sales_order_with_company",
                args: {
                    docname: frm.doc.name,
                    customer: values.customer || "",
                    company: values.company || ""
                },
                freeze: true,
                freeze_message: __("Creating Sales Order...")
            }).then(r => {
                if (r.message && r.message.status === "success") {
                    frappe.msgprint({
                        title: __("Sales Order Created"),
                        message: __("Sales Order {0} was created.", [
                            frappe.utils.escape_html(r.message.sales_order)
                        ]),
                        indicator: "green"
                    });
                    frm.reload_doc();
                }
            }).catch(error => {
                frappe.msgprint({
                    title: __("Unable to Create Sales Order"),
                    message: error.message || __("Check the selected company and PO details, then try again."),
                    indicator: "red"
                });
            });
        },
        __("Select Our Company"),
        __("Create Sales Order")
    );
}