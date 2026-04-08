import frappe
from frappe.model.document import Document


class PBXSettings(Document):
    def validate(self):
        if self.pbx_url:
            self.pbx_url = self.pbx_url.rstrip("/")

    def on_update(self):
        # Clear cached token when settings change
        frappe.cache().delete_value("pbx_auth_token")

    @frappe.whitelist()
    def test_connection(self):
        """Test PBX connection from the Settings form."""
        from fonouc_integration.fonouc_integration.api.pbx_client import FonoUCClient
        try:
            client = FonoUCClient()
            result = client.get("/ucp/v2/account/basic")
            frappe.msgprint(
                f"✅ Connected successfully! Account: <b>{result.get('name', 'Unknown')}</b>",
                title="PBX Connection Test",
                indicator="green",
            )
        except Exception as e:
            frappe.throw(f"Connection failed: {str(e)}")

    @frappe.whitelist()
    def sync_users(self):
        """Sync PBX users to Agent Mapping table."""
        from fonouc_integration.fonouc_integration.api.pbx_client import FonoUCClient
        try:
            client = FonoUCClient()
            users = client.get("/api/v2/config/users")
            count = 0
            for u in users:
                email = u.get("username") or u.get("email", "")
                if not email:
                    continue
                if not frappe.db.exists("PBX Agent Mapping", {"pbx_user_id": u.get("id")}):
                    doc = frappe.new_doc("PBX Agent Mapping")
                    doc.pbx_user_id = u.get("id")
                    doc.pbx_extension = u.get("presence_id") or u.get("username")
                    doc.pbx_user_name = f"{u.get('first_name','')} {u.get('last_name','')}".strip()
                    doc.pbx_email = email
                    # Auto-map if Frappe user with same email exists
                    if frappe.db.exists("User", email):
                        doc.frappe_user = email
                    doc.insert(ignore_permissions=True)
                    count += 1
            frappe.db.commit()
            frappe.msgprint(f"✅ Synced {count} new PBX users.", title="User Sync", indicator="green")
        except Exception as e:
            frappe.throw(f"User sync failed: {str(e)}")
