"""Grounding of ONE prescription row: the single code path behind /api/format, /api/v1/correct and
/api/v1/rx/check-row, so the page and the Spell it popover can never disagree. Pure; no AI, no network."""
import difflib
import re

from . import dosing, formulary, generics
from .candidates import MIN_SCORE, scored_spellings, similarity, suggest_candidates
from .lasa import lasa_row

SUGGESTION_LIMIT = 5
D_UNKNOWN = "unknown-medicine"        # determinism is imported lazily, so its RX_UNKNOWN_MEDICINE is not usable here
MAX_OPTIONS, POOL_ALL = 40, 100       # the Spell it list: names returned, names looked at (I2-c pages them)
INLINE_MIN, INLINE_GAP = 0.9, 0.05    # the inline Did you mean: a clear winner only (plan I2-a)
INLINE_LETTERS, INLINE_TEXT = 6, 0.7  # ... of a name with 6+ letters whose spelling alone (no sound bonus) is that alike; 0.8 would drop croissin -> Crocin (0.714)
INLINE_POOL = 40                      # names looked at for a longer name the typed one is the start of


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
    status, extra = dosing.ground_extra(status, match, given, strength, dose, age_sex, name)
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
        "lexicon_match": match, "generic": D._generic_of(name, match), "schedule": generics.schedule_of(match),
        **extra, **lextra,
        **formulary.row_extras(name, match, status), **did_you_mean(name, status),
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


def _letters(text) -> str:
    return re.sub(r"[^a-z]", "", str(text or "").lower())


def _sound_options(name, k, clinic=True, prefix_first=True):
    """[(name, generic, score, reason)]: lexicon spellings ("sounds") and, when ``clinic``, this clinic's single-word
    names ("clinic") by one score, then the I1-r1 near-tie rule (usage moves clinic names only).
    ``prefix_first``: a name that starts with the typed letters ("paracet" -> Paracetamol) comes before the others."""
    layer = formulary.active_layer()
    mine = [(n, g, s, "clinic") for n, g in layer.items if clinic and (s := similarity(name, n)) >= MIN_SCORE]
    lex = [(s, c, sc, "sounds") for s, c, sc in scored_spellings(name, k + len(mine))]
    typed = _letters(name)
    merged = sorted(lex + mine, key=lambda o: (not (prefix_first and _letters(o[0]).startswith(typed)), -round(o[2], 6), o[0].lower(), o[0]))
    by_name = {o[0]: o for o in merged}
    return [by_name[n] for n in formulary.tie_break([(o[0], o[2], o[3] == "clinic") for o in merged], layer.usage_of)][:k]


def options(row: dict, cap: int = MAX_OPTIONS):
    """([{"name", "generic", "reason"}], total): the one list behind Spell it and the inline Did you mean (I2-a, I2-c).

    Order as ``suggestions``: the lexicon match ("matched"), else the row's own clinic name ("clinic"); sound-alikes;
    the match's look-alike twins. A twin keeps the reason "lookalike" wherever it appears. One entry per name
    (case-insensitive); ``total`` counts entries before the cap."""
    from . import lasa
    match, name = row.get("lexicon_match") or "", row.get("name", "")
    twins = {t.casefold() for t in (lasa.twins(match) if match else [])}
    out, seen = [], set()

    def add(n, generic, reason):
        if n and n.casefold() not in seen:
            seen.add(n.casefold())
            out.append({"name": n, "generic": generic or "", "reason": "lookalike" if n.casefold() in twins else reason})
    if match:
        add(match, match, "matched")
    elif (hit := formulary.active_layer().get(name)):
        add(hit[0], hit[1], "clinic")
    for n, generic, _score, reason in _sound_options(name, POOL_ALL, clinic=not match):
        add(n, generic, reason)
    for t in (lasa.twins(match) if match else []):
        add(t, t, "lookalike")
    return out[:cap], len(out)


_DYM_CACHE: dict = {}        # (letters of the name, clinic layer) -> (lexicon list, result); bounded, see _DYM_MAX
_DYM_MAX = 512
_NO_DYM = {"did_you_mean": "", "did_you_mean_generic": ""}


def _clear_dym_cache() -> None:
    _DYM_CACHE.clear()


def _best_alike(name: str) -> dict:
    """The clear-winner rule for ``name`` (status is checked by the caller); one scored pass, so ~13 ms uncached."""
    from . import lasa
    alikes = _sound_options(name, INLINE_POOL, prefix_first=False)       # the sound score alone ranks here; the Spell it list reorders
    if not alikes or alikes[0][2] < INLINE_MIN:
        return _NO_DYM
    top, typed = alikes[0], _letters(name)
    shown = _letters(top[0])
    if len(shown) < INLINE_LETTERS or difflib.SequenceMatcher(None, typed, shown).ratio() < INLINE_TEXT:
        return _NO_DYM                                                    # a short name, or one that only SOUNDS like the typed word
    same = (top[1] or top[0]).casefold()
    if any(_letters(o[0]).startswith(typed) and (o[1] or o[0]).casefold() != same for o in alikes[1:]):
        return _NO_DYM                                                    # the typed word starts another name: incomplete, not misspelt
    rival = next((o for o in alikes[1:] if (o[1] or o[0]).casefold() != same), None)
    if (rival and round(top[2] - rival[2], 6) < INLINE_GAP) or (top[1] and top[1] in lasa.always_flag_names()):
        return _NO_DYM
    return {"did_you_mean": top[0], "did_you_mean_generic": top[1]}


def did_you_mean(name: str, status: str) -> dict:
    """The inline suggestion for an ``unknown-medicine`` row: the top sound-alike when it scores >= INLINE_MIN, is
    INLINE_GAP ahead of the next different generic and is not on the curated look-alike list. A suggestion only.

    Cached per (letters of the name, clinic layer object, lexicon list object): a clinic list or usage change builds a
    new layer, a lexicon reload a new list, so a hit is never another clinic's or version's suggestion. Max _DYM_MAX."""
    if status != D_UNKNOWN:
        return dict(_NO_DYM)
    from .determinism import load_lexicon
    layer, lex, letters = formulary.active_layer(), load_lexicon(), re.sub(r"[^a-z]", "", (name or "").lower())
    hit = _DYM_CACHE.get((letters, layer))
    if hit is None or hit[0] is not lex:
        if len(_DYM_CACHE) >= _DYM_MAX:
            _DYM_CACHE.clear()
        hit = _DYM_CACHE[(letters, layer)] = (lex, _best_alike(name))
    return dict(hit[1])
