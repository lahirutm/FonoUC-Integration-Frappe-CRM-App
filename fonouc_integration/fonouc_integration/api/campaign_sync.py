"""
Campaign Sync
Pushes CRM Leads matching the configured filters to their linked PBX campaign.
Uses the PBX "leads/api" endpoint so the PBX fetches directly from Frappe CRM's
REST API — this is the most efficient approach and avoids rate-limit issues.
"""
import frappe
from frappe.utils import now_datetime

from fonouc_integration.fonouc_integration.api.pbx_client import FonoUCClient


def sync_all_campaigns():
    """Called by scheduler (daily or on-demand) to sync all active campaigns."""
    links = frappe.get_all("PBX Campaign Link", filters={"is_active": 1}, pluck="name")
    for name in links:
        try:
            sync_campaign(name)
        except Exception as e:
            frappe.logger().error(f"Campaign sync failed for {name}: {e}")


def sync_campaign(campaign_link_name: str) -> dict:
    """
    Sync one PBX Campaign Link.
    Returns a dict with { pushed: int } indicating leads sent.
    """
    link = frappe.get_doc("PBX Campaign Link", campaign_link_name)
    client = FonoUCClient()
    settings = frappe.get_single("PBX Settings")

    # Build the Frappe CRM REST API URL that the PBX will call to fetch leads
    filters = []
    if link.lead_filter_status:
        filters.append(f'["status","=","{link.lead_filter_status}"]')
    if link.lead_filter_source:
        filters.append(f'["source","=","{link.lead_filter_source}"]')

    filter_str = f"[{','.join(filters)}]" if filters else "[]"
    limit = link.lead_limit or 200

    # Frappe CRM REST API endpoint for CRM Lead list
    frappe_api_url = (
        f"https://erp.cybergate.lk/api/resource/CRM Lead"
        f"?filters={filter_str}"
        f"&fields=[\"name\",\"{link.number_field}\",\"{link.first_name_field}\","
        f"\"{link.last_name_field}\",\"{link.notes_field}\"]"
        f"&limit={limit}"
    )

    # Field mapping: PBX field → CRM Lead field name inside the response
    mapping = {
        "leads_array": "data",
        "number": link.number_field or "mobile_no",
        "first_name": link.first_name_field or "first_name",
        "last_name": link.last_name_field or "last_name",
        "ticket_id": "name",
        "notes": link.notes_field or "notes",
    }

    try:
        client.sync_leads_from_url(link.pbx_campaign_id, frappe_api_url, mapping)
        pushed = limit  # PBX doesn't return count directly
    except Exception:
        # Fallback: push leads one by one
        pushed = _push_leads_individually(client, link)

    # Update last sync timestamp
    frappe.db.set_value(
        "PBX Campaign Link", campaign_link_name,
        "last_sync", now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
    )
    frappe.db.commit()
    frappe.logger().info(f"Campaign sync done for '{link.campaign_name}': {pushed} leads pushed.")
    return {"pushed": pushed}


def _push_leads_individually(client: FonoUCClient, link) -> int:
    """Fallback: fetch leads from DB and push one by one."""
    filters = {}
    if link.lead_filter_status:
        filters["status"] = link.lead_filter_status
    if link.lead_filter_source:
        filters["source"] = link.lead_filter_source

    fields = ["name", link.number_field, link.first_name_field, link.last_name_field]
    if link.notes_field:
        fields.append(link.notes_field)

    leads = frappe.get_all("CRM Lead", filters=filters, fields=fields, limit=link.lead_limit or 200)
    pushed = 0
    for lead in leads:
        phone = lead.get(link.number_field)
        if not phone:
            continue
        try:
            client.add_lead_to_campaign(link.pbx_campaign_id, {
                "number": phone,
                "first_name": lead.get(link.first_name_field, ""),
                "last_name": lead.get(link.last_name_field, ""),
                "ticket_id": lead.get("name", ""),
                "note": lead.get(link.notes_field, "") if link.notes_field else "",
                "priority": 50,
            })
            pushed += 1
        except Exception as e:
            frappe.logger().warning(f"Failed to push lead {lead.get('name')}: {e}")

    return pushed
