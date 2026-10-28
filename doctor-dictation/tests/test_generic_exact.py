from doctor_dictation.core import determinism as D
from doctor_dictation.core.combo import COMBO_SUFFIXES, combo_suffix

def test_exact_lookup_matches_brand_alias_and_generic_only():
    assert D._exact_lookup("Crocin") == "Paracetamol" and D._exact_lookup("  crocin. ") == "Paracetamol"
    assert D._exact_lookup("Amlo") == "Amlodipine" and D._exact_lookup("Cetirizine") == "Cetirizine"
    assert D._exact_lookup("Crocinn") == "" and D._exact_lookup("Zerodol-P") == "" and D._exact_lookup("") == ""
    assert D._canonical_lookup("Zerodol-P") == "Aceclofenac"          # fuzzy stays, for suggestions

def test_exact_lookup_ignores_space_versus_hyphen():
    assert D._exact_lookup("Moxikind CV") == D._exact_lookup("Moxikind-CV") == "Co-Amoxiclav"
    assert D._exact_lookup("Taxim O") == "Cefixime"

def test_combo_suffix_detects_the_spec_probe_and_a_trailing_strength():
    assert combo_suffix("Zerodol-P") == ("Zerodol", "P") and combo_suffix("zerodol p") == ("zerodol", "p")
    assert combo_suffix("Pantop-D") == ("Pantop", "D") and combo_suffix("Glycomet-GP") == ("Glycomet", "GP")
    assert combo_suffix("Amlong-A") == ("Amlong", "A") and combo_suffix("Ecosprin-AV") == ("Ecosprin", "AV")
    assert combo_suffix("Glycomet-GP 1") == ("Glycomet", "GP") and combo_suffix("Glycomet GP2") == ("Glycomet", "GP")
    assert combo_suffix("Zerodol Forte") == ("Zerodol", "Forte")

def test_combo_suffix_ignores_generic_bases_short_tails_and_unknown_suffixes():
    for name in ("Metformin SR", "Paracetamol-P", "Zerodol", "Zerodol-Q", "Dolo-650", "Zzqxwv-P", "", "P", "Kidrich-D3"):
        assert combo_suffix(name) is None, name

def test_no_shipped_brand_or_alias_is_flagged_as_a_combination():
    names = [n for e in D.load_lexicon() for n in [*e.get("brands", []), *e.get("aliases", [])]]
    assert [n for n in names if combo_suffix(n)] == []
    assert {"p", "d", "gp", "av", "cv", "xt", "lc", "am", "h", "plus", "forte", "mr", "sr", "a"} <= COMBO_SUFFIXES


from doctor_dictation.core import rowcheck
from doctor_dictation.core.determinism import ground_rx, validate_structured

def _row(name, text=None):
    out, _w = validate_structured({"rx": [{"form": "Tab.", "name": name, "dose": "1-0-1"}]}, text or f"tab {name.lower()}")
    return out["rx"][0]

def test_exact_match_shows_the_generic_with_source_lexicon():
    r = _row("Crocin")
    assert (r["generic"], r["generic_source"], r["combo_base"]) == ("Paracetamol", "lexicon", "")

def test_fuzzy_match_keeps_the_match_but_no_generic():
    r = _row("Crocinn", "tab crocinn")
    assert (r["status"], r["lexicon_match"], r["generic"], r["generic_source"]) == ("verified", "Paracetamol", "", "")
    assert _row("Metformin SR")["generic"] == ""

def test_spec_probe_rows_get_no_generic_and_a_combo_base():
    for name, base in (("Zerodol-P", "Zerodol"), ("Pantop-D", "Pantop"), ("Glycomet-GP", "Glycomet"),
                       ("Amlong-A", "Amlong"), ("Ecosprin-AV", "Ecosprin")):
        r = _row(name)
        assert (r["status"], r["lexicon_match"], r["generic"], r["generic_source"], r["combo_base"]) == \
            ("unknown-medicine", "", "", "", base), name

def test_combination_row_raises_no_repair_issue_and_no_did_you_mean():
    rows, issues = ground_rx([{"name": "Zerodol-P"}], "tab zerodol p")
    assert issues == [] and rows[0]["generic"] == "" and rows[0]["combo_base"] == "Zerodol"
    assert _row("Zerodol-P")["did_you_mean"] == ""
    assert rowcheck.did_you_mean("Zerodol-P", "unknown-medicine") == {"did_you_mean": "", "did_you_mean_generic": ""}

def test_generic_hidden_still_hides_and_a_known_combination_entry_still_prints_in_full():
    assert (_row("Feronia-XT")["generic"], _row("Feronia-XT")["lexicon_match"]) == ("", "Ferrous Ascorbate")
    assert _row("Ultracet")["generic"] == "Tramadol + Paracetamol" and _row("Moxikind CV")["generic"] == "Co-Amoxiclav"


# ---- final fix wave ----
import time
from doctor_dictation.core import combo

def test_unicode_dashes_count_as_a_hyphen():
    for dash in ("‐", "‑", "‒", "–", "—", "―", "−"):
        assert combo_suffix(f"Zerodol{dash}P") == ("Zerodol", "P"), repr(dash)
        assert D._exact_lookup(f"Moxikind{dash}CV") == "Co-Amoxiclav", repr(dash)

def test_en_dash_combination_row_is_unknown_with_combo_base():
    for dash in ("–", "—"):
        r = _row(f"Zerodol{dash}P")
        assert r["status"] == "unknown-medicine" and r["combo_base"] == "Zerodol" and r["generic"] == "", dash

def test_alias_map_is_cached_per_lexicon_list(monkeypatch):
    a = D._alias_map()
    assert D._alias_map() is a
    lex1 = D.load_lexicon()
    sep1, canon1 = D._sep_map(lex1, a), combo._canonical_names(lex1)
    assert D._sep_map(lex1, a) is sep1 and combo._canonical_names(lex1) is canon1
    monkeypatch.setattr(D, "_lexicon_cache", list(D.load_lexicon()))
    b = D._alias_map()
    assert b is not a and b == a and D._alias_map() is b
    lex2 = D.load_lexicon()
    assert D._sep_map(lex2, b) is not sep1 and combo._canonical_names(lex2) is not canon1

def test_inline_dym_does_not_steer_a_combination_back_to_its_head():
    for name in ("Zerodal-P", "Shelcal-HD", "Augmentin Duo", "Zerodal–P"):
        assert rowcheck.did_you_mean(name, "unknown-medicine")["did_you_mean"] == "", name

def test_inline_dym_still_fixes_plain_misspellings_and_strength_tails():
    assert rowcheck.did_you_mean("Crocinn", "unknown-medicine")["did_you_mean"] != ""
    assert not rowcheck._steers_to_head("Dolo 650", {"did_you_mean": "Dolo"})      # a strength is not a tail
