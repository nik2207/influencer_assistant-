/* App shell: sign-in, hash router, navigation, account menu and start-up. */
(function () {
  "use strict";
  const { $, $$, esc, h, api, state, icon, toast, busy, modal, errorState, friendlyError } = CA;

  const NAV = [
    { id: "dashboard", label: "Dashboard", icon: "home" },
    { id: "deals", label: "Deals", icon: "briefcase" },
    { id: "inbox", label: "Inbox", icon: "mail" },
    { id: "schedule", label: "Schedule", icon: "calendar" },
    { id: "invoices", label: "Invoices", icon: "receipt" },
    { id: "expenses", label: "Expenses", icon: "receipt" },
    { id: "analytics", label: "Analytics", icon: "chart" },
    { id: "content", label: "Content", icon: "sparkle" },
    { id: "mediakit", label: "Media kit", icon: "receipt" },
    { id: "brands", label: "Brands", icon: "store" },
    { id: "assistant", label: "Assistant", icon: "sparkle" },
  ];
  const EXTRA = { profile: { id: "profile", label: "Profile & preferences", icon: "sparkle" } };  // pages outside the main nav
  const navUiKey = id => ({ dashboard: "nav_dashboard", deals: "nav_deals", inbox: "nav_inbox", schedule: "nav_schedule",
    invoices: "nav_invoices", expenses: "nav_expenses", analytics: "nav_analytics", content: "nav_content",
    mediakit: "nav_mediakit", brands: "nav_brands",
    assistant: "nav_assistant" }[id] || "nav_dashboard");
  const navLabel = n => (n.id === "deals" ? CA.t("deals") : CA.ui(navUiKey(n.id)));
  const MOBILE_PRIMARY = ["dashboard", "deals", "inbox", "schedule", "assistant"];
  const LANGS = { en: "English", hi: "\u0939\u093F\u0928\u094D\u0926\u0940", mr: "\u092E\u0930\u093E\u0920\u0940" };
  const LANG_SHORT = { en: "EN", hi: "\u0939\u093F", mr: "\u092E\u0930\u093E" };

  let renderId = 0, current = "dashboard";

  /* ---------- routing ---------- */
  const routeFromHash = () => {
    const r = (location.hash.replace(/^#\/?/, "") || "dashboard").split("?")[0];
    return NAV.some(n => n.id === r) || EXTRA[r] ? r : "dashboard";
  };

  CA.go = name => {
    if (location.hash === "#/" + name) render({ silent: true }); else location.hash = "#/" + name;
  };
  CA.refreshView = () => { if (state.me) render({ silent: true }); };

  function markNav(route) {
    $$("#topnav a, #bottomnav a").forEach(a => {
      if (a.dataset.route === route) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    const more = $("#moreBtn");
    if (more) { if (!MOBILE_PRIMARY.includes(route)) more.setAttribute("aria-current", "page"); else more.removeAttribute("aria-current"); }
  }

  async function render(opts = {}) {
    if (!state.me) return;
    const route = routeFromHash();
    const changed = route !== current;
    current = route;
    const rid = ++renderId;
    markNav(route);
    CA.chat.onRoute(route);
    const navItem = NAV.find(n => n.id === route) || EXTRA[route];
    const label = route === "deals" ? CA.t("deals") : (navItem.id ? CA.ui(navUiKey(navItem.id)) : navItem.label);
    document.body.classList.toggle("page-profile", route === "profile");
    document.body.classList.toggle("page-assistant", route === "assistant");
    document.title = label + " \u00B7 Creator Assistant";
    $("#shell").classList.toggle("shell--assistant", route === "assistant");
    const view = $("#view");
    if (route === "assistant") {
      view.replaceChildren();
      const log = $("#log"); log.scrollTop = log.scrollHeight;
      if (!opts.silent) setTimeout(() => $("#msg").focus(), 50);
      return;
    }
    if (!opts.silent || changed) window.scrollTo({ top: 0 });
    const ctx = { alive: () => rid === renderId, silent: !!opts.silent && !changed };
    try { await CA.views[route](view, ctx); }
    catch (err) {
      if (!ctx.alive()) return;
      view.replaceChildren(errorState({ title: `We couldn't load ${label.toLowerCase()}`,
        text: friendlyError(err, "Something went wrong on our side. Please try again."), onRetry: () => render() }));
    }
    if (!opts.silent && ctx.alive()) { const m = $("#main"); m.focus({ preventScroll: true }); }
  }

  /* ---------- navigation ---------- */
  function buildNav() {
    $("#topnav").innerHTML = NAV.map(n => `<a href="#/${n.id}" data-route="${n.id}">${icon(n.icon)}<span>${navLabel(n)}</span></a>`).join("");
    const prim = NAV.filter(n => MOBILE_PRIMARY.includes(n.id));
    $("#bottomnav").innerHTML = prim.map(n => `<a href="#/${n.id}" data-route="${n.id}">${icon(n.icon)}<span>${n.id === "dashboard" ? CA.ui("nav_home") : navLabel(n)}</span></a>`).join("") +
      `<button class="navbtn" id="moreBtn" type="button" aria-haspopup="dialog">${icon("more")}<span>${CA.ui("nav_more")}</span></button>`;
    $("#moreBtn").onclick = () => {
      const sheet = $("#moreSheet");
      sheet.innerHTML = `<div class="stack">${NAV.filter(n => !MOBILE_PRIMARY.includes(n.id)).map(n =>
        `<a class="menu__item" href="#/${n.id}">${icon(n.icon)}<span>${navLabel(n)}</span></a>`).join("")}
        <a class="menu__item" href="#/profile">${icon("sparkle")}<span>Profile &amp; preferences</span></a>
        <button class="menu__item" type="button" id="sheetClose">${icon("x")}<span>Close</span></button></div>`;
      $$("a", sheet).forEach(a => a.addEventListener("click", () => sheet.close()));
      $("#sheetClose", sheet).onclick = () => sheet.close();
      sheet.addEventListener("click", e => { if (e.target === sheet) sheet.close(); }, { once: true });
      sheet.showModal();
    };
  }

  /* ---------- account menu ---------- */
  function paintAccount() {
    const me = state.me;
    const name = me.name || me.email.split("@")[0];
    $("#avatar").textContent = name.trim().charAt(0).toUpperCase() || "?";
    $("#acctName").textContent = name;
    $("#acctHandle").textContent = me.handle || me.email;
    $("#langChip").textContent = LANG_SHORT[me.language] || "EN";
  }

  function closeMenu() { $("#acctMenu").classList.add("hidden"); $("#acctBtn").setAttribute("aria-expanded", "false"); }

  async function openMenu() {
    if (CA.chat && CA.chat.close) CA.chat.close();
    const menu = $("#acctMenu"), me = state.me;
    const speak = $("#speak") ? $("#speak").checked : false;
    menu.innerHTML = `<div class="menu__block"><strong>${esc(me.name || me.email)}</strong><span class="caption">${esc((state.profile && state.profile.personalization ? state.profile.personalization.label + " \u00B7 " : "") + (me.handle || me.email))}</span></div>
      <a class="menu__item" href="#/profile" id="profLink">${icon("sparkle")}<span>Profile &amp; preferences</span></a>
      <div class="menu__sep"></div>
      <div class="menu__block"><label class="label" for="lang">Reply language</label>
        <select class="select" id="lang">${Object.entries(LANGS).map(([k, v]) => `<option value="${k}" ${me.language === k ? "selected" : ""}>${v}</option>`).join("")}</select></div>
      <div class="menu__block"><label class="checkbox"><input type="checkbox" id="speak" ${speak ? "checked" : ""}> Read replies aloud</label></div>
      <div class="menu__sep"></div>
      <div class="menu__block"><span class="caption">Integrations</span>
        <a class="menu__item" href="#/inbox" style="padding:.4rem 0"><span class="dot" id="dGmail"></span><span style="flex:1">Gmail</span><span class="caption" id="tGmail">Checking...</span></a>
        <a class="menu__item" href="#/schedule" style="padding:.4rem 0"><span class="dot" id="dCal"></span><span style="flex:1">Google Calendar</span><span class="caption" id="tCal">Checking...</span></a>
        <button class="menu__item" type="button" id="tgBtn" style="padding:.4rem 0">${icon("send2")}<span>Link Telegram</span>${me.telegram_linked ? '<span class="badge badge--success" style="margin-left:auto">Linked</span>' : ""}</button></div>
      <div class="menu__sep"></div>
      <button class="menu__item" type="button" id="outBtn">${icon("logout")}<span>Log out</span></button>`;
    menu.classList.remove("hidden"); $("#acctBtn").setAttribute("aria-expanded", "true");
    $$("a", menu).forEach(a => a.addEventListener("click", closeMenu));

    $("#lang").onchange = async e => {
      try {
        const u = await api("/auth/me", { method: "PATCH", json: { language: e.target.value } });
        state.me = u; paintAccount(); CA.applyLanguage(); buildNav(); markNav(current); CA.refreshView(); CA.chat.refreshWelcome();
        toast("success", `${CA.ui("lang_toast")} ${LANGS[u.language]}`);
      }
      catch (err) { toast("error", friendlyError(err, "We couldn't change the language.")); }
    };
    $("#outBtn").onclick = CA.logout;
    $("#tgBtn").onclick = async e => {
      closeMenu();
      try {
        const r = await api("/auth/telegram-code", { method: "POST" });
        const body = h(`<div class="stack"><p>Open your Telegram bot and send this message:</p><div class="code-box">/link ${esc(r.code)}</div>
          <p class="caption">${esc(r.instruction)}</p><button class="btn btn--secondary" type="button">${icon("copy")}Copy command</button></div>`);
        $("button", body).onclick = async () => { try { await navigator.clipboard.writeText("/link " + r.code); toast("success", "Command copied"); } catch (er) { toast("warning", "Couldn't copy. Type the command manually."); } };
        modal({ title: "Link Telegram", bodyNode: body });
      } catch (err) { toast("error", friendlyError(err, "We couldn't create a link code.")); }
    };

    const [g, c] = await Promise.allSettled([api("/gmail/status"), api("/calendar/status")]);
    if (!menu.isConnected || menu.classList.contains("hidden")) return;
    const set = (d, t, on, txt) => { $(d).classList.toggle("dot--on", on); $(t).textContent = txt; };
    set("#dGmail", "#tGmail", g.status === "fulfilled" && g.value.connected, g.status !== "fulfilled" ? "Unavailable" : !g.value.configured ? "Not set up" : g.value.connected ? "Connected" : "Connect");
    set("#dCal", "#tCal", c.status === "fulfilled" && c.value.granted, c.status !== "fulfilled" ? "Unavailable" : !c.value.configured ? "Not set up" : c.value.granted ? "Connected" : "Connect");
  }

  function bindMenu() {
    $("#acctBtn").onclick = () => ($("#acctMenu").classList.contains("hidden") ? openMenu() : closeMenu());
    $("#langChip").onclick = () => { if ($("#acctMenu").classList.contains("hidden")) openMenu(); else closeMenu(); };
    document.addEventListener("click", e => { if (!e.target.closest(".account") && !e.target.closest("#langChip")) closeMenu(); });
    document.addEventListener("keydown", e => { if (e.key === "Escape") closeMenu(); });
  }

  /* Called by the profile page after a save. Keeps the header, nav wording and chat suggestions in step. */
  CA.profileChanged = p => {
    state.me = { ...state.me, ...p.user };
    paintAccount(); CA.applyLanguage(); buildNav(); markNav(current);
    CA.chat.refreshWelcome(); CA.refreshView();
  };

  /* ---------- sign in ---------- */
  let signup = false;
  function bindAuth() {
    const err = $("#authErr");
    const showErr = m => { err.textContent = m; err.classList.toggle("hidden", !m); };
    $("#toggle").onclick = () => {
      signup = !signup; showErr("");
      $("#nameField").classList.toggle("hidden", !signup);
      $("#authBtn").textContent = signup ? "Create account" : "Log in";
      $("#toggle").textContent = signup ? "I already have an account" : "Create an account";
      $("#authTitle").textContent = signup ? "Create your account" : "Welcome back";
      $("#authSub").textContent = signup ? "Start managing your creator business." : "Log in to your creator workspace.";
      $("#password").autocomplete = signup ? "new-password" : "current-password";
    };
    $("#authForm").onsubmit = async e => {
      e.preventDefault(); showErr("");
      const email = $("#email").value.trim(), password = $("#password").value;
      if (!email || password.length < 8) { showErr("Enter your email and a password of at least 8 characters."); return; }
      await busy($("#authBtn"), signup ? "Creating account..." : "Logging in...", async () => {
        try {
          if (signup) {
            state.tok = await api("/auth/register", { method: "POST", json: { email, password, name: $("#name").value } });
          } else {
            const r = await fetch("/auth/login", { method: "POST", body: new URLSearchParams({ username: email, password }) });
            if (!r.ok) { let d = ""; try { d = (await r.json()).detail; } catch (x) { /* ignore */ } throw new Error(r.status === 429 ? "Too many attempts. Please wait a minute and try again." : (typeof d === "string" && d) || "Login failed."); }
            state.tok = await r.json();
          }
          localStorage.setItem("tok", JSON.stringify(state.tok));
          location.hash = "#/dashboard";
          await boot();
        } catch (ex) { showErr(friendlyError(ex, "We couldn't log you in. Please try again.")); }
      });
    };
  }

  function showAuth() {
    $("#app").classList.add("hidden"); $("#auth").classList.remove("hidden");
    document.title = "Log in \u00B7 Creator Assistant";
    CA.readFlashToast();
  }

  /* ---------- start-up ---------- */
  let booted = false;
  async function boot() {
    if (!state.tok) return showAuth();
    try { state.me = await api("/auth/me"); } catch (e) { localStorage.removeItem("tok"); state.tok = null; return showAuth(); }
    state.stages = await api("/deals/stages").catch(() => []);
    $("#auth").classList.add("hidden"); $("#app").classList.remove("hidden");
    await CA.loadProfile();  // creator type, labels and suggestions (the app still works if this fails)
    buildNav(); paintAccount(); CA.applyLanguage();
    if (!booted) { bindMenu(); window.addEventListener("hashchange", () => render()); booted = true; }
    await CA.chat.loadHistory();

    const q = new URLSearchParams(location.search), g = q.get("gmail");
    if (g) {
      history.replaceState(null, "", location.pathname);
      location.hash = q.get("cal") ? "#/schedule" : "#/inbox";
      if (g === "connected") toast("success", q.get("cal") ? "Google connected. Gmail and Calendar are ready." : "Gmail connected successfully");
      else if (g === "denied") toast("warning", "Google wasn't connected because access was declined.");
      else toast("error", "The Google connection failed. Please try again.");
    }
    await render();
  }

  bindAuth();
  boot();
})();
