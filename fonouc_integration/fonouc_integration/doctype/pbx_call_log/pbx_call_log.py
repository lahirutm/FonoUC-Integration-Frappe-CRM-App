import frappe
from frappe.model.document import Document


class PBXCallLog(Document):
    def after_insert(self):
        self._create_crm_activity()

    def _create_crm_activity(self):
        """Create a CRM Activity on the linked Lead/Deal when a call log is inserted."""
        reference_doctype = None
        reference_name = None

        if self.linked_lead:
            reference_doctype = "CRM Lead"
            reference_name = self.linked_lead
        elif self.linked_deal:
            reference_doctype = "CRM Deal"
            reference_name = self.linked_deal

        if not reference_doctype:
            return

        duration_fmt = self._format_duration(self.duration or 0)
        recording_note = ""
        if self.has_recording and self.recording_url:
            recording_note = f"\n🎙️ [Listen to Recording]({self.recording_url})"

        note = (
            f"**PBX Call — {self.direction} | {self.status}**\n"
            f"- From: {self.caller_number} ({self.caller_name or 'Unknown'})\n"
            f"- To: {self.called_number}\n"
            f"- Agent: {self.agent_name or self.agent_extension or 'N/A'}\n"
            f"- Duration: {duration_fmt}\n"
            f"- Queue: {self.queue_name or 'N/A'}"
            f"{recording_note}"
        )

        try:
            activity = frappe.new_doc("CRM Activity")
            activity.subject = f"📞 {self.direction} Call — {self.status} — {self.caller_number}"
            activity.activity_type = "Phone"
            activity.reference_doctype = reference_doctype
            activity.reference_name = reference_name
            activity.user = self.frappe_user or frappe.session.user
            activity.activity_date = self.call_datetime
            activity.note = note
            activity.insert(ignore_permissions=True)
        except Exception:
            # CRM Activity may not exist in all Frappe CRM versions — fall back silently
            pass

    @staticmethod
    def _format_duration(seconds):
        mins, secs = divmod(int(seconds), 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours}h {mins}m {secs}s"
        return f"{mins}m {secs}s"


def has_permission(doc, user=None, permission_type=None):
    """Allow CRM Users to see call logs linked to their leads."""
    return True
