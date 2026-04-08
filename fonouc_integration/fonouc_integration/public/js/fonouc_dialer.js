/**
 * FonoUC WebRTC Dialer — JsSIP based
 * Registers as SIP client and dials directly from browser
 */
(function () {
  'use strict';

  var UA = null;
  var currentSession = null;
  var dialerVisible = false;
  var registered = false;
  var lastPath = '';
  var settings = null;

  // ── Load JsSIP from CDN ───────────────────────────────────────────
  function loadJsSIP(callback) {
    if (window.JsSIP) { callback(); return; }
    var s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/jssip/3.10.0/jssip.min.js';
    s.onload = callback;
    s.onerror = function() {
      console.error('[FonoUC] Failed to load JsSIP');
    };
    document.head.appendChild(s);
  }

  // ── Fetch SIP settings from backend ──────────────────────────────
  function fetchSettings(callback) {
    fetch('/api/method/fonouc_integration.fonouc_integration.integrations.fonouc.handler.get_sip_settings')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.message) {
          settings = data.message;
          callback(true);
        } else {
          callback(false);
        }
      })
      .catch(function() { callback(false); });
  }

  // ── Register SIP UA ───────────────────────────────────────────────
  function registerSIP() {
    if (!window.JsSIP || !settings || !settings.wss_server || !settings.sip_realm) {
      console.warn('[FonoUC] Missing SIP config:', settings);
      return;
    }

    if (UA) {
      try { UA.stop(); } catch(e) {}
      UA = null;
    }

    JsSIP.debug.disable('JsSIP:*');

    var socket = new JsSIP.WebSocketInterface(settings.wss_server);

    var config = {
      sockets:    [socket],
      uri:        'sip:' + settings.extension + '@' + settings.sip_realm,
      ha1:        settings.ha1,
      realm:      settings.sip_realm,
      display_name: settings.display_name || settings.extension,
      register:   true,
      register_expires: 300,
      user_agent: 'FonoUC-CRM/1.0',
    };

    UA = new JsSIP.UA(config);

    UA.on('registered', function() {
      registered = true;
      updateStatus('ready', '● Ready');
      console.log('[FonoUC] SIP registered');
    });

    UA.on('unregistered', function() {
      registered = false;
      updateStatus('offline', '○ Offline');
    });

    UA.on('registrationFailed', function(e) {
      registered = false;
      updateStatus('error', '✕ Reg Failed');
      console.error('[FonoUC] Registration failed:', e.cause);
    });

    UA.on('newRTCSession', function(data) {
      var session = data.session;
      if (data.originator === 'remote') {
        handleIncomingCall(session, data);
      }
    });

    UA.start();
  }

  // ── Handle incoming call ──────────────────────────────────────────
  function handleIncomingCall(session, data) {
    currentSession = session;
    var caller = data.request.from.uri.user || 'Unknown';
    updateStatus('ringing', '📞 Incoming: ' + caller);

    showNotification('📞 Incoming call from ' + caller, function() {
      session.answer({
        mediaConstraints: { audio: true, video: false }
      });
      updateStatus('in-call', '🔴 In Call: ' + caller);
      session.on('ended', onCallEnded);
      session.on('failed', onCallEnded);
    }, function() {
      session.terminate();
      updateStatus('ready', '● Ready');
    });

    // Auto-open lead for incoming call
    fetch('/api/method/fonouc_integration.fonouc_integration.api.endpoints.find_lead_by_phone?phone=' + encodeURIComponent(caller))
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.message && d.message.lead) {
          window.location.href = '/crm/leads/' + d.message.lead;
        }
      });
  }

  // ── Make outbound call ────────────────────────────────────────────
  function makeCall(destination) {
    if (!UA || !registered) {
      showToast('SIP not registered. Please wait...', '#dc3545');
      registerSIP();
      return;
    }
    if (currentSession) {
      showToast('Already on a call', '#fd7e14');
      return;
    }

    updateStatus('calling', '📞 Calling ' + destination + '...');

    var options = {
      mediaConstraints: { audio: true, video: false },
      pcConfig: {
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
      }
    };

    try {
      var session = UA.call('sip:' + destination + '@' + settings.sip_realm, options);
      currentSession = session;

      session.on('progress',  function() { updateStatus('calling', '📞 Ringing ' + destination); });
      session.on('confirmed', function() { updateStatus('in-call', '🔴 In Call: ' + destination); startCallTimer(); });
      session.on('ended',     onCallEnded);
      session.on('failed',    function(e) { showToast('Call failed: ' + e.cause, '#dc3545'); onCallEnded(); });

      // Log to CRM
      logCallToCRM(destination, 'Outgoing');

    } catch(e) {
      showToast('Call error: ' + e.message, '#dc3545');
      updateStatus('ready', '● Ready');
    }
  }

  function hangup() {
    if (currentSession) {
      try { currentSession.terminate(); } catch(e) {}
    }
  }

  function onCallEnded() {
    currentSession = null;
    stopCallTimer();
    updateStatus('ready', '● Ready');
  }

  // ── Call timer ────────────────────────────────────────────────────
  var callTimer = null;
  var callSeconds = 0;

  function startCallTimer() {
    callSeconds = 0;
    callTimer = setInterval(function() {
      callSeconds++;
      var m = Math.floor(callSeconds / 60);
      var s = callSeconds % 60;
      var el = document.getElementById('pbx-timer');
      if (el) el.textContent = (m < 10 ? '0' + m : m) + ':' + (s < 10 ? '0' + s : s);
    }, 1000);
  }

  function stopCallTimer() {
    if (callTimer) { clearInterval(callTimer); callTimer = null; }
    var el = document.getElementById('pbx-timer');
    if (el) el.textContent = '';
  }

  // ── Log call to CRM ───────────────────────────────────────────────
  function logCallToCRM(destination, type) {
    var csrf = window.csrf_token || '';
    fetch('/api/method/fonouc_integration.fonouc_integration.integrations.fonouc.handler.make_a_call', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrf },
      body: JSON.stringify({ to_number: destination })
    }).catch(function() {});
  }

  // ── UI ────────────────────────────────────────────────────────────
  function buildDialer() {
    if (document.getElementById('pbx-dialer')) return;

    var dialer = document.createElement('div');
    dialer.id = 'pbx-dialer';
    dialer.style.cssText = [
      'position:fixed', 'bottom:20px', 'right:20px', 'z-index:99999',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
    ].join(';');

    dialer.innerHTML = [
      // Floating button
      '<button id="pbx-toggle" style="width:56px;height:56px;border-radius:50%;',
      'background:#16a34a;color:white;border:none;font-size:20px;cursor:pointer;',
      'box-shadow:0 4px 20px rgba(0,0,0,0.3);display:flex;align-items:center;',
      'justify-content:center;margin-left:auto;">📞</button>',

      // Panel
      '<div id="pbx-panel" style="display:none;position:absolute;bottom:66px;right:0;',
      'width:280px;background:white;border-radius:16px;',
      'box-shadow:0 8px 40px rgba(0,0,0,0.2);overflow:hidden;">',

        // Header
        '<div style="background:#16a34a;color:white;padding:12px 16px;',
        'display:flex;justify-content:space-between;align-items:center;">',
          '<div>',
            '<div style="font-weight:700;font-size:14px;">FonoUC Dialer</div>',
            '<div id="pbx-status" style="font-size:11px;opacity:0.85;">○ Connecting...</div>',
          '</div>',
          '<div id="pbx-timer" style="font-size:18px;font-weight:700;font-family:monospace;"></div>',
        '</div>',

        // Dialpad area
        '<div style="padding:16px;">',
          // Number input
          '<input id="pbx-number" type="tel" placeholder="Enter number or extension"',
          ' style="width:100%;padding:10px 12px;border:2px solid #e5e7eb;border-radius:8px;',
          'font-size:16px;text-align:center;box-sizing:border-box;margin-bottom:12px;',
          'letter-spacing:1px;"/>',

          // Dialpad grid
          '<div id="pbx-keypad" style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;">',
          '</div>',

          // Call / Hangup buttons
          '<div style="display:flex;gap:8px;">',
            '<button id="pbx-call-btn" style="flex:1;padding:12px;background:#16a34a;color:white;',
            'border:none;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;">',
            '📞 Call</button>',
            '<button id="pbx-hangup-btn" style="display:none;flex:1;padding:12px;background:#dc3545;',
            'color:white;border:none;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;">',
            '📵 Hang Up</button>',
          '</div>',
        '</div>',
      '</div>',
    ].join('');

    document.body.appendChild(dialer);

    // Build keypad
    var keys = ['1','2','3','4','5','6','7','8','9','*','0','#'];
    var keypad = document.getElementById('pbx-keypad');
    keys.forEach(function(k) {
      var btn = document.createElement('button');
      btn.textContent = k;
      btn.style.cssText = 'padding:12px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;font-size:18px;cursor:pointer;font-weight:600;';
      btn.addEventListener('click', function() {
        document.getElementById('pbx-number').value += k;
      });
      keypad.appendChild(btn);
    });

    // Toggle panel
    document.getElementById('pbx-toggle').addEventListener('click', function() {
      var panel = document.getElementById('pbx-panel');
      dialerVisible = !dialerVisible;
      panel.style.display = dialerVisible ? 'block' : 'none';
      // Pre-fill phone from page
      if (dialerVisible) {
        var phone = getPhoneFromPage();
        if (phone) document.getElementById('pbx-number').value = phone;
      }
    });

    // Call button
    document.getElementById('pbx-call-btn').addEventListener('click', function() {
      var num = document.getElementById('pbx-number').value.trim();
      if (!num) { showToast('Enter a number to call', '#fd7e14'); return; }
      makeCall(num);
      document.getElementById('pbx-call-btn').style.display = 'none';
      document.getElementById('pbx-hangup-btn').style.display = 'block';
    });

    // Hangup button
    document.getElementById('pbx-hangup-btn').addEventListener('click', function() {
      hangup();
      document.getElementById('pbx-call-btn').style.display = 'block';
      document.getElementById('pbx-hangup-btn').style.display = 'none';
    });

    // Allow Enter key to dial
    document.getElementById('pbx-number').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') document.getElementById('pbx-call-btn').click();
    });
  }

  function updateStatus(state, text) {
    var el = document.getElementById('pbx-status');
    var btn = document.getElementById('pbx-toggle');
    if (el) el.textContent = text;
    var colors = { ready: '#16a34a', offline: '#6b7280', error: '#dc3545', calling: '#2563eb', 'in-call': '#dc3545', ringing: '#d97706' };
    if (btn) btn.style.background = colors[state] || '#16a34a';
    // Show/hide call controls
    var callBtn = document.getElementById('pbx-call-btn');
    var hangupBtn = document.getElementById('pbx-hangup-btn');
    if (callBtn && hangupBtn) {
      if (state === 'in-call' || state === 'calling') {
        callBtn.style.display = 'none';
        hangupBtn.style.display = 'block';
      } else if (state === 'ready' || state === 'offline' || state === 'error') {
        callBtn.style.display = 'block';
        hangupBtn.style.display = 'none';
      }
    }
  }

  function getPhoneFromPage() {
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      var txt = walker.currentNode.textContent.trim();
      if (/^07\d{8}$/.test(txt) || /^\+94\d{9}$/.test(txt)) return txt;
    }
    return '';
  }

  function showToast(msg, color) {
    var t = document.createElement('div');
    t.style.cssText = 'position:fixed;top:20px;right:90px;z-index:999999;background:' + (color||'#333') + ';color:white;padding:10px 16px;border-radius:8px;font-size:13px;font-family:sans-serif;box-shadow:0 4px 12px rgba(0,0,0,0.2);';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function() { t.remove(); }, 4000);
  }

  function showNotification(msg, onAnswer, onReject) {
    var n = document.createElement('div');
    n.style.cssText = 'position:fixed;top:20px;right:90px;z-index:999999;background:white;border:2px solid #16a34a;border-radius:12px;padding:16px;font-family:sans-serif;box-shadow:0 8px 32px rgba(0,0,0,0.2);min-width:280px;';
    n.innerHTML = '<div style="font-weight:600;margin-bottom:12px;color:#111;">' + msg + '</div>'
      + '<div style="display:flex;gap:8px;">'
      + '<button style="flex:1;padding:8px;background:#16a34a;color:white;border:none;border-radius:6px;cursor:pointer;font-weight:600;">Answer</button>'
      + '<button style="flex:1;padding:8px;background:#dc3545;color:white;border:none;border-radius:6px;cursor:pointer;font-weight:600;">Decline</button>'
      + '</div>';
    document.body.appendChild(n);
    n.querySelectorAll('button')[0].onclick = function() { n.remove(); onAnswer(); };
    n.querySelectorAll('button')[1].onclick = function() { n.remove(); onReject(); };
    setTimeout(function() { if (n.parentNode) { n.remove(); onReject(); } }, 30000);
  }

  // ── Auto-fill phone on Lead/Deal pages ───────────────────────────
  function watchRouteForPhone() {
    setInterval(function() {
      var path = window.location.pathname;
      if (path === lastPath) return;
      lastPath = path;
      if (path.indexOf('/crm/leads/') > -1 || path.indexOf('/crm/deals/') > -1) {
        setTimeout(function() {
          var phone = getPhoneFromPage();
          var inp = document.getElementById('pbx-number');
          if (phone && inp && !inp.value) inp.value = phone;
        }, 2500);
      }
    }, 500);
  }

  // ── Init ──────────────────────────────────────────────────────────
  function init() {
    buildDialer();
    watchRouteForPhone();
    fetchSettings(function(ok) {
      if (!ok) {
        updateStatus('offline', '○ Not configured');
        return;
      }
      loadJsSIP(function() {
        registerSIP();
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 1000);
  }

})();
