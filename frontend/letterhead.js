"use strict";
// Letterhead panel (spec 7A.1/7A.3). Loaded after app.js; uses its global loadProfile().
(function () {
  const API = "/api/v1/templates";
  const MAX_BYTES = 8 * 1024 * 1024;            // mirrors TEMPLATE_MAX_IMAGE_BYTES
  const UPLOAD_TIMEOUT_MS = 120000;             // the vision call dominates
  const DOCTOR_KEYS = ["doctor_name", "qualifications", "reg_no"];
  const PROFILE_KEYS = ["doctor_name", "qualifications", "reg_no", "clinic_name", "address", "phone"];
  const PROFILE_LABEL = { doctor_name: "Doctor name", qualifications: "Qualifications",
    reg_no: "Registration no.", clinic_name: "Clinic name", address: "Address", phone: "Phone" };
  const MSG = {
    400: "That file could not be read. Use a JPEG, PNG, iPhone (HEIC) or PDF of the blank pad. A PDF must not be password protected.",
    413: "That picture is too large. Use a photo under 8 MB, for example by scanning at a lower resolution.",
    429: "You have reached today's limit of letterhead uploads. Try again tomorrow, or keep the current layout.",
    502: "The AI could not read this letterhead, and nothing was saved. Try a clearer, straight-on photo, or use the built-in layout.",
    503: "Reading letterheads is not set up on this server (no AI model that can read pictures is configured). Ask your administrator. The built-in layout still works.",
  };
  const lh = { draft: null, abort: null, blobUrl: null, active: false, mine: false, personal: false, choices: null,
    clinicView: null, mineView: null, tidy: null };
  const NUDGE = " Some lines on it look like blank labels from the paper pad. Press Fix lines to check them.";
  const NUDGE_MINE = " Some lines on your letterhead look like blank labels from the paper pad. Press Fix lines on my letterhead to check them.";
  const STALE = "The letterhead changed since you opened it. Close and reopen Fix lines.";
  const WARN_TEXT = "This line may be a doctor's name or degree. Doctor names should come from the doctors choice below, so they stay correct for each prescription.";
  const el = (id) => document.getElementById(id);
  const status = (m) => { el("lhStatus").textContent = m; };
  function showErr(m) { const e = el("lhError"); e.textContent = m || ""; e.hidden = !m; }
  function httpMessage(code, what, body) {
    if (what === "lines") {                // an active letterhead, not a draft
      if (code === 404 || code === 409) return "This letterhead is no longer in use. Close this panel and check the current letterhead.";
      if (code === 400) return (body && body.error) || "A line could not be saved. Check the lines and try again.";
    }
    if (MSG[code] && what === "upload") return MSG[code];
    if (code === 404) return "This draft no longer exists (drafts expire after a day). Upload the picture again.";
    return "Something went wrong (code " + code + "). Try again; if it keeps happening, tell your administrator.";
  }
  function netMessage(e) {
    if (e && e.name === "AbortError") return "That took too long and was stopped. Check your connection and try again.";
    return "Could not reach the server. Check your connection and try again.";
  }
  function setBusy(on, label) {
    el("lhPanel").setAttribute("aria-busy", on ? "true" : "false");
    el("lhPanel").querySelectorAll("button.lh-act, #lhFile").forEach((b) => { b.disabled = on; });
    el("lhProgress").hidden = !on;
    el("lhProgressText").textContent = on ? label : "";
  }
  async function call(url, opts, ms) {
    const ac = new AbortController();
    lh.abort = ac;
    const timer = setTimeout(() => ac.abort(), ms || 30000);
    try { return await fetch(url, Object.assign({}, opts, { signal: ac.signal })); }
    finally { clearTimeout(timer); lh.abort = null; }
  }
  async function json(r) { try { return await r.json(); } catch (e) { return {}; } }
  // The stop button shows only with an active letterhead AND the upload view (never beside the review footer).
  function syncStop() {
    const up = !el("lhUpload").hidden;
    el("lhStopBtn").hidden = !(lh.active && up);
    el("lhTidyBtn").hidden = !(lh.clinicView && up);
    el("lhTidyMineBtn").hidden = !(lh.mineView && up);
  }
  async function refreshStatus() {
    try {
      const r = await call(API + "/current");
      const j = r.ok ? await json(r) : null;
      lh.active = !!(j && j.clinic); lh.mine = !!(j && j.mine); lh.personal = !!(j && j.personal);
      lh.clinicView = (j && j.clinic) || null; lh.mineView = (j && j.mine) || null; syncStop();
      profileStatusLine(!j ? "unknown" : j.clinic ? "active" : "builtin");
      profileMineLine(j);
      status(!j ? "Could not check the current letterhead (code " + r.status + ")."
        : (j.clinic ? "The clinic letterhead is active: prescriptions print on it." : "Using the built-in layout (no clinic letterhead is active).")
          + (j.mine ? " Your own letterhead is active for your prescriptions." : "")
          + (j.clinic && (j.clinic.fill_in || []).length ? NUDGE : "")
          + (j.mine && (j.mine.fill_in || []).length ? NUDGE_MINE : ""));
    } catch (e) {
      lh.active = false; lh.clinicView = null; lh.mineView = null; syncStop(); profileStatusLine("unknown"); profileMineLine(null);
      status("Could not check the current letterhead. " + netMessage(e));
    }
  }
  // ---- Profile dialog entry point (the Letterhead section of #profilePanel) ----
  const PROF_IDS = { doctor_name: "profDoctor", qualifications: "profQual", reg_no: "profReg",
    clinic_name: "profClinic", address: "profAddress", phone: "profPhone" };
  const PROF_LINE = {
    builtin: "Clinic letterhead: none. Prescriptions print on the built-in layout with your clinic details.",
    active: "Clinic letterhead: active. Prescriptions print on it.",
    unknown: "Could not check the current letterhead right now. You can still open the letterhead manager.",
  };
  function profileStatusLine(kind) { el("profLhStatus").textContent = PROF_LINE[kind]; }
  function profileMineLine(j) {
    const line = el("profLhMine"), btn = el("profUseClinicBtn");
    line.hidden = !(j && j.personal); btn.hidden = !(j && j.mine);
    if (j && j.personal) line.textContent = j.mine ? "My own letterhead: active. Only my prescriptions print on it." : "My own letterhead: none.";
  }
  async function useClinic() {
    if (!window.confirm("Your prescriptions will print on the clinic letterhead again. Your own letterhead is kept but no longer used. Continue?")) return;
    const btn = el("profUseClinicBtn"); btn.disabled = true;
    try {
      const r = await call(API + "/deactivate", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope: "mine" }) });
      if (!r.ok) { el("profLhMine").textContent = "Could not switch back (code " + r.status + "). Try again."; return; }
      await refreshStatus();
    } catch (e) { el("profLhMine").textContent = netMessage(e); }
    finally { btn.disabled = false; }
  }
  // Dirty = any of the six inputs or the OP prefix differs from the last loaded/saved profile (state.profile).
  function profileDirty() {
    const saved = (typeof state !== "undefined" && state.profile) || {};
    if (el("profOpPrefix").value.toUpperCase() !== (saved.op_prefix || "").toUpperCase()) return true;
    return Object.keys(PROF_IDS).some((k) => el(PROF_IDS[k]).value !== (saved[k] || ""));
  }
  function syncProfileBtn() {
    const dirty = profileDirty(), b = el("profileLetterheadBtn");
    b.disabled = dirty || (typeof state !== "undefined" && state.working === true);
    if (dirty) b.title = "Save your clinic profile first"; else b.removeAttribute("title");
    el("profLhHint").hidden = !dirty;
  }
  function show(view) {
    el("lhUpload").hidden = view !== "upload";
    const tidy = view === "tidy";
    el("lhReview").hidden = view !== "review" && !tidy;
    el("lhFoot").hidden = view !== "review" && !tidy;
    el("lhDetailsPart").hidden = tidy;                      // fixing the lines of an active letterhead: no details, no accept
    ["lhAcceptBtn", "lhReuploadBtn", "lhBuiltinBtn", "lhUpdateBtn"].forEach((id) => { el(id).hidden = tidy; });
    el("lhTidySaveBtn").hidden = !tidy;
    syncStop();
  }
  async function openPanel() {
    showErr(""); el("lhDone").hidden = true;
    lh.choices = null;                      // colleagues may have been added or disabled since the last opening
    const p = el("lhPanel");
    if (typeof p.showModal === "function") p.showModal(); else p.setAttribute("open", "");
    await refreshStatus();                  // lh.personal must be fresh before the review shows its scope box
    if (lh.draft) renderReview(lh.draft); else { show("upload"); el("lhFile").focus(); }
  }
  function closePanel() {
    const p = el("lhPanel");
    if (typeof p.close === "function") p.close(); else p.removeAttribute("open");
  }
  async function upload(ev) {
    ev.preventDefault();
    showErr("");
    const f = el("lhFile").files[0];
    if (!f) { showErr("Choose a picture of your blank prescription pad first."); el("lhFile").focus(); return; }
    if (f.size > MAX_BYTES) { showErr(MSG[413]); return; }
    const fd = new FormData();
    fd.append("image", f);
    setBusy(true, "Uploading and reading your letterhead. This can take up to a minute…");
    try {
      const r = await call(API, { method: "POST", body: fd }, UPLOAD_TIMEOUT_MS);
      const j = await json(r);
      if (r.status !== 201 && !r.ok) { showErr(httpMessage(r.status, "upload")); return; }
      lh.draft = j;
      renderReview(j);
    } catch (e) { showErr(netMessage(e)); }
    finally { setBusy(false); }
  }
  function field(id, label, value, tag) {
    const w = document.createElement("label");
    w.className = "field"; w.textContent = label;
    const i = document.createElement(tag || "input");
    i.id = id; i.value = value || ""; if (tag === "textarea") i.rows = 2;
    w.appendChild(i); return w;
  }
  function radioValue(name, fallback) {
    const r = document.querySelector('input[name="' + name + '"]:checked');
    return r ? r.value : fallback;
  }
  function renderWarnings(d) {
    el("lhLines").querySelectorAll("input.lh-line-text").forEach((inp) => {
      const id = inp.id + "Warn", old = el(id);
      if (old) old.remove();
      inp.removeAttribute("aria-describedby");
      const hit = (d.warnings || []).some((w) => w.section === inp.dataset.section && w.index === Number(inp.dataset.index));
      if (!hit) return;
      const p = document.createElement("p");
      p.id = id; p.className = "lh-line-warn"; p.textContent = WARN_TEXT;
      inp.setAttribute("aria-describedby", id);
      inp.parentNode.insertAdjacentElement("afterend", p);
    });
  }
  function renderDoctors(d) {
    const mode = (d.doctors && d.doctors.mode) || "author";
    document.querySelectorAll('input[name="lhDoctorsMode"]').forEach((r) => { r.checked = r.value === mode; });
    const names = [];
    (((d.profile || {}).doctor_name || "").split(";").map((t) => t.trim())).concat((d.layout || {}).doctor_hints || []).forEach((n) => {
      if (n && names.indexOf(n) < 0) names.push(n);
    });
    el("lhHints").hidden = !names.length;
    el("lhHints").textContent = names.length ? "Names read from the pad: " + names.join("; ") + ". The app never guesses who they are: choose below." : "";
    el("lhDoctorsBox").hidden = !lh.personal;   // signed in only: single mode has no doctors to choose
    el("lhScopeBox").hidden = !lh.personal;
    document.querySelectorAll('input[name="lhScope"]').forEach((r) => { r.checked = r.value === "clinic"; });
    el("lhDoctorPicks").textContent = "";
    syncPicks();
  }
  async function syncPicks() {
    const box = el("lhDoctorPicks"), mode = radioValue("lhDoctorsMode", "author"), selected = mode === "selected";
    el("lhFillHint").hidden = !(lh.personal && mode === "author");
    box.hidden = !selected;
    if (!selected || box.querySelector("input") || lh.loadingPicks) return;
    lh.loadingPicks = true;
    try { await fillPicks(box); } finally { lh.loadingPicks = false; }
  }
  async function fillPicks(box) {
    if (!lh.choices) {
      box.textContent = "Loading the clinic's doctors…";
      try { const r = await call(API + "/doctors"); lh.choices = r.ok ? ((await json(r)).doctors || []) : null; }
      catch (e) { lh.choices = null; }
      if (!lh.choices) { box.textContent = "Could not load the clinic's doctors. Close and reopen this panel to try again."; return; }
    }
    const ticked = (lh.draft && lh.draft.doctors && lh.draft.doctors.ids) || [];
    box.textContent = lh.choices.length ? "" : "This clinic has no doctor accounts yet.";
    lh.choices.forEach((doc) => {
      const w = document.createElement("label"), c = document.createElement("input");
      c.type = "checkbox"; c.value = String(doc.id); c.checked = ticked.indexOf(doc.id) >= 0;
      w.appendChild(c); w.appendChild(document.createTextNode(" " + doc.name + (doc.qualifications ? ", " + doc.qualifications : "")));
      box.appendChild(w);
    });
  }
  function collectDoctors() {
    const mode = radioValue("lhDoctorsMode", "author"), ids = [];
    el("lhDoctorPicks").querySelectorAll("input:checked").forEach((c) => ids.push(Number(c.value)));
    return { mode: mode, ids: mode === "selected" ? ids : [] };
  }
  async function saveDoctors() {
    if (el("lhDoctorsBox").hidden) return true;   // single mode: nothing to send, the draft stays on author mode
    const r = await call(API + "/" + lh.draft.id + "/doctors", { method: "PUT",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(collectDoctors()) });
    const j = await json(r);
    if (!r.ok) { showErr(j.error || httpMessage(r.status, "doctors")); return false; }
    if (j && j.doctors) lh.draft = Object.assign({}, lh.draft, j);
    return true;
  }
  // The lines and the where-to-print questions; a re-render after a save keeps the labels the doctor unticked.
  function renderLines(d, keepTicks) {
    LhLines.render(el("lhLinesBox"), d, { labels: PROFILE_LABEL, unticked: keepTicks || [] });
  }
  function renderReview(d) {
    show("review");
    renderLines(d, null);
    const pf = el("lhProfileFields"); pf.textContent = "";
    const grid = el("lhDoctorGrid"), hidden = [];     // the doctors are edited side by side; the joined strings live in hidden inputs
    grid.textContent = "";
    grid.parentNode.querySelectorAll('input[type="hidden"][id^="lhProf_"]').forEach((n) => n.remove());   // a re-render starts clean
    PROFILE_KEYS.forEach((k) => {
      if (DOCTOR_KEYS.indexOf(k) < 0) {
        pf.appendChild(field("lhProf_" + k, PROFILE_LABEL[k], (d.profile || {})[k], k === "address" ? "textarea" : "input"));
        return;
      }
      const h = document.createElement("input");
      h.type = "hidden"; h.id = "lhProf_" + k; h.value = (d.profile || {})[k] || "";
      grid.parentNode.insertBefore(h, grid);
      hidden.push(h);
    });
    DoctorGrid.mount(grid, hidden);
    renderWarnings(d); renderDoctors(d);
    loadPreview(lh.draft.id);
    const first = el("lhLines").querySelector("input.lh-line-text") || el("lhProf_clinic_name"); first.focus();
  }
  function collect() {
    const profile = {};
    PROFILE_KEYS.forEach((k) => { profile[k] = el("lhProf_" + k).value.trim(); });
    return Object.assign({ profile: profile }, LhLines.collect(el("lhLinesBox")));
  }
  async function loadPreview(id) {
    const box = el("lhPreview"); box.textContent = "Drawing preview…";
    if (lh.blobUrl) { URL.revokeObjectURL(lh.blobUrl); lh.blobUrl = null; }
    try {
      const r = await call(API + "/" + id + "/preview.pdf?t=" + Date.now(), {}, 60000);
      if (!r.ok) { box.textContent = r.status === 404 ? httpMessage(404) :
        "The preview could not be drawn (code " + r.status + "). Press Update preview to try again."; return; }
      lh.blobUrl = URL.createObjectURL(new Blob([await r.arrayBuffer()], { type: "application/pdf" }));
      box.textContent = "";
      if (navigator.pdfViewerEnabled !== false) {
        const o = document.createElement("object");
        o.data = lh.blobUrl + "#view=Fit&toolbar=0"; o.type = "application/pdf"; o.setAttribute("aria-label", "Page 1 preview");
        box.appendChild(o);
      } else {
        const p = document.createElement("p");
        p.textContent = "This browser cannot show a PDF inside the page. ";
        const a = document.createElement("a");
        a.href = lh.blobUrl; a.target = "_blank"; a.rel = "noopener"; a.textContent = "Open the page 1 preview in a new tab";
        p.appendChild(a); box.appendChild(p);
      }
    } catch (e) { box.textContent = "The preview could not be loaded. " + netMessage(e); }
  }
  async function saveEdits() {
    const r = await call(API + "/" + lh.draft.id, { method: "PUT",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(collect()) });
    if (!r.ok) { showErr(httpMessage(r.status, "edit")); return false; }
    const j = await json(r);
    if (j && j.layout) {
      lh.draft = Object.assign({}, lh.draft, j);
      renderLines(lh.draft, LhLines.unticked(el("lhLinesBox")));   // removed lines are gone: the line numbers moved
    }
    return true;
  }
  async function updatePreview() {
    showErr(""); setBusy(true, "Saving your edits…");
    try { if (await saveEdits() && await saveDoctors()) { renderWarnings(lh.draft); await loadPreview(lh.draft.id); } } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  async function accept() {
    showErr(""); setBusy(true, "Saving your letterhead…");
    try {
      if (!(await saveEdits()) || !(await saveDoctors())) return;
      const mine = lh.personal && radioValue("lhScope", "clinic") === "mine";
      const r = await call(API + "/" + lh.draft.id + "/accept", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scope: mine ? "mine" : "clinic" }) });
      if (!r.ok) { showErr(httpMessage(r.status, "accept")); return; }
      lh.draft = null;
      if (typeof loadProfile === "function") await loadProfile();
      syncProfileBtn();
      show("upload"); el("lhFile").value = "";
      el("lhDone").hidden = false;
      el("lhDone").textContent = mine
        ? "Done. Your own letterhead is saved. Only your prescriptions print on it; colleagues keep the clinic letterhead."
        : "Done. The clinic letterhead is saved, and its clinic details were saved to the Profile. New prescriptions print on it.";
      refreshStatus();
    } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  // Fix the lines of an ACTIVE letterhead from the screen: no draft, no accept, the change is live on save.
  function openTidy(view) {
    showErr(""); el("lhDone").hidden = true;
    lh.tidy = view;
    show("tidy");
    renderLines(view, null);   // no doctor-name warnings here: their text points at the hidden doctors choice
    loadPreview(view.id);
    const first = el("lhLines").querySelector("input.lh-line-text"); if (first) first.focus();
  }
  async function saveTidy() {
    showErr(""); el("lhDone").hidden = true; setBusy(true, "Saving the lines…");
    try {
      const r = await call(API + "/" + lh.tidy.id + "/lines", { method: "PUT",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(LhLines.collect(el("lhLinesBox"))) });
      const j = await json(r);
      if (!r.ok) {
        const stale = r.status === 400 && /letterhead changed|no such line/.test((j && j.error) || "");
        showErr(stale ? STALE : httpMessage(r.status, "lines", j));
        if (r.status === 400) refreshStatus();
        return;
      }
      if (j && j.layout) {
        lh.tidy = Object.assign({}, lh.tidy, j);
        renderLines(lh.tidy, LhLines.unticked(el("lhLinesBox")));   // removed lines are gone: the numbers moved
        loadPreview(lh.tidy.id);
      }
      el("lhDone").hidden = false;
      el("lhDone").textContent = "Saved. New prescriptions and re-prints use the fixed letterhead.";
      refreshStatus();
    } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  async function discard(thenUpload) {
    showErr(""); setBusy(true, "Discarding the draft…");
    try {
      const r = await call(API + "/" + lh.draft.id, { method: "DELETE" });
      if (!r.ok && r.status !== 404) { showErr(httpMessage(r.status, "discard")); return; }
      lh.draft = null; el("lhFile").value = ""; show("upload");
      refreshStatus();
      if (thenUpload) { setBusy(false); el("lhFile").focus(); }  // a disabled input cannot take focus
      else { el("lhDone").hidden = false; el("lhDone").textContent = "The draft was discarded. Nothing about your prescriptions changed."; }
    } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  async function useDetails() {
    showErr(""); setBusy(true, "Saving your clinic details…");
    try {
      if (!(await saveEdits())) return;
      const r = await call(API + "/" + lh.draft.id + "/use-details", { method: "POST" });
      if (!r.ok) { showErr(httpMessage(r.status, "use-details")); return; }
      lh.draft = null;
      if (typeof loadProfile === "function") await loadProfile();
      syncProfileBtn();
      el("lhFile").value = ""; show("upload");
      await refreshStatus();
      el("lhDone").hidden = false;
      el("lhDone").textContent = "Your clinic details were saved to your Profile. " +
        (lh.active ? "Your accepted letterhead stays active." : "The built-in layout stays in use.");
    } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  async function stopUsing() {
    if (!window.confirm("Prescriptions will print on the built-in layout again. Your accepted letterhead is kept but no longer used. Continue?")) return;
    showErr(""); el("lhDone").hidden = true; setBusy(true, "Switching to the built-in layout…");
    try {
      const r = await call(API + "/deactivate", { method: "POST" });
      if (!r.ok) { showErr(httpMessage(r.status, "stop")); return; }
      await refreshStatus();
      el("lhDone").hidden = false;
      el("lhDone").textContent = "Done. Prescriptions now print on the built-in layout with your clinic details.";
    } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  el("profileLetterheadBtn").addEventListener("click", openPanel);
  el("profileForm").addEventListener("input", syncProfileBtn);
  // app.js's own click handler (bound earlier) has already filled the form when this runs.
  el("profileOpenBtn").addEventListener("click", () => { syncProfileBtn(); refreshStatus(); });
  el("lhPanel").addEventListener("close", () => {
    syncProfileBtn();
    const b = el("profileLetterheadBtn");
    if (el("profilePanel").open && !b.disabled) b.focus();
  });
  el("lhCloseBtn").addEventListener("click", closePanel);
  el("lhPanel").addEventListener("close", () => { if (lh.abort && !lh.draft) lh.abort.abort(); });
  el("lhPanel").addEventListener("close", () => { lh.tidy = null; });
  el("lhStopBtn").addEventListener("click", stopUsing);
  el("lhTidyBtn").addEventListener("click", () => lh.clinicView && openTidy(lh.clinicView));
  el("lhTidyMineBtn").addEventListener("click", () => lh.mineView && openTidy(lh.mineView));
  el("lhTidySaveBtn").addEventListener("click", saveTidy);
  el("lhUploadForm").addEventListener("submit", upload);
  el("lhUpdateBtn").addEventListener("click", updatePreview);
  el("lhAcceptBtn").addEventListener("click", accept);
  document.querySelectorAll('input[name="lhDoctorsMode"]').forEach((r) => r.addEventListener("change", syncPicks));
  el("profUseClinicBtn").addEventListener("click", useClinic);
  el("lhReuploadBtn").addEventListener("click", () => discard(true));
  el("lhBuiltinBtn").addEventListener("click", useDetails);
})();
