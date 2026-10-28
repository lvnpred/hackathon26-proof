"""A clinic's own drug list as pure data (plan I1-h): rules for learning a name, the immutable layer, the grounding hook.

The api layer loads the layer from the clinic's database and ``activate``s it for the request (a ContextVar, like
scope.py, so it follows asyncio.to_thread). Nothing here does I/O. A clinic name is verified for its NAME only.
"""
import hashlib
import logging
import math
import re
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date
from functools import cached_property, lru_cache

from .candidates import MIN_SCORE, scored_candidates, similarity, suggest_candidates

VERIFIED, UNVERIFIED_NAME, LOOKALIKE = "verified", "unverified-name", "lookalike-check"
THRESHOLD = 2                                  # saved prescriptions that must confirm a name
MAX_NAME, MAX_WORDS = 60, 5                    # MAX_NAME equals hints._MAX_DOCTOR_NAME (a test pins it)
MAX_HINTS, HINT_CHARS = 10, 150                # clinic names offered to the speech engine: count and characters
HALF_LIFE_DAYS = 30                            # usage halves for every 30 days a name goes unconfirmed (plan I1-r1)
BAND, POOL = 0.03, 3                           # near-equal: within 0.03 of the top sound-alike; sound-alikes per row
_NAME_OK = re.compile(r"[A-Za-z][A-Za-z0-9 .'+/-]*")


def key(name) -> str:
    return " ".join(str(name or "").split()).casefold()


def has_letters(name) -> bool:
    """At least 3 letters: "9876543210" or "B2" typed into a name cell is not a medicine name."""
    return sum(c.isalpha() for c in str(name or "")) >= 3


def clean_name(raw) -> str:
    """The name to store, or "" for anything that is not plausibly a medicine name."""
    name = " ".join(str(raw or "").split())
    if not (3 <= len(name) <= MAX_NAME) or len(name.split()) > MAX_WORDS or not _NAME_OK.fullmatch(name):
        return ""
    if not has_letters(name):
        return ""
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), name) if name.isupper() or name.islower() else name


_FORMS = {"tab", "tablet", "cap", "capsule", "syp", "syrup", "inj", "injection", "oint", "cream", "gel", "drops", "susp"}
_HONORIFICS = {"dr", "mr", "mrs", "ms", "mx", "prof", "shri", "smt"}


def person_like(name) -> bool:
    """True for a name that reads as a person: an honorific first, or 2-3 Capitalised letters-only words without a form prefix.

    "Zorbexin SR" (SR is not Capitalised), "Vitamin D3" (digit) and single words are not person-like."""
    words = str(name or "").split()
    if words and words[0].rstrip(".").casefold() in _HONORIFICS:
        return True
    cap = all(w.isalpha() and w[0].isupper() and w[1:].islower() for w in words)
    return 2 <= len(words) <= 3 and cap and words[0].casefold() not in _FORMS


def learnable(structured, confirmed_rows, known_patient_words=None) -> list[tuple[str, str]]:
    """[(name, generic)] a saved form teaches: confirmed rows whose name the lexicon does not know exactly, once per name.

    The doctor's confirmation, not the row's status text, is the trigger (the client could send any status), and a
    name made only of the patient's own name words is never learned (a patient typed into a medicine cell). Person-like
    names, and names with a word (3+ letters) in ``known_patient_words`` (casefolded words of the clinic's patients), are skipped."""
    from .determinism import _exact_lookup
    rows = structured.get("rx") if isinstance(structured, dict) else None
    confirmed = {i for i in (confirmed_rows or []) if isinstance(i, int)}
    patient = {w.casefold() for w in str(structured.get("patientName") or "").split()} if isinstance(structured, dict) else set()
    known = known_patient_words or frozenset()
    out, seen = [], set()
    for i, row in enumerate(rows if isinstance(rows, list) else []):
        if isinstance(row, dict) and row.get("generic_source") == "doctor":
            continue      # a doctor's generic goes to the clinic overlay, not the clinic list
        name = clean_name(row.get("name")) if i in confirmed and isinstance(row, dict) else ""
        if not name or key(name) in seen or _exact_lookup(name) or {w.casefold() for w in name.split()} <= patient:
            continue
        if person_like(name) or any(len(w) >= 3 and w.casefold() in known for w in name.split()):
            continue
        seen.add(key(name))
        out.append((name, clean_name(row.get("generic"))))
    return out


@dataclass(frozen=True)
class ClinicLayer:
    """Active names in rank order: ((name, generic or ''), ...); ranked_layer puts the most used first (I1-r1).

    ``usage`` is ((name key, usage score), ...); a name missing from it scores 0.0. Neither the order nor the
    usage is part of ``version``: /api/format reads the layer only through ``get``."""
    items: tuple = ()
    usage: tuple = ()

    @cached_property
    def _usage(self) -> dict:
        return dict(self.usage)

    def usage_of(self, name) -> float:
        return self._usage.get(key(name), 0.0)

    @cached_property
    def _by_key(self) -> dict:
        return {key(n): (n, g) for n, g in self.items}

    @cached_property
    def version(self) -> str:
        """Changes whenever a name is added or removed ("0" when empty); part of the /api/format cache key."""
        return hashlib.sha1("|".join(sorted(self._by_key)).encode()).hexdigest()[:8] if self.items else "0"

    def get(self, name):
        return self._by_key.get(key(name))

    def hint_names(self) -> list[str]:
        """The highest-ranked names that fit MAX_HINTS and HINT_CHARS, so they cannot crowd the 500-character hint budget."""
        out, used = [], 0
        for name, _generic in self.items:
            if len(out) >= MAX_HINTS or used + len(name) + 2 > HINT_CHARS:
                break
            out.append(name)
            used += len(name) + 2
        return out


def usage_score(confirm_count, last_seen_at, today: date) -> float:
    """log2(1 + confirm_count), halved for every HALF_LIFE_DAYS whole days since last_seen_at, rounded to 6 places.

    A future date counts as today; a missing count or an unreadable date scores 0.0 (it ranks last, never first)."""
    try:
        age = max(0, (today - date.fromisoformat(str(last_seen_at)[:10])).days)
        count = max(0, int(confirm_count))
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return round(math.log2(1 + count) * 0.5 ** (age / HALF_LIFE_DAYS), 6)


def ranked_layer(rows, today: date) -> ClinicLayer:
    """The layer for db.formulary.list_active rows, most used first. Ties: more recently seen, then the name key."""
    rows = [r for r in rows or () if str(r.get("name") or "").strip()]
    score = {key(r["name"]): usage_score(r.get("confirm_count"), r.get("last_seen_at"), today) for r in rows}
    rows = sorted(rows, key=lambda r: key(r["name"]))                                     # three stable sorts,
    rows = sorted(rows, key=lambda r: str(r.get("last_seen_at") or ""), reverse=True)     # least important first
    rows = sorted(rows, key=lambda r: -score[key(r["name"])])
    return ClinicLayer(tuple((r["name"], r.get("generic") or "") for r in rows),
                       tuple((key(r["name"]), score[key(r["name"])]) for r in rows))


def tie_break(scored, usage_of, preferred=None) -> list[str]:
    """Names of ``scored`` ([(name, score, from_clinic)], best first) after the near-tie rule (plan I1-r1).

    Inside the band (within BAND of the TOP score) the clinic's names trade places by usage, more used first; a
    lexicon name keeps its exact slot, and nothing enters or leaves the band. With no usage nothing moves.
    ``preferred`` (name -> bool, Spell it context, SH-B4) puts the clinic names it marks first inside those same slots."""
    if not scored:
        return []
    top = scored[0][1]
    slots = [i for i, (_n, s, clinic) in enumerate(scored) if clinic and round(top - s, 6) <= BAND]
    moved = sorted((scored[i] for i in slots), key=lambda c: (not (preferred and preferred(c[0])), -usage_of(c[0]),
                                                              -round(c[1], 6), c[0].lower(), c[0]))
    out = list(scored)
    for i, cand in zip(slots, moved):
        out[i] = cand
    return [n for n, _s, _c in out]


def sound_alikes(name, k: int = POOL) -> list[str]:
    """Up to k names that sound like ``name``: the lexicon's and this clinic's single-word names by one score, then
    the near-tie rule. With an empty layer this is exactly suggest_candidates(name, k)."""
    layer = active_layer()
    clinic = [c for c in ((n, similarity(name, n), True) for n, _generic in layer.items) if c[1] >= MIN_SCORE]
    lexicon = [(n, s, False) for n, s in scored_candidates(name, k + len(clinic))]
    merged = sorted(lexicon + clinic, key=lambda c: (-round(c[1], 6), c[0].lower(), c[0]))
    return tie_break(merged, layer.usage_of)[:k]


log = logging.getLogger(__name__)
_EMPTY = ClinicLayer()
_active: ContextVar[ClinicLayer | None] = ContextVar("dd_clinic_layer", default=None)
_in_request: ContextVar[bool] = ContextVar("dd_request_scoped", default=False)
_warned = False


def mark_request_scoped() -> None:
    """Called for every API request (an app-wide dependency): a read of the layer after this should have a layer."""
    _in_request.set(True)


def active_layer() -> ClinicLayer:
    """This request's layer. Never set (CLI, bench, a bare thread) means empty; inside a request that is a wiring
    bug (the route lacks ``use_clinic_layer``), so say so once per process instead of failing open silently."""
    global _warned
    layer = _active.get()
    if layer is not None:
        return layer
    if _in_request.get() and not _warned:
        _warned = True
        log.warning("clinic formulary: a request read the default EMPTY layer; a route that grounds rows or builds "
                    "hints is missing the use_clinic_layer dependency (clinic names will read as unknown)")
    return _EMPTY


def activate(layer: ClinicLayer) -> None:
    _active.set(layer)


@lru_cache(maxsize=512)
def _twin(name_key: str, lexicon_identity: str) -> str:
    found = suggest_candidates(name_key, 1, guard=False)     # a clinic's own name still gets its look-alike flag
    return found[0] if found else ""


def _lexicon_twin(name) -> str:
    """The lexicon drug a clinic name sounds like ("" if none). Looks at the lexicon only, never at the clinic list.
    Cached per ``lexicon_identity`` (shipped version + clinic overlay version), so one clinic's list never answers
    for another's."""
    from .determinism import lexicon_identity
    return _twin(key(name), lexicon_identity())


def ground_clinic(name, transcript_lower, in_transcript):
    """(status, "", issue) for a name on this clinic's list, else None. Called after the lexicon missed.

    Order (contract 4.2): not clearly dictated, then look-alike of a lexicon drug, then verified. A learned name
    gets no strengths and no dose check. The issue is None for a look-alike: the reason lives in the row's
    ``lookalike`` and an issue would open extra LLM repair calls."""
    if active_layer().get(name) is None:
        return None
    if not in_transcript(name, transcript_lower):
        return (UNVERIFIED_NAME, "", f"'{name}': not clearly dictated in transcript")
    if _lexicon_twin(name):
        return (LOOKALIKE, "", None)
    return (VERIFIED, "", None)


def source_of(name, match) -> str:
    """"clinic" for a name only the clinic's list knows (no lexicon match), else "lexicon"."""
    return "clinic" if not match and active_layer().get(name) is not None else "lexicon"


def row_extras(name, match, status) -> dict:
    """The row keys this part owns: ``source``, and ``lookalike`` for a clinic name flagged as a look-alike."""
    src = source_of(name, match)
    return {"source": src, **({"lookalike": _lexicon_twin(name)} if src == "clinic" and status == LOOKALIKE else {})}
