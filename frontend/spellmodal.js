"use strict";
// Spell it as a modal dialog (plan I2-c): open, close, focus trap, keys, paging and the microphone. The row rules (request token, confirmed set
// before the render, Undo record, stale-answer drops) stay in rxview.js: it calls open() with what to run, and this file never changes a row.
// DOM is built with createElement and textContent only (SugList builds the list). The clip goes to the one hook H.transcribe, nowhere else.
window.SpellModal = (function () {
  const PAGE_KEYS = { PageDown: 1, PageUp: -1 };
  const MSG_NOVOICE = "Voice input is not available in this browser.", MSG_VIEW = "This prescription is view only.", MSG_WAIT = "Wait for the page to finish, then try again.";
  let H = null, cur = null, tok = 0, bound = null;
  let rec = null, stream = null, timer = null, vid = 0, phase = "";       // voice: the recorder, its stream, the cap timer, a session id and "starting" | "recording" | "reading"
  const $ = (id) => document.getElementById(id);
  const micAllowed = () => !H.working() && !H.viewOnly() && !H.recording();
  const isOpenFor = (rowid) => !!cur && cur.rowid === rowid;
  // Two live regions, one at a time: errors in #spellMsg (role=alert), progress and hints in #spellInfo (role=status, polite).
  const say = (m, info) => { $("spellMsg").textContent = info ? "" : (m || ""); $("spellInfo").textContent = info ? (m || "") : ""; };
  const blockedWhy = () => (H.viewOnly() ? MSG_VIEW : H.working() ? "Wait for the page to finish." : "");
  const voiceReady = () => { const md = H.media(); return !!(md && typeof md.getUserMedia === "function" && H.Recorder()); };
  const optionsOf = (res) => (Array.isArray(res && res.options) ? res.options : (Array.isArray(res && res.suggestions) ? res.suggestions.map((n) => ({ name: String(n), generic: "", reason: "" })) : []))
    .filter((o) => o && typeof o.name === "string" && o.name);
  const stopTracks = (s) => { try { s.getTracks().forEach((t) => t.stop()); } catch (e) { /* already stopped */ } };
  const closeDialog = () => { if (typeof H.dialog.close === "function") H.dialog.close(); else H.dialog.removeAttribute("open"); };
  function focusables() {
    return [$("spellInput"), $("spellMic"), ...$("spellList").children, $("spellPrev"), $("spellNext"), $("spellClose"), $("spellUse")].filter((n) => !n.disabled && !n.hidden);
  }
  function micTitle() {
    if (blockedWhy()) return blockedWhy();
    if (!voiceReady()) return MSG_NOVOICE;
    if (H.recording()) return "Stop the dictation first.";
    if (cur && cur.checking) return "Wait for the check to finish.";
    return "Say the name. It fills the box; nothing changes until you press Use this.";
  }
  function show() {                                   // draw the current page, the label and which controls work
    if (!cur) return;
    const list = $("spellList"), at = document.activeElement, wasItem = [...list.children].includes(at);
    const p = SugList.page(cur.items, cur.page, cur.total); cur.page = p.index;
    SugList.list(list, p.items);
    const off = cur.checking, blocked = !!blockedWhy();   // Close stays usable: a check can be left running behind the row's own spinner
    [...list.children].forEach((b) => { b.disabled = off || blocked; });
    $("spellInput").disabled = off; $("spellUse").disabled = off || blocked;
    $("spellPrev").disabled = off || !p.hasPrev; $("spellNext").disabled = off || !p.hasNext;
    $("spellPage").textContent = cur.searching ? "Searching..." : cur.loading ? "Looking for names..." : (cur.lead || "") + p.label;
    $("spellMic").disabled = off || !micAllowed() || !voiceReady(); $("spellMic").title = micTitle();
    if (off && at && at !== $("spellClose") && focusables().indexOf(at) < 0) $("spellClose").focus();     // a disabled control cannot keep focus
    else if (wasItem) (list.children[0] || $("spellInput")).focus();                                       // the item on screen was replaced by the new page
    else if (at && at.disabled) (!$("spellPrev").disabled ? $("spellPrev") : !$("spellNext").disabled ? $("spellNext") : $("spellInput")).focus();
  }
  function open(spec) {                               // spec: {rowid, title, opener(), problem, load(), use(name), alive(), onClose()}
    if (cur) close(false);
    cur = Object.assign({ items: [], total: 0, page: 0, loading: !spec.problem, checking: false, searching: false, searched: false, lead: "", sid: 0, first: { items: [], total: 0 }, alive: () => true, tok: ++tok }, spec);
    $("spellTitle").textContent = spec.title; $("spellInput").value = ""; say(spec.problem || "");
    if (!spec.problem && !voiceReady()) say(MSG_NOVOICE, true);
    const b = spec.opener && spec.opener(); if (b) b.setAttribute("aria-expanded", "true");
    if (H.dialog.open) closeDialog();
    if (typeof H.dialog.showModal === "function") H.dialog.showModal(); else H.dialog.setAttribute("open", "");
    show(); $("spellInput").focus();
    if (spec.problem) return;
    const mine = cur.tok;
    spec.load().then((res) => {
      if (!cur || cur.tok !== mine) return;          // closed, or another row opened: drop it
      const items = optionsOf(res), total = +(res && res.total) || items.length;
      cur.first = { items, total }; cur.loading = false;
      if (!cur.searched) { cur.items = items; cur.total = total; }                  // a typed search that answered first keeps its list
      show();
    }).catch((e) => { if (cur && cur.tok === mine) { cur.loading = false; show(); say(RxState.errorText(e) + " You can still type the name."); } });
  }
  function close(refocus) {
    if (!cur) return;
    cancelSearch(); const c = cur; cur = null; stopVoice();
    closeDialog();
    const b = c.opener && c.opener(); if (b) b.setAttribute("aria-expanded", "false");
    if (refocus && c.onClose) c.onClose();
  }
  function use(name) {
    if (!cur || cur.checking) return;
    if (H.viewOnly()) { say(MSG_VIEW); return; }
    if (H.working()) { say(MSG_WAIT); return; }
    if (!cur.alive()) { close(false); return; }
    stopVoice(); cancelSearch();                      // a clip or a search in progress is not wanted any more
    cur.use(name);
  }
  function onKey(e) {
    if (!cur) return;
    const items = [...$("spellList").children], i = items.indexOf(e.target);
    if (e.key === "Escape") { e.preventDefault(); close(true); }
    else if (Object.prototype.hasOwnProperty.call(PAGE_KEYS, e.key)) { e.preventDefault(); cur.page += PAGE_KEYS[e.key]; cur.lead = ""; show(); }
    else if (e.key === "Tab") {
      const f = focusables(), at = f.indexOf(document.activeElement);
      if (!f.length) return;
      if (e.shiftKey && at <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && at === f.length - 1) { e.preventDefault(); f[0].focus(); }
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!items.length || (i < 0 && e.target !== $("spellInput"))) return;
      e.preventDefault(); items[i < 0 ? 0 : Math.min(items.length - 1, Math.max(0, i + (e.key === "ArrowDown" ? 1 : -1)))].focus();
    } else if (e.key === "Enter" && e.target === $("spellInput")) { e.preventDefault(); use($("spellInput").value); }
    else if ((e.key === "Enter" || e.key === " ") && i >= 0) { e.preventDefault(); use(items[i].dataset.value); }
  }
  function onClick(e) {
    const t = e.target, b = t && t.closest ? t.closest("button") : null;
    if (!cur || !b || b.disabled) return;
    if (b.id === "spellClose") close(true);
    else if (b.id === "spellUse") use($("spellInput").value);
    else if (b.id === "spellPrev" || b.id === "spellNext") { cur.page += b.id === "spellNext" ? 1 : -1; cur.lead = ""; show(); }
    else if (b.id === "spellMic") toggleVoice();
    else if (b.dataset.action === "pick") use(b.dataset.value);
  }
  // ---- typing: a pause after the last key re-checks the typed name and replaces the list; emptying the field brings the first list back ----
  function cancelSearch() {
    if (!cur) return;
    if (cur.timer) { clearTimeout(cur.timer); cur.timer = null; }
    if (cur.ctrl) { cur.ctrl.abort(); cur.ctrl = null; }
    cur.sid++; cur.searching = false;
  }
  function typed() {
    if (!cur || !cur.search) return;
    cancelSearch();
    const name = RxState.cleanTyped($("spellInput").value);
    if (!name) { if (cur.first) { cur.items = cur.first.items; cur.total = cur.first.total; cur.page = 0; cur.lead = ""; cur.searched = false; } if (cur.searchErr) { cur.searchErr = false; say(""); } show(); return; }
    if ((name.match(/[A-Za-z]/g) || []).length < 2 || RxState.typedProblem(name)) { show(); return; }       // too short, or what Use this would refuse: no request
    const c = cur, sid = c.sid;
    c.timer = setTimeout(() => { c.timer = null; runSearch(c, sid, name); }, H.searchMs);
  }
  function runSearch(c, sid, name) {
    if (cur !== c || c.sid !== sid || c.checking || blockedWhy()) return;
    if (c.searchErr) { c.searchErr = false; say(""); }
    c.ctrl = typeof AbortController === "function" ? new AbortController() : null; c.searching = true; c.lead = ""; show();
    c.search(name, c.ctrl && c.ctrl.signal).then((res) => {
      if (cur !== c || c.sid !== sid) return;          // closed, typed again or used: drop it
      c.items = optionsOf(res); c.total = +(res && res.total) || c.items.length; c.page = 0; c.searching = false; c.searched = true; c.ctrl = null;
      c.lead = c.items.length ? c.items.length + (c.items.length === 1 ? " suggestion. " : " suggestions. ") : ""; show();
    }).catch(() => {
      if (cur !== c || c.sid !== sid) return;
      c.searching = false; c.ctrl = null; c.searchErr = true; show(); say("Could not update the names. The list is unchanged. You can still type the name.");
    });
  }
  // ---- voice: record a few seconds, send the clip to the one transcribe hook, put the words in the field (never applied) ----------------
  function endRecording() {                           // release the recorder, the timer and the microphone
    if (timer) { clearTimeout(timer); timer = null; }
    const r = rec; rec = null;
    if (r && r.state === "recording") { r.onstop = () => {}; try { r.stop(); } catch (e) { /* already stopped */ } }
    if (stream) { stopTracks(stream); stream = null; }
    const m = $("spellMic"); if (m) m.setAttribute("aria-pressed", "false");
  }
  function stopVoice() {                              // close, another open or Use this: end everything and drop any answer still on its way
    vid++; phase = ""; endRecording();
  }
  async function toggleVoice() {
    if (!cur || cur.checking || !micAllowed()) return;
    if (phase === "recording") { if (rec && rec.state === "recording") rec.stop(); return; }
    if (phase) return;                                // asking for the microphone, or reading a clip: a second tap does nothing
    const mine = ++vid, md = H.media(), R = H.Recorder();
    if (!voiceReady()) { say(RxState.voiceError({ kind: "no-recorder" }, "mic")); return; }
    phase = "starting";
    let s;
    try { s = await md.getUserMedia({ audio: true }); }
    catch (e) { if (vid === mine) { phase = ""; say(RxState.voiceError(e, "mic")); } return; }
    if (vid !== mine) { stopTracks(s); return; }      // closed while the browser asked: release it at once
    stream = s;
    const mime = ["audio/webm", "audio/mp4"].find((t) => typeof R.isTypeSupported === "function" && R.isTypeSupported(t)) || "", parts = [];
    let me;
    try { me = mime ? new R(stream, { mimeType: mime }) : new R(stream); }
    catch (e) { phase = ""; endRecording(); say(RxState.voiceError({ kind: "no-recorder" }, "mic")); return; }
    rec = me; me.ondataavailable = (ev) => { if (ev.data) parts.push(ev.data); };
    me.onstop = async () => {
      if (vid !== mine || rec !== me) return;
      const type = me.mimeType; endRecording(); phase = "reading";
      const blob = new Blob(parts, { type: type || "audio/webm" });
      if (!blob.size) { phase = ""; say(RxState.voiceError({ kind: "no-audio" }, "mic")); return; }
      say("Reading the name...", true);
      let text;
      try { text = await H.transcribe(blob); }
      catch (e) { if (vid === mine) { phase = ""; say(RxState.voiceError(e, "upload")); } return; }
      if (vid !== mine || !cur) return;               // closed, or another row opened: drop it
      phase = "";
      const name = RxState.cleanTyped(String(text || "").replace(/[.?!,;:\s]+$/, "")).slice(0, 60);
      if (!name) { say(RxState.voiceError({ kind: "no-speech" }, "upload")); return; }
      $("spellInput").value = name; $("spellInput").focus(); say('Heard "' + name + '". Check it, then press Use this.', true); typed();
    };
    try { me.start(); }
    catch (e) { phase = ""; endRecording(); say("Could not start recording. Type the name."); return; }
    phase = "recording"; $("spellMic").setAttribute("aria-pressed", "true"); say("Listening... tap Say it again to stop.", true);
    if (H.voiceMs > 0) timer = setTimeout(() => { if (rec === me && me.state === "recording") me.stop(); }, H.voiceMs);
  }
  function init(hooks) {                              // hooks: {dialog, working, recording, viewOnly, transcribe, media, Recorder, voiceMs}
    H = Object.assign({ voiceMs: 4000, searchMs: 350, viewOnly: () => false }, hooks);
    if (bound !== H.dialog) {                         // a second init() must not bind twice
      H.dialog.addEventListener("keydown", onKey); H.dialog.addEventListener("click", onClick);
      H.dialog.addEventListener("input", (e) => { if (e.target === $("spellInput")) typed(); });
      H.dialog.addEventListener("cancel", (e) => { e.preventDefault(); close(true); });     // the browser's own Esc
      bound = H.dialog;
    }
  }
  const closeFor = (rowid, refocus) => { if (isOpenFor(rowid)) close(refocus); };
  function setChecking(rowid, on) { if (isOpenFor(rowid)) { cur.checking = !!on; show(); } }
  function sync() {                                   // the page became busy or view-only (or free again) while the dialog is open
    if (!cur) return;
    const why = blockedWhy();
    if (why) { say(why, true); cur.blockedMsg = why; } else if (cur.blockedMsg) { cur.blockedMsg = ""; say(""); }
    if (why) { cancelSearch(); stopVoice(); }
    show();
  }
  return { init, open, close, closeFor, isOpenFor, setChecking, sync, tokenFor: (rowid) => (isOpenFor(rowid) ? cur.tok : 0), busy: () => !!rec,
    sweep: () => { if (cur && !cur.alive()) close(false); },                                   // the page calls it after a row is deleted
    say: (rowid, m, focus) => { if (isOpenFor(rowid)) { say(m); if (focus) $("spellInput").focus(); } } };
})();
