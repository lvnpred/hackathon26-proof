"""Plan I2-b, page: frontend/sections.js under node with a tiny fake DOM (elements by id, text, hidden)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from doctor_dictation.core.followup import date_label

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FAKE = """const els = {}; ["pRevDate", "pCcNote", "pDxNote"].forEach((id) => { els[id] = { id, textContent: "", hidden: true }; });
globalThis.document = { getElementById: (id) => els[id] || null }; globalThis.window = globalThis;
const posts = []; const tick = () => new Promise((r) => setTimeout(r, 0));"""


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    js = FAKE + "require(process.argv[1]); Sections.init({ post: (u, b) => new Promise((res) => posts.push({ u, b, res })), waitMs: 0 });" \
        + "(async () => {" + body + "})().catch((e) => { console.error(e.stack); process.exit(1); });"
    out = subprocess.run([node, "-e", js, str(FRONT / "sections.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_label_matches_the_server_and_a_stale_answer_is_dropped():
    isos = ["2026-10-24", "2027-01-07", "2029-02-28", "2028-02-29", "", "bad"]
    r = _run("""const labels = %s.map(Sections.dateLabel);
      Sections.showDate("2026-10-24"); const shown = els.pRevDate.textContent;
      Sections.onReviewInput("1 week"); await tick(); Sections.onReviewInput("2 weeks"); await tick();
      posts[1].res({ review_date: "2026-10-31" }); await tick(); posts[0].res({ review_date: "2026-10-24" }); await tick();
      console.log(JSON.stringify({ labels, shown, sent: posts.map((p) => [p.u, p.b.review]), now: els.pRevDate.textContent }));""" % json.dumps(isos))
    assert r["labels"] == [date_label(i) for i in isos]                         # one format, server and page
    assert r["shown"] == "(Sat 24 Oct 2026)" and r["now"] == "(Sat 31 Oct 2026)"   # the older answer lost the race
    assert r["sent"] == [["/api/v1/review-date", "1 week"], ["/api/v1/review-date", "2 weeks"]]


def test_prose_notes_are_text_only_and_an_edit_clears_its_section():
    r = _run("""Sections.showProseCheck([{ field: "complaints", index: 1, words: ["diabetic", "<b>5</b>"] }, { field: "x", index: 0, words: ["y"] }]);
      const shown = [els.pCcNote.textContent, els.pCcNote.hidden, els.pDxNote.hidden];
      Sections.clearProse("complaints"); const cleared = [els.pCcNote.textContent, els.pCcNote.hidden];
      Sections.showProseCheck(undefined);
      console.log(JSON.stringify({ shown, cleared, none: [els.pCcNote.hidden, els.pDxNote.hidden] }));""")
    assert r["shown"] == ["Line 2: not heard in the dictation: diabetic, <b>5</b>. Check this line.", False, True]
    assert r["cleared"] == ["", True] and r["none"] == [True, True]


def test_a_failed_review_date_call_changes_nothing_and_a_blank_answer_shows_no_date():
    r = _run("""Sections.showDate("2026-10-24");
      Sections.onReviewInput("soon"); await tick();
      const before = els.pRevDate.textContent;
      posts[0].res(Promise.reject(new Error("boom"))); await tick(); await tick();
      Sections.onReviewInput("SOS"); await tick(); posts[1].res({ review_date: "" }); await tick();
      console.log(JSON.stringify({ before, after: els.pRevDate.textContent, sent: posts.length }));""")
    assert r == {"before": "", "after": "", "sent": 2}


def test_app_js_wires_the_sections_module_into_the_page_flow():
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "Sections.init({ post: postJson });" in app
    assert 'Sections.showDate(s.review_date || "");' in app                                    # renderSheet: a saved or new sheet shows its date
    assert app.count("Sections.showProseCheck(j.prose_check);") == 2                          # after a dictation and after a correction
    assert '$("pRev").addEventListener("input", () => Sections.onReviewInput(text($("pRev"))));' in app
    assert 'Sections.clearProse("complaints")' in app and 'Sections.clearProse("diagnosis")' in app    # an edit clears its own note
    assert 'Sections.showDate(""); Sections.showProseCheck([]);' in app                       # New patient
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert html.index("sections.js?v=") < html.index("app.js?v=")


def test_each_flagged_line_is_named_in_one_polite_status_note():
    r = _run("""Sections.showProseCheck([{ field: "diagnosis", index: 0, words: ["acute"] }, { field: "diagnosis", index: 2, words: ["likely", "viral"] }]);
      console.log(JSON.stringify({ t: els.pDxNote.textContent, h: els.pDxNote.hidden, c: els.pCcNote.hidden }));""")
    assert r == {"t": "Line 1: not heard in the dictation: acute. Check this line. Line 3: not heard in the dictation: likely, viral. Check this line.", "h": False, "c": True}
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    for note in ("pCcNote", "pDxNote"):
        assert f'id="{note}" class="prose-note no-print" role="status" aria-live="polite" hidden' in html
    assert 'role="note"' not in html.split('id="pCcNote"')[1].split("</p>")[0]
