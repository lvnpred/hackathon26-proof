// Save & admit to ward (spec §6.1, §7.1). The doctor types a one-line reason (required); the save then runs through
// app.js's own saveDocument with `admit` and `admit_reason` added (window.ddAdmit, cleared in finally), and the page
// polls GET /api/v1/documents/{id}/admission until Count Guard has the patient. A failed push never undoes the save.
(function (root) {
  "use strict";
  const MSG = {
    sending: "Saved. Sending to Count Guard…",
    done: "Saved and in Count Guard.",
    notYet: "Saved. Not yet in Count Guard — use Sync there.",
    needReason: "Type the reason for admission, then press “Save & admit to ward” again.",
  };
  const TRIES = 5, EVERY_MS = 1000;

  // env: { fetch, wait(ms) } -> one of MSG.done / MSG.notYet.
  async function poll(documentId, env) {
    const url = "/api/v1/documents/" + encodeURIComponent(documentId) + "/admission";
    for (let i = 0; i < TRIES; i++) {
      await env.wait(EVERY_MS);
      try {
        const r = await env.fetch(url, { headers: { Accept: "application/json" } });
        if (r.status === 404) break;                 // nothing recorded (e.g. multi-clinic): it will not arrive
        if (!r.ok) continue;
        const j = await r.json();
        if (j && j.pushed_at) return MSG.done;
        if (j && j.last_error) return MSG.notYet;
      } catch (_e) { /* a network blip: try again */ }
    }
    return MSG.notYet;
  }

  // env: { reason(), askReason(), save(), setStatus(msg), fetch, wait } -> the final status, or null when not saved.
  async function admitAndSave(env) {
    const reason = String(env.reason() || "").trim();
    if (!reason) { env.askReason(); env.setStatus(MSG.needReason); return null; }
    root.ddAdmit = { admit: true, admit_reason: reason };
    let j;
    try { j = await env.save(); } finally { delete root.ddAdmit; }
    if (!j || j.document_id == null) return null;   // blocked, refused or failed: app.js already said why
    env.setStatus(MSG.sending);
    const msg = await poll(j.document_id, env);
    env.setStatus(msg);
    return msg;
  }

  // The admit button follows #saveBtn: shown, hidden and disabled together (New patient hides both, a block disables both).
  function wire(doc) {
    const saveBtn = doc.getElementById("saveBtn"), row = doc.getElementById("admitRow");
    const btn = doc.getElementById("admitBtn"), input = doc.getElementById("admitReason");
    if (!saveBtn || !row || !btn || !input) return;
    const follow = () => {
      row.hidden = saveBtn.hidden;
      btn.disabled = saveBtn.disabled;
      if (saveBtn.hidden) { input.value = ""; input.hidden = true; }
    };
    follow();
    new root.MutationObserver(follow).observe(saveBtn, { attributes: true, attributeFilter: ["hidden", "disabled"] });
    const env = {
      reason: () => (input.hidden ? "" : input.value),
      askReason: () => { input.hidden = false; input.focus(); },
      save: () => root.saveDocument(),
      setStatus: (m) => root.setStatus(m),
      fetch: (u, o) => root.fetch(u, o),
      wait: (ms) => new Promise((res) => root.setTimeout(res, ms)),
    };
    btn.addEventListener("click", () => { if (!btn.disabled) admitAndSave(env); });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); btn.click(); } });
  }

  const api = { MSG, poll, admitAndSave, wire };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else { root.Admit = api; wire(root.document); }
})(typeof window !== "undefined" ? window : globalThis);
