import frappe
from frappe.model.document import Document


class CRMFonoUCSettings(Document):
    def validate(self):
        if self.pbx_url:
            self.pbx_url = self.pbx_url.rstrip("/")
