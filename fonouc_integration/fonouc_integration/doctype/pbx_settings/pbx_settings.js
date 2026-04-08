frappe.ui.form.on("PBX Settings", {
    refresh(frm) {
        frm.add_custom_button(__("Test Connection"), () => {
            frm.call("test_connection");
        }, __("PBX Actions"));

        frm.add_custom_button(__("Sync PBX Users"), () => {
            frm.call("sync_users");
        }, __("PBX Actions"));

        frm.add_custom_button(__("Sync CDRs Now"), () => {
            frappe.call({
                method: "fonouc_integration.fonouc_integration.api.cdr_sync.sync_cdrs",
                callback(r) {
                    if (!r.exc) {
                        frappe.show_alert({ message: "CDR sync triggered!", indicator: "green" });
                        frm.reload_doc();
                    }
                }
            });
        }, __("PBX Actions"));
    },
});
