import frappe


@frappe.whitelist()
def is_call_integration_enabled():
    """
    Override of crm.integrations.api.is_call_integration_enabled
    Returns fonouc_enabled AND spoofs twilio_enabled so CRM shows call button.
    """
    fonouc_enabled = frappe.db.get_single_value("CRM FonoUC Settings", "enabled")

    from crm.integrations.api import get_user_default_calling_medium
    default_medium = get_user_default_calling_medium()

    return {
        "twilio_enabled":         1 if fonouc_enabled else 0,
        "exotel_enabled":         0,
        "fonouc_enabled":         fonouc_enabled,
        "default_calling_medium": default_medium or "FonoUC",
    }
