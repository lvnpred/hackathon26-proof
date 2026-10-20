/* Sections (plan I2-b): the follow-up date beside the review line and the "not heard" notes under the prose sections.
   Browser global window.Sections; also loads under node with a fake DOM (tests/test_frontend_sections.py). */
(function () {
  "use strict";
  const URL = "/api/v1/review-date";
  const NOTE = { complaints: "pCcNote", diagnosis: "pDxNote", findings: "pFxNote" };
  let H = { post: null, waitMs: 400 };
  let seq = 0;
  let timer = null;

  const $ = (id) => document.getElementById(id);

  function init(hooks) {
    H = { post: (hooks && hooks.post) || null, waitMs: hooks && hooks.waitMs != null ? hooks.waitMs : 400 };
  }

  const dateLabel = (iso) => (window.Dates ? window.Dates.label(iso) : "");   // the same text as core/followup.date_label: one formatter (dates.js)

  function showDate(iso) {
    const n = $("pRevDate");
    if (n) n.textContent = dateLabel(iso) ? "(" + dateLabel(iso) + ")" : "";
  }

  function onReviewInput(text) {                   // the doctor typed: ask the server again; only the newest answer shows
    const tok = ++seq;
    if (timer) clearTimeout(timer);
    showDate("");
    if (!H.post) return;
    timer = setTimeout(() => {
      H.post(URL, { review: String(text || "").slice(0, 1000) }, 10000)
        .then((j) => { if (tok === seq) showDate(j && j.review_date); })
        .catch(() => {});                          // a failed call leaves the review text alone; the date stays empty
    }, H.waitMs);
  }

  function clearProse(field) {
    const n = $(NOTE[field] || "");
    if (n) { n.textContent = ""; n.hidden = true; }
  }

  function showProseCheck(list) {
    const lines = {};                              // field -> note sentences, one per flagged line
    (Array.isArray(list) ? list : []).forEach((e) => {
      if (!e || !NOTE[e.field] || !Array.isArray(e.words) || !e.words.length) return;
      (lines[e.field] = lines[e.field] || []).push("Line " + ((+e.index || 0) + 1) + ": not heard in the dictation: " +
        e.words.map(String).join(", ") + ". Check this line.");
    });
    Object.keys(NOTE).forEach((field) => {
      clearProse(field);
      const n = $(NOTE[field]);
      if (!n || !lines[field]) return;
      n.textContent = lines[field].join(" ");     // text only; set before it is shown so a screen reader announces it
      n.hidden = false;
    });
  }

  window.Sections = { init, dateLabel, showDate, onReviewInput, showProseCheck, clearProse };
})();
