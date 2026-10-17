"""The Team screen's "Clinic medicines" tab (plan I1-h4): static pins on comment-stripped source, and team.js run in node
against tests/team_medicines_fakedom.js for the behaviour. Offline; no browser."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FAKEDOM = Path(__file__).parent / "team_medicines_fakedom.js"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _code(name):
    """A frontend file without its comments, so a pin cannot be satisfied by a comment."""
    text = re.sub(r"/\*.*?\*/", "", _read(name), flags=re.S)
    return "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in text.splitlines())


def _page(body, **opts):
    """Open team.js in the fake DOM as an admin with the sample medicines and users (opts override); `body` is JS that
    sees `D` (the helper) and `p` (the opened page) and prints one JSON value."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = ("const D = require(process.argv[1]); (async () => { const p = await D.open({role: 'admin', ...D.sample, ...%s}); %s })()"
              ".catch((e) => { console.error(e); process.exit(1); });") % (json.dumps(opts), body)
    out = subprocess.run([node, "-e", script, str(FAKEDOM), str(FRONT / "team.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# --- static ------------------------------------------------------------------------------------------------------

def test_the_tab_is_added_only_after_auth_me_says_admin_and_uses_the_formulary_routes():
    js = _code("team.js")
    assert '"/api/v1/formulary"' in js and 'method: "DELETE"' in js and '"/api/v1/auth/me"' in js
    assert 'return me.role === "admin"' in js.split("async function isAdmin()")[1].split("\n  }")[0]
    gate = js.split("function showMedsTab()")[1].split("\n  }")[0]
    assert "if (!t.admin) return;" in gate
    assert gate.index("if (!t.admin) return;") < gate.index("buildTabs()") < gate.index("buildMeds()")     # built only for an admin
    assert 'role: "tablist"' in js and "Clinic medicines" in js
    assert "buildTabs()" not in js.split("async function showMedsTab()")[0].split("function build()")[1].split("function buildTabs")[0]


def test_the_tab_never_turns_server_text_into_html_or_adds_an_external_host():
    for name in ("team.js", "team.css"):
        code = _code(name)
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", code), name
        assert "http://" not in code and "https://" not in code and "@import" not in code and "url(" not in code, name
    js = _code("team.js")
    assert "Number(m.id)" in js and "m.id + " not in js


def test_removal_asks_first_says_the_removal_is_soft_and_announces_the_result_politely():
    js = _code("team.js")
    remove = js.split("async function removeMed(")[1].split("\n  }")[0]
    assert "window.confirm(" in remove and remove.index("window.confirm(") < remove.index("send(MEDS")
    assert "two new documents" in remove and "two new documents" in js.split("function buildMeds()")[1].split("\n  }")[0]
    assert 'role: "status"' in js.split("function buildMeds()")[1].split("\n  }")[0] and "setLive(" in remove
    assert 'el("teamMedLive").textContent' in js.split("function setLive(")[1].split("\n")[0]
    assert 'el("teamTabMeds").focus()' in remove
    assert "aria-live" not in js and 'make("button", { type: "button", class: "team-med-remove" }, "Remove")' in js


def test_error_text_prefers_error_then_detail_and_never_prints_an_object():
    js = _code("team.js")
    fn = js.split("function errorText(")[1].split("\n  }")[0]
    assert "b.error" in fn and "detail" in fn and "msg" in fn and "JSON.stringify" not in fn and "String(" not in fn


def test_the_medicine_buttons_are_44px_scoped_and_focus_with_the_accent_ring():
    css = re.sub(r"/\*.*?\*/", "", _read("team.css"), flags=re.S)
    selectors = [s.strip() for block in re.findall(r"([^{}]+)\{", css) for s in block.split(",")]
    assert all(s.startswith((".team-panel", "dialog.team-panel", "@media (max-width:520px)")) for s in selectors), selectors
    phone = css.split("@media (max-width:520px)")[1].split("\n}")[0]
    assert phone.count(".team-meds-table") >= 6 and ".team-table " not in phone and "td[data-label]::before" in phone   # this table only
    assert re.search(r"\.team-meds-table, [^{]*td \{ display:block;", phone) and "thead { display:none; }" in phone
    assert re.search(r"\.team-panel \.team-row-actions \.team-med-remove \{[^}]*min-height:44px", css)
    assert re.search(r"\.team-panel button:focus-visible[^{]*\{ outline:3px solid var\(--accent\)", css)
    assert ".team-panel .team-tab-body" in css and ".team-panel .team-live" in css and "animation" not in css


def test_a_long_unbroken_medicine_name_wraps_inside_the_medicines_table_only():
    css = re.sub(r"/\*.*?\*/", "", _read("team.css"), flags=re.S)
    rule = re.search(r"(\.team-panel \.team-meds-table td:first-child) \{([^}]*)\}", css.split("@media")[0])    # before the phone block: all widths
    assert rule, "a top-level (all widths) rule for the name cell of the medicines table"
    assert "overflow-wrap:anywhere" in rule.group(2) and "word-break:break-word" in rule.group(2)


def test_the_phone_layout_has_what_it_needs_from_the_markup():
    r = _page("""await p.openMeds(); const tb = p.ids.teamMedRows;
      console.log(JSON.stringify({cls: tb.parentNode.attrs.class, labels: tb.children[0].children.map((td) => td.attrs['data-label'] || null),
        last: tb.children[0].children[4].attrs.class}))""")
    assert "team-meds-table" in r["cls"].split() and "team-table" in r["cls"].split()
    assert r["labels"] == [None, "Confirmed on", "Last seen", "Added by", None] and r["last"] == "team-row-actions"


def test_the_team_assets_are_cache_busted_to_at_least_2_and_the_script_parses():
    html = _read("index.html")
    for asset in ("team.css", "team.js"):
        version = re.search(re.escape(asset) + r"\?v=(\d+)", html)
        assert version and int(version.group(1)) >= 2, asset
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    assert subprocess.run([node, "--check", str(FRONT / "team.js")], capture_output=True).returncode == 0


# --- behaviour in the fake DOM -----------------------------------------------------------------------------------

def test_a_doctor_and_single_mode_never_get_the_tab_or_call_the_formulary():
    for opts in ({"role": "doctor"}, {"role": None}):
        r = _page("await p.openTeam(); console.log(JSON.stringify({tab: !!p.ids.teamTabMeds, tabs: !!p.ids.teamTabPeople, panel: !!p.ids.teamMeds,"
                  " rows: !!p.ids.teamMedRows, people: !!p.ids.teamPeople, calls: p.calls}))", **opts)
        assert (r["tab"], r["tabs"], r["panel"], r["rows"]) == (False, False, False, False), opts
        assert r["people"] is True                                    # the members screen is as before
        assert not [c for c in r["calls"] if "formulary" in c], r["calls"]


def test_the_add_user_form_and_the_row_actions_are_built_for_admins_only_static():
    js = _code("team.js")
    assert "if (!t.admin) return [];" in js.split("function rowActions(")[1].split("\n  }")[0]
    assert "if (t.admin) people.append(form);" in js and "if (t.admin) el(\"teamAddForm\").addEventListener" in js
    handler = js.split('document.addEventListener("DOMContentLoaded"')[1]
    assert handler.index("t.admin = await isAdmin();") < handler.index("t.dialog = build();")      # decided before the dialog exists
    assert "cell.append(...rowActions(u))" in js and js.count('"Reset password"') == 1       # the buttons are made in rowActions only


def test_a_doctor_sees_the_people_list_read_only_and_an_admin_sees_the_controls():
    users = [{"id": 1, "username": "dr.me", "display_name": "Dr. Me", "is_active": True, "last_login_at": None},
             {"id": 5, "username": "dr.rao", "display_name": "Dr. Rao", "is_active": True, "last_login_at": None},
             {"id": 6, "username": "dr.off", "display_name": "Dr. Off", "is_active": False, "last_login_at": None}]
    body = """await p.openTeam();
      console.log(JSON.stringify({form: !!p.ids.teamAddForm, addBtn: !!p.ids.teamAddBtn, names: p.ids.teamRows.children.map((tr) => tr.children[0].textContent),
        actions: p.ids.teamRows.children.map((tr) => tr.children[4].children.map((b) => b.textContent)), tabs: !!p.ids.teamTabMeds}))"""
    doctor = _page(body, role="doctor", users=users, me=1)
    assert doctor == {"form": False, "addBtn": False, "names": ["Dr. Me (you)", "Dr. Rao", "Dr. Off"], "actions": [[], [], []], "tabs": False}
    admin = _page(body, role="admin", users=users, me=1)
    assert admin["form"] is True and admin["addBtn"] is True and admin["tabs"] is True
    assert admin["actions"] == [[], ["Disable", "Reset password"], ["Enable", "Reset password"]]       # none on your own row


def test_an_admin_sees_the_tab_and_the_list_joins_added_by_against_the_team():
    r = _page("""
      const tabs = p.ids.teamTabMeds.parentNode;
      const before = {hidden: tabs.hidden, role: tabs.attrs.role, selected: p.ids.teamTabPeople.attrs['aria-selected'], medsHidden: p.ids.teamMeds.hidden};
      await p.openMeds();
      console.log(JSON.stringify({before, rows: p.rows(), calls: p.calls, meds: p.ids.teamMeds.hidden, people: p.ids.teamPeople.hidden,
        sel: p.ids.teamTabMeds.attrs['aria-selected'], empty: p.ids.teamMedEmpty.hidden, type: p.ids.teamTabMeds.attrs.type}));""")
    assert r["before"] == {"hidden": False, "role": "tablist", "selected": "true", "medsHidden": True}
    assert r["type"] == "button" and r["sel"] == "true" and (r["meds"], r["people"], r["empty"]) == (False, True, True)
    assert [row[0] for row in r["rows"]] == ["Zorbexin", "Quelvarin", "Mystara"]
    assert [row[3] for row in r["rows"]] == ["Dr. Rao", "Unknown", "Unknown"]     # joined; null and an id not on the team
    assert r["rows"][0][1] == "2 documents" and r["rows"][1][1] == "3 documents"
    assert "GET /api/v1/formulary" in r["calls"] and "GET /api/v1/users" in r["calls"]


def test_added_by_falls_back_to_the_username_and_to_unknown_when_the_team_cannot_be_read():
    users = [{"id": 5, "username": "dr.rao", "display_name": ""}]
    r = _page("await p.openMeds(); console.log(JSON.stringify(p.rows().map((x) => x[3])))", users=users)
    assert r == ["dr.rao", "Unknown", "Unknown"]


def test_the_server_text_is_set_as_text_and_an_empty_list_says_so():
    evil = [{"id": 1, "name": "<img src=x onerror=alert(1)>", "confirm_count": 2, "last_seen_at": None, "added_by": None}]
    r = _page("await p.openMeds(); console.log(JSON.stringify({rows: p.rows(), kids: p.ids.teamMedRows.children[0].children[0].children.length}))", items=evil)
    assert r["rows"][0][0] == "<img src=x onerror=alert(1)>" and r["kids"] == 0 and r["rows"][0][2] == "Never"
    e = _page("await p.openMeds(); console.log(JSON.stringify({empty: p.ids.teamMedEmpty.hidden, rows: p.rows()}))", items=[])
    assert e == {"empty": False, "rows": []}


def test_remove_asks_first_then_deletes_reloads_announces_and_returns_focus():
    r = _page("""
      await p.openMeds();
      p.calls.length = 0;
      const btn = p.removeButton(0);
      await btn.click(); await p.tick();
      console.log(JSON.stringify({calls: p.calls, confirms: p.confirms, label: btn.attrs['aria-label'], text: btn.textContent,
        live: p.ids.teamMedLive.textContent, liveRole: p.ids.teamMedLive.attrs.role, err: p.ids.teamError.hidden,
        focus: document.activeElement === p.removeButton(0) && p.removeButton(0) !== btn, rows: p.rows().length, cls: btn.attrs.class}));""")
    assert r["calls"] == ["DELETE /api/v1/formulary/7", "GET /api/v1/formulary"], r["calls"]
    assert len(r["confirms"]) == 1 and "Zorbexin" in r["confirms"][0] and "two new documents" in r["confirms"][0]
    assert (r["label"], r["text"], r["cls"]) == ("Remove Zorbexin from your clinic's medicines", "Remove", "team-med-remove")
    assert r["liveRole"] == "status" and "Removed Zorbexin" in r["live"] and "two new documents" in r["live"]
    assert r["err"] is True and r["focus"] is True and r["rows"] == 2      # the row is gone; focus moved to the next row's Remove


def test_after_a_removal_focus_goes_to_the_next_row_else_the_previous_row_else_the_tab():
    r = _page("""
      await p.openMeds();
      const out = [];
      const names = () => p.rows().map((x) => x[0]).join(",");
      const focused = () => { const a = document.activeElement; return a === p.ids.teamTabMeds ? "tab" : a.attrs['aria-label']; };
      await p.removeButton(1).click(); await p.tick();                  // middle row: the next row (Mystara) gets focus
      out.push([names(), focused()]);
      await p.removeButton(1).click(); await p.tick();                  // last row: the previous row (Zorbexin)
      out.push([names(), focused()]);
      await p.removeButton(0).click(); await p.tick();                  // only row: the tab button
      out.push([names(), focused()]);
      console.log(JSON.stringify(out));""")
    assert r == [["Zorbexin,Mystara", "Remove Mystara from your clinic's medicines"],
                 ["Zorbexin", "Remove Zorbexin from your clinic's medicines"], ["", "tab"]]


def test_remove_buttons_and_the_dialog_are_busy_while_a_removal_is_pending_and_free_after():
    r = _page("""
      await p.openMeds();
      let release; p.gate.hold = (m) => m === "DELETE" ? new Promise((res) => { release = res; }) : undefined;
      const pending = p.removeButton(0).click(); await p.tick();
      const during = {disabled: p.ids.teamMedRows.children.map((tr) => tr.children[4].children[0].disabled), busy: p.ids.teamPanel.attrs['aria-busy'],
        add: p.ids.teamAddBtn.disabled, tab: p.ids.teamTabMeds.disabled};
      p.gate.hold = null; release(); await pending; await p.tick();
      console.log(JSON.stringify({during, after: {disabled: p.ids.teamMedRows.children.map((tr) => tr.children[4].children[0].disabled), busy: p.ids.teamPanel.attrs['aria-busy'], add: p.ids.teamAddBtn.disabled}}));""")
    assert r["during"] == {"disabled": [True, True, True], "busy": "true", "add": True, "tab": False}
    assert r["after"] == {"disabled": [False, False], "busy": "false", "add": False}


def test_an_older_list_answer_never_draws_over_a_newer_one_and_a_reload_shows_loading():
    r = _page("""
      const q = [];
      p.gate.hold = (m, u) => m === "GET" && u === "/api/v1/formulary" ? new Promise((res) => q.push(res)) : undefined;
      p.ids.teamTabMeds.click(); await p.tick();                         // load 1 is parked
      const loading = {live: p.ids.teamMedLive.textContent, rows: p.rows().length, empty: p.ids.teamMedEmpty.hidden};
      await p.ids.teamTabPeople.click(); p.ids.teamTabMeds.click(); await p.tick();   // load 2 is parked
      q[1]([200, {items: [{id: 2, name: "Newer", confirm_count: 2, last_seen_at: null, added_by: null}]}]); await p.tick();
      q[0]([200, {items: [{id: 1, name: "Older", confirm_count: 2, last_seen_at: null, added_by: null}]}]); await p.tick();
      console.log(JSON.stringify({loading, queued: q.length, rows: p.rows().map((x) => x[0]), live: p.ids.teamMedLive.textContent}));""")
    assert r["loading"] == {"live": "Loading…", "rows": 0, "empty": True}
    assert (r["queued"], r["rows"], r["live"]) == (2, ["Newer"], "")


def test_a_failed_reload_empties_the_table_instead_of_showing_old_rows_as_current():
    r = _page("""
      await p.openMeds();
      const first = p.rows().length;
      p.gate.hold = (m, u) => m === "GET" && u === "/api/v1/formulary" ? [500, {}] : undefined;
      await p.ids.teamTabPeople.click(); await p.openMeds();
      console.log(JSON.stringify({first, rows: p.rows().length, err: p.ids.teamError.textContent, empty: p.ids.teamMedEmpty.hidden, live: p.ids.teamMedLive.textContent}));""")
    assert r == {"first": 3, "rows": 0, "err": "Something went wrong (code 500). Try again.", "empty": True, "live": ""}


def test_a_removal_of_a_medicine_already_gone_says_so_in_plain_words():
    r = _page("""
      await p.openMeds();
      await p.removeButton(0).click(); await p.tick();
      console.log(JSON.stringify(p.ids.teamError.textContent));""", delete=[404, {"error": "no such medicine"}])
    assert r == "That medicine was already removed. The list has been refreshed."


def test_a_declined_confirmation_deletes_nothing_and_says_nothing():
    r = _page("""
      await p.openMeds(); p.calls.length = 0;
      await p.removeButton(1).click(); await p.tick();
      console.log(JSON.stringify({calls: p.calls, confirms: p.confirms.length, live: p.ids.teamMedLive.textContent, rows: p.rows().length}));""",
              answers=[False])
    assert r == {"calls": [], "confirms": 1, "live": "", "rows": 3}


@pytest.mark.parametrize("status,payload,expect", [
    (403, {"error": "You are not allowed to do that"}, "You are not allowed to do that"),
    (404, {"error": "no such medicine"}, "That medicine was already removed. The list has been refreshed."),
    (422, {"detail": "Input should be a valid integer"}, "Input should be a valid integer"),
    (422, {"detail": [{"loc": ["path", "entry_id"], "msg": "Input should be greater than or equal to 1", "type": "x"}]},
     "Input should be greater than or equal to 1"),
    (422, {"detail": {"nested": "object"}}, "Something went wrong (code 422). Try again."),
    (500, {}, "Something went wrong (code 500). Try again."),
    (500, None, "Something went wrong (code 500). Try again."),
    (503, {"error": "try again"}, "The server is busy. Try again in a moment."),
])
def test_a_failed_removal_shows_a_readable_message_reloads_the_list_and_keeps_the_message(status, payload, expect):
    r = _page("""
      await p.openMeds(); p.calls.length = 0;
      await p.removeButton(0).click(); await p.tick();
      console.log(JSON.stringify({calls: p.calls, err: p.ids.teamError.textContent, shown: !p.ids.teamError.hidden, live: p.ids.teamMedLive.textContent,
        rows: p.rows().length, focus: document.activeElement && document.activeElement.attrs.id}));""", delete=[status, payload])
    assert r["calls"] == ["DELETE /api/v1/formulary/7", "GET /api/v1/formulary"], r["calls"]
    assert r["err"] == expect and r["shown"] is True and r["live"] == "" and r["rows"] == 3
    assert "[object" not in r["err"] and "{" not in r["err"] and r["focus"] == "teamTabMeds"


def test_a_failed_list_load_uses_the_same_readable_messages():
    r = _page("await p.openMeds(); console.log(JSON.stringify({err: p.ids.teamError.textContent, rows: p.rows().length, empty: p.ids.teamMedEmpty.hidden}))",
              list=[422, {"detail": [{"msg": "Bad thing"}]}])
    assert r == {"err": "Bad thing", "rows": 0, "empty": True}       # a failed load is not "nothing learned"


def test_the_tabs_switch_panels_clear_the_error_and_reopening_starts_on_people():
    r = _page("""
      await p.openMeds();
      await p.ids.teamTabPeople.click(); await p.tick();
      const people = {meds: p.ids.teamMeds.hidden, people: p.ids.teamPeople.hidden, sel: p.ids.teamTabPeople.attrs['aria-selected']};
      await p.openMeds();
      await p.ids.teamPanel.close(); await p.openTeam();
      console.log(JSON.stringify({people, again: {meds: p.ids.teamMeds.hidden, people: p.ids.teamPeople.hidden}}));""")
    assert r["people"] == {"meds": True, "people": False, "sel": "true"}
    assert r["again"] == {"meds": True, "people": False}
