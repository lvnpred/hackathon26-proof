"""The Team page's Medicines and Investigations tabs (frontend/clinlists.js, plan PQ-f Task 7): static pins, and the
tabs run in node against tests/team_medicines_fakedom.js. Offline; no browser."""
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


def _item(key, badge="shipped", generic="", brands=(), flag="", pending=None, fid=None, base=False, **entry):
    return {"entry_key": key, "badge": badge, "flag": flag, "entry": {"canonical": generic or key, "brands": list(brands), **entry},
            "shipped": {"canonical": key} if base else None, "base_sha_now": "", "formulary_id": fid, "pending": pending}


MEDS = [
    _item("amoxicillin", flag="shipped-changed", badge="clinic-edited", brands=["Mox"]),
    _item("metformin", brands=["Glycomet"]),
    _item("paracetamol", badge="clinic-added", brands=["Crocin"]),
    _item("zorbexin", badge="learned", generic="", brands=["Zorbexin"], fid=7),
    _item("cetirizine", brands=["Cetzine"], pending={"count": 1, "threshold": 2, "action": "edit", "data": {"generic": "levocetirizine"}}),
]


def _page(body, **opts):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = ("const D = require(process.argv[1]); (async () => { const p = await D.open({role: 'admin', ...%s}); %s })()"
              ".catch((e) => { console.error(e); process.exit(1); });") % (json.dumps(opts), body)
    out = subprocess.run([node, "-e", script, str(FAKEDOM), str(FRONT / "team.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_clinlists_is_plain_text_only_and_uses_the_lists_route():
    js = _code("clinlists.js")
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", js)
    assert "http://" not in js and "https://" not in js
    assert '"/api/v1/lists/"' in js


def test_index_loads_clinlists_before_team_and_bumps_the_versions():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert "clinlists.js?v=4" in html and "listedit.js?v=1" in html and "team.js?v=7" in html and "team.css?v=6" in html
    assert html.index("listedit.js?v=") < html.index("clinlists.js?v=") < html.index("team.js?v=")


def test_a_doctor_page_has_no_list_tabs():
    r = _page("await p.openTeam(); console.log(JSON.stringify({m: !!p.ids.teamTabMeds, t: !!p.ids.teamTabTests, tp: !!p.ids.teamTests, calls: p.calls}))", role="doctor")
    assert (r["m"], r["t"], r["tp"]) == (False, False, False)
    assert not [c for c in r["calls"] if "lists" in c]


def test_admin_sees_three_tabs_and_medicines_lists_badges():
    r = _page("""
      const labels = p.ids.teamTabPeople.parentNode.children.map((b) => b.textContent);
      await p.openMeds();
      console.log(JSON.stringify({labels, rows: p.rows(), cols: p.ids.teamMedHead.querySelectorAll("th").map((th) => th.textContent)}));""",
              lists={"medicine": MEDS})
    assert r["labels"] == ["People", "Medicines", "Investigations"]
    assert r["cols"] == ["Medicine", "Generic", "Brands", "Source", "Actions"]
    sources = {row[0]: row[3] for row in r["rows"]}
    assert sources["metformin"] == "Shared" and "Added by clinic" in sources["paracetamol"] and "Learned" in sources["Zorbexin"]   # a short tag (UI-A Task 4)
    assert "Edited by clinic" in sources["amoxicillin"]


def test_flagged_rows_come_first_with_their_text():
    flagged = [_item("a", badge="clinic-edited", flag="shipped-changed"), _item("b", flag="safety-override"), _item("c")]
    r = _page("await p.openMeds(); console.log(JSON.stringify(p.rows()))", lists={"medicine": flagged})
    assert "Updated in the shared list" in r[0][3] and "Safety entry: the shared list is used" in r[1][3]
    assert [row[0] for row in r] == ["a", "b", "c"]            # the server sorts; the page keeps its order


def test_an_inert_row_shows_why_under_its_flag():
    inert = dict(_item("crocinol", badge="clinic-added", flag="shipped-changed"),
                 flag_reason="'Crocin' is a brand of Paracetamol \u2014 choose the generic")
    r = _page("await p.openMeds(); console.log(JSON.stringify(p.rows()))", lists={"medicine": [inert, _item("c")]})
    assert "Updated in the shared list" in r[0][3] and "'Crocin' is a brand of Paracetamol" in r[0][3]
    assert "Keep mine" in r[0][4] and "Take new" in r[0][4]


def test_pending_row_shows_pending_1_of_2():
    r = _page("await p.openMeds(); console.log(JSON.stringify(p.rows()))", lists={"medicine": MEDS})
    cet = next(row for row in r if row[0] == "cetirizine")
    assert "Pending (1 of 2)" in cet[3] and "levocetirizine" in cet[3]


def test_filter_narrows_rows_without_a_new_request():
    r = _page("""
      await p.openMeds(); const calls = p.calls.length;
      await p.type("teamMedFilter", "glyco");
      const text = p.rows().map((x) => x[0]);
      await p.type("teamMedFilter", "");
      await p.ids.teamMedChipClinic.click();                  // the "Clinic changes" chip replaced the "Only changed or flagged" checkbox
      console.log(JSON.stringify({calls, after: p.calls.length, text, only: p.rows().map((x) => x[0])}));""", lists={"medicine": MEDS})
    assert r["calls"] == r["after"] and r["text"] == ["metformin"]
    assert sorted(r["only"]) == ["Zorbexin", "amoxicillin", "cetirizine", "paracetamol"]      # pending rows stay; plain shared ones go


def test_investigations_tab_lists_its_columns_and_an_empty_list_says_so():
    tests = [_item("cbc", generic="CBC", print="Complete blood count", category="Blood")]
    r = _page("""
      await p.openTests();
      console.log(JSON.stringify({rows: p.testRows(), cols: p.ids.teamTests.querySelectorAll("th").map((th) => th.textContent), empty: p.ids.teamTestEmpty.hidden,
        calls: p.calls.filter((c) => c.includes("lists"))}));""", lists={"investigation": tests})
    assert r["cols"] == ["Test", "Print", "Category", "Source", "Actions"] and r["rows"][0][:3] == ["CBC", "Complete blood count", "Blood"]
    assert r["calls"] == ["GET /api/v1/lists/investigation"] and r["empty"] is True
    e = _page("await p.openTests(); console.log(JSON.stringify({rows: p.testRows(), empty: p.ids.teamTestEmpty.hidden}))")
    assert e == {"rows": [], "empty": False}


def test_learned_row_remove_keeps_todays_wording_and_focus():
    r = _page("""
      await p.openMeds(); p.calls.length = 0;
      const btn = p.removeButton(0);
      await btn.click(); await p.tick();
      console.log(JSON.stringify({calls: p.calls, confirm: p.confirms[0], label: btn.attrs["aria-label"], live: p.ids.teamMedLive.textContent,
        focus: document.activeElement === p.ids.teamTabMeds}));""", items=[{"id": 7, "name": "Zorbexin", "generic": ""}])   # the fake server drops a deleted name from the list
    assert r["calls"] == ["DELETE /api/v1/formulary/7", "GET /api/v1/lists/medicine"]
    assert "Zorbexin" in r["confirm"] and "two new documents" in r["confirm"]
    assert r["label"] == "Remove Zorbexin from your clinic's medicines" and "Removed Zorbexin" in r["live"]
    assert r["focus"] is True                                           # the list is now empty: the tab gets focus


# --- row actions and the edit dialog (plan PQ-f Task 8) ---------------------------------------------------------------

ACARBOSE = _item("acarbose", brands=["Glucobay"], base=True)
LIST_MEDS = [
    ACARBOSE,                                                                                          # 0 shipped
    _item("crocin", badge="clinic-added", generic="paracetamol", brands=["Crocin", "Calpol"]),         # 1 clinic-added
    _item("metformin", badge="clinic-edited", brands=["Glycomet"], base=True),                        # 2 clinic-edited
    _item("ramipril", badge="hidden"),                                                                 # 3 hidden
    _item("zorbexin", badge="learned", generic="zorexin", brands=["Zorbexin"], fid=7),                 # 4 learned
    _item("amoxicillin", badge="clinic-edited", flag="shipped-changed", brands=["Mox"], base=True),  # 5 shipped-changed
    _item("warfarin", badge="clinic-added", flag="safety-override"),                                   # 6 safety-override
    _item("cetirizine", brands=["Cetzine"], base=True, pending={"count": 1, "threshold": 2, "action": "edit", "data": {"generic": "levocetirizine"}}),   # 7 pending on a shared entry
    _item("zerodol-p", badge="learned", generic="aceclofenac", brands=["Zerodol-P"], pending={"count": 1, "threshold": 2, "action": "add", "data": {"name": "Zerodol-P", "generic": "aceclofenac"}}),  # 8 pending-only
]
EXPECT = [
    ["Edit", "Hide"], ["Edit", "Reset to default"], ["Edit", "Reset to default"], ["Reset to default"], ["Edit", "Remove"],
    ["Edit", "Reset to default", "Keep mine", "Take new"], ["Edit", "Reset to default"],
    ["Approve now", "Edit", "Hide"], ["Approve now", "Edit", "Reset to default"],
]


def test_row_actions_by_state():
    r = _page("await p.openMeds(); console.log(JSON.stringify(LIST.map((_x, i) => p.labels('teamMedRows', i))))".replace("LIST", "Array.from({length: 9})"),
              lists={"medicine": LIST_MEDS})
    assert r == EXPECT
    assert [x for x in r if "Keep mine" in x or "Take new" in x] == [EXPECT[5]]            # only the flagged row
    assert [x for x in r if "Approve now" in x] == EXPECT[7:]                              # only pending rows


def _act(label, row, **opts):
    body = """await p.openMeds(); p.calls.length = 0; await p.press('teamMedRows', %d, %s);
      console.log(JSON.stringify({posts: p.posts, calls: p.calls, confirms: p.confirms, live: p.ids.teamMedLive.textContent, err: p.ids.teamError.textContent}))""" % (row, json.dumps(label))
    return _page(body, lists={"medicine": LIST_MEDS}, **opts)


def test_hide_posts_the_exact_body_after_a_confirm_then_reloads_and_announces():
    r = _act("Hide", 0)
    assert r["posts"] == [{"op": "hide", "entry_key": "acarbose", "data": {}}]
    assert len(r["confirms"]) == 1 and "Hide acarbose" in r["confirms"][0] and "Reset to default" in r["confirms"][0]
    assert r["calls"] == ["POST /api/v1/lists/medicine/changes", "GET /api/v1/lists/medicine"] and r["live"] == "Hidden acarbose."


def test_declining_the_confirm_posts_nothing():
    r = _act("Hide", 0, answers=[False])
    assert r["posts"] == [] and r["calls"] == [] and len(r["confirms"]) == 1


def test_reset_asks_first_and_posts_reset():
    r = _act("Reset to default", 3)
    assert r["posts"] == [{"op": "reset", "entry_key": "ramipril", "data": {}}] and "Reset ramipril" in r["confirms"][0]
    shared = _act("Reset to default", 2)["confirms"][0]
    own = _act("Reset to default", 1)["confirms"][0]
    assert "shared list" in shared and "not on the shared list" in own


def test_keep_mine_and_take_new_post_their_ops_without_a_confirm():
    keep, take = _act("Keep mine", 5), _act("Take new", 5)
    assert keep["posts"] == [{"op": "keep-mine", "entry_key": "amoxicillin", "data": {}}] and keep["confirms"] == []
    assert take["posts"] == [{"op": "take-new", "entry_key": "amoxicillin", "data": {}}] and take["confirms"] == []


def test_approve_now_posts_approve_with_no_confirm_and_announces():
    r = _act("Approve now", 8)
    assert r["posts"] == [{"op": "approve", "entry_key": "zerodol-p", "data": {}}] and r["confirms"] == []
    assert r["live"] == "Approved Zerodol-P."


def test_a_server_refusal_shows_its_text_and_reloads():
    r = _act("Hide", 0, change=[409, {"error": "This is your own addition — use Reset to remove it"}])
    assert "use Reset" in r["err"] and r["calls"][-1] == "GET /api/v1/lists/medicine" and r["live"] == ""


def test_edit_a_shared_medicine_sends_edit_without_a_name_and_cancel_sends_nothing():
    r = _page("""
      await p.openMeds(); await p.press('teamMedRows', 0, 'Edit');
      const f = {name: p.ids.listEditName.value, nameRO: p.ids.listEditName.attrs.readonly, open: p.ids.listEditDialog.open, safety: !!p.ids.listEditSafety};
      await p.fill({listEditGeneric: "acarbose", listEditAliases: "a, b ,", listEditBrands: "Glucobay, Precose"});
      await p.press('teamMedRows', 0, 'Edit'); await p.ids.listEditCancel.click(); await p.tick();
      console.log(JSON.stringify({f, posts: p.posts, live: p.ids.teamMedLive.textContent}))""", lists={"medicine": LIST_MEDS})
    assert r["f"] == {"name": "acarbose", "nameRO": "readonly", "open": True, "safety": False}
    assert r["posts"] == [{"op": "edit", "entry_key": "acarbose", "data": {"generic": "acarbose", "aliases": ["a", "b"], "brands": ["Glucobay", "Precose"]}}]
    assert r["live"] == "Saved acarbose."


def test_a_learned_rows_edit_posts_add_with_its_name_and_typed_generic():
    r = _page("""
      await p.openMeds(); await p.press('teamMedRows', 4, 'Edit');
      const start = {name: p.ids.listEditName.value, generic: p.ids.listEditGeneric.value};
      await p.fill({listEditGeneric: "zorexin hcl"});
      console.log(JSON.stringify({start, posts: p.posts}))""", lists={"medicine": LIST_MEDS})
    assert r["start"] == {"name": "Zorbexin", "generic": "zorexin"}
    assert r["posts"] == [{"op": "add", "entry_key": "zorbexin", "data": {"name": "Zorbexin", "generic": "zorexin hcl", "aliases": [], "brands": []}}]


def test_editing_a_pending_row_prefills_the_doctors_value_and_a_clinic_added_row_keeps_its_name():
    r = _page("""
      await p.openMeds(); await p.press('teamMedRows', 7, 'Edit');
      const pend = p.ids.listEditGeneric.value; await p.ids.listEditCancel.click();
      await p.press('teamMedRows', 1, 'Edit'); const own = {name: p.ids.listEditName.value, brands: p.ids.listEditBrands.value};
      await p.fill({}); console.log(JSON.stringify({pend, own, posts: p.posts}))""", lists={"medicine": LIST_MEDS})
    assert r["pend"] == "levocetirizine" and r["own"] == {"name": "Crocin", "brands": "Calpol"}
    assert r["posts"][0]["op"] == "edit" and r["posts"][0]["entry_key"] == "crocin" and r["posts"][0]["data"]["name"] == "Crocin"


def test_add_a_medicine_and_add_a_test_post_op_add():
    r = _page("""
      await p.openMeds(); const labels = [p.ids.teamMedAdd.textContent];
      p.ids.teamMedAdd.click(); await p.tick();
      const title = p.ids.listEditTitle.textContent;
      await p.fill({listEditName: "Dolo  650", listEditGeneric: "Paracetamol", listEditBrands: "Dolo"});
      await p.openTests(); labels.push(p.ids.teamTestAdd.textContent);
      p.ids.teamTestAdd.click(); await p.tick();
      const fields = p.ids.listEditDialog.querySelectorAll("label").map((l) => l.textContent);
      await p.fill({listEditName: "CBC", listEditCategory: "Blood", listEditPrint: "Complete blood count"});
      console.log(JSON.stringify({labels, title, fields, posts: p.posts, live: p.ids.teamTestLive.textContent}))""")
    assert r["labels"] == ["Add a medicine", "Add a test"] and r["title"] == "Add a medicine"
    assert [f.split(" (")[0] for f in r["fields"]] == ["Name", "Aliases", "Category", "Print"]
    assert r["posts"][0] == {"op": "add", "entry_key": "dolo 650", "data": {"name": "Dolo 650", "generic": "Paracetamol", "aliases": [], "brands": ["Dolo"]}}
    assert r["posts"][1] == {"op": "add", "entry_key": "cbc", "data": {"name": "CBC", "aliases": [], "category": "Blood", "print": "Complete blood count"}}
    assert r["live"] == "Added CBC."


def test_the_filter_renders_once_per_keystroke():
    js = _code("clinlists.js")
    assert js.count('addEventListener("input"') == 1 and js.count('addEventListener("change"') == 0    # chips are buttons (click)


def test_listedit_is_text_only_exports_open_and_the_owner_gets_the_safety_box():
    js = _code("listedit.js")
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", js)
    assert "window.ListEdit = { open }" in js and "http://" not in js and "https://" not in js
    r = _page("""
      await p.openMeds();
      const open = window.ListEdit.open('medicine', null, {owner: true});
      p.ids.listEditName.value = 'Zebrol'; p.ids.listEditGeneric.value = 'zebrolide'; p.ids.listEditSafety.checked = true;
      await p.ids.listEditDialog.querySelectorAll('form')[0].fire('submit');
      const c = window.ListEdit.open('medicine', null, {}); const none = !p.ids.listEditSafety; await p.ids.listEditCancel.click();
      console.log(JSON.stringify({res: await open, cancelled: await c, none}))""")
    assert r["res"]["data"]["safety"] is True and r["res"]["op"] == "add" and r["cancelled"] is None and r["none"] is True


def test_an_empty_generic_is_refused_in_the_dialog_which_stays_open_with_its_values():
    r = _page("""
      await p.openMeds(); p.ids.teamMedAdd.click(); await p.tick();
      await p.fill({listEditName: "Dolo 650", listEditGeneric: "  ", listEditBrands: "Dolo"});
      const d = p.ids.listEditDialog;
      console.log(JSON.stringify({posts: p.posts, open: d.open, err: p.ids.listEditError.textContent, hidden: p.ids.listEditError.hidden,
        brands: p.ids.listEditBrands.value, name: p.ids.listEditName.value}))""")
    assert r == {"posts": [], "open": True, "err": "Enter the generic name.", "hidden": False, "brands": "Dolo", "name": "Dolo 650"}


def test_two_clicks_on_approve_send_one_post_and_a_failure_re_enables_the_row():
    r = _page("""
      await p.openMeds();
      const btn = p.ids.teamMedRows.children[8].children.slice(-1)[0].children.find((b) => b.textContent === "Approve now");
      btn.click(); btn.click(); await p.tick(); await p.tick();
      console.log(JSON.stringify({posts: p.posts.length}))""", lists={"medicine": LIST_MEDS})
    assert r == {"posts": 1}
    f = _page("""
      await p.openMeds();
      const btn = p.ids.teamMedRows.children[8].children.slice(-1)[0].children.find((b) => b.textContent === "Approve now");
      p.gate.hold = async (m, u) => (m === "POST" ? [409, {error: "no"}] : null);
      btn.click(); await p.tick();
      console.log(JSON.stringify({off: btn.disabled}))""", lists={"medicine": LIST_MEDS})
    assert f == {"off": False}


# --- light polish (plan UI-A Task 4) -----------------------------------------------------------------------------------

def _css():
    return re.sub(r"/\*.*?\*/", "", (FRONT / "team.css").read_text(encoding="utf-8"), flags=re.S)


def test_the_search_is_labelled_and_a_count_says_showing_n_of_m():
    r = _page("""
      await p.openMeds(); const s = p.ids.teamMedFilter;
      const start = p.ids.teamMedCount.textContent;
      await p.type("teamMedFilter", "glyco");
      console.log(JSON.stringify({label: s.attrs["aria-label"], ph: s.attrs.placeholder, start, typed: p.ids.teamMedCount.textContent,
        role: p.ids.teamMedCount.attrs.role, tph: p.ids.teamTestFilter.attrs.placeholder, tlabel: p.ids.teamTestFilter.attrs["aria-label"]}))""",
              lists={"medicine": MEDS})
    assert r["label"] == "Search medicines" and r["ph"] == "Search name, generic or brand"
    assert r["tlabel"] == "Search investigations" and r["tph"]
    assert (r["start"], r["typed"], r["role"]) == ("Showing 5 of 5", "Showing 1 of 5", "status")


def test_filter_chips_show_counts_filter_the_rows_and_say_which_is_pressed():
    r = _page("""
      await p.openMeds(); const calls = p.calls.length;
      const ids = ["teamMedChipAll", "teamMedChipClinic", "teamMedChipLearned", "teamMedChipHidden"];
      const state = () => ids.map((i) => p.ids[i].attrs["aria-pressed"]);
      const out = {labels: ids.map((i) => p.ids[i].textContent), types: ids.map((i) => p.ids[i].attrs.type), start: state(),
        group: p.ids.teamMedChipAll.parentNode.attrs.role};
      for (const [i, name] of [[2, "learned"], [3, "hidden"], [1, "clinic"]]) {
        await p.ids[ids[i]].click(); out[name] = {rows: p.rows().map((x) => x[0]), pressed: state(), count: p.ids.teamMedCount.textContent};
      }
      await p.type("teamMedFilter", "zer");  out.both = p.rows().map((x) => x[0]);      // the search narrows inside the chip
      await p.type("teamMedFilter", "");
      await p.ids.teamMedChipAll.click(); out.all = p.rows().length; out.after = p.calls.length - calls;
      console.log(JSON.stringify(out))""", lists={"medicine": LIST_MEDS})
    assert r["labels"] == ["All (9)", "Clinic changes (8)", "Learned (2)", "Hidden (1)"]
    assert r["types"] == ["button"] * 4 and r["group"] == "group" and r["start"] == ["true", "false", "false", "false"]
    assert r["learned"] == {"rows": ["Zorbexin", "Zerodol-P"], "pressed": ["false", "false", "true", "false"], "count": "Showing 2 of 9"}
    assert r["hidden"]["rows"] == ["ramipril"] and r["hidden"]["pressed"] == ["false", "false", "false", "true"]
    assert "acarbose" not in r["clinic"]["rows"] and len(r["clinic"]["rows"]) == 8 and r["clinic"]["count"] == "Showing 8 of 9"
    assert r["both"] == ["Zerodol-P"] and r["all"] == 9 and r["after"] == 0       # chips and search never send a request


def test_the_chip_stays_on_after_an_action_reloads_the_list():
    r = _page("""
      await p.openMeds(); await p.ids.teamMedChipHidden.click(); await p.press('teamMedRows', 0, 'Reset to default');
      console.log(JSON.stringify({pressed: p.ids.teamMedChipHidden.attrs["aria-pressed"], posts: p.posts, rows: p.rows().map((x) => x[0])}))""",
              lists={"medicine": LIST_MEDS})
    assert r["posts"] == [{"op": "reset", "entry_key": "ramipril", "data": {}}]
    assert r["pressed"] == "true" and r["rows"] == ["ramipril"]


def test_the_source_is_a_small_tag_and_the_actions_sit_on_one_compact_line():
    r = _page("""
      await p.openMeds(); const tr = p.ids.teamMedRows.children[0];
      const tag = tr.children[3].children[0];
      console.log(JSON.stringify({tag: tag.tag, cls: tag.attrs.class, text: tag.textContent, acts: tr.children[4].children.map((b) => b.tag)}))""",
              lists={"medicine": LIST_MEDS})
    assert r["tag"] == "span" and "team-tag" in r["cls"].split() and r["text"] == "Shared" and r["acts"] == ["button", "button"]
    css = _css()
    wide = css.split("@media")[0]
    assert re.search(r"\.team-panel \.team-tag \{[^}]*white-space:nowrap", wide)
    assert re.search(r"\.team-panel \.team-meds-table \.team-row-actions \{[^}]*white-space:nowrap", wide)          # Edit and Hide on one line
    assert re.search(r"\.team-panel \.team-meds-table td \{[^}]*padding:[0-9]px", wide)                         # about one text line per row
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", css.split(".team-panel .team-tag")[1].split("@media")[0])   # tokens, no raw colours


def test_the_list_tabs_widen_the_dialog_and_the_header_row_stays_in_view():
    r = _page("""
      const seen = []; const w = () => p.ids.teamPanel.attrs["data-wide"];
      await p.openMeds(); seen.push(w()); await p.openTests(); seen.push(w());
      await p.ids.teamTabPeople.click(); seen.push(w());
      const box = p.ids.teamMedRows.parentNode.parentNode.attrs.class;
      console.log(JSON.stringify({seen, box}))""")
    assert r["seen"] == ["true", "true", "false"] and "team-list-box" in r["box"].split()
    css = _css()
    assert re.search(r'dialog\.team-panel\[data-wide="true"\] \{ width:min\(1100px, 96vw\); \}', css)
    box = re.search(r"\.team-panel \.team-list-box \{([^}]*)\}", css.split("@media")[0]).group(1)
    assert "overflow:auto" in box and "max-height:" in box
    th = re.search(r"\.team-panel \.team-list-box th \{([^}]*)\}", css).group(1)
    assert "position:sticky" in th and "top:0" in th and "background:var(--card)" in th


def test_the_intro_is_one_sentence_with_the_rest_behind_what_do_these_mean():
    r = _page("""
      const out = {};
      for (const id of ["teamMeds", "teamTests"]) {
        const panel = p.ids[id]; const d = panel.querySelectorAll("details")[0];
        out[id] = {hint: panel.children[0].textContent, summary: d.querySelectorAll("summary")[0].textContent, more: d.textContent};
      }
      console.log(JSON.stringify(out))""")
    for v in r.values():
        assert v["hint"].count(". ") == 0 and v["hint"].endswith(".") and len(v["hint"]) < 100, v["hint"]
        assert v["summary"] == "What do these mean?"
    assert "two new documents" in r["teamMeds"]["more"] and "Clinic changes" in r["teamMeds"]["more"]


def test_an_empty_list_hides_the_header_row_and_the_test_list_says_why():
    r = _page("""
      const box = (id) => p.ids[id].querySelectorAll(".team-list-box")[0].hidden;
      await p.openTests(); const t = {head: p.ids.teamTests.querySelectorAll("thead")[0].hidden, box: box("teamTests"), text: p.ids.teamTestEmpty.textContent, shown: !p.ids.teamTestEmpty.hidden};
      await p.openMeds(); const m = {head: p.ids.teamMeds.querySelectorAll("thead")[0].hidden, box: box("teamMeds")};
      console.log(JSON.stringify({t, m}))""", lists={"medicine": MEDS})
    assert r["t"] == {"head": True, "box": True, "shown": True,
                      "text": "The shared test list is not loaded yet. Tests your doctors add or remember appear here."}
    assert r["m"] == {"head": False, "box": False}
