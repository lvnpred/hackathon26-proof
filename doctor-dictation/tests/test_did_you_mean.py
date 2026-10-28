"""Plan I2-a: lexicon spellings, the one suggestion list, and the inline Did you mean (a suggestion, never a rewrite)."""
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import override_settings
from doctor_dictation.core import formulary as F, rowcheck
from doctor_dictation.core.candidates import scored_spellings, suggest_candidates
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import _FORMAT_CACHE, validate_structured
from doctor_dictation.core.safety import screen_unverified

NONE = {"did_you_mean": "", "did_you_mean_generic": ""}

def test_scored_spellings_keep_a_brand_in_its_own_spelling(frozen_lexicon):
    assert [(s, c) for s, c, _sc in scored_spellings("croissin", 5)] == [("Crocin", "Paracetamol")]
    assert [(s, c) for s, c, _sc in scored_spellings("citrizene", 5)] == [("Cetirizine", "Cetirizine"), ("Ceftriaxone", "Ceftriaxone")]
    assert scored_spellings("the doctor", 5) == [] and scored_spellings("croissin", 0) == []
    assert suggest_candidates("croissin") == ["Paracetamol"]                  # the canonical list is unchanged (I1-r1)

def test_unknown_rows_carry_a_did_you_mean_from_the_first_authoring_and_stay_as_dictated(frozen_lexicon, monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    _FORMAT_CACHE.clear()
    j = TestClient(M.app).post("/api/format", json={"transcript": "tab citrizene 10 mg at night. tab croissin 500 mg sos. tab cetirizine 10 mg once daily"}).json()
    rows = j["structured"]["rx"]
    assert [(r["name"], r["status"], r["did_you_mean"], r["did_you_mean_generic"]) for r in rows] == [
        ("Citrizene", "unknown-medicine", "Cetirizine", "Cetirizine"),
        ("Croissin", "unknown-medicine", "Crocin", "Paracetamol"),
        ("Cetirizine", "verified", "", "")]
    assert "[unverified: confirm with doctor]" in rows[0]["instructions"]               # never renamed, never verified
    assert [b["index"] for b in screen_unverified(j["structured"], [])] == [0, 1]        # the Save gate still blocks both
    s, _w = validate_structured({"rx": [{"name": "Zzqxwv"}]}, "zzqxwv")
    assert {k: s["rx"][0][k] for k in NONE} == NONE                                      # nothing close: nothing offered

def test_the_inline_suggestion_needs_a_clear_winner_and_never_a_curated_twin(monkeypatch):
    def fake(opts):
        rowcheck._clear_dym_cache()                       # a faked source must not meet an answer cached from the real one
        monkeypatch.setattr(rowcheck, "_sound_options", lambda name, k, clinic=True, prefix_first=True: opts)
    fake([("Zorbexin", "Zorbexin", 0.95, "sounds"), ("Zorbexon", "Zorbexon", 0.93, "sounds")])
    assert rowcheck.did_you_mean("Zorbexn", "unknown-medicine") == NONE                  # 0.02 apart: the doctor picks
    fake([("Zorbexin", "Zorbexin", 0.95, "sounds"), ("Zorbexin Forte", "Zorbexin", 0.94, "sounds")])
    assert rowcheck.did_you_mean("Zorbexn", "unknown-medicine")["did_you_mean"] == "Zorbexin"   # the same generic is no rival
    fake([("Zorbexin", "Zorbexin", 0.89, "sounds")])
    assert rowcheck.did_you_mean("Zorbexn", "unknown-medicine") == NONE                  # under INLINE_MIN
    fake([("Prednisolone", "Prednisolone", 1.0, "sounds")])
    assert rowcheck.did_you_mean("Prednisolon", "unknown-medicine") == NONE              # a curated look-alike pair
    fake([("Zorbexin", "", 1.0, "clinic")])
    assert rowcheck.did_you_mean("Zorbexim", "unknown-medicine") == {"did_you_mean": "Zorbexin", "did_you_mean_generic": ""}
    for status in ("verified", "unverified-name", "lookalike-check", "dose-check", "unverified-strength", ""):
        assert rowcheck.did_you_mean("Zorbexn", status) == NONE
    assert (rowcheck.INLINE_MIN, rowcheck.INLINE_GAP, rowcheck.MAX_OPTIONS) == (0.9, 0.05, 40)

def test_options_carry_a_generic_and_a_reason_for_each_name(frozen_lexicon):
    F.activate(F.ClinicLayer((("Zorbexin", "Paracetamol"), ("Prednizone", ""))))   # Prednizone sounds like Prednisone
    try:
        opts, total = rowcheck.options({"name": "Prednisone", "lexicon_match": "Prednisone"})
        assert opts[:2] == [{"name": "Prednisone", "generic": "Prednisone", "reason": "matched"},
                            {"name": "Prednisolone", "generic": "Prednisolone", "reason": "lookalike"}] and total == len(opts)
        assert "Zorbexin" not in [o["name"] for o in opts]          # a matched row never offers clinic names (I1-r1 decision 3)
        assert "Prednizone" not in [o["name"] for o in opts]        # not even a clinic name that sounds like the match
        assert rowcheck.options({"name": "Zorbexim", "lexicon_match": ""})[0][0] == {"name": "Zorbexin", "generic": "Paracetamol", "reason": "clinic"}
        assert rowcheck.options({"name": "Croissin", "lexicon_match": ""})[0][0] == {"name": "Crocin", "generic": "Paracetamol", "reason": "sounds"}
    finally:
        F.activate(F.ClinicLayer())

def test_correct_and_save_recompute_the_did_you_mean_the_page_never_sends(frozen_lexicon):
    cur = {"rx": [{"name": "Citrizene", "status": "unknown-medicine", "lexicon_match": "", "instructions": "[unverified: confirm with doctor]"}]}
    fresh = {"name": "Citrizene", "status": "x", "lexicon_match": "x", "instructions": "", "did_you_mean": "STALE"}
    row = preserve_untouched_rx_status(cur, {}, {"rx": [fresh]})["rx"][0]
    assert (row["status"], row["did_you_mean"], row["did_you_mean_generic"]) == ("unknown-medicine", "Cetirizine", "Cetirizine")


# ---- fix round: one computation per row, and a cache that is never another clinic's or lexicon's ----
def _count(monkeypatch, module, attr):
    calls = []
    real = getattr(module, attr)
    monkeypatch.setattr(module, attr, lambda *a, **k: calls.append(a) or real(*a, **k))
    return calls

def test_one_row_costs_one_computation_for_both_fields(frozen_lexicon, monkeypatch):
    from doctor_dictation.core import correction
    rowcheck._clear_dym_cache()
    outer = _count(monkeypatch, correction, "did_you_mean")      # the call in preserve (once per row, not per field)
    inner = _count(monkeypatch, rowcheck, "_best_alike")          # the scoring pass behind it
    cur = {"rx": [{"name": "Citrizene", "status": "unknown-medicine", "lexicon_match": "", "instructions": ""}]}
    row = preserve_untouched_rx_status(cur, {}, {"rx": [{"name": "Citrizene", "status": "x", "lexicon_match": "x", "instructions": ""}]})["rx"][0]
    assert (row["did_you_mean"], row["did_you_mean_generic"]) == ("Cetirizine", "Cetirizine")
    assert len(outer) == 1 and len(inner) == 1

def test_a_cache_hit_equals_a_fresh_result_and_costs_no_scoring(frozen_lexicon, monkeypatch):
    rowcheck._clear_dym_cache()
    fresh = {n: rowcheck.did_you_mean(n, "unknown-medicine") for n in ("Citrizene", "Croissin", "Zzqxwv")}
    assert fresh["Citrizene"]["did_you_mean"] == "Cetirizine" and fresh["Croissin"]["did_you_mean"] == "Crocin"
    scoring = _count(monkeypatch, rowcheck, "_best_alike")
    for n, want in fresh.items():
        assert rowcheck.did_you_mean(n, "unknown-medicine") == want
        assert rowcheck.did_you_mean(n.upper() + "-", "unknown-medicine") == want   # same letters, same answer
    assert scoring == []                                                              # all hits
    got = rowcheck.did_you_mean("Citrizene", "unknown-medicine")
    got["did_you_mean"] = "TAMPERED"                                                  # a caller cannot poison the cache
    assert rowcheck.did_you_mean("Citrizene", "unknown-medicine")["did_you_mean"] == "Cetirizine"
    assert rowcheck.did_you_mean("Citrizene", "verified") == NONE                     # the status gate is outside the cache

def test_a_clinic_layer_or_lexicon_change_invalidates_the_cache(frozen_lexicon, monkeypatch):
    from doctor_dictation.core import determinism as D
    rowcheck._clear_dym_cache()
    assert rowcheck.did_you_mean("Zorbexen", "unknown-medicine") == NONE              # nothing close, cached
    F.activate(F.ClinicLayer((("Zorbexin", "Paracetamol"),)))
    try:
        assert rowcheck.did_you_mean("Zorbexen", "unknown-medicine") == {"did_you_mean": "Zorbexin", "did_you_mean_generic": "Paracetamol"}
        F.activate(F.ClinicLayer((("Zorbexin", "Ibuprofen"),)))                          # same name, another generic: a new layer
        assert rowcheck.did_you_mean("Zorbexen", "unknown-medicine")["did_you_mean_generic"] == "Ibuprofen"
    finally:
        F.activate(F.ClinicLayer())
    assert rowcheck.did_you_mean("Zorbexen", "unknown-medicine") == NONE              # back to the empty layer: not the clinic's answer
    scoring = _count(monkeypatch, rowcheck, "_best_alike")
    rowcheck.did_you_mean("Citrizene", "unknown-medicine")
    rowcheck.did_you_mean("Citrizene", "unknown-medicine")
    assert len(scoring) == 1
    monkeypatch.setattr(D, "_lexicon_cache", list(D.load_lexicon()))                  # a reloaded lexicon is a new list object
    rowcheck.did_you_mean("Citrizene", "unknown-medicine")
    assert len(scoring) == 2

def test_the_cache_is_bounded(frozen_lexicon):
    rowcheck._clear_dym_cache()
    for i in range(rowcheck._DYM_MAX + 40):
        rowcheck.did_you_mean(f"qq{chr(97 + i % 26)}{chr(97 + i // 26 % 26)}{chr(97 + i // 676)}x", "unknown-medicine")
    assert len(rowcheck._DYM_CACHE) <= rowcheck._DYM_MAX


def test_the_pruned_scan_gives_exactly_the_unpruned_result(frozen_lexicon):
    """scored_spellings skips rows whose upper bound is under MIN_SCORE; that must never change an answer."""
    import re
    from doctor_dictation.core import candidates as C
    from doctor_dictation.core.determinism import _maps

    def unpruned(name, k):
        low = re.sub(r"[^a-z]", "", name.lower())
        key = C.phonetic_key(low)
        if len(low) < 4 or len(key) < 3:
            return []
        shown, best = _maps()[0], {}
        for text, tkey, canon in C._rows():
            sc, spelling = C._score(low, key, text, tkey), shown.get(text, canon)
            if sc >= C.MIN_SCORE and sc > best.get(spelling, (0.0, ""))[0]:
                best[spelling] = (sc, canon)
        ranked = sorted(best.items(), key=lambda kv: (-round(kv[1][0], 6), kv[0].lower(), kv[0]))
        return [(s, c, sc) for s, (sc, c) in ranked[:k]]
    spellings = [t for t, _k, _c in C._rows()][::9]
    probes = spellings + [w[:-1] + "x" for w in spellings[::2]] + [w[1:] for w in spellings[::3]] + ["citrizene", "croissin", "zorbexim"]
    assert len(probes) > 150
    assert [r for r in probes if scored_spellings(r, 50) != unpruned(r, 50)] == []


# ---- final fix minor (a): the inline path wants a name of 6+ letters, a TEXT likeness >= INLINE_TEXT and no longer name the typed one is the start of
def test_the_inline_guards_on_fake_options(monkeypatch):
    def fake(opts):
        rowcheck._clear_dym_cache()
        monkeypatch.setattr(rowcheck, "_sound_options", lambda name, k, clinic=True, prefix_first=True: opts)
    fake([("Pirox", "Piroxicam", 1.0, "sounds")])
    assert rowcheck.did_you_mean("Pirexx", "unknown-medicine") == NONE                   # 5 letters: too short to suggest alone
    fake([("Zorbexin", "Zorbexin", 1.0, "sounds")])
    assert rowcheck.did_you_mean("Qlmzvt", "unknown-medicine") == NONE                   # a high sound score, no likeness in the letters
    assert rowcheck.did_you_mean("Zorbexn", "unknown-medicine")["did_you_mean"] == "Zorbexin"
    fake([("Hytrol", "Enalapril", 0.98, "sounds"), ("Hydralazine", "Hydralazine", 0.88, "sounds")])
    assert rowcheck.did_you_mean("hydral", "unknown-medicine") == NONE                   # the typed name starts a longer name: incomplete, not wrong
    fake([("Zorbexin", "Zorbexin", 1.0, "sounds"), ("Zorbexinol", "Zorbexinol", 0.7, "sounds")])
    assert rowcheck.did_you_mean("Zorbexi", "unknown-medicine") == NONE                  # likewise, whatever the other name scores


def test_mutated_names_that_used_to_get_a_wrong_suggestion_get_none_on_the_live_lexicon():
    for typed in ("Vimoat", "Brili", "Paroxe", "Trile", "hydral"):           # Vymada, Prolia, Pirox, Detrol, Hytrol (which hid Hydralazine)
        assert rowcheck.did_you_mean(typed, "unknown-medicine") == NONE, typed
    assert rowcheck.did_you_mean("citrizene", "unknown-medicine")["did_you_mean"] == "Cetirizine"
    assert rowcheck.did_you_mean("croissin", "unknown-medicine")["did_you_mean"] == "Crocin"
    assert rowcheck.did_you_mean("amlodipin", "unknown-medicine")["did_you_mean"] == "Amlodipine"


# ---- final fix minor (b): names that start with the typed letters come first; the usage tie-break and clinic order are intact
def test_names_that_start_with_the_typed_letters_list_first(frozen_lexicon):
    names = [o[0] for o in rowcheck._sound_options("paracet", 10)]
    assert names[:2] == ["Paracetamol", "Prasita"]                                       # was Prasita (0.94) before Paracetamol (0.91)
    assert [o[0] for o in rowcheck._sound_options("paracet", 10, prefix_first=False)][:2] == ["Prasita", "Paracetamol"]
    assert [o[0] for o in rowcheck._sound_options("cetr", 4)][:2] == ["Ceftriaxone", "Cetirizine"]   # nothing starts with "cetr": the score order stays
    layer = F.ClinicLayer((("Paracetol", ""), ("Paracetin", "")), (("paracetin", 5.0),))
    F.activate(layer)
    try:
        got = [(o[0], o[3]) for o in rowcheck._sound_options("paracet", 10)]
        assert [n for n, _r in got].index("Paracetamol") < [n for n, _r in got].index("Prasita")
        clinic = [n for n, r in got if r == "clinic"]
        assert clinic == ["Paracetin", "Paracetol"] or clinic == ["Paracetol", "Paracetin"]
    finally:
        F.activate(F.ClinicLayer())


def test_the_inline_path_ranks_by_sound_alone_and_a_longer_name_of_the_same_generic_is_no_objection(monkeypatch):
    seen = []
    rowcheck._clear_dym_cache()
    monkeypatch.setattr(rowcheck, "_sound_options", lambda name, k, clinic=True, prefix_first=True:
                        seen.append(prefix_first) or [("Zorbexin", "Zorbexin", 1.0, "sounds"), ("Zorbexinol", "Zorbexin", 0.7, "sounds")])
    assert rowcheck.did_you_mean("Zorbexi", "unknown-medicine")["did_you_mean"] == "Zorbexin"   # the longer name is the same generic: no objection
    assert seen == [False]                                                                       # the Spell it reorder never decides the inline suggestion
