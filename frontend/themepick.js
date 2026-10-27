/* ThemePick (round 2, R4): the screen colour theme, per device. Loaded in <head> so <html data-theme> is set before the
   first paint; theme.css reads it (screen only, so print never changes). Stored in localStorage "dd.theme"; a missing, bad
   or unreadable value is the Regular theme (midnight), and storage errors never throw. The Profile panel's Appearance
   radios follow it and set it at once. Browser global window.ThemePick; also loads under node (tests/test_frontend_themepick.py). */
(function () {
  "use strict";
  const KEY = "dd.theme", THEMES = ["midnight", "ink", "graphite"], FALLBACK = "midnight";
  const valid = (t) => THEMES.indexOf(t) >= 0;
  const radios = () => (typeof document.querySelectorAll === "function" ? [...document.querySelectorAll('input[name="ddTheme"]')] : []);

  function current() {
    try { const t = window.localStorage.getItem(KEY); return valid(t) ? t : FALLBACK; } catch (e) { return FALLBACK; }
  }

  function apply(t) {
    t = valid(t) ? t : FALLBACK;
    document.documentElement.setAttribute("data-theme", t);
    radios().forEach((r) => { r.checked = r.value === t; });
    return t;
  }

  function set(t) {
    t = apply(t);
    try { window.localStorage.setItem(KEY, t); } catch (e) { /* private window or blocked storage: this page only */ }
    return t;
  }

  function wire() {
    radios().forEach((r) => r.addEventListener("change", () => { if (r.checked) set(r.value); }));
    apply(current());
  }

  apply(current());
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire); else wire();
  window.ThemePick = { apply, current, set };
})();
