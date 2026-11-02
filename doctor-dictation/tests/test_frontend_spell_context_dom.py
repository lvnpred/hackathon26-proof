"""Spell it context group (SH-B2 UI): the load request carries the sheet's context, the answer's groups sit below the sound-alikes, never first.
Runs frontend/rxview.js, suglist.js and spellmodal.js under node on the fake DOM of test_frontend_rxspell_dom.py."""
import json
import re
from pathlib import Path

from tests.test_frontend_rxspell_dom import _run

FRONT = Path(__file__).resolve().parents[1] / "frontend"
CTX = [{"kind": "diagnosis", "for": "BPH", "items": [{"name": "Urimax", "generic": "Tamsulosin"}]},
       {"kind": "patient", "for": "", "items": [{"name": "Dutas", "generic": ""}, {"name": "Uromax", "generic": ""}]}]
_PRE = "const CTX = " + json.dumps(CTX) + ";"


def test_the_load_sends_the_context_and_the_group_sits_below_the_sound_alikes():
    r = _run(_PRE + """
      const tr = mkRow("c1", "unknown-medicine", { name: "Yurimacks" }); click(spellBtn(tr));
      const sent = posts[0].body;
      posts.shift().res({ row: {}, suggestions: [], options: [{ name: "Uromax", generic: "", reason: "sounds" }], total: 1, context: CTX }); await tick();
      const labels = [...ids.spellCtx.querySelectorAll(".spell-ctx-label")].map((n) => n.textContent);
      const names = [...ids.spellCtx.querySelectorAll("button")].map((b) => b.dataset.value);
      console.log(JSON.stringify({ hasCtx: "context" in sent && "document_id" in sent, labels, names, first: ids.spellList.children[0].dataset.value, hidden: ids.spellCtx.hidden }));""")
    assert r == {"hasCtx": True, "labels": ["Used for BPH", "This patient's earlier medicines"], "names": ["Urimax", "Dutas"], "first": "Uromax", "hidden": False}


def test_the_group_never_comes_first_and_drops_names_already_shown():
    r = _run(_PRE + """
      const tr = mkRow("c1", "unknown-medicine", { name: "Yurimacks" }); click(spellBtn(tr));
      posts.shift().res({ row: {}, suggestions: [], options: [], total: 0, context: CTX }); await tick();
      const none = { hidden: ids.spellCtx.hidden, n: ids.spellCtx.querySelectorAll("button").length };
      dclick(ids.spellClose);
      click(spellBtn(tr));
      const OPTS = ["Urimax", "Dutas", "Uromax"].map((n) => ({ name: n, generic: "", reason: "sounds" }));
      posts.shift().res({ row: {}, suggestions: [], options: OPTS, total: 3, context: CTX }); await tick();
      console.log(JSON.stringify({ none, all: { hidden: ids.spellCtx.hidden, n: ids.spellCtx.querySelectorAll("button").length } }));""")
    assert r == {"none": {"hidden": True, "n": 0}, "all": {"hidden": True, "n": 0}}


def test_search_and_use_requests_carry_no_context_and_a_group_tap_uses_the_name():
    r = _run(_PRE + """
      const tr = mkRow("c1", "unknown-medicine", { name: "Yurimacks" }); click(spellBtn(tr));
      posts.shift().res({ row: {}, suggestions: [], options: [{ name: "Uromax", generic: "", reason: "sounds" }], total: 1, context: CTX }); await tick();
      dtype("Uri"); await sleep(80);
      const search = posts[0].body; posts.shift().res({ row: {}, suggestions: [], options: [{ name: "Uromax", generic: "", reason: "sounds" }], total: 1 }); await tick();
      const gone = ids.spellCtx.hidden;
      dtype(""); await tick();
      dclick(ids.spellCtx.querySelectorAll("button")[0]); await tick();
      const use = posts[0].body;
      console.log(JSON.stringify({ search: Object.keys(search).sort(), gone, use: Object.keys(use).sort(), name: use.row.name }));""")
    assert r["search"] == ["age_sex", "row", "transcript"] and r["use"] == ["age_sex", "row", "transcript"]
    assert r["name"] == "Urimax"


def test_group_helpers_and_the_arrow_keys_run_over_list_then_group():
    r = _run(_PRE + """
      const long = SugList.groupLabel({ kind: "diagnosis", for: "x".repeat(60) });
      const bare = SugList.groupLabel({ kind: "diagnosis", for: "" }), pat = SugList.groupLabel({ kind: "patient", for: "BPH" });
      const bad = [SugList.groupsOf(null), SugList.groupsOf({ context: "x" }), SugList.groupsOf({ context: [{ kind: "other", items: [{ name: "A" }] }, { kind: "patient", items: [{ name: 5 }] }] })];
      const big = SugList.groupsOf({ context: [CTX[0], CTX[1], CTX[0]].map((g) => Object.assign({}, g, { items: ["a", "b", "c", "d"].map((n) => ({ name: n })) })) });
      const tr = mkRow("c1", "unknown-medicine", { name: "Yurimacks" }); click(spellBtn(tr));
      posts.shift().res({ row: {}, suggestions: [], options: [{ name: "Uromax", generic: "", reason: "sounds" }], total: 1, context: CTX }); await tick();
      ids.spellList.children[0].focus(); const seen = [];
      for (let i = 0; i < 2; i++) { dkey("ArrowDown", document.activeElement); seen.push(document.activeElement.dataset.value); }
      console.log(JSON.stringify({ long, bare, pat, bad, groups: big.length, items: big[0].items.length, seen }));""")
    assert r == {"long": "Used for " + "x" * 40 + "…", "bare": "Used for this diagnosis", "pat": "This patient's earlier medicines",
                 "bad": [[], [], []], "groups": 2, "items": 3, "seen": ["Urimax", "Dutas"]}


def test_versions_and_markup():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert html.index('id="spellList"') < html.index('id="spellCtx"') < html.index('id="spellPrev"')
    for pin in ("suglist.js?v=5", "rxview.js?v=20", "spellmodal.js?v=3", "app.js?v=62", "theme.css?v=9"):
        assert pin in html
    for js in ("suglist.js", "spellmodal.js"):
        assert "innerHTML" not in (FRONT / js).read_text(encoding="utf-8")
    css = (FRONT / "theme.css").read_text(encoding="utf-8")
    assert re.search(r"\.spell-ctx-label \{[^}]*var\(--ink-muted\)", css)
