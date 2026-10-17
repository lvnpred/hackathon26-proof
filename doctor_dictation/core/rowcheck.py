"""Grounding of ONE prescription row: the single code path behind /api/format, /api/v1/correct and
/api/v1/rx/check-row, so the page and the Spell it popover can never disagree. Pure; no AI, no network."""
from . import dosing, formulary
from .candidates import suggest_candidates
from .lasa import lasa_row

SUGGESTION_LIMIT = 5


def ground_with_notes(item: dict, raw_transcript: str, normalized_transcript: str, age_sex: str = "", index: int = 0):
    """(row, notes): the coerced, grounded row, or None for an empty one (no name and no strength).

    ``notes`` are the warning strings validate_structured reports for this row, already prefixed ``rx[index]``.
    """
    from . import determinism as D   # lazy: determinism imports this module
    notes = []
    form = str(item.get("form") or "Tab.")
    if form not in D.ALLOWED_FORMS:
        form = "Tab."
    name = str(item.get("name") or "").strip().strip(".")
    strength = str(item.get("strength") or "").strip()
    dose = str(item.get("dose") or "").strip()
    if dose not in D.ALLOWED_DOSES:
        fixed = D.normalize_dose(dose.lower()) if dose else ""
        if fixed:
            dose = fixed
        else:
            notes.append(f"rx[{index}] {name or '?'}: unknown dose '{dose}' -> '1-0-0'")
            dose = "1-0-0"
    timing = str(item.get("timing") or "").strip()
    if timing not in D.ALLOWED_TIMINGS:
        fixed = D.normalize_timing(timing.lower())
        if fixed:
            timing = fixed
        elif ("food" in timing.lower() or "bedtime" in timing.lower()
              or "as needed" in timing.lower()):
            pass  # legacy combined strings from seeded example
        else:
            timing = ""
    duration = D.normalize_duration(str(item.get("duration") or "").lower()) or str(item.get("duration") or "")
    instructions = str(item.get("instructions") or "")
    if not name and not strength:
        return None, notes + [f"rx[{index}]: dropped empty row"]
    # Agent-loop grounding: status + lexicon match on every row.
    status, match, issue = D._ground_row(name, strength, (normalized_transcript or "").lower())
    given = form if item.get("form") == form else ""  # a defaulted or coerced form is not a form mismatch
    status, extra = dosing.ground_extra(status, match, given, strength, dose, age_sex)
    status, lextra = lasa_row(status, match, name, raw_transcript)
    if status == D.RX_VERIFIED:
        pass
    elif status == D.RX_UNKNOWN_MEDICINE:
        notes.append(f"rx[{index}] '{name}': not in medicine list -> flagged {status}")
        instructions = (instructions + " [unverified: confirm with doctor]").strip()
    elif status == D.RX_UNVERIFIED_STRENGTH:
        notes.append(f"rx[{index}] '{name}': {issue} -> flagged {status}")
        instructions = (instructions + " [unverified strength: confirm with doctor]").strip()
    elif status == D.RX_UNVERIFIED_NAME:
        notes.append(f"rx[{index}] {issue} -> flagged unverified")
        instructions = (instructions + " [unverified: confirm with doctor]").strip()
    return {
        "form": form, "name": name, "strength": strength,
        "dose": dose, "timing": timing, "duration": duration,
        "instructions": instructions, "status": status,
        "lexicon_match": match, "generic": D._generic_of(name, match), **extra, **lextra,
        **formulary.row_extras(name, match, status),
    }, notes


def ground_one(row: dict, raw_transcript: str, normalized_transcript: str, age_sex: str = "") -> dict:
    """The grounded row for ``row`` (contract 4.3). Raises ValueError when it has neither a name nor a strength."""
    out, _ = ground_with_notes(row, raw_transcript, normalized_transcript, age_sex)
    if out is None:
        raise ValueError("row has neither a name nor a strength")
    return out


def suggestions(row: dict) -> list:
    """The lexicon match first (so the matched drug is always offered, even for a short or odd typed name), then
    sound-alike names for the typed name, then the look-alike twins of the match: de-duplicated
    case-insensitively, first occurrence wins, at most SUGGESTION_LIMIT. A row with no lexicon match also gets this
    clinic's names (its own name first); usage breaks only near-ties among them (I1-r1)."""
    from . import lasa   # lazy, like determinism above: lasa may import determinism, which imports this module
    twins = lasa.twins(row["lexicon_match"]) if row.get("lexicon_match") else []
    seen, out = set(), []
    match = [row["lexicon_match"]] if row.get("lexicon_match") else []
    own = [] if match else [hit[0] for hit in [formulary.active_layer().get(row.get("name", ""))] if hit]
    alikes = suggest_candidates(row.get("name", "")) if match else formulary.sound_alikes(row.get("name", ""))
    for name in match + own + alikes + list(twins):
        if name.casefold() not in seen:
            seen.add(name.casefold())
            out.append(name)
    return out[:SUGGESTION_LIMIT]
