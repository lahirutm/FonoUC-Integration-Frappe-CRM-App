# FonoUC Integration — Frappe CRM App

Full integration between **FonoUC Soft PBX** (GOPortalbackend API) and **Frappe CRM**.

## Features

| Feature | Description |
|---|---|
| **CDR Sync** | Polls PBX every 5 min, creates `PBX Call Log` records, auto-links to CRM Leads |
| **Click-to-Call** | Call button on Lead/Deal forms — resolves agent extension and originates call |
| **Call Recording Links** | Recording URLs attached to call logs with in-form playback button |
| **Campaign Lead Sync** | Pushes CRM Leads to PBX outbound campaigns with field mapping |
| **Live Agent Dashboard** | Real-time queue & agent status page, auto-refreshes every 15 seconds |

---

## Installation

### 1. Get the app onto your server

```bash
cd /home/frappe/frappe-bench
bench get-app fonouc_integration /path/to/fonouc_integration
# OR clone from your git repo:
# bench get-app fonouc_integration https://github.com/yourorg/fonouc_integration
```

### 2. Install on your site

```bash
bench --site erp.cybergate.lk install-app fonouc_integration
bench --site erp.cybergate.lk migrate
bench build --app fonouc_integration
bench restart
```

---

## Configuration

### Step 1 — PBX Settings

Go to **FonoUC PBX → PBX Settings** and fill in:

| Field | Value |
|---|---|
| PBX Base URL | `https://your-company.fonouc.com` |
| Account ID | Your account ID from the PBX portal |
| Auth Method | `API Key` (recommended) or `Username & Password` |
| API Key | Generated in PBX portal under **API Keys** |

Click **PBX Actions → Test Connection** to verify.

### Step 2 — Generate a PBX API Key

In the PBX portal:
1. Go to **Settings → API Keys**
2. Click **Create API Key**
3. Copy the key and paste into PBX Settings

### Step 3 — Sync PBX Users

Click **PBX Actions → Sync PBX Users**. This creates `PBX Agent Mapping` records
linking each PBX extension to a Frappe CRM user by matching email addresses.

Review the mappings at **FonoUC PBX → PBX Agent Mapping** and correct any
that did not auto-match.

### Step 4 — CDR Sync (automatic)

CDRs sync automatically every 5 minutes via the Frappe scheduler.
Trigger a manual sync via **PBX Actions → Sync CDRs Now**.

### Step 5 — Campaign Sync

1. Go to **FonoUC PBX → PBX Campaign Link → New**
2. Enter a name, paste the **PBX Campaign ID** (from the PBX portal)
3. Set lead filters (optional) and field mapping
4. Click **Campaign → Sync Leads to PBX Now**

### Step 6 — Live Agent Dashboard

Navigate to **FonoUC PBX → PBX Live Agent Status** (or open
`https://erp.cybergate.lk/pbx-agent-status`).

---

## Architecture

```
Frappe CRM (erp.cybergate.lk)
    │
    ├── Scheduler (every 5 min)
    │       └── cdr_sync.py  ──────── GET /api/v2/config/reports/cdrs
    │                                 GET /api/v2/config/reports/recordings
    │
    ├── CRM Lead / Deal Form
    │       └── click_to_call.js ──── endpoints.py → initiate_call()
    │                                 endpoints.py → get_call_logs()
    │
    ├── PBX Campaign Link
    │       └── campaign_sync.py ──── POST /api/v2/config/campaigns/{id}/leads/api
    │
    └── Live Agent Status Page
            └── pbx_agent_status.js ─ GET /callcenter/queues/status
                                      GET /callcenter/queues/calls
```

---

## DocTypes Created

| DocType | Purpose |
|---|---|
| `PBX Settings` | Singleton — stores PBX URL, credentials, sync status |
| `PBX Call Log` | One record per CDR; links to Lead/Deal/Contact |
| `PBX Agent Mapping` | Maps PBX extension → Frappe CRM user |
| `PBX Campaign Link` | Links a Frappe CRM lead filter to a PBX campaign ID |

---

## Troubleshooting

**CDR sync not running?**
```bash
bench --site erp.cybergate.lk scheduler status
bench --site erp.cybergate.lk enable-scheduler
```

**Click-to-Call shows "No extension mapped"?**
Check **PBX Agent Mapping** — ensure the logged-in user has a mapping with a
valid PBX extension and `Active = Yes`.

**Token expired errors?**
Go to **PBX Settings** and click **Test Connection** — this will re-authenticate.
Or switch to **API Key** auth which never expires.

**Check scheduler logs:**
```bash
bench --site erp.cybergate.lk show-pending-jobs
tail -f logs/scheduler.log
```

---

## Permissions

| Role | Access |
|---|---|
| System Manager | Full access to all PBX doctypes |
| CRM User | Read-only access to PBX Call Log |

---

## License
MIT — © Cybergate 2024
