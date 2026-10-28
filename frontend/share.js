"use strict";
// Share dialog (owner feedback C2): shows the private download link of a saved prescription as a QR and a link, opens WhatsApp,
// SMS, a Gmail or Outlook compose tab or the mail app with the server's fixed text, and lets the author or a clinic admin turn
// the link off. The patient's phone number and email stay in their inputs; they are never stored or sent to the server. Only the
// "Email with" choice is remembered, per browser. Loaded BEFORE app.js; also loads under node.
(function (root) {
  const $ = (id) => root.document.getElementById(id);
  const MSG = {
    revoked: "This link was turned off.",
    old: "This prescription was saved before sharing was added.",
    missing: "This prescription could not be found.",
    dead: "This link can no longer be used. Print a fresh copy for the patient.",
    gone: "The share link could not be loaded. Try again.",
  };
  const NO_LINK = "no share link for this prescription";     // the server's text for "saved, but no link yet"
  const PHONE_HINT = "Enter the patient's 10-digit mobile number";
  const EMAIL_HINT = "Check the patient's email address";
  const VIA_KEY = "dd.mailVia", VIAS = ["gmail", "outlook", "app"];
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
  const mailtoUrl = (subject, body, to) => "mailto:" + encodeURIComponent(to || "") + "?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
  const smsUrl = (phone, message) => "sms:+" + phone + "?&body=" + encodeURIComponent(message);   // "?&" reads on both iOS and Android

  function mailUrl(via, to, subject, body) {             // via: gmail | outlook (a compose page in a new tab) | app (mailto)
    const e = encodeURIComponent;
    if (via === "gmail") return "https://mail.google.com/mail/?view=cm&fs=1&to=" + e(to || "") + "&su=" + e(subject) + "&body=" + e(body);
    if (via === "outlook") return "https://outlook.live.com/mail/0/deeplink/compose?to=" + e(to || "") + "&subject=" + e(subject) + "&body=" + e(body);
    return mailtoUrl(subject, body, to);
  }

  function normalizeEmail(raw) {                         // "" is fine (the doctor types it in the mail tab); a bad address is null
    const s = String(raw == null ? "" : raw).trim();
    if (!s) return "";
    return /^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$/.test(s) && s.length <= 254 ? s : null;
  }

  function savedVia() {
    try { const v = root.localStorage.getItem(VIA_KEY); return VIAS.includes(v) ? v : "gmail"; } catch (e) { return "gmail"; }
  }
  function keepVia(v) { try { root.localStorage.setItem(VIA_KEY, v); } catch (e) { /* private window: the choice is not kept */ } }

  function sync(printBtn) {                              // Share follows Print: saved, no unsaved change, not busy
    const b = $("shareBtn");
    if (!b) return;
    b.hidden = printBtn.hidden;
    b.disabled = printBtn.disabled;
  }

  function phoneState() {
    const ok = !!(info && info.active && normalizePhone($("shareTel").value));
    ["shareWa", "shareSms"].forEach((id) => { $(id).disabled = !ok; $(id).title = ok ? "" : PHONE_HINT; });
    const mailOk = !!(info && info.active) && normalizeEmail($("shareEmail").value) !== null;
    $("shareMail").disabled = !mailOk;
    $("shareMail").title = mailOk ? "" : EMAIL_HINT;
  }

  function clearPhone() {                                // also clears the email: neither outlives the dialog
    $("shareTel").value = "";
    $("shareEmail").value = "";
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
    ["shareWa", "shareMail", "shareTel", "shareEmail", "shareVia", "shareLink", "shareCopy", "shareCopyMsg"].forEach((id) => { $(id).hidden = !live; });
    $("shareSms").hidden = !(live && coarse());
    $("shareMore").hidden = !(live && typeof root.navigator.share === "function");
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

  async function copyMessage() {
    if (!(info && info.active)) return;
    try { await root.navigator.clipboard.writeText(info.message); $("shareMsg").textContent = "Message copied."; }
    catch (e) { $("shareMsg").textContent = "The message could not be copied. Use Copy link instead."; }
  }

  async function more() {                                // the phone's own share sheet: WhatsApp, Gmail, SMS and the rest
    if (!(info && info.active)) return;
    try { await root.navigator.share({ title: info.subject, text: info.message }); }
    catch (e) { if (!e || e.name !== "AbortError") $("shareMsg").textContent = "Sharing is not available here. Use Copy message."; }
  }

  function coarse() {                                    // phones and tablets: SMS only makes sense there
    try { return !!(root.matchMedia && root.matchMedia("(pointer: coarse)").matches); } catch (e) { return false; }
  }

  function mail() {
    const to = normalizeEmail($("shareEmail").value);
    if (!(info && info.active) || to === null) return;
    const via = VIAS.includes($("shareVia").value) ? $("shareVia").value : "gmail";
    const url = mailUrl(via, to, info.subject, info.message);
    if (via === "app") root.location.href = url;
    else root.open(url, "_blank", "noopener");
  }

  function init(opts) {
    docId = opts.documentId;
    $("shareBtn").addEventListener("click", open);
    $("shareTel").addEventListener("input", phoneState);
    $("shareEmail").addEventListener("input", phoneState);
    $("shareVia").value = savedVia();
    $("shareVia").addEventListener("change", () => keepVia($("shareVia").value));
    $("shareWa").addEventListener("click", () => {
      const phone = normalizePhone($("shareTel").value);
      if (phone && info && info.active) root.open(whatsappUrl(phone, info.message), "_blank", "noopener");
    });
    $("shareSms").addEventListener("click", () => {
      const phone = normalizePhone($("shareTel").value);
      if (phone && info && info.active) root.location.href = smsUrl(phone, info.message);
    });
    $("shareMail").addEventListener("click", mail);
    $("shareMore").addEventListener("click", more);
    $("shareRevoke").addEventListener("click", revoke);
    $("shareCopy").addEventListener("click", copy);
    $("shareCopyMsg").addEventListener("click", copyMessage);
    $("shareClose").addEventListener("click", () => $("shareDlg").close());
    $("shareDlg").addEventListener("close", clearPhone);
  }

  const api = { init, sync, open, normalizePhone, normalizeEmail, whatsappUrl, mailtoUrl, mailUrl, smsUrl };
  root.Share = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
