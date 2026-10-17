"""Steppers (I1-f). The stage rules run under node (no DOM); the wiring is checked as text, with comments stripped so a
comment cannot satisfy a check. Behaviour in a real browser is the manual checklist in the plan."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _code(name):
    """Source with block comments and line comments removed (a // inside a string, such as a URL, is kept)."""
    s = re.sub(r"/\*.*?\*/", "", _read(name), flags=re.S)
    return re.sub(r"(^|[\s;{}),])//[^\n]*", r"\1", s)


def _slice(src, start, end):
    a = src.index(start)
    return src[a:src.index(end, a)]


def _node(expr):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = "globalThis.window = globalThis; require(process.argv[1]); console.log(JSON.stringify(" + expr + "))"
    out = subprocess.run([node, "-e", script, str(FRONT / "steps.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _status(stage, info="{}"):
    return f"StepsLogic.main({json.dumps(stage)}, {info}).steps.map((s) => s.status)"


def test_the_main_progress_has_four_steps_and_never_a_stage_the_page_cannot_know():
    r = _node('StepsLogic.main("listening", {}).steps.map((s) => s.label)')
    assert r == ["Listening", "Transcribing", "Structuring and checking", "Your review"]
    assert _node(_status("listening")) == ["now", "todo", "todo", "todo"]
    assert _node(_status("transcribing")) == ["done", "now", "todo", "todo"]
    assert _node(_status("structuring")) == ["done", "done", "now", "todo"]
    assert _node(_status("ready")) == ["done", "done", "done", "now"]
    assert _node(_status("idle")) == ["todo"] * 4 and _node(_status("no-such-stage")) == ["todo"] * 4


def test_words_come_from_what_the_page_measured():
    r = _node('StepsLogic.main("ready", {recorded:"00:48", words:142, rows:5, needs:2}).steps.map((s) => s.sub)')
    assert r == ["00:48 recorded", "142 words", "5 medicines checked", "2 medicines need you"]
    one = _node('StepsLogic.main("ready", {words:1, rows:1, needs:1}).steps.map((s) => s.sub)')
    assert one[1:] == ["1 word", "1 medicine checked", "1 medicine needs you"]
    assert _node('StepsLogic.main("structuring", {mode:"correct"}).steps[2].sub') == "Applying your correction"
    assert _node('StepsLogic.main("ready", {rows:3}).steps[3].sub') == "Everything checked. Ready to save."
    # zero medicine rows: never "Everything checked", and no "0 medicines checked" either
    nothing = _node('StepsLogic.main("ready", {rows:0, needs:0}).steps')
    assert nothing[3]["sub"] == "No medicines yet" and nothing[2]["sub"] == "" and nothing[3]["status"] == "now"
    assert _node('StepsLogic.main("ready", {}).steps[3].sub') == "No medicines yet"
    # a row added by hand later counts as needing the doctor even when the saved row count was zero
    assert _node('StepsLogic.main("ready", {rows:0, needs:1}).steps[3].sub') == "1 medicine needs you"


def test_a_failure_marks_only_the_step_that_failed_and_a_reopened_prescription_claims_nothing_was_heard():
    assert _node(_status("failed-listening", '{reason:"No audio captured"}')) == ["failed", "todo", "todo", "todo"]
    assert _node(_status("failed-transcribing", '{reason:"No words found"}')) == ["done", "failed", "todo", "todo"]
    assert _node(_status("failed-structuring", '{reason:"x"}')) == ["done", "done", "failed", "todo"]
    assert _node('StepsLogic.main("failed-transcribing", {reason:"No words found"}).steps[1].sub') == "No words found"
    assert _node(_status("opened")) == ["na", "na", "na", "now"]
    assert _node('StepsLogic.main("opened", {}).steps[3].sub') == "Reopened prescription"
    assert _node('StepsLogic.main("failed-structuring", {}).chip') == {"text": "Problem", "cls": "failed"}
    assert _node('StepsLogic.main("opened", {}).chip') == {"text": "Ready", "cls": "ready"}


def test_a_view_only_prescription_never_shows_your_review_in_progress():
    v = _node('StepsLogic.main("opened", {viewOnly:true}).steps')
    assert [s["status"] for s in v] == ["na", "na", "na", "na"]
    assert v[3]["sub"] == "View only. You can print it."
    assert [s["status"] for s in _node('StepsLogic.main("opened", {viewOnly:false}).steps')] == ["na", "na", "na", "now"]


def test_the_profile_steps_follow_what_is_filled_in_and_what_has_focus():
    assert _node('StepsLogic.profile({}).map((s) => s.status)') == ["now", "todo", "todo"]
    assert _node('StepsLogic.profile({clinic:"x", mine:"y"}).map((s) => s.status)') == ["done", "done", "now"]
    assert _node('StepsLogic.profile({clinic:"x", mine:"y", active:"clinic"}).map((s) => s.status)') == ["now", "done", "todo"]
    locked = _node('StepsLogic.profile({clinic:"x", mine:"y", lhLocked:true})[2]')
    assert locked["status"] == "locked" and locked["sub"] == "Opens after you save"
    assert _node('StepsLogic.profile({clinic:"x", mine:"y", lhDone:true}).map((s) => s.status)') == ["done", "done", "done"]


def test_the_letterhead_steps_follow_the_panels_real_states_and_show_no_percentage():
    up = "{upload:true, review:false, busyLabel:'', done:''}"
    assert _node(f"StepsLogic.letterhead({up}).map((s) => s.status)") == ["now", "todo", "todo", "todo"]
    reading = _node("StepsLogic.letterhead({upload:true, review:false, busyLabel:'Uploading and reading your letterhead. This can take up to a minute…', done:''})")
    assert [s["status"] for s in reading] == ["done", "now", "todo", "todo"] and reading[1]["sub"] == "Sending the picture and reading the pad"
    assert _node("StepsLogic.letterhead({upload:false, review:true, busyLabel:'', done:''}).map((s) => s.status)") == ["done", "done", "now", "todo"]
    assert _node("StepsLogic.letterhead({upload:false, review:true, busyLabel:'Saving your edits…', done:''}).map((s) => s.status)") == ["done", "done", "now", "todo"]
    assert _node("StepsLogic.letterhead({upload:false, review:true, busyLabel:'Saving your letterhead…', done:''}).map((s) => s.status)") == ["done", "done", "done", "now"]
    for msg in ("Done. The clinic letterhead is saved, and its clinic details were saved to the Profile. New prescriptions print on it.",
                "Done. Your own letterhead is saved. Only your prescriptions print on it; colleagues keep the clinic letterhead."):
        assert _node(f"StepsLogic.letterhead({{upload:true, review:false, busyLabel:'', done:{json.dumps(msg)}}}).map((s) => s.status)") == ["done"] * 4
    for msg in ("The draft was discarded.", "Done. Prescriptions now print on the built-in layout with your clinic details."):   # discard and "stop using" are not accept
        assert _node(f"StepsLogic.letterhead({{upload:true, review:false, busyLabel:'', done:{json.dumps(msg)}}}).map((s) => s.status)") == ["now", "todo", "todo", "todo"], msg
    assert "%" not in _code("steps.js") and '<progress aria-label="Working"></progress>' in _read("index.html")


def test_the_words_the_steppers_read_still_exist_where_they_are_produced():
    lh, app = _code("letterhead.js"), _code("app.js")
    for text in ('"Uploading and reading your letterhead.', '"Saving your letterhead…"', '"Done. Your own letterhead is saved.', '"Done. The clinic letterhead is saved',
                 "Clinic letterhead: active."):
        assert text in lh, text
    assert 'el("lhPanel").setAttribute("aria-busy"' in lh and "lhPanel\").addEventListener(\"close\", () => { if (lh.abort && !lh.draft) lh.abort.abort(); })" in lh
    # the accept match in steps.js must match both accept messages and not the "stop using" one
    pat = re.search(r"/(\^Done\\\. \(Your own\|The clinic\) letterhead is saved)/", _code("steps.js"))
    assert pat, "steps.js must match the accept messages by their full opening words"
    rx = re.compile(pat.group(1))
    msgs = [a or b for a, b in re.findall(r'"(Done\. [^"]*)"|`(Done\. [^`]*)`', lh)]
    assert len([m for m in msgs if rx.match(m)]) == 2 and any("built-in layout" in m for m in msgs if not rx.match(m))
    for stage in ('setStep("transcribing"', 'setStep("structuring"', 'setStep("failed-structuring"', 'setStep("opened"'):
        assert stage in app, stage
    assert 'setStep("working")' not in app and "agentChip.className" not in app


def test_app_js_routes_each_failure_to_the_step_that_failed():
    app = _code("app.js")
    stop = _slice(app, "async function onRecordingStop", "async function postJson")
    assert 'setStep("failed-listening", { reason: "No audio captured" })' in stop
    assert 'setStep("transcribing", { recorded: timerEl.textContent })' in stop
    assert 'setStep("failed-transcribing", { reason: "No words found" })' in stop
    # applyCorrection/readForm can throw after the transcript is known: that is a structuring failure, not a transcription one
    catch = stop[stop.index("} catch (e)"):]
    assert 'state.transcript ? "failed-structuring" : "failed-transcribing"' in catch and 'setStep("idle")' not in stop
    fmt = _slice(app, "async function formatTranscript", "async function applyCorrection")
    assert 'setStep("structuring", { words: wordCount(transcript), mode: "dictate" })' in fmt
    assert fmt.count('setStep("ready", stepCounts())') == 1 and 'setStep("failed-structuring"' in fmt and 'setStep("idle")' not in fmt
    cor = app[app.index("async function applyCorrection"):]
    cor = cor[:cor.index("\n}\n")]
    assert 'setStep("structuring", { words: wordCount(transcript), mode: "correct" })' in cor
    assert cor.count('setStep("ready", stepCounts())') == 1 and 'setStep("failed-structuring"' in cor and 'setStep("idle")' not in cor
    tr = _slice(app, "async function transcribe", "async function formatTranscript")
    assert tr.index('setStep("transcribing")') < tr.index('"/api/transcribe"')


def test_a_reopened_prescription_reports_view_only_and_the_review_line_follows_the_count():
    app = _code("app.js")
    op = _slice(app, "async function openDocument", "\n}\n")
    assert op.index("Authorship.onOpen(j)") < op.index('setStep("opened", { viewOnly: viewOnlyNow, ...stepCounts() })')
    assert op.index("const viewOnlyNow") < op.index('setStep("opened"')
    grounding = _slice(app, "function updateGrounding", "\n}\n")
    assert "if (window.Steps) Steps.needs(stepCounts())" in grounding and "RxView.sync()" in grounding


def test_the_page_loads_the_steppers_and_the_old_three_step_markup_is_gone():
    html, css = _read("index.html"), _read("styles.css")
    assert re.search(r'<ol id="steps" class="stp-list" aria-label="Assistant progress"></ol>', html) and 'data-step="working"' not in html
    assert html.index("steps.js?v=") < html.index("app.js?v=") and 'href="steps.css?v=1"' in html and int(re.search(r"app\.js\?v=(\d+)", html).group(1)) >= 29
    assert html.index('id="profSteps"') < html.index('id="profClinicPart"') and html.index('id="lhSteps"') < html.index('class="lh-body"')
    assert ".steps .step" not in css and ".step[data-step" not in css and "@page { margin: 14mm; }" in css
    assert "styles.css?v=9" in html          # the stylesheet version is deliberately not bumped (stale .steps rules are harmless)


def test_the_taller_sticky_pane_stays_scrollable_and_steps_are_hidden_in_print():
    css = _read("steps.css")
    assert re.search(r"\.middle\s*\{[^}]*max-height:\s*calc\(100vh - var\(--topbar-h,\s*70px\) - 24px\)[^}]*overflow-y:\s*auto", css)
    printed = _read("styles.css").split("@media print", 1)[1]
    assert re.search(r"\.topbar, \.sidebar, \.middle, \.no-print[^{]*\{\s*display:none !important", printed)


def test_steps_js_parses_builds_dom_safely_and_the_stylesheet_has_no_motion():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    assert subprocess.run([node, "--check", str(FRONT / "steps.js")], capture_output=True, text=True).returncode == 0
    js, css = _code("steps.js"), _code("steps.css")
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "animation" not in css and "transition" not in css
    assert 'cancel.className = "stp-cancel"' in js and 'className = "stp-cancel lh-act"' not in js    # setBusy() disables .lh-act buttons; Cancel must stay enabled
    assert len(_read("steps.js").splitlines()) < 500


def _page(expr):
    """Run steps.js with a document that has no elements: Steps.main/needs then run their state logic and return the rules' result."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = ("globalThis.window = globalThis; globalThis.document = { getElementById: () => null }; require(process.argv[1]);"
              "const sub = (r) => r && r.steps.map((s) => s.sub); const st = (r) => r && r.steps.map((s) => s.status);" + expr)
    out = subprocess.run([node, "-e", script, str(FRONT / "steps.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_review_line_and_the_medicine_count_follow_the_live_rows_not_the_draft():
    # draft arrives with 2 verified rows, the doctor deletes both: step 3 and 4 must say so
    r = _page('Steps.main("ready", {rows:2, needs:0}); console.log(JSON.stringify([sub(Steps.needs({rows:2, needs:0})), sub(Steps.needs({rows:0, needs:0}))]))')
    assert r[0][2:] == ["2 medicines checked", "Everything checked. Ready to save."]
    assert r[1][2:] == ["", "No medicines yet"]
    # draft with no rows, the doctor adds one that needs them, then resolves it
    r = _page('Steps.main("ready", {rows:0, needs:0}); console.log(JSON.stringify([sub(Steps.needs({rows:1, needs:1})), sub(Steps.needs({rows:1, needs:0}))]))')
    assert r[0][2:] == ["1 medicine checked", "1 medicine needs you"] and r[1][2:] == ["1 medicine checked", "Everything checked. Ready to save."]
    # a draft whose only row is blank says 0 medicines: the page passes the live count, which skips blank rows
    assert _page('console.log(JSON.stringify(sub(Steps.main("ready", {rows:0, needs:0}))))')[2:] == ["", "No medicines yet"]
    # needs() before any stage, or after idle, changes nothing
    assert _page('console.log(JSON.stringify(Steps.needs({rows:1, needs:1})))') is None
    assert _page('Steps.main("idle"); console.log(JSON.stringify(Steps.needs({rows:1, needs:1})))') is None


def test_a_reopened_own_prescription_shows_the_live_count_and_a_view_only_one_stays_untouched():
    r = _page('const a = sub(Steps.main("opened", {viewOnly:false, rows:1, needs:1}));'
              'const b = sub(Steps.needs({rows:1, needs:0})); const c = sub(Steps.needs({rows:0, needs:0}));'
              'console.log(JSON.stringify([a, b, c, sub(Steps.main("opened", {viewOnly:false}))]))')
    assert r[0][3] == "Reopened prescription. 1 medicine needs you"
    assert r[1][3] == "Reopened prescription. Everything checked. Ready to save." and r[2][3] == "Reopened prescription. No medicines yet"
    assert r[3][3] == "Reopened prescription"          # no live count passed: old wording
    v = _page('Steps.main("opened", {viewOnly:true, rows:1, needs:1}); console.log(JSON.stringify([Steps.needs({rows:3, needs:3}), sub(Steps.main("opened", {viewOnly:true, rows:1, needs:1}))]))')
    assert v[0] is None and v[1][3] == "View only. You can print it."
    # the status of step 4 while it is in progress is still "now" for an own document
    assert _page('console.log(JSON.stringify(st(Steps.main("opened", {viewOnly:false, rows:1, needs:1}))))')[3] == "now"


def _dom(body):
    """Run steps.js against tests/steps_fakedom.js (elements by id, observers fired on demand); body is JS that prints one JSON value."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = ("const D = require(process.argv[1]); require(process.argv[2]);"
              "const fire = () => D.fire(), E = D.els;" + body)
    out = subprocess.run([node, "-e", script, str(Path(__file__).parent / "steps_fakedom.js"), str(FRONT / "steps.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


_PROFILE = 'E.profClinic.value = "Clinic"; E.profDoctor.value = "Dr"; E.profLhStatus.textContent = "%s"; E.profLhMine.hidden = %s; E.profLhMine.textContent = "%s"; fire(); '
_NONE = "Clinic letterhead: none. Prescriptions print on the built-in layout with your clinic details."
_OWN = "My own letterhead: active. Only my prescriptions print on it."


def test_the_profile_letterhead_step_reads_both_the_clinic_line_and_the_own_line_and_repaints_on_either():
    def run(clinic, mine_hidden, mine):
        return _dom((_PROFILE % (clinic, json.dumps(mine_hidden), mine)) + 'console.log(JSON.stringify(D.status("profSteps")))')
    assert run("Clinic letterhead: active. Prescriptions print on it.", True, "") == ["done", "done", "done"]
    assert run(_NONE, False, _OWN) == ["done", "done", "done"]            # own letterhead only: the line is in #profLhMine, not #profLhStatus
    assert run(_NONE, True, "") == ["done", "done", "now"]
    assert run(_NONE, False, "My own letterhead: none.") == ["done", "done", "now"]
    assert run(_NONE, False, "My own letterhead: not set.") == ["done", "done", "now"]
    assert run(_NONE, True, _OWN) == ["done", "done", "now"]               # a hidden own line is ignored
    # a change to #profLhMine alone must repaint: both lines are watched
    assert {"profLhStatus", "profLhMine", "profLhHint"} <= set(_dom('console.log(JSON.stringify(D.observed))'))


def test_the_profile_letterhead_step_is_locked_before_save_and_open_after():
    r = _dom('E.profClinic.value = "C"; E.profDoctor.value = "D"; E.profLhHint.hidden = false; fire();'
             'const a = [D.status("profSteps")[2], D.subs("profSteps")[2]]; E.profLhHint.hidden = true; fire();'
             'console.log(JSON.stringify([a, [D.status("profSteps")[2], D.subs("profSteps")[2]]]))')
    assert r[0] == ["locked", "Opens after you save"] and r[1] == ["now", ""]


def test_the_main_steps_set_aria_current_on_exactly_the_active_step_and_the_chip_follows_the_stage():
    r = _dom('const out = {}; for (const s of ["listening", "transcribing", "structuring", "ready", "failed-transcribing", "opened", "idle"]) {'
             'Steps.main(s, {viewOnly: false}); out[s] = [D.current("steps"), E.agentChip.textContent, E.agentChip.className]; } console.log(JSON.stringify(out))')
    cur = lambda s: r[s][0]
    assert cur("listening") == ["step", None, None, None] and cur("transcribing") == [None, "step", None, None]
    assert cur("structuring") == [None, None, "step", None] and cur("ready") == [None, None, None, "step"] and cur("opened") == [None, None, None, "step"]
    assert cur("failed-transcribing") == [None] * 4 and cur("idle") == [None] * 4
    assert [r[s][1:] for s in ("listening", "transcribing", "structuring", "ready", "failed-transcribing", "idle")] == [
        ["Listening", "agent-chip listening"], ["Transcribing", "agent-chip working"], ["Structuring", "agent-chip working"],
        ["Ready", "agent-chip ready"], ["Problem", "agent-chip failed"], ["Idle", "agent-chip idle"]]


def test_the_cancel_link_shows_only_while_reading_and_clicks_the_close_button():
    r = _dom('const cancel = E.lhProgress.lastChild; const o = [cancel.hidden];'
             'E.lhPanel.setAttribute("aria-busy", "true"); E.lhProgressText.textContent = "Uploading and reading your letterhead. This can take up to a minute…"; fire(); o.push(cancel.hidden);'
             'E.lhProgressText.textContent = "Saving your letterhead…"; fire(); o.push(cancel.hidden);'
             'E.lhPanel.setAttribute("aria-busy", "false"); E.lhProgressText.textContent = ""; fire(); o.push(cancel.hidden);'
             'E.lhPanel.setAttribute("aria-busy", "true"); E.lhProgressText.textContent = "Uploading and reading your letterhead. x"; fire(); o.push(cancel.hidden);'
             'cancel.click(); console.log(JSON.stringify([o, E.lhCloseBtn.clicks || 0, cancel.className, cancel.id]))')
    assert r[0] == [True, False, True, True, False] and r[1] == 1 and r[2] == "stp-cancel" and r[3] == "lhCancelBtn"


_ACCEPT = "Done. The clinic letterhead is saved, and its clinic details were saved to the Profile. New prescriptions print on it."


def test_letterhead_accept_reads_the_done_box_only_on_the_upload_view_and_not_after_a_failed_later_upload():
    def seq(setup):
        return _dom('E.lhUpload.hidden = false; E.lhReview.hidden = true; ' + setup + ' fire(); console.log(JSON.stringify(D.status("lhSteps")))')
    done_box = 'E.lhDone.hidden = false; E.lhDone.textContent = %s;' % json.dumps(_ACCEPT)
    assert seq(done_box) == ["done"] * 4
    assert seq('E.lhStatus.textContent = %s; E.lhDone.hidden = true;' % json.dumps(_ACCEPT)) == ["now", "todo", "todo", "todo"]      # #lhStatus is not the done box
    assert seq(done_box + 'E.lhUpload.hidden = true;') == ["now", "todo", "todo", "todo"]                                         # accept counts only with the upload view showing
    # accept, then a second upload runs and fails: the old Done is still in the box but an error is showing -> Accept is not done
    assert seq(done_box + 'E.lhError.hidden = false; E.lhError.textContent = "Could not reach the server.";') == ["now", "todo", "todo", "todo"]
    assert seq(done_box + 'E.lhError.hidden = false; fire(); E.lhError.hidden = true;') == ["done"] * 4
    # the error element is watched, so showing it repaints on its own
    assert "lhError" in _dom('console.log(JSON.stringify(D.observed))')


def test_a_missing_steps_js_does_not_stop_page_init():
    app = _code("app.js")
    assert "function setStep(stage, info) { if (window.Steps) Steps.main(stage, info); }" in app
    assert "if (window.Steps) Steps.needs(stepCounts());" in app and app.count("Steps.") == 2


def test_a_microphone_that_cannot_start_marks_listening_as_the_problem_and_step_two_never_reads_empty():
    app = _code("app.js")
    begin = _slice(app, "async function beginRecording", "async function onRecordingStop")
    assert begin.count('setStep("failed-listening", { reason: "Microphone unavailable" })') == 1
    assert begin.count('setStep("failed-listening", { reason: "Recording not supported" })') == 1
    assert begin.index('"Microphone unavailable: "') < begin.index('{ reason: "Microphone unavailable" }') < begin.index('"Recording is not supported in this browser."')
    f = _node('StepsLogic.main("failed-listening", {reason:"Microphone unavailable"}).steps.map((s) => [s.status, s.sub])')
    assert f[0] == ["failed", "Microphone unavailable"] and [s[0] for s in f[1:]] == ["todo"] * 3
    app_live = next(l for l in app.splitlines() if l.startswith("const stepCounts"))       # the live count skips blank rows like the sticky bar
    assert 'rxBody.querySelectorAll("tr[data-index]")' in app_live and "!RxView.isBlank(tr)" in app_live and "needs: openRows().length" in app_live
    assert "(state.structured.rx || []).length" not in app and "const live = rows().filter((tr) => !isBlank(tr));" in _code("rxview.js")
    # a correction that throws before any word count was recorded: step 2 says what is true, not an empty line
    assert _node('StepsLogic.main("failed-structuring", {reason:"x"}).steps.map((s) => s.sub)') == ["", "Transcript ready", "x", ""]
