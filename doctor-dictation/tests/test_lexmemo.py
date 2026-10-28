"""per_lexicon: identity-keyed, few-slot, race-free lexicon caches (plan PQ-f Task 4, Review Focus 1)."""
import sys
import threading

import pytest

from doctor_dictation.core import candidates, combo, lasa, overlay_state, surface
from doctor_dictation.core import determinism as D
from doctor_dictation.core.lexmemo import MAX_SLOTS, per_lexicon


def _counting():
    calls = []

    def build(tag):
        def run():
            calls.append(tag)
            return {"built": tag}
        return run
    return calls, build


def test_same_list_builds_once():
    slot, lex = {}, [{"canonical": "A"}]
    calls, build = _counting()
    first = per_lexicon(slot, lex, build("a"))
    assert per_lexicon(slot, lex, build("a")) is first and calls == ["a"]


def test_equal_content_new_list_rebuilds():
    slot = {}
    calls, build = _counting()
    a, b = [{"canonical": "A"}], [{"canonical": "A"}]
    assert a == b and a is not b
    va, vb = per_lexicon(slot, a, build("a")), per_lexicon(slot, b, build("b"))
    assert calls == ["a", "b"] and va is not vb
    assert per_lexicon(slot, a, build("a")) is va and per_lexicon(slot, b, build("b")) is vb


def test_one_list_past_max_slots_evicts_the_oldest():
    slot = {}
    calls, build = _counting()
    lists = [[{"canonical": str(i)}] for i in range(MAX_SLOTS + 1)]
    for i, lex in enumerate(lists):
        per_lexicon(slot, lex, build(i))
    assert len(slot) == MAX_SLOTS and MAX_SLOTS == 32 == overlay_state.MAX_VIEWS   # as many lists as overlay views
    for i in range(1, MAX_SLOTS + 1):                      # the newer ones still hit
        per_lexicon(slot, lists[i], build(i))
    assert calls == list(range(MAX_SLOTS + 1))
    per_lexicon(slot, lists[0], build(0))                  # the first one was dropped
    assert calls[-1] == 0 and len(calls) == MAX_SLOTS + 2


def test_a_hit_counts_as_recent_use():
    slot = {}
    calls, build = _counting()
    lists = [[{"canonical": str(i)}] for i in range(MAX_SLOTS + 1)]
    for i in range(MAX_SLOTS):
        per_lexicon(slot, lists[i], build(i))
    per_lexicon(slot, lists[0], build(0))                  # touch the oldest
    per_lexicon(slot, lists[MAX_SLOTS], build(MAX_SLOTS))  # evicts list 1, not list 0
    per_lexicon(slot, lists[0], build(0))
    assert calls.count(0) == 1
    per_lexicon(slot, lists[1], build(1))
    assert calls.count(1) == 2


def _entry(canon, brands=(), aliases=(), hidden=()):
    return {"canonical": canon, "aliases": list(aliases), "brands": list(brands), "forms": [], "strengths": [],
            **({"generic_hidden": list(hidden)} if hidden else {})}


SHIPPED = [_entry("Paracetamol", ["Crocin", "Dolo"], ["pcm"]), _entry("Aceclofenac", ["Zerodol", "Hifenac"]),
           _entry("Pantoprazole", ["Pantop"], ["panto"])]
CLINIC = SHIPPED + [_entry("Zyqorinib", ["Zyqorlex"], ["zyq-max"], hidden=["Zyqorlex"]), _entry("Zyqorinab", ["Zyqorabex"])]


def _reset_slots():
    for s in (D._alias_slot, D._maps_slot, D._sep_slot, combo._canon_slot, surface._hidden_slot, lasa._slot,
              candidates._slot):
        s.clear()


@pytest.fixture
def two_lists(monkeypatch):
    """load_lexicon returns this thread's list (``use(lex)``), the same trick Task 5's ContextVar plays per request."""
    local = threading.local()
    shipped, clinic = [dict(e) for e in SHIPPED], [dict(e) for e in CLINIC]

    def use(lex):
        local.lex = lex
    monkeypatch.setattr(D, "load_lexicon", lambda: getattr(local, "lex", shipped))
    _reset_slots()
    yield shipped, clinic, use
    _reset_slots()


def test_alternating_lexicons_do_not_rebuild(two_lists, monkeypatch):
    shipped, clinic, use = two_lists
    built = []
    real = D.surface_map
    monkeypatch.setattr(D, "surface_map", lambda lex, amap: built.append(lex) or real(lex, amap))
    for lex in (shipped, clinic, shipped):
        use(lex)
        amap = D._maps()[0]
        assert ("zyqorlex" in amap) is (lex is clinic)
        assert surface._hidden_brands(lex) == (frozenset({"zyqorlex"}) if lex is clinic else frozenset())
        assert ("zyqorinib" in lasa._index()["by_low"]) is (lex is clinic)
        assert any(c == "Zyqorinib" for _t, _k, c in candidates._rows()) is (lex is clinic)
    assert len(built) == 2 and built[0] is shipped and built[1] is clinic


def _observe(lex, clinic) -> list:
    """Every lexicon-cached lookup, as (what, got, expected) for the list this thread runs under."""
    mine = lex is clinic
    return [
        ("alias", D._alias_map().get("zyqorlex"), "Zyqorinib" if mine else None),
        ("maps", "zyqorlex" in D._maps()[0], mine),
        ("sep", D._exact_lookup("Zyq Max"), "Zyqorinib" if mine else ""),
        ("exact2", D._exact_lookup("Zyqorlex"), "Zyqorinib" if mine else ""),
        ("combo", combo.combo_suffix("Zyqorlex-P"), ("Zyqorlex", "P") if mine else None),
        ("hidden", surface.generic_hidden("Zyqorlex", "Zyqorinib"), mine),
        ("lasa", lasa.twins("Zyqorinib"), ["Zyqorinab"] if mine else []),
        ("cand", any(c == "Zyqorinib" for _t, _k, c in candidates._rows()), mine),
    ]


def test_interleaved_threads_each_see_their_own_list(two_lists):
    shipped, clinic, use = two_lists
    wrong, errors = [], []
    start = threading.Barrier(12)

    def worker(n):
        try:
            start.wait()
            for i in range(150):
                lex = clinic if (i + n) % 2 else shipped
                use(lex)
                wrong.extend((n, i, *o) for o in _observe(lex, clinic) if o[1] != o[2])
        except Exception as err:          # noqa: BLE001  (surface any crash as a failure, not a hung thread)
            errors.append(repr(err))
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)           # switch threads as often as possible: widen any check-then-read window
    try:
        threads = [threading.Thread(target=worker, args=(n,)) for n in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old)
    assert not errors and not wrong, (errors[:3], wrong[:5])
    assert len(D._alias_slot) == 2 and len(lasa._slot) == 2    # both lists stay cached: no rebuild per switch
