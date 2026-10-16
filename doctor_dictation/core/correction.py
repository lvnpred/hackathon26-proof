"""Apply a spoken correction to the current prescription form.

A correction names only what changed, so `merge_form` folds a *patch* form
into the current one without clobbering anything the doctor stayed silent
about. `extract_correction` produces that patch: offline (rules) it is empty,
and with an LLM the model is shown the current form plus an instruction to
change only what the correction states. `merge_form` itself is pure and
deterministic: no network, no time, no randomness, stdlib only. Returns a
brand-new dict and never mutates `current`.

Merge rules (see the plan, Task 4):
- Scalars (`patientName`, `ageSex`, `opNo`, `review`) overwrite only when the
  patch value is non-empty.
- List fields (`diagnosis`, `complaints`, `investigations`, `advice`) replace
  only when the patch list is non-empty.
- `rx` merges by case-insensitive `name`: a patch row naming an existing
  medicine **overlays** that row, field-by-field -- fields present in the patch
  overwrite, fields the patch omits are **retained** (a dose-only correction
  keeps the existing strength). The row's `name` keeps the current/canonical
  spelling unless the patch explicitly names a key. A new name is appended (a nameless row never is);
  rows not named in the patch are left untouched. A brand and its generic are one
  medicine: `match_by_generic` renames such a patch row to the form's row first.
"""
import json

from .determinism import (  # determinism never imports this module
    RX_UNVERIFIED_NAME, _alias_map, _ambiguous_for, _canonical_lookup,
)
from .dosing import DOSE_CHECK, check_dose
from .surface import _generic_of

SCALAR_FIELDS = ("patientName", "ageSex", "opNo", "review")
LIST_FIELDS = ("diagnosis", "complaints", "investigations", "advice")

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
    "doctor dictated. Never return an rx row without a name. A brand and its generic are the "
    "same medicine (Zyloric is Allopurinol): when the doctor names the other one, use the name "
    "on the current form.\n"
    '2. Allowed dose codes ONLY: "1-0-0", "1-0-1", "1-1-1", "0-0-1", "SOS". '
    "Map: once daily/OD -> 1-0-0; twice daily/BD -> 1-0-1; thrice daily/TDS -> 1-1-1; "
    "at bedtime/HS -> 0-0-1; as needed/for pain -> SOS.\n"
    '3. Allowed timing ONLY: "After food", "Before food", "At bedtime", or "".\n'
    '4. ageSex format is "<age> / <M|F>", for example "45 / M".\n'
    '5. Duration format: "<N> days/weeks/months" with digits; two weeks -> 14 days.\n'
    "6. Never invent strengths, durations or drugs. Return only fields the doctor stated.\n"
    '7. To REMOVE something add a top-level "remove" object: {"rx": ["<row name>"], '
    '"diagnosis": [], "complaints": [], "investigations": [], "advice": []} '
    "(list the exact text of each item to delete). To CHANGE the name or text of one "
    'existing row/item add a top-level "replace" object: {"rx": [{"from": "<current name>", '
    '"to": "<right name>"}], "diagnosis": [{"from": "<current text>", "to": "<new text>"}], '
    '"complaints": [], "investigations": [], "advice": []}. Both keys are optional; omit '
    "empty ones.\n"
    '8. Use "remove"/"replace" ONLY when the doctor explicitly asks to remove, delete, '
    "drop, cancel or stop something, or says a name/text is wrong and gives the right one. "
    'Copy "from" and each removed item exactly as it appears in the current form. Never '
    "remove or rename anything the doctor did not name. For a wrong drug name use "
    '"replace" and do NOT also add a new row for it.\n'
    '9. Never use "remove" to change a dose, strength, timing or duration: give the new '
    'value in an rx row. Use "remove" only when the doctor says to remove, delete, drop, '
    "cancel or stop the medicine or item entirely.\n"
    "Examples:\n"
    '- "remove the Pantoprazole" -> {"remove": {"rx": ["Pantoprazole"]}}\n'
    '- "the drug name is wrong, it is Cefixime not Cephixime" -> '
    '{"replace": {"rx": [{"from": "Cephixime", "to": "Cefixime"}]}}'
)


def _norm_name(value) -> str:
    """Case-insensitive, whitespace-insensitive medicine key."""
    return str(value or "").strip().lower()


def _text(value) -> str:
    """Stripped string form of any value (None -> "")."""
    return str(value if value is not None else "").strip()


def resolve_blank_names(current: dict, patch: dict):
    """Give every nameless patch rx row the medicine it can only mean, or drop it.

    The model sometimes returns `{"name": "", "strength": "5 ml"}` for "strength
    is 5 ml for the Ascoril"; merging that by name would append a ghost row.
    A nameless row is applied to the ONE current (named) row that is missing a
    field the row states, filling only that row's empty fields. With zero or
    several candidates it is dropped and a warning says what was ignored.
    Returns `(patch_copy, warnings)`; never mutates its inputs.
    """
    pat = dict(patch) if isinstance(patch, dict) else {}
    rows = pat.get("rx")
    if not isinstance(rows, list):
        return pat, []
    cur_rows = current.get("rx") if isinstance(current, dict) else None
    named = [r for r in cur_rows if isinstance(r, dict) and _norm_name(r.get("name"))] \
        if isinstance(cur_rows, list) else []
    kept, warnings = [], []
    for row in rows:
        if not isinstance(row, dict) or _norm_name(row.get("name")):
            kept.append(row)
            continue
        stated = {f: _text(v) for f, v in row.items() if f != "name" and _text(v)}
        if not stated:
            continue  # nothing to apply
        candidates = [r for r in named if any(not _text(r.get(f)) for f in stated)]
        unique = len(candidates) == 1 and sum(
            _norm_name(r.get("name")) == _norm_name(candidates[0]["name"]) for r in named) == 1
        if unique:  # two rows sharing a name would merge into the first one
            target = candidates[0]
            fill = {f: v for f, v in stated.items() if not _text(target.get(f))}
            skipped = {f: v for f, v in stated.items() if f not in fill}
            if skipped:
                said = ", ".join(f"{f}: {v}" for f, v in skipped.items())
                warnings.append(
                    f"Applied to {target['name']}, but not changed because they already "
                    f"have a value ({said}). Name the medicine to change them.")
            kept.append({"name": target["name"], **fill})
            continue
        said = ", ".join(f"{f}: {v}" for f, v in stated.items())
        warnings.append(
            "Could not tell which medicine this correction was for, so it was "
            f"not applied ({said}). Name the medicine and try again.")
    pat["rx"] = kept
    return pat, warnings


MIN_ALIAS_LETTERS = 5  # shorter names never match by "same medicine" (ops.py applies the same floor)


def same_medicine_rows(rows, name) -> list:
    """Indices of the named rx rows whose `lexicon_match` is the generic `name` is an exact name of.

    Brand and generic are one medicine ("allopurinol" finds the `Zyloric` row). Exact lexicon
    names only: a fuzzy neighbour is often another drug (Famciclovir is not Acyclovir). `[]` when
    the name is not in the lexicon or two generics claim it (never guessed). Also used by ops.
    """
    low = _norm_name(name)
    generic = "" if not low or _ambiguous_for(low) else _alias_map().get(low, "").lower()
    return [i for i, r in enumerate(rows if isinstance(rows, list) else [])
            if generic and isinstance(r, dict) and _norm_name(r.get("name"))
            and _norm_name(r.get("lexicon_match")) == generic]


def match_by_generic(current: dict, patch: dict):
    """Rename each patch rx row naming no current row to the ONE current row of its generic.

    "change allopurinol to 300 mg" against a `Zyloric` row would otherwise append a second
    allopurinol row (both verified). An exact name always wins; with two current rows of that
    generic nothing is guessed: the row stays new, a warning says so, and its name is returned
    in `unsure` so the caller blocks it (`flag_unsure_rows`). Returns
    `(patch_copy, warnings, unsure)`; never mutates its inputs.
    """
    pat = dict(patch) if isinstance(patch, dict) else {}
    rows, cur_rows = pat.get("rx"), current.get("rx") if isinstance(current, dict) else None
    if not isinstance(rows, list) or not isinstance(cur_rows, list):
        return pat, [], set()
    names = {_norm_name(r.get("name")) for r in cur_rows if isinstance(r, dict)}
    out, warnings, unsure = [], [], set()
    for row in rows:
        said = _text(row.get("name")) if isinstance(row, dict) else ""
        short = len(" ".join(_norm_name(said).split())) < MIN_ALIAS_LETTERS  # keto, levo, pan: many drugs
        same = [] if not said or short or _norm_name(said) in names else same_medicine_rows(cur_rows, said)
        if len(same) == 1:
            target = cur_rows[same[0]]["name"]
            row = {**row, "name": target}
            warnings.append(f"'{said}' matched the existing row '{target}' (same medicine).")
        elif same:
            listed = ", ".join(_text(cur_rows[i]["name"]) for i in same)
            unsure.add(_norm_name(said))
            warnings.append(f"'{said}' could be any of {listed} (same medicine), so it was added "
                            "as a new row to confirm. Use the x button on the row you do not want.")
        out.append(row)
    pat["rx"] = out
    return pat, warnings, unsure


def _merge_row(existing: dict, patch_row: dict) -> dict:
    """Overlay a matching patch row onto an existing rx row.

    Fields present in the patch overwrite; fields the patch omits are retained
    (so a dose-only correction keeps the existing strength). The existing row's
    `name` is kept (it is already canonical after grounding) unless the current
    name is blank.
    """
    merged = dict(existing)
    for field, value in patch_row.items():
        if field == "name" and existing.get("name"):
            continue
        merged[field] = value
    return merged


def _merge_rx(current_rows, patch_rows):
    """Merge patch rx rows into current rx rows by case-insensitive name."""
    current_rows = current_rows if isinstance(current_rows, list) else []
    out = [dict(r) if isinstance(r, dict) else r for r in current_rows]
    # First index of each named row wins, so duplicate current rows keep the
    # first and later duplicates stay untouched.
    index_by_name = {}
    for i, row in enumerate(out):
        if isinstance(row, dict):
            key = _norm_name(row.get("name"))
            if key and key not in index_by_name:
                index_by_name[key] = i
    if not isinstance(patch_rows, list):
        return out
    for row in patch_rows:
        if not isinstance(row, dict):
            out.append(row)
            continue
        key = _norm_name(row.get("name"))
        if key and key in index_by_name:
            i = index_by_name[key]
            out[i] = _merge_row(out[i], row)  # update named row in place
        elif key:
            out.append(dict(row))  # new medicine -> append
        # a nameless row is never appended (resolve_blank_names handles those first)
    return out


def _merged_keys(current: dict, patch: dict):
    """Current keys first (stable order), then any patch-only keys."""
    keys = list(current.keys())
    for key in patch:
        if key not in keys:
            keys.append(key)
    return keys


def merge_form(current: dict, patch: dict) -> dict:
    """Return a new form with `patch` applied on top of `current`."""
    cur = current if isinstance(current, dict) else {}
    pat = patch if isinstance(patch, dict) else {}
    out = {}

    for key in _merged_keys(cur, pat):
        cur_val = cur.get(key)
        pat_val = pat.get(key, None)

        if key == "rx":
            out["rx"] = _merge_rx(cur_val, pat_val)
        elif key in LIST_FIELDS:
            if isinstance(pat_val, list) and pat_val:
                out[key] = list(pat_val)
            else:
                out[key] = list(cur_val) if isinstance(cur_val, list) else cur_val
        elif key in SCALAR_FIELDS:
            out[key] = pat_val if pat_val else cur_val
        elif key in pat:
            out[key] = pat_val
        else:
            out[key] = cur_val

    return out


# Row fields validate_structured derives from the name and the grounding (screen only).
DERIVED_ROW_FIELDS = ("generic", "heard", "lookalike", "dose_note")


def _recomputed_generic(row: dict) -> str:
    """`generic` from the name + restored `lexicon_match`; "" when they no longer agree (a name
    hand-edited in the UI keeps the old data-lexicon: Febuxostat must not show "Allopurinol")."""
    name, match = row.get("name", ""), row.get("lexicon_match", "")
    return _generic_of(name, match) if match and _canonical_lookup(name) == match else ""


# DERIVED_ROW_FIELDS that depend on name + lexicon_match only: recomputed for an untouched row, never
# copied from the prior row (the client's readRx does not send them back). The rest are restored.
RECOMPUTED_ROW_FIELDS = {"generic": _recomputed_generic}

def _dose_note(row: dict, prev: dict, age_sex) -> str:
    """Why a restored dose-check row was flagged, recomputed from the validated row (the page does not send
    `dose_note` back); the prior row's note when nothing is recomputed (reference changed, row edited)."""
    form = row.get("form") if prev.get("form") == row.get("form") else ""   # same "form given" rule as validate_structured
    verdict = check_dose(row.get("lexicon_match", ""), row.get("strength", ""), row.get("dose", ""), age_sex, form)
    return verdict.note or prev.get("dose_note", "")


GROUNDING_MARKERS = (
    "[unverified: confirm with doctor]",
    "[unverified strength: confirm with doctor]",
)


def flag_unsure_rows(structured: dict, names) -> dict:
    """Give the verified rows `match_by_generic` could not place a blocking `unverified-name`.

    The doctor must confirm such a row (save gate), or remove it. Rows already blocked keep their
    status. Mutates and returns `structured`.
    """
    rows = structured.get("rx") if isinstance(structured, dict) else None
    for row in rows if isinstance(rows, list) and names else []:
        if isinstance(row, dict) and _norm_name(row.get("name")) in names \
                and row.get("status") == "verified":
            row["status"] = RX_UNVERIFIED_NAME
            row["instructions"] = f"{row.get('instructions') or ''} {GROUNDING_MARKERS[0]}".strip()
    return structured


def _patch_rx_names(patch: dict) -> set:
    """Case-insensitive names of the rx rows a patch names."""
    names = set()
    rows = patch.get("rx") if isinstance(patch, dict) else None
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            key = _norm_name(row.get("name"))
            if key:
                names.add(key)
    return names


def strip_grounding_markers(form: dict) -> dict:
    """Copy `form` with auto-added `[unverified …]` markers dropped from rx rows.

    Re-validating an already-validated form would otherwise stack a fresh
    marker onto the retained one, so strip first; `validate_structured` then
    re-adds at most one marker per still-unverified row.
    """
    out = dict(form) if isinstance(form, dict) else {}
    rows = out.get("rx")
    if isinstance(rows, list):
        cleaned = []
        for row in rows:
            if not isinstance(row, dict):
                cleaned.append(row)
                continue
            text = str(row.get("instructions") or "")
            for marker in GROUNDING_MARKERS:
                text = text.replace(marker, "")
            cleaned.append({**row, "instructions": " ".join(text.split())})
        out["rx"] = cleaned
    return out


def preserve_untouched_rx_status(current: dict, patch: dict, structured: dict,
                                 extra_named=()) -> dict:
    """Restore prior rx verification state for rows the patch does not name.

    A correction must not change the verification state of rows it never
    mentions, so those rows are restored *exactly* to what they had: `status`,
    `lexicon_match`, and `instructions` are copied back from the prior row, and
    any of those keys the prior row lacked are removed again (so a status-less
    row is not stamped with a fresh status or an `[unverified …]` marker). Only
    patch-named (and brand-new) rows keep the grounding `validate_structured`
    recomputed. Mutates and returns `structured`.
    """
    named = _patch_rx_names(patch) | {_norm_name(n) for n in extra_named}
    prior = {}
    cur_rows = current.get("rx") if isinstance(current, dict) else None
    for row in cur_rows if isinstance(cur_rows, list) else []:
        if isinstance(row, dict):
            prior[_norm_name(row.get("name"))] = row
    out_rows = structured.get("rx") if isinstance(structured, dict) else None
    for row in out_rows if isinstance(out_rows, list) else []:
        if not isinstance(row, dict):
            continue
        key = _norm_name(row.get("name"))
        prev = prior.get(key)
        if key in named or prev is None:
            continue
        for field in ("status", "lexicon_match", "instructions"):
            if field in prev:
                row[field] = prev[field]
            else:
                row.pop(field, None)
        for field in DERIVED_ROW_FIELDS:  # follow the restored status; absent when the prior row had none
            if "status" not in prev:
                row.pop(field, None)
            elif field in RECOMPUTED_ROW_FIELDS:  # from the restored name + lexicon_match
                row[field] = RECOMPUTED_ROW_FIELDS[field](row)
            elif field == "dose_note" and row.get("status") == DOSE_CHECK:  # the page never sends it back
                row[field] = _dose_note(row, prev, structured.get("ageSex"))
            else:
                row[field] = prev.get(field, "")
    return structured


def build_correction_messages(correction_text: str, current_form: dict) -> list:
    """LLM messages: the current form plus the new dictation to apply."""
    return [
        {"role": "system", "content": CORRECTION_INSTRUCTION},
        {"role": "user", "content": json.dumps(
            {"current_form": current_form if isinstance(current_form, dict) else {},
             "correction": correction_text or ""},
            ensure_ascii=False)},
    ]


async def extract_correction(correction_text: str, current_form: dict, complete=None) -> dict:
    """Return a *patch* form extracted from a spoken correction.

    The LLM path is dependency-injected: the caller must pass an async
    `complete(messages) -> (dict_or_None, err)` (the endpoint wires in the
    configured model). Called with the two positional arguments alone --
    `extract_correction(correction_text, current_form)`, the rules/offline path
    (e.g. no API key configured) -- there is no completer, so an empty patch
    `{}` is returned and `merge_form` leaves the current form untouched (an
    empty correction never wipes the form). With a completer, the model is shown
    the current form plus an instruction to change only what the correction
    states; a non-dict reply is treated as no patch.
    """
    if complete is None or not (correction_text or "").strip():
        return {}
    patch, _err = await complete(build_correction_messages(correction_text, current_form))
    return patch if isinstance(patch, dict) else {}
