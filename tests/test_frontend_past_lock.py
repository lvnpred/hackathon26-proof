"""Past prescriptions open view and reprint only (UI-A Task 1): frontend/authorship.js runs under node on a tiny fake DOM
(only the elements Authorship touches), with frontend/dates.js for the banner date."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"

_DOM = r"""
class El {
  constructor(id) { this.id = id; this.hidden = false; this.disabled = false; this.textContent = ""; this.cls = new Set(); this.kids = []; this.dataset = {}; this.contentEditable = "true"; }
  get classList() { const s = this.cls; return { add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c) }; }
  querySelectorAll(sel) {
    if (sel === '[contenteditable="true"]') return this.kids.filter((k) => k.contentEditable === "true");
    if (sel === '[data-ro="1"]') return this.kids.filter((k) => k.dataset.ro === "1");
    return [];
  }
  addEventListener() {}
}
const ids = {}; ["viewOnlyBanner", "recBtn", "saveBtn", "confirmAllBtn", "sheet", "resaveNote", "correctingCue", "printBtn", "grounding"].forEach((id) => { ids[id] = new El(id); });
const cell = new El("cell"); ids.sheet.kids.push(cell);
globalThis.window = globalThis;
globalThis.document = { getElementById: (id) => ids[id] || null, querySelectorAll: () => [] };
globalThis.fetch = () => Promise.resolve({ status: 404 });
const snap = () => ({ banner: ids.viewOnlyBanner.textContent, shown: !ids.viewOnlyBanner.hidden, viewOnly: Authorship.isViewOnly(),
  rec: ids.recBtn.disabled, save: ids.saveBtn.disabled, print: ids.printBtn.disabled, cell: cell.contentEditable });
"""


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = _DOM + f"require({json.dumps(str(FRONT / 'dates.js'))}); require({json.dumps(str(FRONT / 'authorship.js'))});\n" + body
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_past_prescription_locks_the_sheet_in_single_database_mode():
    r = _run('Authorship.onOpen({past: true, visit_date: "2026-10-20", structured: {}}); console.log(JSON.stringify(snap()));')
    assert r == {"banner": "Prescription from 20 Oct 2026: view and reprint only", "shown": True, "viewOnly": True,
                 "rec": True, "save": True, "print": False, "cell": "false"}


def test_new_patient_unlocks_a_past_prescription():
    r = _run('Authorship.onOpen({past: true, visit_date: "2026-10-20"}); Authorship.clear(); console.log(JSON.stringify(snap()));')
    assert r == {"banner": "", "shown": False, "viewOnly": False, "rec": False, "save": False, "print": False, "cell": "true"}


def test_opening_todays_prescription_after_a_past_one_unlocks():
    r = _run('Authorship.onOpen({past: true, visit_date: "2026-10-20"}); Authorship.onOpen({past: false, visit_date: "2026-10-21"});'
             ' console.log(JSON.stringify(snap()));')
    assert r["viewOnly"] is False and r["shown"] is False and (r["rec"], r["save"], r["cell"]) == (False, False, "true")


def test_a_colleagues_past_prescription_shows_the_colleague_banner():
    r = _run('Authorship.onOpen({past: true, visit_date: "2026-10-20", can_edit: false, author: {name: "Dr. Mehta"}});'
             ' console.log(JSON.stringify(snap()));')
    assert r["banner"] == "Dr. Mehta's prescription: view only" and r["viewOnly"] is True and r["rec"] is True


def test_your_own_past_prescription_signed_in_is_locked_too():
    r = _run('Authorship.onOpen({past: true, visit_date: "2026-10-20", can_edit: true, author: {name: "Dr. Rao"}});'
             ' console.log(JSON.stringify(snap()));')
    assert r["banner"] == "Prescription from 20 Oct 2026: view and reprint only" and r["viewOnly"] is True and r["save"] is True


def test_a_view_only_sheet_hides_the_you_can_save_line():
    # app.js renders "All medicines are ready. You can Save." (#grounding) before onOpen locks the sheet; a locked
    # sheet cannot be saved, so the lock hides that line (past days and a colleague's prescription alike).
    r = _run('ids.grounding.textContent = "All medicines are ready. You can Save.";'
             ' Authorship.onOpen({past: true, visit_date: "2026-10-20"}); const past = ids.grounding.hidden;'
             ' Authorship.clear(); ids.grounding.hidden = false;'
             ' Authorship.onOpen({past: false, can_edit: false, author: {name: "Dr. Mehta"}});'
             ' console.log(JSON.stringify({past, colleague: ids.grounding.hidden}));')
    assert r == {"past": True, "colleague": True}


def test_a_refused_past_save_locks_a_sheet_that_opened_editable():
    # Opened at 23:55 (today, editable), saved at 00:05: the server answers 409 "past prescription"; the page locks.
    r = _run('Authorship.onOpen({past: false, visit_date: "2026-10-20"}); const before = Authorship.isViewOnly();'
             ' Authorship.lockPast("2026-10-20"); console.log(JSON.stringify({before, ...snap()}));')
    assert r["before"] is False and r["viewOnly"] is True and (r["rec"], r["save"]) == (True, True)
    assert r["banner"] == "Prescription from 20 Oct 2026: view and reprint only" and r["print"] is False


def test_the_page_locks_on_a_past_prescription_refusal_and_keeps_the_last_good_day():
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    save = app[app.index("async function saveDocument("):app.index('saveBtn.addEventListener("click", saveDocument)')]
    assert 'e.data.error === "past prescription"' in save and "Authorship.lockPast(state.visitDate)" in save
    load = app[app.index("async function loadToday("):app.index("async function openDocument(")]
    assert "state.shownDay = state.listDay" in load                # a day is "shown" only once its rows arrived
    assert "state.listDay = state.shownDay" in load                # a failed fetch puts the title back on that day


def test_the_lock_survives_a_re_enforce_after_set_working():
    r = _run('Authorship.onOpen({past: true, visit_date: "2026-10-20"}); ids.recBtn.disabled = false; ids.saveBtn.disabled = false;'
             ' Authorship.enforce(); console.log(JSON.stringify(snap()));')
    assert (r["rec"], r["save"], r["viewOnly"]) == (True, True, True)


def test_the_page_says_a_past_prescription_is_view_and_reprint_only():
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    body = app[app.index("async function openDocument("):app.index("function updateResaveNote(")]
    assert "j.past" in body and "Past prescriptions are view and reprint only." in body
    save = app[app.index("async function saveDocument("):app.index('saveBtn.addEventListener("click", saveDocument)')]
    assert "e.data.hint" in save                                   # the server's 409 "past prescription" says why
