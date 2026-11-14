/* Assistant chat: messages, approvals, voice recording, read-aloud, and the floating window
   (open/close, drag, resize, expand, remembered position). Chat behaviour is unchanged. */
(function () {
  "use strict";
  const { $, esc, h, api, state, toast, icon, friendlyError, confirm } = CA;
  const SUGGESTIONS = ["Add a barter deal with Mamaearth", "Book a cab from Panvel to Bandra tomorrow at 4 pm",
    "Check my inbox", "Any follow-ups pending?"];
  let sending = false, loading = false, voiceBusy = false;
  const MIN_RECORD_MS = 1200;
  const VOICE_STT_KEY = "ca.voice.stt";
  let lastVoiceBlob = null, recStartedAt = 0;

  const log = () => $("#log");
  const clearWelcome = () => { const w = $(".chat__welcome"); if (w) w.remove(); };
  const toBottom = () => { const l = log(); l.scrollTop = l.scrollHeight; };
  const refresh = () => { if (CA.refreshView) CA.refreshView(); };

  function bubble(role, text, opts = {}) {
    clearWelcome();
    const extra = opts.voice ? " voice" : opts.err ? " err" : "";
    const el = h(`<div class="msg ${role}${extra}"></div>`);
    el.textContent = text;
    if (opts.voice && opts.detected) {
      const b = h(`<span class="msg__badge">${CA.ui("voice_detected")}: ${esc(opts.detected)}</span>`);
      el.append(b);
    }
    if (opts.err && opts.onRetry) {
      const btn = h(`<button class="btn btn--secondary btn--sm msg__retry" type="button">${CA.ui("voice_retry")}</button>`);
      btn.onclick = opts.onRetry;
      el.append(btn);
    }
    log().append(el); toBottom();
    if (role === "assistant" && !loading && !isOpen() && !pageMode()) dot(true);
    return el;
  }

  function welcome() {
    if (log().children.length) return;
    const el = h(`<div class="chat__welcome"><div class="state__icon" style="margin:0">${icon("sparkle")}</div>
      <div class="state__title">How can I help today?</div>
      <p class="caption">Try one of these, or type your own.</p><div class="chips"></div></div>`);
    CA.suggestions().forEach(t => {
      const b = h(`<button class="chip" type="button"></button>`);
      b.textContent = t; b.onclick = () => send(t);
      el.querySelector(".chips").append(b);
    });
    log().append(el);
  }

  function typing(on) {
    let t = $("#typing");
    if (on && !t) { t = h(`<div class="msg assistant typing" id="typing" aria-label="Assistant is typing"><i></i><i></i><i></i></div>`); log().append(t); toBottom(); }
    if (!on && t) t.remove();
  }

  function bookingReply(result) {
    if (!result || result.error) return { ok: false, text: "Booking failed: " + (result && result.error ? result.error : "Unknown error") };
    const demo = /mock|demo/i.test(String(result.provider || ""));
    const lead = demo ? "Demo booking recorded (not a real cab or porter booking). " : "Booked. ";
    return { ok: true, text: `${lead}Ref ${result.reference} (${result.provider}). ${result.pickup} to ${result.drop} at ${result.when}` };
  }

  function approval(a) {
    clearWelcome();
    const el = h(`<div class="approve"><div><strong>Needs your approval</strong><span></span></div>
      <p class="caption approve__note">Nothing runs until you approve. Cab and porter bookings use a demo provider unless a real partner API is connected.</p>
      <div class="row__actions"><button class="btn btn--accent btn--sm" type="button" data-ok>Approve</button>
      <button class="btn btn--secondary btn--sm" type="button" data-no>Reject</button></div></div>`);
    el.querySelector("span").textContent = a.summary;
    if (a.recognized_text) {
      const note = h(`<p class="caption approve__heard"><strong>${CA.ui("voice_recognized")}:</strong> ${esc(a.recognized_text)}</p>`);
      el.querySelector(".approve__note").before(note);
    }
    const done = async ok => {
      if (ok) {
        const yes = await confirm({ title: "Approve this action?", text: a.summary, submitLabel: "Approve and run", submitClass: "btn--accent" });
        if (!yes) return;
      }
      const btns = el.querySelectorAll("button"); btns.forEach(b => b.disabled = true);
      try {
        const r = await api(`/agent/${ok ? "approve" : "reject"}/${a.id}`, { method: "POST" });
        el.remove();
        if (r.error) {
          toast("error", friendlyError({ message: r.error }));
          bubble("assistant", r.error);
        } else if (!ok) {
          toast("info", "Action rejected");
          bubble("assistant", "Cancelled.");
        } else if (r.status === "executed" && r.result) {
          const br = bookingReply(r.result);
          if (br.ok) { toast("success", demoShort(r.result) ? "Demo booking recorded" : "Booking confirmed"); bubble("assistant", br.text); }
          else { toast("error", br.text); bubble("assistant", br.text); }
        } else if (r.result && r.result.error) {
          toast("error", "The action could not be completed.");
          bubble("assistant", "Failed: " + r.result.error);
        } else bubble("assistant", "Approved.");
        refresh();
      } catch (err) { btns.forEach(b => b.disabled = false); toast("error", friendlyError(err)); }
    };
    el.querySelector("[data-ok]").onclick = () => done(true);
    el.querySelector("[data-no]").onclick = () => done(false);
    log().append(el); toBottom();
  }

  function demoShort(result) { return /mock|demo/i.test(String(result.provider || "")); }

  function say(text) {
    if (!$("#speak") || !$("#speak").checked || !window.speechSynthesis) return;
    const lang = { en: "en-IN", hi: "hi-IN", mr: "mr-IN" }[(state.me && state.me.language) || "en"];
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang;
    const voices = speechSynthesis.getVoices();
    const pick = voices.find(v => v.lang && v.lang.toLowerCase().startsWith(lang.slice(0, 2)));
    if (pick) u.voice = pick;
    speechSynthesis.speak(u);
  }

  function handle(out, userVoice) {
    if (userVoice && userVoice.transcript) {
      bubble("user", userVoice.transcript, { voice: true, detected: userVoice.detected_language || "" });
    }
    bubble("assistant", out.reply); say(out.reply);
    out.pending.forEach(approval);
    refresh();
  }

  async function send(text) {
    text = (text || "").trim();
    if (!text || sending) return;
    sending = true; $("#send").disabled = true;
    bubble("user", text); typing(true);
    try { handle(await api("/agent/chat", { method: "POST", json: { message: text } })); }
    catch (err) { bubble("assistant", "Sorry, that didn't work: " + friendlyError(err)); }
    typing(false);
    sending = false; $("#send").disabled = false;
  }

  async function loadHistory() {
    log().innerHTML = "";
    loading = true;
    try {
      const hist = await api("/agent/history");
      hist.forEach(m => bubble(m.role, m.content, {
        voice: m.source === "voice",
        detected: m.detected_language || "",
      }));
      const pending = await api("/agent/pending");
      pending.forEach(approval);
      if (pending.length && !isOpen() && !pageMode()) dot(true);
    } catch (err) { toast("warning", "Couldn't load your chat history."); }
    loading = false;
    welcome();
  }

  function setMic(on) {
    const m = $("#mic");
    m.classList.toggle("rec", on);
    m.innerHTML = icon(on ? "stop" : "mic");
    m.setAttribute("aria-label", on ? "Stop recording" : "Record voice message");
  }

  function sttLang() {
    const sel = $("#voiceSttLang");
    if (!sel) return (state.me && state.me.language) || "en";
    return sel.value || "en";
  }

  function syncVoiceBar(show) {
    const bar = $("#voiceBar");
    if (!bar) return;
    bar.hidden = !show;
    const sel = $("#voiceSttLang");
    if (sel) {
      const prefer = (() => { try { return localStorage.getItem(VOICE_STT_KEY); } catch (e) { return null; } })()
        || (state.me && state.me.language) || "en";
      sel.value = ["en", "hi", "mr"].includes(prefer) ? prefer : "en";
      sel.onchange = () => { try { localStorage.setItem(VOICE_STT_KEY, sel.value); } catch (e) { /* ok */ } };
    }
  }

  function setVoiceStatus(text) {
    const s = $("#voiceStatus");
    if (s) s.textContent = text || "";
  }

  async function uploadVoice(blob) {
    if (!blob || voiceBusy) return;
    voiceBusy = true;
    lastVoiceBlob = blob;
    $("#mic").disabled = true;
    setVoiceStatus(CA.ui("voice_processing"));
    typing(true);
    const fd = new FormData();
    fd.append("file", blob, "voice.webm");
    fd.append("language", sttLang());
    try {
      const out = await api("/voice/chat", { method: "POST", body: fd });
      handle(out, { transcript: out.transcript, detected_language: out.detected_language });
      setVoiceStatus("");
    } catch (err) {
      const msg = friendlyError(err, "Voice isn't available right now.");
      bubble("assistant", msg, { err: true, onRetry: () => uploadVoice(lastVoiceBlob) });
      toast("warning", msg);
    }
    typing(false);
    voiceBusy = false;
    $("#mic").disabled = false;
  }

  let rec = null, chunks = [], recStream = null;
  function bindVoice() {
    syncVoiceBar(true);
    $("#mic").onclick = async () => {
      if (voiceBusy) return;
      if (rec) {
        if (Date.now() - recStartedAt < MIN_RECORD_MS) {
          toast("info", "Keep speaking for a second longer, then tap stop.");
          return;
        }
        rec.stop();
        return;
      }
      try {
        recStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus" : "audio/webm";
        rec = new MediaRecorder(recStream, { mimeType: mime }); chunks = [];
        rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
        rec.onstop = async () => {
          recStream.getTracks().forEach(t => t.stop());
          recStream = null;
          setMic(false);
          setVoiceStatus("");
          const recRef = rec;
          rec = null;
          const blob = new Blob(chunks, { type: recRef.mimeType || "audio/webm" });
          chunks = [];
          await uploadVoice(blob);
        };
        rec.start();
        recStartedAt = Date.now();
        setMic(true);
        setVoiceStatus(CA.ui("voice_listening"));
      } catch (e) {
        bubble("assistant", "Microphone access was blocked. Allow it in your browser settings.");
      }
    };
  }

  /* ---------- floating window ---------- */
  const GEO_KEY = "ca.chatbox";
  const mobile = () => window.matchMedia("(max-width: 900px)").matches;
  const pageMode = () => document.body.classList.contains("page-assistant");
  const isOpen = () => !!$("#chat") && $("#chat").classList.contains("is-open");
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi));
  const dot = on => { const d = $("#chatFab .fab__dot"); if (d) d.hidden = !on; };
  let geo = (() => { try { return JSON.parse(localStorage.getItem(GEO_KEY) || "null") || {}; } catch (e) { return {}; } })();
  const saveGeo = () => { try { localStorage.setItem(GEO_KEY, JSON.stringify(geo)); } catch (e) { /* storage unavailable */ } };

  /* Writes size and position (anchored bottom-right) to CSS variables, always keeping the window on screen. */
  function applyGeo() {
    const el = $("#chat"), vw = window.innerWidth, vh = window.innerHeight;
    const w = clamp(geo.w || 400, 320, vw - 16), ht = clamp(geo.h || 600, 380, vh - 16);
    const r = clamp(geo.r == null ? 24 : geo.r, 8, vw - w - 8), b = clamp(geo.b == null ? 24 : geo.b, 8, vh - ht - 8);
    el.style.setProperty("--cw", w + "px"); el.style.setProperty("--ch", ht + "px");
    el.style.setProperty("--cr", r + "px"); el.style.setProperty("--cb", b + "px");
    return { w, h: ht, r, b };
  }

  function paintMax() {
    const el = $("#chat"), on = el.classList.contains("is-max");
    $("#chatMax").innerHTML = icon(on ? "shrink" : "expand");
    $("#chatMax").setAttribute("aria-label", on ? "Make assistant smaller" : "Expand assistant");
  }

  function setOpen(on, opts = {}) {
    const el = $("#chat"), fab = $("#chatFab");
    if (!el || pageMode()) return;
    el.classList.toggle("is-open", on);
    fab.hidden = on; fab.setAttribute("aria-expanded", String(on));
    document.body.classList.toggle("chat-open", on && mobile());
    if (on) {
      el.classList.toggle("is-max", !!geo.max && !mobile()); paintMax(); applyGeo(); dot(false); toBottom();
      if (opts.focus !== false) setTimeout(() => $("#msg").focus(), 30);
    } else if (opts.focus !== false) fab.focus();
  }

  function toggleMax() {
    const el = $("#chat");
    if (mobile() || pageMode()) return;
    el.classList.toggle("is-max"); geo = { ...geo, max: el.classList.contains("is-max") };
    saveGeo(); paintMax(); toBottom();
  }

  /* One pointer-drag helper for both moving (header) and resizing (corner handle). */
  function trackPointer(e, onMove, onEnd) {
    const sx = e.clientX, sy = e.clientY;
    const move = ev => onMove(ev.clientX - sx, ev.clientY - sy);
    const up = () => {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", up);
      document.removeEventListener("pointercancel", up);
      onEnd();
    };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", up);
    document.addEventListener("pointercancel", up);
  }

  function startDrag(e) {
    const el = $("#chat");
    if (mobile() || pageMode() || el.classList.contains("is-max")) return;
    if (e.button > 0 || e.target.closest("button")) return;
    const g = applyGeo(), head = e.currentTarget;
    head.classList.add("is-dragging");
    trackPointer(e, (dx, dy) => { geo = { ...geo, w: g.w, h: g.h, r: g.r - dx, b: g.b - dy }; applyGeo(); },
      () => { head.classList.remove("is-dragging"); geo = { ...geo, ...applyGeo() }; saveGeo(); });
  }

  function startResize(e) {
    if (mobile() || pageMode() || e.button > 0) return;
    e.preventDefault();
    const g = applyGeo(), vw = window.innerWidth, vh = window.innerHeight;
    document.body.classList.add("is-resizing");
    trackPointer(e, (dx, dy) => {
      geo = { ...geo, r: g.r, b: g.b, w: clamp(g.w - dx, 320, vw - g.r - 8), h: clamp(g.h - dy, 380, vh - g.b - 8) };
      applyGeo();
    }, () => { document.body.classList.remove("is-resizing"); geo = { ...geo, ...applyGeo() }; saveGeo(); });
  }

  /* Called by the router. On the Assistant route the chat is the page; elsewhere it floats. */
  function onRoute(route) {
    const page = route === "assistant";
    if (page === pageMode()) return;
    document.body.classList.toggle("page-assistant", page);
    $("#chat").classList.remove("is-open");
    document.body.classList.remove("chat-open");
    $("#chatFab").hidden = false; $("#chatFab").setAttribute("aria-expanded", "false");
    if (page) dot(false);
  }

  function initWindow() {
    $("#chatFab").querySelector(".fab__icon").innerHTML = icon("sparkle");
    $("#chatClose").innerHTML = icon("x"); paintMax();
    $("#chatFab").onclick = () => setOpen(true);
    $("#chatClose").onclick = () => setOpen(false);
    $("#chatMax").onclick = toggleMax;
    $("#chatHead").addEventListener("pointerdown", startDrag);
    $("#chatHead").addEventListener("dblclick", e => { if (!e.target.closest("button")) toggleMax(); });
    $("#chatResize").addEventListener("pointerdown", startResize);
    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && isOpen() && !pageMode() && $("#chat").contains(document.activeElement)) setOpen(false);
    });
    window.addEventListener("resize", () => { if (isOpen() && !mobile() && !pageMode()) applyGeo(); });
  }

  function init() {
    $("#send").innerHTML = icon("send");
    setMic(false); bindVoice();
    $("#send").onclick = () => { const t = $("#msg").value; $("#msg").value = ""; $("#msg").style.height = ""; send(t); };
    $("#msg").onkeydown = e => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#send").click(); }
    };
    $("#msg").oninput = e => { e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 140) + "px"; };
  }

  function ask(text) {
    if (!pageMode()) setOpen(true, { focus: !text });
    setTimeout(() => { if (text) send(text); else $("#msg").focus(); }, 60);
  }

  init(); initWindow();
  /* After the creator type changes, redraw the starter suggestions (only while the welcome card is showing). */
  function refreshWelcome() { const w = $(".chat__welcome"); if (w) { w.remove(); welcome(); } }

  CA.chat = { loadHistory, send, ask, bubble, onRoute, refreshWelcome, open: () => setOpen(true), close: () => setOpen(false) };
})();
