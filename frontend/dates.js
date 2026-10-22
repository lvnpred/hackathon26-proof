"use strict";
/* Dates (iteration 3): the one place the page formats a date or a time. Same tables and same text as core/datefmt.py,
   and both are tested against tests/data/date_formats.json, so screen and print agree. Browser global window.Dates;
   also loads under node for tests. The locale and the clinic time zone come from /api/health (init); Intl is used ONLY to
   convert an instant into the clinic zone, the text is built from the tables below, so every browser prints the same. */
(function (root) {
  const TABLES = {
    "en-IN": {
      months: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
      days: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],              // Monday first, as the server
      am: "am", pm: "pm",
    },
  };
  const DEFAULT_LOCALE = "en-IN", DEFAULT_ZONE = "Asia/Kolkata";            // the same defaults as the server
  let locale = DEFAULT_LOCALE, zone = DEFAULT_ZONE;
  const table = () => TABLES[locale] || TABLES[DEFAULT_LOCALE];

  function init(h) {                                                        // h: { locale | date_locale, timezone }, e.g. the /api/health body
    h = h || {};
    const wanted = String(h.date_locale || h.locale || "").trim();
    locale = TABLES[wanted] ? wanted : DEFAULT_LOCALE;
    zone = String(h.timezone || "").trim() || DEFAULT_ZONE;
  }

  function parts(instant) {                                                 // y, m, d, hh, mm of an instant in the clinic zone; null if invalid
    const t = instant instanceof Date ? instant : (typeof instant === "string" && instant ? new Date(instant) : null);
    if (!t || isNaN(t.getTime())) return null;
    try {
      const got = {};
      new Intl.DateTimeFormat("en-US", { timeZone: zone, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric" })
        .formatToParts(t).forEach((p) => { got[p.type] = +p.value; });
      return { y: got.year, m: got.month, d: got.day, hh: got.hour % 24, mm: got.minute };
    } catch (e) {                                                           // an unknown zone name: the browser's own zone
      return { y: t.getFullYear(), m: t.getMonth() + 1, d: t.getDate(), hh: t.getHours(), mm: t.getMinutes() };
    }
  }

  function ymd(iso) {                                                       // a strict YYYY-MM-DD that is a real day, else null
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(typeof iso === "string" ? iso : "");
    if (!m) return null;
    if (+m[1] < 1000) return null;                                          // one rule with the server: Date.UTC maps years 0-99 to 1900-1999
    const t = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    return t.getUTCFullYear() === +m[1] && t.getUTCMonth() === +m[2] - 1 && t.getUTCDate() === +m[3] ? { y: +m[1], m: +m[2], d: +m[3], t } : null;
  }

  const dateText = (y, m, d) => d + " " + table().months[m - 1] + " " + y;
  const timeText = (hh, mm) => (hh % 12 || 12) + ":" + String(mm).padStart(2, "0") + " " + (hh >= 12 ? table().pm : table().am);

  const date = (iso) => { const p = ymd(iso); return p ? dateText(p.y, p.m, p.d) : ""; };                       // "17 Oct 2026"
  const label = (iso) => { const p = ymd(iso); return p ? table().days[(p.t.getUTCDay() + 6) % 7] + " " + dateText(p.y, p.m, p.d) : ""; };   // "Sat 24 Oct 2026"
  const time = (instant) => { const p = parts(instant); return p ? timeText(p.hh, p.mm) : ""; };               // "3:05 pm"
  const dateTime = (instant) => { const p = parts(instant); return p ? dateText(p.y, p.m, p.d) + ", " + timeText(p.hh, p.mm) : ""; };
  const today = (now) => { const p = parts(now || new Date()); return p ? dateText(p.y, p.m, p.d) : ""; };      // the clinic day
  const pad2 = (n) => String(n).padStart(2, "0");
  const todayIso = (now) => { const p = parts(now || new Date()); return p ? p.y + "-" + pad2(p.m) + "-" + pad2(p.d) : ""; };   // "2026-10-17", the clinic day
  const short = (iso) => { const p = ymd(iso); return p ? table().days[(p.t.getUTCDay() + 6) % 7] + ", " + p.d + " " + table().months[p.m - 1] : ""; };   // "Sat, 17 Oct"

  // The page starts before /api/health answers: it shows the default day. When health arrives, apply it, and re-default the
  // sheet date node only if it still shows what the default produced (the field is read-only; a reopened document's own
  // visit day differs from the default and is left alone).
  function initFrom(h, node, now) {
    const before = today(now);
    init(h);
    if (node && node.textContent === before) node.textContent = today(now);
  }

  root.Dates = { init, initFrom, date, label, short, time, dateTime, today, todayIso, locale: () => locale, zone: () => zone, tables: TABLES };   // tables: tests add a locale to prove init reads the health field
  if (typeof module !== "undefined" && module.exports) module.exports = root.Dates;
})(typeof window !== "undefined" ? window : globalThis);
