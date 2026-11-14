/* Campaign ROI (Phase 12B). Uses persisted invoices, payments, expenses only. */
(function () {
  "use strict";
  const { $, $$, esc, h, api, state, icon, toast, busy, money, friendlyError, emptyState, skeleton, modal } = CA;

  function params() {
    return new URLSearchParams(location.hash.split("?")[1] || "");
  }

  function chartCompare(rows) {
    if (!rows.length) return h(`<p class="caption">No campaigns to compare.</p>`);
    const max = Math.max(...rows.map(r => Math.max(r.invoiced_inr, r.received_inr, 1)));
    const box = h(`<div class="roi-chart stack"></div>`);
    rows.slice(0, 8).forEach(r => {
      const row = h(`<div class="roi-bar"><div class="caption">${esc(r.brand)} #${r.deal_id}</div>
        <div class="roi-bar__track"><span class="roi-bar__inv" style="width:${(r.invoiced_inr / max) * 100}%"></span>
        <span class="roi-bar__rec" style="width:${(r.received_inr / max) * 100}%"></span></div>
        <div class="caption">Inv ${money(r.invoiced_inr)} · Rec ${money(r.received_inr)}${r.roi_pct != null ? ` · ROI ${r.roi_pct}%` : ""}</div></div>`);
      box.append(row);
    });
    box.append(h(`<p class="hint">Dark bar = invoiced · accent = received (from stored payments).</p>`));
    return box;
  }

  function roiCard(c) {
    const est = c.invoiced_revenue.is_estimate ? " (est.)" : "";
    return h(`<article class="card stack roi-card" data-id="${c.deal_id}">
      <div class="row__top"><span class="deal__brand">${esc(c.brand)}</span><span class="badge">#${c.deal_id}</span></div>
      <p class="caption">${esc(c.kind)} · ${esc(c.status)}</p>
      <div class="roi-metrics">
        <div><span class="label">Invoiced</span><strong>${money(c.invoiced_revenue.amount_inr)}${est}</strong></div>
        <div><span class="label">Received</span><strong>${money(c.received_revenue.amount_inr)}</strong></div>
        <div><span class="label">Outstanding</span><strong>${money(c.outstanding.amount_inr)}</strong></div>
        <div><span class="label">Profit (est.)</span><strong>${money(c.profit_estimate.amount_inr)}</strong></div>
      </div>
      <p class="hint">${esc(c.disclaimer)}</p>
      <div class="cluster">
        <button type="button" class="btn btn--secondary btn--sm" data-roi="detail">Details</button>
        <button type="button" class="btn btn--ghost btn--sm" data-roi="tips">AI tips</button>
      </div></article>`);
  }

  async function showDetail(id) {
    const c = await api(`/roi/deals/${id}`);
    const vs = c.estimated_vs_actual || {};
    modal({
      title: `${c.brand} — ROI`,
      submitLabel: "Close",
      body: `<p class="hint">${esc(c.disclaimer)}</p>
        <ul class="stack" style="list-style:none;padding:0">
          <li><strong>Invoiced</strong> ${money(c.invoiced_revenue.amount_inr)} <em>(${esc(c.invoiced_revenue.source)})</em></li>
          <li><strong>Received</strong> ${money(c.received_revenue.amount_inr)}</li>
          <li><strong>Outstanding</strong> ${money(c.outstanding.amount_inr)}</li>
          <li><strong>Actual expenses</strong> ${money(c.actual_expenses.amount_inr)}</li>
          <li><strong>Est. production</strong> ${money(c.estimated_expenses.amount_inr)}</li>
          <li><strong>Net cash flow</strong> ${money(c.net_cash_flow.amount_inr)}</li>
          <li><strong>ROI</strong> ${c.roi_pct != null ? c.roi_pct + "%" : "—"}</li>
          <li><strong>Cost / engagement</strong> ${c.cost_per_engagement != null ? money(c.cost_per_engagement) : "—"}</li>
          <li><strong>Revenue / deliverable</strong> ${c.revenue_per_deliverable != null ? money(c.revenue_per_deliverable) : "—"}</li>
        </ul>
        <p class="caption">Deliverables: ${vs.deliverables ? vs.deliverables.actual_count : 0} actual / ${vs.deliverables ? vs.deliverables.estimated_count : 0} est.</p>`,
      onSubmit: () => {},
    });
  }

  async function render(host, ctx) {
    const p = params();
    const brand = p.get("brand") || "";
    const from = p.get("from") || "";
    const to = p.get("to") || "";
    const qsp = new URLSearchParams();
    if (brand) qsp.set("brand", brand);
    if (from) qsp.set("from_date", from);
    if (to) qsp.set("to_date", to);

    const head = h(`<div class="page-head"><div>
      <h1 class="page-title">${esc(CA.ui("roi_title"))}</h1>
      <p class="page-sub">${esc(CA.ui("roi_sub"))}</p></div>
      <div class="page-actions cluster">
        <button class="btn btn--secondary" type="button" id="roi-back">${esc(CA.ui("roi_back"))}</button>
        <a class="btn btn--ghost" id="roi-csv" href="#" download="campaign-roi.csv">${icon("download")} CSV</a>
      </div></div>`);
    $("#roi-back", head).onclick = () => { location.hash = "#/deals"; CA.refreshView(); };
    $("#roi-csv", head).onclick = async e => {
      e.preventDefault();
      try {
        const tok = state.tok.access_token;
        const r = await fetch("/roi/campaigns/export.csv?" + qsp.toString(), { headers: { Authorization: "Bearer " + tok } });
        const blob = await r.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "campaign-roi.csv";
        a.click();
      } catch (err) { toast("error", friendlyError(err)); }
    };

    const filters = h(`<motion class="card form-grid" style="padding:12px"></motion>`.replace(/motion/g, "div"));
    filters.innerHTML = `
      <div class="field"><label class="label">${esc(CA.ui("roi_brand"))}</label><input class="input" id="roi-brand" value="${esc(brand)}"></div>
      <div class="field"><label class="label">${esc(CA.ui("roi_from"))}</label><input class="input" type="date" id="roi-from" value="${esc(from)}"></div>
      <div class="field"><label class="label">${esc(CA.ui("roi_to"))}</label><input class="input" type="date" id="roi-to" value="${esc(to)}"></div>
      <div class="field" style="align-self:end"><button class="btn btn--secondary" type="button" id="roi-go">${esc(CA.ui("roi_apply"))}</button></div>`;
    $("#roi-go", filters).onclick = () => {
      const np = new URLSearchParams();
      np.set("tab", "roi");
      const b = $("#roi-brand").value.trim(); if (b) np.set("brand", b);
      if ($("#roi-from").value) np.set("from", $("#roi-from").value);
      if ($("#roi-to").value) np.set("to", $("#roi-to").value);
      location.hash = `#/deals?${np.toString()}`;
      CA.refreshView();
    };

    if (!ctx.silent) host.replaceChildren(head, filters, skeleton("cards"));
    let data;
    try { data = await api("/roi/campaigns?" + qsp.toString()); } catch (e) {
      if (!ctx.alive()) return;
      host.replaceChildren(head, filters, emptyState({ icon: "alert", title: CA.ui("couldnt_load"), text: friendlyError(e) }));
      return;
    }
    if (!ctx.alive()) return;

    const totals = h(`<section class="card"><h2 class="card__title">${esc(CA.ui("roi_overview"))}</h2>
      <div class="dash-metrics">${["invoiced_inr", "received_inr", "outstanding_inr", "profit_estimate_inr"].map(k =>
        `<div class="stat"><span class="caption">${k.replace(/_/g, " ")}</span><span class="stat__value">${money(data.totals[k] || 0)}</span></div>`).join("")}
      </div></section>`);

    const chart = h(`<section class="card"><h2 class="card__title">${esc(CA.ui("roi_compare"))}</h2></section>`);
    chart.append(chartCompare(data.compare));

    const grid = h(`<motion class="deal-grid"></motion>`.replace(/motion/g, "div"));
    if (!data.campaigns.length) grid.append(emptyState({ icon: "briefcase", title: CA.ui("roi_empty"), text: CA.ui("roi_empty_sub") }));
    data.campaigns.forEach(c => {
      const card = roiCard(c);
      $("[data-roi=detail]", card).onclick = () => showDetail(c.deal_id);
      $("[data-roi=tips]", card).onclick = e => busy(e.currentTarget, "…", async () => {
        try {
          const t = await api(`/roi/deals/${c.deal_id}/suggestions`);
          modal({ title: "Pricing & profitability", submitLabel: "Close",
            body: `<p class="hint">${esc(t.note || "")}</p><ul>${(t.suggestions || []).map(s => `<li>${esc(s)}</li>`).join("")}</ul>`,
            onSubmit: () => {} });
        } catch (err) { toast("error", friendlyError(err)); }
      });
      grid.append(card);
    });

    host.replaceChildren(head, filters, totals, chart, grid);
  }

  CA.campaignRoiPage = { render };
})();
