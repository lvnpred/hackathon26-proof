"""Plan B Task 5: frontend/dictguard.js under node with a tiny fake DOM (banner, forced-choice prompt, one-level Undo)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FAKE = """const els = {}; let adds = 0;
["addingBanner", "nameCheck", "nameCheckText", "nameCheckNew", "nameCheckApply", "undoDict", "undoDictBtn"].forEach((id) => {
  const l = {};
  els[id] = { id, textContent: "", hidden: true, disabled: false, focus() { document.activeElement = els[id]; },
    addEventListener(t, f) { adds++; (l[t] = l[t] || []).push(f); }, fire(t, ev) { (l[t] || []).forEach((f) => f(ev || {})); } };
});
globalThis.document = { getElementById: (id) => els[id] || null, activeElement: null }; globalThis.window = globalThis;
const tick = () => new Promise((r) => setTimeout(r, 0));
const mk = () => ({ structured: { patientName: "Suresh Babu", rx: [{ name: "Dolo" }] }, confirmed: new Set(["r1"]), documentId: 4, dirty: false,
  visitDate: "2026-10-26", savedPatientName: "Suresh Babu", transcript: "t", transcriptSha: "s", engine: "e" });
let state = mk(), rendered = [], restored = 0, notes = [], working = false, checked = 0;
const row = { dataset: { rowid: "r1" }, _rx: { how: "chose" } };
DictGuard.init({ state: () => state, serialize: () => ({ structured: state.structured, indexToRowid: ["r1"] }),
  render: (s, ids) => rendered.push([s, ids]), rows: () => [row], renderCheck: () => { checked++; }, working: () => working,
  restored: () => { restored++; }, notify: (m) => notes.push(m) });"""


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    js = "globalThis.window = globalThis; require(process.argv[1]);" + FAKE.replace("globalThis.window = globalThis;", "") \
        + "(async () => {" + body + "})().catch((e) => { console.error(e.stack); process.exit(1); });"
    # DictGuard must exist before FAKE's init call, and document before the module's lazy lookups: load module first
    out = subprocess.run([node, "-e", js, str(FRONT / "dictguard.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_banner_and_prompt_copy():
    r = _run("""DictGuard.banner({ name: "Suresh Babu", op: "OP-20261026-002", saved: true }); const a = [els.addingBanner.textContent, els.addingBanner.hidden];
      DictGuard.banner(null); const hid = els.addingBanner.hidden;
      DictGuard.ask({ name: "Ravi", op_no: "" }, "Suresh"); const labels = [els.nameCheckNew.textContent, els.nameCheckApply.textContent, els.nameCheckText.textContent];
      console.log(JSON.stringify({ a, hid, labels, b: DictGuard.bannerText({ name: "", op: "", saved: false }),
        p: DictGuard.promptText({ name: "Ravi Kumar", op_no: "" }, "Suresh Babu"), q: DictGuard.promptText({ name: "", op_no: "7" }, "") }));""")
    assert r["a"] == ["Adding to: Suresh Babu · OP-20261026-002 (saved)", False] and r["hid"] is True
    assert r["labels"] == ["Start new patient (Enter)", "Apply to Suresh", "This sounds like Ravi, not Suresh."]
    assert r["b"] == "Adding to: this prescription (not saved yet)"
    assert r["p"] == {"line": "This sounds like Ravi Kumar, not Suresh Babu.", "fresh": "Start new patient (Enter)", "apply": "Apply to Suresh Babu"}
    assert r["q"]["line"] == "This sounds like 7, not this prescription."


def test_ask_defaults_to_start_new_patient_on_enter_and_apply_needs_its_button():
    r = _run("""let got = null; DictGuard.ask({ name: "Ravi", op_no: "" }, "Suresh").then((v) => { got = v; });
      const focus = document.activeElement.id; els.nameCheck.fire("keydown", { key: "Escape" }); await tick();
      const pending = [got, els.nameCheck.hidden]; els.nameCheck.fire("keydown", { key: "Enter" }); await tick();
      const first = [got, els.nameCheck.hidden];
      let got2 = null; DictGuard.ask({ name: "Ravi", op_no: "" }, "Suresh").then((v) => { got2 = v; });
      els.nameCheckApply.fire("click"); await tick();
      console.log(JSON.stringify({ focus, pending, first, got2, texts: [els.nameCheckNew.textContent, els.nameCheckApply.textContent] }));""")
    assert r["focus"] == "nameCheckNew" and r["pending"] == [None, False]
    assert r["first"] == ["new", True] and r["got2"] == "apply"


def test_undo_restores_exactly_the_previous_sheet():
    r = _run("""const orig = state.structured; DictGuard.keep(DictGuard.capture()); orig.rx[0].name = "X";
      state.structured = { patientName: "Other" }; state.visitDate = "x"; state.savedPatientName = "x"; state.transcript = "x"; state.transcriptSha = "x"; state.engine = "x"; state.confirmed = new Set(); state.documentId = 9;
      const before = DictGuard.canUndo(); DictGuard.undo();
      console.log(JSON.stringify({ before, rendered, confirmed: [...state.confirmed], doc: state.documentId, dirty: state.dirty, restored,
        can: DictGuard.canUndo(), hidden: els.undoDict.hidden, notes, checked, how: row._rx.how, meta: [state.visitDate, state.savedPatientName, state.transcript, state.transcriptSha, state.engine], posted: typeof DictGuard.post }));""")
    assert r["before"] is True
    assert r["rendered"] == [[{"patientName": "Suresh Babu", "rx": [{"name": "Dolo"}]}, ["r1"]]]
    assert r["confirmed"] == ["r1"] and r["doc"] == 4 and r["dirty"] is True and r["restored"] == 1
    assert r["can"] is True and r["hidden"] is False and r["checked"] == 1 and r["how"] == "chose" and r["posted"] == "undefined"
    assert r["meta"] == ["2026-10-26", "Suresh Babu", "t", "s", "e"]
    assert r["notes"] == ["Back to the sheet before your last dictation. Undo again to return. Save to keep it."]


def test_the_snapshot_survives_a_reset_and_save_and_brings_back_its_own_document():
    r = _run("""state.documentId = null; const snap = DictGuard.capture(); DictGuard.keep(snap);
      state.documentId = 12; working = true; DictGuard.undo(); const stuck = [state.documentId, rendered.length];
      working = false; const second = DictGuard.capture(); second.documentId = 7; DictGuard.keep(second); DictGuard.undo();
      const afterSecond = state.documentId; DictGuard.keep(snap); state.documentId = 12; DictGuard.undo();
      state.structured = null; console.log(JSON.stringify({ stuck, afterSecond, doc: state.documentId, rendered: rendered.length, nul: DictGuard.capture(), can: DictGuard.canUndo() }));""")
    assert r["stuck"] == [12, 0]                        # busy: nothing changes
    assert r["afterSecond"] == 7                        # one level: the second keep replaced the first
    assert r["doc"] is None and r["rendered"] == 2 and r["nul"] is None and r["can"] is True


def test_undo_twice_brings_the_newer_sheet_back_and_swaps_the_document_both_ways():
    r = _run("""DictGuard.keep(DictGuard.capture());
      state.structured = { patientName: "Suresh Babu", rx: [{ name: "Pan" }] }; state.documentId = 9; state.transcript = "t2";
      DictGuard.undo(); const one = [state.structured.rx[0].name, state.documentId, state.transcript, DictGuard.canUndo()];
      DictGuard.undo(); const two = [state.structured.rx[0].name, state.documentId, state.transcript, DictGuard.canUndo()];
      working = true; DictGuard.undo(); const busy = [state.structured.rx[0].name, state.documentId, rendered.length];
      console.log(JSON.stringify({ one, two, busy, hidden: els.undoDict.hidden }));""")
    assert r["one"] == ["Dolo", 4, "t", True]
    assert r["two"] == ["Pan", 9, "t2", True]
    assert r["busy"] == ["Pan", 9, 2] and r["hidden"] is False


def test_the_prompt_points_the_status_at_itself():
    r = _run("""DictGuard.ask({ name: "Ravi", op_no: "" }, "Suresh Babu"); DictGuard.ask({ name: "Ravi", op_no: "" }, "Suresh Babu");
      els.nameCheckNew.fire("click"); await tick(); DictGuard.ask({ name: "Ravi", op_no: "" }, ""); console.log(JSON.stringify({ notes }));""")
    assert r["notes"] == ["Choose: start a new patient, or apply to Suresh Babu.", "Choose: start a new patient, or apply to this prescription."]


def test_kept_note_names_the_sheet_only_when_the_dictated_patient_differed():
    r = _run("""const cur = { patientName: "Suresh Babu", ageSex: "40 / M", opNo: "OP 2" };
      console.log(JSON.stringify({
        name: DictGuard.keptNote({ patientName: "Ravi Kumar", ageSex: "40 / M", opNo: "OP 2" }, cur),
        age: DictGuard.keptNote({ patientName: "Suresh Babu", ageSex: "45 / M", opNo: "OP 2" }, cur),
        same: DictGuard.keptNote({ ...cur, rx: [] }, cur), blank: DictGuard.keptNote({ patientName: "", ageSex: "", opNo: "" }, cur),
        unnamed: DictGuard.keptNote({ patientName: "Ravi" }, { patientName: "" }) }));""")
    assert r["name"] == r["age"] == 'Kept Suresh Babu\'s details. Say "change the name to …" to rename.'
    assert r["same"] == "" and r["blank"] == ""
    assert r["unnamed"] == 'Kept this prescription\'s details. Say "change the name to …" to rename.'


def test_keep_identity_puts_back_the_sheets_patient():
    r = _run("""const inp = { patientName: "Ravi Kumar", ageSex: "45 / M", opNo: "", rx: [1] };
      const out = DictGuard.keepIdentity(inp, { patientName: "Suresh Babu", ageSex: "40 / M", opNo: "OP 2" });
      console.log(JSON.stringify({ out, inp }));""")
    assert r["out"] == {"patientName": "Suresh Babu", "ageSex": "40 / M", "opNo": "OP 2", "rx": [1]}
    assert r["inp"] == {"patientName": "Ravi Kumar", "ageSex": "45 / M", "opNo": "", "rx": [1]}


def test_enter_on_apply_applies_and_overlapping_asks_share_one_prompt():
    r = _run("""let a = null, b = null, n = 0;
      const p1 = DictGuard.ask({ name: "Ravi", op_no: "" }, "Suresh").then((v) => { a = v; n++; });
      const afterOne = adds; const p2 = DictGuard.ask({ name: "Ravi", op_no: "" }, "Suresh").then((v) => { b = v; n++; });
      const afterTwo = adds; els.nameCheckNew.fire("click"); els.nameCheckNew.fire("click"); await tick();
      const shared = [a, b, n, els.nameCheck.hidden];
      let c = null; DictGuard.ask({ name: "Ravi", op_no: "" }, "Suresh").then((v) => { c = v; });
      els.nameCheck.fire("keydown", { key: "Enter", target: els.nameCheckApply }); await tick();
      let d = null; DictGuard.ask({ name: "Ravi", op_no: "" }, "Suresh").then((v) => { d = v; });
      els.nameCheck.fire("keydown", { key: "Enter", target: els.nameCheckText }); await tick();
      console.log(JSON.stringify({ afterOne, afterTwo, grown: adds - afterOne, shared, c, d }));""")
    assert r["afterOne"] == r["afterTwo"] and r["grown"] == 0   # handlers bound once, never per call
    assert r["shared"] == ["new", "new", 2, True]               # both callers settle once, on the one prompt
    assert r["c"] == "apply" and r["d"] == "new"


def _fn(src, head):
    part = src[src.index(head):]
    return part[:part.index("\n}\n") + 3]


def _correct(answer, pick="apply"):
    """Run app.js's real applyCorrection against stubbed collaborators; `answer` is the /api/v1/correct reply or None to reject."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    script = """
      const SHEET = { patientName: "Suresh Babu", ageSex: "40 / M", opNo: "OP 1", rx: [{ name: "Dolo" }] };
      const log = { render: [], asks: 0, keeps: [], resets: 0, formats: [], order: [] };
      const state = { structured: SHEET, transcript: "", documentId: 4, retry: null, confirmed: new Set(), lastBlock: [], dirty: false };
      const answer = %s, pick = %s, snap = { id: "snap" };
      const serializeForm = () => ({ structured: SHEET, indexToRowid: ["r1"] });
      const noop = () => {}, wordCount = () => 3, stepCounts = () => ({}), openRows = () => [], warningNote = () => "", errorMessage = (e) => e.message;
      const renderTranscript = noop, setWorking = noop, setStep = noop, markDirty = noop, hideBlockPanel = noop, renderCheck = noop, showError = noop;
      const setStatus = (m) => { log.status = m; };
      const CORRECT_TIMEOUT_MS = 1, RxState = { carryRowids: () => ["r1"] }, RxView = { focusFirst: noop }, Sections = { showProseCheck: noop };
      const rxBody = { querySelectorAll: () => [] }, $ = (id) => ({ id }), text = () => "Suresh Babu";
      const renderSheet = (s) => log.render.push(s);
      const postJson = async () => { if (!answer) throw new Error("boom"); return answer; };
      const resetSheet = () => { log.resets++; log.order.push("reset"); };
      const formatTranscript = async (t, s) => { log.formats.push([t, s]); log.order.push("format"); };
      const DictGuard = { ask: async () => { log.asks++; return pick; }, keep: (s) => { log.keeps.push(s); log.order.push("keep"); },
        keptNote: (s, c) => s.patientName !== c.patientName ? "KEPT" : "",
        keepIdentity: (s, c) => { const o = JSON.parse(JSON.stringify(s)); ["patientName", "ageSex", "opNo"].forEach((k) => { o[k] = c[k]; }); return o; } };
      %s
      (async () => { await applyCorrection("Next patient Ravi Kumar", snap);
        console.log(JSON.stringify({ log, retry: state.retry, same: state.structured === SHEET })); })();
    """ % (json.dumps(answer), json.dumps(pick), _fn(app, "async function applyCorrection("))
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_correction_naming_another_patient_changes_nothing_and_enter_starts_a_new_prescription():
    r = _correct({"structured": {"patientName": "Ravi Kumar", "rx": []}, "other_patient": {"name": "Ravi Kumar", "op_no": ""}, "changed_rows": []}, "new")
    assert r["log"]["render"] == [] and r["same"] is True
    assert r["log"]["resets"] == 1
    assert r["log"]["formats"] == [["Next patient Ravi Kumar", {"id": "snap"}]]
    assert r["log"]["keeps"] == [{"id": "snap"}]
    assert r["log"]["order"] == ["keep", "reset", "format"]


def test_apply_keeps_the_sheets_patient_and_the_same_patient_applies_silently():
    other = {"structured": {"patientName": "Ravi Kumar", "ageSex": "9 / M", "opNo": "", "rx": []}, "other_patient": {"name": "Ravi Kumar", "op_no": ""}, "changed_rows": []}
    r = _correct(other, "apply")
    assert [s["patientName"] for s in r["log"]["render"]] == ["Suresh Babu"] and r["log"]["render"][0]["opNo"] == "OP 1"
    assert r["log"]["keeps"] == [{"id": "snap"}] and r["log"]["resets"] == 0
    assert r["log"]["status"].endswith(" KEPT")
    r = _correct({**other, "other_patient": None}, "new")
    assert "KEPT" not in r["log"]["status"]
    assert r["log"]["asks"] == 0 and len(r["log"]["render"]) == 1 and r["log"]["render"][0]["patientName"] == "Ravi Kumar"
    assert r["log"]["keeps"] == [{"id": "snap"}]


def test_a_failed_correction_keeps_the_form_the_retry_and_the_snapshot():
    r = _correct(None)
    assert r["log"]["render"] == [] and r["log"]["keeps"] == [] and r["log"]["asks"] == 0
    assert r["retry"] == {"mode": "correct", "transcript": "Next patient Ravi Kumar", "snap": {"id": "snap"}}


def test_app_wires_the_guard_and_index_loads_it_first():
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    for needle in ("DictGuard.banner(", "DictGuard.capture()", "#undoDictBtn", "DictGuard.init("):
        assert needle in app, needle
    assert app.count("DictGuard.clear()") == 2
    assert html.index("dictguard.js?v=") < html.index("app.js?v=")
