"""Which said clauses a model's order draft accounts for (clarity §4.5, ruling P14), so no said order vanishes.

Each kept item is grounded in ONE clause (its home): its drug name, its numbers and its interval are in that clause, and
half its key words. An item with no home is rejected. A clause is covered only when the items at home in it TOGETHER
account for every drug name, every number, every observation or procedure word, and every key word in it (a name the
lexicon does not know, "with codeine"). A clause with a word that turns an order around ("stop", "do not", "omit") is
ALWAYS shown and keeps no item, and an item whose own text says such a word is never kept (ruling P16). A limit is at
home only where its value follows a word for its own vital, and accounts only for that vital's words. Anything else in
a clause makes the whole clause "not understood". When in doubt, a clause is shown as not understood.
"""

from __future__ import annotations

from collections import Counter

import re

from app.journey.dictation import (
    _ADMIT, _DRUG, _EVERY, _NUMBER, _OBS, _PROCEDURE, _STOP, _UNIT, _UNIT_WORDS, _WORD, NEGATION, VITALS, _clauses, digits, limit_said,
    vital_of,
)
from app.morning.lexicon import ground

# Timing words every order shares: they say nothing about which order a clause is.
_GENERIC = {"every", "hour", "hr", "minute", "min", "day", "time", "daily", "dose", "take", "given"}
# Filler that joins or softens orders and names none.
_FILLER = {"also", "plus", "then", "please", "give", "patient", "can", "should", "need"}
# Words an item's own fields stand for: its proof, its limits (each limit only the words of its own vital).
_PROOF_WORDS = {"photo": {"photo", "picture", "strip", "monitor", "proof", "image"}, "video": {"video", "clip", "proof"}}
_LIMIT_WORDS = {"lower", "upper", "limit", "minimum", "maximum", "below", "above", "under", "over", "call", "alert"}
_VITAL_WORDS = {"sbp": {"sbp", "systolic", "blood", "pressure"}, "hr": {"pulse", "heart", "rate"},
                "spo2": {"spo2", "oxygen", "saturation", "sat"}, "temp": {"temp", "temperature", "fever"}}
_UNIT_WORD = re.compile(rf"\b({_UNIT_WORDS})\b", re.I)


def _units(text: str) -> str:
    """'500 milligrams' -> '500 mg': a spoken unit is the same word as its short form."""
    return _UNIT_WORD.sub(lambda m: _UNIT.get(m.group(1).lower().rstrip("s"), m.group(1)), text)


def keywords(text: str) -> set[str]:
    return {w.rstrip("s") for w in _WORD.findall(_units(digits(text)).lower()) if w not in _STOP} - _GENERIC - _FILLER


def numbers(text: str) -> Counter:
    return Counter(_NUMBER.findall(digits(text)))


def _said(transcript: str) -> list[str]:
    return [c for c in _clauses(transcript) if not _ADMIT.match(c) and (keywords(c) or numbers(c))]


def _everys(clause: str) -> set[float]:
    out = set()
    for found in _EVERY.finditer(digits(clause)):
        amount = float(found.group(1)) if found.group(1) else 1.0
        out.add(amount / 60 if found.group(2).lower().startswith("m") else amount)
    return out


def _word_of(value) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _stated(item: dict) -> Counter:
    """The numbers an item states, each as often as its text says it (max over text, amount and limits)."""
    limits = Counter(_word_of(v) for v in (item.get("limits") or {}).values() if v is not None)
    return numbers(str(item.get("text") or "")) | numbers(str(item.get("amount") or "")) | limits


def _item_numbers(item: dict) -> Counter:
    """What an item accounts for in its clause: the numbers it states, and its interval."""
    every = item.get("every_h")
    return _stated(item) | (Counter([_word_of(every)]) if every is not None else Counter())


def _names(item: dict) -> set[str]:
    """The drug an item names: its name field, else a drug its text says ("saline drip with paracetamol"), with the generic."""
    found = [str(item.get("name") or "").strip().lower()] if item.get("name") else _DRUG.findall(str(item.get("text") or ""))
    return {w for n in found for w in (n.lower(), str(ground(n.lower())["generic"] or n).lower())} - {""}


def _item_words(item: dict) -> set[str]:
    """The key words an item accounts for: its text and name, and the words its proof and limits stand for."""
    words = keywords(f"{item.get('text') or ''} {item.get('name') or ''}") | _PROOF_WORDS.get(item.get("proof") or "", set())
    for key, value in (item.get("limits") or {}).items():
        if value is not None:
            words |= _LIMIT_WORDS | _VITAL_WORDS.get(vital_of(key), set())
    return words


def item_in(item: dict, clause: str) -> bool:
    """The item is grounded in this one clause: its name, its numbers, its interval, and half its key words."""
    heard = digits(clause).lower()
    name = str(item.get("name") or "").strip().lower()
    if name and name not in heard:
        return False
    if _stated(item) - numbers(clause):
        return False
    if item.get("every_h") is not None and item["every_h"] not in _everys(clause):
        return False
    if any(v is not None and not limit_said(heard, k, v) for k, v in (item.get("limits") or {}).items()):
        return False  # "pulse below 60" is no systolic limit (ruling P16)
    words = keywords(str(item.get("text") or ""))
    return bool(name or words) and len(words & keywords(clause)) * 2 >= len(words)


def accounted(clause: str, items: list[dict]) -> bool:
    """The items at home in this clause together account for every drug, number and obs or procedure word in it."""
    if not items:
        return False
    heard = digits(clause).lower()
    named = Counter(n for i in items for n in _names(i))
    for drug, n in Counter(d.lower() for d in _DRUG.findall(heard)).items():
        generic = str(ground(drug)["generic"] or drug).lower()
        if max(named[drug], named[generic]) < n:
            return False
    have = sum((_item_numbers(i) for i in items), Counter())
    if numbers(clause) - have:
        return False
    if not keywords(clause) <= set().union(*(_item_words(i) for i in items)):  # "with codeine", "nil by mouth"
        return False
    if NEGATION.search(heard):  # a stop or not word: always shown (ruling P16)
        return False
    if _OBS.search(heard) and not any(i["kind"] == "obs" for i in items):
        return False
    return not _PROCEDURE.search(heard) or any(i["kind"] == "procedure" or i.get("mode") == "start_end" for i in items)


def place(transcript: str, candidates: list[dict]) -> tuple[list[dict], list[str]]:
    """(kept items, clauses not understood). A candidate with no home clause is not kept; see the module doc.

    A model item that was not kept was said (if at all) in a clause the kept items do not account for, and every such
    clause is already shown, so a rejected item needs no clause of its own."""
    said = _said(transcript)
    homes: dict[int, list[dict]] = {}
    for item in candidates:
        if NEGATION.search(f"{item.get('text') or ''} {item.get('name') or ''}"):
            continue  # an item that says stop or not is never kept (ruling P16)
        fits = [n for n, clause in enumerate(said) if item_in(item, clause)]
        # The first fitting clause that has no item like it yet: the same order said twice is two clauses, two items.
        free = [n for n in fits if not any(_same(item, other) for other in homes.get(n, []))]
        home = (free or fits or [None])[0]
        if home is not None:
            homes.setdefault(home, []).append(item)
    out = [n for n, clause in enumerate(said) if not accounted(clause, homes.get(n, []))]
    # A clause that turns an order around keeps none of its items: never a give order (ruling P16).
    kept = [i for n, items in sorted(homes.items()) if not NEGATION.search(said[n]) for i in items]
    kept.sort(key=lambda i: next(k for k, c in enumerate(candidates) if c is i))
    return kept, [said[n][:200] for n in out][:20]


def _same(a: dict, b: dict) -> bool:
    return (a.get("kind"), str(a.get("name") or "").lower()) == (b.get("kind"), str(b.get("name") or "").lower())


def unplaced_sentences(transcript: str, texts: list[str]) -> list[str]:
    """Sentences no single section stands for: every drug name, number and key word of the sentence in ONE section.

    Every key word, not half: a name the lexicon does not know ("codeine") is only a key word, and must not be lost."""
    out = []
    for sentence in _said(transcript):
        words, nums = keywords(sentence), numbers(sentence)
        drugs = {d.lower() for d in _DRUG.findall(digits(sentence))}
        if not any(not (nums - numbers(t)) and all(d in digits(t).lower() for d in drugs) and words <= keywords(t)
                   for t in texts):
            out.append(f"{sentence[:599]}.")
    return out[:20]
