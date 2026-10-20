from doctor_dictation.api.format import SYSTEM_PROMPT
from doctor_dictation.core import promptrules as R
from doctor_dictation.core.correction import CORRECTION_INSTRUCTION


def test_every_shared_rule_is_in_both_prompts():
    assert len(R.SHARED_RULES) == 5
    for rule in R.SHARED_RULES:
        assert rule in SYSTEM_PROMPT and rule in CORRECTION_INSTRUCTION, rule


def test_rule_text_carries_the_spec_wording():
    assert 'If no form was dictated, use ""' in R.FORM_RULE
    assert "exactly one section" in R.ONE_SECTION_RULE
    assert "Never repeat the patient name, age, sex or vitals" in R.NO_DEMOGRAPHICS_RULE
    assert "Never add a test that was not dictated" in R.INVESTIGATIONS_RULE and "return []" in R.INVESTIGATIONS_RULE
    assert '"X-ray, CT and MRI of head and hip" is one item' in R.INVESTIGATIONS_RULE


def test_rules_text_numbers_from_start():
    assert R.rules_text(8).splitlines()[0].startswith("8. form:") and R.rules_text(8).splitlines()[4].startswith("12. vitals:")


def test_format_schema_has_vitals_and_an_empty_form():
    schema = SYSTEM_PROMPT[SYSTEM_PROMPT.index("{\n"):]
    assert '"vitals": {"bp": "string", "pulse": "string", "weight": "string", "spo2": "string", "temp": "string"}' in schema
    assert '"form": "Tab.|Cap.|Syr.|Inj.|empty"' in schema
    assert schema.index('"opNo"') < schema.index('"vitals"') < schema.index('"complaints"')


def test_correction_prompt_patches_one_vital():
    assert 'return only the vitals the correction states, for example {"vitals": {"bp": "130/80"}}' in CORRECTION_INSTRUCTION


PATCH_SCOPE_LINE = ('Rules 10-14 apply only to the fields the doctor states in this correction. '
                    'Never send "" or [] to clear a field the doctor did not mention: leave it out.')


def test_correction_prompt_scopes_shared_rules_to_stated_fields():
    assert PATCH_SCOPE_LINE in CORRECTION_INSTRUCTION
    assert PATCH_SCOPE_LINE not in SYSTEM_PROMPT
    assert CORRECTION_INSTRUCTION.index(PATCH_SCOPE_LINE) < CORRECTION_INSTRUCTION.index("10. form:")
