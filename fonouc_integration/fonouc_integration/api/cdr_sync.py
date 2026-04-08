import frappe
from frappe.utils import now_datetime, get_datetime
from datetime import datetime, timedelta

from fonouc_integration.fonouc_integration.api.pbx_client import FonoUCClient
from fonouc_integration.fonouc_integration.doctype.pbx_agent_mapping.pbx_agent_mapping import (
    get_frappe_user_for_extension,
)


@frappe.whitelist()
def sync_cdrs():
    settings = frappe.get_single("PBX Settings")
    if not settings.pbx_url:
        return
    try:
        _run_sync(settings)
    except Exception as e:
        frappe.logger().error(f"CDR sync error: {e}", exc_info=True)
        frappe.db.set_value("PBX Settings", None, {
            "last_sync_status":  "Failed",
            "last_sync_message": str(e)[:500],
        })
        frappe.db.commit()


def _run_sync(settings):
    client  = FonoUCClient()
    now     = datetime.utcnow()

    if settings.last_cdr_sync:
        from_dt = get_datetime(settings.last_cdr_sync) - timedelta(minutes=2)
    else:
        from_dt = now - timedelta(hours=24)

    from_ts = int(from_dt.timestamp())
    to_ts   = int(now.timestamp())

    frappe.logger().info(f"CDR sync: {from_dt} → {now}")

    raw  = client.get_cdrs(from_ts, to_ts)
    cdrs = raw.get("data", []) if isinstance(raw, dict) else []

    # Recordings map: call_id → recording doc
    try:
        rec_raw = client.get_recordings(from_ts, to_ts)
        rec_map = _build_recording_map(rec_raw)
    except Exception:
        rec_map = {}

    new_count = 0
    for cdr in cdrs:
        # Real field names from actual API response:
        # id, call_id, datetime, timestamp, caller_id_name, caller_id_number,
        # callee_id_name, callee_id_number, to, from, billing_seconds,
        # duration_seconds, ringing_seconds, hangup_cause,
        # media_recording_id, recording_filename, a_leg, interaction_id
        cdr_id = cdr.get("id")
        if not cdr_id:
            continue
        if frappe.db.exists("PBX Call Log", cdr_id):
            continue

        caller_no   = cdr.get("caller_id_number") or ""
        caller_name = cdr.get("caller_id_name") or ""
        callee_no   = cdr.get("callee_id_number") or ""
        # Extract clean extension from "to" field e.g. "0117310906@172.32.32.2"
        to_field    = cdr.get("to") or ""
        called_no   = callee_no or to_field.split("@")[0]
        duration    = int(cdr.get("billing_seconds") or cdr.get("duration_seconds") or 0)
        hangup      = cdr.get("hangup_cause") or ""
        call_dt     = _parse_datetime(cdr.get("datetime") or cdr.get("timestamp"))
        direction   = _get_direction(cdr)
        status      = _get_status(hangup, duration)

        # Agent extension from callee or to field
        agent_ext   = callee_no or to_field.split("@")[0]
        frappe_user = get_frappe_user_for_extension(agent_ext) or ""

        # Recording
        rec_id  = cdr.get("media_recording_id") or ""
        if not rec_id:
            rec_id = rec_map.get(cdr.get("call_id", ""), {}).get("_id", "")
        rec_url = client.get_recording_url(rec_id) if rec_id else ""

        # CRM entity match
        linked_lead, linked_contact = _find_crm_entities(caller_no or called_no)

        # ── PBX Call Log ─────────────────────────────────────────────
        try:
            log = frappe.new_doc("PBX Call Log")
            log.call_id         = cdr_id
            log.call_datetime   = call_dt
            log.direction       = direction
            log.status          = status
            log.duration        = duration
            log.caller_number   = caller_no
            log.caller_name     = caller_name
            log.called_number   = called_no
            log.agent_extension = agent_ext
            log.frappe_user     = frappe_user
            log.has_recording   = 1 if rec_id else 0
            log.recording_id    = rec_id
            log.recording_url   = rec_url
            log.linked_lead     = linked_lead or ""
            log.linked_contact  = linked_contact or ""
            log.insert(ignore_permissions=True)
            new_count += 1
        except frappe.DuplicateEntryError:
            pass

        # ── CRM Call Log (shows in Calls tab natively) ────────────────
        _create_crm_call_log(
            cdr_id, call_dt, direction, status, duration,
            caller_no, caller_name, called_no, agent_ext,
            frappe_user, rec_url, linked_lead, linked_contact,
        )

    frappe.db.commit()

    msg = f"Synced {new_count} new CDRs ({from_dt.strftime('%Y-%m-%d %H:%M')} – {now.strftime('%H:%M')} UTC)"
    frappe.db.set_value("PBX Settings", None, {
        "last_cdr_sync":     now.strftime("%Y-%m-%d %H:%M:%S"),
        "last_sync_status":  "Success",
        "last_sync_message": msg,
    })
    frappe.db.commit()
    frappe.logger().info(f"CDR sync: {msg}")


def _create_crm_call_log(cdr_id, call_dt, direction, status, duration,
                          caller_no, caller_name, called_no, agent_ext,
                          frappe_user, rec_url, linked_lead, linked_contact):
    if frappe.db.exists("CRM Call Log", {"id": cdr_id}):
        return
    try:
        doc = frappe.new_doc("CRM Call Log")
        doc.id         = cdr_id
        doc.type       = "Incoming" if direction == "Inbound" else "Outgoing"
        doc.status     = "Completed" if status == "Answered" else "Missed"
        doc.duration   = duration
        doc.start_time = call_dt
        doc.end_time   = call_dt
        doc.caller     = caller_no
        doc.receiver   = called_no
        setattr(doc, "from", caller_no)
        doc.to         = called_no
        doc.note       = f"PBX | Agent: {agent_ext} | CDR: {cdr_id}"
        if rec_url:
            doc.recording_url = rec_url
        if linked_lead:
            doc.reference_doctype = "CRM Lead"
            doc.reference_docname = linked_lead
        elif linked_contact:
            doc.reference_doctype = "Contact"
            doc.reference_docname = linked_contact
        if frappe_user:
            doc.owner = frappe_user
        doc.insert(ignore_permissions=True)
    except Exception as e:
        frappe.logger().warning(f"CRM Call Log insert failed for {cdr_id}: {e}")


# ── Helpers ───────────────────────────────────────────────────────────

def _build_recording_map(raw):
    items = []
    if isinstance(raw, dict):
        items = raw.get("recordings", raw.get("data", []))
    elif isinstance(raw, list):
        items = raw
    result = {}
    for r in items:
        cid = r.get("call_id") or r.get("cdr_id") or r.get("_id")
        if cid:
            result[cid] = r
    return result


def _parse_datetime(val):
    if not val:
        return now_datetime()
    if isinstance(val, (int, float)):
        return datetime.utcfromtimestamp(float(val)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        return datetime.strptime(str(val)[:19], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(val)[:19]


def _get_direction(cdr):
    # From field: "0362254255@20.20.20.89" — external IP = inbound
    # To field: "0117310906@172.32.32.2" — internal IP = inbound to extension
    callee = cdr.get("callee_id_number") or ""
    # Short extension (≤6 digits) as callee = inbound call to agent
    if callee and len(callee) <= 6:
        return "Inbound"
    # Long number as callee = outbound call
    if callee and len(callee) > 6:
        return "Outbound"
    return "Inbound"


def _get_status(hangup_cause, duration):
    if duration > 0:
        return "Answered"
    if "BUSY" in hangup_cause:
        return "Busy"
    if "VOICEMAIL" in hangup_cause:
        return "Voicemail"
    return "Missed"


def _find_crm_entities(number):
    if not number:
        return None, None
    # Strip leading zeros and country code for fuzzy match
    short = number[-9:] if len(number) >= 9 else number
    lead = frappe.db.sql(
        "SELECT name FROM `tabCRM Lead` WHERE mobile_no LIKE %s OR phone LIKE %s LIMIT 1",
        (f"%{short}", f"%{short}"), as_dict=True,
    )
    if lead:
        return lead[0].name, None
    contact = frappe.db.sql(
        "SELECT parent FROM `tabContact Phone` WHERE phone LIKE %s LIMIT 1",
        (f"%{short}",), as_dict=True,
    )
    if contact:
        return None, contact[0].parent
    return None, None
