"""Plan I2-c fix round B, D, E, G: screen-reader text, busy and unsupported states, a recorder that cannot start, focus after a late answer."""
import re
from pathlib import Path

from test_frontend_rxspell_dom import _run

FRONT = Path(__file__).resolve().parents[1] / "frontend"
OPEN = """const tr = mkRow("z1", "unknown-medicine", { name: "Zyloprim" }); await openPanel(tr);"""


def test_a_list_item_is_named_by_its_visible_name_and_described_by_the_generic_and_the_warning():
    r = _run("""
      const tr = mkRow("a1", "lookalike-check", { name: "Prednisone" });
      click(spellBtn(tr)); await reply({}, [], [{ name: "Prednisolone", generic: "Prednisolone", reason: "lookalike" }, { name: "Crocin", generic: "Paracetamol", reason: "sounds" }, { name: "Plain", generic: "", reason: "" }], 3);
      const descr = (b) => (b.attrs["aria-describedby"] || "").split(" ").filter(Boolean).map((id) => { const n = b.children.find((c) => c.id === id); return n ? n.textContent : null; });
      const [look, croc, plain] = ids.spellList.children;
      const idsAll = ids.spellList.children.map((b) => b.attrs["aria-describedby"]).filter(Boolean).join(" ").split(" ");
      const t2 = mkRow("a2", "unknown-medicine", { name: "Croissin" }, { did_you_mean: "Crocin", did_you_mean_generic: "Paracetamol" });
      const dym = t2.querySelector('[data-action="dym"]');
      console.log(JSON.stringify({ labels: [look.attrs["aria-label"], croc.attrs["aria-label"], plain.attrs["aria-label"]], look: descr(look), croc: descr(croc), plain: plain.attrs["aria-describedby"] || null,
        unique: new Set(idsAll).size === idsAll.length, dym: [dym.attrs["aria-label"], descr(dym)] }));""")
    assert r["labels"] == ["Prednisolone: use for this row", "Crocin: use for this row", "Plain: use for this row"]      # starts with the visible name
    assert r["look"] == ["looks alike: a different medicine"] and r["croc"] == ["generic: Paracetamol", "sounds like"] and r["plain"] is None
    assert r["unique"] is True and r["dym"] == ["Did you mean Crocin? Use it for this row", ["generic: Paracetamol"]]


def test_the_mic_name_contains_its_visible_text_and_info_goes_to_a_status_while_errors_go_to_an_alert():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    mic = html[html.index('<button id="spellMic"'):].split("</button>", 1)[0]
    label, text = re.search(r'aria-label="([^"]*)"', mic).group(1), mic.split(">", 1)[1]
    assert text and text.lower() in label.lower() and label.lower().startswith(text.lower())          # WCAG 2.5.3: label in name
    r = _run(OPEN + """
      dclick(ids.spellMic); await tick(); const listening = [ids.spellInfo.textContent, ids.spellMsg.textContent];
      dclick(ids.spellMic); await tick(); const reading = [ids.spellInfo.textContent, ids.spellMsg.textContent];
      voice[0].res("Cetirizine"); await tick(); const heard = [ids.spellInfo.textContent, ids.spellMsg.textContent];
      flags.mic = "NotAllowedError"; dclick(ids.spellMic); await tick(); const denied = [ids.spellInfo.textContent, ids.spellMsg.textContent];
      console.log(JSON.stringify({ listening, reading, heard, denied }));""")
    assert r["listening"] == ["Listening... tap Say it again to stop.", ""] and r["reading"] == ["Reading the name...", ""]
    assert r["heard"] == ['Heard "Cetirizine". Check it, then press Use this.', ""]
    assert r["denied"] == ["", "The microphone is blocked. Allow it in the browser, or type the name."]    # one region at a time


def test_working_or_view_only_during_the_dialog_switches_the_mic_and_use_this_off_at_once_and_back():
    r = _run(OPEN + """
      const st = () => [ids.spellMic.disabled, ids.spellUse.disabled, ids.spellInfo.textContent];
      const base = st();
      flags.working = true; SpellModal.sync(); const working = st();
      flags.working = false; SpellModal.sync(); const back = st();
      globalThis.Authorship = { isViewOnly: () => true }; SpellModal.sync(); const vo = st();
      globalThis.Authorship = undefined; SpellModal.sync();
      console.log(JSON.stringify({ base, working, back, vo, after: st() }));""")
    assert r["base"] == [False, False, ""]
    assert r["working"] == [True, True, "Wait for the page to finish."] and r["back"] == [False, False, ""]
    assert r["vo"] == [True, True, "This prescription is view only."] and r["after"] == [False, False, ""]


def test_an_unsupported_browser_shows_a_disabled_mic_with_its_reason_at_once():
    r = _run("""
      flags.noRecorder = true;
      const tr = mkRow("u1", "unknown-medicine", { name: "Zyloprim" }); await openPanel(tr);
      const off = [ids.spellMic.disabled, ids.spellInfo.textContent, ids.spellMic.title];
      dclick(ids.spellMic); await tick();
      console.log(JSON.stringify({ off, gum: gum.length, use: ids.spellUse.disabled }));""")
    assert r["off"] == [True, "Voice input is not available in this browser.", "Voice input is not available in this browser."]
    assert r["gum"] == 0 and r["use"] is False


def test_spell_while_the_page_is_working_says_why_instead_of_doing_nothing():
    r = _run("""
      const tr = mkRow("w1", "unknown-medicine", { name: "Zyloprim" });
      flags.working = true; click(spellBtn(tr)); flags.working = false;
      console.log(JSON.stringify({ open: panels(), posts: posts.length, notes }));""")
    assert r == {"open": 0, "posts": 0, "notes": ["Wait for the page to finish."]}


def test_a_recorder_that_cannot_start_releases_the_microphone_and_says_so():
    r = _run(OPEN + """
      flags.startThrows = true; dclick(ids.spellMic); await tick();
      const failed = [said(), stream.stopped, SpellModal.busy(), ids.spellMic.attrs["aria-pressed"], FakeRec.last && FakeRec.last.state];
      flags.startThrows = false; dclick(ids.spellMic); await tick();                    // the phase was reset: a new try works
      console.log(JSON.stringify({ failed, again: [gum.length, FakeRec.last.state, ids.spellInfo.textContent] }));""")
    assert r["failed"] == ["Could not start recording. Type the name.", 1, False, "false", "inactive"]
    assert r["again"] == [2, "recording", "Listening... tap Say it again to stop."]


def test_a_late_use_this_answer_moves_focus_only_when_the_dialog_that_started_it_is_still_open_or_focus_is_lost():
    r = _run("""
      const out = [];
      const other = new El("button"); ROOT_EL.appendChild(other);
      const run = async (id, how) => {
        const tr = mkRow(id, "lookalike-check", { name: "Prednisone" }); await openPanel(tr); await useTyped("Prednisolone");
        if (how === "esc") { dkey("Escape"); other.focus(); }                      // the doctor left and went on to something else
        if (how === "esc-lost") { dkey("Escape"); document.activeElement = null; }  // closed, focus fell to nowhere
        await reply({ name: "Prednisolone", status: "verified", lexicon_match: "Prednisolone" });
        out.push([how, document.activeElement === tr.querySelector(".rx-state"), document.activeElement === other]);
      };
      await run("r1", "stay"); await run("r2", "esc"); await run("r3", "esc-lost");
      console.log(JSON.stringify(out));""")
    assert r == [["stay", True, False], ["esc", False, True], ["esc-lost", True, False]]


def test_becoming_busy_while_recording_stops_the_clip_and_releases_the_microphone():
    r = _run(OPEN + """
      dclick(ids.spellMic); await tick();
      flags.working = true; SpellModal.sync(); flags.working = false;
      console.log(JSON.stringify({ rec: FakeRec.last.state, busy: SpellModal.busy(), stopped: stream.stopped, pressed: ids.spellMic.attrs["aria-pressed"], sent: voice.length }));""")
    assert r == {"rec": "inactive", "busy": False, "stopped": 1, "pressed": "false", "sent": 0}


def test_the_page_tells_the_dialog_when_it_becomes_busy_and_links_a_search_to_its_request():
    import json, shutil, subprocess
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "SpellModal.sync()" in app.split("function setWorking(on, msg) {")[1].split("\n}\n")[0]
    assert "notify: setStatus" in app
    node = shutil.which("node")
    if node is None:
        import pytest
        pytest.skip("node is not installed")
    src = app[app.index("async function postJson"):]
    src = src[:src.index("\n}\n") + 3]
    script = """
      const seen = []; globalThis.fetch = (url, o) => { seen.push(o.signal); return new Promise((res, rej) => o.signal.addEventListener("abort", () => rej(Object.assign(new Error("a"), { name: "AbortError" })))); };
      const safeJson = async () => ({});
      """ + src + """
      (async () => {
        const outer = new AbortController(); const p = postJson("/x", {}, 60000, outer.signal).catch((e) => e);
        outer.abort(); const e = await p;
        console.log(JSON.stringify({ aborted: seen[0].aborted, err: [e.aborted, e.message] }));
        process.exit(0);
      })();"""
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == {"aborted": True, "err": [True, "timed out"]}                      # the caller's abort reaches fetch
