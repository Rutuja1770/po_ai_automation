// Copyright (c) 2026, Assimilate and contributors
// For license information, please see license.txt

// frappe.ui.form.on("AI PO Processing", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("AI PO Processing", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button("Process PO", () => {
            process_po(frm);
        });
    }
});


function process_po(frm) {

    if (!frm.doc.po_attachment) {
        frappe.msgprint({
            title: "PO Attachment Required",
            message: "Please upload a Customer PO PDF or image first.",
            indicator: "red"
        });

        return;
    }

    frappe.confirm(
        "Do you want to process this PO using AI?",
        () => {

            frappe.show_alert({
                message: "PO processing started...",
                indicator: "blue"
            });

            frappe.call({
                method: "po_ai_automation.api.process_po",
                args: {
                    docname: frm.doc.name
                },
                freeze: true,
                freeze_message: "Processing Customer PO..."
            }).then(r => {

                if (r.message) {

                    frappe.msgprint({
                        title: "PO Processing Completed",
                        message: "PO was processed successfully.",
                        indicator: "green"
                    });

                    frm.reload_doc();
                }

            });

        }
    );
}