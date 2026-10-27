"use strict";
// Share dialog (owner feedback C2): shows the private download link of a saved prescription as a QR and a link, opens WhatsApp
// or the mail app with the server's fixed text, and lets the author or a clinic admin turn the link off.
// The patient's phone number stays in the input; it is never stored or sent to the server. Loaded BEFORE app.js; also loads under node.
(function (root) {
  const $ = (id) => root.document.getElementById(id);
  const MSG = {
    revoked: "This link was turned off.",
    old: "This prescription was saved before sharing was added.",
    missing: "This prescription could not be found.",
    dead: "This link can no longer be used. Print a fresh copy for the patient.",
    gone: "The share link could not be loaded. Please try again.",
  };
  const NO_LINK = "no share link for this prescription";     // the server's text for "saved, but no link yet"
  const PHONE_HINT = "Enter the patient's 10-digit mobile number";
  let docId = () => null;
  let info = null;

  function normalizePhone(raw) {
    const s = String(raw == null ? "" : raw).trim();
    const d = s.replace(/\D/g, "");
    if (s.startsWith("+")) return d.length >= 8 && d.length <= 15 ? d : null;
    if (d.length === 10 && /^[6-9]/.test(d)) return "91" + d;
    if (d.length === 11 && d[0] === "0") return "91" + d.slice(1);
    if (d.length === 12 && d.startsWith("91")) return d;
    return null;
  }

  const whatsappUrl = (phone, message) => "https://wa.me/" + phone + "?text=" + encodeURIComponent(message);
  const mailtoUrl = (subject, body) => "mailto:?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);

  function sync(printBtn) {                              // Share follows Print: saved, no unsaved change, not busy
    const b = $("shareBtn");
    if (!b) return;
    b.hidden = printBtn.hidden;
    b.disabled = printBtn.disabled;
  }

  function phoneState() {
    const ok = !!(info && info.active && normalizePhone($("shareTel").value));
    $("shareWa").disabled = !ok;
    $("shareWa").title = ok ? "" : PHONE_HINT;
  }

  function clearPhone() {
    $("shareTel").value = "";
    info = null;
    phoneState();
  }

  function show(j, note) {                               // j: the server's share JSON, or null with a note only
    info = j;
    const live = !!(j && j.active);
    $("shareMsg").textContent = note || "";
    const qr = live ? String(j.qr || "") : "";
    const qrOk = qr.startsWith("data:image/svg+xml");
    $("shareQr").hidden = !qrOk;
    $("shareQr").src = qrOk ? qr : "";
    $("shareWa").hidden = !live;
    $("shareMail").hidden = !live;
    $("shareTel").hidden = !live;
    $("shareLink").hidden = !live;
    $("shareCopy").hidden = !live;
    $("shareUntil").textContent = live ? "Valid until " + j.valid_until : "";
    $("shareRevoke").hidden = !(j && j.can_revoke && j.active);
    if (live) {
      $("shareLink").value = j.url;
    } else {
      $("shareLink").value = "";
    }
    phoneState();
  }

  async function open() {
    const id = docId();
    if (id == null) return;
    clearPhone();                                        // never carry one patient's number to another prescription
    let r, j = null;
    try {
      r = await root.fetch("/api/v1/documents/" + encodeURIComponent(id) + "/share", { cache: "no-store" });
      j = await r.json().catch(() => null);
    } catch (e) { r = null; }
    if (r && r.ok && j) {
      show(j, j.active ? "" : j.revoked ? MSG.revoked
        : j.renewable === false ? MSG.dead
        : "This link expired on " + j.valid_until + ". Save the prescription again for a new one.");
    } else if (r && r.status === 404) show(null, j && j.error === NO_LINK ? MSG.old : MSG.missing);
    else show(null, (r && j && j.error) || MSG.gone);
    if (!$("shareDlg").open) $("shareDlg").showModal();
  }

  async function revoke() {
    const id = docId();
    if (id == null || !root.confirm("Turn off this link? The printed QR stops working too.")) return;
    let r, j = null;
    try {
      r = await root.fetch("/api/v1/documents/" + encodeURIComponent(id) + "/share/revoke", { method: "POST" });
      j = await r.json().catch(() => null);
    } catch (e) { r = null; }
    if (r && r.ok) return open();
    $("shareMsg").textContent = (r && j && j.error) || MSG.gone;
  }

  async function copy() {
    try { await root.navigator.clipboard.writeText($("shareLink").value); $("shareMsg").textContent = "Link copied."; }
    catch (e) { $("shareLink").select && $("shareLink").select(); $("shareMsg").textContent = "Press Ctrl+C to copy the link."; }
  }

  function init(opts) {
    docId = opts.documentId;
    $("shareBtn").addEventListener("click", open);
    $("shareTel").addEventListener("input", phoneState);
    $("shareWa").addEventListener("click", () => {
      const phone = normalizePhone($("shareTel").value);
      if (phone && info && info.active) root.open(whatsappUrl(phone, info.message), "_blank", "noopener");
    });
    $("shareMail").addEventListener("click", () => { if (info && info.active) root.location.href = mailtoUrl(info.subject, info.message); });
    $("shareRevoke").addEventListener("click", revoke);
    $("shareCopy").addEventListener("click", copy);
    $("shareClose").addEventListener("click", () => $("shareDlg").close());
    $("shareDlg").addEventListener("close", clearPhone);
  }

  const api = { init, sync, open, normalizePhone, whatsappUrl, mailtoUrl };
  root.Share = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
