"""core/overlay.screen_rows: the rows of the clinic list screen (plan PQ-f, Task 6)."""
from doctor_dictation.core import overlay as O
from test_overlay_core import COMBO, SHIPPED, row


def screen(rows=(), learned=(), pending=(), shipped=SHIPPED, kind="medicine"):
    return O.screen_rows(kind, shipped, list(rows), list(learned), list(pending))


def item(items, key):
    (found,) = [i for i in items if i["entry_key"] == key]
    return found


def test_screen_lists_every_badge_once():
    rows = [row("aceclofenac", "edit", {"brands": ["Zerodol", "Acemiz"]}, O.entry_sha(SHIPPED[0])),
            row("zerodol-p", "add", {"name": "Zerodol-P", "generic": COMBO}),
            row("paracetamol", "hide", {}, O.entry_sha(SHIPPED[1])),
            row("calcium", "edit", {"generic": "Calcium"}, "gone")]
    items = screen(rows, learned=[{"id": 7, "name": "Zorbexin", "generic": None}])
    badges = {i["entry_key"]: i["badge"] for i in items}
    assert badges == {"aceclofenac": "clinic-edited", "zerodol-p": "clinic-added", "paracetamol": "hidden",
                      "calcium": "clinic-edited", "zorbexin": "learned"}
    hidden = item(items, "paracetamol")
    assert hidden["entry"]["canonical"] == "Paracetamol" and hidden["shipped"] == SHIPPED[1]
    assert item(items, "zorbexin")["formulary_id"] == 7 and item(items, "zerodol-p")["formulary_id"] is None
    assert item(items, "zerodol-p")["shipped"] is None and item(items, "zerodol-p")["base_sha_now"] == ""
    assert item(items, "aceclofenac")["base_sha_now"] == O.entry_sha(SHIPPED[0])


def test_screen_shipped_without_a_row_is_plain():
    items = screen()
    assert [(i["entry_key"], i["badge"], i["flag"], i["pending"]) for i in items] == [
        ("aceclofenac", "shipped", "", None), ("paracetamol", "shipped", "", None)]
    assert items[0]["entry"] is SHIPPED[0] or items[0]["entry"] == SHIPPED[0]


def test_screen_flags_come_first_and_name_the_reason():
    rows = [row("paracetamol", "edit", {"brands": ["Crocin"]}, "stale"), row("aceclofenac", "edit", {"brands": ["Zerodol"]}, "stale")]
    items = screen(rows)
    assert [(i["entry_key"], i["flag"]) for i in items] == [("aceclofenac", "shipped-changed"), ("paracetamol", "safety-override")]


def test_screen_a_learned_name_the_overlay_already_lists_is_not_listed_twice():
    rows = [row("zerodol-p", "add", {"name": "Zerodol-P", "generic": COMBO})]
    learned = [{"id": 1, "name": "zerodol-p", "generic": None}, {"id": 2, "name": "Crocin", "generic": None},
               {"id": 3, "name": "Zorbexin", "generic": "Aceclofenac"}]
    items = screen(rows, learned=learned)
    assert [i["entry_key"] for i in items if i["badge"] == "learned"] == ["zorbexin"]
    assert item(items, "zorbexin")["entry"] == {"canonical": "Aceclofenac", "brands": ["Zorbexin"]}


def test_screen_pending_attaches_to_its_key_or_makes_a_learned_item():
    pend = [{"entry_key": "aceclofenac", "action": "edit", "data": {"generic": "Aceclofenac SR"}, "confirm_count": 1},
            {"entry_key": "zerodol-p", "action": "add", "data": {"name": "Zerodol-P", "generic": COMBO}, "confirm_count": 1}]
    items = screen(pending=pend)
    assert item(items, "aceclofenac")["pending"] == {"count": 1, "threshold": 2, "action": "edit",
                                                     "data": {"generic": "Aceclofenac SR"}}
    own = item(items, "zerodol-p")
    assert own["badge"] == "learned" and own["entry"]["canonical"] == COMBO and own["entry"]["brands"] == ["Zerodol-P"]
    assert own["pending"]["count"] == 1 and own["formulary_id"] is None


def test_screen_investigation_with_an_empty_shipped_list():
    items = screen([row("rft", "add", {"name": "RFT"})], shipped=[], kind="investigation")
    assert [(i["entry_key"], i["badge"], i["entry"]["canonical"]) for i in items] == [("rft", "clinic-added", "RFT")]


def test_screen_a_refused_stored_row_is_still_listed_so_it_can_be_reset():
    items = screen([row("aceclofenac", "add", {"name": "Aceclofenac", "generic": "Aceclofenac"})])
    assert item(items, "aceclofenac")["badge"] == "clinic-added"
