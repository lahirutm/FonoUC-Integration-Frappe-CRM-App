import frappe
from frappe.model.document import Document


class PBXAgentMapping(Document):
    pass


def get_frappe_user_for_extension(extension):
    """Resolve a PBX extension to a Frappe user email."""
    result = frappe.db.get_value(
        "PBX Agent Mapping",
        {"pbx_extension": extension, "is_active": 1},
        "frappe_user"
    )
    return result


def get_frappe_user_for_pbx_id(pbx_user_id):
    """Resolve a PBX user ID to a Frappe user email."""
    result = frappe.db.get_value(
        "PBX Agent Mapping",
        {"pbx_user_id": pbx_user_id, "is_active": 1},
        "frappe_user"
    )
    return result
