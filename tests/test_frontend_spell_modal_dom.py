"""Plan I2-c: the Spell it modal: an accessible dialog, paging and keys, close while checking, one shared item builder."""
import re
from pathlib import Path

from test_frontend_rxspell_dom import _run

FRONT = Path(__file__).resolve().parents[1] / "frontend"
HTML = (FRONT / "index.html").read_text(encoding="utf-8")


def test_the_modal_is_a_labelled_dialog_that_keeps_focus_and_gives_it_back():
    tag = HTML[HTML.index('<dialog id="spellDlg"'):].split(">", 1)[0]
    assert all(a in tag for a in ('role="dialog"', 'aria-modal="true"', 'aria-labelledby="spellTitle"', 'aria-describedby="spellHint"'))
    r = _run("""
      const tr = mkRow("m1", "unknown-medicine", { name: "Zyloprim" });
      await openPanel(tr);
      const opened = [panels(), ids.spellTitle.textContent, document.activeElement === ids.spellInput, spellBtn(tr).attrs["aria-expanded"]];
      ids.spellUse.focus(); dkey("Tab"); const wrapped = document.activeElement === ids.spellInput;
      dkey("Tab", ids.spellInput, true); const back = document.activeElement === ids.spellUse;
      dkey("Escape"); const closed = [panels(), document.activeElement === spellBtn(tr), spellBtn(tr).attrs["aria-expanded"]];
      console.log(JSON.stringify({ opened, wrapped, back, closed }));""")
    assert r == {"opened": [1, "Spell Zyloprim", True, "true"], "wrapped": True, "back": True, "closed": [0, True, "false"]}


def test_paging_with_keys_and_buttons_and_enter_uses_the_focused_name():
    r = _run("""
      const tr = mkRow("m2", "unknown-medicine", { name: "Zorbex" });
      click(spellBtn(tr));
      await reply({}, [], Array.from({ length: 20 }, (_, i) => ({ name: "Zorb" + (i + 1), generic: "", reason: "sounds" })), 20);
      const p1 = [ids.spellPage.textContent, ids.spellList.children.length, ids.spellPrev.disabled];
      dkey("PageDown"); dkey("PageDown"); const p3 = [ids.spellPage.textContent, ids.spellNext.disabled];
      dkey("PageUp"); const p2 = ids.spellPage.textContent;
      dkey("ArrowDown", ids.spellInput); const first = document.activeElement.dataset.value;
      dkey("ArrowDown"); const second = document.activeElement.dataset.value;
      dkey("Enter"); await tick();
      console.log(JSON.stringify({ p1, p3, p2, first, second, sent: posts[0].body.row.name, checking: tr._rx.checking }));""")
    assert r["p1"] == ["Showing 1-8 of 20", 8, True] and r["p3"] == ["Showing 17-20 of 20", True] and r["p2"] == "Showing 9-16 of 20"
    assert (r["first"], r["second"], r["sent"], r["checking"]) == ("Zorb9", "Zorb10", "Zorb10", True)


def test_close_while_checking_keeps_the_row_spinner_and_an_edit_still_drops_the_answer():
    r = _run("""
      const a = mkRow("m3", "lookalike-check", { name: "Prednisone" });
      await openPanel(a); await useTyped("Prednisolone");
      dclick(ids.spellClose); const during = [panels(), !!a.querySelector(".rx-checking")];
      await reply({ name: "Prednisolone", status: "verified", lexicon_match: "Prednisolone" });
      const landed = [confirmed.has("m3"), a._rx.how, cell(a, "name").textContent];
      const b = mkRow("m4", "lookalike-check", { name: "Prednisone" });
      await openPanel(b); await useTyped("Prednisolone"); dclick(ids.spellClose);
      RxView.onEdit(b, cell(b, "dose")); RxView.renderRow(b);
      await reply({ name: "Prednisolone", status: "verified" });
      console.log(JSON.stringify({ during, landed, dropped: [confirmed.has("m4"), cell(b, "name").textContent, b._rx.checking] }));""")
    assert r == {"during": [0, True], "landed": [True, "spell", "Prednisolone"], "dropped": [False, "Prednisone", False]}


def test_the_inline_suggestion_and_the_modal_list_are_built_by_one_component():
    r = _run("""
      const tr = mkRow("m5", "unknown-medicine", { name: "Croissin" }, { did_you_mean: "Crocin", did_you_mean_generic: "Paracetamol" });
      const inline = tr.querySelector('[data-action="dym"]');
      click(spellBtn(tr)); await reply({}, [], [{ name: "Crocin", generic: "Paracetamol", reason: "sounds" }], 1);
      const item = ids.spellList.children[0];
      const parts = (b) => b.children.map((c) => [c.className, c.textContent]);
      console.log(JSON.stringify({ inline: [inline.className, parts(inline)], item: [item.className, parts(item)] }));""")
    assert r["inline"] == ["rx-act sug ", [["sug-name", "Did you mean Crocin?"], ["sug-gen", "generic: Paracetamol"]]]
    assert r["item"] == ["rx-act sug spell-item", [["sug-name", "Crocin"], ["sug-gen", "generic: Paracetamol"], ["sug-why", "sounds like"]]]


# ---- added by the I2-c task 3-4 run: the plan's review focus, one real-value test each ----------------------------------

def test_the_typed_field_keeps_the_60_character_8_word_rules_and_the_old_wording_and_never_asks_the_server():
    assert 'maxlength="60"' in HTML[HTML.index('id="spellInput"'):].split(">", 1)[0]
    r = _run("""
      const tr = mkRow("t1", "unknown-medicine", { name: "Zyloprim" });
      await openPanel(tr); const loads = posts.length;
      const out = [];
      for (const v of ["", " ", "x", "<b>hi</b>", "a".repeat(61), "Vitamin one two three four five six seven eight"]) {
        ids.spellInput.value = v; document.activeElement = null; dclick(ids.spellUse); await tick();
        out.push([ids.spellMsg.textContent, document.activeElement === ids.spellInput]);
      }
      console.log(JSON.stringify({ out, extra: posts.length - loads, checking: tr._rx.checking, open: panels(), row: cell(tr, "name").textContent }));""")
    assert r["out"] == [["Type a medicine name first.", True], ["Type a medicine name first.", True], ["That is too short for a medicine name.", True],
                        ["Use letters and digits only.", True], ["That is too long for a medicine name (60 characters at most).", True],
                        ["That is too many words for a medicine name (8 at most).", True]]
    assert (r["extra"], r["checking"], r["open"], r["row"]) == (0, False, 1, "Zyloprim")      # nothing sent, the modal stays open, the row is untouched


def test_a_second_modal_is_impossible_and_a_late_list_for_the_first_row_is_dropped():
    r = _run("""
      const a = mkRow("s1", "unknown-medicine", { name: "Zyloprim" }), b = mkRow("s2", "unknown-medicine", { name: "Croissin" });
      click(spellBtn(a)); const pa = posts.shift();                                  // A's list is still loading
      click(spellBtn(b));                                                            // the fake showModal throws when already open: the modal closes A first
      const now = [panels(), ids.spellTitle.textContent, spellBtn(a).attrs["aria-expanded"], spellBtn(b).attrs["aria-expanded"], SpellModal.isOpenFor("s1"), SpellModal.isOpenFor("s2")];
      pa.res({ row: {}, options: [{ name: "StaleName", generic: "", reason: "sounds" }], total: 1 }); await tick();
      const afterLate = [ids.spellList.children.length, ids.spellPage.textContent];
      await reply({}, [], [{ name: "Crocin", generic: "", reason: "sounds" }], 1);
      console.log(JSON.stringify({ now, afterLate, list: ids.spellList.children.map((c) => c.dataset.value), title: ids.spellTitle.textContent }));""")
    assert r["now"] == [1, "Spell Croissin", "false", "true", False, True]
    assert r["afterLate"] == [0, "Looking for names..."]                                # A's answer never reaches B's modal
    assert r["list"] == ["Crocin"] and r["title"] == "Spell Croissin"


def test_pages_clamp_arrows_stop_at_the_ends_and_a_cap_note_shows_when_more_were_found():
    r = _run("""
      const tr = mkRow("p1", "unknown-medicine", { name: "Zorbex" });
      click(spellBtn(tr));
      await reply({}, [], Array.from({ length: 10 }, (_, i) => ({ name: "Zorb" + (i + 1), generic: "", reason: "sounds" })), 60);
      const first = ids.spellPage.textContent;
      dkey("PageUp"); const atStart = ids.spellPage.textContent;                       // before the first page: stays
      dkey("PageDown"); dkey("PageDown"); dkey("PageDown"); const atEnd = [ids.spellPage.textContent, ids.spellList.children.length, ids.spellNext.disabled, ids.spellPrev.disabled];
      dclick(ids.spellPrev); const prev = ids.spellPage.textContent; dclick(ids.spellNext); const next = ids.spellPage.textContent;
      dkey("ArrowDown", ids.spellInput); dkey("ArrowDown"); dkey("ArrowDown"); const last = document.activeElement.dataset.value;   // two items on this page: stays on the last
      dkey("ArrowUp"); dkey("ArrowUp"); dkey("ArrowUp"); const top = document.activeElement.dataset.value;
      console.log(JSON.stringify({ first, atStart, atEnd, prev, next, last, top }));""")
    assert r["first"] == "Showing 1-8 of 10 (60 found: type more letters to narrow them)" and r["atStart"] == r["first"]
    assert r["atEnd"] == ["Showing 9-10 of 10 (60 found: type more letters to narrow them)", 2, True, False]
    assert (r["prev"], r["next"]) == (r["first"], r["atEnd"][0]) and (r["last"], r["top"]) == ("Zorb10", "Zorb9")


def test_space_uses_the_focused_name_and_a_hostile_name_stays_text_everywhere():
    r = _run("""
      const tr = mkRow("h1", "unknown-medicine", { name: "Zorbex" });
      click(spellBtn(tr));
      await reply({}, [], [{ name: "<img src=x onerror=1>", generic: "<b>g</b>", reason: "sounds" }, { name: "Zorbexa", generic: "", reason: "clinic" }], 2);
      const item = ids.spellList.children[0];
      const text = [item.children[0].textContent, item.children[1].textContent, item.children.length, item.dataset.value];
      dkey("ArrowDown", ids.spellInput); dkey("ArrowDown"); dkey(" "); await tick();
      console.log(JSON.stringify({ text, sent: posts[0].body.row.name, reason: ids.spellList.children[1].children.map((c) => c.textContent) }));""")
    assert r["text"] == ["<img src=x onerror=1>", "generic: <b>g</b>", 3, "<img src=x onerror=1>"]
    assert r["sent"] == "Zorbexa" and r["reason"] == ["Zorbexa", "your clinic uses it"]


def test_a_pick_goes_through_use_name_confirmed_before_the_render_name_questions_only():
    r = _run("""
      const out = [];
      for (const [id, st] of [["k1", "verified"], ["k2", "dose-check"]]) {
        const tr = mkRow(id, "lookalike-check", { name: "Prednisone", dose: "1-1-1" });
        click(spellBtn(tr)); await reply({}, [], [{ name: "Prednisolone", generic: "", reason: "sounds" }], 1);
        dclick(ids.spellList.children[0]); await tick();
        const busy = [ids.spellUse.disabled, ids.spellInput.disabled, ids.spellClose.disabled, ids.spellList.children[0].disabled];
        await reply({ name: "Prednisolone", status: st, lexicon_match: "Prednisolone", dose_note: st === "dose-check" ? "high" : "" });
        out.push([id, busy, confirmed.has(id), tr._rx.how, tr.querySelector(".rx-reason").textContent, cell(tr, "name").textContent, cell(tr, "dose").textContent, panels(), document.activeElement === tr.querySelector(".rx-state")]);
      }
      console.log(JSON.stringify(out));""")
    assert r[0] == ["k1", [True, True, False, True], True, "spell", "You chose this name.", "Prednisolone", "1-1-1", 0, True]   # Close stays usable while checking
    assert r[1][:4] == ["k2", [True, True, False, True], False, ""] and r[1][5:8] == ["Prednisolone", "1-1-1", 0]               # a dose question stays open


def test_a_failed_use_keeps_the_modal_open_with_the_message_and_gives_the_controls_back():
    r = _run("""
      const tr = mkRow("f1", "unknown-medicine", { name: "Zyloprim" });
      await openPanel(tr); await useTyped("Allopurinol");
      const err = new Error("boom"); err.status = 500; posts.shift().rej(err); await tick();
      console.log(JSON.stringify({ open: panels(), msg: ids.spellMsg.textContent, off: [ids.spellUse.disabled, ids.spellInput.disabled], focus: document.activeElement === ids.spellInput,
        value: ids.spellInput.value, row: cell(tr, "name").textContent, note: tr._rx.note, undos: undos.length }));""")
    assert r["open"] == 1 and r["msg"] == "The medicine check is not available right now. The row is unchanged." and r["off"] == [False, False]
    assert r["focus"] is True and r["value"] == "Allopurinol" and r["row"] == "Zyloprim" and r["undos"] == 0


def test_a_failed_list_load_says_so_and_the_doctor_can_still_type():
    r = _run("""
      const tr = mkRow("l1", "unknown-medicine", { name: "Zyloprim" });
      click(spellBtn(tr)); const loading = [ids.spellPage.textContent, ids.spellMsg.textContent];
      posts.shift().rej({ aborted: true }); await tick();
      const failed = [ids.spellPage.textContent, ids.spellMsg.textContent, ids.spellList.children.length];
      await useTyped("Allopurinol");
      console.log(JSON.stringify({ loading, failed, typed: posts[0].body.row.name }));""")
    assert r["loading"] == ["Looking for names...", ""]
    assert r["failed"] == ["No close names found. Type the name.", "The check took too long and was stopped. You can still type the name.", 0]
    assert r["typed"] == "Allopurinol"


def test_edit_delete_undo_and_a_correction_close_the_modal_without_taking_focus_and_stale_lists_are_dropped():
    r = _run("""
      const out = {};
      const mk = async (id) => { const tr = mkRow(id, "unknown-medicine", { name: "Zyloprim" }); click(spellBtn(tr)); return tr; };
      let tr = await mk("e1"); const pend = posts.shift(); ids.spellInput.focus();
      RxView.onEdit(tr, cell(tr, "dose")); RxView.renderRow(tr);                              // a hand edit
      out.edit = [panels(), SpellModal.isOpenFor("e1"), document.activeElement === ids.spellInput];
      pend.res({ row: {}, options: [{ name: "Late", generic: "", reason: "sounds" }], total: 1 }); await tick();
      out.late = ids.spellList.children.length;
      tr = await mk("e2"); posts.shift(); tr.remove(); RxView.sync(); out.del = [panels(), SpellModal.isOpenFor("e2")];   // delete + page sync
      tr = await mk("e3"); posts.shift(); RxView.restore({ rowid: "e3", data: { name: "Zyloprim", status: "unknown-medicine" }, wasConfirmed: false }); out.undo = panels();
      tr = await mk("e4"); posts.shift(); confirmed.add("e4"); RxView.renderRow(tr); out.confirmed = panels();           // confirmed from outside
      tr = await mk("e5"); posts.shift(); tr.remove(); const back = mkRow("e5", "unknown-medicine", { name: "Zyloprim" });   // delete then Undo: same id, new element
      RxView.sync(); out.undelete = [panels(), SpellModal.isOpenFor("e5")];
      console.log(JSON.stringify(out));""")
    assert r == {"edit": [0, False, True], "late": 0, "del": [0, False], "undo": 0, "confirmed": 0, "undelete": [0, False]}


def test_the_browsers_own_escape_closes_the_modal_and_gives_focus_back():
    r = _run("""
      const tr = mkRow("c1", "unknown-medicine", { name: "Zyloprim" });
      await openPanel(tr); let prevented = 0;
      (dlg.handlers.cancel || []).forEach((f) => f({ preventDefault() { prevented++; } }));
      const first = [panels(), prevented, document.activeElement === spellBtn(tr)];
      (dlg.handlers.cancel || []).forEach((f) => f({ preventDefault() { prevented++; } })); dkey("Escape");   // nothing open: harmless
      console.log(JSON.stringify({ first, still: panels() }));""")
    assert r == {"first": [0, 1, True], "still": 0}


def test_use_this_says_why_when_the_page_is_busy_or_view_only():
    r = _run("""
      const tr = mkRow("b1", "unknown-medicine", { name: "Zyloprim" });
      await openPanel(tr); ids.spellInput.value = "Allopurinol";
      flags.working = true; dclick(ids.spellUse); const working = ids.spellMsg.textContent; flags.working = false;
      globalThis.Authorship = { isViewOnly: () => true }; dclick(ids.spellUse); const vo = ids.spellMsg.textContent; globalThis.Authorship = undefined;
      console.log(JSON.stringify({ working, vo, posts: posts.length, checking: tr._rx.checking }));""")
    assert r == {"working": "Wait for the page to finish, then try again.", "vo": "This prescription is view only.", "posts": 0, "checking": False}


def test_the_modal_markup_scripts_and_css_follow_the_contract():
    js = (FRONT / "spellmodal.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "fetch(" not in js and "XMLHttpRequest" not in js and len(js.splitlines()) <= 500
    assert "innerHTML" not in (FRONT / "suglist.js").read_text(encoding="utf-8")
    assert HTML.index("rxview.js?v=") < HTML.index("spellmodal.js?v=") < HTML.index("app.js?v=") and HTML.index("<dialog id=\"spellDlg\"") < HTML.index("<script src=\"auth.js")
    tab = [m for m in re.findall(r'id="(spell\w+)"', HTML)]
    assert tab == ["spellDlg", "spellTitle", "spellHint", "spellInput", "spellMic", "spellInfo", "spellMsg", "spellList", "spellPrev", "spellPage", "spellNext", "spellClose", "spellUse"]
    assert 'aria-label="Medicine name"' in HTML and 'role="alert"' in HTML[HTML.index('id="spellMsg"'):].split(">", 1)[0] and 'role="status"' in HTML[HTML.index('id="spellPage"'):].split(">", 1)[0]
    assert 'role="status"' in HTML[HTML.index('id="spellInfo"'):].split(">", 1)[0] and 'aria-live="polite"' in HTML[HTML.index('id="spellInfo"'):].split(">", 1)[0]
    css = re.sub(r"\s+", " ", re.sub(r"/\*.*?\*/", "", (FRONT / "rx.css").read_text(encoding="utf-8"), flags=re.S))
    ring = re.search(r"\.spell-item:focus-visible[^{]*\{([^}]*)\}", css).group(1)
    assert ".spell-dlg button:focus-visible" in css and ".spell-line input:focus-visible" in css and "outline:3px solid var(--accent)" in ring
    assert re.search(r"\.spell-line input \{[^}]*min-height:44px", css) and re.search(r"\.spell-pager \{[^}]*align-items:center", css)
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_opening_while_the_dialog_is_somehow_already_open_does_not_throw():
    r = _run("""
      const tr = mkRow("o1", "unknown-medicine", { name: "Zyloprim" });
      dlg.open = true;                                                               // the browser would throw InvalidStateError from showModal here
      click(spellBtn(tr)); await reply({}, ["Allopurinol"]);
      console.log(JSON.stringify({ open: panels(), title: ids.spellTitle.textContent, items: ids.spellList.children.length }));""")
    assert r == {"open": 1, "title": "Spell Zyloprim", "items": 1}
