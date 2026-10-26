"""Plan SH-H4: find the patient a dictation names (contract 5.6, owner decision 7). Pure and offline."""
from doctor_dictation.core.patientctx import AGE_SLACK, match_patient, patient_of, sex_letter


def p(pid, name, age_sex="", op_no=None):
    return {"id": pid, "name": name, "age_sex": age_sex, "op_no": op_no}


def test_the_sex_letter_reads_every_way_the_sheet_writes_it():
    assert [sex_letter(s) for s in ("45 / M", "45 / F", "45Y/M", "45 / Male", "Female", "45 M", "6 months / F")] == \
        ["M", "F", "M", "M", "F", "M", "F"]
    assert [sex_letter(s) for s in ("", "45", None, 45)] == ["", "", "", ""] and AGE_SLACK == 1


def test_only_the_exact_name_matches_after_casefolding_and_collapsing_spaces():
    pool = [p(1, "Suresh Babu", "40 / M"), p(2, "Asha Verma", "34 / F")]
    assert match_patient("", "  suresh   BABU ", "40 / M", pool) == (1,)
    assert match_patient("", "Usha Verma", "34 / F", pool) == ()             # one letter off is someone else
    assert match_patient("", "Suresh Baabu", "40 / M", pool) == match_patient("", "Suresh", "40 / M", pool) == ()


def test_rows_with_the_same_name_age_and_sex_are_one_person_and_two_people_are_nobody():
    same = [p(1, "Ravi Kumar", "40 / M"), p(2, "ravi  kumar", "40 / M"), p(3, "Asha Verma", "34 / F")]
    assert match_patient("", "Ravi Kumar", "40 / M", same) == match_patient("", "Ravi Kumar", "", same) == (1, 2)
    apart = [p(1, "Ravi Kumar", "40 / M"), p(2, "Ravi Kumar", "50 / M")]
    assert match_patient("", "Ravi Kumar", "", apart) == match_patient("", "Ravi Kumar", "45 / M", apart) == ()
    assert match_patient("", "Ravi Kumar", "40 / M", apart) == (1,)          # the dictated age tells them apart
    assert match_patient("", "Ravi Kumar", "40 / M", [p(1, "Ravi Kumar", "40 / M"), p(2, "Ravi Kumar", "")]) == ()


def test_age_and_sex_rule_a_candidate_out_only_when_both_sides_give_them():
    ravi = [p(1, "Ravi Kumar", "40 / M")]
    assert match_patient("", "Ravi Kumar", "42 / M", ravi) == ()                # two years apart
    assert match_patient("", "Ravi Kumar", "39 / M", ravi) == (1,)
    assert match_patient("", "Ravi Kumar", "40 / F", ravi) == ()                # the other sex
    assert match_patient("", "Ravi Kumar", "", ravi) == match_patient("", "Ravi Kumar", "M", ravi) == (1,)
    assert match_patient("", "Ravi Kumar", "40 / M", [p(1, "Ravi Kumar", "")]) == (1,)     # stored without age_sex


def test_an_op_number_match_wins_and_a_shared_op_narrows_the_name_rule():
    pool = [p(1, "Ravi Kumar", "40 / M", "RAO-0007"), p(2, "Somebody Else", "", "RAO-0008"), p(3, "Ravi Kumar", "40 / M")]
    assert match_patient("RAO-0007", "Somebody Else", "", pool) == (1, 3)     # the OP wins; his other row comes too
    assert match_patient(" RAO-0007 ", "", "", pool) == (1, 3)                 # trimmed; no name needed
    assert match_patient("rao-0007", "", "", pool) == ()                       # exact: case counts
    assert match_patient("RAO-0099", "Ravi Kumar", "40 / M", pool) == (1, 3)   # an unknown OP: the name rule
    shared = [p(1, "Ravi Kumar", "40 / M", "OP 5"), p(2, "Asha Verma", "34 / F", "OP 5"), p(3, "Ravi Kumar", "70 / M", "OP 6")]
    assert match_patient("OP 5", "Ravi Kumar", "", shared) == (1,)             # among the OP's patients only
    assert match_patient("OP 5", "", "", shared) == ()


def test_blank_or_short_input_matches_nobody_and_patient_of_reads_the_sheet():
    assert match_patient("", "", "", [p(1, "", "")]) == () and match_patient("", "Al", "", [p(1, "Al", "")]) == ()
    assert match_patient("", "Ravi Kumar", "40 / M", []) == () and match_patient(None, None, None, None) == ()
    assert patient_of({"patientName": "Ravi Kumar", "ageSex": "40 / M", "opNo": "OP 5", "rx": []}) == \
        {"name": "Ravi Kumar", "age_sex": "40 / M", "op_no": "OP 5"}
    assert patient_of({"patientName": 7}) == patient_of(None) == {"name": "", "age_sex": "", "op_no": ""}


def test_rows_a_birthday_apart_are_one_person_and_two_years_apart_are_not():
    pool = [p(1, "Suresh Babu", "40 / M"), p(2, "suresh babu", "41 / M"), p(3, "Asha Verma", "34 / F")]
    assert [match_patient("", "Suresh Babu", d, pool) for d in ("40 / M", "41 / M", "", "M")] == [(1, 2)] * 4
    assert match_patient("", "Ravi Kumar", "41 / M", [p(1, "Ravi Kumar", "40 / M"), p(2, "Ravi Kumar", "42 / M")]) == ()
    assert match_patient("", "Ravi Kumar", "", [p(1, "Ravi Kumar", "40 / M"), p(2, "Ravi Kumar", "41 / F")]) == ()
    unknown = [p(1, "Ravi Kumar", "40 / M"), p(2, "Ravi Kumar", "41 / M"), p(3, "Ravi Kumar", "")]
    assert match_patient("", "Ravi Kumar", "40 / M", unknown) == ()
    op = [p(1, "Suresh Babu", "40 / M", "OP 9"), p(2, "Suresh Babu", "41 / M", "OP 9"), p(3, "Suresh Babu", "41 / M")]
    assert match_patient("OP 9", "", "", op) == (1, 2, 3)
