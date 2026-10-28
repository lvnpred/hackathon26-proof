import pytest

from doctor_dictation.core.patientswitch import other_patient, said_patient, same_person

SHEET = {"name": "Suresh Babu", "age_sex": "40 / M", "op_no": "OP-20261026-002"}


def test_said_patient_reads_labels_and_a_leading_name_only():
    assert said_patient("Next patient Ravi Kumar, 45 years male, fever 3 days") == {"name": "Ravi Kumar", "op_no": ""}
    assert said_patient("Ravi Kumar 45 years male with fever")["name"] == "Ravi Kumar"
    assert said_patient("name is ravi kumar, cough")["name"] == "Ravi Kumar"
    assert said_patient("Mrs. Asha Verma, add tab Dolo")["name"] == "Asha Verma"
    for t in ("refer to Dr Ravi Kumar", "patient is complaining of cough", "fever since 3 years", "add tab Dolo 650", ""):
        assert said_patient(t)["name"] == "", t
    assert said_patient("OP number 7, add cough syrup")["op_no"] == "7"


def test_name_variants_of_one_person_are_the_same_person():
    for said in ("Suresh", "suresh  babu", "S. Babu", "Mr Suresh Babu", "Babu", "SURESH B"):
        assert same_person(said, "Suresh Babu"), said
    for said in ("Ravi Kumar", "Suresh Kumar", "Suresh Baboo"):
        assert not same_person(said, "Suresh Babu"), said
    assert same_person("", "Suresh Babu")


def test_a_transcript_or_a_patch_naming_someone_else_is_another_patient():
    assert other_patient("Next patient Ravi Kumar, 45 years male, fever", SHEET, {}) == {"name": "Ravi Kumar", "op_no": ""}
    assert other_patient("add tab Dolo 650", SHEET, {"patientName": "Ravi Kumar"}) == {"name": "Ravi Kumar", "op_no": ""}
    assert other_patient("OP 7, add tab Dolo", SHEET, {}) == {"name": "", "op_no": "7"}
    assert other_patient("add tab Dolo", SHEET, {"opNo": "OP-20261026-007"}) == {"name": "", "op_no": "OP-20261026-007"}


def test_the_same_patient_a_blank_sheet_or_nothing_said_never_asks():
    assert other_patient("Suresh, add tab Dolo 650", SHEET, {"patientName": "Suresh"}) is None
    assert other_patient("patient S. Babu, OP 2, stop the syrup", SHEET, {}) is None   # "2" is the sheet OP's tail
    assert other_patient("patient Ravi Kumar, fever", {"name": "", "age_sex": "", "op_no": ""}, {}) is None
    assert other_patient("add tab Dolo", SHEET, {}) is None


def test_intent_words_skip_the_check():
    for t in ("correct this, patient name is Ravi Kumar", "Update: patient Ravi Kumar", "same patient, Ravi Kumar",
              "change the patient's name to Ravi Kumar", "Correction, named Ravi Kumar"):
        assert other_patient(t, SHEET, {"patientName": "Ravi Kumar"}) is None, t


def test_a_patch_name_wins_the_label_when_both_name_someone():
    assert other_patient("patient Ravi, fever", SHEET, {"patientName": "Ravi Kumar"}) == {"name": "Ravi Kumar", "op_no": ""}


def test_weak_label_needs_a_capitalised_name_and_clinical_words_never_name_anyone():
    for t in ("patient denies chest pain", "patient is diabetic", "patient reports headache", "patient hba1c high",
              "patient is hypertensive", "patient feels better", "patient needs review", "do not miss evening dose"):
        assert other_patient(t, SHEET, {}) is None, t
    assert other_patient("patient is Ramesh, fever", SHEET, {}) == {"name": "Ramesh", "op_no": ""}
    assert other_patient("patient name is lakshmi, fever", SHEET, {}) == {"name": "Lakshmi", "op_no": ""}
    assert other_patient("Mrs Lakshmi, add tab Dolo", SHEET, {}) == {"name": "Lakshmi", "op_no": ""}


@pytest.mark.parametrize("t", [
    "Give the patient Dolo 650", "Give patient Dolo 650", "Patient BP 130/80", "Patient RBS 140", "Patient CBC normal",
    "Diabetes 10 years, add Metformin", "Hypertension 5 years", "Smoker 20 years",
    "the tablet name is Thyronorm", "medicine name is Eltroxin", "Post op 5 days, review", "patient Metformin 500",
    "Don't miss Metformin",
])
def test_routine_dictation_never_names_another_patient(t):
    assert other_patient(t, SHEET, {}) is None


@pytest.mark.parametrize("t", [
    "Next patient, Ravi Kumar, 45 years male.", "Next patient. Ravi Kumar, 45 years", "Next patient: Ravi Kumar",
    "Patient name: Ravi Kumar", "next patient ravi kumar 45 years",
])
def test_a_next_patient_label_with_punctuation_or_lower_case_still_names_them(t):
    assert other_patient(t, SHEET, {}) == {"name": "Ravi Kumar", "op_no": ""}


def test_existing_labels_still_name_the_patient():
    assert said_patient("Ramesh 40 years")["name"] == "Ramesh"
    assert said_patient("mr. Ramesh kumar 40 years")["name"] == "Ramesh Kumar"
    assert said_patient("Patient Ravi Kumar, 45 years male")["name"] == "Ravi Kumar"


def test_next_patient_with_only_an_op_number_names_no_one():
    assert said_patient("Next patient OP 15") == {"name": "", "op_no": "15"}
    assert other_patient("Next patient OP 15", SHEET, {}) == {"name": "", "op_no": "15"}
