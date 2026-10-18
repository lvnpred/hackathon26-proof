"""The doctors grid in the forms: static wiring checks (no browser). The round trips run in node by hand."""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parent.parent / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def test_the_grid_component_is_dom_safe_and_bounded():
    js = _read("doctorgrid.js")
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js
    for token in ("function parse(", "function serialise(", "function refresh(", "function mount(", "const MAX = 12",
                  '"Remove Doctor "', "+ Add doctor", 'setAttribute("for", fid)', 'new Event("input"', "replace(/;/g, \",\")"):
        assert token in js, token
    assert "return { parse, serialise, mount, refresh, MAX }" in js


def test_the_profile_form_keeps_the_hidden_sources_and_mounts_the_grid():
    html, app = _read("index.html"), _read("app.js")
    for i in ("profDoctor", "profQual", "profReg"):
        assert f'<input id="{i}" type="hidden" />' in html
    assert 'id="profDoctorGrid"' in html and html.index("profClinicPart") < html.index("profMinePart") < html.index("profDoctorGrid")
    body = app.split("function fillProfileForm(")[1].split("\n}\n")[0]
    assert 'typeof DoctorGrid !== "undefined"' in body and 'DoctorGrid.refresh("profDoctorGrid")' in body
    assert 'doctor_name: inputVal("profDoctor")' in app                         # the request body is unchanged
    assert html.index("doctorgrid.js?v=1") < html.index("app.js?v=")


def test_the_review_screen_shows_clinic_details_then_the_doctors_grid_and_sends_joined_strings():
    html, js = _read("index.html"), _read("letterhead.js")
    assert html.index("<h3>Clinic details</h3>") < html.index('id="lhProfileFields"') < html.index("<h3>Doctors</h3>") < html.index('id="lhDoctorGrid"')
    assert "DoctorGrid.mount(grid, hidden)" in js and 'h.type = "hidden"; h.id = "lhProf_" + k' in js
    assert 'PROFILE_KEYS.forEach((k) => { profile[k] = el("lhProf_" + k).value.trim(); });' in js     # collector unchanged


def test_the_grid_is_two_columns_and_one_on_narrow_containers():
    css = _read("styles.css")
    assert "grid-template-columns:1fr 1fr" in css and "@container (max-width:420px)" in css and "@media (max-width:420px)" in css
    html = _read("index.html")
    assert all(v in html for v in ("letterhead.css?v=8", "letterhead.js?v=11", "doctorgrid.js?v=1"))
    assert int(re.search(r"styles\.css\?v=(\d+)", html).group(1)) >= 9
