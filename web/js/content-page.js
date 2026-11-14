/* Content Planner (Phase 8). Drafts only — no auto-publish. */
(function () {
  "use strict";
  const { $, $$, esc, h, api, state, icon, toast, busy, modal, confirm, emptyState, skeleton, friendlyError } = CA;

  const STATUSES = ["idea", "draft", "ready", "scheduled", "published"];
  const FORMATS = ["reel", "youtube", "caption", "shorts", "carousel"];

  function statusBadge(s) {
    return `<span class="status-chip">${esc(s)}</span>`;
  }

  function renderBodyPreview(body) {
    if (!body || !Object.keys(body).length) return "";
    const parts = [];
    if (body.hook) parts.push(`Hook: ${body.hook}`);
    if (body.script) parts.push(body.script);
    if (body.sections) body.sections.forEach(sec => parts.push(`${sec.title}: ${sec.text}`));
    return parts.join("\n\n").slice(0, 2000);
  }

  async function openEditor(item, drafts) {
    const latest = drafts[0];
    const body = latest?.body_json || {};
    modal({
      title: CA.ui("ct_edit") + " · " + item.title,
      submitLabel: CA.ui("ct_save_draft"),
      body: `<p class="content-banner">${esc(CA.ui("ct_publish_note"))}</p>
        <div class="form-grid content-editor">
          <div class="field full"><label class="label">${CA.ui("ct_status")}</label>
            <select class="select" id="ct-st" name="status">${STATUSES.map(s =>
              `<option value="${s}" ${item.status === s ? "selected" : ""}>${s}</option>`).join("")}
            </select></div>
          <div class="field full"><label class="label">${CA.ui("ct_title")}</label>
            <input class="input" id="ct-title" value="${esc(item.title)}"></div>
          <div class="field full"><label class="label">${CA.ui("ct_script")}</label>
            <textarea class="textarea" id="ct-script">${esc(renderBodyPreview(body))}</textarea></div>
          <div class="field full"><label class="label">${CA.ui("ct_caption")}</label>
            <textarea class="textarea" id="ct-cap">${esc(latest?.caption || "")}</textarea></div>
          <div class="field full"><label class="label">${CA.ui("ct_hashtags")}</label>
            <input class="input" id="ct-tags" value="${esc(latest?.hashtags || "")}"></div>
        </div>`,
      onSubmit: async () => {
        const title = $("#ct-title").value.trim();
        const status = $("#ct-st").value;
        await api(`/content/plan/${item.id}`, { method: "PATCH", json: { title, status } });
        const script = $("#ct-script").value;
        await api(`/content/plan/${item.id}/drafts`, {
          method: "POST",
          json: { body_json: { script }, caption: $("#ct-cap").value, hashtags: $("#ct-tags").value },
        });
        toast("success", CA.ui("ct_saved"));
        CA.refreshView();
      },
    });
  }

  function genModal(deals) {
    modal({
      title: CA.ui("ct_generate"),
      submitLabel: CA.ui("ct_generate_btn"),
      body: `<div class="form-grid">
        <div class="field"><label class="label">${CA.ui("ct_format")}</label>
          <select class="select" id="g-fmt">${FORMATS.map(f => `<option value="${f}">${f}</option>`).join("")}</select></div>
        <div class="field"><label class="label">${CA.ui("ct_platform")}</label>
          <select class="select" id="g-plat"><option value="instagram">Instagram</option>
            <option value="youtube">YouTube</option><option value="tiktok">TikTok</option></select></div>
        <div class="field full"><label class="label">${CA.ui("ct_topic")}</label>
          <input class="input" id="g-topic" placeholder="e.g. monsoon skincare routine"></div>
        <div class="field"><label class="label">${CA.ui("ct_deal")}</label>
          <select class="select" id="g-deal"><option value="">—</option>
            ${deals.map(d => `<option value="${d.id}">#${d.id} ${esc(d.brand)}</option>`).join("")}</select></div>
      </div>`,
      onSubmit: async () => {
        const json = {
          format: $("#g-fmt").value,
          platform: $("#g-plat").value,
          topic: $("#g-topic").value,
          deal_id: $("#g-deal").value ? Number($("#g-deal").value) : null,
        };
        await api("/content/generate/script", { method: "POST", json });
        toast("success", CA.ui("ct_generated"));
        CA.refreshView();
      },
    });
  }

  async function renderContent(v, ctx) {
    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    const dealFilter = params.get("deal_id") || "";
    const head = h(`<div class="page-head"><div>
      <h1 class="page-title">${esc(CA.ui("ct_title"))}</h1>
      <p class="page-sub">${esc(CA.ui("ct_sub"))}</p></div>
      <div class="page-actions">
        <button class="btn btn--secondary" type="button" id="ct-ideas">${icon("sparkle")}${CA.ui("ct_ideas")}</button>
        <button class="btn btn--accent" type="button" id="ct-gen">${icon("plus")}${CA.ui("ct_generate")}</button>
      </div></div>`);
    if (!ctx.silent) v.replaceChildren(head, skeleton());

    const qsp = new URLSearchParams();
    if (dealFilter) qsp.set("deal_id", dealFilter);
    const q = params.get("q") || "";
    const stParam = params.get("status") || "";
    const planQs = new URLSearchParams();
    if (dealFilter) planQs.set("deal_id", dealFilter);
    if (q) planQs.set("q", q);
    if (stParam) planQs.set("status", stParam);

    const [meta, tips, items, cal, deals] = await Promise.allSettled([
      api("/content/meta"),
      api("/content/suggestions"),
      api("/content/plan" + (planQs.toString() ? "?" + planQs : "")),
      api("/content/calendar"),
      api("/deals").catch(() => []),
    ]);
    if (!ctx.alive()) return;
    if (items.status === "rejected") throw items.reason;
    const list = items.value;
    const suggestions = tips.status === "fulfilled" ? tips.value.tips : [];

    const banner = h(`<p class="content-banner" role="note">${esc(CA.ui("ct_publish_note"))}</p>`);

    const filters = h(`<div class="content-filters card">
      <div class="field"><label class="label" for="ct-q">${CA.ui("ct_search")}</label>
        <input class="input" id="ct-q" value="${esc(q)}" placeholder="title, notes…"></div>
      <div class="field"><label class="label" for="ct-filter-st">${CA.ui("ct_status")}</label>
        <select class="select" id="ct-filter-st"><option value="">All</option>
          ${STATUSES.map(s => `<option value="${s}" ${stParam === s ? "selected" : ""}>${s}</option>`).join("")}</select></div>
      <button class="btn btn--primary" type="button" id="ct-apply">${CA.ui("ct_apply")}</button>
    </div>`);

    const sugCard = h(`<section class="card"><h2 class="card__title">${CA.ui("ct_suggestions")}</h2>
      <ul class="stack"></ul></section>`);
    const ul = $("ul", sugCard);
    if (!suggestions.length) ul.append(h(`<li class="caption">${CA.ui("ct_no_suggestions")}</li>`));
    suggestions.forEach(t => ul.append(h(`<li>${esc(t)}</li>`)));

    const calItems = cal.status === "fulfilled" ? cal.value.items || [] : [];
    const calCard = h(`<section class="card"><h2 class="card__title">${CA.ui("ct_calendar")}</h2>
      <p class="caption">${esc((cal.status === "fulfilled" && cal.value.note) || "")}</p><div class="list"></div></section>`);
    if (!calItems.length) $(".list", calCard).append(h(`<p class="caption">${CA.ui("ct_cal_empty")}</p>`));
    calItems.forEach(it => {
      $(".list", calCard).append(h(`<div class="row"><div class="row__top">
        <span class="row__title">${esc(it.title)}</span>${statusBadge(it.status)}</div>
        <div class="caption">${esc(it.platform)} · ${it.scheduled_at ? it.scheduled_at.replace("T", " ").slice(0, 16) : CA.ui("ct_unscheduled")}</div></div>`));
    });

    const card = h(`<section class="card"><div class="list" id="ct-list"></div></section>`);
    const filtered = list;
    if (!filtered.length) {
      $("#ct-list", card).append(emptyState({ icon: "sparkle", title: CA.ui("ct_empty"), text: CA.ui("ct_empty_sub") }));
    }

    v.replaceChildren(head, banner, filters, sugCard, calCard, card);

    for (const it of filtered) {
      let drafts = [];
      try { drafts = await api(`/content/plan/${it.id}/drafts`); } catch (e) { /* ignore */ }
      if (!ctx.alive()) return;
      const row = h(`<div class="row" data-id="${it.id}"><div class="row__top">
        <span class="cluster"><span class="row__title">${esc(it.title)}</span>${statusBadge(it.status)}</span>
        <span class="caption">${esc(it.platform)} · ${esc(it.format)}</span></div>
        <div class="caption">${it.deal_id ? "Deal #" + it.deal_id + " · " : ""}${esc(it.notes || "")}</div>
        <div class="row__actions"></div></div>`);
      const acts = $(".row__actions", row);
      const add = (label, fn) => { const b = h(`<button class="btn btn--secondary btn--sm" type="button">${label}</button>`); b.onclick = () => busy(b, "…", fn); acts.append(b); };
      add(CA.ui("ct_edit"), () => openEditor(it, drafts));
      if (drafts[0]) {
        add(CA.ui("ct_copy"), async () => {
          const t = [drafts[0].caption, drafts[0].hashtags, renderBodyPreview(drafts[0].body_json)].filter(Boolean).join("\n\n");
          await navigator.clipboard.writeText(t);
          toast("success", CA.ui("ct_copied"));
        });
        add(CA.ui("ct_export"), async () => {
          await api("/auth/me");
          const r = await fetch(`/content/drafts/${drafts[0].id}/export.txt`, { headers: { Authorization: "Bearer " + state.tok.access_token } });
          const blob = await r.blob();
          const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `content-${it.id}.txt`;
          document.body.append(a); a.click(); a.remove();
        });
        add(CA.ui("ct_repurpose"), () => modal({
          title: CA.ui("ct_repurpose"),
          submitLabel: CA.ui("ct_generate_btn"),
          body: `<div class="field"><label class="label">Target</label>
            <select class="select" id="rp-fmt"><option value="youtube">YouTube</option><option value="reel">Reel</option>
            <option value="caption">Caption</option></select></div>`,
          onSubmit: async () => {
            await api("/content/repurpose", { method: "POST", json: {
              draft_id: drafts[0].id, target_format: $("#rp-fmt").value,
              target_platform: $("#rp-fmt").value === "youtube" ? "youtube" : "instagram",
            }});
            toast("success", CA.ui("ct_generated"));
            CA.refreshView();
          },
        }));
      }
      const del = h(`<button class="btn btn--ghost btn--sm" type="button">${CA.ui("ct_delete")}</button>`);
      del.onclick = async () => {
        if (!(await confirm({ title: CA.ui("ct_delete"), text: it.title, submitLabel: CA.ui("ct_delete"), submitClass: "btn--danger" }))) return;
        await api(`/content/plan/${it.id}`, { method: "DELETE" });
        toast("success", CA.ui("ct_deleted"));
        CA.refreshView();
      };
      acts.append(del);
      $("#ct-list", card).append(row);
    }

    $("#ct-apply", filters).onclick = () => {
      const qq = $("#ct-q").value.trim();
      const st = $("#ct-filter-st").value;
      const d = dealFilter ? `deal_id=${dealFilter}&` : "";
      let hash = `#/content?${d}q=${encodeURIComponent(qq)}`;
      if (st) hash += `&status=${st}`;
      location.hash = hash;
    };
    $("#ct-gen", head).onclick = () => genModal(deals.status === "fulfilled" ? deals.value : []);
    $("#ct-ideas", head).onclick = () => busy($("#ct-ideas", head), "…", async () => {
      await api("/content/generate/ideas", { method: "POST", json: { platform: "instagram", count: 5 } });
      toast("success", CA.ui("ct_ideas_done"));
      CA.refreshView();
    });
  }

  CA.views.content = renderContent;
})();
