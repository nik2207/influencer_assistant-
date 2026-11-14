/* Creator Analytics Hub (Phase 7). */
(function () {
  "use strict";
  const { $, $$, esc, h, api, state, icon, toast, busy, modal, confirm, emptyState, skeleton, friendlyError } = CA;

  const METRICS = ["followers", "reach", "impressions", "views", "engagement", "engagement_rate"];

  function defaultRange() {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - 30);
    return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10) };
  }

  function srcBadge(source, confidence) {
    const cls = confidence === "verified" ? " src-badge--verified" : "";
    return `<span class="src-badge${cls}" title="${esc(source)} / ${esc(confidence)}">${esc(source)}</span>`;
  }

  function barChart(series) {
    if (!series?.length) return emptyState({ icon: "chart", title: CA.ui("an_no_chart"), text: CA.ui("an_no_chart_sub") });
    const max = Math.max(...series.map(p => p.value), 1);
    const bars = series.map(p => {
      const ht = Math.max(4, Math.round(100 * p.value / max));
      return `<span style="height:${ht}px" title="${esc(p.period)}: ${p.value}"></span>`;
    }).join("");
    return h(`<div class="chart-bars" role="img" aria-label="Growth chart">${bars}</div>`);
  }

  async function downloadExport(path, fname) {
    const r = await fetch(path, { headers: { Authorization: "Bearer " + state.tok.access_token } });
    if (!r.ok) throw new Error("Download failed");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await r.blob());
    a.download = fname;
    document.body.append(a);
    a.click();
    a.remove();
  }

  function addMetricModal(platforms) {
    const plats = platforms.length ? platforms : [{ platform: "youtube", label: "YouTube" }];
    modal({
      title: CA.ui("an_add_metric"),
      submitLabel: CA.ui("an_save_metric"),
      body: `<div class="form-grid">
        <div class="field"><label class="label" for="m-plat">${CA.ui("an_platform")}</label>
          <select class="select" id="m-plat" name="platform" required>
            ${plats.map(p => `<option value="${esc(p.platform)}">${esc(p.label || p.platform)}</option>`).join("")}
          </select></div>
        <div class="field"><label class="label" for="m-key">${CA.ui("an_metric")}</label>
          <select class="select" id="m-key" name="metric_key">${METRICS.map(k => `<option value="${k}">${k.replace(/_/g, " ")}</option>`).join("")}</select></div>
        <div class="field"><label class="label" for="m-val">${CA.ui("an_value")}</label>
          <input class="input" id="m-val" name="value" type="number" min="0" step="any" required></div>
        <div class="field"><label class="label" for="m-from">${CA.ui("an_period_start")}</label>
          <input class="input" id="m-from" name="period_start" type="date"></div>
        <div class="field full"><label class="label" for="m-notes">${CA.ui("an_notes")}</label>
          <input class="input" id="m-notes" name="notes"></div></div>`,
      onSubmit: async d => {
        const json = {
          platform: d.platform,
          metric_key: d.metric_key,
          value: Number(d.value),
          period_start: d.period_start || null,
          notes: d.notes || "",
          social_account_id: plats.find(p => p.platform === d.platform)?.social_account_id || null,
        };
        await api("/analytics/metrics", { method: "POST", json });
        toast("success", CA.ui("an_metric_saved"));
        CA.refreshView();
      },
    });
  }

  async function renderAnalytics(v, ctx) {
    const range = defaultRange();
    const head = h(`<div class="page-head"><div>
      <h1 class="page-title">${esc(CA.ui("an_title"))}</h1>
      <p class="page-sub">${esc(CA.ui("an_sub"))}</p></div>
      <div class="page-actions">
        <button class="btn btn--secondary" type="button" id="an-csv">${icon("download")}${CA.ui("an_export_csv")}</button>
        <button class="btn btn--secondary" type="button" id="an-pdf">${icon("download")}${CA.ui("an_export_pdf")}</button>
        <button class="btn btn--accent" type="button" id="an-add">${icon("plus")}${CA.ui("an_add_metric")}</button>
      </div></div>`);
    if (!ctx.silent) v.replaceChildren(head, skeleton());

    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    const from = params.get("from") || range.from;
    const to = params.get("to") || range.to;
    const chartPlat = params.get("platform") || "";
    const chartMetric = params.get("metric") || "followers";
    const grain = params.get("grain") || "week";

    const qs = `from_date=${from}&to_date=${to}`;
    const [overview, platforms, chart, compare, insights, content] = await Promise.allSettled([
      api(`/analytics/overview?${qs}`),
      api("/analytics/platforms"),
      chartPlat ? api(`/analytics/chart?platform=${chartPlat}&metric_key=${chartMetric}&${qs}&grain=${grain}`) : null,
      api(`/analytics/compare?metric_key=followers&${qs}`),
      api(`/analytics/insights?${qs}`),
      api("/analytics/content?limit=8"),
    ]);
    if (!ctx.alive()) return;
    if (overview.status === "rejected") throw overview.reason;
    const ov = overview.value;
    const plats = platforms.status === "fulfilled" ? platforms.value : [];
    const chartData = chart.status === "fulfilled" ? chart.value : [];
    const cmp = compare.status === "fulfilled" ? compare.value : [];
    const insightText = insights.status === "fulfilled" ? insights.value.text : "";
    const top = content.status === "fulfilled" ? content.value : [];

    const filterWrap = h(`<div class="analytics-filters card">
      <div class="field"><label class="label" for="an-from">${CA.ui("an_from")}</label>
        <input class="input" id="an-from" type="date" value="${esc(from)}"></div>
      <div class="field"><label class="label" for="an-to">${CA.ui("an_to")}</label>
        <input class="input" id="an-to" type="date" value="${esc(to)}"></div>
      <div class="field"><label class="label" for="an-grain">${CA.ui("an_grain")}</label>
        <select class="select" id="an-grain"><option value="day">Daily</option>
          <option value="week" ${grain === "week" ? "selected" : ""}>Weekly</option>
          <option value="month" ${grain === "month" ? "selected" : ""}>Monthly</option></select></div>
      <button class="btn btn--primary" type="button" id="an-apply">${CA.ui("an_apply")}</button>
    </div>`);

    const grid = h(`<div class="analytics-grid"></div>`);
    (ov.platforms || []).forEach(p => {
      const card = h(`<section class="card analytics-card"><h3>${esc(p.label)}</h3>
        <p class="caption">${esc(p.handle || p.platform)} · ${(p.followers || 0).toLocaleString("en-IN")} followers
          · ${esc(p.connection_status || "manual")}</p><div class="metrics"></div></section>`);
      const box = $(".metrics", card);
      const mets = p.metrics || {};
      if (!Object.keys(mets).length) box.append(h(`<p class="caption">${CA.ui("an_no_metrics")}</p>`));
      else Object.entries(mets).forEach(([k, info]) => {
        box.append(h(`<div class="metric-pill"><strong>${esc(k.replace(/_/g, " "))}</strong>
          ${Number(info.value).toLocaleString("en-IN")} ${srcBadge(info.source, info.confidence)}</div>`));
      });
      const gf = p.growth_followers;
      if (gf?.points >= 2) {
        box.append(h(`<p class="caption">${CA.ui("an_growth")}: ${gf.delta > 0 ? "+" : ""}${gf.delta.toLocaleString("en-IN")}
          (${gf.pct > 0 ? "+" : ""}${gf.pct}%)</p>`));
      }
      const conn = p.oauth?.status === "connected";
      const syncBtn = h(`<button class="btn btn--ghost btn--sm" type="button">${conn ? CA.ui("an_sync") : CA.ui("an_connect")}</button>`);
      syncBtn.onclick = () => busy(syncBtn, "…", async () => {
        try {
          if (p.platform === "youtube" && !conn) {
            const r = await api("/analytics/connect/youtube");
            location.href = r.url;
            return;
          }
          const r = await api(`/analytics/sync/${p.platform}`, { method: "POST" });
          toast("info", r.note || CA.ui("an_sync_done"));
          CA.refreshView();
        } catch (e) {
          toast("error", friendlyError(e, CA.ui("an_connect_fail")));
        }
      });
      card.append(syncBtn);
      grid.append(card);
    });
    if (!grid.children.length) {
      grid.append(emptyState({ icon: "chart", title: CA.ui("an_no_platforms"), text: CA.ui("an_no_platforms_sub") }));
    }

    const chartPlatSel = plats.length ? plats[0].platform : "youtube";
    const chartCard = h(`<section class="card"><h2 class="card__title">${CA.ui("an_chart_title")}</h2>
      <div class="cluster" style="margin-bottom:1rem">
        <select class="select" id="an-cplat">${plats.map(p => `<option value="${p.platform}" ${p.platform === (chartPlat || chartPlatSel) ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select>
        <select class="select" id="an-cmet">${METRICS.map(m => `<option value="${m}" ${m === chartMetric ? "selected" : ""}>${m}</option>`).join("")}</select>
      </div></section>`);
    let series = chartData;
    if (!chartPlat && plats.length) {
      try { series = await api(`/analytics/chart?platform=${chartPlatSel}&metric_key=${chartMetric}&${qs}&grain=${grain}`); } catch (e) { series = []; }
    }
    chartCard.append(barChart(series || []));

    const cmpCard = h(`<section class="card"><h2 class="card__title">${CA.ui("an_compare")}</h2><div class="list"></div></section>`);
    if (!cmp.length) $(".list", cmpCard).append(h(`<p class="caption">${CA.ui("an_no_compare")}</p>`));
    cmp.forEach(row => {
      $(".list", cmpCard).append(h(`<div class="row"><div class="row__top">
        <span class="row__title">${esc(row.platform)}</span>
        <span>${row.latest != null ? Number(row.latest).toLocaleString("en-IN") : "—"}</span></div>
        <div class="caption">${CA.ui("an_growth")}: ${row.delta > 0 ? "+" : ""}${(row.delta || 0).toLocaleString("en-IN")}
          (${row.pct || 0}%) · ${row.points || 0} points</div></div>`));
    });

    const topCard = h(`<section class="card"><h2 class="card__title">${CA.ui("an_top_content")}</h2><div class="list"></div></section>`);
    if (!top.length) $(".list", topCard).append(emptyState({ icon: "sparkle", title: CA.ui("an_no_content"), text: "" }));
    top.forEach(c => {
      $(".list", topCard).append(h(`<div class="row"><div class="row__top">
        <span class="row__title">${esc(c.title || "Untitled")}</span>
        <span>${Number(c.views).toLocaleString("en-IN")} views</span></div>
        <div class="caption">${esc(c.platform)} · ${Number(c.engagement).toLocaleString("en-IN")} engagement ${srcBadge(c.source, "verified")}</div></div>`));
    });

    const importRow = h(`<section class="card"><h2 class="card__title">${CA.ui("an_import")}</h2>
      <p class="caption">${CA.ui("an_import_hint")}</p>
      <input type="file" id="an-file" accept=".csv,text/csv"></section>`);

    const insightsCard = h(`<section class="card"><h2 class="card__title">${CA.ui("an_insights")}</h2>
      <div class="insights-box">${esc(insightText)}</div></section>`);

    v.replaceChildren(head, filterWrap, grid, chartCard, cmpCard, topCard, importRow, insightsCard);

    const applyRange = () => {
      const f = $("#an-from").value, t = $("#an-to").value, g = $("#an-grain").value;
      const plat = $("#an-cplat")?.value || chartPlatSel;
      const met = $("#an-cmet")?.value || chartMetric;
      location.hash = `#/analytics?from=${f}&to=${t}&grain=${g}&platform=${plat}&metric=${met}`;
    };
    $("#an-apply", filterWrap).onclick = applyRange;
    $("#an-cplat", chartCard)?.addEventListener("change", applyRange);
    $("#an-cmet", chartCard)?.addEventListener("change", applyRange);

    $("#an-add", head).onclick = () => addMetricModal(plats.length ? plats : ov.platforms || []);
    $("#an-csv", head).onclick = () => busy($("#an-csv", head), "…", async () => {
      await downloadExport(`/analytics/export/csv?from_date=${from}&to_date=${to}`, `analytics-${from}.csv`);
      toast("success", CA.ui("an_downloaded"));
    });
    $("#an-pdf", head).onclick = () => busy($("#an-pdf", head), "…", async () => {
      await downloadExport(`/analytics/export/pdf?from_date=${from}&to_date=${to}`, `analytics-${from}.pdf`);
      toast("success", CA.ui("an_downloaded"));
    });

    $("#an-file", importRow).onchange = async e => {
      const file = e.target.files?.[0];
      if (!file) return;
      const fd = new FormData();
      fd.append("file", file);
      try {
        const r = await fetch("/analytics/import", {
          method: "POST",
          headers: { Authorization: "Bearer " + state.tok.access_token },
          body: fd,
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || "Import failed");
        toast("success", `${CA.ui("an_imported")} (${j.row_count} rows)`);
        if (j.errors?.length) toast("info", j.errors.slice(0, 2).join("; "));
        CA.refreshView();
      } catch (err) {
        toast("error", friendlyError(err, CA.ui("an_import_fail")));
      }
      e.target.value = "";
    };

    if (location.hash.includes("connect=ok")) toast("success", CA.ui("an_connected"));
    if (location.hash.includes("connect=error")) toast("error", CA.ui("an_connect_fail"));
  }

  CA.views.analytics = renderAnalytics;
})();
