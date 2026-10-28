"""Prompt rules shared by the format prompt and the correction prompt, written once (plan PQ-d). Stdlib only."""

FORM_RULE = ('form: use the form as dictated ("tablet" -> "Tab.", "capsule" -> "Cap.", "syrup" -> "Syr.", '
             '"injection" -> "Inj."). If no form was dictated, use "". Never guess a form from the medicine name.')
ONE_SECTION_RULE = "Each item goes into exactly one section: never put the same text in two of complaints, findings and diagnosis."
NO_DEMOGRAPHICS_RULE = ("Never repeat the patient name, age, sex or vitals in complaints, findings, diagnosis or advice; "
                        "they go only in patientName, ageSex and vitals.")
INVESTIGATIONS_RULE = ("investigations: copy each test as dictated. Never add a test that was not dictated. If none "
                       'was dictated, return []. Tests that share a body site stay one item: "X-ray, CT and MRI of '
                       'head and hip" is one item, not three.')
VITALS_RULE = ('vitals: copy only the vitals dictated, with digits: bp "140/90", pulse "88/min", weight "72 kg", '
               'spo2 "98%", temp "101 F". Use "" for each vital not dictated.')

SPELLED_RULE = ("If the doctor spells a word letter by letter, write the spelled word: it replaces the spoken word "
                "before it.")

SHARED_RULES = (FORM_RULE, ONE_SECTION_RULE, NO_DEMOGRAPHICS_RULE, INVESTIGATIONS_RULE, VITALS_RULE)


def rules_text(start: int) -> str:
    """The shared rules as a numbered list starting at `start`, one per line, no trailing newline."""
    return "\n".join(f"{start + i}. {rule}" for i, rule in enumerate(SHARED_RULES))
