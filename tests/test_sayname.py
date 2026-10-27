from doctor_dictation.core.sayname import clean_said_name as clean

def test_spelled_letters_win():
    assert clean("Eltroxin, E-L-T-R-O-X-I-N") == "Eltroxin"
    assert clean("E L T R O X I N") == "Eltroxin"
    assert clean("tablet cello dial spelled S-I-L-O-D-A-L") == "Silodal"

def test_filler_before_the_name_is_stripped():
    assert clean("tablet Eltroxin") == "Eltroxin"
    assert clean("it is Eltroxin") == "Eltroxin"
    assert clean("the name is Eltroxin") == "Eltroxin"
    assert clean("um, capsule Omez") == "Omez"

def test_a_not_clause_is_dropped_wherever_it_stands():
    assert clean("it is Eltroxin, not L-thyroxine") == "Eltroxin"
    assert clean("not L-thyroxine, Eltroxin") == "Eltroxin"

def test_a_plain_name_passes_through_unchanged():
    assert [clean(t) for t in ("Eltroxin", "Dolo 650", "Thyronorm.", "  Pan 40 ")] == ["Eltroxin", "Dolo 650", "Thyronorm", "Pan 40"]

def test_filler_only_keeps_what_was_heard():
    assert clean("tablet") == "tablet" and clean("") == "" and clean(None) == ""

def test_letters_with_a_filler_word_before_them_read_as_a_name():
    assert clean("tablet E-L-T") == "Elt" and clean("U S G") == "U S G"

def test_a_respelled_name_after_no_wins():
    assert clean("Thyronorm, T-H-Y-R-O-N-O-R-M, no, Eltroxin E-L-T-R-O-X-I-N") == "Eltroxin"
