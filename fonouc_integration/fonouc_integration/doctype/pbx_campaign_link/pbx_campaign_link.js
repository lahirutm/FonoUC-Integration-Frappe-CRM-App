frappe.ui.form.on("PBX Campaign Link", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Sync Leads to PBX Now"), () => {
                frappe.confirm(
                    `Push CRM leads to PBX campaign <b>${frm.doc.campaign_name}</b>?`,
                    () => frm.call("sync_leads_now")
                );
            }, __("Campaign"));

            frm.add_custom_button(__("View PBX Campaigns"), () => {
                frappe.call({
                    method: "fonouc_integration.fonouc_integration.api.endpoints.get_pbx_campaigns",
                    callback(r) {
                        if (r.message) {
                            let rows = r.message.map(c =>
                                `<tr><td>${c.id}</td><td>${c.name}</td><td>${c.status}</td></tr>`
                            ).join("");
                            frappe.msgprint({
                                title: "PBX Campaigns",
                                message: `<table class="table table-bordered">
                                    <thead><tr><th>ID</th><th>Name</th><th>Status</th></tr></thead>
                                    <tbody>${rows}</tbody>
                                </table>`,
                                wide: true
                            });
                        }
                    }
                });
            }, __("Campaign"));
        }
    }
});
