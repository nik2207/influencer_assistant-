/* Media Kit & Rate Card (Phase 9). */
(function () {
  "use strict";
  const { $, $$, esc, h, api, state, icon, toast, busy, confirm, skeleton, friendlyError } = CA;

  const DELIV = ["reel", "post", "story", "video", "integration", "other"];
  const TPLS = ["classic", "minimal", "bold"];

  function money(n, cur) {
    const sym = { INR: "\u20B9", USD: "$", EUR: "\u20AC", GBP: "\u00A3" }[cur] || cur + " ";
    return sym + Number(n || 0).toLocaleString("en-IN");
  }

  function renderPreview(p) {
    const cr = p.creator || {};
    const el = h(`<motion-dummy></motion-dummy>`);
    el.innerHTML = `<div class="mk-preview">
      <h2>${esc(cr.headline || cr.name)}</h2>
      <p class="muted">${esc(cr.niche || "")} · ${esc(cr.creator_type || "")}${cr.city ? " · " + esc(cr.city) : ""}</p>
      <p>${esc(cr.intro || cr.bio || "")}</p>
      <h3>Platforms</h3>
      <ul>${(p.platforms || []).map(pl => `<li>${esc(pl.label)} ${esc(pl.handle || "")} — ${(pl.followers || 0).toLocaleString("en-IN")} <span class="muted">(profile)</span>
        ${(pl.metrics || []).map(m => `<br><span class="muted">${esc(m.metric)}: ${m.value.toLocaleString("en-IN")} [${esc(m.source)}]</span>`).join("")}</li>`).join("") || "<li class='muted'>Add platforms in Profile</li>"}</ul>
      ${p.rates?.length ? `<h3>Rate card</h3><ul>${p.rates.map(r => `<li>${esc(r.title || r.deliverable)}: ${money(r.price, r.currency)}</li>`).join("")}</ul>` : ""}
      ${p.portfolio?.length ? `<h3>Collaborations</h3><ul>${p.portfolio.map(x => `<li>${esc(x.brand)} — ${esc(x.summary || x.deliverables)}</li>`).join("")}</ul>` : ""}
      ${p.samples?.length ? `<h3>Samples</h3><ul>${p.samples.map(s => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a></li>`).join("")}</ul>` : ""}
      ${p.contact?.email || p.contact?.phone ? `<h3>Contact</h3><p>${esc(p.contact.email || "")} ${p.contact.phone ? " · " + esc(p.contact.phone) : ""}</p>` : ""}
      <p class="caption">${esc(p.disclaimer || "")}</p></div>`;
    el.firstChild.className = "mk-preview";
    return el.firstChild;
  }

  async function loadAvatar(target) {
    try {
      const r = await fetch("/media-kit/avatar", { headers: { Authorization: "Bearer " + state.tok.access_token } });
      if (!r.ok) return;
      const img = h(`<img class="mk-avatar" alt="">`);
      img.src = URL.createObjectURL(await r.blob());
      target.prepend(img);
    } catch (e) { /* no avatar */ }
  }

  async function renderMediaKit(v, ctx) {
    const head = h(`<div class="page-head"><div>
      <h1 class="page-title">${esc(CA.ui("mk_title"))}</h1>
      <p class="page-sub">${esc(CA.ui("mk_sub"))}</p></div>
      <div class="page-actions">
        <button class="btn btn--secondary" type="button" id="mk-pdf">${icon("download")}${CA.ui("mk_pdf")}</button>
        <button class="btn btn--accent" type="button" id="mk-save">${icon("check")}${CA.ui("mk_save")}</button>
      </div></div>`);
    if (!ctx.silent) v.replaceChildren(head, skeleton());

    const [preview, deals, meta] = await Promise.all([
      api("/media-kit"),
      api("/deals").catch(() => []),
      api("/media-kit/meta"),
    ]);
    if (!ctx.alive()) return;

    const layout = h(`<div class="mk-layout">
      <motion-edit class="stack"></motion-edit>
      <div id="mk-prev-host"></div>
    </div>`);
    layout.querySelector("motion-edit").outerHTML = '<div class="stack" id="mk-edit"></div>';
    const edit = $("#mk-edit", layout);

    const settings = h(`<section class="card"><h2 class="card__title">${CA.ui("mk_settings")}</h2>
      <div class="form-grid">
        <div class="field full"><label class="label">${CA.ui("mk_headline")}</label>
          <input class="input" id="mk-head" value="${esc(preview.creator.headline || "")}"></div>
        <div class="field full"><label class="label">${CA.ui("mk_intro")}</label>
          <textarea class="textarea" id="mk-intro" rows="4">${esc(preview.creator.intro || "")}</textarea></div>
        <div class="field"><label class="label">${CA.ui("mk_template")}</label>
          <select class="select" id="mk-tpl">${TPLS.map(t => `<option value="${t}" ${preview.settings.pdf_template === t ? "selected" : ""}>${t}</option>`).join("")}</select></div>
        <div class="field"><label class="label">${CA.ui("mk_avatar")}</label>
          <input type="file" id="mk-av" accept="image/jpeg,image/png,image/webp"></div>
        <label class="field"><input type="checkbox" id="mk-rates" ${preview.settings.show_rates ? "checked" : ""}> ${CA.ui("mk_show_rates")}</label>
        <label class="field"><input type="checkbox" id="mk-met" ${preview.settings.show_metrics ? "checked" : ""}> ${CA.ui("mk_show_metrics")}</label>
        <label class="field"><input type="checkbox" id="mk-em" ${preview.settings.show_contact_email ? "checked" : ""}> ${CA.ui("mk_show_email")}</label>
        <label class="field"><input type="checkbox" id="mk-ph" ${preview.settings.show_phone ? "checked" : ""}> ${CA.ui("mk_show_phone")}</label>
      </div></section>`);

    const rates = h(`<section class="card"><h2 class="card__title">${CA.ui("mk_rates")}</h2>
      <p class="caption">${CA.ui("mk_rates_hint")}</p><div class="stack" id="mk-rate-rows"></div>
      <button class="btn btn--ghost btn--sm" type="button" id="mk-rate-add">${icon("plus")}${CA.ui("mk_add_rate")}</button></section>`);
    const rateBox = $("#mk-rate-rows", rates);
    const rateLines = preview.rates?.length ? preview.rates : [
      { deliverable: "reel", title: "Instagram Reel", price: 0, currency: preview.settings.currency || "INR", notes: "" },
      { deliverable: "post", title: "Feed post", price: 0, currency: preview.settings.currency || "INR", notes: "" },
      { deliverable: "story", title: "Story set", price: 0, currency: preview.settings.currency || "INR", notes: "" },
      { deliverable: "video", title: "YouTube video", price: 0, currency: preview.settings.currency || "INR", notes: "" },
    ];
    const addRateRow = (r = { deliverable: "reel", title: "", price: 0, currency: "INR", notes: "" }) => {
      const row = h(`<div class="mk-rate-row">
        <select class="select" data-d>${DELIV.map(d => `<option value="${d}" ${r.deliverable === d ? "selected" : ""}>${d}</option>`).join("")}</select>
        <input class="input" data-t value="${esc(r.title)}" placeholder="Title">
        <input class="input" data-p type="number" min="0" step="1" value="${r.price || 0}">
        <input class="input" data-c value="${esc(r.currency || "INR")}" maxlength="3">
      </div>`);
      rateBox.append(row);
    };
    rateLines.forEach(addRateRow);

    const port = h(`<section class="card"><h2 class="card__title">${CA.ui("mk_portfolio")}</h2>
      <div class="field"><label class="label">${CA.ui("mk_deal")}</label>
        <select class="select" id="mk-deal"><option value="">—</option>
          ${deals.map(d => `<option value="${d.id}">#${d.id} ${esc(d.brand)}</option>`).join("")}</select></div>
      <input class="input" id="mk-sum" placeholder="${CA.ui("mk_summary")}">
      <button class="btn btn--secondary btn--sm" type="button" id="mk-port-add">${CA.ui("mk_add")}</button>
      <ul id="mk-port-list" class="stack"></ul></section>`);
    const portList = $("#mk-port-list", port);
    (preview.portfolio || []).forEach(p => {
      portList.append(h(`<li data-deal="${p.deal_id}">${esc(p.brand)} — ${esc(p.summary || p.deliverables || "")}</li>`));
    });

    const samples = h(`<section class="card"><h2 class="card__title">${CA.ui("mk_samples") || "Content samples"}</h2>
      <motion class="form-grid"></motion><ul id="mk-sam-list" class="stack"></ul></section>`);
    samples.querySelector("motion").outerHTML = `<div class="form-grid">
      <input class="input" id="mk-st" placeholder="Title">
      <input class="input" id="mk-su" placeholder="URL"></div>
      <button class="btn btn--secondary btn--sm" type="button" id="mk-sam-add">${CA.ui("mk_add")}</button>`;
    const samList = $("#mk-sam-list", samples);
    (preview.samples || []).forEach(s => {
      samList.append(h(`<li>${esc(s.title || s.url)} — <span class="muted">${esc(s.url)}</span></li>`));
    });

    const share = h(`<section class="card mk-publish"><h2 class="card__title">${CA.ui("mk_share")}</h2>
      <p>${CA.ui("mk_share_hint")}</p>
      <p id="mk-share-url" class="caption">${preview.share?.public_url ? location.origin + preview.share.public_url : CA.ui("mk_not_published")}</p>
      <motion-btns class="cluster"></motion-btns></section>`);
    share.querySelector("motion-btns").outerHTML = `<div class="cluster">
      <button class="btn btn--warning" type="button" id="mk-pub">${CA.ui("mk_publish")}</button>
      <button class="btn btn--ghost" type="button" id="mk-rev">${CA.ui("mk_revoke")}</button>
    </div>`;

    edit.append(settings, rates, port, samples, share);
    const prevHost = $("#mk-prev-host", layout);
    const prevEl = renderPreview(preview);
    prevHost.append(prevEl);
    loadAvatar(prevEl);

    v.replaceChildren(head, layout);

    const refreshPreview = async () => {
      const p = await api("/media-kit");
      prevHost.replaceChildren(renderPreview(p));
      loadAvatar($(".mk-preview", prevHost));
    };

    $("#mk-save", head).onclick = () => busy($("#mk-save", head), "…", async () => {
      await api("/media-kit", { method: "PUT", json: {
        headline: $("#mk-head").value, intro: $("#mk-intro").value, pdf_template: $("#mk-tpl").value,
        show_rates: $("#mk-rates").checked, show_metrics: $("#mk-met").checked,
        show_contact_email: $("#mk-em").checked, show_phone: $("#mk-ph").checked,
      }});
      const lines = [...$$(".mk-rate-row", rateBox)].map(row => ({
        deliverable: $("[data-d]", row).value,
        title: $("[data-t]", row).value,
        price: Number($("[data-p]", row).value),
        currency: $("[data-c]", row).value.toUpperCase(),
      }));
      await api("/media-kit/rates", { method: "PUT", json: { lines } });
      const portItems = [...$$("#mk-port-list li")].map((li, i) => ({
        deal_id: Number(li.dataset.deal), summary: li.textContent.split("—").slice(1).join("—").trim(), visible: true,
      })).filter(x => x.deal_id);
      await api("/media-kit/portfolio", { method: "PUT", json: { items: portItems } });
      const samItems = [...$$("#mk-sam-list li")].map(li => ({
        title: li.dataset.title || li.textContent.split("—")[0].trim(),
        url: li.dataset.url || "",
        visible: true,
      })).filter(x => x.url || x.title);
      await api("/media-kit/samples", { method: "PUT", json: { items: samItems } });
      toast("success", CA.ui("mk_saved"));
      await refreshPreview();
    });

    $("#mk-rate-add", rates).onclick = () => addRateRow();
    $("#mk-sam-add", samples).onclick = () => {
      const t = $("#mk-st").value.trim(), u = $("#mk-su").value.trim();
      if (!t && !u) return;
      samList.append(h(`<li data-title="${esc(t)}" data-url="${esc(u)}">${esc(t || u)} — <span class="muted">${esc(u)}</span></li>`));
    };
    $("#mk-port-add", port).onclick = () => {
      const id = $("#mk-deal").value;
      if (!id) return toast("info", CA.ui("mk_pick_deal"));
      portList.append(h(`<li data-deal="${id}">${esc($("#mk-deal option:checked").textContent)} — ${esc($("#mk-sum").value)}</li>`));
    };

    $("#mk-av", settings).onchange = async e => {
      const f = e.target.files?.[0];
      if (!f) return;
      const fd = new FormData();
      fd.append("file", f);
      const r = await fetch("/media-kit/avatar", { method: "POST", headers: { Authorization: "Bearer " + state.tok.access_token }, body: fd });
      if (!r.ok) { toast("error", friendlyError(new Error("Upload failed"))); return; }
      toast("success", CA.ui("mk_avatar_ok"));
      await refreshPreview();
    };

    $("#mk-pdf", head).onclick = () => busy($("#mk-pdf", head), "…", async () => {
      const r = await fetch("/media-kit/export/pdf", { headers: { Authorization: "Bearer " + state.tok.access_token } });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob());
      a.download = "media-kit.pdf";
      a.click();
    });

    $("#mk-pub", share).onclick = async () => {
      if (!(await confirm({
        title: CA.ui("mk_publish"),
        text: CA.ui("mk_publish_confirm"),
        submitLabel: CA.ui("mk_publish"),
        submitClass: "btn--warning",
      }))) return;
      const res = await api("/media-kit/share/publish", { method: "POST", json: { confirm_public: true } });
      $("#mk-share-url").textContent = location.origin + res.public_url;
      toast("success", CA.ui("mk_published"));
    };
    $("#mk-rev", share).onclick = async () => {
      await api("/media-kit/share/revoke", { method: "POST" });
      $("#mk-share-url").textContent = CA.ui("mk_not_published");
      toast("success", CA.ui("mk_revoked"));
    };
  }

  CA.views.mediakit = renderMediaKit;
})();
