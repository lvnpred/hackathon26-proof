"""The Team page's "Corrected mishearings" section (frontend/mishear.js, plan SH-H2 Task 5): static pins, and the section
runs in node against tests/team_medicines_fakedom.js. Offline; no browser."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FAKEDOM = Path(__file__).parent / "team_medicines_fakedom.js"


def _code(name):
    text = re.sub(r"/\*.*?\*/", "", (FRONT / name).read_text(encoding="utf-8"), flags=re.S)
    return "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in text.splitlines())


def _page(body, **opts):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = ("const D = require(process.argv[1]); (async () => { const p = await D.open({role: 'admin', ...%s}); %s })()"
              ".catch((e) => { console.error(e); process.exit(1); });") % (json.dumps(opts), body)
    out = subprocess.run([node, "-e", script, str(FAKEDOM), str(FRONT / "team.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


PAIRS = [{"id": 4, "spoken": "Dolo", "heard": "dollo", "confirm_count": 3, "doctor_id": 5, "doctor": "Dr. Rao"},
         {"id": 6, "spoken": "Pan", "heard": "fan", "confirm_count": 2, "doctor_id": 6, "doctor": "Dr. Mehta"}]
ROWS = "p.ids.teamMishearRows.children.map((tr) => tr.children.map((td) => td.textContent))"
FIRST = "p.ids.teamMishearRows.children[0].children[4].children[0]"


def test_mishear_is_plain_text_loads_between_clinlists_and_team_and_parses():
    js, html = _code("mishear.js"), (FRONT / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", js) and '"/api/v1/spoken/mishearings"' in js
    assert 'class: "team-table team-meds-table"' in js                      # the phone rules in team.css key off this class
    assert "medicine name is put first in the speech hints" in js and "is no longer put first in this doctor's speech hints." in js
    assert "mishear.js?v=2" in html and "team.js?v=7" in html
    assert html.index("clinlists.js?v=") < html.index("mishear.js?v=") < html.index("team.js?v=")
    if shutil.which("node"):
        assert subprocess.run([shutil.which("node"), "--check", str(FRONT / "mishear.js")], capture_output=True).returncode == 0


def test_an_admin_sees_the_pairs_in_the_medicines_tab_as_text():
    r = _page("await p.openMeds(); console.log(JSON.stringify({t: p.ids.teamMishearTitle.textContent, inMeds: p.ids.teamMishear.parentNode"
              " === p.ids.teamMeds, rows: %s, empty: p.ids.teamMishearEmpty.hidden, calls: p.calls}))" % ROWS, mishearings=PAIRS)
    assert (r["t"], r["inMeds"], r["empty"]) == ("Corrected mishearings", True, True)
    assert r["rows"] == [["dollo", "Dolo", "Dr. Rao", "3", "Remove"], ["fan", "Pan", "Dr. Mehta", "2", "Remove"]]
    assert "GET /api/v1/spoken/mishearings" in r["calls"]
    e = _page("await p.openMeds(); console.log(JSON.stringify({rows: %s, kids: p.ids.teamMishearRows.children[0].children[0].children.length}))"
              % ROWS, mishearings=[dict(PAIRS[0], heard="<img src=x onerror=alert(1)>")])
    assert e["rows"][0][0] == "<img src=x onerror=alert(1)>" and e["kids"] == 0
    n = _page("await p.openMeds(); console.log(JSON.stringify({rows: %s, empty: p.ids.teamMishearEmpty.hidden}))" % ROWS)
    assert n == {"rows": [], "empty": False}


def test_remove_asks_deletes_reloads_announces_and_a_decline_does_nothing():
    body = ("await p.openMeds(); p.calls.length = 0; const b = %s; const label = b.attrs['aria-label']; await b.click(); await p.tick();"
            " console.log(JSON.stringify({calls: p.calls, confirm: p.confirms[0] || '', label, live: p.ids.teamMishearLive.textContent,"
            " rows: p.ids.teamMishearRows.children.length, focus: (document.activeElement && document.activeElement.attrs.class) || ''}))" % FIRST)
    r = _page(body, mishearings=PAIRS)
    assert r["calls"] == ["DELETE /api/v1/spoken/mishearings/4", "GET /api/v1/spoken/mishearings"]
    assert '"dollo" to Dolo' in r["confirm"] and "two new documents" in r["confirm"]
    assert (r["label"], r["live"]) == ('Remove the pair "dollo" to Dolo', 'Removed the pair "dollo" to Dolo.')
    assert (r["rows"], r["focus"]) == (1, "team-mishear-remove")
    no = _page(body, mishearings=PAIRS, answers=[False])
    assert (no["calls"], no["live"], no["rows"]) == ([], "", 2)


def test_a_gone_pair_says_so_and_a_doctor_page_has_no_section():
    r = _page("await p.openMeds(); await %s.click(); await p.tick(); console.log(JSON.stringify(p.ids.teamError.textContent))" % FIRST,
              mishearings=PAIRS, mishearDelete=[404, {"error": "no such mishearing"}])
    assert r == "That pair was already removed. The list has been refreshed."
    d = _page("await p.openTeam(); console.log(JSON.stringify({sec: !!p.ids.teamMishear, calls: p.calls}))", role="doctor")
    assert d["sec"] is False and not [c for c in d["calls"] if "spoken" in c]


def test_a_second_click_while_the_delete_is_on_its_way_does_nothing():
    body = ("await p.openMeds(); p.calls.length = 0; let release; p.gate.hold = (m) => m === 'DELETE' ? new Promise((r) => { release = () => r(null); }) : null;"
            " const b = %s; const c1 = b.click(); await p.tick(); const dis = b.disabled; await b.click(); release(); await c1; await p.tick();"
            " console.log(JSON.stringify({calls: p.calls, confirms: p.confirms.length, dis}))" % FIRST)
    r = _page(body, mishearings=PAIRS)
    assert r["calls"] == ["DELETE /api/v1/spoken/mishearings/4", "GET /api/v1/spoken/mishearings"]
    assert (r["confirms"], r["dis"]) == (1, True)
