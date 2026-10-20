"""Spoken remove / replace ops for corrections (pure, deterministic, stdlib only).

The correction patch may carry two extra top-level keys the plain merge cannot
express: `remove` ({"rx": ["Pantoprazole"], "diagnosis": ["viral fever"], ...})
and `replace` ({"rx": [{"from": "Cephixime", "to": "Cefixime"}], ...}).
`apply_ops` applies them to the current form (removes first, then replaces) and
hands back the rest of the patch for the ordinary `merge_form`. Anything it
cannot match unambiguously is left alone and reported in a note: it never
guesses between candidates, never mutates its inputs and never raises on
garbage.
"""
import copy
import re

from .correction import (DERIVED_ROW_FIELDS, GROUNDING_MARKERS, LIST_FIELDS, MIN_ALIAS_LETTERS,
                         _norm_name, _text, same_medicine_rows)
from .doctor_generic import DOCTOR_GENERIC_FIELDS

_FIELDS = ("rx",) + LIST_FIELDS


MIN_REF = 3
CAP = 3
TOO_SHORT = "That name is too short to match safely; nothing was changed. Use the x button."


def _key(value) -> str:
    """Normalised match key: lower-case, whitespace collapsed."""
    return " ".join(_norm_name(value).split())


def _find_rx(rows, ref):
    """Index of the one row `ref` names, else (None, "none"|"many").

    Exact normalised name first; otherwise ONLY a row whose name starts with
    `ref` at a word boundary ("dolo" -> "dolo 650", never "pan" ->
    "pantoprazole"). There is no reverse direction: a longer ref never matches a
    shorter row name. Last, the brand/generic of `ref` by the row's `lexicon_match`
    ("allopurinol" -> the Zyloric row), only for an exact lexicon name of 5+ letters: short
    aliases ("levo", "keto", "pan") mean several drugs colloquially. Unique matches only.
    """
    names = [_key(r.get("name")) if isinstance(r, dict) else "" for r in rows]
    exact = [i for i, n in enumerate(names) if n and n == ref]
    if exact:
        return (exact[0], "") if len(exact) == 1 else (None, "many")
    loose = [i for i, n in enumerate(names)
             if n.startswith(ref) and n[len(ref):len(ref) + 1].isspace()]
    loose = loose or (same_medicine_rows(rows, ref) if len(ref) >= MIN_ALIAS_LETTERS else [])
    return (loose[0], "") if len(loose) == 1 else (None, "many" if loose else "none")


def _find_item(items, ref):
    """Exactly one equal item, else `ref` as whole words inside exactly one item."""
    names = [_key(i) if isinstance(i, str) else "" for i in items]
    exact = [i for i, n in enumerate(names) if n and n == ref]
    if exact:
        return (exact[0], "") if len(exact) == 1 else (None, "many")
    rx = re.compile(r"(?<!\w)" + re.escape(ref) + r"(?!\w)")
    sub = [i for i, n in enumerate(names) if n and rx.search(n)]
    return (sub[0], "") if len(sub) == 1 else (None, "many" if sub else "none")


def _locate(seq, field, ref):
    """(index|None, note|"") for `ref` in `seq`, applying the length floor."""
    key = _key(ref)
    if len(key) < MIN_REF:
        return None, TOO_SHORT
    idx, why = _find_rx(seq, key) if field == "rx" else _find_item(seq, key)
    return (idx, "") if idx is not None else (None, _miss(why, ref, field))


def _miss(kind, ref, field):
    where = "on the prescription" if field == "rx" else f"in {field}"
    if kind == "none":
        return f"Could not find {ref} {where}; nothing was changed. Use the x button."
    noun = "rows" if field == "rx" else "items"
    return (f"Several {noun} match {ref}; nothing was changed. "
            f"Use the x button on the right {noun[:-1]}.")


def _regrounded(row, new_name):
    out = {k: v for k, v in row.items() if k not in ("status", "lexicon_match", *DERIVED_ROW_FIELDS, *DOCTOR_GENERIC_FIELDS)}
    out["name"] = new_name
    if "instructions" in out:
        text = str(out["instructions"] or "")
        for marker in GROUNDING_MARKERS:
            text = text.replace(marker, "")
        out["instructions"] = " ".join(text.split())
    return out


def _refs(value):
    """Non-blank string refs of a `remove` list; garbage is dropped."""
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _pairs(value):
    """(from, to) string pairs of a `replace` list; garbage is dropped."""
    out = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict) and isinstance(item.get("from"), str) \
                and isinstance(item.get("to"), str) and item["from"].strip():
            out.append((item["from"].strip(), item["to"].strip()))
    return out


def _do_removes(form, field, refs, notes):
    """Remove every ref found in `field`, or none at all if that would wipe too much."""
    seq = form.get(field)
    if not isinstance(seq, list):
        return
    hits = []
    for ref in refs:
        idx, note = _locate(seq, field, ref)
        if idx is None:
            notes.append(note)
        elif idx not in hits:
            hits.append(idx)
    if not hits:
        return
    if len(hits) > CAP or (len(hits) == len(seq) and len(seq) >= 2):
        noun, hint = ("medicines", "rows") if field == "rx" else ("items", "items")
        notes.append(f"That would remove {len(hits)} {noun} at once; nothing was changed. "
                     f"Use the x button on the {hint} you mean.")
        return
    for idx in hits:
        gone = seq[idx]
        notes.append(f"Removed {_text(gone.get('name') if field == 'rx' else gone)}.")
    form[field] = [v for i, v in enumerate(seq) if i not in hits]


def _do_replace(form, field, old, new, notes, touched):
    seq = form.get(field)
    if not isinstance(seq, list):
        return
    idx, note = _locate(seq, field, old)
    if idx is None:
        notes.append(note)
        return
    if not new:
        notes.append(f"No new text was given to replace {old}; nothing was changed.")
        return
    if field == "rx":
        was = _text(seq[idx].get("name"))
        if _key(was) == _key(new):
            notes.append(f"{was} already has that name; nothing was changed.")
            return
        if any(i != idx and isinstance(r, dict) and _key(r.get("name")) == _key(new)
               for i, r in enumerate(seq)):
            notes.append(f"Another row is already named {new}; nothing was changed. "
                         "Use the x button to remove the wrong one.")
            return
        seq[idx] = _regrounded(seq[idx], new)
        touched.add(_key(new))
        notes.append(f"Renamed {was} to {new}.")
    else:
        was = seq[idx]
        seq[idx] = new
        notes.append(f"Changed {was} to {new}.")


def apply_ops(current: dict, patch: dict):
    """Apply `patch["remove"]` then `patch["replace"]` to `current`.

    Returns `(new_current, patch_without_ops, notes, touched)`; `touched` is the
    set of normalised new names of renamed rx rows (their grounding must be
    recomputed, never restored). Inputs are never mutated.
    """
    form = copy.deepcopy(current) if isinstance(current, dict) else {}
    rest = {k: copy.deepcopy(v) for k, v in patch.items() if k not in ("remove", "replace")} \
        if isinstance(patch, dict) else {}
    notes: list = []
    touched: set = set()
    removes = patch.get("remove") if isinstance(patch, dict) else None
    replaces = patch.get("replace") if isinstance(patch, dict) else None
    if isinstance(removes, dict):
        for field in _FIELDS:
            _do_removes(form, field, _refs(removes.get(field)), notes)
    if isinstance(replaces, dict):
        for field in _FIELDS:
            for old, new in _pairs(replaces.get(field)):
                _do_replace(form, field, old, new, notes, touched)
    return form, rest, notes, touched
