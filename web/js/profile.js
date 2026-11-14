/* Profile & preferences page. Loads and saves through /profile. Everything the form offers
   (creator types, platforms, languages, currencies) comes from the server, so the UI never hard-codes those lists. */
(function () {
  "use strict";
  const { $, $$, esc, h, api, state, icon, toast, busy, modal, emptyState, errorState, skeleton, friendlyError } = CA;

  const LOGO = { instagram: "IG", youtube: "YT", twitch: "Tw", facebook: "f", threads: "@", x: "X", tiktok: "Tk",
    linkedin: "in", pinterest: "P", spotify: "Sp" };
  const PAYMENT_LABEL = { upi: "UPI", bank: "Bank transfer", other: "Other" };
  const LANG_LABEL = { en: "English", hi: "\u0939\u093F\u0928\u094D\u0926\u0940", mr: "\u092E\u0930\u093E\u0920\u0940" };
  const fmtN = n => Number(n || 0).toLocaleString("en-IN");

  /* ---------- the same rules the server enforces, so mistakes show up before saving ---------- */
  const RULES = {
    name: v => (!v ? "Enter your display name" : v.length > 80 ? "Display name must be 80 characters or fewer" : ""),
    handle: v => (v && !/^@?[A-Za-z0-9._-]{1,60}$/.test(v) ? "Handle can use letters, numbers, dots, dashes and underscores only" : ""),
    niche: v => (v.length > 120 ? "Niche must be 120 characters or fewer" : ""),
    city: v => (v.length > 80 ? "City must be 80 characters or fewer" : ""),
    bio: v => (v.length > 400 ? "Bio must be 400 characters or fewer" : ""),
    contact_email: v => (v && !/^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/.test(v) ? "Enter a valid email address" : ""),
    phone: v => (v && !/^\+?[0-9 ()-]{7,20}$/.test(v) ? "Use digits, spaces, + and - (7 to 20 characters)" : ""),
    home_location: v => (v.length > 200 ? "Home location must be 200 characters or fewer" : ""),
    upi_vpa: v => (v && !/^[A-Za-z0-9._-]{2,64}@[A-Za-z][A-Za-z0-9.-]{1,63}$/.test(v) ? "UPI ID should look like name@bank" : ""),
    gstin: v => (v && !/^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/.test(v.toUpperCase()) ? "GSTIN should be 15 characters, like 27ABCDE1234F1Z5" : ""),
    invoice_notes: v => (v.length > 400 ? "Invoice notes must be 400 characters or fewer" : ""),
    payment_terms_days: v => (!Number.isInteger(v) || v < 0 || v > 120 ? "Enter a number of days from 0 to 120" : ""),
    languages: v => (!v.length ? "Choose at least one language" : ""),
  };

  const field = (id, label, control, hint = "", cls = "") => `<div class="field ${cls}" data-field="${id}">
    <label class="label" for="pf-${id}">${esc(label)}</label>${control}${hint ? `<span class="hint" id="pf-${id}-hint">${esc(hint)}</span>` : ""}
    <div class="field-error" id="pf-${id}-err" role="alert" hidden></div></div>`;
  const input = (id, val, extra = "") => `<input class="input" id="pf-${id}" name="${id}" value="${esc(val)}" ${extra}>`;
  const privacy = text => `<p class="private-note">${icon("info")}<span>${esc(text)}</span></p>`;

  /* ---------- page ---------- */
  async function profileView(v, ctx) {
    if (!ctx.silent) v.replaceChildren(skeleton("dashboard"));
    let data = await api("/profile");
    if (!ctx.alive()) return;
    state.profile = data;
    draw(v, data);
  }

  function draw(v, data) {
    const { user, creator, platforms, options } = data;
    const type = options.creator_types.find(t => t.id === creator.creator_type) || options.creator_types[0];
    const initial = (user.name || user.email || "?").trim().charAt(0).toUpperCase();
    const comp = data.completeness;

    const overview = h(`<section class="card ov" aria-label="Profile overview">
      <div class="ov__avatar" aria-hidden="true">${esc(initial)}</div>
      <div>
        <div class="ov__name">${esc(user.name || "Your name")}</div>
        <div class="muted">${esc(user.handle || user.email)}${user.city ? " \u00B7 " + esc(user.city) : ""}</div>
        <div class="ov__meta"><span class="badge badge--gold">${esc(type.label)}</span>${user.niche ? `<span class="badge">${esc(user.niche)}</span>` : ""}
          ${creator.languages.map(l => `<span class="badge badge--info">${esc(LANG_LABEL[l] || l)}</span>`).join("")}<span class="badge badge--purple">${esc(creator.currency)}</span></div>
        <div class="ov__stats"><div class="ov__stat"><strong>${fmtN(data.total_followers)}</strong><span class="caption">total audience</span></div>
          <div class="ov__stat"><strong>${platforms.length}</strong><span class="caption">${platforms.length === 1 ? "account" : "accounts"} added</span></div></div>
      </div>
      <div class="ov__side"><div class="meter__label"><span>Profile strength</span><strong>${comp.percent}%</strong></div>
        <div class="meter" role="progressbar" aria-valuenow="${comp.percent}" aria-valuemin="0" aria-valuemax="100" aria-label="Profile strength"><i style="width:${comp.percent}%"></i></div>
        <p class="caption" style="margin-top:8px">${comp.missing.length ? "Add: " + esc(comp.missing.join(", ")) : "Everything is filled in. Nice."}</p></div></section>`);

    const form = h(`<form class="profile" id="profileForm" novalidate aria-label="Edit profile"></form>`);

    /* About you */
    const about = h(`<section class="card profile__section"><div><h2 class="card__title">About you</h2>
      <p class="profile__intro">The assistant uses this to write pitches and replies in your voice.</p></div>
      <div class="form-grid">
        ${field("name", "Display name", input("name", user.name, 'autocomplete="name" maxlength="80" required'))}
        ${field("handle", "Handle", input("handle", user.handle, 'placeholder="@yourhandle" maxlength="61" autocapitalize="none"'))}
        ${field("niche", "Niche or category", input("niche", user.niche, 'placeholder="e.g. beauty, gaming, travel" maxlength="120"'))}
        ${field("city", "City", input("city", user.city, 'autocomplete="address-level2" maxlength="80"'))}
        <div class="field full"><span class="label" id="pf-type-label">Creator type</span>
          <div class="type-pick" role="radiogroup" aria-labelledby="pf-type-label">${options.creator_types.map(t => `<label><input type="radio" name="creator_type" value="${esc(t.id)}" ${t.id === creator.creator_type ? "checked" : ""}>
            <strong>${esc(t.label)}</strong><span>${esc(t.examples.slice(0, 2).join(", "))}</span></label>`).join("")}</div>
          <span class="hint">Changes the words and shortcuts you see, for example Deals or Sponsorships. All features stay available.</span></div>
        ${field("bio", "Short bio", `<textarea class="textarea" id="pf-bio" name="bio" rows="3" maxlength="400" placeholder="One or two lines brands should know about you">${esc(creator.bio)}</textarea><div class="counter" id="pf-bio-count"></div>`, "", "full")}
      </div></section>`);

    /* Social accounts */
    const defaults = type.default_platforms || [];
    const order = [...options.platforms].sort((a, b) => (platforms.some(p => p.platform === b.id) - platforms.some(p => p.platform === a.id)) ||
      ((defaults.includes(b.id) ? 1 : 0) - (defaults.includes(a.id) ? 1 : 0)));
    const social = h(`<section class="card profile__section"><div><h2 class="card__title">Social accounts</h2>
      <p class="profile__intro">Add the channels brands will look at. Accounts are entered by hand for now, so keep follower counts up to date.</p></div>
      <div class="plat-grid" id="platGrid"></div></section>`);
    const grid = $("#platGrid", social);
    order.forEach(p => {
      const have = platforms.find(x => x.platform === p.id);
      const card = h(`<article class="plat plat--${esc(p.id)} ${have ? "is-on" : ""}"><div class="plat__logo" aria-hidden="true">${esc(LOGO[p.id] || p.label.charAt(0))}</div>
        <div class="plat__name">${esc(p.label)}</div>
        <div class="plat__sub">${have ? `@${esc(have.handle)}<br>${fmtN(have.followers)} followers` : `Add your ${esc(p.label)} account`}</div>
        <div class="plat__actions">${have ? `<button class="btn btn--secondary btn--sm" type="button" data-edit>Edit</button><button class="btn btn--ghost btn--sm" type="button" data-remove aria-label="Remove ${esc(p.label)}">Remove</button>`
          : `<button class="btn btn--secondary btn--sm" type="button" data-edit aria-label="Add ${esc(p.label)} account">Add account</button>`}</div></article>`);
      $("[data-edit]", card).onclick = () => platformDialog(p, have, v);
      const rm = $("[data-remove]", card);
      if (rm) rm.onclick = () => removePlatform(p, v);
      grid.append(card);
    });

    /* Language & region */
    const langs = h(`<section class="card profile__section"><div><h2 class="card__title">Language &amp; region</h2>
      <p class="profile__intro">Sets the language the assistant replies in and the currency it uses.</p></div>
      <div class="form-grid">
        ${field("language", "Reply language", `<select class="select" id="pf-language" name="language">${options.languages.map(l => `<option value="${esc(l.id)}" ${user.language === l.id ? "selected" : ""}>${esc(LANG_LABEL[l.id] || l.label)}</option>`).join("")}</select>`)}
        ${field("currency", "Preferred currency", `<select class="select" id="pf-currency" name="currency">${options.currencies.map(c => `<option ${creator.currency === c ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>`, "Invoices are still created in rupees for now.")}
        <div class="field full" data-field="languages"><span class="label" id="pf-languages-label">Languages you use</span>
          <div class="lang-set" role="group" aria-labelledby="pf-languages-label">${options.languages.map(l => `<label class="checkbox"><input type="checkbox" name="languages" value="${esc(l.id)}" ${creator.languages.includes(l.id) ? "checked" : ""}> ${esc(LANG_LABEL[l.id] || l.label)}</label>`).join("")}</div>
          <div class="field-error" id="pf-languages-err" role="alert" hidden></div></div>
        ${field("home_location", "Default pickup location", input("home_location", creator.home_location, 'placeholder="e.g. Panvel, Navi Mumbai" maxlength="200" autocomplete="street-address"'), "Used to suggest cab and porter pickups.", "full")}
      </div>${privacy("Your pickup location is private. It is never sent to the AI model.")}</section>`);

    /* Contact */
    const contact = h(`<section class="card profile__section"><div><h2 class="card__title">Contact details</h2>
      <p class="profile__intro">Optional. Shown on your documents when you choose to include them.</p></div>
      <div class="form-grid">
        ${field("contact_email", "Business email", input("contact_email", creator.contact_email, 'type="email" autocomplete="email" maxlength="255" placeholder="you@example.com"'))}
        ${field("phone", "Phone", input("phone", creator.phone, 'type="tel" autocomplete="tel" maxlength="24" placeholder="+91 98765 43210"'))}
      </div>${privacy("Email and phone are private. They are never sent to the AI model.")}</section>`);

    /* Payments & invoices */
    const pay = h(`<section class="card profile__section"><div><h2 class="card__title">Payments &amp; invoices</h2>
      <p class="profile__intro">Defaults for the invoices you create.</p></div>
      <div class="form-grid">
        ${field("upi_vpa", "UPI ID", input("upi_vpa", user.upi_vpa, 'placeholder="name@bank" maxlength="100" autocapitalize="none"'), "Used for the payment link on invoices.")}
        ${field("payment_method", "Preferred payment method", `<select class="select" id="pf-payment_method" name="payment_method">${options.payment_methods.map(m => `<option value="${esc(m)}" ${creator.payment_method === m ? "selected" : ""}>${esc(PAYMENT_LABEL[m] || m)}</option>`).join("")}</select>`)}
        ${field("payment_terms_days", "Payment terms (days)", input("payment_terms_days", creator.payment_terms_days, 'type="number" min="0" max="120" step="1" inputmode="numeric"'), "Printed on every invoice.")}
        ${field("gstin", "GSTIN (optional)", input("gstin", creator.gstin, 'maxlength="15" autocapitalize="characters" placeholder="27ABCDE1234F1Z5"'))}
        ${field("invoice_notes", "Invoice notes", `<textarea class="textarea" id="pf-invoice_notes" name="invoice_notes" rows="2" maxlength="400" placeholder="e.g. Please pay by NEFT. Thank you!">${esc(creator.invoice_notes)}</textarea>`, "", "full")}
      </div></section>`);

    const bar = h(`<div class="savebar" role="region" aria-label="Save changes"><span class="savebar__status" id="pfStatus" aria-live="polite">All changes saved</span>
      <span class="savebar__btns"><button class="btn btn--secondary" type="button" id="pfCancel" disabled>Cancel</button>
      <button class="btn btn--primary" type="submit" id="pfSave" disabled>Save changes</button></span></div>`);

    form.append(about, social, langs, contact, pay, bar);
    const head = h(`<div class="page-head"><div><h1 class="page-title">Profile &amp; preferences</h1>
      <p class="page-sub">Your details help the assistant write better pitches and replies.</p></div></div>`);
    const wrap = h(`<div class="stack stack--lg"></div>`); wrap.append(overview, form);
    v.replaceChildren(head, wrap);
    wire(form, data, v);
  }

  /* ---------- form behaviour ---------- */
  const read = form => {
    const fd = new FormData(form), s = k => String(fd.get(k) || "").trim();
    return { name: s("name"), handle: s("handle"), niche: s("niche"), city: s("city"), language: s("language"), upi_vpa: s("upi_vpa"),
      creator_type: s("creator_type"), bio: s("bio"), currency: s("currency"), languages: fd.getAll("languages"),
      contact_email: s("contact_email").toLowerCase(), phone: s("phone"), home_location: s("home_location"),
      payment_method: s("payment_method"), payment_terms_days: Number(s("payment_terms_days") === "" ? NaN : s("payment_terms_days")),
      invoice_notes: s("invoice_notes"), gstin: s("gstin").toUpperCase() };
  };

  function showError(form, key, msg) {
    const err = $(`#pf-${key}-err`, form), el = $(`#pf-${key}`, form);
    if (err) { err.textContent = msg; err.hidden = !msg; }
    if (el) { if (msg) { el.setAttribute("aria-invalid", "true"); el.setAttribute("aria-describedby", `pf-${key}-err`); } else { el.removeAttribute("aria-invalid"); el.removeAttribute("aria-describedby"); } }
  }

  function validate(form, vals) {
    const bad = {};
    Object.keys(RULES).forEach(k => { const m = RULES[k](vals[k]); showError(form, k, m); if (m) bad[k] = m; });
    return bad;
  }

  function wire(form, data, view) {
    const base = data.creator, baseUser = data.user;
    const baseline = JSON.stringify(read(form));
    const save = $("#pfSave", form), cancel = $("#pfCancel", form), status = $("#pfStatus", form);
    const count = () => { const b = $("#pf-bio", form), c = $("#pf-bio-count", form); if (b && c) c.textContent = `${b.value.length}/400`; };
    count();

    const markDirty = () => {
      const dirty = JSON.stringify(read(form)) !== baseline;
      save.disabled = !dirty; cancel.disabled = !dirty;
      status.textContent = dirty ? "You have unsaved changes" : "All changes saved";
      status.classList.toggle("is-dirty", dirty);
      window.onbeforeunload = dirty ? () => "" : null;
    };
    form.addEventListener("input", e => {
      count();
      const key = e.target.name; if (key && RULES[key]) showError(form, key, "");
      markDirty();
    });
    form.addEventListener("change", e => {
      if (e.target.name === "language") {  // the reply language is always one of your languages
        const box = $(`input[name="languages"][value="${e.target.value}"]`, form); if (box) box.checked = true;
        showError(form, "languages", "");
      }
      markDirty();
    });

    cancel.onclick = () => { window.onbeforeunload = null; draw(view, state.profile); toast("info", "Changes discarded"); };

    form.onsubmit = async e => {
      e.preventDefault();
      if (save.disabled) return;
      const vals = read(form), bad = validate(form, vals);
      const first = Object.keys(bad)[0];
      if (first) { const el = $(`#pf-${first}`, form) || $(`[data-field="${first}"] input`, form); if (el) el.focus(); toast("warning", "Please fix the highlighted fields."); return; }
      const changed = {};
      Object.entries(vals).forEach(([k, val]) => {
        const old = k in baseUser ? baseUser[k] : base[k];
        if (JSON.stringify(val) !== JSON.stringify(old)) changed[k] = val;
      });
      await busy(save, "Saving...", async () => {
        try {
          const res = await api("/profile", { method: "PATCH", json: changed });
          window.onbeforeunload = null;
          state.profile = res;
          CA.profileChanged(res);
          toast("success", "Profile saved");
          draw(view, res);
        } catch (err) {
          if (err.fields) {
            let focused = false;
            Object.entries(err.fields).forEach(([k, m]) => { showError(form, k, m); if (!focused) { const el = $(`#pf-${k}`, form); if (el) { el.focus(); focused = true; } } });
            toast("warning", "Please fix the highlighted fields.");
          } else toast("error", friendlyError(err, "We couldn't save your profile. Please try again."));
        }
      });
    };
  }

  /* ---------- platform add / edit / remove ---------- */
  function platformDialog(p, have, view) {
    modal({
      title: `${have ? "Edit" : "Add"} ${p.label} account`, submitLabel: have ? "Save" : "Add account",
      body: `<div class="field"><label class="label" for="pl-handle">Handle</label>
          <input class="input" id="pl-handle" name="handle" required maxlength="61" autocapitalize="none" placeholder="yourhandle" value="${esc(have ? have.handle : "")}"></div>
        <div class="field"><label class="label" for="pl-url">Profile link (optional)</label>
          <input class="input" id="pl-url" name="url" type="url" maxlength="300" inputmode="url" placeholder="${esc(p.base)}yourhandle" value="${esc(have ? have.url : "")}">
          <span class="hint">Leave empty and we will build it from your handle.</span></div>
        <div class="field"><label class="label" for="pl-fol">Followers or subscribers</label>
          <input class="input" id="pl-fol" name="followers" type="number" min="0" max="2000000000" step="1" inputmode="numeric" required value="${have ? have.followers : ""}"></div>`,
      onSubmit: async d => {
        const handle = (d.handle || "").trim().replace(/^@/, "");
        if (!handle) throw new Error("Enter the account handle.");
        const followers = Number(d.followers);
        if (!Number.isInteger(followers) || followers < 0) throw new Error("Enter the follower count as a whole number.");
        const res = await api(`/profile/platforms/${p.id}`, { method: "PUT", json: { handle, url: (d.url || "").trim(), followers } });
        state.profile = res; CA.profileChanged(res);
        toast("success", `${p.label} account ${have ? "updated" : "added"}`);
        draw(view, res);
      },
    });
  }

  function removePlatform(p, view) {
    let yes = false;
    const m = modal({ title: `Remove ${p.label}?`, body: `<p>This removes the ${esc(p.label)} account from your profile. Nothing changes on ${esc(p.label)} itself.</p>`,
      submitLabel: "Remove", submitClass: "btn--danger", onSubmit: async () => { yes = true; } });
    m.el.addEventListener("close", async () => {
      if (!yes) return;
      try {
        const res = await api(`/profile/platforms/${p.id}`, { method: "DELETE" });
        state.profile = res; CA.profileChanged(res);
        toast("success", `${p.label} removed`);
        draw(view, res);
      } catch (e) { toast("error", friendlyError(e, "We couldn't remove that account.")); }
    });
  }

  CA.views.profile = profileView;
})();
