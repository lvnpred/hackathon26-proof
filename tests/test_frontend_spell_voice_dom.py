"""Plan I2-c: the modal's microphone: record a few seconds, the existing /api/transcribe route, fill the field, never apply."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from test_frontend_rxspell_dom import _run

FRONT = Path(__file__).resolve().parents[1] / "frontend"
OPEN = """const tr = mkRow("v1", "unknown-medicine", { name: "Citrizene" }); await openPanel(tr); const loads = posts.length;"""


def test_voice_fills_the_field_and_never_applies_it():
    r = _run(OPEN + """
      dclick(ids.spellMic); await tick(); const listening = [ids.spellMic.attrs["aria-pressed"], ids.spellInfo.textContent, SpellModal.busy()];
      dclick(ids.spellMic); await tick();                                       // stop: the clip goes to the transcribe hook
      const sent = [voice.length, voice[0].blob instanceof Blob, stream.stopped];
      voice[0].res("C e t i r i z i n e."); await tick();
      console.log(JSON.stringify({ listening, sent, field: ids.spellInput.value, msg: ids.spellInfo.textContent, err: ids.spellMsg.textContent,
        focus: document.activeElement === ids.spellInput, checks: posts.length - loads, row: cell(tr, "name").textContent, busy: SpellModal.busy() }));""")
    assert r["listening"] == ["true", "Listening... tap Say it again to stop.", True] and r["sent"] == [1, True, 1]
    assert (r["field"], r["msg"]) == ("Cetirizine", 'Heard "Cetirizine". Check it, then press Use this.')
    assert (r["focus"], r["checks"], r["row"], r["busy"], r["err"]) == (True, 0, "Citrizene", False, "")     # nothing sent to check-row, row unchanged


def test_each_voice_failure_is_one_sentence_and_the_field_is_untouched():
    r = _run(OPEN + """
      const out = [];
      const tryMic = async (setup, finish) => { ids.spellInput.value = "typed"; setup(); dclick(ids.spellMic); await tick();
        if (FakeRec.last && FakeRec.last.state === "recording") { dclick(ids.spellMic); await tick(); }
        if (finish) { finish(voice[voice.length - 1]); await tick(); }
        out.push([ids.spellMsg.textContent, ids.spellInput.value]); flags.mic = "ok"; flags.noRecorder = false; flags.audio = ["a1"]; FakeRec.last = null; };
      await tryMic(() => { flags.mic = "NotAllowedError"; });
      await tryMic(() => { flags.mic = "NotFoundError"; });
      await tryMic(() => { flags.noRecorder = true; });
      await tryMic(() => { flags.audio = []; });
      await tryMic(() => {}, (v) => v.res("  "));
      await tryMic(() => {}, (v) => { const e = new Error("boom"); e.status = 500; v.rej(e); });
      await tryMic(() => {}, (v) => v.rej({ aborted: true }));
      console.log(JSON.stringify(out));""")
    assert r == [["The microphone is blocked. Allow it in the browser, or type the name.", "typed"],
                 ["No microphone was found. Type the name.", "typed"],
                 ["Voice input is not supported in this browser. Type the name.", "typed"],
                 ["No sound was recorded. Try again, or type the name.", "typed"],
                 ["No name was heard. Try again, or type the name.", "typed"],
                 ["Could not read that. Try again or type the name.", "typed"],
                 ["Reading the name took too long. Type the name instead.", "typed"]]


def test_the_mic_is_off_for_view_only_while_working_and_while_dictation_records():
    r = _run(OPEN + """
      const out = [];
      for (const [k, v] of [["vo", true], ["working", true], ["recording", true]]) {
        if (k === "vo") globalThis.Authorship = { isViewOnly: () => true }; else flags[k] = v;
        SpellModal.setChecking("v1", false); dclick(ids.spellMic); await tick();
        out.push([k, ids.spellMic.disabled, gum.length]);
        globalThis.Authorship = undefined; flags.working = false; flags.recording = false;
      }
      console.log(JSON.stringify(out));""")
    assert r == [["vo", True, 0], ["working", True, 0], ["recording", True, 0]]


def test_a_late_transcript_after_close_or_another_row_is_dropped():
    r = _run(OPEN + """
      dclick(ids.spellMic); await tick(); dclick(ids.spellClose);                 // Close while recording: the mic is released
      const stopped = [FakeRec.last.state, stream.stopped, SpellModal.busy(), voice.length];
      await openPanel(tr); dclick(ids.spellMic); await tick(); dclick(ids.spellMic); await tick();   // a clip is sent, its answer pending
      dclick(ids.spellClose); const t2 = mkRow("v2", "unknown-medicine", { name: "Croissin" }); await openPanel(t2);
      voice[0].res("cetirizine"); await tick();
      console.log(JSON.stringify({ stopped, field: ids.spellInput.value, msg: said(), title: ids.spellTitle.textContent }));""")
    assert r == {"stopped": ["inactive", 1, False, 0], "field": "", "msg": "", "title": "Spell Croissin"}


# ---- added by the I2-c task 3-4 run ------------------------------------------------------------------------------------

def test_a_double_tap_never_starts_two_recordings_and_a_tap_while_reading_is_ignored():
    r = _run(OPEN + """
      dclick(ids.spellMic); dclick(ids.spellMic); await tick();                      // second tap while the permission prompt is open
      const started = [gum.length, FakeRec.last.state, SpellModal.busy()];
      dclick(ids.spellMic); await tick();                                            // stop
      const reading = [voice.length, FakeRec.last.state, SpellModal.busy(), stream.stopped];
      dclick(ids.spellMic); await tick();                                            // tap while the clip is being read
      const tapped = [gum.length, voice.length, ids.spellMic.attrs["aria-pressed"]];
      voice[0].res("Cetirizine"); await tick();
      dclick(ids.spellMic); await tick();                                            // now a new recording may start
      console.log(JSON.stringify({ started, reading, tapped, again: [gum.length, FakeRec.last.state], field: ids.spellInput.value }));""")
    assert r["started"] == [1, "recording", True] and r["reading"] == [1, "inactive", False, 1]
    assert r["tapped"] == [1, 1, "false"] and r["again"] == [2, "recording"] and r["field"] == "Cetirizine"


def test_the_clip_is_capped_by_a_timer_that_a_manual_stop_cancels():
    r = _run(OPEN + """
      const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
      const hooks = { dialog: dlg, working: () => flags.working, recording: () => flags.recording, viewOnly: () => false, voiceMs: 25,
        media: () => ({ getUserMedia: () => { gum.push(1); return Promise.resolve(stream); } }), Recorder: () => FakeRec, transcribe: (blob) => new Promise((res, rej) => voice.push({ blob, res, rej })) };
      SpellModal.init(hooks);                                                         // a second init must not bind the dialog twice
      dclick(ids.spellMic); await tick(); const on = FakeRec.last.state; await sleep(80);
      const auto = [FakeRec.last.state, voice.length, stream.stopped];
      voice[0].res("x"); await tick();
      dclick(ids.spellMic); await tick(); dclick(ids.spellMic); await tick(); await sleep(80);   // stopped by hand: the timer must not send a second clip
      console.log(JSON.stringify({ on, auto, manual: [voice.length, stream.stopped], keys: (dlg.handlers.keydown || []).length, clicks: (dlg.handlers.click || []).length }));""")
    assert r["on"] == "recording" and r["auto"] == ["inactive", 1, 1] and r["manual"] == [2, 2] and (r["keys"], r["clicks"]) == (1, 1)


def test_an_unsupported_browser_says_so_and_every_stream_is_released():
    r = _run(OPEN + """
      const out = [], granted = () => gum.length;
      const run = async (setup, finish) => { setup(); dclick(ids.spellMic); await tick();
        if (FakeRec.last && FakeRec.last.state === "recording") { dclick(ids.spellMic); await tick(); }
        if (finish) { finish(voice[voice.length - 1]); await tick(); }
        out.push(ids.spellMsg.textContent); flags.noRecorder = false; flags.audio = ["a1"]; flags.mic = "ok"; FakeRec.last = null; };
      await run(() => { flags.noRecorder = true; });                                  // no recorder: said at once, the microphone is never asked for
      await run(() => { flags.audio = []; });
      await run(() => {}, (v) => v.res(""));
      await run(() => {}, (v) => v.rej(new Error("x")));
      await run(() => {}, (v) => v.res("ok name"));
      const released = [granted(), stream.stopped];
      SpellModal.init({ dialog: dlg, working: () => false, recording: () => false, viewOnly: () => false, voiceMs: 0, media: () => undefined, Recorder: () => FakeRec, transcribe: () => Promise.reject(new Error("no")) });
      dclick(ids.spellMic); await tick(); const noMedia = [ids.spellMsg.textContent, gum.length];
      console.log(JSON.stringify({ released, noMedia, last: out[out.length - 1] }));""")
    assert r["released"] == [4, 4]                                                      # every granted stream was stopped (no permission is asked when there is no recorder)
    assert r["noMedia"] == ["Voice input is not supported in this browser. Type the name.", 4]


def test_the_transcript_is_trimmed_capped_and_stays_text_and_the_mic_waits_for_a_check():
    r = _run(OPEN + """
      const say = async (text) => { dclick(ids.spellMic); await tick(); dclick(ids.spellMic); await tick(); voice[voice.length - 1].res(text); await tick(); return ids.spellInput.value; };
      const out = [await say("  Cetirizine.  "), await say("Vitamin   D3?"), await say("a".repeat(90)).then((v) => v.length), await say("<img src=x onerror=1>")];
      const field = ids.spellInput.value; const html = ids.spellMsg.children.length;
      ids.spellInput.value = "Allopurinol"; dclick(ids.spellUse); await tick();                    // a check starts: the mic is off and ignores taps
      const g = gum.length; dclick(ids.spellMic); await tick();
      console.log(JSON.stringify({ out, field, html, mic: [ids.spellMic.disabled, gum.length - g], checks: posts.length - loads }));""")
    assert r["out"] == ["Cetirizine", "Vitamin D3", 60, "<img src=x onerror=1>"] and r["field"] == "<img src=x onerror=1>" and r["html"] == 0
    assert r["mic"] == [True, 0] and r["checks"] == 1                                    # only Use this reaches check-row


def test_a_late_voice_failure_after_close_never_writes_into_another_rows_modal():
    r = _run(OPEN + """
      dclick(ids.spellMic); await tick(); dclick(ids.spellMic); await tick();           // clip sent
      dclick(ids.spellClose); const t2 = mkRow("v3", "unknown-medicine", { name: "Croissin" }); await openPanel(t2);
      voice[0].rej(new Error("boom")); await tick();
      console.log(JSON.stringify({ msg: said(), mic: [ids.spellMic.attrs["aria-pressed"], ids.spellMic.disabled] }));""")
    assert r == {"msg": "", "mic": ["false", False]}


def test_the_permission_prompt_answered_after_close_releases_the_stream():
    r = _run(OPEN + """
      let grant; SpellModal.init({ dialog: dlg, working: () => false, recording: () => false, viewOnly: () => false, voiceMs: 0,
        media: () => ({ getUserMedia: () => new Promise((res) => { gum.push(1); grant = () => res(stream); }) }), Recorder: () => FakeRec, transcribe: () => Promise.reject(new Error("no")) });
      dclick(ids.spellMic); await tick(); dclick(ids.spellClose); grant(); await tick();
      console.log(JSON.stringify({ stopped: stream.stopped, busy: SpellModal.busy(), rec: FakeRec.last === undefined || FakeRec.last === null, msg: said() }));""")
    assert r == {"stopped": 1, "busy": False, "rec": True, "msg": ""}


def test_the_mic_button_is_labelled_44px_and_the_page_uses_the_one_transcribe_route():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    mic = html[html.index('id="spellMic"'):].split(">", 1)[0]
    assert 'aria-label="Say it: say the name"' in mic and 'aria-pressed="false"' in mic and 'type="button"' in mic and "rx-act" in mic
    css = re.sub(r"\s+", " ", (FRONT / "rx.css").read_text(encoding="utf-8"))
    assert re.search(r"#spellMic \{[^}]*min-width:44px", css) and '#spellMic[aria-pressed="true"]' in css
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    js = (FRONT / "spellmodal.js").read_text(encoding="utf-8")
    assert app.count('"/api/transcribe"') == 2 and "transcribe: transcribeName" in app and "SpellModal.busy()" in app.split('recBtn.addEventListener("click"')[1].split("});")[0]
    assert "H.transcribe(" in js and "getUserMedia({ audio: true })" in js and "audio/webm" in js and "audio/mp4" in js    # the dictation constraints and formats
    assert js.count("H.transcribe(") == 1 and "navigator" not in js and "window.MediaRecorder" not in js


def test_transcribe_name_posts_the_clip_to_the_existing_route_with_a_short_timeout():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    src = app[app.index("async function transcribeName"):]
    src = src[:src.index("\n}\n") + 3]
    script = """
      globalThis.FormData = class { constructor() { this.f = []; } append(k, v, n) { this.f.push([k, n]); } };
      const calls = []; let mode = "ok"; const timers = [];
      globalThis.setTimeout = (f, ms) => { timers.push(ms); return 1; }; globalThis.clearTimeout = () => { timers.push("cleared"); };
      globalThis.fetch = (url, o) => { calls.push([url, o.method, o.body.f, !!o.signal]); if (mode === "abort") { const e = new Error("a"); e.name = "AbortError"; return Promise.reject(e); }
        return Promise.resolve({ ok: mode === "ok", status: mode === "ok" ? 200 : 500, json: async () => (mode === "ok" ? { transcript: "  Cetirizine " } : { error: "stt down" }) }); };
      const safeJson = async (r) => { try { return await r.json(); } catch { return {}; } };
      """ + src + """
      (async () => {
        const out = { ok: await transcribeName("blob") };
        mode = "bad"; try { await transcribeName("blob"); } catch (e) { out.bad = [e.message, e.status]; }
        mode = "abort"; try { await transcribeName("blob"); } catch (e) { out.abort = [e.aborted, e.message]; }
        out.calls = calls; out.timers = timers; console.log(JSON.stringify(out));
      })();"""
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert r["ok"] == "Cetirizine" and r["bad"] == ["stt down", 500] and r["abort"] == [True, "timed out"]
    assert all(c == ["/api/transcribe", "POST", [["audio", "name.webm"]], True] for c in r["calls"]) and len(r["calls"]) == 3
    assert r["timers"].count(20000) == 3 and r["timers"].count("cleared") == 3          # a 20-second ceiling, always cleared


def test_use_this_while_recording_or_reading_drops_the_clip_and_the_late_words():
    r = _run(OPEN + """
      dclick(ids.spellMic); await tick();                                            // recording
      ids.spellInput.value = "Allopurinol"; dclick(ids.spellUse); await tick();
      const rec = [FakeRec.last.state, stream.stopped, voice.length, posts.length - loads, SpellModal.busy()];
      posts.shift().rej(new Error("x")); await tick();                               // the check fails: the modal stays, the field keeps what was typed
      dclick(ids.spellMic); await tick(); dclick(ids.spellMic); await tick();        // a clip is being read ...
      dclick(ids.spellUse); await tick();                                            // ... and Use this is pressed
      voice[0].res("Cetirizine"); await tick();
      console.log(JSON.stringify({ rec, field: ids.spellInput.value, sent: posts.length }));""")
    assert r["rec"] == ["inactive", 1, 0, 1, False]
    assert r["field"] == "Allopurinol" and r["sent"] == 1                         # the late words never replace the typed name; the second Use this sent its own check


def test_a_name_heard_is_searched_like_a_typed_one_but_never_applied():
    r = _run(OPEN + """
      dclick(ids.spellMic); await tick(); dclick(ids.spellMic); await tick(); voice[0].res("Cetirizine"); await tick();
      await sleep(80);
      console.log(JSON.stringify({ search: [posts.length - loads, posts.length > loads && posts[loads].body.row.name], row: cell(tr, "name").textContent, conf: confirmed.has("v1") }));""")
    assert r == {"search": [1, "Cetirizine"], "row": "Citrizene", "conf": False}
