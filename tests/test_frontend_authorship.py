"""Static checks for the M3 browser wiring (view-only sheet, Today toggle, Profile split). No browser needed;
the manual checklist in the M3 plan covers behaviour."""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def test_authorship_js_loads_after_auth_js_and_before_app_js():
    html = _read("index.html")
    assert html.index("auth.js") < html.index("authorship.js") < html.index("app.js")


def test_index_has_the_banner_and_the_today_toggle():
    html = _read("index.html")
    assert 'id="viewOnlyBanner"' in html and html.index('id="viewOnlyBanner"') < html.index('id="sheet"')
    toggle = html.split('id="todayScope"')[1].split("</div>")[0]
    assert "hidden" in html.split('id="todayScope"')[1].split(">")[0]          # shown only once signed in
    assert 'data-scope="mine"' in toggle and "My prescriptions" in toggle
    assert 'data-scope="clinic"' in toggle and "Whole clinic" in toggle


def test_profile_dialog_is_split_into_clinic_details_and_my_details():
    html = _read("index.html")
    clinic = html.split('id="profClinicPart"')[1].split("</fieldset>")[0]
    mine = html.split('id="profMinePart"')[1].split("</fieldset>")[0]
    assert "Clinic details" in clinic and all(f'id="{i}"' in clinic for i in ("profClinic", "profAddress", "profPhone"))
    assert "My details" in mine and all(f'id="{i}"' in mine for i in ("profDoctor", "profQual", "profReg"))


def test_authorship_js_shows_the_banner_and_locks_the_sheet():
    js = _read("authorship.js")
    assert "'s prescription: view only" in js
    for needle in ('"recBtn"', '"saveBtn"', "contentEditable", "can_edit === false", "?scope=", "/api/v1/auth/me"):
        assert needle in js, needle
    assert re.search(r"return \{[^}]*onOpen[^}]*clear[^}]*enforce[^}]*isViewOnly[^}]*todayQuery[^}]*authorLabel", js)


def test_app_js_calls_authorship_only_through_a_guard():
    js = _read("app.js")
    calls = re.findall(r"Authorship\.(\w+)\(", js)
    assert sorted(set(calls)) == ["authorLabel", "clear", "enforce", "isViewOnly", "keepsOwnHeader", "onOpen", "todayQuery", "viewOnlyAuthor"]
    for line in (ln for ln in js.splitlines() if "Authorship." in ln):
        assert "window.Authorship" in line, line


def test_a_correction_names_the_document_it_corrects():
    js = _read("app.js")
    assert re.search(r'postJson\("/api/v1/correct", \{[^}]*document_id: state\.documentId', js)


def _function(js, name):
    """A top-level function (app.js) or the two-space-indented one inside authorship.js's closure."""
    start = js.index(f"function {name}(")
    indent = "  " if js[start - 2:start] == "  " else ""
    return js[start:js.index(f"\n{indent}}}\n", start)]


def test_profile_header_leaves_the_authors_doctor_lines_alone_while_view_only():
    body = _function(_read("app.js"), "renderProfileHeader")
    guard = body.index("Authorship.isViewOnly()")
    assert "window.Authorship" in body[:guard].splitlines()[-1] or "window.Authorship" in body[body.rindex("\n", 0, guard):guard]
    assert guard < body.index('setText($("cDoctor")') and guard < body.index('setText($("cReg")')


def test_set_working_ends_by_enforcing_view_only():
    body = _function(_read("app.js"), "setWorking")
    tail = body.rstrip().splitlines()
    assert "Authorship.enforce()" in tail[-1] and "window.Authorship" in tail[-1]
    assert body.index(".x-btn, #undoBtn") < body.index("Authorship.enforce()")      # after the x-btn re-enable


def test_a_late_today_response_cannot_render_over_a_newer_one():
    body = _function(_read("app.js"), "loadToday")
    assert "++todaySeq" in body
    assert body.index("await safeJson(r)") < body.index("!== todaySeq") < body.index("renderToday(")


def test_clear_only_touches_the_sheet_buttons_when_leaving_view_only():
    body = _function(_read("authorship.js"), "clear")
    guard = body.index("if (was) {")
    assert 'querySelectorAll(".x-btn")' in body[guard:] and "b.disabled = busy()" in body[guard:]
    assert re.search(r'querySelectorAll\("\.confirm-btn"\)\.forEach\(\(b\) => \{ b\.disabled = false;', body[guard:])
    assert ".confirm-btn" not in body[:guard]                      # single mode: nothing assigned from busy()
    assert not re.search(r"confirm-btn[^\n]*busy\(\)", body)       # setWorking(false) never re-enables them


def test_an_opened_prescription_keeps_its_own_header_lines_until_cleared():
    js = _read("authorship.js")
    assert "ownHeader = true" in _function(js, "onOpen") and "ownHeader = false" in _function(js, "clear")
    assert js.index("ownHeader = true") > js.index("if (!a) return")   # single mode sends no author: live profile header
    body = _function(_read("app.js"), "renderProfileHeader")
    assert "Authorship.keepsOwnHeader()" in body and body.index("keepsOwnHeader") < body.index('setText($("cDoctor")')


def test_the_profile_dialog_focuses_the_first_field_of_the_clinic_fieldset():
    body = _function(_read("app.js"), "openProfilePanel")
    assert '$("profClinic") || $("profDoctor")' in body


def test_a_view_only_sheet_says_so_in_the_status_and_the_mic_label():
    app, js = _read("app.js"), _read("authorship.js")
    assert "You can print it, not edit it." in app and "Authorship.viewOnlyAuthor()" in app
    assert '"Dictation off"' in app and "Authorship.isViewOnly()" in app.split("function refreshMicLabel")[1][:400]
    assert "function viewOnlyAuthor()" in js and "viewOnlyAuthor" in js.split("return {")[-1]


def test_the_top_bar_keeps_the_signed_in_users_own_name():
    app, auth = _read("app.js"), _read("auth.js")
    assert "window.DDUser = me;" in auth
    assert 'setText($("topDoctor"), (window.DDUser && window.DDUser.display_name) || p.doctor_name' in app
    html = _read("index.html")
    assert all(v in html for v in ("auth.js?v=2", "authorship.js?v=2", "app.js?v=21"))
