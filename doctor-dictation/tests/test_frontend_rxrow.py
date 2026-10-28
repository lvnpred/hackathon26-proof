"""Medication row UI (I1-e). The rules in frontend/rxstate.js run under node (no DOM); the wiring is checked as text,
like the other tests/test_frontend_*.py files. DOM behaviour is the manual Playwright checklist in the plan."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from doctor_dictation.core.safety import screen_unverified

FRONT = Path(__file__).resolve().parents[1] / "frontend"
STATUSES = ["verified", "unverified-name", "unknown-medicine", "unverified-strength", "lookalike-check", "dose-check", "", "future-status", None,
            ["verified"], 5, " verified ", "VERIFIED", "verified\n", {}, True]

def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")

def _node(expr):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = "globalThis.window = globalThis; require(process.argv[1]); console.log(JSON.stringify(" + expr + "))"
    out = subprocess.run([node, "-e", script, str(FRONT / "rxstate.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)

def _state(status, source="", confirmed=False):
    return f"RxState.rowState({{status:{json.dumps(status)},source:{json.dumps(source)}}},{{confirmed:{json.dumps(confirmed)}}})"

def test_every_status_maps_to_the_contract_state():
    expect = {("verified", "lexicon", False): "ok", ("verified", "", False): "ok", ("verified", "clinic", False): "known",
              ("unverified-strength", "", False): "dose", ("dose-check", "", False): "dose", ("unknown-medicine", "", False): "confirm",
              ("unverified-name", "", False): "confirm", ("lookalike-check", "", False): "confirm",
              ("verified", "clinic", True): "you", ("unknown-medicine", "", True): "you", ("dose-check", "", True): "you"}
    got = _node("[" + ",".join(_state(*k) + ".state" for k in expect) + "]")
    assert dict(zip(expect, got)) == expect

def test_an_unknown_future_status_or_a_missing_one_is_a_safe_confirm_never_ok():
    got = _node('[{status:"brand-new-status"},{status:""},{},{status:null}].map((r) => RxState.rowState(r, {}))')
    assert [g["state"] for g in got] == ["confirm"] * 4 and all(g["needsYou"] and g["canConfirm"] for g in got)
    assert got[0]["reason"] == "This row needs a check (status: brand-new-status)." and got[1]["reason"].startswith("You changed this row")

def test_needs_you_agrees_with_the_servers_save_gate_for_every_status():
    keys = [(s, c) for s in STATUSES for c in (False, True)]
    ui = _node("[" + ",".join(_state(s, "", c) + ".needsYou" for s, c in keys) + "]")
    server = [bool(screen_unverified({"rx": [{"name": "x", "status": s}]}, [0] if c else [])) for s, c in keys]
    assert ui == server                       # a UI block is a server block; a UI-allowed save passes the server gate

def test_reasons_are_plain_words_taken_from_the_row_fields():
    r = _node("""[
      RxState.rowState({status:"lookalike-check",heard:"prednisone",lookalike:"Prednisolone"},{}).reason,
      RxState.rowState({status:"unknown-medicine",heard:"zyloprim",name:"Zyloprim"},{}).reason,
      RxState.rowState({status:"unverified-name",heard:"amlo dipine"},{}).reason,
      RxState.rowState({status:"dose-check",dose_note:"3000 mg a day; usual adult maximum 2000 mg"},{}).reason,
      RxState.rowState({status:"unverified-strength",strength:"15 mg"},{strength:"15 mg"}).reason,
      RxState.rowState({status:"unverified-strength",strength_options:["5 mg"]},{strength:""}).reason,
      RxState.rowState({status:"verified"},{confirmed:true,how:"chip",strength:"10 mg"}).reason]""")
    assert r[0] == 'Heard "prednisone". It looks like Prednisolone. They are different medicines.'
    assert r[1] == '"zyloprim" is not in the medicine list.' and r[2] == 'Heard "amlo dipine". The name was not clearly dictated.'
    assert r[3] == "3000 mg a day; usual adult maximum 2000 mg" and r[4] == "Strength 15 mg is not one this medicine usually comes in."
    assert r[5] == "No strength was dictated. Tap one below." and r[6] == "You chose the strength 10 mg."

def test_chips_put_the_usual_strength_first_drop_duplicates_and_only_show_on_dose_rows():
    row = '{status:"unverified-strength",strength_options:["2.5 mg","5 mg","10 mg","5 MG"],usual_strength:"5 mg"}'
    chips, verified, confirm = _node(f'[RxState.rowState({row},{{}}).chips, RxState.rowState({{status:"verified",strength_options:["5 mg"]}},{{}}).chips, RxState.rowState({{status:"unknown-medicine",strength_options:["5 mg"]}},{{}}).chips]')
    assert chips == [{"label": "5 mg", "usual": True}, {"label": "2.5 mg", "usual": False}, {"label": "10 mg", "usual": False}]
    assert verified == [] and confirm == []
    assert _node('RxState.rowState({status:"unverified-strength",strength_options:["5 mg"],usual_strength:"10 mg"},{}).chips') == [{"label": "5 mg", "usual": False}]

def test_a_hand_edit_drops_stale_reasons_and_a_name_edit_drops_the_old_drugs_data():
    name, dose = _node('[RxState.afterEdit({heard:"x",lookalike:"y",dose_note:"z",generic:"G",source:"clinic",usual_strength:"5 mg",strength_options:["5 mg"]}, "name"), RxState.afterEdit({generic:"G",heard:"x",strength_options:["5 mg"]}, "dose")]')
    assert name == {"heard": "", "lookalike": "", "dose_note": "", "generic": "", "source": "", "usual_strength": "", "strength_options": [], "did_you_mean": "", "did_you_mean_generic": "", "schedule": "", "generic_source": "", "combo_base": "", "generic_suggestion": "", "generic_suggestion_unknown": [], "generic_pending": False, "generic_listed": "", "remember_generic": False, "spelled_heard": "", "typed_heard": "x"}   # I2-a: a name edit clears the suggestion too; I2-d: and the schedule badge
    assert dose["generic"] == "G" and dose["heard"] == "" and dose["strength_options"] == ["5 mg"]

def test_summary_words():
    a, b, c = _node("[RxState.summary({total:6,needs:2,checking:0}), RxState.summary({total:6,needs:0,checking:0}), RxState.summary({total:1,needs:1,checking:0})]")
    assert a == {"title": "6 medicines", "ready": "4 ready", "needs": "2 need you", "saveLabel": "Resolve 2 to save", "saveDisabled": True}
    assert b["saveLabel"] == "Save prescription" and b["saveDisabled"] is False and c["title"] == "1 medicine" and c["needs"] == "1 needs you"

def test_odd_statuses_are_unreadable_confirms_with_a_safe_reason():
    odd = [["verified"], 5, {}, True, " verified ", "VERIFIED", "verified\n"]
    got = _node("[" + ",".join(_state(s) + ".state" for s in odd) + "]")
    assert got == ["confirm"] * len(odd)
    reasons = _node("[" + ",".join(_state(s) + ".reason" for s in odd[:4]) + "]")
    assert reasons == ["This row needs a check (status: unreadable)."] * 4
    assert _node(_state("verified", "Clinic") + ".state") == "ok" and _node(_state("verified", ["clinic"]) + ".state") == "ok"

def test_non_strings_never_render_as_object_text_and_numbers_stringify():
    r = _node("""[
      RxState.rowState({status:"unknown-medicine",heard:{},name:{}},{}).reason,
      RxState.rowState({status:"unverified-strength",strength:{}},{}).reason,
      RxState.rowState({status:"unverified-strength",strength:5},{}).reason,
      RxState.rowState({status:"unverified-strength",strength_options:[{},["x"],5,"10 mg",true]},{}).chips,
      RxState.metaOf({heard:{},generic:["a"],dose_note:5,strength_options:[{},7]})]""")
    assert r[0] == "This medicine is not in the medicine list." and r[1] == "No strength was dictated."
    assert r[2] == "Strength 5 is not one this medicine usually comes in."
    assert r[3] == [{"label": "5", "usual": False}, {"label": "10 mg", "usual": False}]
    assert r[4]["heard"] == "" and r[4]["generic"] == "" and r[4]["dose_note"] == "5" and r[4]["strength_options"] == ["7"]
    assert "[object" not in json.dumps(r)

def test_chip_confirmation_without_a_strength_and_unknown_medicine_without_a_name():
    r = _node("""[
      RxState.rowState({status:"verified"},{confirmed:true,how:"chip"}).reason,
      RxState.rowState({status:"verified",dose_note:"too high"},{confirmed:true,how:"chip",strength:""}).reason,
      RxState.rowState({status:"unknown-medicine",name:"Zyloprim"},{}).reason]""")
    assert r == ["You chose a strength.", "You chose a strength. Note: too high", '"Zyloprim" is not in the medicine list.']

def test_after_edit_for_every_column():
    meta = '{heard:"x",lookalike:"y",dose_note:"z",generic:"G",source:"clinic",usual_strength:"5 mg",strength_options:["5 mg"]}'
    cols = ["strength", "dose", "timing", "duration", "instructions", "form", "", None]
    got = _node("[" + ",".join(f"RxState.afterEdit({meta},{json.dumps(c)})" for c in cols) + ",RxState.afterEdit(undefined,\"name\"),RxState.afterEdit(" + meta + ")]")
    for m in got[:len(cols)] + [got[-1]]:
        assert (m["heard"], m["lookalike"], m["dose_note"]) == ("", "", "")
        assert m["generic"] == "G" and m["source"] == "clinic" and m["usual_strength"] == "5 mg" and m["strength_options"] == ["5 mg"]
    assert got[len(cols)]["heard"] == "" and got[len(cols)]["dose_note"] == ""

def test_summary_edge_inputs_never_show_negative_or_impossible_numbers():
    a, b, c, d = _node("[RxState.summary(), RxState.summary({total:2,needs:5,checking:0}), RxState.summary({total:-3,needs:-1,checking:-2}), RxState.summary({total:'4',needs:2.9,checking:'x'})]")
    assert a == {"title": "0 medicines", "ready": "0 ready", "needs": "0 need you", "saveLabel": "Save prescription", "saveDisabled": False}
    assert b["ready"] == "0 ready" and b["needs"] == "2 need you" and b["saveLabel"] == "Resolve 2 to save"
    assert c == a
    assert d["title"] == "4 medicines" and d["ready"] == "2 ready" and d["needs"] == "2 need you" and d["saveDisabled"] is True


def test_the_new_scripts_parse_and_build_dom_without_innerhtml():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    for name in ("rxstate.js", "rxview.js"):
        assert subprocess.run([node, "--check", str(FRONT / name)], capture_output=True, text=True).returncode == 0, name
        assert "innerHTML" not in _read(name) and "insertAdjacentHTML" not in _read(name)

def test_everything_new_is_screen_only_and_the_print_rules_are_untouched():
    css, base, js, page = _read("rx.css"), _read("styles.css"), _read("rxview.js"), _read("index.html")
    heads = re.findall(r"<thead>\s*<tr>(.*?)</tr>\s*</thead>", page, re.S)
    rx_head = [h for h in heads if "<th>#</th>" in h and "<th>Medicine</th>" in h]
    assert len(rx_head) == 1
    cells = re.findall(r"<th[^>]*>(.*?)</th>", rx_head[0], re.S)
    assert cells[-2:] == ["Check", ""]                                   # Check is second-to-last, the delete column is last
    blocks = re.findall(r"@media\s+print\s*\{(.*?)\}\s*\}?", css, re.S)
    assert any(re.search(r"td\.check\s*,\s*table\.rx\s+th:nth-last-child\(2\)\s*\{\s*display\s*:\s*none\s*!important", b) for b in blocks)
    assert "rx-print-sym" not in js and "printSymbol" not in _read("rxstate.js")
    for cls in ('"rx-extra rx-gen-tag no-print"', '"rx-extra rx-chips no-print"', '"rx-state no-print"'):
        assert cls in js, cls
    assert re.search(r"\.no-print\b[^{]*\{\s*display\s*:\s*none\s*!important", base)
    assert ".rx-act { min-height:44px;" in css and "#sheet.view-only .rx-act" in css and "#sheet.view-only .rx-chips" in css
    assert js.count("Authorship.isViewOnly()") >= 2                  # a colleague's prescription: no chip taps, Save stays off


def test_ok_reason_does_not_claim_a_strength_match_that_was_never_checked():
    r = _node("""[
      RxState.rowState({status:"verified",strength_options:["5 mg"]},{strength:""}).reason,
      RxState.rowState({status:"verified",strength:"  "},{}).reason,
      RxState.rowState({status:"verified",strength:"5 mg"},{}).reason,
      RxState.rowState({status:"verified",strength:"5 mg",strength_options:[" "]},{}).reason,
      RxState.rowState({status:"verified",strength:"5 mg",strength_options:["5 mg"]},{}).reason]""")
    assert r == ["Name matches the medicine list. No strength was given."] * 2 + ["Name matches the medicine list."] * 2 + ["Name and strength match the medicine list."]


def test_a_chip_on_a_dose_check_row_keeps_it_open_and_a_listed_strength_reads_as_one():
    r = _node("""[
      RxState.rowState({status:"dose-check",dose_note:""},{how:"chip-open",strength:"500 mg"}),
      RxState.rowState({status:"unverified-strength",strength_options:["5 mg","10 mg"]},{strength:" 10 MG "}).reason,
      RxState.rowState({status:"unverified-strength",strength_options:["5 mg"]},{strength:"10 mg"}).reason,
      RxState.rowState({status:"dose-check",dose_note:"too high"},{strength:"500 mg"}).reason]""")
    assert r[0]["state"] == "dose" and r[0]["needsYou"] and r[0]["canConfirm"] and r[0]["reason"] == "You changed the strength to 500 mg. Check the dose again."
    assert r[1] == "10 MG is one of its strengths. Confirm it or tap another."
    assert r[2] == "Strength 10 mg is not one this medicine usually comes in. Tap one below." and r[3] == "too high"


def test_chip_dedupe_trims_and_odd_numbers_and_empty_calls_are_safe():
    chips, none, empty, summ, st = _node("""[
      RxState.chipsFor({strength_options:["5 mg"," 5 mg","5 mg ","  "],usual_strength:""}),
      RxState.chipsFor(), RxState.chipsFor(null),
      RxState.summary({total:NaN,needs:Infinity,checking:-Infinity}),
      RxState.rowState({status:"unverified-strength",strength:NaN,heard:Infinity},{strength:Infinity}).reason]""")[0:5]
    assert [c["label"] for c in chips] == ["5 mg"] and none == [] == empty
    assert summ["title"] == "0 medicines" and summ["needs"] == "0 need you" and "NaN" not in st and "Infinity" not in st
    assert st == "No strength was dictated."
    assert _node('RxState.metaOf({strength_options:[" 5 mg ","  "]}).strength_options') == ["5 mg"]


def test_the_view_hardening_is_present():
    js, css = _read("rxview.js"), _read("rx.css")
    assert "b.disabled = " in js and "chip-open" in js and "activeElement" in js
    assert "var(--accent)" in css.split(".rx-state:focus-visible")[1].split("\n")[0] and "--rx-focus" not in css
    assert re.search(r"\.rx-act\.mini[^{]*\{[^}]*margin-left:\s*0", css)


def test_the_page_loads_the_new_files_before_app_js_and_holds_save_in_the_bar():
    html = _read("index.html")
    pos = [html.index(s) for s in ("rxstate.js?v=", "rxview.js?v=", "app.js?v=")]
    assert pos == sorted(pos) and re.search(r'href="rx\.css\?v=\d+"', html)
    bar = html[html.index('id="rxBar"'):html.index('id="sheet"')]
    assert 'id="saveBtn"' in bar and 'id="printBtn"' in bar and 'aria-describedby="rxNeeds"' in bar and 'id="rxNeeds" class="rx-count" data-state="dose" role="status"' in bar
    assert html.count('id="saveBtn"') == 1 and "confirmAllBtn" not in html and "Confirm all" not in html
    assert int(re.search(r"app\.js\?v=(\d+)", html).group(1)) >= 27

def test_app_js_edits_are_hooks_and_the_save_request_still_carries_confirmed_rows():
    app = _read("app.js")
    for token in ("RxView.init({", "RxView.attach(tr, r);", "RxView.onEdit(tr, e.target);", "Object.assign(rec, RxView.meta(tr))", "function renderCheck(tr) { RxView.renderRow(tr); }",
                  "if (state.confirmed.has(k.rowid)) confirmed_rows.push(i);", "      confirmed_rows,\n"):
        assert token in app, token
    assert "PILL" not in app and "confirmAllBtn" not in app and "statusText(" not in app
    assert "RxView.needsYou(tr)" in app.split("function openRows()")[1].split("function updateGrounding()")[0]
    body = _strip_comments(app).split("function setWorking(")[1].split("\n}\n")[0]          # a commented-out sync must fail this
    assert body.index("RxView.sync()") < body.index("Authorship.enforce()") and body.rstrip().splitlines()[-1].count("Authorship.enforce()") == 1


def test_confirm_clicks_are_ignored_while_working_or_view_only_and_the_block_panel_follows_chip_taps():
    app = _read("app.js")
    handler = app.split("// ---- confirm interactions")[1].split("function refreshBlockPanel()")[0]
    guard = "if (state.working || (window.Authorship && Authorship.isViewOnly())) return;"
    assert guard in handler and handler.index('closest(\'[data-action="confirm"]\')') < handler.index(guard) < handler.index("state.confirmed.add(rowid)")
    assert "changed: () => { markDirty(); updateGrounding(); if (!blockPanel.hidden) refreshBlockPanel(); }," in app


def test_the_rx_header_marks_the_check_column_and_the_print_rule_hides_it_by_class_as_well():
    html, css = _read("index.html"), _read("rx.css")
    rx_head = re.findall(r"<thead>(.*?)</thead>", html, re.S)[1] if len(re.findall(r"<thead>", html)) > 1 else re.findall(r"<thead>(.*?)</thead>", html, re.S)[0]
    ths = re.findall(r"<th([^>]*)>(.*?)</th>", rx_head, re.S)
    assert ths[-2] == (' class="check"', "Check") and ths[-1][1] == ""
    assert "table.rx th.check" in css and "table.rx th:nth-last-child(2)" in css       # the robust selector and the positional one


def _view_node(expr):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = ("globalThis.window = globalThis; require(process.argv[1]); require(process.argv[2]); console.log(JSON.stringify(" + expr + "))")
    out = subprocess.run([node, "-e", script, str(FRONT / "rxstate.js"), str(FRONT / "rxview.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_rxview_wire_returns_only_heard_and_lookalike_as_strings():
    r = _view_node("""(() => {
      const a = {}, b = {}, c = {}, d = {};
      RxView.attach(a, {heard: "amlo dipine", lookalike: "Check vs amiloride", generic: "g", how: "chip", dose_note: "n", strength_options: ["5 mg"], source: "formulary"});
      RxView.attach(b, {heard: 5, lookalike: null});
      RxView.attach(c, null);
      d._rx = {meta: undefined};
      return [RxView.wire(a), RxView.wire(b), RxView.wire(c), RxView.wire(d)];
    })()""")
    assert r[0] == {"heard": "amlo dipine", "lookalike": "Check vs amiloride"}
    assert list(r[0]) == ["heard", "lookalike"] and all(list(x) == ["heard", "lookalike"] for x in r)
    assert r[1] == {"heard": "5", "lookalike": ""}                      # metaOf stringifies numbers, null is empty
    assert r[2] == r[3] == {"heard": "", "lookalike": ""}


def test_read_rx_sends_heard_and_lookalike_from_the_row_meta_and_never_how():
    app = _read("app.js")
    read_rx = app.split("function readRx()")[1].split("kept.push(")[0]
    assert "Object.assign(rec, RxView.wire(tr));" in read_rx
    assert "RxView.meta(tr)" not in read_rx and "how" not in read_rx.replace("show", "")


# ---- final-review fixes: node harness with a tiny fake DOM, so RxView.init/sync/reasonFor run for real ----
_FAKE_DOM = """
function node() { return { children: [], textContent: "", hidden: false, dataset: {}, lastChild: null,
  append(...k) { k.forEach((c) => this.appendChild(c)); }, appendChild(c) { this.children.push(c); this.lastChild = c; return c; },
  setAttribute() {}, addEventListener() {}, querySelector() { return null; } }; }
const els = {}; ["rxBar", "rxTitle", "rxReady", "rxNeeds"].forEach((id) => { els[id] = node(); });
globalThis.document = { getElementById: (id) => els[id], createElement: () => node(), createElementNS: () => node(),
  querySelector: () => ({ offsetHeight: 104 }), documentElement: { style: { v: {}, setProperty(k, v) { this.v[k] = v; } } } };
function row(id, status, cols, meta) {
  const tr = { dataset: { rowid: id, status: status, index: id }, querySelector(sel) { const m = /data-col="(\\w+)"/.exec(sel); return m ? { textContent: cols[m[1]] || "" } : null; } };
  RxView.attach(tr, Object.assign({ status: status }, meta || {})); return tr;
}
function setup(rows, o) {
  o = o || {}; const confirmed = new Set(o.confirmed || []);
  globalThis.Authorship = o.viewOnly ? { isViewOnly: () => true } : undefined;
  const saveBtn = { textContent: "", disabled: false };
  RxView.init({ body: { addEventListener() {}, querySelectorAll: () => rows }, saveBtn, confirmed: () => confirmed, working: () => !!o.working, changed() {}, hasSheet: () => true });
  return { saveBtn, confirmed };
}
"""


def _dom(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = "globalThis.window = globalThis;" + _FAKE_DOM + "require(process.argv[1]); require(process.argv[2]); require(process.argv[3]);" + body
    out = subprocess.run([node, "-e", script, str(FRONT / "rxstate.js"), str(FRONT / "rxview.js"), str(FRONT / "spellmodal.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _strip_comments(js):
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|(?<![:\"'\\])//[^\n]*", "", js)


def test_the_409_panel_reason_comes_from_the_row_not_just_the_status():
    r = _dom("""
      const a = row("1", "unverified-strength", { name: "Amlodipine", strength: "15 mg" }, { strength_options: ["5 mg", "10 mg"] });
      const b = row("2", "lookalike-check", { name: "Prednisone", strength: "5 mg" }, { heard: "prednisolone", lookalike: "prednisolone" });
      const c = row("3", "dose-check", { name: "Paracetamol", strength: "1000 mg" }, { dose_note: "4000 mg a day; usual max 3000 mg" });
      const d = row("4", null, { name: "Odd" });
      const e = row("5", "verified", {});
      setup([a, b, c, d, e]);
      console.log(JSON.stringify([a, b, c, d, e].map(RxView.reasonFor)));""")
    assert "15 mg" in r[0] and "prednisolone" in r[1].lower() and "4000 mg a day" in r[2] and r[3] == "You changed this row. Confirm it before saving."
    assert r[4] == "Empty row: removed when you save"
    app = _strip_comments(_read("app.js"))
    panel = app.split("function refreshBlockPanel()")[1].split("function hideBlockPanel")[0]
    assert "RxView.blockReason(rowTr, b)" in panel and "RxState.rowState({ status: b.status }, {}).reason" in panel and "rowTr ?" in panel
    assert "reasonFor" in _read("rxview.js").split("return { init")[1]


def test_save_follows_the_rows_working_and_view_only_and_blank_rows_do_not_count():
    r = _dom("""
      const need = row("1", "unverified-name", { name: "Zolpid" }), ok = row("2", "verified", { name: "Aspirin" }), blank = row("3", "", {});
      const out = {};
      let s = setup([need, ok, blank]); RxView.sync(); out.needs = [s.saveBtn.disabled, s.saveBtn.textContent, els.rxNeeds.lastChild.textContent, els.rxTitle.textContent];
      s = setup([ok, blank]); RxView.sync(); out.ready = [s.saveBtn.disabled, s.saveBtn.textContent, els.rxTitle.textContent];
      s = setup([need, ok], { confirmed: ["1"] }); RxView.sync(); out.confirmed = [s.saveBtn.disabled, s.saveBtn.textContent];
      s = setup([ok], { working: true }); RxView.sync(); out.working = s.saveBtn.disabled;
      s = setup([need], { viewOnly: true }); RxView.sync(); out.view = [s.saveBtn.disabled, s.saveBtn.textContent];
      s = setup([ok], { viewOnly: true }); RxView.sync(); out.viewOk = [s.saveBtn.disabled, s.saveBtn.textContent];
      out.bar = els.rxBar.hidden; out.h = document.documentElement.style.v;
      console.log(JSON.stringify(out));""")
    assert r["needs"] == [True, "Resolve 1 to save", "1 needs you", "2 medicines"]
    assert r["ready"] == [False, "Save prescription", "1 medicine"]
    assert r["confirmed"] == [False, "Save prescription"] and r["working"] is True
    assert r["view"] == [True, "View only"] and r["viewOk"] == [True, "View only"]
    assert r["bar"] is False and r["h"] == {"--topbar-h": "104px"}


def test_a_blank_row_shows_a_neutral_line_and_no_pill_or_buttons():
    r = _dom("""
      function cellNode() { const n = node(); n.querySelectorAll = () => []; return n; }
      const cell = cellNode(), med = cellNode();
      const tr = row("1", "", {});
      const cols = tr.querySelector;
      tr.querySelector = (q) => (q === "td.check" ? cell : q === "td.med" ? med : q === ".rx-state" ? (cell.children[0] || null) : cols(q));
      setup([tr]); RxView.renderRow(tr);
      const box = cell.children[0];
      console.log(JSON.stringify({ reason: box.children[1].textContent, pillHidden: box.children[0].hidden, acts: box.children[3].children.length, state: tr.dataset.rxstate === undefined }));""")
    assert r == {"reason": "Empty row: removed when you save", "pillHidden": True, "acts": 0, "state": True}


def test_page_wiring_tokens_survive_comment_stripping():
    app = _strip_comments(_read("app.js"))
    grounding = app.split("function updateGrounding()")[1].split("\nfunction ")[0]
    assert grounding.count("RxView.sync()") == 2
    assert "RxView.sync()" in app.split("function resetSheet()")[1].split("\nfunction ")[0]
    body = app.split("function setWorking(")[1].split("\n}\n")[0]
    assert body.index("RxView.sync()") < body.index("Authorship.enforce()")
    handler = app.split('rxBody.addEventListener("click"')[1].split("function refreshBlockPanel()")[0]
    assert "renderCheck(tr);" in handler and "updateGrounding();" in handler and "state.confirmed.add(rowid)" in handler
    assert "need you." in app and "All medicines ready." in app and "need a check" not in app and "verified ✓" not in app


def test_undo_restores_the_row_confirmed_before_its_first_render():
    app = _strip_comments(_read("app.js"))
    undo = app.split("function undoDelete()")[1].split("} else {")[0]
    assert undo.index("if (r.wasConfirmed) state.confirmed.add(r.rowid);") < undo.index("rxRow(r.data, r.pos, r.rowid)")
    assert "tr.dataset.rowid = rowid != null ? String(rowid) : String(++rowSeq);" in app


def test_the_chip_you_chose_wording_survives_the_undo_snapshot():
    r = _dom("""
      const tr = row("1", "unverified-strength", { name: "Amlodipine", strength: "5 mg" }, { strength_options: ["5 mg"] });
      const snap = RxView.meta(tr); snap.how = "chip";
      const confirmedSet = ["1"];
      const back = row("1", "unverified-strength", { name: "Amlodipine", strength: "5 mg" }, snap);
      setup([back], { confirmed: confirmedSet });
      console.log(JSON.stringify([RxView.meta(back).how, RxView.reasonFor(back)]));""")
    assert r[0] == "chip" and "5 mg" in r[1] and "chose" in r[1].lower()


def test_the_sticky_bar_tracks_the_top_bar_height():
    css, js = _read("rx.css"), _read("rxview.js")
    assert "top:var(--topbar-h, 64px)" in css and "top:64px" not in css and ".rx-pill[hidden]" in css
    for token in ('setProperty("--topbar-h"', '"resize"', "document.fonts.ready"):
        assert token in js, token


def test_a_wide_rx_table_scrolls_inside_the_sheet_and_the_check_column_is_not_forced_wide():
    css = _read("rx.css")
    assert re.search(r"td\.check\s*\{\s*min-width:\s*(?:1\d\d|\d\d)px", css) and "min-width:250px" not in css
    assert re.search(r"#sheet\s*\{\s*overflow-x:\s*auto", css)
    assert "ResizeObserver" in _read("rxview.js")


def test_the_on_screen_print_fallback_prints_the_medicine_name_in_capitals():
    """Final review M4: window.print() of the on-screen sheet capitalises the name like the PDF; screen keeps the case."""
    css = (FRONT / "rx.css").read_text(encoding="utf-8")
    prints = re.findall(r"@media print \{([^@]*?)\}\s*\}", css)
    assert any(re.search(r'table\.rx \[data-col="name"\] \{ text-transform:uppercase; ', p) for p in prints)
    assert css.count('[data-col="name"]') == 1                          # only in print: the screen stays as dictated
    assert 'rx.css?v=10"' in (FRONT / "index.html").read_text(encoding="utf-8")
