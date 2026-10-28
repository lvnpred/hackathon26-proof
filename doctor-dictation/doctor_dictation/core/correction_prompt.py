"""The LLM prompt for a spoken correction: the system instruction and the message list.

Split out of ``correction.py`` (kept under the 500-line limit); ``correction`` re-exports both names.
"""
import json

from .promptrules import SPELLED_RULE, rules_text

_HIDDEN = ("generic_suggestion", "generic_suggestion_unknown", "generic_pending", "typed_heard")

CORRECTION_INSTRUCTION = (
    "You are applying a spoken correction to an existing prescription form. "
    "Change ONLY what this correction states; leave every other field "
    "byte-identical. Return ONLY a JSON object containing the fields that "
    "change, using the same schema as the form. If the correction changes "
    "nothing, return {}.\n"
    "RULES:\n"
    '1. Every rx row you return MUST include "name": the medicine the correction '
    "is about, copied from the current form with its exact spelling. If the doctor "
    "refers to a medicine, find it in the current form and use that name. "
    "A medicine that is not on the current form is a NEW row: use the name the "
    "doctor dictated. " + SPELLED_RULE + " Never return an rx row without a name. A brand and its generic are the "
    "same medicine (Zyloric is Allopurinol): when the doctor names the other one, use the name "
    "on the current form.\n"
    '2. Allowed dose codes ONLY: "1-0-0", "1-0-1", "1-1-1", "0-0-1", "SOS". '
    "Map: once daily/OD -> 1-0-0; twice daily/BD -> 1-0-1; thrice daily/TDS -> 1-1-1; "
    "at bedtime/HS -> 0-0-1; as needed/for pain -> SOS.\n"
    '3. Allowed timing ONLY: "After food", "Before food", "At bedtime", or "".\n'
    '4. ageSex format is "<age> / <M|F>", for example "45 / M".\n'
    '5. Duration format: "<N> days/weeks/months" with digits; two weeks -> 14 days.\n'
    "6. Never invent strengths, durations or drugs. Return only fields the doctor stated.\n"
    '7. A list section (complaints, findings, diagnosis, investigations, advice) keeps its items: return in it ONLY the '
    'new items the correction adds ("also", "add", "update ... as" add items). To CHANGE an existing item use "replace" '
    'and to DELETE one use "remove", only when the doctor names that item. '
    'To REMOVE something add a top-level "remove" object: {"rx": ["<row name>"], '
    '"diagnosis": [], "complaints": [], "findings": [], "investigations": [], "advice": []} '
    "(list the exact text of each item to delete). To CHANGE the name or text of one "
    'existing row/item add a top-level "replace" object: {"rx": [{"from": "<current name>", '
    '"to": "<right name>"}], "diagnosis": [{"from": "<current text>", "to": "<new text>"}], '
    '"complaints": [], "findings": [], "investigations": [], "advice": []}. Both keys are optional; omit '
    "empty ones.\n"
    '8. Use "remove"/"replace" ONLY when the doctor explicitly asks to remove, delete, '
    "drop, cancel or stop something, or says a name/text is wrong and gives the right one. "
    'Copy "from" and each removed item exactly as it appears in the current form. Never '
    "remove or rename anything the doctor did not name. For a wrong drug name use "
    '"replace" and do NOT also add a new row for it.\n'
    '9. Never use "remove" to change a dose, strength, timing or duration: give the new '
    'value in an rx row. Use "remove" only when the doctor says to remove, delete, drop, '
    "cancel or stop the medicine or item entirely.\n"
    'Rules 10-14 apply only to the fields the doctor states in this correction. '
    'Never send "" or [] to clear a field the doctor did not mention: leave it out.\n'
    + rules_text(10) + "\n"
    '15. vitals: return only the vitals the correction states, for example {"vitals": {"bp": "130/80"}}; '
    'the other vitals keep their values, so leave them out instead of sending "".\n'
    '16. To set or change a medicine\'s generic (its composition), return that rx row with "name" and "generic": '
    'the ingredients joined by " + ". Use "generic" ONLY when the doctor states the generic or composition. '
    'Never return "generic_source" or "generic_suggestion".\n'
    "Examples:\n"
    '- "remove the Pantoprazole" -> {"remove": {"rx": ["Pantoprazole"]}}\n'
    '- "generic of Zerodol-P is aceclofenac plus paracetamol" -> '
    '{"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}]}\n'
    '- "the drug name is wrong, it is Cefixime not Cephixime" -> '
    '{"replace": {"rx": [{"from": "Cephixime", "to": "Cefixime"}]}}'
)


def build_correction_messages(correction_text: str, current_form: dict, extra_rule: str = "") -> list:
    """LLM messages: the current form plus the new dictation to apply."""
    form = dict(current_form) if isinstance(current_form, dict) else {}
    if isinstance(form.get("rx"), list):          # the model never sees suggestions or the pending flag
        form["rx"] = [{k: v for k, v in r.items() if k not in _HIDDEN} if isinstance(r, dict) else r for r in form["rx"]]
    return [
        {"role": "system", "content": CORRECTION_INSTRUCTION + extra_rule},
        {"role": "user", "content": json.dumps(
            {"current_form": form,
             "correction": correction_text or ""},
            ensure_ascii=False)},
    ]
