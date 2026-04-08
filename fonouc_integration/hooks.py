app_name = "fonouc_integration"
app_title = "FonoUC Integration"
app_publisher = "Cybergate"
app_description = "FonoUC Soft PBX Integration for Frappe CRM"
app_email = "admin@cybergate.lk"
app_license = "MIT"

scheduler_events = {
    "cron": {
        "*/5 * * * *": [
            "fonouc_integration.fonouc_integration.api.cdr_sync.sync_cdrs"
        ],
    },
    "hourly": [
        "fonouc_integration.fonouc_integration.api.pbx_client.refresh_token"
    ],
}

app_include_js = [
    "/assets/fonouc_integration/js/click_to_call.js",
    "/assets/fonouc_integration/js/fonouc_dialer.js"
]

web_include_js = [
    "/assets/fonouc_integration/js/click_to_call.js",
    "/assets/fonouc_integration/js/fonouc_dialer.js"
]

# Override CRM's is_call_integration_enabled to add FonoUC
override_whitelisted_methods = {
    "crm.integrations.api.is_call_integration_enabled": "fonouc_integration.fonouc_integration.integrations.fonouc.overrides.is_call_integration_enabled"
}

has_permission = {
    "PBX Call Log": "fonouc_integration.fonouc_integration.doctype.pbx_call_log.pbx_call_log.has_permission",
}

boot_session = "fonouc_integration.fonouc_integration.api.endpoints.boot_session"

# Customize CRM Telephony Agent to add FonoUC fields
after_migrate = [
    "fonouc_integration.fonouc_integration.integrations.fonouc.setup.add_fonouc_fields_to_telephony_agent"
]
