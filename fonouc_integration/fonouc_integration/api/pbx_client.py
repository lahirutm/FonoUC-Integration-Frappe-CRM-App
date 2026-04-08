import frappe
import requests
from datetime import datetime, timedelta

CDR_PATHS = ("/api/v2/reports/", "/api/v2/cdrs/")


class FonoUCClient:

    def __init__(self):
        self.settings   = frappe.get_single("PBX Settings")
        self.base_url   = self.settings.pbx_url.rstrip("/")
        self.account_id = self.settings.account_id
        self.api_key    = self.settings.get_password("api_key") or ""

    def _get_headers(self, path=""):
        headers = {
            "X-Account-ID": self.account_id,
            "Content-Type": "application/json",
        }
        if any(path.startswith(p) for p in CDR_PATHS):
            headers["Authorization"] = f"Bearer {self._get_token()}"
        else:
            headers["X-API-Key"] = self.api_key
            token = frappe.cache().get_value("pbx_auth_token")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get_token(self):
        cached = frappe.cache().get_value("pbx_auth_token")
        if cached:
            return cached
        return self._login()

    def _login(self):
        resp = requests.post(
            f"{self.base_url}/api/v2/login",
            json={
                "username": self.settings.pbx_username,
                "password": self.settings.get_password("pbx_password"),
                "domain":   self.settings.pbx_domain,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data  = resp.json()
        token = data["access_token"]
        frappe.cache().set_value("pbx_auth_token", token, expires_in_sec=3300)
        frappe.db.set_value("PBX Settings", None, {
            "auth_token":   token,
            "token_expiry": (datetime.now() + timedelta(minutes=55)).strftime("%Y-%m-%d %H:%M:%S"),
        })
        frappe.db.commit()
        return token

    def get_ucp_login_url(self):
        """Return UCP login URL. Agent logs in once; UCP maintains its own session."""
        # Extract the PBX domain from base_url e.g. https://dialog.cybergate.lk:9443
        # UCP is served on port 443 (no port needed)
        import re
        domain = re.sub(r':\d+$', '', self.base_url.replace('https://', '').replace('http://', ''))
        return f"https://{domain}/ucp/login"

    def get(self, path, params=None):
        resp = requests.get(
            f"{self.base_url}{path}",
            headers=self._get_headers(path),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def post(self, path, data=None):
        resp = requests.post(
            f"{self.base_url}{path}",
            headers=self._get_headers(path),
            json=data,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def put(self, path, data=None):
        resp = requests.put(
            f"{self.base_url}{path}",
            headers=self._get_headers(path),
            json=data,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_account_info(self):
        return self.get("/ucp/v2/account/basic")

    def get_users(self):
        return self.get("/api/v2/config/users")

    def get_cdrs(self, from_ts, to_ts, page_size=500):
        return self.get("/api/v2/reports/cdrs", {
            "startDate": from_ts,
            "endDate":   to_ts,
            "pageSize":  page_size,
        })

    def get_queue_cdrs(self, from_ts, to_ts):
        return self.get("/api/v2/reports/queues_cdrs", {
            "startDate": from_ts,
            "endDate":   to_ts,
        })

    def get_cdr_by_id(self, cdr_id):
        return self.get(f"/api/v2/cdrs/cdr/{cdr_id}")

    def get_recordings(self, from_ts, to_ts, page_size=500):
        return self.get("/api/v2/reports/recordings", {
            "startDate": from_ts,
            "endDate":   to_ts,
            "pageSize":  page_size,
        })

    def get_recording_url(self, recording_id):
        return f"{self.base_url}/api/v2/reports/recordings/{recording_id}"

    def get_queues_status(self):
        return self.get("/callcenter/queues/status")

    def get_queues_calls(self):
        return self.get("/callcenter/queues/calls")

    def get_queues_list(self):
        return self.get("/api/v2/config/queues")

    def get_campaigns(self):
        return self.get("/api/v2/config/campaigns")

    def get_campaign(self, campaign_id):
        return self.get(f"/api/v2/config/campaigns/{campaign_id}")

    def add_lead_to_campaign(self, campaign_id, lead):
        return self.post(f"/api/v2/config/campaigns/{campaign_id}/lead", lead)


@frappe.whitelist()
def refresh_token():
    try:
        frappe.cache().delete_value("pbx_auth_token")
        client = FonoUCClient()
        client._login()
        frappe.logger().info("PBX auth token refreshed.")
    except Exception as e:
        frappe.logger().error(f"PBX token refresh failed: {e}")
