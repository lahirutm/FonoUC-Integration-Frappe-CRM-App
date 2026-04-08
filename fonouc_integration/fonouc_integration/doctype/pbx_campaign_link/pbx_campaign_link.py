import frappe
from frappe.model.document import Document


class PBXCampaignLink(Document):

    @frappe.whitelist()
    def sync_leads_now(self):
        """Manually trigger lead sync for this campaign."""
        from fonouc_integration.fonouc_integration.api.campaign_sync import sync_campaign
        result = sync_campaign(self.name)
        frappe.msgprint(
            f"✅ Synced {result['pushed']} leads to PBX campaign <b>{self.campaign_name}</b>.",
            title="Campaign Sync",
            indicator="green",
        )
