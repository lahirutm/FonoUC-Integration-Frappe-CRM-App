import frappe
from fonouc_integration.fonouc_integration.api.pbx_client import FonoUCClient


def boot_session(bootinfo):
    try:
        settings = frappe.get_single("PBX Settings")
        bootinfo.pbx_enabled = bool(settings.pbx_url)
        bootinfo.pbx_url = settings.pbx_url or ""
    except Exception:
        bootinfo.pbx_enabled = False


@frappe.whitelist()
def initiate_call(destination: str):
    user = frappe.session.user
    agent = frappe.db.get_value(
        "PBX Agent Mapping",
        {"frappe_user": user, "is_active": 1},
        ["pbx_email", "pbx_extension"],
        as_dict=True,
    )
    if not agent:
        frappe.throw(
            f"No PBX agent mapped for user <b>{user}</b>. Set up an Agent Mapping first.",
            title="PBX Not Configured",
        )
    client = FonoUCClient()
    magic_link = client.get_ucp_login_url()
    frappe.logger().info(f"Click-to-Call: {user} ({agent.pbx_email}) → {destination}")
    return {
        "status": "ok",
        "magic_link": magic_link,
        "destination": destination,
        "agent_email": agent.pbx_email,
    }


@frappe.whitelist()
def get_live_status():
    client = FonoUCClient()
    try:
        queues = client.get_queues_status()
        calls  = client.get_queues_calls()
    except Exception as e:
        frappe.throw(f"Could not fetch live status: {e}")
    if isinstance(queues, dict) and "id" in queues:
        queues = [queues]
    if not isinstance(queues, list):
        queues = []
    if isinstance(calls, dict):
        calls = [calls]
    if not isinstance(calls, list):
        calls = []
    return {"queues": queues, "live_calls": calls}


@frappe.whitelist()
def get_pbx_campaigns():
    client = FonoUCClient()
    return client.get_campaigns()


@frappe.whitelist()
def trigger_campaign_sync(campaign_link_name: str):
    from fonouc_integration.fonouc_integration.api.campaign_sync import sync_campaign
    return sync_campaign(campaign_link_name)


@frappe.whitelist()
def get_call_logs(reference_doctype: str, reference_name: str):
    field_map = {
        "CRM Lead":  "linked_lead",
        "CRM Deal":  "linked_deal",
        "Contact":   "linked_contact",
    }
    field = field_map.get(reference_doctype)
    if not field:
        return []
    return frappe.get_all(
        "PBX Call Log",
        filters={field: reference_name},
        fields=[
            "name", "call_datetime", "direction", "status",
            "caller_number", "caller_name", "called_number",
            "agent_name", "agent_extension", "duration",
            "has_recording", "recording_url", "disposition",
        ],
        order_by="call_datetime desc",
        limit=50,
    )


@frappe.whitelist()
def get_recording_url(call_id: str):
    client = FonoUCClient()
    rec_id = frappe.db.get_value("PBX Call Log", call_id, "recording_id")
    if not rec_id:
        frappe.throw("No recording found for this call.")
    url = client.get_recording_url(rec_id)
    frappe.db.set_value("PBX Call Log", call_id, {"has_recording": 1, "recording_url": url})
    frappe.db.commit()
    return {"url": url}


@frappe.whitelist(allow_guest=False)
def find_lead_by_phone(phone: str):
    if not phone:
        return {}
    short = phone[-9:] if len(phone) >= 9 else phone
    lead = frappe.db.sql(
        "SELECT name FROM `tabCRM Lead` WHERE mobile_no LIKE %s OR phone LIKE %s LIMIT 1",
        (f"%{short}", f"%{short}"), as_dict=True,
    )
    if lead:
        return {"lead": lead[0].name}
    return {}
