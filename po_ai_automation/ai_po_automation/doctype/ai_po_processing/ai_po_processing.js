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
            process_po(frm, true);
        });
    },

    po_attachment(frm) {
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
    }
});


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

                frappe.msgprint({
                    title: "PO Processing Completed",
                    message: "PO was processed successfully.",
                    indicator: "green"
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