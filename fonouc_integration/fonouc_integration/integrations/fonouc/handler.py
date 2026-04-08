"""
FonoUC Telephony Integration for Frappe CRM
Follows the same pattern as Exotel/Twilio integrations.
"""
import frappe
from frappe import _

from crm.integrations.api import get_contact_by_phone_number


@frappe.whitelist()
def is_integration_enabled():
    return frappe.db.get_single_value("CRM FonoUC Settings", "enabled", True)


@frappe.whitelist()
def make_a_call(to_number, caller_id=None):
    """
    Outbound Click-to-Call using FonoUC.
    Opens the UCP softphone in a popup window.
    Returns call details and the UCP URL for the frontend to open.
    """
    if not is_integration_enabled():
        frappe.throw(_("FonoUC integration is not enabled"), title=_("Not Enabled"))

    user = frappe.session.user

    # Get agent's PBX details
    agent = frappe.db.get_value(
        "CRM Telephony Agent",
        user,
        ["mobile_no", "fonouc_extension", "fonouc_email"],
        as_dict=True,
    )
    if not agent:
        frappe.throw(
            _("No Telephony Agent configured for {0}").format(user),
            title=_("Agent Not Found"),
        )

    if not agent.fonouc_extension:
        frappe.throw(
            _("No FonoUC extension set for agent {0}. Please configure it in CRM Telephony Agent.").format(user),
            title=_("Extension Missing"),
        )

    # Get UCP URL for the popup
    from fonouc_integration.fonouc_integration.api.pbx_client import FonoUCClient
    client = FonoUCClient()
    settings = frappe.get_single("CRM FonoUC Settings")

    import re
    domain = re.sub(r':\d+$', '', settings.pbx_url.replace('https://', '').replace('http://', ''))
    ucp_url = f"https://{domain}/ucp/login"

    # Generate a unique call ID
    import uuid
    call_id = f"fonouc-{uuid.uuid4().hex[:16]}"

    # Create CRM Call Log immediately as "Initiated"
    call_log = create_call_log(
        call_id=call_id,
        from_number=agent.fonouc_extension,
        to_number=to_number,
        agent=user,
        status="Initiated",
        call_type="Outgoing",
    )

    frappe.logger().info(f"FonoUC Click-to-Call: {user} ext:{agent.fonouc_extension} → {to_number}")

    return {
        "call_id": call_id,
        "ucp_url": ucp_url,
        "to_number": to_number,
        "from_extension": agent.fonouc_extension,
        "status": "Initiated",
    }


@frappe.whitelist(allow_guest=True)
def handle_incoming(**kwargs):
    """
    Webhook endpoint for FonoUC Pivot/Callflow to send incoming call events.
    Configure in FonoUC callflow: voice_url = https://erp.cybergate.lk/api/method/fonouc_integration.fonouc_integration.integrations.fonouc.handler.handle_incoming
    """
    args = frappe._dict(kwargs)

    caller_number = args.get("Caller-ID-Number") or args.get("From") or ""
    called_number = args.get("To") or args.get("Request") or ""
    call_id       = args.get("Call-ID") or args.get("call_id") or ""
    direction     = (args.get("Direction") or "inbound").lower()

    frappe.logger().info(f"FonoUC incoming call: {caller_number} → {called_number} [{call_id}]")

    # Publish realtime event to CRM frontend
    frappe.publish_realtime("fonouc_incoming_call", {
        "call_id":       call_id,
        "caller_number": caller_number,
        "called_number": called_number,
        "direction":     direction,
    })

    # Create call log
    if call_id and not frappe.db.exists("CRM Call Log", call_id):
        create_call_log(
            call_id=call_id,
            from_number=caller_number,
            to_number=called_number,
            agent=None,
            status="Ringing",
            call_type="Incoming",
        )

    # Return empty response to PBX (no callflow redirect)
    return {"status": "ok"}


@frappe.whitelist()
def update_call_status(call_id, status, duration=0, recording_url=None):
    """Update an existing CRM Call Log — called after call ends."""
    if not frappe.db.exists("CRM Call Log", call_id):
        return

    status_map = {
        "completed":   "Completed",
        "answered":    "Completed",
        "no-answer":   "No Answer",
        "failed":      "Failed",
        "busy":        "Busy",
        "cancelled":   "Canceled",
        "in-progress": "In Progress",
    }
    crm_status = status_map.get(status.lower(), "Completed")

    frappe.db.set_value("CRM Call Log", call_id, {
        "status":        crm_status,
        "duration":      int(duration or 0),
        "recording_url": recording_url or "",
    })
    frappe.db.commit()


def create_call_log(call_id, from_number, to_number, agent,
                    status="Initiated", call_type="Outgoing"):
    """Create a CRM Call Log linked to Lead/Deal/Contact."""
    try:
        call_log = frappe.new_doc("CRM Call Log")
        call_log.id               = call_id
        call_log.type             = call_type
        call_log.status           = status
        call_log.telephony_medium = "FonoUC"
        setattr(call_log, "from", from_number)
        call_log.to               = to_number

        if call_type == "Incoming":
            call_log.receiver = agent or ""
        else:
            call_log.caller = agent or ""

        # Link to Lead/Deal/Contact
        contact_number = from_number if call_type == "Incoming" else to_number
        _link(contact_number, call_log)

        call_log.insert(ignore_permissions=True)
        frappe.db.commit()
        return call_log
    except Exception as e:
        frappe.logger().error(f"FonoUC: Failed to create CRM Call Log: {e}")
        return None


def _link(contact_number, call_log):
    """Link call log to CRM Lead/Deal/Contact by phone number."""
    try:
        contact = get_contact_by_phone_number(contact_number)
        if contact.get("name"):
            doctype = "Contact"
            docname = contact.get("name")
            if contact.get("lead"):
                doctype = "CRM Lead"
                docname = contact.get("lead")
            elif contact.get("deal"):
                doctype = "CRM Deal"
                docname = contact.get("deal")
            call_log.link_with_reference_doc(doctype, docname)
    except Exception as e:
        frappe.logger().warning(f"FonoUC: Could not link call log: {e}")


@frappe.whitelist()
def get_sip_settings():
    """Return SIP/WebRTC config for the current user's dialer."""
    if not is_integration_enabled():
        return {}

    settings = frappe.get_single("CRM FonoUC Settings")
    user = frappe.session.user

    agent = frappe.db.get_value(
        "CRM Telephony Agent",
        user,
        ["fonouc_extension", "fonouc_email"],
        as_dict=True,
    )
    if not agent or not agent.fonouc_extension:
        return {}

    # Get HA1 from PBX login
    from fonouc_integration.fonouc_integration.api.pbx_client import FonoUCClient
    client = FonoUCClient()
    ha1 = frappe.cache().get_value(f"pbx_ha1_{user}")
    if not ha1:
        try:
            import requests
            resp = requests.post(
                f"{settings.pbx_url}/api/v2/login",
                json={
                    "username": settings.pbx_username,
                    "password": settings.get_password("pbx_password"),
                    "domain":   settings.pbx_domain,
                },
                timeout=10,
            )
            data = resp.json()
            ha1 = data.get("user", {}).get("pvt_md5_auth", "")
            if ha1:
                frappe.cache().set_value(f"pbx_ha1_{user}", ha1, expires_in_sec=3300)
        except Exception as e:
            frappe.logger().error(f"FonoUC: Could not get HA1: {e}")

    return {
        "wss_server":    settings.wss_server or "wss://dialog.cybergate.lk:5065",
        "sip_realm":     settings.sip_realm or "",
        "extension":     agent.fonouc_extension,
        "ha1":           ha1 or "",
        "display_name":  user,
    }
