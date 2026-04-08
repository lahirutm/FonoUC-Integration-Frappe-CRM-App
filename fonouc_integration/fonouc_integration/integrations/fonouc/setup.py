import frappe


def add_fonouc_fields_to_telephony_agent():
    """
    Add FonoUC-specific fields to CRM Telephony Agent via Custom Fields.
    This runs after migrate so it survives CRM app updates.
    """
    fields_to_add = [
        {
            "dt": "CRM Telephony Agent",
            "fieldname": "fonouc",
            "fieldtype": "Check",
            "label": "FonoUC",
            "insert_after": "exotel",
        },
        {
            "dt": "CRM Telephony Agent",
            "fieldname": "fonouc_extension",
            "fieldtype": "Data",
            "label": "FonoUC Extension",
            "insert_after": "fonouc",
        },
        {
            "dt": "CRM Telephony Agent",
            "fieldname": "fonouc_email",
            "fieldtype": "Data",
            "label": "FonoUC Email",
            "insert_after": "fonouc_extension",
        },
    ]

    for field in fields_to_add:
        if not frappe.db.exists("Custom Field", {"dt": field["dt"], "fieldname": field["fieldname"]}):
            custom_field = frappe.new_doc("Custom Field")
            custom_field.update(field)
            custom_field.insert(ignore_permissions=True)
            frappe.logger().info(f"Added custom field {field['fieldname']} to {field['dt']}")

    frappe.db.commit()
