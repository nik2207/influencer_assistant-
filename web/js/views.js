/* Views: Dashboard, Deals, Inbox, Schedule, Invoices, Brands, plus the quick-action dialogs.
   Each view is  async (container, ctx)  where ctx = { alive(), silent }. */
(function () {
  "use strict";
  const { $, $$, esc, h, api, state, money, dtf, timef, dayLabel, stageLabel, icon, toast, busy, modal,
    emptyState, errorState, skeleton, friendlyError } = CA;

  const ok = r => (r.status === "fulfilled" ? r.value : null);
  const DONE = ["done", "cancelled"];
  let uid = 0;
  let dealFilter = "all";

  /* ---------- small builders ---------- */
  const pageHead = (title, sub = "", actions = "") => h(`<div class="page-head"><div>
    <h1 class="page-title">${esc(title)}</h1>${sub ? `<p class="page-sub">${esc(sub)}</p>` : ""}</div>
    <div class="page-actions">${actions}</div></div>`);
  const bindActions = root => $$("[data-act]", root).forEach(b => { b.onclick = () => CA.actions[b.dataset.act](b); });
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;

  const STAGE_TONE = { negotiating: "info", confirmed: "info", product_received: "purple", content_due: "warning",
    posted: "success", payment_pending: "warning", done: "success", cancelled: "danger" };
  const stageBadge = s => `<span class="badge ${STAGE_TONE[s] ? "badge--" + STAGE_TONE[s] : ""}">${esc(stageLabel(s))}</span>`;
  const kindBadge = k => (k === "barter" ? '<span class="badge badge--purple">Barter</span>' : '<span class="badge badge--gold">Paid</span>');
  const CAT = { paid_collab: ["Paid collab", "gold"], barter_collab: ["Barter", "purple"], negotiation: ["Negotiation", "info"],
    payment: ["Payment", "success"], event_invite: ["Event", "info"] };
  const catBadge = c => { const [t, k] = CAT[c] || [c, ""]; return `<span class="badge ${k ? "badge--" + k : ""}">${esc(t)}</span>`; };
  const invBadge = s => {
    const map = { paid: ["Paid", "success"], draft: ["Draft", "info"], sent: ["Sent", "info"],
      partially_paid: ["Partial", "warning"], overdue: ["Overdue", "danger"], cancelled: ["Cancelled", ""] };
    const [t, k] = map[s] || ["Pending", "warning"];
    return `<span class="badge ${k ? "badge--" + k : ""}">${t}</span>`;
  };

  /* ======================================================================
     Quick actions (dialogs reuse existing endpoints, no new backend)
     ====================================================================== */
  function addDeal() {
    const stages = (state.stages.length ? state.stages : ["lead"]).filter(s => s !== "cancelled");
    modal({
      title: CA.t("add_deal"), submitLabel: CA.t("add_deal"),
      body: `<div class="form-grid">
        <div class="field full"><label class="label" for="d-brand">Brand</label><input class="input" id="d-brand" name="brand" required placeholder="e.g. Mamaearth"></div>
        <div class="field"><label class="label" for="d-kind">Type</label><select class="select" id="d-kind" name="kind"><option value="paid">Paid</option><option value="barter">Barter</option></select></div>
        <div class="field"><label class="label" for="d-value">Value (&#8377;)</label><input class="input" id="d-value" name="value_inr" type="number" min="0" step="1" placeholder="0"></div>
        <div class="field full"><label class="label" for="d-deliv">Deliverables</label><input class="input" id="d-deliv" name="deliverables" placeholder="${esc(CA.t("deliverables_hint"))}"></div>
        <div class="field"><label class="label" for="d-stage">Stage</label><select class="select" id="d-stage" name="status">${stages.map(s => `<option value="${esc(s)}">${esc(stageLabel(s))}</option>`).join("")}</select></div>
        <div class="field"><label class="label" for="d-due">Due date</label><input class="input" id="d-due" name="due_date" type="date"></div></div>`,
      onSubmit: async d => {
        const brand = (d.brand || "").trim();
        if (!brand) throw new Error("Please enter the brand name.");
        await api("/deals", { method: "POST", json: { brand, kind: d.kind, value_inr: Number(d.value_inr || 0),
          deliverables: d.deliverables || "", status: d.status || "lead", due_date: d.due_date || null } });
        toast("success", `${CA.cap(CA.t("deal"))} with ${brand} added`);
        CA.refreshView();
      },
    });
  }

  async function createInvoice() {
    let deals;
    try { deals = await api("/deals"); } catch (e) { toast("error", friendlyError(e, "We couldn't load your deals.")); return; }
    deals = deals.filter(d => d.status !== "cancelled");
    if (!deals.length) { toast("info", "Add a deal first, then you can create its invoice."); addDeal(); return; }
    modal({
      title: "Create invoice", submitLabel: "Create invoice",
      body: `<div class="field"><label class="label" for="i-deal">Deal</label><select class="select" id="i-deal" name="deal_id" required>
          ${deals.map(d => `<option value="${d.id}">#${d.id} ${esc(d.brand)}${d.value_inr ? " \u00B7 " + money(d.value_inr) : ""}</option>`).join("")}</select></div>
        <div class="field"><label class="label" for="i-amt">Amount (&#8377;)</label>
          <input class="input" id="i-amt" name="amount_inr" type="number" min="1" step="1" placeholder="Leave blank to use the deal value">
          <span class="hint">Needed only if the deal has no value yet.</span></div>`,
      onSubmit: async d => {
        const q = d.amount_inr ? `?amount_inr=${encodeURIComponent(d.amount_inr)}` : "";
        const r = await api(`/invoices/for-deal/${d.deal_id}${q}`, { method: "POST" });
        toast("success", `Invoice ${r.invoice.number} created`);
        CA.go("invoices");
      },
    });
  }

  function addEvent() {
    modal({
      title: CA.t("add_event"), submitLabel: CA.t("add_event"),
      body: `<div class="form-grid">
        <div class="field full"><label class="label" for="e-title">Title</label><input class="input" id="e-title" name="title" required placeholder="${esc(CA.t("event_hint"))}"></div>
        <div class="field"><label class="label" for="e-start">Starts</label><input class="input" id="e-start" name="start" type="datetime-local" required></div>
        <div class="field"><label class="label" for="e-end">Ends (optional)</label><input class="input" id="e-end" name="end" type="datetime-local"></div>
        <div class="field full"><label class="label" for="e-loc">Location</label><input class="input" id="e-loc" name="location" placeholder="Optional"></div></div>`,
      onSubmit: async d => {
        const title = (d.title || "").trim();
        if (!title) throw new Error("Please enter a title.");
        const r = await api("/events", { method: "POST", json: { title, start_at: d.start, end_at: d.end || null, location: d.location || "" } });
        if (r.conflicts && r.conflicts.length) toast("warning", `Added, but it clashes with ${r.conflicts.map(c => c.title).join(", ")}.`);
        else toast("success", r.google_synced ? "Event added to your calendar and Google Calendar" : "Event added to your calendar");
        if (r.google_error) toast("warning", "Google Calendar sync failed: " + r.google_error);
        CA.refreshView();
      },
    });
  }

  async function syncInbox(btn) {
    await busy(btn, "Checking your inbox...", async () => {
      try {
        const r = await api("/gmail/sync", { method: "POST" });
        toast("success", r.new ? `${plural(r.new, "new brand email")} found (checked ${r.fetched})` : `Checked ${r.fetched} emails. Nothing new.`);
        CA.refreshView();
      } catch (e) { toast("error", friendlyError(e, "We couldn't sync your Gmail right now.")); }
    });
  }

  async function checkGmail(btn) {
    let st;
    try { st = await api("/gmail/status"); } catch (e) { toast("error", friendlyError(e)); return; }
    if (!st.configured) { toast("warning", "Gmail isn't set up on this server yet. See the README."); return; }
    if (!st.connected) { toast("info", "Connect Gmail to find brand emails."); CA.go("inbox"); return; }
    await busy(btn, "Checking your inbox...", async () => {
      try {
        const r = await api("/gmail/sync", { method: "POST" });
        toast("success", r.new ? `${plural(r.new, "new brand email")} found (checked ${r.fetched})` : `Checked ${r.fetched} emails. Nothing new.`);
        CA.go("inbox");
      } catch (e) { toast("error", friendlyError(e, "We couldn't sync your Gmail right now.")); }
    });
  }

  CA.actions = { addDeal, createInvoice, addEvent, checkGmail, askAI: () => CA.chat.ask(), syncInbox };

  /* ======================================================================
     Dashboard
     ====================================================================== */
  function statCard({ ic, label, value, sub, route, key }) {
    const el = h(`<button class="card card--interactive stat ${key ? "stat--key" : ""}" type="button" aria-label="${esc(label)}: ${esc(value)}. Open ${esc(route)}">
      <span class="stat__top"><span>${esc(label)}</span><span class="stat__icon">${icon(ic)}</span></span>
      <span class="stat__value">${esc(value)}</span><span class="caption">${esc(sub)}</span></button>`);
    el.onclick = () => CA.go(route);
    return el;
  }

  async function dashboard(v, ctx) {
    if (!ctx.silent) v.replaceChildren(skeleton("dashboard"));
    const monthStart = new Date(); monthStart.setDate(1);
    const finQs = `?from_date=${monthStart.toISOString().slice(0, 10)}&to_date=${new Date().toISOString().slice(0, 10)}`;
    const batch = await Promise.allSettled([api("/deals"), api("/invoices/summary" + finQs), api("/events"), api("/gmail/status"),
      api("/agent/pending"), api("/calendar/suggestions")]);
    if (!ctx.alive()) return;
    const [deals, finSum, events, gst, pending, sugs] = batch.map(ok);
    let emails = null, fups = null;
    if (gst && gst.connected) {
      const second = (await Promise.allSettled([api("/gmail/emails"), api("/followups")])).map(ok);
      if (!ctx.alive()) return;
      [emails, fups] = second;
    }

    const now = new Date();
    const me = state.me;
    const name = ((me.name || me.email.split("@")[0]).trim().split(/\s+/)[0]) || "there";
    const greet = CA.timeGreet();
    const outstanding = finSum ? finSum.outstanding : null;
    const upcoming = events ? events.filter(e => new Date(e.end_at) >= now).sort((a, b) => new Date(a.start_at) - new Date(b.start_at)) : null;
    const week = upcoming ? upcoming.filter(e => new Date(e.start_at) < new Date(now.getTime() + 7 * 864e5)) : null;
    const active = deals ? deals.filter(d => !DONE.includes(d.status)) : null;
    const newEmails = emails ? emails.filter(e => e.status === "new") : null;
    const byId = Object.fromEntries((deals || []).map(d => [d.id, d]));
    const failed = batch.slice(0, 3).some(r => r.status === "rejected");

    /* metrics */
    const gmailSub = !gst ? "Couldn't load" : !gst.configured ? "Gmail not set up" : !gst.connected ? "Connect Gmail" : "to review";
    const metrics = h(`<section class="dash-metrics" aria-label="Key numbers"></section>`);
    metrics.append(
      statCard({ ic: "receipt", label: CA.ui("outstanding"), value: finSum ? money(finSum.outstanding) : "\u2014", key: true, route: "invoices",
        sub: finSum ? money(finSum.total_received) + " " + CA.ui("received") : CA.ui("couldnt_load") }),
      statCard({ ic: "mail", label: CA.ui("new_brand_emails"), value: newEmails ? String(newEmails.length) : "\u2014", route: "inbox", sub: gmailSub }),
      statCard({ ic: "calendar", label: CA.ui("upcoming_events"), value: week ? String(week.length) : "\u2014", route: "schedule", sub: week ? CA.ui("next_7_days") : CA.ui("couldnt_load") }),
      statCard({ ic: "briefcase", label: "Active " + CA.t("deals_lower"), value: active ? String(active.length) : "\u2014", route: "deals",
        sub: active ? `${active.filter(d => d.kind === "barter").length} barter \u00B7 ${active.filter(d => d.kind !== "barter").length} paid` : "Couldn't load" }),
    );

    /* quick actions */
    const quick = h(`<section class="quick" style="margin-top:var(--space-4)" aria-label="Quick actions">
      <button class="quick__btn" type="button" data-act="addDeal"><span class="qi">${icon("plus")}</span>${esc(CA.t("add_deal"))}</button>
      <button class="quick__btn" type="button" data-act="createInvoice"><span class="qi">${icon("receipt")}</span>${esc(CA.ui("create_invoice"))}</button>
      <button class="quick__btn" type="button" data-act="checkGmail"><span class="qi">${icon("mail")}</span>${esc(CA.ui("check_gmail"))}</button>
      <button class="quick__btn" type="button" data-act="addEvent"><span class="qi">${icon("calendar")}</span>${esc(CA.t("add_event"))}</button>
      <button class="quick__btn" type="button" data-act="askAI"><span class="qi">${icon("sparkle")}</span>${esc(CA.ui("ask_ai"))}</button></section>`);
    bindActions(quick);

    /* needs attention (real data only) */
    const attn = [];
    if (finSum && finSum.overdue_count > 0) {
      attn.push({ tone: "danger", ic: "alert", text: `${plural(finSum.overdue_count, "overdue invoice")}`, sub: money(finSum.overdue_amount) + " outstanding", route: "invoices" });
    } else if (outstanding > 0) {
      attn.push({ tone: "warning", ic: "alert", text: "Payments outstanding", sub: money(outstanding) + " to collect", route: "invoices" });
    }
    const today0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    (deals || []).filter(d => d.due_date && ["confirmed", "product_received", "content_due"].includes(d.status)).forEach(d => {
      const days = Math.round((new Date(d.due_date + "T00:00:00") - today0) / 864e5);
      if (days <= 3) attn.push({ tone: days < 0 ? "danger" : "warning", ic: "clock", route: "deals", sub: d.deliverables || d.title || "",
        text: `${d.brand} deliverable ${days < 0 ? "is overdue" : days === 0 ? "is due today" : "due in " + plural(days, "day")}` });
    });
    if (newEmails && newEmails.length) attn.push({ tone: "info", ic: "mail", text: `${plural(newEmails.length, "brand email")} need review`, sub: "", route: "inbox" });
    if (fups && fups.length) attn.push({ tone: "info", ic: "send2", text: `${plural(fups.length, "email thread")} need a reply or follow-up`, sub: "", route: "inbox" });
    if (pending && pending.length) attn.push({ tone: "info", ic: "check", text: `${plural(pending.length, "action")} waiting for your approval`, sub: "", route: "assistant" });
    if (sugs && sugs.length) attn.push({ tone: "info", ic: "calendar", text: `${plural(sugs.length, "date")} found in emails`, sub: "Add them to your calendar", route: "schedule" });
    if (gst && gst.configured && !gst.connected) attn.push({ tone: "info", ic: "mail", text: "Connect Gmail to catch brand emails automatically", sub: "", route: "inbox" });

    const attnCard = h(`<section class="card"><div class="card__head"><h2 class="card__title">${esc(CA.ui("needs_attention"))}</h2></div><div class="stack" id="attn"></div></section>`);
    const attnBox = $("#attn", attnCard);
    if (attn.length) attn.slice(0, 6).forEach(a => {
      const b = h(`<button class="attn" type="button"><span class="attn__icon attn__icon--${a.tone}">${icon(a.ic)}</span>
        <span class="attn__text">${esc(a.text)}${a.sub ? `<span class="attn__sub">${esc(a.sub)}</span>` : ""}</span>${icon("chevron")}</button>`);
      b.onclick = () => CA.go(a.route);
      attnBox.append(b);
    });
    else attnBox.append(emptyState({ icon: "check", title: "You're all caught up", text: "Nothing needs your attention right now." }));

    /* upcoming */
    const upCard = h(`<section class="card"><div class="card__head"><h2 class="card__title">${esc(CA.ui("upcoming"))}</h2>
      <button class="btn btn--ghost btn--sm" type="button" data-go="schedule">View schedule</button></div><div class="timeline" id="up"></div></section>`);
    $("[data-go]", upCard).onclick = () => CA.go("schedule");
    const upBox = $("#up", upCard);
    if (upcoming && upcoming.length) upcoming.slice(0, 5).forEach(e => upBox.append(h(`<div class="timeline__item">
      <div class="timeline__time">${esc(timef(e.start_at))}<span class="timeline__day">${esc(dayLabel(e.start_at))}</span></div>
      <div><div class="row__title">${esc(e.title)}</div>${e.location ? `<div class="caption">${esc(e.location)}</div>` : ""}</div></div>`)));
    else upBox.append(emptyState({ icon: "calendar", title: "Nothing scheduled", text: "Add a shoot or call to see it here.", actionLabel: "Add event", onAction: addEvent }));

    /* AI card */
    const dueSoon = (active || []).filter(d => d.due_date && Math.round((new Date(d.due_date + "T00:00:00") - today0) / 864e5) <= 7 && Math.round((new Date(d.due_date + "T00:00:00") - today0) / 864e5) >= 0).length;
    const summary = [week ? `You have ${plural(week.length, "upcoming event")} this week` : null,
      dueSoon ? `${dueSoon} ${dueSoon === 1 ? CA.t("due_label").replace(/s(?= due$)/, "") : CA.t("due_label")} soon` : null,
      outstanding != null && outstanding > 0 ? `${money(outstanding)} outstanding on invoices` : null].filter(Boolean).join(" and ");
    const ai = h(`<section class="ai-card" aria-label="AI assistant"><div class="ai-card__title">${icon("sparkle")}${esc(CA.ui("ai_assistant"))}</div>
      <p><strong>${esc(greet)}, ${esc(name)}.</strong> ${esc(summary ? summary + "." : "How can I help you today?")}</p>
      <div><button class="btn btn--accent" type="button" data-act="askAI">${esc(CA.ui("ask_assistant"))}</button></div>
      <div class="cluster" id="aichips"></div></section>`);
    bindActions(ai);
    CA.chips().forEach(t => {
      const c = h(`<button class="chip" type="button"></button>`); c.textContent = t; c.onclick = () => CA.chat.ask(t);
      $("#aichips", ai).append(c);
    });

    /* active deals */
    const dealsCard = h(`<section class="card"><div class="card__head"><h2 class="card__title">Active ${esc(CA.t("deals_lower"))}</h2>
      <button class="btn btn--ghost btn--sm" type="button">All ${esc(CA.t("deals_lower"))}</button></div><div class="list" id="dl"></div></section>`);
    $("button", dealsCard).onclick = () => CA.go("deals");
    const dl = $("#dl", dealsCard);
    if (active && active.length) active.slice(0, 4).forEach(d => dl.append(h(`<div class="row"><div class="row__top">
      <span class="row__title">${esc(d.brand)}</span><span class="deal__value">${d.value_inr ? money(d.value_inr) : ""}</span></div>
      <div class="cluster">${kindBadge(d.kind)}${stageBadge(d.status)}</div></div>`)));
    else dl.append(emptyState({ icon: "briefcase", title: `No active ${CA.t("deals_lower")}`, text: `Add your first ${CA.t("deal")} to start tracking it.`, actionLabel: CA.t("add_deal"), onAction: addDeal }));

    const head = h(`<div class="page-head"><div><h1 class="page-title">${esc(greet)}, ${esc(name)}</h1>
      <p class="page-sub">${esc(CA.ui("dash_sub"))}</p></div></div>`);
    const left = h(`<div class="stack"></div>`); left.append(attnCard, upCard);
    const right = h(`<div class="stack"></div>`); right.append(ai, dealsCard);
    const grid = h(`<div class="dash-grid"></div>`); grid.append(left, right);
    v.replaceChildren(head, metrics, quick, grid);
    const authFailed = batch.some(r => r.status === "rejected" && r.reason && r.reason.status === 401);
    if (authFailed && state.tok) { CA.logout({ sessionExpired: true }); return; }
    if (failed) toast("warning", CA.ui("dash_load_warn"));
  }

  /* ======================================================================
     Deals
     ====================================================================== */
  function dealCard(d) {
    const stages = state.stages.filter(s => s !== "cancelled");
    const i = stages.indexOf(d.status);
    const track = stages.map((s, n) => `<button type="button" title="${esc(stageLabel(s))}" data-id="${d.id}" data-s="${esc(s)}"
      aria-label="Move ${esc(d.brand)} to ${esc(stageLabel(s))}" class="${n < i ? "done" : n === i ? "now" : ""}"></button>`).join("");
    const meta = [d.deliverables || d.title, d.due_date ? "due " + d.due_date : ""].filter(Boolean).join(" \u00B7 ");
    return h(`<article class="card deal"><div class="row__top"><span class="deal__brand">${esc(d.brand)}</span>
      <span class="deal__value">${d.value_inr ? money(d.value_inr) : ""}</span></div>
      <div class="cluster">${kindBadge(d.kind)}${stageBadge(d.status)}<span class="caption">#${d.id}</span></div>
      ${meta ? `<div class="caption">${esc(meta)}</div>` : ""}
      <div class="stages" role="group" aria-label="Deal stage">${track}</div></article>`);
  }

  async function deals(v, ctx) {
    const tab = new URLSearchParams(location.hash.split("?")[1] || "").get("tab");
    if (tab === "roi" && CA.campaignRoiPage) {
      return CA.campaignRoiPage.render(v, ctx);
    }
    const head = pageHead(CA.t("deals"), CA.t("pages_sub"),
      `<button class="btn btn--secondary" type="button" id="go-roi">Campaign ROI</button>
      <button class="btn btn--accent" type="button" data-act="addDeal">${icon("plus")}${esc(CA.t("add_deal"))}</button>`);
    bindActions(head);
    const roiBtn = $("#go-roi", head);
    if (roiBtn) roiBtn.onclick = () => { location.hash = "#/deals?tab=roi"; CA.refreshView(); };
    if (!ctx.silent) v.replaceChildren(head, skeleton("cards"));
    const list = await api("/deals");
    if (!ctx.alive()) return;
    const body = h(`<div class="stack"></div>`);
    const draw = () => {
      body.replaceChildren();
      if (!list.length) {
        body.append(h(`<div class="card"></div>`));
        body.firstChild.append(emptyState({ icon: "briefcase", title: `No ${CA.t("deals_lower")} yet`, text: `Add your first ${CA.t("deal")}, or tell the assistant about it in chat.`, actionLabel: CA.t("add_deal"), onAction: addDeal, actionClass: "btn--accent" }));
        return;
      }
      const shown = list.filter(d => dealFilter === "all" || (dealFilter === "active" && !DONE.includes(d.status)) || d.kind === dealFilter);
      const filters = h(`<div class="filters" role="group" aria-label="Filter deals">${[["all", "All"], ["active", "Active"], ["paid", "Paid"], ["barter", "Barter"]]
        .map(([k, l]) => `<button type="button" data-f="${k}" aria-pressed="${dealFilter === k}">${l}</button>`).join("")}</div>`);
      $$("button", filters).forEach(b => b.onclick = () => { dealFilter = b.dataset.f; draw(); });
      body.append(filters);
      if (!shown.length) { body.append(h(`<div class="card"></div>`)); body.lastChild.append(emptyState({ icon: "briefcase", title: "No deals in this filter", text: "Try a different filter." })); return; }
      const grid = h(`<div class="deal-grid"></div>`);
      shown.forEach(d => grid.append(dealCard(d)));
      $$(".stages button", grid).forEach(b => b.onclick = async () => {
        const wrap = b.closest(".stages"); $$("button", wrap).forEach(x => x.disabled = true);
        const deal = list.find(x => x.id === Number(b.dataset.id));
        try {
          await api(`/deals/${b.dataset.id}`, { method: "PATCH", json: { status: b.dataset.s } });
          toast("success", `${deal ? deal.brand : "Deal"} moved to ${stageLabel(b.dataset.s)}`);
          CA.refreshView();
        } catch (e) { $$("button", wrap).forEach(x => x.disabled = false); toast("error", friendlyError(e, "We couldn't update that deal.")); }
      });
      body.append(grid);
    };
    draw();
    v.replaceChildren(head, body);
  }

  /* ======================================================================
     Inbox (Gmail brand emails + follow-ups)
     ====================================================================== */
  function openEditor(el, text, save, push) {
    const id = "ed" + (++uid);
    el.innerHTML = `<label class="sr-only" for="${id}">Draft</label><textarea class="textarea" id="${id}">${esc(text)}</textarea>
      <div class="row__actions"><button class="btn btn--secondary btn--sm" type="button" data-s="save">Save edits</button>
      <button class="btn btn--primary btn--sm" type="button" data-s="push">${icon("mail")}Save to Gmail drafts</button></div>
      <p class="hint">Nothing is sent. The draft appears in your Gmail Drafts folder for you to review and send.</p>`;
    const area = $("textarea", el);
    $('[data-s="save"]', el).onclick = e => busy(e.currentTarget, "Saving...", async () => {
      try { await save(area.value); toast("success", "Draft saved"); } catch (err) { toast("error", friendlyError(err)); }
    });
    $('[data-s="push"]', el).onclick = e => busy(e.currentTarget, "Saving to Gmail...", async () => {
      try { await save(area.value); await push(); toast("success", "Saved to your Gmail drafts. Open Gmail to review and send."); }
      catch (err) { toast("error", friendlyError(err, "We couldn't save the draft to Gmail.")); }
    });
    area.focus();
  }

  function mailCard(m) {
    const amt = m.amount_inr ? ` \u00B7 <span title="Unverified until you confirm">${money(m.amount_inr)} (AI)</span>` : "";
    const intelHint = m.intelligence_version ? `<span class="badge">Intel v${m.intelligence_version}</span>` : "";
    const el = h(`<div class="row"><div class="row__top"><span class="cluster">${catBadge(m.category)}${intelHint}<span class="row__title">${esc(m.brand || m.sender_name)}</span></span>
      <span class="caption">#${m.id}</span></div>
      <div>${esc(m.summary || m.subject)}</div>
      <div class="caption">${esc(m.sender_name)} &lt;${esc(m.sender_email)}&gt;${amt}${m.deliverables ? " \u00B7 " + esc(m.deliverables) : ""}</div>
      <p class="hint" style="margin:4px 0 0">${esc(m.unverified_notice || "AI-extracted values are unverified until you confirm.")}</p>
      <div class="row__actions">
        <button class="btn btn--secondary btn--sm" type="button" data-a="draft">${m.draft_reply ? "Edit reply" : "Draft reply"}</button>
        <button class="btn btn--ghost btn--sm" type="button" data-a="intel">Details</button>
        ${m.deal_id ? `<span class="badge badge--success">In deals as #${m.deal_id}</span>` : `<button class="btn btn--secondary btn--sm" type="button" data-a="deal">Add to deals</button>`}
        <button class="btn btn--ghost btn--sm" type="button" data-a="dismiss">Dismiss</button></div>
      <div class="draft" hidden></div></div>`);
    const ed = $(".draft", el);
    $$("[data-a]", el).forEach(b => b.onclick = () => busy(b, b.dataset.a === "draft" ? "Writing..." : "Working...", async () => {
      try {
        if (b.dataset.a === "deal") {
          if (!(await CA.confirm({ title: "Create deal from email?", text: "Budget and deliverables may be AI-extracted and unverified. Confirm only after you review the original email.", submitLabel: "Create deal" }))) return;
          const r = await api(`/gmail/emails/${m.id}/to-deal`, { method: "POST", json: { confirm: true, apply_intelligence: true } });
          toast("success", `Added to deals as #${r.deal_id} (${r.brand})`);
          CA.refreshView();
        } else if (b.dataset.a === "intel") {
          const d = await api(`/gmail/emails/${m.id}`);
          const i = d.intelligence || {};
          modal({
            title: `Email #${m.id} intelligence`,
            submitLabel: "Close",
            body: `<p class="hint">${esc(d.unverified_notice || "")}</p>
              <p><strong>Kind:</strong> ${esc(i.collab_kind || "?")} · <strong>Budget:</strong> ${i.budget ? money(i.budget.amount_inr || 0) : "—"}</p>
              <p><strong>Deliverables:</strong> ${esc((i.deliverables || []).map(x => x.text).join(", ") || m.deliverables)}</p>
              <p><strong>Payment terms:</strong> ${esc((i.payment_terms || {}).text || "—")}</p>
              <p><strong>Follow-up:</strong> ${esc((i.follow_up || {}).reason || "—")}</p>`,
            onSubmit: () => {},
          });
        }
        else if (b.dataset.a === "dismiss") { await api(`/gmail/emails/${m.id}/dismiss`, { method: "POST" }); toast("info", "Email dismissed"); CA.refreshView(); }
        else {
          const d = await api(`/gmail/emails/${m.id}`);
          const text = d.draft_reply || (await api(`/gmail/emails/${m.id}/draft`, { method: "POST" })).draft_reply;
          ed.hidden = false;
          openEditor(ed, text, t => api(`/gmail/emails/${m.id}/draft`, { method: "PUT", json: { draft_reply: t } }),
            () => api(`/gmail/emails/${m.id}/push-draft`, { method: "POST" }));
        }
      } catch (err) { toast("error", friendlyError(err)); }
    }));
    return el;
  }

  async function loadFollowups(card) {
    const box = $(".fu-body", card);
    let fu;
    try { fu = await api("/followups"); } catch (e) { box.replaceChildren(errorState({ title: "Couldn't load follow-ups", text: friendlyError(e), onRetry: () => loadFollowups(card) })); return; }
    $(".fu-count", card).textContent = fu.length ? ` (${fu.length})` : "";
    box.replaceChildren();
    if (!fu.length) { box.append(emptyState({ icon: "check", title: "Nothing waiting", text: "Check follow-ups to scan your threads for replies you owe or brands that have gone quiet." })); return; }
    const list = h(`<div class="list"></div>`);
    fu.forEach(f => {
      const row = h(`<div class="row"><div class="row__top"><span class="cluster">
        <span class="badge ${f.state === "needs_reply" ? "badge--warning" : "badge--info"}">${f.state === "needs_reply" ? "You owe a reply" : "Waiting on brand"}</span>
        <span class="row__title">${esc(f.brand)}</span></span><span class="caption">${plural(f.days_waiting, "day")}</span></div>
        <div class="caption">${esc(f.subject)}</div>
        <div class="row__actions"><button class="btn btn--secondary btn--sm" type="button" data-fa="draft">${f.state === "needs_reply" ? "Draft reply" : "Draft nudge"}</button>
        <button class="btn btn--ghost btn--sm" type="button" data-fa="snooze">Snooze 2 days</button>
        <button class="btn btn--ghost btn--sm" type="button" data-fa="done">Done</button></div><div class="draft" hidden></div></div>`);
      const ed = $(".draft", row);
      $$("[data-fa]", row).forEach(b => b.onclick = () => busy(b, "Working...", async () => {
        try {
          if (b.dataset.fa === "snooze") { await api(`/followups/${f.id}/snooze?days=2`, { method: "POST" }); toast("info", "Snoozed for 2 days"); loadFollowups(card); }
          else if (b.dataset.fa === "done") { await api(`/followups/${f.id}/resolve`, { method: "POST" }); toast("success", "Marked as done"); loadFollowups(card); }
          else if (f.state === "needs_reply") {
            const d = await api(`/gmail/emails/${f.email_id}`);
            const text = d.draft_reply || (await api(`/gmail/emails/${f.email_id}/draft`, { method: "POST" })).draft_reply;
            ed.hidden = false;
            openEditor(ed, text, t => api(`/gmail/emails/${f.email_id}/draft`, { method: "PUT", json: { draft_reply: t } }),
              () => api(`/gmail/emails/${f.email_id}/push-draft`, { method: "POST" }));
          } else {
            const text = (await api(`/followups/${f.id}/nudge`, { method: "POST" })).draft_reply;
            ed.hidden = false;
            openEditor(ed, text, t => api(`/followups/${f.id}/nudge`, { method: "PUT", json: { draft_reply: t } }),
              () => api(`/followups/${f.id}/nudge/push`, { method: "POST" }));
          }
        } catch (err) { toast("error", friendlyError(err)); }
      }));
      list.append(row);
    });
    box.append(list);
  }

  async function inbox(v, ctx) {
    if (!ctx.silent) v.replaceChildren(pageHead("Inbox", "Brand emails and follow-ups, sorted for you."), skeleton());
    const st = await api("/gmail/status");
    if (!ctx.alive()) return;
    const plain = pageHead("Inbox", "Brand emails and follow-ups, sorted for you.");

    if (!st.configured) {
      const c = h(`<div class="card"></div>`);
      c.append(emptyState({ icon: "mail", title: "Gmail isn't set up yet", text: "Add your Google credentials to the server's .env file and restart. The README explains each step." }));
      v.replaceChildren(plain, c); return;
    }
    if (!st.connected) {
      const c = h(`<div class="card"></div>`);
      c.append(emptyState({ icon: "mail", title: "Connect Gmail", actionLabel: "Connect Gmail", actionClass: "btn--accent",
        text: "Creator Assistant finds brand emails, sorts them and drafts replies. It reads mail and saves drafts, it never sends anything, and only brand-related emails are kept. You can disconnect and delete the data any time.",
        onAction: btn => busy(btn, "Opening Google...", async () => {
          try { location.href = (await api("/gmail/connect")).url; } catch (e) { toast("error", friendlyError(e, "We couldn't start the Gmail connection.")); }
        }) }));
      v.replaceChildren(plain, c); return;
    }

    const synced = st.last_sync_at ? ` \u00B7 last checked ${dtf(st.last_sync_at + "Z")}` : "";
    const head = pageHead("Inbox", `Connected as ${st.email}${synced}`,
      `<button class="btn btn--accent" type="button" data-act="syncInbox">${icon("refresh")}Check for new emails</button>
       <button class="btn btn--secondary" type="button" id="clean" title="Remove job alerts and notifications">Clean up</button>
       <button class="btn btn--danger-outline" type="button" id="disc">Disconnect</button>`);
    bindActions(head);
    $("#clean", head).onclick = e => busy(e.currentTarget, "Cleaning up...", async () => {
      try { const r = await api("/gmail/cleanup", { method: "POST" }); toast("success", r.removed ? `Removed ${plural(r.removed, "unrelated email")}` : "Nothing to clean up"); CA.refreshView(); }
      catch (err) { toast("error", friendlyError(err)); }
    });
    $("#disc", head).onclick = async () => {
      if (!(await CA.confirm({ title: "Disconnect Gmail?", text: "This revokes access and deletes the brand emails saved in this app. Your Gmail itself is not changed.", submitLabel: "Disconnect", submitClass: "btn--danger" }))) return;
      try { await api("/gmail/disconnect", { method: "DELETE" }); toast("success", "Gmail disconnected"); CA.refreshView(); }
      catch (err) { toast("error", friendlyError(err)); }
    };

    const fuCard = h(`<section class="card"><div class="card__head"><h2 class="card__title">Follow-ups<span class="fu-count"></span></h2>
      <button class="btn btn--secondary btn--sm" type="button" id="fchk">Check follow-ups</button></div><div class="fu-body"></div></section>`);
    fuCard.querySelector(".fu-body").append(skeleton());
    $("#fchk", fuCard).onclick = e => busy(e.currentTarget, "Checking threads...", async () => {
      try { const r = await api("/followups/refresh", { method: "POST" }); toast("success", `Checked ${plural(r.checked, "thread")}: ${r.active} need attention`); await loadFollowups(fuCard); }
      catch (err) { toast("error", friendlyError(err, "We couldn't check your follow-ups.")); }
    });

    const mailCardBox = h(`<section class="card"><div class="card__head"><h2 class="card__title">Brand emails</h2></div>
      <div class="cluster" style="padding:0 12px 12px">
        <input class="input" id="mail-q" placeholder="Search brand or subject" style="max-width:200px">
        <select class="select" id="mail-cat"><option value="">All categories</option>
          <option value="paid_collab">Paid collab</option><option value="barter_collab">Barter</option>
          <option value="negotiation">Negotiation</option><option value="payment">Payment</option>
          <option value="event_invite">Event</option></select>
        <label class="chk"><input type="checkbox" id="mail-inq"> Inquiries only</label>
        <button class="btn btn--secondary btn--sm" type="button" id="mail-filt">Apply</button>
      </div><div class="list" id="mails"></div></section>`);
    const mails = $("#mails", mailCardBox);
    const loadMails = async () => {
      const p = new URLSearchParams();
      const qq = $("#mail-q", mailCardBox).value.trim();
      const cat = $("#mail-cat", mailCardBox).value;
      if (qq) p.set("q", qq);
      if (cat) p.set("category", cat);
      if ($("#mail-inq", mailCardBox).checked) p.set("inquiry_only", "true");
      return api("/gmail/emails?" + p.toString());
    };
  $("#mail-filt", mailCardBox).onclick = async () => {
      try {
        const list = await loadMails();
        mails.replaceChildren();
        if (!list.length) mails.append(emptyState({ icon: "mail", title: "No emails match", text: "Try another filter." }));
        else list.forEach(m => mails.append(mailCard(m)));
      } catch (e) { toast("error", friendlyError(e)); }
    };
    let list;
    try { list = await loadMails(); } catch (e) { list = null; mails.replaceChildren(errorState({ title: "Couldn't load your emails", text: friendlyError(e, "We couldn't load your brand emails."), onRetry: () => CA.refreshView() })); }
    if (!ctx.alive()) return;
    if (list && !list.length) mails.replaceChildren(emptyState({ icon: "mail", title: "No brand emails yet", actionLabel: "Check for new emails", actionClass: "btn--accent",
      text: "Check your inbox and Creator Assistant will pick out collaboration, barter and payment emails.", onAction: btn => syncInbox(btn) }));
    else if (list) { mails.replaceChildren(); list.forEach(m => mails.append(mailCard(m))); }

    const body = h(`<div class="stack"></div>`); body.append(fuCard, mailCardBox);
    v.replaceChildren(head, body);
    loadFollowups(fuCard);
  }

  /* ======================================================================
     Schedule (events + Google Calendar + suggestions from emails)
     ====================================================================== */
  async function schedule(v, ctx) {
    const head = pageHead("Schedule", "Shoots, calls and deadlines in one place.",
      `<button class="btn btn--accent" type="button" data-act="addEvent">${icon("plus")}Add event</button>`);
    bindActions(head);
    if (!ctx.silent) v.replaceChildren(head, skeleton());
    const [st, ev, sug] = await Promise.all([api("/calendar/status"), api("/events"), api("/calendar/suggestions")]);
    if (!ctx.alive()) return;

    const gcal = h(`<section class="card"></section>`);
    if (!st.configured) gcal.append(h(`<p class="muted">Google isn't set up on this server yet. See the README to enable Calendar sync.</p>`));
    else if (!st.granted) {
      gcal.append(h(`<div class="spread"><div><div class="card__title">Google Calendar</div>
        <p class="muted">Connect it to see your Google events here and add shoots to your calendar automatically.</p></div>
        <button class="btn btn--accent" type="button" id="gcal">Connect Google Calendar</button></div>`));
      if (st.last_error) gcal.append(h(`<p class="form-error" style="margin-top:var(--space-3)">${esc(st.last_error)}</p>`));
      $("#gcal", gcal).onclick = e => busy(e.currentTarget, "Opening Google...", async () => {
        try { location.href = (await api("/gmail/connect?calendar=true")).url; } catch (err) { toast("error", friendlyError(err, "We couldn't start the Google connection.")); }
      });
    } else {
      gcal.append(h(`<div class="spread"><div class="cluster"><span class="dot dot--on"></span><div><div class="card__title">Google Calendar connected</div>
        <div class="caption">${st.last_pull_at ? "Last synced " + esc(dtf(st.last_pull_at + "Z")) : "Not synced yet"}</div></div></div>
        <button class="btn btn--secondary" type="button" id="gsync">${icon("refresh")}Sync now</button></div>`));
      if (st.last_error) gcal.append(h(`<p class="form-error" style="margin-top:var(--space-3)">${esc(st.last_error)}</p>`));
      $("#gsync", gcal).onclick = e => busy(e.currentTarget, "Syncing calendar...", async () => {
        try { const r = await api("/calendar/sync", { method: "POST" }); toast("success", `Calendar synced: ${r.pushed} sent, ${r.created} imported, ${r.updated} updated, ${r.removed} removed`); CA.refreshView(); }
        catch (err) { toast("error", friendlyError(err, "Calendar sync failed.")); CA.refreshView(); }
      });
    }

    const parts = [head, gcal];

    if (sug.length) {
      const card = h(`<section class="card"><div class="card__head"><h2 class="card__title">Found in your emails</h2></div><div class="list"></div></section>`);
      sug.forEach(s => {
        const row = h(`<div class="row"><div class="row__top"><span class="row__title">${esc(s.title)}</span><span class="caption">${esc(dtf(s.start_at))}</span></div>
          <div class="caption">${esc(s.brand)} \u00B7 ${esc(s.subject)}</div>
          <div class="row__actions"><button class="btn btn--accent btn--sm" type="button" data-sa>Add to calendar</button>
          <button class="btn btn--ghost btn--sm" type="button" data-sd>Dismiss</button></div></div>`);
        $("[data-sa]", row).onclick = e => busy(e.currentTarget, "Adding...", async () => {
          try {
            const r = await api(`/calendar/suggestions/${s.id}/accept`, { method: "POST" });
            if (r.conflicts.length) toast("warning", `Added, but it clashes with ${r.conflicts.map(c => c.title).join(", ")}.`);
            else toast("success", r.google_synced ? `"${r.event.title}" added to your calendar and Google Calendar` : `"${r.event.title}" added to your calendar`);
            if (r.google_error) toast("warning", "Google Calendar sync failed: " + r.google_error);
            CA.refreshView();
          } catch (err) { toast("error", friendlyError(err)); }
        });
        $("[data-sd]", row).onclick = e => busy(e.currentTarget, "Dismissing...", async () => {
          try { await api(`/calendar/suggestions/${s.id}/dismiss`, { method: "POST" }); toast("info", "Suggestion dismissed"); CA.refreshView(); }
          catch (err) { toast("error", friendlyError(err)); }
        });
        $(".list", card).append(row);
      });
      parts.push(card);
    }

    const now = new Date();
    const sorted = [...ev].sort((a, b) => new Date(a.start_at) - new Date(b.start_at));
    const upcoming = sorted.filter(e => new Date(e.end_at) >= now), past = sorted.filter(e => new Date(e.end_at) < now);
    const evCard = h(`<section class="card"><div class="card__head"><h2 class="card__title">Upcoming</h2></div><div id="evs"></div></section>`);
    const evs = $("#evs", evCard);
    if (!upcoming.length) evs.append(emptyState({ icon: "calendar", title: "Nothing scheduled", text: "Add a shoot, call or deadline. Dates found in brand emails will show up here too.", actionLabel: "Add event", onAction: addEvent, actionClass: "btn--accent" }));
    else {
      let last = "";
      upcoming.forEach(e => {
        const lbl = dayLabel(e.start_at);
        if (lbl !== last) { evs.append(h(`<div class="day-label">${esc(lbl)}</div>`)); last = lbl; }
        evs.append(h(`<div class="timeline__item" style="margin-bottom:var(--space-3)"><div class="timeline__time">${esc(timef(e.start_at))}</div>
          <div><div class="row__title">${esc(e.title)}</div>${e.location ? `<div class="caption">${esc(e.location)}</div>` : ""}</div></div>`));
      });
    }
    if (past.length) evs.append(h(`<details class="past"><summary>${plural(past.length, "past event")}</summary>${past.slice(-10).reverse().map(e =>
      `<div class="caption" style="padding:4px 0">${esc(dtf(e.start_at))} \u00B7 ${esc(e.title)}</div>`).join("")}</details>`));
    parts.push(evCard);

    const wrap = h(`<div class="stack"></div>`); wrap.append(...parts.slice(1));
    v.replaceChildren(head, wrap);
  }

  async function invoices(v, ctx) {
    if (CA.invoicesPage) return CA.invoicesPage.render(v, ctx);
    v.replaceChildren(emptyState({ icon: "receipt", title: "Invoices unavailable", text: "Reload the page." }));
  }

  /* ======================================================================
     Brands
     ====================================================================== */
  async function brands(v, ctx) {
    if (CA.brandCrmPage) return CA.brandCrmPage.render(v, ctx);
    const head = pageHead("Brands", "Brands that fit your niche, with a pitch ready to send.");
    v.replaceChildren(head, emptyState({ icon: "store", title: "Brands unavailable", text: "Reload the page." }));
  }

  CA.views = { dashboard, deals, inbox, schedule, invoices, brands };
})();
