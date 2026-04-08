frappe.pages["pbx-agent-status"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "📞 PBX Live Agent Status",
        single_column: true,
    });

    page.add_action_item(__("Refresh Now"), () => load_data());

    // Auto-refresh toggle
    let auto_refresh = true;
    let timer = null;

    const btn = page.add_action_item(__("⏸ Pause Auto-Refresh"), () => {
        auto_refresh = !auto_refresh;
        if (auto_refresh) {
            btn.innerHTML = "⏸ Pause Auto-Refresh";
            schedule_refresh();
        } else {
            btn.innerHTML = "▶ Resume Auto-Refresh";
            clearTimeout(timer);
        }
    });

    // ── Layout ──────────────────────────────────────────────────────
    const $body = $(wrapper).find(".page-content");
    $body.html(`
        <div id="pbx-dashboard" style="padding:16px;">
            <div id="pbx-summary" class="row" style="margin-bottom:20px;"></div>
            <div id="pbx-queues"></div>
            <div id="pbx-live-calls" style="margin-top:24px;"></div>
        </div>
    `);

    // ── Data loading ─────────────────────────────────────────────────
    function load_data() {
        frappe.call({
            method: "fonouc_integration.fonouc_integration.api.endpoints.get_live_status",
            callback(r) {
                if (r.exc || !r.message) {
                    $("#pbx-summary").html(
                        `<div class="alert alert-danger">Failed to fetch PBX data. Check PBX Settings.</div>`
                    );
                    return;
                }
                render(r.message.queues || [], r.message.live_calls || []);
            },
        });
    }

    function schedule_refresh() {
        timer = setTimeout(() => {
            if (auto_refresh) { load_data(); schedule_refresh(); }
        }, 15000);
    }

    // ── Rendering ────────────────────────────────────────────────────
    function render(queues, live_calls) {
        render_summary(queues, live_calls);
        render_queues(queues);
        render_live_calls(live_calls);
        update_timestamp();
    }

    function render_summary(queues, live_calls) {
        const total_agents = queues.reduce((a, q) => a + (q.total_agents || 0), 0);
        const logged_in    = queues.reduce((a, q) => a + (q.logged_in_agents || 0), 0);
        const total_calls  = live_calls.length;
        const waiting      = live_calls.filter(c => !c.answered).length;

        const cards = [
            { label: "Queues",          value: queues.length,  color: "#5e64ff" },
            { label: "Total Agents",    value: total_agents,   color: "#2d8a4e" },
            { label: "Agents Online",   value: logged_in,      color: "#28a745" },
            { label: "Active Calls",    value: total_calls,    color: "#fd7e14" },
            { label: "Waiting Callers", value: waiting,        color: "#dc3545" },
        ];

        const html = cards.map(c => `
            <div class="col-md-2 col-sm-4" style="margin-bottom:12px;">
                <div style="background:${c.color};color:#fff;border-radius:8px;
                            padding:16px 12px;text-align:center;">
                    <div style="font-size:28px;font-weight:700;">${c.value}</div>
                    <div style="font-size:11px;opacity:.85;margin-top:4px;">${c.label}</div>
                </div>
            </div>`).join("");

        $("#pbx-summary").html(html);
    }

    function render_queues(queues) {
        if (!queues.length) {
            $("#pbx-queues").html(`<p class="text-muted">No queue data available.</p>`);
            return;
        }

        const tabs_nav = queues.map((q, i) =>
            `<li class="nav-item">
                <a class="nav-link ${i === 0 ? "active" : ""}"
                   data-toggle="tab" href="#pbx-q-${i}">${q.name || q.id}</a>
             </li>`
        ).join("");

        const tabs_content = queues.map((q, i) => {
            const agents = (q.agents || []).map(a => {
                const status_color = a.logged_in ? (a.status === "idle" ? "#28a745" : "#fd7e14") : "#6c757d";
                const reg_pill = a.registered
                    ? `<span class="badge badge-success">Registered</span>`
                    : `<span class="badge badge-secondary">Unregistered</span>`;
                const call_info = a.conference
                    ? `🔴 On call with ${a.conference.caller?.number || "?"} (${fmt_secs(a.conference.duration)})`
                    : "⚪ Idle";

                return `<tr>
                    <td><span style="color:${status_color};">●</span> ${a.name || a.id}</td>
                    <td>${a.extension || "—"}</td>
                    <td>${reg_pill}</td>
                    <td>${a.logged_in ? "✅ Logged In" : "❌ Logged Out"}</td>
                    <td>${call_info}</td>
                </tr>`;
            }).join("") || `<tr><td colspan="5" class="text-muted text-center">No agents in this queue.</td></tr>`;

            return `
            <div class="tab-pane fade ${i === 0 ? "show active" : ""}" id="pbx-q-${i}">
                <div class="row" style="margin:12px 0 8px;">
                    <div class="col-md-3">
                        <small class="text-muted">Strategy:</small>
                        <b>${q.strategy || "—"}</b>
                    </div>
                    <div class="col-md-3">
                        <small class="text-muted">Logged In:</small>
                        <b>${q.logged_in_agents || 0} / ${q.total_agents || 0}</b>
                    </div>
                    <div class="col-md-3">
                        <small class="text-muted">Max Wait:</small>
                        <b>${q.max_time_caller_in_queue ? fmt_secs(q.max_time_caller_in_queue) : "—"}</b>
                    </div>
                </div>
                <table class="table table-sm table-bordered" style="font-size:12px;">
                    <thead style="background:var(--subtle-fg);">
                        <tr>
                            <th>Agent</th><th>Extension</th><th>SIP</th>
                            <th>Queue Status</th><th>Current Call</th>
                        </tr>
                    </thead>
                    <tbody>${agents}</tbody>
                </table>
            </div>`;
        }).join("");

        $("#pbx-queues").html(`
            <h6 style="color:var(--text-muted);margin-bottom:8px;">Queue Details</h6>
            <ul class="nav nav-tabs" style="margin-bottom:0;">${tabs_nav}</ul>
            <div class="tab-content" style="border:1px solid var(--border-color);
                 border-top:none;padding:12px;border-radius:0 0 6px 6px;">
                ${tabs_content}
            </div>`
        );
    }

    function render_live_calls(calls) {
        if (!calls.length) {
            $("#pbx-live-calls").html(
                `<p class="text-muted" style="font-size:12px;">No active calls at this moment.</p>`
            );
            return;
        }

        const rows = calls.map(c => {
            const agent = (c.agent || [{}])[0];
            const caller = c.caller || {};
            const answered_badge = c.answered
                ? `<span class="badge badge-success">Answered</span>`
                : `<span class="badge badge-warning">Waiting</span>`;

            return `<tr>
                <td>${answered_badge}</td>
                <td>${caller.number || "?"} <small class="text-muted">${caller.name || ""}</small></td>
                <td>${agent.name || agent.id || "—"} (${agent.ext || ""})</td>
                <td>${fmt_secs(c.duration || 0)}</td>
                <td>${c.wait_time ? fmt_secs(c.wait_time) : "—"}</td>
                <td>${c.queue_id || "—"}</td>
            </tr>`;
        }).join("");

        $("#pbx-live-calls").html(`
            <h6 style="color:var(--text-muted);margin-bottom:8px;">🔴 Live Calls (${calls.length})</h6>
            <table class="table table-sm table-bordered" style="font-size:12px;">
                <thead style="background:var(--subtle-fg);">
                    <tr>
                        <th>Status</th><th>Caller</th><th>Agent</th>
                        <th>Duration</th><th>Wait Time</th><th>Queue</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>`
        );
    }

    function update_timestamp() {
        const ts = frappe.datetime.now_datetime();
        page.set_indicator(`Last updated: ${ts}`, "blue");
    }

    function fmt_secs(s) {
        s = parseInt(s) || 0;
        const m = Math.floor(s / 60), sec = s % 60;
        return m ? `${m}m ${sec}s` : `${sec}s`;
    }

    // ── Kick off ─────────────────────────────────────────────────────
    load_data();
    schedule_refresh();
};
