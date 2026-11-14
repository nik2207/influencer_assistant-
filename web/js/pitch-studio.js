/* Pitch Studio — multi-variant outreach editor (Phase 6). */
(function () {
  "use strict";
  const { $, $$, esc, h, api, state, icon, toast, busy, modal, skeleton, friendlyError, confirm } = CA;

  let studio = null; // { brand, category, suggestions, edits, selected, savedId, dirty }

  function fullText(s) { return `Subject: ${s.subject}\n\n${s.body}`; }

  function currentEdit() {
    const v = studio.selected;
    return studio.edits[v] || studio.suggestions.find(x => x.variant === v);
  }

  function markDirty() { studio.dirty = true; }

  function renderPanel(root) {
    const s = currentEdit();
    if (!s) return;
    const panel = $(".ps-panel", root);
    panel.innerHTML = `
      <div class="field"><label class="label" for="ps-subj">Subject</label>
        <input class="input" id="ps-subj" value="${esc(s.subject)}"></div>
      <div class="field"><label class="label" for="ps-body">Email body</label>
        <textarea class="textarea" id="ps-body" rows="12">${esc(s.body)}</textarea></div>
      <p class="caption">Format: ${esc(s.collaboration_format || "")} · Deliverables: ${esc(s.deliverables || "")}</p>
      <div class="row__actions">
        <button type="button" class="btn btn--secondary btn--sm" data-regen>${icon("refresh")}Regenerate</button>
        <select class="select" id="ps-lang" aria-label="Language"><option value="">Language</option><option value="hi">Hindi</option><option value="mr">Marathi</option></select>
        <button type="button" class="btn btn--secondary btn--sm" data-copy>${icon("copy")}Copy</button>
        <button type="button" class="btn btn--secondary btn--sm" data-dl>${icon("download")}Download</button>
      </div>`;
    $("#ps-subj", panel).oninput = e => { studio.edits[studio.selected].subject = e.target.value; markDirty(); };
    $("#ps-body", panel).oninput = e => { studio.edits[studio.selected].body = e.target.value; markDirty(); };
    $("[data-copy]", panel).onclick = async () => {
      try { await navigator.clipboard.writeText(fullText(currentEdit())); toast("success", "Pitch copied"); }
      catch (e) { toast("warning", "Couldn't copy. Select the text and copy manually."); }
    };
    $("[data-dl]", panel).onclick = () => {
      const t = fullText(currentEdit());
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([t], { type: "text/plain" }));
      a.download = `pitch-${studio.brand.replace(/\s+/g, "-")}.txt`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast("success", "Download started");
    };
    $("[data-regen]", panel).onclick = e => busy(e.currentTarget, "Rewriting...", async () => {
      const cur = currentEdit();
      try {
        const r = await api("/outreach/studio/regenerate", {
          method: "POST",
          json: {
            brand: studio.brand, variant: studio.selected, language: $("#ps-lang", panel).value,
            goals: studio.goals || "", deliverables: studio.deliverables || "",
            subject: cur.subject, body: cur.body,
          },
        });
        if (!(await confirm({ title: "Replace with regenerated text?", text: "Your current edits for this variant will be replaced.", submitLabel: "Replace" }))) return;
        studio.edits[studio.selected] = { ...cur, ...r };
        renderPanel(root);
        toast("success", "Suggestion updated");
      } catch (err) { toast("error", friendlyError(err)); }
    });
  }

  function closeStudio(root) {
    if (studio && studio.dirty && !confirm) { /* sync confirm below */ }
    root.remove();
    studio = null;
  }

  async function openStudio(brand, category = "") {
    if (studio && studio.dirty) {
      if (!(await confirm({ title: "Discard unsaved changes?", text: "You have unsaved edits in the Pitch Studio.", submitLabel: "Discard", submitClass: "btn--danger" }))) return;
    }
    const wrap = h(`<section class="card pitch-studio" id="pitchStudio" aria-label="Pitch Studio">
      <div class="card__head"><h2 class="card__title">Pitch Studio — ${esc(brand)}</h2>
        <button type="button" class="btn btn--ghost btn--sm" data-close>${icon("x")}Close</button></div>
      <div class="ps-loading"></div></section>`);
    const host = $("#pitchStudioHost") || document.body;
    const existing = $("#pitchStudio");
    if (existing) existing.remove();
    host.append(wrap);
    const load = $(".ps-loading", wrap);
    load.append(skeleton());
    try {
      const data = await api("/outreach/studio/generate", { method: "POST", json: { brand } });
      studio = {
        brand: data.brand, category: data.category || category, suggestions: data.suggestions,
        edits: {}, selected: data.suggestions[0].variant, savedId: null, dirty: false,
        goals: "", deliverables: "", deal_id: data.deal_id,
      };
      data.suggestions.forEach(s => { studio.edits[s.variant] = { ...s }; });
      load.replaceWith(h(`<div class="stack">
        <p class="hint">${esc(data.disclaimer || "")}</p>
        <div class="filters" role="tablist">${data.suggestions.map(s =>
          `<button type="button" role="tab" data-v="${s.variant}" aria-selected="${studio.selected === s.variant}">${esc(s.tone_label)}</button>`).join("")}</div>
        <div class="ps-panel"></div>
        <div class="row__actions">
          <button type="button" class="btn btn--secondary" data-save>Save draft</button>
          <button type="button" class="btn btn--primary" data-gmail>${icon("mail")}Save to Gmail Drafts</button>
        </div></div>`));
      $$("[data-v]", wrap).forEach(b => b.onclick = async () => {
        if (studio.selected === b.dataset.v) return;
        if (studio.dirty && !(await confirm({ title: "Unsaved edits?", text: "Save draft first if you want to keep changes on this variant.", submitLabel: "Switch anyway" }))) return;
        studio.selected = b.dataset.v;
        $$("[data-v]", wrap).forEach(x => x.setAttribute("aria-selected", x.dataset.v === studio.selected));
        renderPanel(wrap);
      });
      renderPanel(wrap);
      $("[data-close]", wrap).onclick = async () => {
        if (studio.dirty && !(await confirm({ title: "Discard unsaved changes?", submitLabel: "Discard", submitClass: "btn--danger" }))) return;
        wrap.remove(); studio = null;
      };
      $("[data-save]", wrap).onclick = e => busy(e.currentTarget, "Saving...", async () => {
        const cur = currentEdit();
        const payload = {
          brand: studio.brand, category: studio.category, variant: studio.selected,
          subject: cur.subject, body: cur.body, status: "ready",
          deal_id: studio.deal_id, goals: studio.goals, deliverables: cur.deliverables || "",
        };
        const r = studio.savedId
          ? await api(`/outreach/drafts/${studio.savedId}`, { method: "PATCH", json: payload })
          : await api("/outreach/drafts", { method: "POST", json: payload });
        studio.savedId = r.id;
        studio.dirty = false;
        toast("success", "Draft saved on the server");
      });
      $("[data-gmail]", wrap).onclick = () => saveGmail(wrap);
      wrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (err) {
      load.replaceChildren(h(`<p class="form-error" role="alert">${esc(friendlyError(err))}</p>`));
    }
  }

  async function saveGmail(root) {
    const cur = currentEdit();
    const body = h(`<div class="stack">
      <p class="hint">This saves a draft in Gmail only. You must open Gmail to review and send. Nothing is sent automatically.</p>
      <div class="field"><label class="label" for="gm-to">To (optional)</label>
        <input class="input" id="gm-to" type="email" placeholder="partnerships@brand.com"></div>
      <div class="field"><label class="label" for="gm-subj">Subject</label><input class="input" id="gm-subj" value="${esc(cur.subject)}"></div>
      <div class="field"><label class="label" for="gm-body">Body</label><textarea class="textarea" id="gm-body" rows="10">${esc(cur.body)}</textarea></div></div>`);
    await new Promise(resolve => {
      const m = modal({ title: "Save to Gmail Drafts", bodyNode: body, submitLabel: "Save to Gmail Drafts",
        onSubmit: async () => {
          if (!studio.savedId) {
            await $("[data-save]", root).click();
            await new Promise(r => setTimeout(r, 400));
          }
          if (!studio.savedId) throw new Error("Save the draft first.");
          const r = await api(`/outreach/drafts/${studio.savedId}/gmail`, {
            method: "POST",
            json: { to: $("#gm-to", body).value.trim(), subject: $("#gm-subj", body).value, body: $("#gm-body", body).value },
          });
          toast("success", r.message || "Saved to Gmail Drafts");
          resolve(true);
        } });
      m.el.addEventListener("close", () => resolve(false));
    });
  }

  CA.pitchStudio = { open: openStudio };
})();
