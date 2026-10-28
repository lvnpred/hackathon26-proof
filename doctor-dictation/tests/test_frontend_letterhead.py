"""Static checks for the letterhead browser code (M4). No browser: the manual checklist covers behaviour."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def test_index_has_the_scope_doctors_and_switch_back_controls():
    html = _read("index.html")
    for elem_id in ("profLhMine", "profUseClinicBtn", "lhDoctorsBox", "lhDoctorPicks", "lhHints", "lhScopeBox"):
        assert f'id="{elem_id}"' in html, elem_id
    for value in ("author", "all", "selected"):
        assert f'name="lhDoctorsMode" value="{value}"' in html
    assert 'name="lhScope" value="clinic" checked' in html and 'name="lhScope" value="mine"' in html
    for text in ("For the whole clinic", "For my prescriptions only", "Use the clinic letterhead"):
        assert text in html


def test_letterhead_js_uses_the_new_routes_and_view_keys():
    js = _read("letterhead.js")
    assert '"/current"' in js and '"/doctors"' in js and 'method: "PUT"' in js
    assert 'scope: "mine"' in js and "warnings" in js and "doctor_hints" in js


def test_letterhead_js_never_builds_markup_from_server_text():
    js = _read("letterhead.js")
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "outerHTML" not in js


def test_letterhead_assets_are_cache_busted():
    html = _read("index.html")
    assert "letterhead.js?v=13" in html and "letterhead.css?v=9" in html
    assert html.index("lhlines.js?v=3") < html.index("letterhead.js?v=")


def test_review_screen_has_the_remove_and_duplicate_controls():
    html, js = _read("index.html"), _read("lhlines.js")
    assert 'id="lhDupes"' in html and 'id="lhSkipped"' in html
    assert "Remove this line" in js and "At the top only" in js and "In both places" in js
    assert "Choose where the" not in js + _read("letterhead.js")        # owner Q5: the question never blocks
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js       # server text is never markup
    assert len(_read("letterhead.js").splitlines()) < 500


def test_clinic_details_have_the_op_prefix_field_wired_both_ways():
    html, js = _read("index.html"), _read("app.js")
    clinic_part = html.split('id="profClinicPart"')[1].split("</fieldset>")[0]          # M3's Clinic details
    assert re.search(r'id="profOpPrefix"[^>]*maxlength="6"', clinic_part)
    assert 'setInput("profOpPrefix"' in js and 'op_prefix: inputVal("profOpPrefix")' in js


def test_single_mode_hides_the_doctors_choice_and_sends_nothing():
    html, js = _read("index.html"), _read("letterhead.js")
    assert re.search(r'id="lhDoctorsBox"[^>]*\bhidden\b', html)
    assert 'el("lhDoctorsBox").hidden = !lh.personal' in js
    guard = js.split("async function saveDoctors()")[1].split("\n", 2)[1]
    assert 'el("lhDoctorsBox").hidden' in guard and "return true" in guard


def test_warning_says_may_be_a_doctors_name():
    assert "may be a doctor's name" in _read("letterhead.js")


def test_app_js_is_cache_busted_after_the_op_prefix_edit():
    html = _read("index.html")
    version = int(re.search(r"app\.js\?v=(\d+)", html).group(1))
    assert version >= 20                                  # bumped by the OP prefix edit (v20) and later edits


def test_loading_the_doctor_picks_cannot_run_twice_at_once():
    assert "lh.loadingPicks" in _read("letterhead.js")


def test_unsaved_op_prefix_counts_as_a_profile_edit():
    js = _read("letterhead.js")
    assert 'el("profOpPrefix").value.toUpperCase()' in js.split("function profileDirty()")[1].split("function syncProfileBtn")[0]


def test_letterhead_js_parses():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    for name in ("letterhead.js", "lhlines.js"):
        out = subprocess.run([node, "--check", str(FRONT / name)], capture_output=True, text=True)
        assert out.returncode == 0, out.stderr


def _open_panel_body():
    js = _read("letterhead.js")
    return js[js.index("async function openPanel"):js.index("function closePanel")]


def test_open_panel_reloads_the_doctor_list_and_waits_for_the_status_before_the_review():
    body = _open_panel_body()
    assert "lh.choices = null" in body                                  # M5 can add or disable doctors between openings
    assert "await refreshStatus()" in body
    assert body.index("await refreshStatus()") < body.index("renderReview(lh.draft)")   # lh.personal is fresh for the scope box
    assert "loadingPicks" in _read("letterhead.js")


def test_the_review_screen_says_the_accepters_details_are_filled_in_author_mode():
    html, js = _read("index.html"), _read("letterhead.js")
    assert 'id="lhFillHint"' in html and "Your own doctor details will be filled from this letterhead." in html
    assert 'el("lhFillHint").hidden = !(lh.personal && mode === "author");' in js
    assert 'lhFillHint").innerHTML' not in js


def test_active_letterhead_can_be_fixed_without_a_new_upload():
    html, js = _read("index.html"), _read("letterhead.js")
    for elem_id in ("lhTidyBtn", "lhTidyMineBtn", "lhTidySaveBtn", "lhDetailsPart"):
        assert f'id="{elem_id}"' in html, elem_id
    assert '"/lines"' in js and "Fix lines on the clinic letterhead" in html and "Fix lines on my letterhead" in html
    assert "New prescriptions and re-prints use the fixed letterhead." in js
    assert "Press Fix lines to check them." in js and "print twice" not in js
    assert "(j.clinic.duplicates" not in js and "j.mine.fill_in" in js
    assert "The letterhead changed since you opened it. Close and reopen Fix lines." in js
    assert "if (r.status === 400) refreshStatus();" in js
    assert "innerHTML" not in js


def test_tidy_mode_hides_accept_and_the_details_part():
    js = _read("letterhead.js")
    show = js[js.index("function show("):js.index("async function openPanel")]
    assert '"tidy"' in show and "lhAcceptBtn" in show and "lhDetailsPart" in show and "lhTidySaveBtn" in show


def test_tidy_saves_the_lines_and_redraws_from_the_returned_view():
    js = _read("letterhead.js")
    save = js[js.index("async function saveTidy"):]
    save = save[:save.index("\n  }\n")]
    assert 'method: "PUT"' in save and "LhLines.collect" in save and "renderLines(" in save and "loadPreview(" in save
    assert "lh.tidy = null" in js
    assert "loadPreview(lh.draft.id)" in js


def test_tidy_errors_do_not_talk_about_drafts():
    js = _read("letterhead.js")
    msg = js[js.index("function httpMessage"):js.index("function netMessage")]
    assert 'what === "lines"' in msg
    assert "This letterhead is no longer in use. Close this panel and check the current letterhead." in msg
    assert "A line could not be saved. Check the lines and try again." in msg
    assert msg.index('what === "lines"') < msg.index("This draft no longer exists")
    assert "404" in msg and "409" in msg and "400" in msg
    save = js[js.index("async function saveTidy"):]
    assert 'httpMessage(r.status, "lines", j)' in save[:save.index("\n  }\n")]


def test_tidy_mode_skips_the_doctor_name_warning_that_points_below():
    js = _read("letterhead.js")
    tidy = js[js.index("function openTidy"):js.index("async function discard")]
    assert "renderWarnings" not in tidy
