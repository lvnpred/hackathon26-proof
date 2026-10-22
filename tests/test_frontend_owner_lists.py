"""The owner's Shared lists tab (frontend/ownerlists.js, plan PQ-f Task 11): static pins, and the tab run in node against
tests/team_medicines_fakedom.js. Offline; no browser."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FAKEDOM = Path(__file__).parent / "team_medicines_fakedom.js"

SHIPPED = [
    {"entry_key": "metformin", "entry": {"canonical": "metformin", "aliases": [], "brands": ["Glycomet"]}, "pending": None},
    {"entry_key": "warfarin", "entry": {"canonical": "warfarin", "aliases": [], "brands": [], "safety": True},
     "pending": {"action": "edit", "entry_key": "warfarin", "data": {"brands": ["Coumadin"], "safety": True}}},
]
ADDS = [{"action": "add", "entry_key": "newmed", "data": {"name": "Newmed", "generic": "newgeneric", "aliases": [], "brands": [], "safety": False}}]
OWNER = {"medicine": {"items": SHIPPED, "pending": ADDS}}


def _page(body, **opts):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    opts = {"role": "admin", "is_owner": True, "owner": OWNER, **opts}
    script = ("const D = require(process.argv[1]); (async () => { const p = await D.open(%s); %s })()"
              ".catch((e) => { console.error(e); process.exit(1); });") % (json.dumps(opts), body)
    out = subprocess.run([node, "-e", script, str(FAKEDOM), str(FRONT / "team.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_ownerlists_is_plain_text_only_and_local():
    text = re.sub(r"/\*.*?\*/", "", (FRONT / "ownerlists.js").read_text(encoding="utf-8"), flags=re.S)
    js = "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in text.splitlines())
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", js)
    assert "http://" not in js and "https://" not in js


def test_index_loads_ownerlists_before_team():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert "ownerlists.js?v=1" in html and "team.js?v=6" in html
    assert html.index("clinlists.js?v=") < html.index("ownerlists.js?v=") < html.index("team.js?v=")


def test_no_shared_lists_tab_without_is_owner():
    r = _page("await p.openTeam(); console.log(JSON.stringify({tab: !!p.ids.teamTabShared, panel: !!p.ids.teamShared, calls: p.calls.filter((c) => c.includes('owner'))}))", is_owner=False)
    assert r == {"tab": False, "panel": False, "calls": []}
    r = _page("await p.openTeam(); console.log(JSON.stringify({tab: !!p.ids.teamTabShared}))", role="doctor", is_owner=False)
    assert r == {"tab": False}


def test_owner_sees_the_tab_rows_hint_and_pending_markers():
    r = _page("""
      await p.openTeam(); await p.openShared();
      const rows = p.ids.ownerListRows.children.map((tr) => tr.children.map((td) => td.textContent));
      console.log(JSON.stringify({rows, hint: p.ids.teamShared.children[0].textContent, dl: p.ids.ownerListDownload.textContent,
        off: p.ids.ownerListDownload.disabled, calls: p.calls.filter((c) => c.includes('owner'))}));""")
    assert r["hint"] == "Changes here do not change any clinic's list. Download the file and give it to the operator to apply, commit and deploy."
    assert [x[0] for x in r["rows"]] == ["metformin", "warfarin", "newmed"] or [x[0] for x in r["rows"]] == ["metformin", "warfarin", "Newmed"]
    assert "Pending change" in r["rows"][1][3] and "Pending change" in r["rows"][2][3] and "Pending" not in r["rows"][0][3]
    assert r["dl"] == "Download changes (2)" and r["off"] is False
    assert r["calls"] == ["GET /api/v1/owner/lists/medicine"]


def test_owner_edit_posts_the_change_with_safety():
    r = _page("""
      await p.openTeam(); await p.openShared();
      await p.press("ownerListRows", 0, "Edit");
      p.ids.listEditSafety.checked = true;
      await p.fill({listEditBrands: "Glycomet, Riomet"});
      console.log(JSON.stringify({posts: p.ownerPosts, generic: Object.keys(p.ownerPosts[0].data)}));""")
    assert r["posts"] == [{"kind": "medicine", "op": "edit", "entry_key": "metformin",
                           "data": {"aliases": [], "brands": ["Glycomet", "Riomet"], "safety": True}}]
    assert "generic" not in r["generic"] and "name" not in r["generic"]


def test_owner_add_posts_name_generic_and_key():
    r = _page("""
      await p.openTeam(); await p.openShared();
      p.ids.ownerListAdd.click(); await p.tick();
      await p.fill({listEditName: "Brand New", listEditGeneric: "brandgeneric"});
      console.log(JSON.stringify(p.ownerPosts));""")
    assert r[0]["op"] == "add" and r[0]["entry_key"] == "brand new"
    assert r[0]["data"]["name"] == "Brand New" and r[0]["data"]["generic"] == "brandgeneric" and r[0]["data"]["safety"] is False


def test_server_error_shows_in_the_team_error_box_and_the_list_reloads():
    r = _page("""
      await p.openTeam(); await p.openShared();
      await p.press("ownerListRows", 0, "Edit");
      await p.fill({listEditBrands: "X"});
      console.log(JSON.stringify({err: p.ids.teamError.textContent, shown: !p.ids.teamError.hidden,
        gets: p.calls.filter((c) => c === "GET /api/v1/owner/lists/medicine").length}));""", ownerChange=[400, {"error": "bad brand"}])
    assert r == {"err": "bad brand", "shown": True, "gets": 2}


def test_discard_posts_drop():
    r = _page("""
      await p.openTeam(); await p.openShared();
      const labels = p.labels("ownerListRows", 1);
      await p.press("ownerListRows", 1, "Discard change");
      console.log(JSON.stringify({labels, posts: p.ownerPosts, confirms: p.confirms}));""")
    assert r["labels"] == ["Edit", "Discard change"] and len(r["confirms"]) == 1
    assert r["posts"] == [{"kind": "medicine", "op": "drop", "entry_key": "warfarin", "data": {}}]


def test_download_uses_the_export_route_and_a_blob():
    r = _page("""
      await p.openTeam(); await p.openShared();
      await p.ids.ownerListDownload.click(); await p.tick();
      console.log(JSON.stringify({calls: p.calls.filter((c) => c.includes('export')), downloads: p.downloads, blobs: p.blobs.length}));""")
    assert r["calls"] == ["GET /api/v1/owner/lists/medicine/export"]
    assert r["downloads"] == [{"download": "list-changes-medicine-2026-10-20.json", "href": "blob:fake-1"}] and r["blobs"] == 1


def test_download_falls_back_to_a_default_name_and_is_off_with_no_changes():
    r = _page("""
      await p.openTeam(); await p.openShared();
      await p.ids.ownerListDownload.click(); await p.tick();
      await p.ids["ownerKind-investigation"].click(); await p.tick();
      console.log(JSON.stringify({d: p.downloads, off: p.ids.ownerListDownload.disabled, label: p.ids.ownerListDownload.textContent}));""",
              ownerExport=[200, {"kind": "medicine", "changes": []}, {}])
    assert r["d"][0]["download"] == "list-changes-medicine.json"
    assert r["off"] is True and r["label"] == "Download changes (0)"


def test_an_owner_who_is_not_a_clinic_admin_gets_only_the_shared_lists_tab():
    r = _page("""
      await p.openTeam();
      const labels = p.ids.teamTabPeople.parentNode.children.map((b) => b.textContent);
      await p.openShared();
      console.log(JSON.stringify({labels, meds: !!p.ids.teamTabMeds, rows: p.ids.ownerListRows.children.length}));""", role="doctor")
    assert r == {"labels": ["People", "Shared lists"], "meds": False, "rows": 3}


def test_editing_a_pending_add_keeps_its_safety():
    adds = [{"action": "add", "entry_key": "newmed", "data": {"name": "Newmed", "generic": "ng", "aliases": [], "brands": [], "safety": True}}]
    r = _page("""
      await p.openTeam(); await p.openShared();
      await p.press("ownerListRows", 0, "Edit");
      const started = p.ids.listEditSafety.checked;
      await p.fill({listEditBrands: "Nm"});
      console.log(JSON.stringify({started, posts: p.ownerPosts}));""", owner={"medicine": {"items": [], "pending": adds}})
    assert r["started"] is True and r["posts"][0]["op"] == "add" and r["posts"][0]["data"]["safety"] is True


def test_switching_lists_during_a_post_skips_the_reload_but_keeps_the_message():
    r = _page("""
      let release; p.gate.hold = async (m) => { if (m === "POST") await new Promise((res) => { release = res; }); };
      await p.openTeam(); await p.openShared();
      await p.press("ownerListRows", 0, "Edit");
      const pending = p.ids.listEditDialog.querySelectorAll("form")[0].fire("submit");
      await p.tick();
      await p.ids["ownerKind-investigation"].click(); await p.tick();
      release(); await pending; await p.tick();
      console.log(JSON.stringify({pressed: p.ids["ownerKind-investigation"].attrs["aria-pressed"], err: p.ids.teamError.textContent,
        meds: p.calls.filter((c) => c === "GET /api/v1/owner/lists/medicine").length, inv: p.calls.filter((c) => c === "GET /api/v1/owner/lists/investigation").length}));""",
              ownerChange=[400, {"error": "bad brand"}])
    assert r == {"pressed": "true", "err": "bad brand", "meds": 1, "inv": 1}
