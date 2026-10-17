"""Plan I2-c fix round A: typing in the Spell it field re-checks the typed name after a pause (debounced), replaces the list, never applies."""
from test_frontend_rxspell_dom import _run

OPEN = """const tr = mkRow("q1", "unknown-medicine", { name: "Zyloprim" }); await openPanel(tr);
  const opts = (names) => names.map((n) => ({ name: n, generic: "", reason: "sounds" })); const names = () => ids.spellList.children.map((c) => c.dataset.value);"""


def test_three_keystrokes_make_one_request_with_the_typed_name_and_the_old_list_stays_until_it_answers():
    r = _run(OPEN + """
      dtype("Pr"); dtype("Pre"); dtype("Pred"); await sleep(5);
      const early = [posts.length, names()];                                           // still inside the pause
      await sleep(80);
      const sent = [posts.length, posts[0].url, posts[0].body.row.name, posts[0].body.row.dose, !!posts[0].signal, ids.spellPage.textContent, names()];
      await reply({}, [], opts(["Prednisolone", "Prednisone"]), 2);
      console.log(JSON.stringify({ early, sent, after: [names(), ids.spellPage.textContent, ids.spellInfo.textContent], row: cell(tr, "name").textContent, conf: confirmed.has("q1"), undos: undos.length }));""")
    assert r["early"] == [0, ["Allopurinol"]]
    assert r["sent"] == [1, "/api/v1/rx/check-row", "Pred", "", True, "Searching...", ["Allopurinol"]]
    assert r["after"] == [["Prednisolone", "Prednisone"], "2 suggestions. Showing 1-2 of 2", ""]
    assert (r["row"], r["conf"], r["undos"]) == ("Zyloprim", False, 0)                  # a search never changes the row


def test_a_newer_request_aborts_the_older_one_and_a_stale_answer_is_dropped_and_the_page_resets():
    r = _run(OPEN + """
      await openPanel(mkRow("q2", "unknown-medicine", { name: "Zorbex" }));
      dtype("Pred"); await sleep(70); const first = posts[0];
      dtype("Predn"); await sleep(70); const second = posts[1];
      const aborted = [first.signal.aborted, second.signal.aborted];
      first.res({ row: {}, options: opts(["Stale"]), total: 1 }); await tick();
      const afterStale = [names(), ids.spellPage.textContent];
      second.res({ row: {}, options: Array.from({ length: 12 }, (_, i) => ({ name: "N" + i, generic: "", reason: "sounds" })), total: 12 }); await tick();
      dkey("PageDown"); const p2 = ids.spellPage.textContent;
      dtype("Predni"); await sleep(70); posts[2].res({ row: {}, options: Array.from({ length: 12 }, (_, i) => ({ name: "L" + i, generic: "", reason: "sounds" })), total: 12 }); await tick();
      console.log(JSON.stringify({ aborted, afterStale, p2, last: [names(), ids.spellPage.textContent] }));""")
    assert r["aborted"] == [True, False] and r["afterStale"] == [["Allopurinol"], "Searching..."]
    assert r["p2"] == "Showing 9-12 of 12" and r["last"] == [["L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7"], "12 suggestions. Showing 1-8 of 12"]


def test_emptying_the_field_restores_the_original_list_and_cancels_what_is_pending():
    r = _run(OPEN + """
      dtype("Pred"); await sleep(70); posts[0].res({ row: {}, options: opts(["Prednisolone"]), total: 1 }); await tick();
      const searched = names();
      dtype("Predn"); await sleep(70);                                                // in flight ...
      dtype("");                                                                      // ... then the field is emptied
      const restored = [names(), ids.spellPage.textContent, posts[1].signal.aborted];
      posts[1].res({ row: {}, options: opts(["Late"]), total: 1 }); await tick();
      dtype("Pr"); dtype(""); await sleep(80);                                        // emptied inside the pause: no request at all
      console.log(JSON.stringify({ searched, restored, late: names(), requests: posts.length }));""")
    assert r["searched"] == ["Prednisolone"] and r["restored"] == [["Allopurinol"], "Showing 1-1 of 1", True]
    assert r["late"] == ["Allopurinol"] and r["requests"] == 2


def test_no_request_under_two_letters_or_over_the_input_rules():
    r = _run(OPEN + """
      for (const v of ["P", "1", "  ", "5-", "a".repeat(61), "Vitamin one two three four five six seven eight", "<b>hi</b>"]) { dtype(v); await sleep(60); }
      const none = posts.length;
      dtype("p r e d"); await sleep(70);                                               // spelled letters are cleaned first
      console.log(JSON.stringify({ none, sent: posts.length && posts[0].body.row.name }));""")
    assert r == {"none": 0, "sent": "pred"}


def test_closing_cancels_the_timer_and_drops_the_answer_and_use_this_cancels_a_search():
    r = _run(OPEN + """
      dtype("Pred"); dclick(ids.spellClose); await sleep(80); const timer = posts.length;      // closed inside the pause
      await openPanel(tr); dtype("Predn"); await sleep(70); const pending = posts.shift();
      dclick(ids.spellClose); const aborted = pending.signal.aborted;
      pending.res({ row: {}, options: opts(["Late"]), total: 1 }); await tick();
      await openPanel(tr); dtype("Predni"); await sleep(70); const s2 = posts.shift();
      ids.spellInput.value = "Prednisolone"; dclick(ids.spellUse); await tick();               // Use this while a search is out
      const useSent = [posts.length, posts[0].body.row.name, s2.signal.aborted];
      s2.res({ row: {}, options: opts(["Late2"]), total: 1 }); await tick();
      console.log(JSON.stringify({ timer, aborted, title: ids.spellTitle.textContent, names: names(), useSent }));""")
    assert r["timer"] == 0 and r["aborted"] is True and r["names"] == ["Allopurinol"] and r["useSent"] == [1, "Prednisolone", True]


def test_a_failed_search_keeps_the_list_with_a_short_message_and_busy_or_view_only_never_searches():
    r = _run(OPEN + """
      dtype("Pred"); await sleep(70); posts[0].rej(new Error("x")); await tick();
      const failed = [names(), ids.spellMsg.textContent];
      dtype("Predn"); await sleep(70); const cleared = [ids.spellMsg.textContent, posts.length]; posts[1].res({ row: {}, options: opts(["Ok"]), total: 1 }); await tick();
      flags.working = true; dtype("Predni"); await sleep(70); const working = posts.length; flags.working = false;
      globalThis.Authorship = { isViewOnly: () => true }; dtype("Prednis"); await sleep(70); const vo = posts.length; globalThis.Authorship = undefined;
      console.log(JSON.stringify({ failed, cleared, working, vo, ok: names() }));""")
    assert r["failed"] == [["Allopurinol"], "Could not update the names. The list is unchanged. You can still type the name."]
    assert r["cleared"] == ["", 2] and r["working"] == 2 and r["vo"] == 2 and r["ok"] == ["Ok"]


def test_enter_and_pick_still_use_a_searched_name_or_the_typed_one():
    r = _run(OPEN + """
      dtype("Pred"); await sleep(70); posts.shift().res({ row: {}, options: opts(["Prednisolone"]), total: 1 }); await tick();
      dkey("ArrowDown", ids.spellInput); dkey("Enter"); await tick();
      const picked = posts[0].body.row.name; posts.shift().rej(new Error("x")); await tick();
      ids.spellInput.value = "Typed"; dkey("Enter", ids.spellInput); await tick(); const typed = posts[0].body.row.name;
      console.log(JSON.stringify({ picked, typed }));""")
    assert r == {"picked": "Prednisolone", "typed": "Typed"}
