/* Core: helpers, icons, API layer, toasts, dialogs and loading/empty/error states.
   Everything is exposed on window.CA so the other scripts stay small. */
(function () {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const h = html => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };

  function readTok() {
    try {
      const t = JSON.parse(localStorage.getItem("tok") || "null");
      if (!t || !t.access_token || !t.refresh_token) return null;
      return t;
    } catch (e) { return null; }
  }
  const state = { tok: readTok(), me: null, stages: [], profile: null };
  let refreshPromise = null;

  /* ---------- formatting ---------- */
  const money = n => "\u20B9" + Number(n || 0).toLocaleString("en-IN");
  const dtf = x => new Date(x).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  const timef = x => new Date(x).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  function dayLabel(x) {
    const d = new Date(x), now = new Date(), tomorrow = new Date(now.getTime() + 864e5);
    if (sameDay(d, now)) return "Today";
    if (sameDay(d, tomorrow)) return "Tomorrow";
    return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
  }
  const stageLabel = s => String(s || "").replace(/_/g, " ").replace(/^./, c => c.toUpperCase());

  /* ---------- icons (inline SVG, one consistent set) ---------- */
  const PATHS = {
    home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    briefcase: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/><path d="M3 13h18"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    receipt: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
    store: '<path d="M4 9l1-5h14l1 5"/><path d="M4 9a2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0"/><path d="M5 12v8h14v-8"/>',
    sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
    check: '<path d="M5 12l4 4 10-10"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    send: '<path d="M4 12l16-8-6 16-3-7z"/>',
    more: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
    refresh: '<path d="M20 11a8 8 0 1 0-2 5.5"/><path d="M20 4v7h-7"/>',
    download: '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    logout: '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 16l-4-4 4-4M6 12h10"/>',
    send2: '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/>',
    chevron: '<path d="M9 6l6 6-6 6"/>',
    expand: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    shrink: '<path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-8M22 20V8"/>',
  };
  const icon = (name, extra = "") => `<svg class="i ${extra}" viewBox="0 0 24 24" aria-hidden="true">${PATHS[name] || ""}</svg>`;

  /* ---------- API layer (token refresh, friendly errors) ---------- */
  function apiError(message, status) { const e = new Error(message); e.status = status; return e; }

  function friendlyError(err, fallback = "Something went wrong. Please try again.") {
    console.error(err);
    if (!err) return fallback;
    const status = err.status;
    if (status === 401) return err.message || ui("session_expired");
    if (status === 403) return "You don't have permission to do that.";
    if (status === 404) return "We couldn't find what you were looking for.";
    if (status === 429) return "Too many requests. Please wait a moment and try again.";
    if (status === 408 || /timeout/i.test(String(err.message || ""))) return "That took too long. Please try again.";
    if (status >= 502 && status <= 504) return "The server is temporarily unavailable. Please try again shortly.";
    if (status >= 500 || (status === 0 && !err.message)) return fallback;
    const m = String(err.message || "");
    return m && m.length < 170 && !/traceback|exception|sqlalchemy/i.test(m) ? m : fallback;
  }

  async function refreshTokens() {
    if (!state.tok?.refresh_token) return false;
    if (refreshPromise) return refreshPromise;
    refreshPromise = (async () => {
      try {
        const rr = await fetch("/auth/refresh", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: state.tok.refresh_token }),
        });
        if (!rr.ok) return false;
        state.tok = await rr.json();
        localStorage.setItem("tok", JSON.stringify(state.tok));
        return true;
      } catch (e) {
        return false;
      } finally {
        refreshPromise = null;
      }
    })();
    return refreshPromise;
  }

  async function api(path, opt = {}, retry = true) {
    const { json, ...rest } = opt;
    const headers = { ...(rest.headers || {}) };
    if (state.tok) headers.Authorization = "Bearer " + state.tok.access_token;
    let body = rest.body;
    if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
    let res;
    try { res = await fetch(path, { ...rest, headers, body }); }
    catch (e) { throw apiError("Can't reach the server. Check that it is running.", 0); }
    if (res.status === 401 && state.tok && retry) {
      if (await refreshTokens()) return api(path, opt, false);
      logout({ sessionExpired: true });
      throw apiError("Your session expired. Please log in again.", 401);
    }
    if (!res.ok) {
      let d = res.statusText, fields = null;
      try {
        const j = await res.json(); d = j.detail || d;
        if (Array.isArray(d)) {  // validation errors: keep one message per field
          fields = {};
          d.forEach(x => { const k = (x.loc || []).filter(p => p !== "body").join("."); if (k && !fields[k]) fields[k] = String(x.msg || "").replace(/^Value error, /, ""); });
          d = Object.values(fields)[0] || "Please check the details and try again.";
        }
      } catch (e) { /* not JSON */ }
      const err = apiError(typeof d === "string" ? d : "Please check the details and try again.", res.status);
      err.fields = fields;
      throw err;
    }
    return res.status === 204 ? null : res.json();
  }

  function logout(opts = {}) {
    if (opts.sessionExpired) {
      try { sessionStorage.setItem("ca.flash", JSON.stringify({ type: "warning", message: "Your session expired. Please log in again." })); } catch (e) { /* ignore */ }
    }
    localStorage.removeItem("tok");
    state.tok = null;
    location.hash = "";
    location.reload();
  }

  function readFlashToast() {
    try {
      const raw = sessionStorage.getItem("ca.flash");
      if (!raw) return;
      sessionStorage.removeItem("ca.flash");
      const f = JSON.parse(raw);
      if (f && f.message) toast(f.type || "info", f.message, f.type === "error" ? 9000 : 6000);
    } catch (e) { /* ignore */ }
  }

  /* ---------- toasts ---------- */
  let lastToast = { key: "", at: 0 };
  function toast(type, message, ms) {
    const root = $("#toasts");
    if (!root) return;
    const key = type + "\0" + message;
    const now = Date.now();
    if (lastToast.key === key && now - lastToast.at < 900) return;
    lastToast = { key, at: now };
    while (root.children.length >= 4) root.firstElementChild.remove();
    const names = { success: "check", error: "alert", warning: "alert", info: "info" };
    const el = h(`<div class="toast toast--${type}" role="${type === "error" ? "alert" : "status"}">
      ${icon(names[type] || "info")}<div class="toast__msg">${esc(message)}</div>
      <button class="toast__close" type="button" aria-label="Dismiss">${icon("x", "")}</button></div>`);
    const close = () => { el.classList.add("is-leaving"); setTimeout(() => el.remove(), 170); };
    el.querySelector(".toast__close").onclick = close;
    root.append(el);
    setTimeout(close, ms || (type === "error" ? 7000 : 4500));
  }

  /* ---------- buttons: busy state blocks double clicks ---------- */
  async function busy(btn, label, fn) {
    if (!btn || btn.dataset.busy) return;
    const old = btn.innerHTML;
    btn.dataset.busy = "1"; btn.disabled = true; btn.setAttribute("aria-busy", "true");
    btn.innerHTML = `<span class="spinner" aria-hidden="true"></span><span>${esc(label)}</span>`;
    try { return await fn(); }
    finally {
      if (btn.isConnected) { btn.disabled = false; btn.innerHTML = old; delete btn.dataset.busy; btn.removeAttribute("aria-busy"); }
    }
  }

  /* ---------- dialogs ---------- */
  function modal({ title, body = "", submitLabel = "Save", submitClass = "btn--primary", cancelLabel = "Cancel", onSubmit = null, bodyNode = null }) {
    const dlg = h(`<dialog class="modal" aria-labelledby="mtitle"><form class="modal__form" novalidate>
      <div class="modal__head"><h2 class="modal__title" id="mtitle">${esc(title)}</h2>
        <button type="button" class="btn btn--ghost btn--icon" data-close aria-label="Close">${icon("x")}</button></div>
      <div class="modal__body stack">${body}</div>
      <p class="form-error" role="alert" hidden></p>
      <div class="modal__foot">
        <button type="button" class="btn btn--secondary" data-close>${esc(onSubmit ? cancelLabel : "Close")}</button>
        ${onSubmit ? `<button type="submit" class="btn ${submitClass}">${esc(submitLabel)}</button>` : ""}
      </div></form></dialog>`);
    if (bodyNode) dlg.querySelector(".modal__body").append(bodyNode);
    const form = dlg.querySelector("form"), err = dlg.querySelector(".form-error");
    const close = () => { if (dlg.open) dlg.close(); };
    dlg.addEventListener("close", () => dlg.remove());
    dlg.addEventListener("click", e => { if (e.target === dlg) close(); });
    dlg.querySelectorAll("[data-close]").forEach(b => b.onclick = close);
    form.onsubmit = async e => {
      e.preventDefault();
      if (!onSubmit) return close();
      if (!form.checkValidity()) { form.reportValidity(); return; }
      err.hidden = true;
      await busy(form.querySelector('[type="submit"]'), "Saving...", async () => {
        try { await onSubmit(Object.fromEntries(new FormData(form).entries()), form); close(); }
        catch (ex) { err.textContent = friendlyError(ex); err.hidden = false; }
      });
    };
    document.body.append(dlg);
    dlg.showModal();
    const first = dlg.querySelector("input:not([type=hidden]), select, textarea");
    if (first) first.focus();
    return { el: dlg, close };
  }

  /** Promise-based confirmation. Resolves true only if the user confirmed (not Escape / cancel). */
  function confirm({ title, text = "", submitLabel = "Confirm", submitClass = "btn--primary", cancelLabel = "Cancel", details = "" }) {
    return new Promise(resolve => {
      let yes = false;
      const body = `${text ? `<p>${esc(text)}</p>` : ""}${details ? `<p class="caption">${esc(details)}</p>` : ""}`;
      const m = modal({ title, body, submitLabel, submitClass, cancelLabel, onSubmit: async () => { yes = true; } });
      m.el.addEventListener("close", () => resolve(yes));
    });
  }

  /* ---------- states: empty, error, skeleton ---------- */
  function emptyState({ icon: ic = "info", title, text = "", actionLabel = "", onAction = null, actionClass = "btn--primary" }) {
    const el = h(`<div class="state"><div class="state__icon">${icon(ic)}</div>
      <div class="state__title">${esc(title)}</div>${text ? `<p class="state__text">${esc(text)}</p>` : ""}
      ${actionLabel ? `<button class="btn ${actionClass}" type="button">${esc(actionLabel)}</button>` : ""}</div>`);
    const b = el.querySelector("button");
    if (b && onAction) b.onclick = () => onAction(b);
    return el;
  }

  function errorState({ title = "Something went wrong", text = "", onRetry = null }) {
    const el = h(`<div class="state state--error" role="alert"><div class="state__icon">${icon("alert")}</div>
      <div class="state__title">${esc(title)}</div>${text ? `<p class="state__text">${esc(text)}</p>` : ""}
      ${onRetry ? `<button class="btn btn--secondary" type="button">${icon("refresh")}Try again</button>` : ""}</div>`);
    const b = el.querySelector("button");
    if (b && onRetry) b.onclick = () => busy(b, "Retrying...", async () => { await onRetry(); });
    return el;
  }

  function skeleton(kind = "list") {
    const line = w => `<div class="skeleton skeleton--line" style="width:${w}"></div>`;
    if (kind === "cards") return h(`<div class="deal-grid">${'<div class="card stack">' + line("45%") + line("80%") + line("100%") + "</div>"}${'<div class="card stack">' + line("55%") + line("70%") + line("100%") + "</div>"}</div>`);
    if (kind === "dashboard") return h(`<div class="stack--lg stack"><div class="stack">${line("38%")}${line("55%")}</div>
      <div class="dash-metrics">${'<div class="skeleton skeleton--block"></div>'.repeat(4)}</div>
      <div class="dash-grid"><div class="skeleton skeleton--block" style="height:220px"></div><div class="skeleton skeleton--block" style="height:220px"></div></div></div>`);
    return h(`<div class="card stack">${line("40%")}${line("90%")}${line("70%")}${line("85%")}</div>`);
  }

  /* ---------- creator-type wording (falls back to the influencer set until the profile loads) ---------- */
  const UI_I18N = {
    en: {
      nav_dashboard: "Dashboard", nav_deals: "Deals", nav_inbox: "Inbox", nav_schedule: "Schedule", nav_invoices: "Invoices",
      nav_expenses: "Expenses", nav_analytics: "Analytics", nav_content: "Content", nav_mediakit: "Media kit",
      nav_brands: "Brands",
      crm_page_title: "Brands", crm_page_sub: "Discover partners, manage relationships, and draft pitches — you approve every send.",
      crm_discover: "Discover", crm_mine: "My brands", crm_search: "Search", crm_apply: "Apply", crm_pitch: "Draft pitch",
      crm_open: "Open CRM", crm_add: "Add to CRM", crm_in_crm: "In CRM", crm_disc_empty: "No brands matched",
      crm_disc_empty_sub: "Try another search or set your niche in Profile.", crm_niche_tip: "Tip: set your niche in Profile for better matches.",
      crm_sort: "Sort", crm_sort_updated: "Recently updated", crm_sort_name: "Name", crm_sort_deals: "Most deals",
      crm_sort_follow: "Follow-up date", crm_stage: "Pipeline stage", crm_due_only: "Due follow-ups only",
      crm_sync: "Sync from deals", crm_synced: "Brands synced from your deals", crm_suggestions: "Needs follow-up",
      crm_empty: "No brands in CRM yet", crm_empty_sub: "Sync from deals or add a brand from Discover.",
      crm_next: "Next follow-up", crm_back: "Back", crm_ai_summary: "AI relationship summary", crm_prefs: "Preferences & notes",
      crm_rel_ph: "Relationship summary (your words)", crm_pref_ph: "Preferences JSON, e.g. {\"tone\":\"friendly\"}",
      crm_save: "Save", crm_saved: "Saved", crm_bad_json: "Preferences must be valid JSON", crm_pipeline: "Deal pipeline",
      crm_contacts: "Contacts", crm_no_contacts: "No contacts yet", crm_add_contact: "Add contact",
      crm_notes: "Notes", crm_note_gen: "General note", crm_note_neg: "Negotiation note",
      crm_followups: "Scheduled follow-ups", crm_schedule: "Schedule reminder", crm_due: "Due date", crm_done: "Mark done",
      crm_history: "Interaction history",       crm_deals: "Campaigns & deals", crm_close: "Close",
      roi_title: "Campaign ROI", roi_sub: "Invoiced, received, expenses and profit from your records — estimates are labeled.",
      roi_back: "Back to deals", roi_brand: "Brand filter", roi_from: "From", roi_to: "To", roi_apply: "Apply",
      roi_overview: "Financial overview", roi_compare: "Campaign comparison", roi_empty: "No deals yet",
      roi_empty_sub: "Add deals and link invoices or expenses to see ROI.",
      mk_title: "Media kit", mk_sub: "Rate card and brand deck — you control what is public.",
      mk_save: "Save", mk_saved: "Media kit saved", mk_pdf: "Download PDF", mk_settings: "Kit settings",
      mk_headline: "Headline", mk_intro: "Introduction", mk_template: "PDF template", mk_avatar: "Profile photo",
      mk_show_rates: "Show rate card", mk_show_metrics: "Show engagement metrics", mk_show_email: "Show contact email",
      mk_show_phone: "Show phone", mk_rates: "Rate card", mk_rates_hint: "Enter your own rates — nothing is guessed.",
      mk_add_rate: "Add line", mk_portfolio: "Collaborations", mk_deal: "Deal", mk_summary: "Short summary", mk_add: "Add",
      mk_share: "Public link", mk_share_hint: "Publishing creates a read-only link. Revoke anytime.",
      mk_not_published: "Not published", mk_publish: "Publish link", mk_publish_confirm: "Anyone with the link can view this snapshot. Private analytics are not included unless you enabled metrics.",
      mk_published: "Link published", mk_revoke: "Revoke link", mk_revoked: "Link revoked",
      mk_avatar_ok: "Photo updated", mk_pick_deal: "Choose a deal first", mk_samples: "Content samples",
      nav_assistant: "Assistant",
      ct_title: "Content", ct_sub: "Ideas, scripts and captions — you publish manually.",
      ct_publish_note: "Drafts only. Nothing is posted to Instagram, YouTube or TikTok from this app.",
      ct_ideas: "5 ideas", ct_generate: "Generate script", ct_generate_btn: "Generate", ct_edit: "Edit",
      ct_save_draft: "Save revision", ct_status: "Status", ct_title_f: "Title", ct_script: "Script", ct_caption: "Caption",
      ct_hashtags: "Hashtags", ct_saved: "Saved", ct_format: "Format", ct_platform: "Platform", ct_topic: "Topic",
      ct_deal: "Campaign / deal", ct_search: "Search", ct_apply: "Apply", ct_suggestions: "Suggestions",
      ct_no_suggestions: "Complete your profile to unlock tips.", ct_calendar: "Upcoming", ct_cal_empty: "Schedule posts to see them here.",
      ct_unscheduled: "Not scheduled", ct_empty: "No content yet", ct_empty_sub: "Generate ideas or a reel script.",
      ct_copy: "Copy", ct_export: "Export", ct_repurpose: "Repurpose", ct_delete: "Delete", ct_deleted: "Deleted",
      ct_copied: "Copied", ct_generated: "Draft created", ct_ideas_done: "Ideas added",
      nav_home: "Home", nav_more: "More",
      an_title: "Analytics", an_sub: "Followers, reach and engagement from verified or manual data only.",
      an_add_metric: "Add metric", an_save_metric: "Save", an_platform: "Platform", an_metric: "Metric", an_value: "Value",
      an_period_start: "Date", an_notes: "Notes", an_metric_saved: "Metric saved", an_from: "From", an_to: "To",
      an_grain: "Chart", an_apply: "Apply", an_export_csv: "CSV", an_export_pdf: "PDF", an_downloaded: "Downloaded",
      an_no_chart: "No chart data", an_no_chart_sub: "Add metrics for this range.", an_no_metrics: "No metrics in range.",
      an_growth: "Change", an_connect: "Connect", an_sync: "Sync", an_sync_done: "Sync finished",
      an_connect_fail: "Connection unavailable — use manual entry.", an_connected: "Account connected",
      an_no_platforms: "No platforms", an_no_platforms_sub: "Add platforms in Profile first.",
      an_chart_title: "Growth", an_compare: "Platform comparison", an_no_compare: "Add follower snapshots to compare.",
      an_top_content: "Top content", an_no_content: "No content logged", an_import: "Import CSV",
      an_import_hint: "Columns: date, platform, metric, value", an_imported: "Import complete", an_import_fail: "Import failed",
      an_insights: "Insights",
      greet_morning: "Good morning", greet_afternoon: "Good afternoon", greet_evening: "Good evening",
      dash_sub: "Here's what needs your attention today.", outstanding: "Outstanding", received: "received",
      new_brand_emails: "New brand emails", upcoming_events: "Upcoming events", next_7_days: "next 7 days",
      needs_attention: "Needs your attention", upcoming: "Upcoming", ai_assistant: "AI Assistant", ask_assistant: "Ask Assistant",
      create_invoice: "Create invoice", check_gmail: "Check Gmail", ask_ai: "Ask AI", couldnt_load: "Couldn't load",
      chat_title: "Assistant", chat_sub: "Ask in English, हिन्दी or मराठी", chat_placeholder: "Type a message",
      voice_listening: "Listening…", voice_processing: "Understanding your voice…", voice_retry: "Retry",
      voice_stt_lang: "Speech language", voice_detected: "Detected", voice_recognized: "Recognized",
      lang_toast: "Replies will now be in",
      session_expired: "Your session expired. Please log in again.",
      dash_load_warn: "Some dashboard numbers couldn't be loaded. Try refreshing.",
    },
    hi: {
      nav_dashboard: "डैशबोर्ड", nav_deals: "डील", nav_inbox: "इनबॉक्स", nav_schedule: "शेड्यूल", nav_invoices: "इनवॉइस",
      nav_expenses: "खर्च", nav_analytics: "एनालिटिक्स", nav_content: "कंटेंट", nav_mediakit: "मीडिया किट",
      nav_brands: "ब्रांड",
      mk_title: "मीडिया किट", mk_sub: "रेट कार्ड — आप नियंत्रित करें क्या सार्वजनिक है।", mk_save: "सेव",
      mk_pdf: "PDF", mk_publish: "लिंक प्रकाशित करें", mk_revoke: "रद्द करें", mk_saved: "सेव हो गया",
      nav_assistant: "सहायक", nav_home: "होम",
      ct_title: "कंटेंट", ct_sub: "आइडिया और स्क्रिप्ट — आप खुद पोस्ट करें।",
      ct_publish_note: "केवल ड्राफ्ट। ऐप से कोई ऑटो-पोस्ट नहीं।",
      ct_ideas: "5 आइडिया", ct_generate: "स्क्रिप्ट", ct_generate_btn: "बनाएं", ct_edit: "संपादित", ct_save_draft: "सेव",
      ct_status: "स्थिति", ct_script: "स्क्रिप्ट", ct_caption: "कैप्शन", ct_hashtags: "हैशटैग", ct_saved: "सेव हो गया",
      ct_format: "फॉर्मैट", ct_platform: "प्लेटफ़ॉर्म", ct_topic: "विषय", ct_deal: "डील", ct_search: "खोज",
      ct_apply: "लागू", ct_suggestions: "सुझाव", ct_calendar: "आगामी", ct_cal_empty: "अभी खाली", ct_empty: "कुछ नहीं",
      ct_copy: "कॉपी", ct_export: "निर्यात", ct_repurpose: "रीपर्पज़", ct_delete: "हटाएं", ct_generated: "बन गया",
      nav_more: "और",
      an_title: "एनालिटिक्स", an_sub: "केवल सही या मैन्युअल डेटा पर आधारित मेट्रिक्स।",
      an_add_metric: "मेट्रिक जोड़ें", an_save_metric: "सेव", an_platform: "प्लेटफ़ॉर्म", an_metric: "मेट्रिक",
      an_value: "मान", an_period_start: "तारीख", an_notes: "नोट", an_metric_saved: "सेव हो गया",
      an_from: "से", an_to: "तक", an_grain: "चार्ट", an_apply: "लागू", an_export_csv: "CSV", an_export_pdf: "PDF",
      an_downloaded: "डाउनलोड", an_no_chart: "कोई चार्ट नहीं", an_no_chart_sub: "इस अवधि में मेट्रिक जोड़ें।",
      an_no_metrics: "कोई मेट्रिक नहीं।", an_growth: "बदलाव", an_connect: "कनेक्ट", an_sync: "सिंक",
      an_sync_done: "सिंक पूर्ण", an_connect_fail: "कनेक्शन उपलब्ध नहीं।", an_connected: "खाता जुड़ा",
      an_no_platforms: "कोई प्लेटफ़ॉर्म नहीं", an_no_platforms_sub: "प्रोफ़ाइल में प्लेटफ़ॉर्म जोड़ें।",
      an_chart_title: "वृद्धि", an_compare: "तुलना", an_no_compare: "तुलना के लिए स्नैपशॉट जोड़ें।",
      an_top_content: "शीर्ष कंटेंट", an_no_content: "कोई कंटेंट नहीं", an_import: "CSV आयात",
      an_import_hint: "कॉलम: date, platform, metric, value", an_imported: "आयात पूर्ण", an_import_fail: "आयात विफल",
      an_insights: "इनसाइट्स",
      greet_morning: "सुप्रभात", greet_afternoon: "नमस्कार", greet_evening: "शुभ संध्या",
      dash_sub: "आज आपका ध्यान किन चीज़ों पर चाहिए।", outstanding: "बकाया", received: "प्राप्त",
      new_brand_emails: "नए ब्रांड ईमेल", upcoming_events: "आगामी इवेंट", next_7_days: "अगले 7 दिन",
      needs_attention: "ध्यान दें", upcoming: "आगामी", ai_assistant: "AI सहायक", ask_assistant: "सहायक से पूछें",
      create_invoice: "इनवॉइस बनाएं", check_gmail: "Gmail देखें", ask_ai: "AI से पूछें", couldnt_load: "लोड नहीं हुआ",
      chat_title: "सहायक", chat_sub: "अंग्रेज़ी, हिन्दी या मराठी में पूछें", chat_placeholder: "संदेश लिखें",
      voice_listening: "सुन रहे हैं…", voice_processing: "समझ रहे हैं…", voice_retry: "फिर कोशिश करें",
      voice_stt_lang: "भाषण भाषा", voice_detected: "पहचानी", voice_recognized: "पहचाना",
      lang_toast: "अब जवाब इस भाषा में होंगे:",
      session_expired: "आपका सत्र समाप्त हो गया। कृपया फिर से लॉग इन करें।",
      dash_load_warn: "कुछ आँकड़े लोड नहीं हुए। पेज रिफ्रेश करें।",
    },
    mr: {
      nav_dashboard: "डॅशबोर्ड", nav_deals: "डील", nav_inbox: "इनबॉक्स", nav_schedule: "वेळापत्रक", nav_invoices: "इनव्हॉइस",
      nav_expenses: "खर्च", nav_analytics: "ॲनालिटिक्स", nav_content: "कंटेंट", nav_mediakit: "मीडिया किट",
      nav_brands: "ब्रँड",
      mk_title: "मीडिया किट", mk_sub: "रेट कार्ड — सार्वजनिक माहिती तुम्ही निवडता.", mk_save: "जतन", mk_pdf: "PDF",
      mk_publish: "लिंक प्रकाशित करा", mk_revoke: "रद्द करा", mk_saved: "जतन झाले",
      nav_assistant: "सहाय्यक", nav_home: "होम",
      ct_title: "कंटेंट", ct_sub: "कल्पना आणि स्क्रिप्ट — तुम्ही स्वतः प्रकाशित करा.",
      ct_publish_note: "फक्त मसुदे. अॅप वरून ऑटो-पोस्ट नाही.",
      ct_ideas: "5 कल्पना", ct_generate: "स्क्रिप्ट", ct_generate_btn: "तयार करा", ct_edit: "संपादन", ct_save_draft: "जतन",
      ct_status: "स्थिती", ct_script: "स्क्रिप्ट", ct_caption: "मथळा", ct_hashtags: "हॅशटॅग", ct_saved: "जतन झाले",
      ct_format: "स्वरूप", ct_platform: "प्लॅटफॉर्म", ct_topic: "विषय", ct_deal: "डील", ct_search: "शोध",
      ct_apply: "लागू", ct_suggestions: "सूचना", ct_calendar: "आगामी", ct_empty: "रिक्त", ct_copy: "कॉपी",
      ct_export: "एक्सपोर्ट", ct_repurpose: "रीपर्पज", ct_delete: "हटवा", ct_generated: "तयार",
      nav_more: "अजून",
      an_title: "ॲनालिटिक्स", an_sub: "फक्त सत्यापित किंवा मॅन्युअल डेटावर आधारित मेट्रिक्स.",
      an_add_metric: "मेट्रिक जोडा", an_save_metric: "जतन", an_platform: "प्लॅटफॉर्म", an_metric: "मेट्रिक",
      an_value: "मूल्य", an_period_start: "तारीख", an_notes: "नोट", an_metric_saved: "जतन झाले",
      an_from: "पासून", an_to: "पर्यंत", an_grain: "चार्ट", an_apply: "लागू", an_export_csv: "CSV", an_export_pdf: "PDF",
      an_downloaded: "डाउनलोड", an_no_chart: "चार्ट नाही", an_no_chart_sub: "या कालावधीत मेट्रिक जोडा.",
      an_no_metrics: "मेट्रिक नाहीत.", an_growth: "बदल", an_connect: "कनेक्ट", an_sync: "सिंक",
      an_sync_done: "सिंक पूर्ण", an_connect_fail: "कनेक्शन उपलब्ध नाही.", an_connected: "खाते जोडले",
      an_no_platforms: "प्लॅटफॉर्म नाहीत", an_no_platforms_sub: "प्रोफाइलमध्ये प्लॅटफॉर्म जोडा.",
      an_chart_title: "वाढ", an_compare: "तुलना", an_no_compare: "तुलनेसाठी स्नॅपशॉट जोडा.",
      an_top_content: "टॉप कंटेंट", an_no_content: "कंटेंट नाही", an_import: "CSV आयात",
      an_import_hint: "कॉलम: date, platform, metric, value", an_imported: "आयात पूर्ण", an_import_fail: "आयात अयशस्वी",
      an_insights: "इनसाइट्स",
      greet_morning: "शुभ सकाळ", greet_afternoon: "नमस्कार", greet_evening: "शुभ संध्याकाळ",
      dash_sub: "आज तुमचे लक्ष कुठे असावे ते येथे आहे.", outstanding: "थकबाकी", received: "मिळाले",
      new_brand_emails: "नवीन ब्रँड ईमेल", upcoming_events: "पुढील कार्यक्रम", next_7_days: "पुढील 7 दिवस",
      needs_attention: "लक्ष द्या", upcoming: "पुढील", ai_assistant: "AI सहाय्यक", ask_assistant: "सहाय्यकाला विचारा",
      create_invoice: "इनव्हॉइस तयार करा", check_gmail: "Gmail तपासा", ask_ai: "AI ला विचारा", couldnt_load: "लोड झाले नाही",
      chat_title: "सहाय्यक", chat_sub: "इंग्रजी, हिन्दी किंवा मराठीमध्ये विचारा", chat_placeholder: "संदेश लिहा",
      voice_listening: "ऐकत आहे…", voice_processing: "समजून घेत आहे…", voice_retry: "पुन्हा प्रयत्न",
      voice_stt_lang: "भाषण भाषा", voice_detected: "ओळखले", voice_recognized: "ओळखले",
      lang_toast: "आता उत्तरे या भाषेत येतील:",
      session_expired: "तुमचे सत्र संपले. कृपया पुन्हा लॉग इन करा.",
      dash_load_warn: "काही आकडे लोड झाले नाहीत. पृष्ठ रिफ्रेश करा.",
    },
  };
  const uiLang = () => (state.me && state.me.language) || "en";
  const ui = key => (UI_I18N[uiLang()] || UI_I18N.en)[key] || UI_I18N.en[key] || key;
  function timeGreet() {
    const hr = new Date().getHours();
    return ui(hr < 12 ? "greet_morning" : hr < 17 ? "greet_afternoon" : "greet_evening");
  }
  function applyLanguage() {
    const lang = uiLang();
    document.documentElement.lang = lang === "hi" ? "hi" : lang === "mr" ? "mr" : "en";
    const cap = $(".chat__title");
    const sub = $(".chat__head .caption");
    const msg = $("#msg");
    if (cap) cap.textContent = ui("chat_title");
    if (sub) sub.textContent = ui("chat_sub");
    if (msg) msg.placeholder = ui("chat_placeholder");
    const vstt = $("#voiceSttLang");
    const vcap = $("#voiceBar label.caption");
    if (vcap) vcap.textContent = ui("voice_stt_lang");
  }

  const DEFAULT_LABELS = { deals: "Deals", deal: "deal", deals_lower: "deals", add_deal: "Add deal", deliverables_hint: "2 reels, 3 stories",
    event: "shoot", add_event: "Add event", event_hint: "Shoot at Bandra studio", due_label: "deliverables due",
    tagline: "Here's what needs your attention today.", pages_sub: "Track every paid and barter collaboration." };
  const DEFAULT_CHIPS = ["List my deals", "Check my inbox", "Any follow-ups pending?"];
  const DEFAULT_SUGGESTIONS = ["Add a barter deal with Mamaearth", "Book a cab from Panvel to Bandra tomorrow at 4 pm", "Check my inbox", "Any follow-ups pending?"];
  const pz = () => (state.profile && state.profile.personalization) || {};
  const t = key => (pz().labels && pz().labels[key]) || DEFAULT_LABELS[key] || key;
  const cap = x => String(x || "").replace(/^./, c => c.toUpperCase());
  const chips = () => pz().chips || DEFAULT_CHIPS;
  const suggestions = () => pz().chat_suggestions || DEFAULT_SUGGESTIONS;
  async function loadProfile() {
    try { state.profile = await api("/profile"); } catch (e) { state.profile = state.profile || null; }
    return state.profile;
  }

  window.CA = { t, ui, timeGreet, applyLanguage, cap, chips, suggestions, loadProfile, readFlashToast, $, $$, esc, h, state, money, dtf, timef, dayLabel, sameDay, stageLabel, icon, api, apiError, friendlyError,
    logout, toast, busy, modal, confirm, emptyState, errorState, skeleton, views: {}, actions: {} };
})();
