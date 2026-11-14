/* Brand Collaboration CRM (Phase 10B). Reminders only — no auto-send. */
(function () {
  "use strict";
  const { $, $$, esc, h, api, state, icon, toast, busy, modal, confirm, emptyState, skeleton, friendlyError, stageLabel } = CA;
  const STAGE_TONE = { negotiating: "info", confirmed: "info", product_received: "purple", content_due: "warning",
    posted: "success", payment_pending: "warning", done: "success", cancelled: "danger", lead: "info" };
  const stageBadge = s => `<span class="badge ${STAGE_TONE[s] ? "badge--" + STAGE_TONE[s] : ""}">${esc(stageLabel(s))}</span>`;

  function hashParams() {
    return new URLSearchParams(location.hash.split("?")[1] || "");
  }

  function setHash(params) {
    const p = params instanceof URLSearchParams ? params : hashParams();
    location.hash = `#/brands?${p.toString()}`;
  }

  function tabsEl(active) {
    const bar = h(`<div class="filters crm-tabs" role="tablist"></div>`);
    [["discover", CA.ui("crm_discover")], ["crm", CA.ui("crm_mine")]].forEach(([k, label]) => {
      const b = h(`<button type="button" role="tab" aria-selected="${active === k}">${esc(label)}</button>`);
      b.dataset.tab = k;
      b.onclick = () => { const p = hashParams(); p.set("tab", k); p.delete("id"); setHash(p); CA.refreshView(); };
      bar.append(b);
    });
    return bar;
  }

  async function renderDiscover(host, ctx) {
    const q = hashParams().get("q") || "";
    const tools = h(`<div class="cluster" style="margin-bottom:12px">
      <input class="input" id="crm-dq" placeholder="${esc(CA.ui("crm_search"))}" value="${esc(q)}">
      <button class="btn btn--secondary" type="button" id="crm-dgo">${esc(CA.ui("crm_apply"))}</button>
    </div>`);
    host.append(tools);
    $("#crm-dgo", host).onclick = () => {
      const p = hashParams(); p.set("tab", "discover");
      const v = $("#crm-dq").value.trim(); if (v) p.set("q", v); else p.delete("q");
      setHash(p); CA.refreshView();
    };
    const list = await api(`/brands-crm/discover?${new URLSearchParams({ q, limit: "24" }).toString()}`);
    if (!ctx.alive()) return;
    if (!list.length) {
      host.append(emptyState({ icon: "store", title: CA.ui("crm_disc_empty"), text: CA.ui("crm_disc_empty_sub") }));
      return;
    }
    if (!state.me.niche) host.append(h(`<p class="hint">${esc(CA.ui("crm_niche_tip"))}</p>`));
    const grid = h(`<div class="brand-grid"></div>`);
    list.forEach(b => {
      const c = h(`<article class="card stack"><div><div class="deal__brand">${esc(b.name)}</div>
        <div class="cluster" style="margin-top:6px"><span class="badge">${esc(b.category)}</span>
        ${b.match ? `<span class="badge badge--gold">${b.match} match</span>` : ""}
        ${b.in_crm ? `<span class="badge">${esc(CA.ui("crm_in_crm"))}</span>` : ""}</div></div>
        <div class="cluster">
          <button class="btn btn--secondary btn--sm" type="button" data-act="pitch">${esc(CA.ui("crm_pitch"))}</button>
          ${b.in_crm && b.brand_record_id ? `<button class="btn btn--ghost btn--sm" type="button" data-act="open">${esc(CA.ui("crm_open"))}</button>` : `<button class="btn btn--ghost btn--sm" type="button" data-act="add">${esc(CA.ui("crm_add"))}</button>`}
        </div></article>`);
      $("button[data-act=pitch]", c).onclick = e => busy(e.currentTarget, "…", async () => {
        try {
          if (CA.pitchStudio) await CA.pitchStudio.open(b.name, b.category);
          else toast("error", "Pitch Studio did not load.");
        } catch (err) { toast("error", friendlyError(err)); }
      });
      const openId = async (id) => { const p = hashParams(); p.set("tab", "crm"); p.set("id", String(id)); setHash(p); CA.refreshView(); };
      $("button[data-act=open]", c)?.addEventListener("click", () => openId(b.brand_record_id));
      $("button[data-act=add]", c)?.addEventListener("click", e => busy(e.currentTarget, "…", async () => {
        try {
          const row = await api("/brands-crm", { method: "POST", json: { display_name: b.name } });
          await openId(row.id);
        } catch (err) { toast("error", friendlyError(err)); }
      }));
      grid.append(c);
    });
    host.append(grid, h(`<div id="pitchStudioHost"></div>`));
    const st = hashParams().get("studio") || new URLSearchParams(location.search).get("studio");
    if (st && CA.pitchStudio) setTimeout(() => CA.pitchStudio.open(st), 200);
  }

  function kanbanBoard(kanban) {
    const stages = (state.stages.length ? state.stages : Object.keys(kanban || {})).filter(s => s !== "cancelled");
    const board = h(`<div class="crm-kanban"></div>`);
    stages.forEach(st => {
      const col = h(`<div class="crm-kanban__col"><div class="caption" style="font-weight:600">${esc(stageLabel(st))}</div>
        <div class="stack crm-kanban__list"></div></div>`);
      const list = $(".crm-kanban__list", col);
      (kanban[st] || []).forEach(d => {
        list.append(h(`<div class="card deal" style="padding:10px"><div class="deal__brand">${esc(d.brand)}</div>
          <div class="caption">#${d.id} · ${esc(d.deliverables || "")}</div></div>`));
      });
      if (!list.children.length) list.append(h(`<p class="caption" style="opacity:.6">—</p>`));
      board.append(col);
    });
    return board;
  }

  async function renderCrmList(host, ctx) {
    const p = hashParams();
    const q = p.get("q") || "";
    const sort = p.get("sort") || "updated";
    const stage = p.get("stage") || "";
    const follow = p.get("follow") === "1";
    const bar = h(`<div class="form-grid" style="margin-bottom:12px">
      <motion class="field"><label class="label">${esc(CA.ui("crm_search"))}</label>
        <input class="input" id="crm-q" value="${esc(q)}"></motion>
      <motion class="field"><label class="label">${esc(CA.ui("crm_sort"))}</label>
        <select class="select" id="crm-sort">
          <option value="updated">${esc(CA.ui("crm_sort_updated"))}</option>
          <option value="name">${esc(CA.ui("crm_sort_name"))}</option>
          <option value="deals">${esc(CA.ui("crm_sort_deals"))}</option>
          <option value="follow_up">${esc(CA.ui("crm_sort_follow"))}</option>
        </select></motion>
      <motion class="field"><label class="label">${esc(CA.ui("crm_stage"))}</label>
        <select class="select" id="crm-stage"><option value="">—</option>
          ${(state.stages || []).map(s => `<option value="${esc(s)}">${esc(stageLabel(s))}</option>`).join("")}
        </select></motion>
      <motion class="field" style="align-self:end">
        <label class="chk"><input type="checkbox" id="crm-fu" ${follow ? "checked" : ""}> ${esc(CA.ui("crm_due_only"))}</label>
        <button class="btn btn--secondary" type="button" id="crm-apply">${esc(CA.ui("crm_apply"))}</button>
        <button class="btn btn--ghost btn--sm" type="button" id="crm-sync">${esc(CA.ui("crm_sync"))}</button>
      </motion></div>`.replace(/motion/g, "div"));
    $("#crm-sort", bar).value = sort;
    $("#crm-stage", bar).value = stage;
    host.append(bar);
    $("#crm-apply", bar).onclick = () => {
      const np = hashParams(); np.set("tab", "crm");
      const qq = $("#crm-q").value.trim(); if (qq) np.set("q", qq); else np.delete("q");
      np.set("sort", $("#crm-sort").value);
      const st = $("#crm-stage").value; if (st) np.set("stage", st); else np.delete("stage");
      if ($("#crm-fu").checked) np.set("follow", "1"); else np.delete("follow");
      setHash(np); CA.refreshView();
    };
    $("#crm-sync", bar).onclick = e => busy(e.currentTarget, "…", async () => {
      try { await api("/brands-crm/sync", { method: "POST" }); toast("success", CA.ui("crm_synced")); CA.refreshView(); }
      catch (err) { toast("error", friendlyError(err)); }
    });

    const [rows, suggestions] = await Promise.all([
      api(`/brands-crm?${new URLSearchParams({ q, sort, stage, follow_up: follow ? "true" : "false" })}`),
      api("/brands-crm/suggestions").catch(() => ({ brands: [] })),
    ]);
    if (!ctx.alive()) return;
    if (suggestions.brands && suggestions.brands.length) {
      const sug = h(`<section class="card stack"><h2 class="card__title">${esc(CA.ui("crm_suggestions"))}</h2>
        <div class="list" id="crm-sug"></div></section>`);
      suggestions.brands.slice(0, 5).forEach(s => {
        const row = h(`<button type="button" class="row" style="text-align:left;width:100%">
          <div class="row__title">${esc(s.display_name)}</div>
          <div class="caption">${esc(s.reasons.join(" · "))}</div></button>`);
        row.onclick = () => { const np = hashParams(); np.set("tab", "crm"); np.set("id", String(s.brand_record_id)); setHash(np); CA.refreshView(); };
        $("#crm-sug", sug).append(row);
      });
      host.append(sug);
    }
    if (!rows.length) {
      host.append(emptyState({ icon: "briefcase", title: CA.ui("crm_empty"), text: CA.ui("crm_empty_sub") }));
      return;
    }
    const grid = h(`<div class="deal-grid" id="crm-list"></div>`);
    rows.forEach(b => {
      const c = h(`<article class="card deal" role="button" tabindex="0">
        <div class="row__top"><span class="deal__brand">${esc(b.display_name)}</span>
        <span class="caption">${b.deal_count} deals</span></div>
        <div class="cluster">${stageBadge(b.pipeline_stage)}
        ${b.next_follow_up ? `<span class="badge">${esc(CA.ui("crm_next"))}: ${esc(b.next_follow_up)}</span>` : ""}</div>
        <p class="caption">${esc(b.category || "")}</p></article>`);
      const open = () => { const np = hashParams(); np.set("tab", "crm"); np.set("id", String(b.id)); setHash(np); CA.refreshView(); };
      c.onclick = open;
      c.onkeydown = ev => { if (ev.key === "Enter") open(); };
      grid.append(c);
    });
    host.append(grid);
  }

  async function renderDetail(host, id, ctx) {
    const detail = await api(`/brands-crm/${id}`);
    const timeline = await api(`/brands-crm/${id}/timeline`).catch(() => []);
    if (!ctx.alive()) return;
    const back = h(`<button class="btn btn--ghost btn--sm" type="button">${icon("arrow-left")}${esc(CA.ui("crm_back"))}</button>`);
    back.onclick = () => { const p = hashParams(); p.set("tab", "crm"); p.delete("id"); setHash(p); CA.refreshView(); };
    const head = h(`<div class="page-head"><div>
      <h1 class="page-title">${esc(detail.display_name)}</h1>
      <p class="page-sub">${esc(detail.category || "")} ${detail.website ? "· " + esc(detail.website) : ""}</p>
    </div><div class="page-actions cluster" id="crm-dact"></div></div>`);
    const act = $("#crm-dact", head);
    act.append(back);
    act.append(h(`<button class="btn btn--secondary" type="button" id="crm-pitch">${esc(CA.ui("crm_pitch"))}</button>`));
    act.append(h(`<button class="btn btn--ghost" type="button" id="crm-sum">${esc(CA.ui("crm_ai_summary"))}</button>`));
    host.append(head);
    $("#crm-pitch", host).onclick = () => CA.pitchStudio && CA.pitchStudio.open(detail.display_name, detail.category);
    $("#crm-sum", host).onclick = e => busy(e.currentTarget, "…", async () => {
      try {
        const r = await api(`/brands-crm/${id}/summary`);
        modal({ title: CA.ui("crm_ai_summary"), body: `<pre class="pre-wrap" style="white-space:pre-wrap">${esc(r.summary)}</pre>`, submitLabel: CA.ui("crm_close"), onSubmit: () => {} });
      } catch (err) { toast("error", friendlyError(err)); }
    });

    const prefs = h(`<section class="card stack"><h2 class="card__title">${esc(CA.ui("crm_prefs"))}</h2>
      <textarea class="textarea" id="crm-rel" rows="3" placeholder="${esc(CA.ui("crm_rel_ph"))}">${esc(detail.relationship_summary || "")}</textarea>
      <textarea class="textarea" id="crm-pref" rows="3" placeholder="${esc(CA.ui("crm_pref_ph"))}">${esc(JSON.stringify(detail.preferences || {}, null, 0))}</textarea>
      <div class="cluster"><label class="label">${esc(CA.ui("crm_next"))}</label>
        <input class="input" type="date" id="crm-nfu" value="${esc(detail.next_follow_up || "")}"></div>
      <button class="btn btn--secondary btn--sm" type="button" id="crm-save">${esc(CA.ui("crm_save"))}</button></section>`);
    $("#crm-save", prefs).onclick = e => busy(e.currentTarget, "…", async () => {
      let preferences = detail.preferences || {};
      try { preferences = JSON.parse($("#crm-pref").value || "{}"); } catch (z) { toast("error", CA.ui("crm_bad_json")); return; }
      try {
        await api(`/brands-crm/${id}`, { method: "PATCH", json: {
          relationship_summary: $("#crm-rel").value,
          preferences,
          next_follow_up: $("#crm-nfu").value || null,
        }});
        toast("success", CA.ui("crm_saved"));
      } catch (err) { toast("error", friendlyError(err)); }
    });
    host.append(prefs);

    host.append(h(`<section class="card"><h2 class="card__title">${esc(CA.ui("crm_pipeline"))}</h2></section>`));
    host.lastChild.append(kanbanBoard(detail.kanban));

    const contacts = h(`<section class="card stack"><div class="card__head"><h2 class="card__title">${esc(CA.ui("crm_contacts"))}</h2>
      <button class="btn btn--ghost btn--sm" type="button" id="crm-addc">${icon("plus")}</button></div><div id="crm-cs" class="list"></div></section>`);
    detail.contacts.forEach(c => {
      $("#crm-cs", contacts).append(h(`<div class="row"><div class="row__title">${esc(c.name)} ${c.email_verified ? "✓" : ""}</div>
        <div class="caption">${esc(c.role)} · ${esc(c.email)}</div></div>`));
    });
    if (!detail.contacts.length) $("#crm-cs", contacts).append(h(`<p class="caption">${esc(CA.ui("crm_no_contacts"))}</p>`));
    $("#crm-addc", contacts).onclick = () => modal({
      title: CA.ui("crm_add_contact"),
      body: `<div class="form-grid">
        <div class="field"><label class="label">Name</label><input class="input" id="cc-n"></div>
        <div class="field"><label class="label">Email</label><input class="input" id="cc-e"></div>
        <div class="field"><label class="label">Role</label><input class="input" id="cc-r"></div></div>`,
      submitLabel: CA.ui("crm_save"),
      onSubmit: async () => {
        await api(`/brands-crm/${id}/contacts`, { method: "POST", json: {
          name: $("#cc-n").value, email: $("#cc-e").value, role: $("#cc-r").value,
        }});
        CA.refreshView();
      },
    });
    host.append(contacts);

    const notesSec = h(`<section class="card stack"><h2 class="card__title">${esc(CA.ui("crm_notes"))}</h2>
      <div class="cluster"><button class="btn btn--ghost btn--sm" type="button" data-k="general">${esc(CA.ui("crm_note_gen"))}</button>
      <button class="btn btn--ghost btn--sm" type="button" data-k="negotiation">${esc(CA.ui("crm_note_neg"))}</button></div>
      <div id="crm-notes" class="list"></div></section>`);
    detail.notes.forEach(n => {
      $("#crm-notes", notesSec).append(h(`<div class="row"><span class="badge">${esc(n.kind)}</span>
        <p>${esc(n.body)}</p><span class="caption">${esc(n.created_at.slice(0, 10))}</span></div>`));
    });
    $$("button[data-k]", notesSec).forEach(b => b.onclick = () => modal({
      title: b.dataset.k === "negotiation" ? CA.ui("crm_note_neg") : CA.ui("crm_note_gen"),
      body: `<textarea class="textarea" id="crm-nb" rows="5"></textarea>`,
      submitLabel: CA.ui("crm_save"),
      onSubmit: async () => {
        await api(`/brands-crm/${id}/notes`, { method: "POST", json: { body: $("#crm-nb").value, kind: b.dataset.k } });
        CA.refreshView();
      },
    }));
    host.append(notesSec);

    const fuSec = h(`<section class="card stack"><h2 class="card__title">${esc(CA.ui("crm_followups"))}</h2>
      <button class="btn btn--secondary btn--sm" type="button" id="crm-sch">${esc(CA.ui("crm_schedule"))}</button>
      <div id="crm-fus" class="list"></div></section>`);
    detail.scheduled_follow_ups.forEach(f => {
      const row = h(`<div class="row cluster"><motionDiv><div class="row__title">${esc(f.due_date)}</div>
        <div class="caption">${esc(f.notes)}</div></motionDiv>
        <button class="btn btn--ghost btn--sm" type="button">${esc(CA.ui("crm_done"))}</button></motionDiv>`.replace(/motionDiv/g, "div"));
      $("button", row).onclick = async () => {
        await api(`/brands-crm/follow-ups/${f.id}/complete`, { method: "POST" });
        CA.refreshView();
      };
      $("#crm-fus", fuSec).append(row);
    });
    $("#crm-sch", fuSec).onclick = () => modal({
      title: CA.ui("crm_schedule"),
      body: `<div class="form-grid">
        <motion class="field"><label class="label">${esc(CA.ui("crm_due"))}</label><input type="date" class="input" id="fu-d"></motion>
        <motion class="field full"><label class="label">Notes</label><textarea class="textarea" id="fu-n"></textarea></motion>
        </div>`.replace(/motion/g, "div"),
      submitLabel: CA.ui("crm_save"),
      onSubmit: async () => {
        await api(`/brands-crm/${id}/follow-ups`, { method: "POST", json: { due_date: $("#fu-d").value, notes: $("#fu-n").value } });
        CA.refreshView();
      },
    });
    host.append(fuSec);

    const hist = h(`<section class="card stack"><h2 class="card__title">${esc(CA.ui("crm_history"))}</h2>
      <motion class="list" id="crm-tl"></motion></section>`.replace(/motion/g, "div"));
    timeline.forEach(ev => {
      $("#crm-tl", hist).append(h(`<button type="button" class="row" style="width:100%;text-align:left" data-type="${esc(ev.type)}" data-ref="${ev.ref_id}">
        <motion class="row__top"><span class="row__title">${esc(ev.title)}</span>
        <span class="caption">${esc(ev.at.slice(0, 10))}</span></motion>
        <motion class="caption">${esc(ev.detail || "")}</motion></button>`.replace(/motion/g, "div")));
    });
    $$("#crm-tl button", hist).forEach(b => b.onclick = () => {
      const t = b.dataset.type, r = b.dataset.ref;
      if (t === "deal") CA.go("deals");
      else if (t === "email") CA.go("inbox");
      else if (t === "pitch") CA.go("brands", `studio=${encodeURIComponent(detail.display_name)}`);
    });
    host.append(hist);

    if (detail.deals && detail.deals.length) {
      const deals = h(`<section class="card stack"><h2 class="card__title">${esc(CA.ui("crm_deals"))}</h2><motion class="list"></motion></section>`.replace(/motion/g, "div"));
      detail.deals.forEach(d => {
        $("div", deals).append(h(`<div class="row"><div class="row__title">#${d.id} ${stageBadge(d.status)}</div>
          <div class="caption">${esc(d.deliverables || "")} ${d.due_date ? "· due " + esc(d.due_date) : ""}</div></div>`));
      });
      host.append(deals);
    }
    host.append(h(`<div id="pitchStudioHost"></div>`));
  }

  async function render(v, ctx) {
    const p = hashParams();
    const tab = p.get("tab") || "discover";
    const id = p.get("id");
    const head = h(`<div class="page-head"><motion><h1 class="page-title">${esc(CA.ui("crm_page_title"))}</h1>
      <p class="page-sub">${esc(CA.ui("crm_page_sub"))}</p></motion></div>`.replace(/motion/g, "div"));
    if (!ctx.silent) v.replaceChildren(head, skeleton());
    const body = h(`<motion class="stack"></motion>`.replace(/motion/g, "div"));
    if (!id) body.append(tabsEl(tab));
    const inner = h(`<motion class="stack"></motion>`.replace(/motion/g, "div"));
    body.append(inner);
    try {
      if (id) await renderDetail(inner, id, ctx);
      else if (tab === "crm") await renderCrmList(inner, ctx);
      else await renderDiscover(inner, ctx);
    } catch (err) {
      inner.replaceChildren(emptyState({ icon: "alert", title: CA.ui("couldnt_load"), text: friendlyError(err) }));
    }
    if (!ctx.alive()) return;
    v.replaceChildren(head, body);
  }

  CA.brandCrmPage = { render };
})();
