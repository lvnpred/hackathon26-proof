"""core/overlay.py: write (``conflicts``) and read (``effective_entries``) agree by construction (PQ-f Task 2, review round 2)."""

from doctor_dictation.core import overlay as O
from doctor_dictation.core import surface
from test_overlay_core import COMBO, SHIPPED, SHIPPED_NS, _real, eff, row

def _real_entry(canon):
    from doctor_dictation.core import determinism as D
    return next(x for x in D.load_lexicon() if x["canonical"] == canon)


def _never_silently_skipped(monkeypatch, rows, new, lookups):
    """``new`` is either refused at write, or accepted and effective at read; returns the refusal."""
    from doctor_dictation.core import determinism as D
    why = O.conflicts("medicine", D.load_lexicon(), rows, new)
    if not why:
        Dm, e, _ = _real(monkeypatch, rows + [new])
        for name, generic in lookups.items():
            assert Dm._exact_lookup(name) == generic, (name, generic)
    return why


def test_w_generic_freed_by_a_later_key_edit(monkeypatch):
    rows = [row("paracetamol", "edit", {"brands": ["Dolo", "Calpol", "Fepanil"]}, O.entry_sha(_real_entry("Paracetamol")))]
    why = _never_silently_skipped(monkeypatch, rows, row("abcbrand", "add", {"name": "Abcbrand", "generic": "Crocin"}),
                                  {"Abcbrand": "Crocin"})
    assert why == ["'Crocin' is a brand of Paracetamol — choose the generic"]


def test_we_edit_generic_freed_by_a_later_key_edit(monkeypatch):
    rows = [row("paracetamol", "edit", {"brands": ["Dolo", "Calpol", "Fepanil"]}, O.entry_sha(_real_entry("Paracetamol")))]
    new = row("aceclofenac", "edit", {"generic": "Crocin"}, O.entry_sha(_real_entry("Aceclofenac")))
    assert _never_silently_skipped(monkeypatch, rows, new, {"Zerodol": "Crocin"})


def test_wn_name_freed_by_a_later_key_generic_rename(monkeypatch):
    rows = [row("zopiclone", "edit", {"generic": "Zopiclone tablets"}, O.entry_sha(_real_entry("Zopiclone")))]
    new = row("abzop", "add", {"name": "Abzop", "generic": "Eszopiclone", "brands": ["Zopiclone"]})
    assert _never_silently_skipped(monkeypatch, rows, new, {"Abzop": "Eszopiclone"})


def test_a_change_that_would_knock_out_an_accepted_row_is_refused():
    rows = [row("mydol", "add", {"name": "Mydol", "generic": "Newgeneric"})]
    # an earlier key that takes "Newgeneric" as a brand would set the accepted Mydol row aside at read
    new = row("abc", "add", {"name": "Abc", "generic": COMBO, "brands": ["Newgeneric"]})
    why = O.conflicts("medicine", SHIPPED, rows, new)
    assert len(why) == 1 and "'mydol'" in why[0]
    assert [x for x in eff(rows)[0] if x.get("clinic")][0]["canonical"] == "Newgeneric"


def test_hide_of_the_clinics_own_addition_says_reset():
    rows = [row("mydol", "add", {"name": "Mydol", "generic": "Paracetamol"})]
    assert O.conflicts("medicine", SHIPPED, rows, row("mydol", "hide", {})) == \
        ["This is your own addition — use Reset to remove it"]


ZOP = {"canonical": "Zopiclone", "aliases": ["zopiclone"], "brands": ["Zopicon"], "forms": [], "strengths": []}


def _pool():
    names = ["Zerodol", "Crocin", "Dolo", "Zopicon", "Newbrand", "Mydol", "Zopiclone", "Aceclofenac"]
    generics = [COMBO, "Paracetamol", "Crocin", "Zerodol", "Ketorolac", "Zopiclone tablets", "Newbrand", "Mydol"]
    return names, generics


def _random_row(rnd, shipped):
    names, generics = _pool()
    pick = rnd.random()
    if pick < 0.5:
        n = rnd.choice(names)
        data = {"name": n, "generic": rnd.choice(generics)}
        if rnd.random() < 0.4:
            data["brands"] = rnd.sample(names, 2)
        return row(O._key(n), "add", data)
    base = rnd.choice(shipped)
    if pick < 0.9:
        data = rnd.choice([{"brands": rnd.sample(names, 2)}, {"generic": rnd.choice(generics)},
                           {"aliases": rnd.sample(names, 1)}])
        return row(O.entry_key_of(base), "edit", data, O.entry_sha(base))
    return row(O.entry_key_of(base), "hide", {}, O.entry_sha(base))


def test_every_row_accepted_by_conflicts_is_effective_at_read():
    import random
    shipped = SHIPPED_NS + [ZOP]
    for seed in range(300):
        rnd, rows = random.Random(seed), []
        for _ in range(10):
            new = _random_row(rnd, shipped)
            if not O.conflicts("medicine", shipped, rows, new):
                rows = [r for r in rows if r["entry_key"] != new["entry_key"]] + [new]
        _ctx, accepted = O._settled("medicine", shipped, rows)
        assert sorted(r["entry_key"] for r in accepted) == sorted(r["entry_key"] for r in rows), seed
        e, _ = O.effective_entries("medicine", shipped, rows)
        assert surface.ambiguous_names(e) == {}, seed
        for r in rows:
            if r["action"] == "add":
                assert any(x.get("clinic") and O._claim(x["canonical"]) == O._claim(r["data"]["generic"]) for x in e), seed
            elif r["action"] == "hide":
                hidden = next(x for x in shipped if O.entry_key_of(x) == r["entry_key"])
                assert not any(x is hidden or x == hidden for x in e), seed


def test_renaming_a_generic_keeps_the_old_generic_as_a_name():
    edit = row("paracetamol", "edit", {"generic": COMBO}, O.entry_sha(SHIPPED_NS[1]))
    e, _ = eff([edit], SHIPPED_NS)
    assert e[1]["canonical"] == COMBO and e[1]["aliases"] == ["paracetamol"]
    # the old generic stays this entry's name, so a clinic add with that generic is refused in either write order
    add = row("dolo", "add", {"name": "Dolo", "generic": "Paracetamol"})
    assert O.conflicts("medicine", SHIPPED_NS, [edit], add)
    assert O.conflicts("medicine", SHIPPED_NS, [add], edit)
    e, _ = eff([edit, add], SHIPPED_NS)
    assert surface.ambiguous_names(e) == {}


def test_a_renamed_generic_is_still_found_by_its_old_name_real_list(monkeypatch):
    # dropping the old name would send "Levofloxacin" to the fuzzy match, which picks Ofloxacin (review round 3)
    for old in ("Levofloxacin", "Citalopram", "Esomeprazole"):
        new = f"{old} X Salt"
        D, e, f = _real(monkeypatch, [row(O._key(old), "edit", {"generic": new}, O.entry_sha(_real_entry(old)))])
        assert f == [] and D._exact_lookup(old) == new and D._exact_lookup(old.lower()) == new
