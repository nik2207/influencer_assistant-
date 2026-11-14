/* Invoices & expenses UI (Phase 5). Registers on CA.invoicesPage and CA.views.expenses. */
(function () {
  "use strict";
  const { $, $$, esc, h, api, state, money, dtf, icon, toast, busy, modal, emptyState, skeleton, friendlyError, confirm } = CA;

  const STATUSES = [
    ["draft", "Draft", "info"], ["sent", "Sent", "info"], ["partially_paid", "Partial", "warning"],
    ["paid", "Paid", "success"], ["overdue", "Overdue", "danger"], ["cancelled", "Cancelled", ""],
  ];
  const statusBadge = s => {
    const row = STATUSES.find(x => x[0] === s) || [s, s, ""];
    return `<span class="badge ${row[2] ? "badge--" + row[2] : ""}">${esc(row[1])}</span>`;
  };

  const CAT = {
    travel: "Travel & cab", food: "Food & refreshments", clothing: "Clothing & styling",
    makeup: "Makeup & grooming", equipment: "Equipment", props: "Props & production",
    software: "Software & subscriptions", accommodation: "Accommodation", other: "Other",
  };

  let invFilter = { status: "", brand: "", q: "", sort: "newest", overdue: false };

  function lineRow(row = {}) {
    return `<div class="form-grid line-row" style="margin-bottom:8px">
      <div class="field full"><label class="label">Description</label>
        <input class="input" name="li_desc" required value="${esc(row.description || "")}"></div>
      <div class="field"><label class="label">Qty</label><input class="input" name="li_qty" type="number" min="0.01" step="0.01" value="${row.quantity ?? 1}"></div>
      <div class="field"><label class="label">Unit price (&#8377;)</label><input class="input" name="li_price" type="number" min="0" step="1" value="${row.unit_price ?? 0}"></div>
      <div class="field" style="align-self:end"><button type="button" class="btn btn--ghost btn--sm" data-rm-line>Remove</button></div></div>`;
  }

  function readLines(form) {
    return $$(".line-row", form).map(r => ({
      description: ($("[name=li_desc]", r).value || "").trim(),
      quantity: Number($("[name=li_qty]", r).value || 1),
      unit_price: Number($("[name=li_price]", r).value || 0),
    })).filter(x => x.description);
  }

  function editorForm(inv, deals) {
    const dealOpts = (deals || []).map(d => `<option value="${d.id}" ${inv.deal_id === d.id ? "selected" : ""}>#${d.id} ${esc(d.brand)}</option>`).join("");
    const lines = (inv.line_items && inv.line_items.length) ? inv.line_items : [{ description: "", quantity: 1, unit_price: 0 }];
    return `<div class="form-grid">
      <div class="field"><label class="label" for="iv-deal">Deal (optional)</label><select class="select" id="iv-deal" name="deal_id"><option value="">—</option>${dealOpts}</select></div>
      <div class="field"><label class="label" for="iv-issue">Issue date</label><input class="input" id="iv-issue" name="issue_date" type="date" value="${inv.issue_date || ""}"></div>
      <div class="field"><label class="label" for="iv-due">Due date</label><input class="input" id="iv-due" name="due_date" type="date" value="${inv.due_date || ""}"></div>
      <div class="field full"><label class="label" for="iv-cname">Your business name</label><input class="input" id="iv-cname" name="creator_name" value="${esc(inv.creator_name || "")}"></div>
      <div class="field"><label class="label" for="iv-cemail">Your email</label><input class="input" id="iv-cemail" name="creator_email" type="email" value="${esc(inv.creator_email || "")}"></div>
      <div class="field"><label class="label" for="iv-cphone">Phone</label><input class="input" id="iv-cphone" name="creator_phone" value="${esc(inv.creator_phone || "")}"></div>
      <div class="field full"><label class="label" for="iv-caddr">Your address</label><input class="input" id="iv-caddr" name="creator_address" value="${esc(inv.creator_address || "")}"></div>
      <div class="field full"><label class="label" for="iv-client">Client / brand</label><input class="input" id="iv-client" name="client_name" required value="${esc(inv.client_name || "")}"></div>
      <div class="field"><label class="label" for="iv-cemail2">Client email</label><input class="input" id="iv-cemail2" name="client_email" type="email" value="${esc(inv.client_email || "")}"></div>
      <div class="field full"><label class="label" for="iv-baddr">Client billing address</label><input class="input" id="iv-baddr" name="client_address" value="${esc(inv.client_address || "")}"></div>
      <div class="field full"><label class="label" for="iv-camp">Campaign</label><input class="input" id="iv-camp" name="campaign" value="${esc(inv.campaign || "")}"></div>
      <div class="field full"><label class="label" for="iv-work">Work description</label><textarea class="textarea" id="iv-work" name="work_description" rows="2">${esc(inv.work_description || "")}</textarea></div>
      <div class="field full"><label class="label">Line items</label><div id="iv-lines">${lines.map(lineRow).join("")}</div>
        <button type="button" class="btn btn--ghost btn--sm" id="iv-add-line">${icon("plus")}Add line</button></div>
      <div class="field"><label class="label" for="iv-disc">Discount (&#8377;)</label><input class="input" id="iv-disc" name="discount_inr" type="number" min="0" value="${inv.discount_inr || 0}"></div>
      <div class="field"><label class="label" for="iv-tax">Tax (%)</label><input class="input" id="iv-tax" name="tax_percent" type="number" min="0" max="100" step="0.1" value="${inv.tax_percent || 0}"></div>
      <div class="field full"><label class="label" for="iv-notes">Notes</label><textarea class="textarea" id="iv-notes" name="notes" rows="2">${esc(inv.notes || "")}</textarea></div>
      <div class="field full"><label class="label" for="iv-terms">Terms</label><textarea class="textarea" id="iv-terms" name="terms" rows="2">${esc(inv.terms || "")}</textarea></div>
      <div class="field"><label class="label" for="iv-sign">Signature (text)</label><input class="input" id="iv-sign" name="signature_text" value="${esc(inv.signature_text || "")}"></div></div>`;
  }

  function bindLineEditor(form) {
    const box = $("#iv-lines", form);
    $("#iv-add-line", form).onclick = () => { box.append(h(lineRow())); bindLineEditor(form); };
    $$("[data-rm-line]", box).forEach(b => b.onclick = () => { b.closest(".line-row").remove(); });
  }

  function payloadFromForm(form) {
    const d = Object.fromEntries(new FormData(form).entries());
    const deal_id = d.deal_id ? Number(d.deal_id) : null;
    return {
      deal_id, issue_date: d.issue_date || null, due_date: d.due_date || null,
      creator_name: d.creator_name || "", creator_email: d.creator_email || "", creator_phone: d.creator_phone || "",
      creator_address: d.creator_address || "", client_name: (d.client_name || "").trim(),
      client_email: d.client_email || "", client_address: d.client_address || "",
      campaign: d.campaign || "", work_description: d.work_description || "",
      line_items: readLines(form), discount_inr: Number(d.discount_inr || 0), tax_percent: Number(d.tax_percent || 0),
      notes: d.notes || "", terms: d.terms || "", signature_text: d.signature_text || "", currency: "INR",
    };
  }

  function openEditor(inv, deals, onDone) {
    const isDraft = inv.status === "draft";
    const m = modal({
      title: isDraft ? `Edit ${inv.number || "draft"}` : `Preview ${inv.number}`,
      body: editorForm(inv, deals),
      submitLabel: isDraft ? "Save draft" : "Close",
      submitClass: "btn--primary",
      onSubmit: isDraft ? async () => {
        const form = m.el.querySelector("form");
        const json = payloadFromForm(form);
        if (!json.client_name) throw new Error("Client name is required.");
        if (!json.line_items.length) throw new Error("Add at least one line item.");
        await api(`/invoices/${inv.id}`, { method: "PATCH", json });
        toast("success", "Draft saved");
        onDone();
      } : null,
    });
    bindLineEditor(m.el.querySelector("form"));
    if (!isDraft) {
      const foot = m.el.querySelector(".modal__foot");
      foot.querySelector('[type="submit"]').textContent = "Close";
    }
  }

  async function previewCard(inv) {
    const pre = h(`<pre class="pitch" style="white-space:pre-wrap;font-size:13px"></pre>`);
    const lines = (inv.line_items || []).map(li => `${li.quantity} × ${li.description} @ ${money(li.unit_price)}`);
    pre.textContent = [
      inv.number, `Status: ${inv.status}`, `Issue: ${inv.issue_date || "—"}  Due: ${inv.due_date || "—"}`,
      `From: ${inv.creator_name}`, `To: ${inv.client_name}`,
      "", ...lines, "",
      `Total: ${money(inv.amount_inr)}  Received: ${money(inv.paid_inr)}  Balance: ${money(inv.balance_inr)}`,
      inv.notes ? "\nNotes: " + inv.notes : "",
    ].join("\n");
    modal({ title: "Invoice preview", bodyNode: pre, submitLabel: "Close", onSubmit: null });
  }

  async function recordPayment(inv) {
    const body = h(`<div class="stack">
      <p class="caption">Outstanding: ${money(inv.balance_inr)}</p>
      <div class="field"><label class="label" for="pay-amt">Amount (&#8377;)</label><input class="input" id="pay-amt" name="amount_inr" type="number" min="1" step="1" required></div>
      <div class="field"><label class="label" for="pay-ref">Reference</label><input class="input" id="pay-ref" name="reference" placeholder="UTR / transaction id"></div></div>`);
    const ok = await new Promise(resolve => {
      const m = modal({ title: `Record payment — ${inv.number}`, bodyNode: body, submitLabel: "Record payment",
        onSubmit: async () => {
          const amt = Number($("#pay-amt", body).value);
          if (!amt || amt <= 0) throw new Error("Enter a valid amount.");
          await api(`/invoices/${inv.id}/payments`, { method: "POST", json: { amount_inr: amt, reference: $("#pay-ref", body).value || "" } });
          toast("success", "Payment recorded");
          resolve(true);
        } });
      m.el.addEventListener("close", () => resolve(false));
    });
    return ok;
  }

  async function paymentHistory(inv) {
    const pays = await api(`/invoices/${inv.id}/payments`);
    const pre = h(`<pre class="pitch"></pre>`);
    pre.textContent = pays.length ? pays.map(p => `${p.paid_at}: ${money(p.amount_inr)} ${p.reference || ""}`).join("\n") : "No payments recorded yet.";
    modal({ title: `Payments — ${inv.number}`, bodyNode: pre });
  }

  async function reminderDraft(inv) {
    const r = await api(`/invoices/${inv.id}/reminder-draft`, { method: "POST" });
    const wrap = h(`<div class="stack"><p class="hint">${esc(r.note)}</p><pre class="pitch"></pre></div>`);
    $("pre", wrap).textContent = r.draft;
    modal({ title: "Payment reminder draft", bodyNode: wrap });
    toast("info", "Review the draft. Nothing was sent.");
  }

  async function renderInvoices(v, ctx) {
    const head = h(`<div class="page-head"><div><h1 class="page-title">Invoices</h1>
      <p class="page-sub">Create, send and track payments. Received income is separate from invoiced amounts.</p></div>
      <div class="page-actions"><button class="btn btn--accent" type="button" id="inv-new">${icon("plus")}New invoice</button></div></div>`);
    if (!ctx.silent) v.replaceChildren(head, skeleton());
    const monthStart = new Date(); monthStart.setDate(1);
    const qs = `?from_date=${monthStart.toISOString().slice(0, 10)}&to_date=${new Date().toISOString().slice(0, 10)}`;
    const params = new URLSearchParams({ sort: invFilter.sort });
    if (invFilter.status) params.set("status", invFilter.status);
    if (invFilter.brand) params.set("brand", invFilter.brand);
    if (invFilter.q) params.set("q", invFilter.q);
    if (invFilter.overdue) params.set("overdue_only", "true");
    const [listR, dealsR, sumR] = await Promise.allSettled([api("/invoices?" + params), api("/deals"), api("/invoices/summary" + qs)]);
    if (!ctx.alive()) return;
    if (listR.status === "rejected") throw listR.reason;
    const items = listR.value, deals = dealsR.status === "fulfilled" ? dealsR.value : [];
    const sum = sumR.status === "fulfilled" ? sumR.value : null;
    const strip = h(`<div class="summary-strip">
      <div class="card stat stat--key"><span class="stat__top"><span>Invoiced</span></span><span class="stat__value">${sum ? money(sum.total_invoiced) : "—"}</span></div>
      <div class="card stat"><span class="stat__top"><span>Received</span></span><span class="stat__value">${sum ? money(sum.total_received) : "—"}</span></div>
      <div class="card stat"><span class="stat__top"><span>Outstanding</span></span><span class="stat__value">${sum ? money(sum.outstanding) : "—"}</span></div>
      <div class="card stat"><span class="stat__top"><span>Overdue</span></span><span class="stat__value">${sum ? money(sum.overdue_amount) : "—"}</span><span class="caption">${sum ? sum.overdue_count + " invoice(s)" : ""}</span></div></div>`);
    const filters = h(`<div class="filters" role="group" aria-label="Filter invoices">
      <input class="input" id="inv-q" placeholder="Search number or brand" style="max-width:200px" value="${esc(invFilter.q)}">
      <select class="select" id="inv-st" style="max-width:140px"><option value="">All statuses</option>
        ${STATUSES.map(([k, l]) => `<option value="${k}" ${invFilter.status === k ? "selected" : ""}>${l}</option>`).join("")}</select>
      <button type="button" data-od ${invFilter.overdue ? 'aria-pressed="true"' : ""}>Overdue</button></div>`);
    $("#inv-q", filters).onchange = e => { invFilter.q = e.target.value; CA.refreshView(); };
    $("#inv-st", filters).onchange = e => { invFilter.status = e.target.value; CA.refreshView(); };
    $("[data-od]", filters).onclick = e => { invFilter.overdue = !invFilter.overdue; CA.refreshView(); };
    const card = h(`<section class="card"><div class="list"></div></section>`);
    if (!items.length) {
      card.querySelector(".list").append(emptyState({ icon: "receipt", title: "No invoices match", text: "Create an invoice or adjust filters." }));
    }
    items.forEach(i => {
      const row = h(`<div class="row"><div class="row__top"><span class="cluster"><span class="row__title">${esc(i.number)}</span>${statusBadge(i.status)}</span>
        <span class="deal__value">${money(i.amount_inr)}</span></div>
        <div class="caption">${esc(i.client_name)} · ${i.due_date ? "Due " + i.due_date : esc(dtf(i.created_at))} · Balance ${money(i.balance_inr)}</div>
        <div class="row__actions"></div></div>`);
      const acts = $(".row__actions", row);
      const add = (label, cls, fn) => { const b = h(`<button class="btn btn--secondary btn--sm ${cls}" type="button">${label}</button>`); b.onclick = () => busy(b, "...", fn); acts.append(b); };
      add("Preview", "", () => previewCard(i));
      if (i.status === "draft") {
        add("Edit", "", async () => { const full = await api(`/invoices/${i.id}`); openEditor(full, deals, () => CA.refreshView()); });
        add("Send", "btn--accent", async () => {
          if (!(await confirm({ title: "Mark as sent?", text: "This generates the PDF and payment link. You can still record payments later.", submitLabel: "Mark sent" }))) return;
          await api(`/invoices/${i.id}/send`, { method: "POST" }); toast("success", "Invoice marked as sent"); CA.refreshView();
        });
      }
      const pdfBtn = h(`<button class="btn btn--secondary btn--sm" type="button" data-pdf>${icon("download")}PDF</button>`);
      pdfBtn.onclick = () => busy(pdfBtn, "Preparing PDF...", async () => {
        await api("/auth/me");
        const r = await fetch(`/invoices/${i.id}/pdf`, { headers: { Authorization: "Bearer " + state.tok.access_token } });
        if (!r.ok) throw new Error("Download failed");
        const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = i.number + ".pdf";
        document.body.append(a); a.click(); a.remove(); toast("success", "PDF downloaded");
      });
      acts.append(pdfBtn);
      if (["sent", "partially_paid", "overdue"].includes(i.status)) {
        add("Record payment", "", async () => { if (await recordPayment(i)) CA.refreshView(); });
        add("Reminder", "", () => reminderDraft(i));
      }
      if (i.status !== "paid" && i.status !== "cancelled" && i.status !== "draft") {
        const pb = h(`<button class="btn btn--success btn--sm" type="button" data-paid>${icon("check")}Mark paid</button>`);
        pb.onclick = async () => {
          if (!(await confirm({ title: `Mark ${i.number} as paid?`, text: `Records the remaining ${money(i.balance_inr)} as received.`, submitLabel: "Mark paid", submitClass: "btn--success" }))) return;
          await busy(pb, "...", async () => { await api(`/invoices/${i.id}/mark-paid`, { method: "POST" }); toast("success", "Marked as paid"); CA.refreshView(); });
        };
        acts.append(pb);
      }
      add("Payments", "", () => paymentHistory(i));
      $(".list", card).append(row);
    });
    $("#inv-new", head).onclick = () => {
      modal({
        title: "New invoice", body: editorForm({ line_items: [{ description: "", quantity: 1, unit_price: 0 }] }, deals),
        submitLabel: "Save draft",
        onSubmit: async () => {
          const form = document.querySelector("dialog.modal form");
          const json = payloadFromForm(form);
          if (!json.client_name) throw new Error("Client name is required.");
          if (!json.line_items.length) throw new Error("Add at least one line item.");
          await api("/invoices", { method: "POST", json });
          toast("success", "Draft invoice created"); CA.refreshView();
        },
      });
      bindLineEditor(document.querySelector("dialog.modal form"));
    };
    v.replaceChildren(head, strip, filters, card);
  }

  async function renderExpenses(v, ctx) {
    const head = h(`<div class="page-head"><div><h1 class="page-title">Expenses</h1>
      <p class="page-sub">Track business spending. Net cash flow uses money received minus expenses.</p></div>
      <div class="page-actions"><button class="btn btn--accent" type="button" id="exp-new">${icon("plus")}Add expense</button></div></div>`);
    if (!ctx.silent) v.replaceChildren(head, skeleton());
    const start = new Date(); start.setDate(1);
    const from = start.toISOString().slice(0, 10), to = new Date().toISOString().slice(0, 10);
    const [list, sum] = await Promise.allSettled([api("/expenses?from_date=" + from + "&to_date=" + to), api(`/expenses/summary?from_date=${from}&to_date=${to}`)]);
    if (!ctx.alive()) return;
    if (list.status === "rejected") throw list.reason;
    const items = list.value;
    const strip = h(`<div class="card stat"><span class="stat__top"><span>This month</span></span>
      <span class="stat__value">${sum.status === "fulfilled" ? money(sum.value.total_inr) : "—"}</span><span class="caption">${from} to ${to}</span></div>`);
    const card = h(`<section class="card"><div class="list"></div></section>`);
    if (!items.length) card.querySelector(".list").append(emptyState({ icon: "receipt", title: "No expenses yet", text: "Log travel, styling, software and other business costs." }));
    items.forEach(e => {
      const row = h(`<div class="row"><div class="row__top"><span class="row__title">${esc(CAT[e.category] || e.category)}</span>
        <span class="deal__value">${money(e.amount_inr)}</span></div>
        <div class="caption">${e.spent_on} · ${esc(e.description)}${e.vendor ? " · " + esc(e.vendor) : ""}</div>
        <div class="row__actions"><button class="btn btn--ghost btn--sm" type="button" data-del>Delete</button></div></div>`);
      $("[data-del]", row).onclick = async () => {
        if (!(await confirm({ title: "Delete expense?", text: e.description, submitLabel: "Delete", submitClass: "btn--danger" }))) return;
        await api(`/expenses/${e.id}`, { method: "DELETE" }); toast("success", "Expense deleted"); CA.refreshView();
      };
      $(".list", card).append(row);
    });
    $("#exp-new", head).onclick = async () => {
      const deals = await api("/deals").catch(() => []);
      modal({
        title: "Add expense",
        body: `<div class="form-grid">
          <div class="field"><label class="label" for="ex-d">Date</label><input class="input" id="ex-d" name="spent_on" type="date" required value="${to}"></div>
          <div class="field"><label class="label" for="ex-c">Category</label><select class="select" id="ex-c" name="category">${Object.entries(CAT).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>
          <div class="field"><label class="label" for="ex-a">Amount (&#8377;)</label><input class="input" id="ex-a" name="amount_inr" type="number" min="1" required></div>
          <div class="field full"><label class="label" for="ex-desc">Description</label><input class="input" id="ex-desc" name="description" required></div>
          <div class="field"><label class="label" for="ex-v">Vendor</label><input class="input" id="ex-v" name="vendor"></div>
          <div class="field"><label class="label" for="ex-deal">Deal</label><select class="select" id="ex-deal" name="deal_id"><option value="">—</option>
            ${deals.map(d => `<option value="${d.id}">#${d.id} ${esc(d.brand)}</option>`).join("")}</select></div></div>`,
        onSubmit: async d => {
          const json = { ...d, amount_inr: Number(d.amount_inr), deal_id: d.deal_id ? Number(d.deal_id) : null };
          await api("/expenses", { method: "POST", json });
          toast("success", "Expense added"); CA.refreshView();
        },
      });
    };
    v.replaceChildren(head, strip, card);
  }

  CA.invoicesPage = { render: renderInvoices };
  CA.views.expenses = renderExpenses;
})();
