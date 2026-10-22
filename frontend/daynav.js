"use strict";
// The Today list's day navigator (UI-A Task 2): ‹ previous day, the day's title, a calendar, › next day (off on today) and
// "Back to today". app.js owns the day (state.listDay: "" = today, else an ISO day) and reloads the list; this file only
// moves it and draws the controls. Loaded after dates.js and BEFORE app.js; also loads under node for tests.
(function (root) {
  const el = (id) => document.getElementById(id);
  let hooks = { day: () => "", go: () => {} };
  const todayIso = () => (root.Dates ? root.Dates.todayIso() : "");
  const isoDay = (s) => typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s) && !!(root.Dates && root.Dates.date(s));

  function shift(iso, n) {                                            // the ISO day n days after iso (UTC maths: no zone shifts)
    const t = new Date(iso + "T00:00:00Z");
    t.setUTCDate(t.getUTCDate() + n);
    return t.toISOString().slice(0, 10);
  }
  // The list URL: the scope query as Authorship gives it, plus date= only for an earlier day.
  function url(base, query, day) {
    return base + (query || "") + (day ? (query ? "&" : "?") + "date=" + encodeURIComponent(day) : "");
  }
  function emptyText(day) {
    return day ? "No prescriptions on " + ((root.Dates && root.Dates.date(day)) || day) + "." : "No patients completed yet today.";
  }

  // Today, a future day and a bad value all mean "" (today): the list never asks for a day the server refuses.
  function go(day) {
    const t = todayIso();
    hooks.go(isoDay(day) && day < t ? day : "");
    render();
  }

  function render() {
    const day = hooks.day(), t = todayIso();
    const title = el("dayTitle"), next = el("dayNext"), back = el("dayToday"), input = el("dayInput");
    if (title) title.textContent = day ? ((root.Dates && root.Dates.short(day)) || day) : "Today";
    if (next) next.disabled = !day;
    if (back) back.hidden = !day;
    if (input) { input.max = t; input.value = day || t; }
  }

  function openPicker() {
    const input = el("dayInput");
    if (!input) return;
    try {
      if (typeof input.showPicker === "function") { input.showPicker(); return; }
    } catch (e) { /* not allowed here: focus instead */ }
    input.focus();
  }

  function init(h) {
    hooks = h;
    const on = (id, type, f) => { const n = el(id); if (n) n.addEventListener(type, f); };
    on("dayPrev", "click", () => go(shift(hooks.day() || todayIso(), -1)));
    on("dayNext", "click", () => { const d = hooks.day(); if (d) go(shift(d, 1)); });
    on("dayToday", "click", () => go(""));
    on("dayPick", "click", openPicker);
    on("dayInput", "change", (e) => go(e.target.value));
    render();
  }

  root.DayNav = { init, render, url, emptyText, shift };
})(typeof window !== "undefined" ? window : globalThis);
