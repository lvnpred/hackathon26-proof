"""Which doctors a letterhead lists (spec 9.2) and the doctor-name warning for literal lines (spec 9.3)."""
from __future__ import annotations

import json
import re

from doctor_dictation.db import templates as tdb
from doctor_dictation.templates import TemplateError

# Spec 9.3 heuristic: "Dr", "MBBS", "MD", "MS", "DNB" as whole words, any case. A hint for the human, not a guarantee.
DOCTOR_LIKE = re.compile(r"\b(?:dr|mbbs|md|ms|dnb)\b", re.IGNORECASE)


def literal_warnings(layout) -> list:
    """Literal text lines that look like a doctor's name or degree: the review screen warns on each."""
    out = []
    for section in ("header", "footer"):
        blocks = layout.get(section) if isinstance(layout, dict) else None
        for index, b in enumerate(blocks if isinstance(blocks, list) else []):
            if (isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
                    and DOCTOR_LIKE.search(b["text"])):
                out.append({"section": section, "index": index, "text": b["text"]})
    return out


def stored_ids(row) -> list:
    """The ``doctors_ids`` of a template row as a list of ints (anything malformed reads as empty)."""
    try:
        ids = json.loads(row["doctors_ids"] or "[]")
    except (TypeError, ValueError):
        return []
    return [i for i in ids if isinstance(i, int) and not isinstance(i, bool)] if isinstance(ids, list) else []


MODES = ("author", "all", "selected")
MAX_SELECTED = 50


def _entry(r) -> dict:
    return {"id": r["id"], "name": (r["doctor_name"] or r["display_name"] or r["username"]).strip(),
            "qualifications": r["qualifications"] or "", "reg_no": r["reg_no"] or ""}


def choices(conn) -> list:
    """The clinic's active doctors in their stable order, for the review screen's "only these doctors" ticks."""
    return [_entry(r) for r in tdb.clinic_doctors(conn)]


def check_choice(conn, mode, ids) -> tuple:
    """Validate a doctors choice; returns ``(mode, ids)`` (ids de-duplicated, empty unless ``selected``)."""
    if mode not in MODES:
        raise TemplateError(400, "doctors mode must be author, all or selected")
    ids = [] if ids is None else ids
    if (not isinstance(ids, list) or len(ids) > MAX_SELECTED
            or any(isinstance(i, bool) or not isinstance(i, int) for i in ids)):
        raise TemplateError(400, f"doctors ids must be a list of at most {MAX_SELECTED} user ids")
    if mode != "selected":
        return mode, []
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise TemplateError(400, "choose at least one doctor")
    known = {r["id"] for r in tdb.clinic_doctors(conn)}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise TemplateError(400, f"not an active doctor of this clinic: {unknown[0]}")
    return mode, ids


def for_print(conn, row):
    """``meta["doctors"]`` for a print on template ``row``: None in ``author`` mode (the sheet prints the author from
    the resolved profile), else the active doctors (``all``) or the ticked ones still active (``selected``), in the
    clinic's stable order. Disabled and unknown ids are skipped."""
    mode = row["doctors_mode"] if row is not None else "author"
    if mode == "all":
        return [_entry(r) for r in tdb.clinic_doctors(conn)]
    if mode == "selected":
        wanted = set(stored_ids(row))
        return [_entry(r) for r in tdb.clinic_doctors(conn) if r["id"] in wanted]
    return None
