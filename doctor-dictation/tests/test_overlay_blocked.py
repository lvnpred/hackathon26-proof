"""A name the clinic's overlay removed never becomes a different drug (plan PQ-f final fix C1, clinical safety).

Hiding Escitalopram used to turn "tab escitalopram 10 mg" into Citalopram, verified. A removed name (a hidden entry's,
a brand or alias an edit dropped, an inert clinic row's) is BLOCKED: it stays as dictated and grades unknown-medicine.
The sweeps run every shipped entry; the memoised view keeps them to seconds. Offline, pure (no database)."""
import pytest

from doctor_dictation.core import determinism as D
from doctor_dictation.core import overlay, overlay_state, rowcheck
from doctor_dictation.core.overlay import _claim

UNKNOWN = "unknown-medicine"


@pytest.fixture(autouse=True)
def _own_overlay():
    before = overlay_state._active.get()
    yield
    overlay_state._active.set(before)


def _lex() -> list:
    return D.shipped_lexicon()           # read per test: another test may have reloaded the shipped list


def _row(entry, action, data):
    return {"kind": "medicine", "entry_key": overlay.entry_key_of(entry), "action": action, "data": data,
            "base_sha": overlay.entry_sha(entry)}


def _names(entry) -> list:
    return list(dict.fromkeys(n for n in [entry["canonical"], *entry.get("aliases", []), *entry.get("brands", [])]
                              if isinstance(n, str) and n.strip()))


def _removed_problems(name: str) -> list:
    """What is wrong with how a BLOCKED name is handled; [] when it stays as dictated and grades unknown."""
    raw = f"tab {name} twice daily"
    norm = D.normalize_transcript(raw)
    out = []
    if _claim(name) not in _claim(norm):
        out.append(("rewritten", name, norm))
    row = rowcheck.ground_one({"name": name, "strength": "", "dose": "1-0-1"}, raw, norm)
    if row["status"] != UNKNOWN or row["lexicon_match"] or row["generic"]:
        out.append(("graded", name, row["status"], row["lexicon_match"]))
    if row["did_you_mean"] or rowcheck.options(row)[1] or rowcheck.suggestions(row):
        out.append(("suggested", name, row["did_you_mean"], rowcheck.options(row)[0][:3]))
    if D._canonical_lookup(name) or D._exact_lookup(name):
        out.append(("lookup", name, D._canonical_lookup(name), D._exact_lookup(name)))
    return out


def _kept_problems(name: str, want: str) -> list:
    """A name still on the clinic's list must find the entry that lists it (``want``, its canonical)."""
    got = D._exact_lookup(name)
    return [] if got == want else [("lost", name, got, want)]


def _owner(name: str) -> str:
    """The canonical of the effective entry that lists ``name`` ("" if none)."""
    c = _claim(name)
    return next((e["canonical"] for e in D.load_lexicon()
                 if c in {_claim(n) for n in [e["canonical"], *e.get("aliases", []), *e.get("brands", [])]}), "")


def _sweep(make_row, kept_in_entry=frozenset()) -> tuple:
    """(problems, blocked names checked, entries checked) over every shipped entry under ``make_row(entry)``."""
    problems, checked, entries = [], 0, 0
    for entry in _lex():
        row = make_row(entry)
        if overlay.conflicts("medicine", _lex(), [], row):
            continue
        entries += 1
        overlay.activate(overlay.state_from_rows([row]))
        try:
            blocked = D.blocked_names()
            for name in _names(entry):
                if _claim(name) in blocked:
                    checked += 1
                    problems += _removed_problems(name)
                else:
                    problems += _kept_problems(name, _owner(name))
                    if not _owner(name):
                        problems.append(("vanished", name))
        finally:
            overlay.activate(overlay.OverlayState())
    return problems, checked, entries


# ---- the sweeps ------------------------------------------------------------------------------------------------------

def test_hiding_any_entry_never_routes_its_names_to_another_drug():
    problems, checked, entries = _sweep(lambda e: _row(e, "hide", {}))
    assert entries == len(_lex()) and checked > len(_lex())
    assert not problems, problems[:10]


def test_an_edit_that_drops_every_brand_and_alias_never_routes_them_to_another_drug():
    problems, checked, entries = _sweep(lambda e: _row(e, "edit", {"aliases": [], "brands": []}))
    assert entries > 400 and checked > 400
    assert not problems, problems[:10]


def test_a_rename_with_its_own_aliases_keeps_the_old_generic_and_blocks_the_dropped_aliases():
    renamed = {}

    def make(e):
        renamed[e["canonical"]] = e["canonical"] + " Renamed"
        return _row(e, "edit", {"generic": e["canonical"] + " Renamed", "aliases": ["Zzqxalias"]})
    problems, checked, entries = _sweep(make)
    assert entries == len(_lex()) and checked > 100
    assert not problems, problems[:10]
    for canon in ("Levofloxacin", "Escitalopram", "Clonazepam"):             # the old generic finds the renamed entry
        e = next(x for x in _lex() if x["canonical"] == canon)
        overlay.activate(overlay.state_from_rows([make(e)]))
        assert D._exact_lookup(canon) == D._canonical_lookup(canon) == canon + " Renamed"
        assert canon + " Renamed" in D.normalize_transcript(f"tab {canon.lower()} twice daily")


# ---- the incidents, one by one ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("hidden, look_alike", [("Escitalopram", "Citalopram"), ("Clonazepam", "Lorazepam"),
                                                ("Levofloxacin", "Ofloxacin"), ("Esomeprazole", "Omeprazole")])
def test_a_hidden_drug_is_not_its_look_alike(hidden, look_alike):
    e = next(x for x in _lex() if x["canonical"] == hidden)
    overlay.activate(overlay.state_from_rows([_row(e, "hide", {})]))
    raw = f"tab {hidden.lower()} 10 mg once daily for 30 days"
    norm = D.normalize_transcript(raw)
    assert look_alike not in norm and hidden.lower() in norm
    (row,), _ = D.ground_rx([{"name": hidden, "strength": ""}], norm, raw)
    assert (row["status"], row["lexicon_match"], row["generic"]) == (UNKNOWN, "", "")
    assert rowcheck.did_you_mean(hidden, UNKNOWN)["did_you_mean"] == ""


def test_a_near_spelling_of_a_hidden_drug_is_not_moved_to_its_look_alike():
    e = next(x for x in _lex() if x["canonical"] == "Escitalopram")
    assert D._canonical_lookup("Escitalopam") == "Escitalopram"
    overlay.activate(overlay.state_from_rows([_row(e, "hide", {})]))
    assert D._canonical_lookup("Escitalopam") == ""
    assert "Citalopram" not in D.normalize_transcript("tab escitalopam 10 mg")


def test_a_blocked_name_matches_whatever_its_separators_and_case():
    e = next(x for x in _lex() if x["canonical"] == "Carbimazole")
    assert "Neo-Mercazole" in e["brands"]
    overlay.activate(overlay.state_from_rows([_row(e, "edit", {"brands": []})]))
    for spelt in ("Neo-Mercazole", "neo mercazole", "NEO–MERCAZOLE", "Neo−Mercazole", "neo-mercazole."):
        assert D.is_blocked(spelt), spelt
        assert not D._exact_lookup(spelt) and not D._canonical_lookup(spelt)
    assert "Omeprazole" not in D.normalize_transcript("tab neo mercazole 5 mg twice daily")


def test_a_blocked_phrase_does_not_eat_into_a_longer_listed_name(monkeypatch):
    lex = [{"canonical": "Calcium Citrate", "aliases": [], "brands": [], "forms": [], "strengths": []},
           {"canonical": "Calcium Citrate Malate", "aliases": [], "brands": [], "forms": [], "strengths": []}]
    view = overlay.View(lex[1:])
    view.blocked = frozenset({"calcium citrate"})
    monkeypatch.setattr(D, "load_lexicon", lambda: view)
    assert D.correct_drugs("tab calcium citrate malate daily") == "tab Calcium Citrate Malate daily"
    assert D.correct_drugs("tab calcium citrate daily") == "tab calcium citrate daily"


# ---- the blocked set -------------------------------------------------------------------------------------------------

def test_no_overlay_means_nothing_blocked():
    assert D.load_lexicon() is _lex() and D.blocked_names() == frozenset()


def test_the_blocked_set_is_part_of_the_memoised_view_and_per_clinic():
    e = next(x for x in _lex() if x["canonical"] == "Escitalopram")
    a = overlay.state_from_rows([_row(e, "hide", {})])
    b = overlay.state_from_rows([_row(e, "edit", {"brands": []})])
    overlay.activate(a)
    view_a = D.load_lexicon()
    assert D.load_lexicon() is view_a and "escitalopram" in view_a.blocked
    overlay.activate(b)
    assert "escitalopram" not in D.blocked_names() and D._exact_lookup("Escitalopram") == "Escitalopram"
    overlay.activate(a)
    assert D.load_lexicon() is view_a


def test_a_name_still_on_the_list_is_not_blocked():
    shipped = [{"canonical": "Paracetamol", "aliases": ["pcm"], "brands": ["Crocin"]},
               {"canonical": "Aceclofenac", "aliases": [], "brands": ["Zerodol"]}]
    rows = [{"kind": "medicine", "entry_key": "paracetamol", "action": "hide", "data": {}, "base_sha": ""},
            {"kind": "medicine", "entry_key": "crocin", "action": "add",
             "data": {"name": "Crocin", "generic": "Paracetamol Clinic"}, "base_sha": ""}]
    _entries, _flags, blocked = overlay.effective_and_blocked("medicine", shipped, rows)
    assert blocked == frozenset({"paracetamol", "pcm"})          # Crocin is the clinic's own entry now


def test_an_inert_clinic_rows_names_are_blocked():
    shipped = [{"canonical": "Paracetamol", "aliases": [], "brands": ["Crocin"]}]
    row = {"kind": "medicine", "entry_key": "crocinol", "action": "add",      # a later list made "Crocin" a brand
           "data": {"name": "Crocinol", "generic": "Crocin", "aliases": ["Crocinola"]}, "base_sha": ""}
    entries, _flags, blocked = overlay.effective_and_blocked("medicine", shipped, [row])
    assert [e["canonical"] for e in entries] == ["Paracetamol"]
    assert blocked == frozenset({"crocinol", "crocinola"})


def test_a_rename_that_sends_aliases_still_keeps_the_old_generic_as_an_alias():
    shipped = [{"canonical": "Levofloxacin", "aliases": ["levo"], "brands": ["Levoflox"]}]
    row = {"kind": "medicine", "entry_key": "levofloxacin", "action": "edit",
           "data": {"generic": "Levofloxacin Hemihydrate", "aliases": ["Lvx"]}, "base_sha": ""}
    (entry,), _flags, blocked = overlay.effective_and_blocked("medicine", shipped, [row])
    assert entry["aliases"] == ["Lvx", "Levofloxacin"] and blocked == frozenset({"levo"})


def test_effective_view_names_its_parameter_shipped():
    import inspect
    assert list(inspect.signature(overlay_state.effective_view).parameters) == ["kind", "shipped"]


def test_conflicts_refuses_a_generic_naming_a_hidden_medicine():         # plan g final review I2, at the source
    para = next(e for e in _lex() if e["canonical"] == "Paracetamol")
    rows = [_row(para, "hide", {})]
    add = {"entry_key": "barprol", "action": "add", "data": {"name": "Barprol", "generic": "Paracetamol"}}
    assert overlay.conflicts("medicine", _lex(), rows, add) == ["Paracetamol is hidden on your list: Reset it first"]
    combo = {**add, "data": {"name": "Barprol", "generic": "Aceclofenac + paracetamol"}}
    assert overlay.conflicts("medicine", _lex(), rows, combo) == ["paracetamol is hidden on your list: Reset it first"]
    assert overlay.conflicts("medicine", _lex(), [], add) == []                     # not hidden: the add is fine
    assert overlay.conflicts("medicine", _lex(), rows, _row(para, "edit", {"aliases": ["PCM"]})) == []   # the hide's own key


def test_conflicts_refuses_hiding_a_medicine_a_clinic_row_uses_as_its_generic():   # the mirror of I2
    para = next(e for e in _lex() if e["canonical"] == "Paracetamol")
    hide = _row(para, "hide", {})
    fooprol = {"entry_key": "fooprol", "action": "add", "data": {"name": "Fooprol", "generic": "Paracetamol"}}
    combo = {"entry_key": "barcomb", "action": "add", "data": {"name": "Barcomb", "generic": "Ibuprofen + Paracetamol"}}
    assert overlay.conflicts("medicine", _lex(), [fooprol], hide) == [
        "Paracetamol is the generic of Fooprol on your list: edit or reset Fooprol first"]
    assert overlay.conflicts("medicine", _lex(), [combo, fooprol], hide) == [
        "Paracetamol is the generic of Barcomb, Fooprol on your list: edit or reset Barcomb, Fooprol first"]
    assert overlay.conflicts("medicine", _lex(), [], hide) == []


# ---- plan h final re-review: a set-aside row is flagged; only a medicine one is blocked ---------------------------------

USG = {"canonical": "Ultrasound Kidneys Ureters and Bladder", "aliases": ["usg kub"], "category": "Imaging", "print": "USG KUB"}
USG_SLASH = {"entry_key": "usg/kub", "action": "add", "base_sha": "", "source": "admin",
             "data": {"name": "USG/KUB", "aliases": [], "category": "", "print": ""}}   # stored before the wider M1 rule


def test_a_set_aside_test_row_is_flagged_and_never_blocks_the_shipped_test():
    from doctor_dictation.core.investigations import remember_row
    entries, flags, blocked = overlay.effective_and_blocked("investigation", [USG], [USG_SLASH])
    assert entries == [USG] and blocked == frozenset() and flags == []        # tests match exactly: nothing to fuzzy-route
    item = next(i for i in overlay.screen_rows("investigation", [USG], [USG_SLASH], []) if i["entry_key"] == "usg/kub")
    assert item["flag"] == overlay.SHIPPED_CHANGED and "already on the list" in item["flag_reason"]   # seen, so it can be Reset
    edit = {"entry_key": overlay.entry_key_of(USG), "action": "edit", "base_sha": overlay.entry_sha(USG), "source": "admin",
            "data": {"aliases": ["usg kub", "sono kub"]}}
    assert overlay.conflicts("investigation", [USG], [USG_SLASH], edit) == []   # the shipped test is not frozen
    view = overlay.View(entries)
    view.blocked = blocked
    assert remember_row({"text": "Sono KUB", "canonical": "USG KUB", "status": "new", "source": "doctor"}, view, [USG])


def test_a_set_aside_medicine_row_is_still_blocked_and_flagged():
    shipped = [{"canonical": "Paracetamol", "aliases": [], "brands": ["Crocin"]}]
    row = {"kind": "medicine", "entry_key": "crocinol", "action": "add",
           "data": {"name": "Crocinol", "generic": "Crocin", "aliases": ["Crocinola"]}, "base_sha": ""}
    assert overlay.effective_and_blocked("medicine", shipped, [row])[2] == frozenset({"crocinol", "crocinola"})
    item = next(i for i in overlay.screen_rows("medicine", shipped, [row], []) if i["entry_key"] == "crocinol")
    assert item["flag"] == overlay.SHIPPED_CHANGED and item["flag_reason"]
