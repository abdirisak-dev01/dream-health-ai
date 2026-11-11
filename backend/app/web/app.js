/* Dream Health web app. © 2026 Abdirisak Omar. All rights reserved.
   Plain JavaScript, no build step. Talks to the same /v1 API as /docs.
   All screen text comes from i18n.js (English, Somali, Spanish). */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const TOKEN_KEY = "dh_token";
  const LANG_KEY = "dh_lang";
  const I18N = window.DH_I18N;
  const state = { me: null, day: null, lastChatId: null, lastSmsId: null, poll: null, phone: null, lang: "en", langPicked: false };

  // ---------- storage (private windows can refuse it, so every call is guarded) ----------
  const store = {
    get(k) { try { return sessionStorage.getItem(k) ?? localStorage.getItem(k); } catch { return null; } },
    setSession(k, v) { try { sessionStorage.setItem(k, v); } catch { /* ignore */ } },
    setLocal(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
    clear(k) { try { sessionStorage.removeItem(k); } catch { /* ignore */ } },
  };

  // ---------- language ----------
  function tr(key, vars = {}) {
    const pack = I18N[state.lang] || I18N.en;
    let s = pack[key] ?? I18N.en[key] ?? key;
    if (typeof s === "string") s = s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
    return s;
  }
  function setLang(lang) {
    state.lang = I18N[lang] ? lang : "en";
    document.documentElement.lang = state.lang;
    store.setLocal(LANG_KEY, state.lang);
    $$("[data-i18n]").forEach(el => { el.textContent = tr(el.dataset.i18n); });
    $$("[data-i18n-ph]").forEach(el => { el.placeholder = tr(el.dataset.i18nPh); });
    $$(".lang-pick button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.lang === state.lang)));
    $("#auth-submit").textContent = authMode === "login" ? tr("btn_login") : tr("btn_register");
    renderDayChecks(true);
  }
  const mealName = t => tr(`m_${t}`) || t;
  const unitText = (q, u) => {
    const names = (I18N[state.lang] || I18N.en).units[u];
    return names ? names[Number(q) === 1 ? 0 : 1] : u;
  };
  const foodLabel = it => (it.food_labels && (it.food_labels[state.lang] || it.food_labels.en)) || it.food_name;

  // ---------- helpers ----------
  class ApiError extends Error {
    constructor(status, body) { super(body?.error?.message || `Request failed (${status})`); this.status = status; this.body = body; }
  }

  async function api(path, { method = "GET", body } = {}) {
    const headers = { "Accept": "application/json" };
    const token = store.get(TOKEN_KEY);
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    if (res.status === 204) return null;
    const data = await res.json().catch(() => null);
    if (res.status === 401 && path !== "/v1/auth/login") { logout(tr("session_ended")); throw new ApiError(401, data); }
    if (!res.ok) throw new ApiError(res.status, data);
    return data;
  }

  function errorText(e) {
    const d = e.body?.error?.details;
    if (Array.isArray(d) && d.length) return d.map(x => `${x.loc?.[x.loc.length - 1] ?? "field"}: ${x.msg}`).join(". ");
    return e.message || tr("error");
  }

  function toast(text) {
    const t = $("#toast");
    t.textContent = text; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, 2600);
  }

  const numLocale = () => (state.lang === "so" ? "en" : state.lang);
  const n0 = v => Math.round(Number(v)).toLocaleString(numLocale());
  const n1 = v => { const x = Number(v); return x >= 100 ? n0(x) : (Math.round(x * 10) / 10).toString(); };
  const hhmm = iso => new Date(iso).toLocaleTimeString(numLocale(), { hour: "numeric", minute: "2-digit" });
  const isoDay = d => d.toISOString().slice(0, 10);
  const todayInTz = tz => new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());

  function setBusy(form, busy) { $$("button", form).forEach(b => { b.disabled = busy; }); }
  function formError(form, text) { const p = $(".form-error", form); if (p) p.textContent = text || ""; }

  // ---------- auth ----------
  let authMode = "login";
  function setAuthMode(mode) {
    authMode = mode;
    $("#auth").classList.toggle("is-register", mode === "register");
    $$(".seg button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.auth === mode)));
    $("#auth-submit").textContent = mode === "login" ? tr("btn_login") : tr("btn_register");
    $("#f-password").autocomplete = mode === "login" ? "current-password" : "new-password";
    formError($("#auth-form"), "");
  }
  $$(".seg button").forEach(b => b.addEventListener("click", () => setAuthMode(b.dataset.auth)));
  // A language picked on the login page wins over the one saved on the account (and gets saved to it).
  $$(".lang-pick button").forEach(b => b.addEventListener("click", () => { state.langPicked = true; setLang(b.dataset.lang); }));

  $("#auth-form").addEventListener("submit", async e => {
    e.preventDefault();
    const f = e.currentTarget;
    const email = $("#f-email").value.trim(), password = $("#f-password").value;
    setBusy(f, true); formError(f, "");
    try {
      if (authMode === "register") {
        if (password.length < 12) throw new ApiError(422, { error: { message: tr("pw_short") } });
        await api("/v1/auth/register", { method: "POST", body: {
          email, password, display_name: $("#f-name").value.trim() || email.split("@")[0],
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Chicago",
          preferred_language: state.lang,
        }});
      }
      const tok = await api("/v1/auth/login", { method: "POST", body: { email, password } });
      store.setSession(TOKEN_KEY, tok.access_token);
      f.reset();
      await boot();
    } catch (err) { formError(f, errorText(err)); }
    finally { setBusy(f, false); }
  });

  function logout(message) {
    store.clear(TOKEN_KEY);
    clearInterval(state.poll);
    state.me = null;
    $("#shell").hidden = true; $("#auth").hidden = false;
    setAuthMode("login");
    if (message) formError($("#auth-form"), message);
  }
  $("#logout").addEventListener("click", () => logout());

  // ---------- routing ----------
  const VIEWS = ["today", "chat", "phone", "reminders", "settings"];
  function route() {
    const tab = VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "today";
    VIEWS.forEach(v => { $(`#view-${v}`).hidden = v !== tab; });
    $$(".rail a").forEach(a => { if (a.dataset.tab === tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    ({ today: loadToday, chat: loadChat, phone: loadPhone, reminders: loadReminders, settings: loadSettings })[tab]();
    document.title = `${tr(`nav_${tab === "phone" ? "texts" : tab}`)} - Dream Health`;
  }
  window.addEventListener("hashchange", () => { if (state.me) route(); });

  // ---------- today ----------
  async function loadToday() {
    if (!state.day) state.day = todayInTz(state.me.timezone);
    const [sum, meals] = await Promise.all([api(`/v1/days/${state.day}/summary`), api(`/v1/meals?date=${state.day}`)]);
    const isToday = state.day === todayInTz(state.me.timezone);
    $("#today-title").textContent = isToday ? tr("today") :
      new Date(state.day + "T12:00:00").toLocaleDateString(numLocale(), { weekday: "long", month: "short", day: "numeric" });
    $("#day-next").disabled = isToday;

    const k = sum.vs_targets.kcal, fill = $("#gauge-fill"), cap = $("#kcal-caption");
    fill.classList.remove("is-low", "is-over");
    cap.replaceChildren();
    if (k.target !== null) {
      const left = Number(k.remaining), target = Number(k.target);
      const pct = Math.max(0, Math.min(100, Number(k.eaten) / target * 100));
      fill.style.strokeDasharray = `${pct} 101`;
      fill.style.opacity = pct > 0 ? "1" : "0";  // round ends would draw dots at 0
      if (left < 0) fill.classList.add("is-over"); else if (left < target * 0.15) fill.classList.add("is-low");
      $("#kcal-left").textContent = n0(Math.abs(left));
      cap.textContent = left < 0 ? tr("kcal_over", { goal: n0(target) }) : tr("kcal_left_of", { goal: n0(target) });
    } else {
      fill.style.strokeDasharray = "0 101";
      fill.style.opacity = "0";
      $("#kcal-left").textContent = n0(sum.totals.kcal);
      const a = document.createElement("a"); a.href = "#settings"; a.textContent = tr("set_goal");
      cap.append(tr("kcal_eaten") + " ", a);
    }

    const dl = $("#macros"); dl.replaceChildren();
    [["protein_g", "protein"], ["carbs_g", "carbs"], ["fat_g", "fat"], ["fiber_g", "fiber"]].forEach(([key, label]) => {
      const v = sum.vs_targets[key];
      const div = document.createElement("div");
      const dt = document.createElement("dt"); dt.textContent = tr(label);
      const dd = document.createElement("dd");
      dd.textContent = v.target === null ? `${n1(v.eaten)} g` : `${n1(v.eaten)} / ${n1(v.target)} g`;
      div.append(dt, dd);
      if (v.target !== null && Number(v.target) > 0) {
        const bar = document.createElement("div"); bar.className = "bar";
        const i = document.createElement("i");
        const pct = Number(v.eaten) / Number(v.target) * 100;
        i.style.width = `${Math.min(100, pct)}%`; if (pct > 100 && key === "fat_g") i.className = "over";
        bar.append(i); div.append(bar);
      }
      dl.append(div);
    });
    $("#today-note").textContent = sum.includes_unverified_food_data ? tr("unverified") : "";

    const ul = $("#meal-list"); ul.replaceChildren();
    if (!meals.length) {
      const li = document.createElement("li"); li.className = "empty";
      li.textContent = isToday ? tr("no_meals_today") : tr("no_meals_day");
      ul.append(li);
    }
    meals.forEach(m => {
      const li = document.createElement("li"); li.className = "meal";
      const top = document.createElement("div"); top.className = "meal-top";
      const h = document.createElement("h3"); h.textContent = mealName(m.meal_type);
      const kc = document.createElement("span"); kc.className = "meal-kcal"; kc.textContent = `${n0(m.totals.kcal)} kcal`;
      top.append(h, kc);
      const items = document.createElement("ul");
      m.items.forEach(it => {
        const x = document.createElement("li");
        x.textContent = `${foodLabel(it)}, ${n1(it.quantity)} ${unitText(it.quantity, it.unit)} (${n0(it.kcal)} kcal)`;
        items.append(x);
      });
      const foot = document.createElement("div"); foot.className = "meal-foot";
      const t = document.createElement("span"); t.textContent = hhmm(m.eaten_at);
      const del = document.createElement("button"); del.className = "link-btn"; del.type = "button"; del.textContent = tr("remove");
      del.addEventListener("click", async () => {
        if (!confirm(tr("remove_q"))) return;
        await api(`/v1/meals/${m.id}`, { method: "DELETE" }); toast(tr("meal_removed")); loadToday();
      });
      foot.append(t, del);
      li.append(top, items, foot); ul.append(li);
    });
  }
  function shiftDay(delta) { const d = new Date(state.day + "T12:00:00"); d.setDate(d.getDate() + delta); state.day = isoDay(d); loadToday(); }
  $("#day-prev").addEventListener("click", () => shiftDay(-1));
  $("#day-next").addEventListener("click", () => shiftDay(1));

  // ---------- chat ----------
  function bubble(m) {
    const li = document.createElement("li");
    li.className = `bubble ${m.direction}${m.kind === "reminder" ? " reminder" : ""}`;
    li.textContent = m.body;
    const t = document.createElement("time"); t.dateTime = m.created_at; t.textContent = hhmm(m.created_at);
    li.append(t);
    return li;
  }

  async function loadChat(onlyNew = false) {
    const after = onlyNew && state.lastChatId ? `&after=${state.lastChatId}` : "";
    const msgs = await api(`/v1/messages?channel=in_app${after}`);
    const ol = $("#chat-thread");
    if (!onlyNew) {
      ol.replaceChildren();
      if (!msgs.length) { const li = document.createElement("li"); li.className = "bubble out"; li.textContent = tr("chat_welcome"); ol.append(li); }
    }
    msgs.forEach(m => ol.append(bubble(m)));
    if (msgs.length) { state.lastChatId = msgs[msgs.length - 1].id; ol.scrollTop = ol.scrollHeight; }
    if (!onlyNew) $("#chat-input").focus({ preventScroll: true });
    return msgs;
  }

  async function sendChat(text) {
    const ol = $("#chat-thread");
    const r = await api("/v1/chat", { method: "POST", body: { text } });
    r.messages.forEach(m => ol.append(bubble(m)));
    state.lastChatId = r.messages[r.messages.length - 1].id;
    ol.scrollTop = ol.scrollHeight;
  }
  $("#chat-form").addEventListener("submit", async e => {
    e.preventDefault();
    const input = $("#chat-input"), text = input.value.trim();
    if (!text) return;
    input.value = "";
    try { await sendChat(text); } catch (err) { toast(errorText(err)); input.value = text; }
  });
  $$(".quick .chip").forEach(c => c.addEventListener("click", () => sendChat(tr(c.dataset.say)).catch(err => toast(errorText(err)))));

  // ---------- fake phone ----------
  async function loadPhone(onlyNew = false) {
    if (!onlyNew) state.phone = await api("/v1/me/phone");
    const p = state.phone;
    $("#phone-banner").hidden = !p.test_mode;
    const ready = !!p.phone && p.verified;
    $("#phone-need").hidden = ready || !!p.pending_phone;
    $("#handset").hidden = !(ready || p.pending_phone);
    if ($("#handset").hidden) return;
    $("#handset-num").textContent = `${p.app_number} → ${p.phone || p.pending_phone}`;
    $("#sms-form").hidden = !ready || !p.test_mode;
    const after = onlyNew && state.lastSmsId ? `&after=${state.lastSmsId}` : "";
    const msgs = await api(`/v1/messages?channel=sms${after}`);
    const ol = $("#sms-thread");
    if (!onlyNew) ol.replaceChildren();
    msgs.forEach(m => ol.append(bubble(m)));
    if (msgs.length) { state.lastSmsId = msgs[msgs.length - 1].id; ol.scrollTop = ol.scrollHeight; }
  }
  $("#sms-form").addEventListener("submit", async e => {
    e.preventDefault();
    const input = $("#sms-input"), text = input.value.trim();
    if (!text) return;
    input.value = "";
    try {
      const msgs = await api("/v1/dev/fake-phone/send", { method: "POST", body: { text } });
      const ol = $("#sms-thread");
      msgs.forEach(m => ol.append(bubble(m)));
      if (msgs.length) state.lastSmsId = msgs[msgs.length - 1].id;
      ol.scrollTop = ol.scrollHeight;
      state.phone = await api("/v1/me/phone");
    } catch (err) { toast(errorText(err)); input.value = text; }
  });

  // ---------- reminders ----------
  function renderDayChecks(relabel = false) {
    const fs = $(".days");
    const days = (I18N[state.lang] || I18N.en).days;
    if (fs.querySelector("label")) {
      if (relabel) $$("label span", fs).forEach((s, i) => { s.textContent = days[i]; });
      return;
    }
    days.forEach((d, i) => {
      const l = document.createElement("label");
      const c = document.createElement("input"); c.type = "checkbox"; c.name = "day"; c.value = String(i); c.checked = true; c.id = `rem-day-${i}`;
      const s = document.createElement("span"); s.textContent = d;
      l.append(c, s); fs.append(l);
    });
  }

  function notifState() {
    const p = $("#notif-state");
    p.replaceChildren();
    if (!("Notification" in window)) { p.textContent = tr("notif_none"); return; }
    if (Notification.permission === "granted") { p.textContent = tr("notif_on"); return; }
    if (Notification.permission === "denied") { p.textContent = tr("notif_blocked"); return; }
    const b = document.createElement("button"); b.type = "button"; b.className = "btn"; b.textContent = tr("notif_btn");
    b.addEventListener("click", async () => { await Notification.requestPermission(); notifState(); });
    p.append(b);
  }

  async function loadReminders() {
    renderDayChecks(); notifState();
    const [rows, phone] = await Promise.all([api("/v1/reminders"), api("/v1/me/phone")]);
    state.phone = phone;
    const smsBox = $("#rem-ch-sms");
    smsBox.disabled = !phone.texts_on;
    smsBox.parentElement.title = phone.texts_on ? "" : tr("r_texts_first");
    if (!phone.texts_on) smsBox.checked = false;

    const days = (I18N[state.lang] || I18N.en).days;
    const ul = $("#rem-list"); ul.replaceChildren();
    if (!rows.length) { const li = document.createElement("li"); li.className = "empty"; li.textContent = tr("r_none"); ul.append(li); }
    rows.forEach(r => {
      const li = document.createElement("li"); li.className = `rem${r.enabled ? "" : " off"}`;
      const time = document.createElement("div"); time.className = "rem-time";
      const [hh, mm] = r.at_time.split(":"); time.textContent = `${hh}:${mm}`;
      const title = document.createElement("div"); title.className = "rem-title";
      title.textContent = r.label === "custom" ? (r.message || tr("m_custom")) : mealName(r.label);
      const meta = document.createElement("div"); meta.className = "rem-meta";
      const dayText = r.days.length === 7 ? tr("r_every_day") : r.days.map(i => days[i]).join(", ");
      meta.textContent = `${dayText}. ${r.channels.map(c => c === "sms" ? tr("ch_text") : tr("ch_app")).join(" + ")}${r.enabled ? "" : ". " + tr("r_paused")}`;
      const actions = document.createElement("div"); actions.className = "rem-actions";
      const mk = (label, fn, cls = "chip") => { const b = document.createElement("button"); b.type = "button"; b.className = cls; b.textContent = label; b.addEventListener("click", fn); return b; };
      actions.append(
        mk(tr("send_now"), async () => {
          const res = await api(`/v1/reminders/${r.id}/send-now`, { method: "POST" });
          toast(res.sent_on.length ? tr("sent_to", { where: res.sent_on.map(c => c === "sms" ? tr("sent_texts") : tr("sent_chat")).join(tr("and")) }) : tr("not_sent"));
        }),
        mk(r.enabled ? tr("pause") : tr("turn_on"), async () => { await api(`/v1/reminders/${r.id}`, { method: "PUT", body: { ...r, enabled: !r.enabled } }); loadReminders(); }),
        mk(tr("delete"), async () => { if (!confirm(tr("delete_q"))) return; await api(`/v1/reminders/${r.id}`, { method: "DELETE" }); loadReminders(); }, "link-btn"),
      );
      li.append(time, title, meta, actions); ul.append(li);
    });
  }

  $("#rem-form").addEventListener("submit", async e => {
    e.preventDefault();
    const f = e.currentTarget;
    const channels = [];
    if ($("#rem-ch-app").checked) channels.push("in_app");
    if ($("#rem-ch-sms").checked) channels.push("sms");
    const days = $$("input[name=day]:checked", f).map(c => Number(c.value));
    formError(f, "");
    if (!channels.length) return formError(f, tr("r_pick_channel"));
    if (!days.length) return formError(f, tr("r_pick_day"));
    setBusy(f, true);
    try {
      await api("/v1/reminders", { method: "POST", body: {
        label: $("#rem-label").value, at_time: $("#rem-time").value, days, channels,
        message: $("#rem-msg").value.trim() || null, skip_if_logged: $("#rem-skip").checked,
      }});
      toast(tr("r_added")); $("#rem-msg").value = ""; loadReminders();
    } catch (err) { formError(f, errorText(err)); }
    finally { setBusy(f, false); }
  });

  // ---------- settings ----------
  async function loadSettings() {
    $("#p-name").value = state.me.display_name;
    $("#p-lang").value = state.lang;
    $("#p-tz").value = state.me.timezone;
    const dl = $("#tz-list");
    if (!dl.children.length && Intl.supportedValuesOf) {
      Intl.supportedValuesOf("timeZone").forEach(z => { const o = document.createElement("option"); o.value = z; dl.append(o); });
    }
    try {
      const t = await api("/v1/me/targets");
      [["t-kcal", "calories_kcal"], ["t-protein", "protein_g"], ["t-carbs", "carbs_g"], ["t-fat", "fat_g"], ["t-fiber", "fiber_g"]]
        .forEach(([id, k]) => { $(`#${id}`).value = t[k] === null ? "" : Math.round(Number(t[k])); });
    } catch (err) { if (err.status !== 404) throw err; }
    renderPhone(await api("/v1/me/phone"));
  }

  function renderPhone(p) {
    state.phone = p;
    const box = $("#phone-status"); box.replaceChildren();
    const line = document.createElement("div"); line.className = "status-line";
    const pill = (text, warn) => { const s = document.createElement("span"); s.className = `pill${warn ? " warn" : ""}`; s.textContent = text; return s; };
    if (p.phone && p.verified) {
      const num = document.createElement("strong"); num.textContent = p.phone;
      line.append(num, p.texts_on ? pill(tr("texts_on")) : pill(p.opted_out ? tr("replied_stop") : tr("texts_off"), true));
      const toggle = document.createElement("button"); toggle.type = "button"; toggle.className = "btn";
      toggle.textContent = p.texts_on ? tr("turn_texts_off") : tr("turn_texts_on");
      toggle.addEventListener("click", async () => renderPhone(await api("/v1/me/phone/consent", { method: "PUT", body: { agree_to_texts: !p.texts_on } })));
      const rm = document.createElement("button"); rm.type = "button"; rm.className = "link-btn"; rm.textContent = tr("remove_number");
      rm.addEventListener("click", async () => { if (confirm(tr("remove_number_q"))) renderPhone(await api("/v1/me/phone", { method: "DELETE" })); });
      line.append(toggle, rm);
    } else {
      const s = document.createElement("span"); s.className = "note"; s.textContent = tr("add_number_note"); line.append(s);
    }
    box.append(line);
    $("#phone-form").hidden = !!(p.phone && p.verified) && !p.pending_phone;
    $("#code-form").hidden = !p.pending_phone;
    if (p.pending_phone) {
      const hint = document.createElement("p"); hint.className = "note";
      hint.textContent = p.test_mode ? tr("code_hint_test", { phone: p.pending_phone }) : tr("code_hint", { phone: p.pending_phone });
      box.append(hint);
    }
  }

  $("#phone-form").addEventListener("submit", async e => {
    e.preventDefault();
    const f = e.currentTarget, panel = $("#phone-panel");
    formError(panel, ""); setBusy(f, true);
    try { renderPhone(await api("/v1/me/phone", { method: "POST", body: { phone: $("#ph-number").value } })); toast(tr("code_sent")); }
    catch (err) { formError(panel, errorText(err)); }
    finally { setBusy(f, false); }
  });
  $("#code-form").addEventListener("submit", async e => {
    e.preventDefault();
    const f = e.currentTarget, panel = $("#phone-panel");
    formError(panel, ""); setBusy(f, true);
    try {
      renderPhone(await api("/v1/me/phone/verify", { method: "POST", body: { code: $("#ph-code").value.trim(), agree_to_texts: $("#ph-agree").checked } }));
      f.reset(); toast(tr("phone_ok"));
    } catch (err) { formError(panel, errorText(err)); }
    finally { setBusy(f, false); }
  });

  $("#targets-form").addEventListener("submit", async e => {
    e.preventDefault();
    const f = e.currentTarget, body = {};
    [["t-kcal", "calories_kcal"], ["t-protein", "protein_g"], ["t-carbs", "carbs_g"], ["t-fat", "fat_g"], ["t-fiber", "fiber_g"]]
      .forEach(([id, k]) => { const v = $(`#${id}`).value; body[k] = v === "" ? null : Number(v); });
    formError(f, ""); setBusy(f, true);
    try { await api("/v1/me/targets", { method: "PUT", body }); toast(tr("goal_saved")); }
    catch (err) { formError(f, errorText(err)); }
    finally { setBusy(f, false); }
  });
  $("#profile-form").addEventListener("submit", async e => {
    e.preventDefault();
    const f = e.currentTarget;
    formError(f, ""); setBusy(f, true);
    try {
      state.me = await api("/v1/me", { method: "PATCH", body: { display_name: $("#p-name").value, timezone: $("#p-tz").value.trim(), preferred_language: $("#p-lang").value } });
      state.day = null;
      setLang(state.me.preferred_language.split("-")[0]);
      toast(tr("profile_saved"));
      loadSettings();
    } catch (err) { formError(f, errorText(err)); }
    finally { setBusy(f, false); }
  });

  // ---------- background: new messages + pop-up notifications ----------
  async function pollTick() {
    if (!state.me) return;
    try {
      const tab = location.hash.slice(1) || "today";
      if (tab === "chat") {
        notify((await loadChat(true)).filter(m => m.kind === "reminder"));
      } else {
        const after = state.lastChatId ? `&after=${state.lastChatId}` : "";
        const fresh = await api(`/v1/messages?channel=in_app${after}`);
        if (fresh.length) state.lastChatId = fresh[fresh.length - 1].id;
        const rems = fresh.filter(m => m.kind === "reminder");
        notify(rems);
        if (rems.length && !document.hidden) toast(rems[rems.length - 1].body);
      }
      if (tab === "phone" && state.phone?.phone) await loadPhone(true);
    } catch { /* offline for a moment: try again next tick */ }
  }
  function notify(msgs) {
    if (!msgs.length || !("Notification" in window) || Notification.permission !== "granted") return;
    msgs.forEach(m => { const n = new Notification("Dream Health", { body: m.body, tag: m.id }); n.onclick = () => { window.focus(); location.hash = "chat"; }; });
  }

  // ---------- start ----------
  async function boot() {
    if (!store.get(TOKEN_KEY)) { $("#auth").hidden = false; return; }
    try { state.me = await api("/v1/me"); } catch { return; }
    const accountLang = state.me.preferred_language.split("-")[0];
    if (state.langPicked && state.lang !== accountLang) {
      try { state.me = await api("/v1/me", { method: "PATCH", body: { preferred_language: state.lang } }); } catch { /* keep going */ }
    }
    state.langPicked = false;
    setLang(state.me.preferred_language.split("-")[0]);
    $("#auth").hidden = true; $("#shell").hidden = false;
    state.day = null; state.lastChatId = null; state.lastSmsId = null;
    const latest = await api("/v1/messages?channel=in_app&limit=1").catch(() => []);
    if (latest.length) state.lastChatId = latest[0].id;
    clearInterval(state.poll); state.poll = setInterval(pollTick, 5000);
    route();
  }
  const saved = store.get(LANG_KEY);
  const browser = (navigator.language || "en").slice(0, 2);
  setLang(saved || (I18N[browser] ? browser : "en"));
  setAuthMode("login");
  boot();
})();
