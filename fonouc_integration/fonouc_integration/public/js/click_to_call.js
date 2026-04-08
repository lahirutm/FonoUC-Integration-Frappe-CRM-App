/**
 * FonoUC Click-to-Call using Embedded UCP iframe + postMessage
 * Injected into CRM Lead and CRM Deal via hooks.py → doctype_js
 */

// Frappe CRM is a Vue SPA — use the global document events approach
document.addEventListener("DOMContentLoaded", () => {
    pbx_observe_lead_pages();
});

function pbx_observe_lead_pages() {
    // Watch for route changes in the Vue SPA
    const observer = new MutationObserver(() => {
        const path = window.location.pathname;
        if (path.includes("/crm/leads/") || path.includes("/crm/deals/")) {
            setTimeout(pbx_inject_ui, 800);
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
}

function pbx_inject_ui() {
    // Don't inject twice
    if (document.getElementById("pbx-call-widget")) return;

    // Get phone number from page
    const phone = pbx_find_phone_on_page();
    if (!phone) return;

    // ── Floating Call Button ──────────────────────────────────────────
    const btn = document.createElement("div");
    btn.id = "pbx-call-widget";
    btn.innerHTML = `
        <button id="pbx-call-btn" title="Call ${phone} via FonoUC PBX"
            style="position:fixed;bottom:80px;right:24px;z-index:9999;
                   background:#28a745;color:#fff;border:none;border-radius:50%;
                   width:56px;height:56px;font-size:22px;cursor:pointer;
                   box-shadow:0 4px 12px rgba(0,0,0,0.3);
                   display:flex;align-items:center;justify-content:center;">
            📞
        </button>`;
    document.body.appendChild(btn);

    document.getElementById("pbx-call-btn").onclick = () => pbx_start_call(phone);
}

function pbx_find_phone_on_page() {
    // Try to find phone number from visible page elements
    const selectors = [
        '[data-fieldname="mobile_no"] .field-value',
        '[data-fieldname="phone"] .field-value',
        '.mobile_no',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.textContent.trim()) return el.textContent.trim();
    }
    return null;
}

function pbx_start_call(destination) {
    // Ask backend for magic link
    fetch("/api/method/fonouc_integration.fonouc_integration.api.endpoints.initiate_call", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-Frappe-CSRF-Token": frappe?.csrf_token || "",
        },
        body: JSON.stringify({ destination }),
    })
    .then(r => r.json())
    .then(data => {
        if (data.exc) {
            alert("PBX Error: " + data.exc);
            return;
        }
        const { magic_link } = data.message;
        pbx_open_ucp_and_call(magic_link, destination);
    })
    .catch(err => alert("PBX connection error: " + err));
}

function pbx_open_ucp_and_call(magic_link, destination) {
    // ── Floating UCP iframe panel ─────────────────────────────────────
    let panel = document.getElementById("pbx-ucp-panel");
    if (!panel) {
        panel = document.createElement("div");
        panel.id = "pbx-ucp-panel";
        panel.innerHTML = `
            <div style="position:fixed;bottom:150px;right:24px;z-index:10000;
                        width:340px;height:520px;border-radius:12px;
                        box-shadow:0 8px 32px rgba(0,0,0,0.35);
                        background:#fff;overflow:hidden;display:flex;flex-direction:column;">
                <div style="background:#246199;color:#fff;padding:10px 14px;
                            display:flex;justify-content:space-between;align-items:center;
                            font-size:14px;font-weight:600;">
                    📞 FonoUC — Calling ${destination}
                    <span id="pbx-close-ucp" style="cursor:pointer;font-size:18px;line-height:1;">×</span>
                </div>
                <iframe id="ucp-iframe" title="ucp"
                    src="${magic_link}"
                    allow="notifications; microphone"
                    style="flex:1;border:none;width:100%;"></iframe>
            </div>`;
        document.body.appendChild(panel);

        document.getElementById("pbx-close-ucp").onclick = () => {
            panel.remove();
        };
    }

    // Wait for iframe to load then send MAKE_CALL via postMessage
    const iframe = document.getElementById("ucp-iframe");
    iframe.onload = () => {
        setTimeout(() => {
            iframe.contentWindow.postMessage({
                type: "MAKE_CALL",
                payload: { destination },
            }, "*");
        }, 1500);
    };

    // Listen for call events from UCP
    window.addEventListener("message", pbx_handle_ucp_event);
}

function pbx_handle_ucp_event(event) {
    const { type, payload } = event.data || {};
    if (!type || !type.startsWith("UCP_")) return;

    if (type === "UCP_INCOMING_CALL") {
        pbx_show_toast(`📞 Incoming call from ${payload.caller_id_number} (${payload.caller_id_name})`, "blue");
        pbx_auto_open_lead(payload.caller_id_number);
    } else if (type === "UCP_ANSWERED_CALL") {
        pbx_show_toast(`✅ Call answered`, "green");
    } else if (type === "UCP_HANGUP_CALL") {
        pbx_show_toast(`📴 Call ended`, "gray");
    } else if (type === "UCP_OUTGOING_CALL") {
        pbx_show_toast(`📞 Calling ${payload.callee_id_number}…`, "green");
    }
}

function pbx_auto_open_lead(caller_number) {
    // Try to find and open a matching lead when an incoming call arrives
    if (!caller_number) return;
    fetch(`/api/method/fonouc_integration.fonouc_integration.api.endpoints.find_lead_by_phone?phone=${encodeURIComponent(caller_number)}`)
        .then(r => r.json())
        .then(data => {
            if (data.message && data.message.lead) {
                // Navigate to the lead
                window.location.href = `/crm/leads/${data.message.lead}`;
            }
        });
}

function pbx_show_toast(message, color) {
    const toast = document.createElement("div");
    toast.style.cssText = `
        position:fixed;top:20px;right:24px;z-index:99999;
        background:${color === "green" ? "#28a745" : color === "blue" ? "#246199" : "#6c757d"};
        color:#fff;padding:12px 18px;border-radius:8px;font-size:13px;
        box-shadow:0 4px 12px rgba(0,0,0,0.2);max-width:320px;`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}
