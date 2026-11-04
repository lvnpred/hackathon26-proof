"""Dictated orders and discharge as drafts: prompts, rules, and the checks a model reply must pass.

Pure functions. Nothing here writes. A draft becomes a record only when a person signs it (D10).
"""

from __future__ import annotations

import json
import re

from app.journey.spoken_numbers import words_to_digits
from app.morning.lexicon import ground, known_names

ORDER_PROMPT = (
    "Turn the doctor's dictated orders into JSON only, with no other text: "
    '{"reason": "", "items": [{"kind": "dose|obs|procedure|check|other", "text": "", "name": "", '
    '"amount": "", "every_h": null, "mode": "tick|start_end", "proof": "none|photo|video", "limits": {}}]}. '
    "Use only what was said. Do not give medical advice.\nTranscript: "
)
DISCHARGE_PROMPT = (
    "Turn the doctor's dictated discharge summary into JSON only, with no other text: "
    '{"sections": [{"heading": "Diagnosis|Procedure|Course on the ward|Medicines|Follow-up", "text": ""}]}. '
    "Use only what was said. Do not give medical advice.\nTranscript: "
)

UNCLEAR = "unclear"
HEADINGS = ("Diagnosis", "Procedure", "Course on the ward", "Medicines", "Follow-up")
ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)

_CLAUSE_SPLIT = re.compile(r"[.;\n](?!\d)")
_ADMIT = re.compile(r"^admit(?:ted)?\s+(?:for\s+)?(.+)", re.I)
_UNIT_WORDS = r"milligrams?|micrograms?|millilit(?:re|er)s?|grams?"
_AMOUNT = re.compile(rf"(\d+(?:\.\d+)?)\s*({_UNIT_WORDS}|mg|g|mcg|ml)\b", re.I)
_UNIT = {"milligram": "mg", "microgram": "mcg", "millilitre": "ml", "milliliter": "ml", "gram": "g"}
# Words that turn an order around (clarity §4.5, ruling P16): a clause with one is ALWAYS shown as not understood and
# keeps no item, in the model path and the rules path. Past forms, n't forms, and both apostrophes ("Don’t").
NEGATION = re.compile(
    r"\b(?:no|not|never|nil|none|without|cannot|instead\s+of|stop(?:s|ped|ping)?|hold(?:s|ing)?|held"
    r"|withh(?:old|eld)(?:s|ing)?|discontinu(?:e|es|ed|ing)|ceas(?:e|es|ed|ing)|omit(?:s|ted|ting)?"
    r"|cancel(?:s|led|ed|ling|ing)?|suspend(?:s|ed|ing)?|withdr(?:aw|aws|awn|awing|ew)|paus(?:e|es|ed|ing)"
    r"|avoid(?:s|ed|ing)?|halt(?:s|ed|ing)?|\w+n['\u2019]t"
    r"|(?:do|does|did|is|are|was|were|should|would|could|wo|ca|must|need|have|has)nt)\b",
    re.I,
)
# Each limit belongs to one vital: its value must be said after a word for that vital, and it accounts only for those
# words (ruling P16: a pulse threshold is never a systolic limit).
VITALS = {
    "sbp": re.compile(r"\b(?:sbp|systolic|bp|blood pressure)\b", re.I),
    "hr": re.compile(r"\b(?:hr|pulse|heart rate)\b", re.I),
    "spo2": re.compile(r"\b(?:spo2|oxygen|saturations?|sats?)\b", re.I),
    "temp": re.compile(r"\b(?:temp|temperature|fever)\b", re.I),
}
_ANY_VITAL = re.compile("|".join(f"(?P<{k}>{r.pattern})" for k, r in VITALS.items()), re.I)


def vital_of(key: str) -> str:
    """'sbp_min' -> 'sbp', 'hr_max' -> 'hr'."""
    return key.split("_")[0]


def limit_said(clause: str, key: str, value) -> bool:
    """The limit's value is said in the clause right after a word for its own vital (the last vital word before it)."""
    word = str(int(value)) if float(value).is_integer() else str(value)
    for found in re.finditer(rf"(?<![\d.]){re.escape(word)}(?![\d.])", clause):
        before = [m.lastgroup for m in _ANY_VITAL.finditer(clause[:found.start()])]
        if before and before[-1] == vital_of(key):
            return True
    return False


_EVERY = re.compile(r"every\s+(?:(\d+(?:\.\d+)?)\s+)?(hours?|h|hrs?|minutes?|min)\b", re.I)
_OBS = re.compile(r"\b(bp|blood pressure|pulse|obs|observations)\b", re.I)
_PROCEDURE = re.compile(r"\b(saline|drip|infusion)\b|over\s+\d+\s*(hours?|h)\b", re.I)
_SBP_MIN = re.compile(r"(?:lower|minimum|min|below|under)\D{0,25}(\d{2,3})", re.I)
_SBP_MAX = re.compile(r"(?:upper|maximum|max|above)\D{0,25}(\d{2,3})", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_DRUG = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(known_names(), key=len, reverse=True)) + r")\b", re.I)
_DOSE_UNIT = re.compile(rf"\d+\s*({_UNIT_WORDS}|mg|g|ml)\b", re.I)
_SECTION_RULES = (
    ("Diagnosis", re.compile(r"diagnos", re.I)),
    ("Medicines", None),
    ("Follow-up", re.compile(r"review|follow|clinic|appointment|stitches", re.I)),
    ("Procedure", re.compile(r"repair|surgery|operation|procedure|count", re.I)),
    ("Course on the ward", re.compile(r"ward|recover|wound|stable|mobilis|eating|drinking|pain|settled", re.I)),
)


def digits(text: str) -> str:
    """Number words become digits: 'eighty two over fifty four' -> '82 over 54' (journey/spoken_numbers.py)."""
    return words_to_digits(text)


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSE_SPLIT.split(digits(text)) if c.strip()]


def _every_h(clause: str) -> float | None:
    found = _EVERY.search(clause)
    if not found:
        return None
    amount = float(found.group(1)) if found.group(1) else 1.0
    value = amount / 60 if found.group(2).lower().startswith("m") else amount
    return value if 0 < value <= 72 else None


def _drug_in(text: str) -> str | None:
    found = _DRUG.search(text)
    return (ground(found.group(1))["generic"] or found.group(1).lower()) if found else None


def _amount(clause: str) -> str:
    found = _AMOUNT.search(clause)
    if not found:
        return ""
    unit = found.group(2).lower().rstrip("s")
    return f"{found.group(1)} {_UNIT.get(unit, unit)}"


def _tidy(item: dict) -> dict:
    """The shape the frontend's orderRowsToItems emits (P2-R9)."""
    out = {"kind": item["kind"], "text": item["text"], "mode": item.get("mode") or "tick", "proof": item.get("proof") or "none"}
    if item.get("every_h"):
        out["every_h"] = item["every_h"]
    if item["kind"] == "dose":
        for key in ("name", "amount"):
            if item.get(key):
                out[key] = item[key]
    limits = {k: v for k, v in (item.get("limits") or {}).items() if v is not None}
    if item["kind"] == "obs" and limits:
        out["limits"] = limits
    return out


def _proof_of(clause: str) -> str:
    said = clause.lower()
    return "video" if "video" in said else "photo" if "photo" in said else "none"


def _unclear(clause: str) -> dict:
    """Words not understood as an order: shown with what was heard, never signed (clarity §4.5)."""
    return {"kind": UNCLEAR, "heard": clause[:200]}


def _clause_item(clause: str) -> dict:
    item = {"kind": UNCLEAR, "text": clause[:200], "mode": "tick", "proof": _proof_of(clause)}
    drug = _drug_in(clause)
    if drug:
        item.update(kind="dose", name=drug, amount=_amount(clause))
    elif _OBS.search(clause):
        item["kind"] = "obs"
        limits = {}
        for key, rule in (("sbp_min", _SBP_MIN), ("sbp_max", _SBP_MAX)):
            found = rule.search(clause)
            if found and limit_said(clause, key, int(found.group(1))):  # "pulse below 60" is no systolic limit
                limits[key] = int(found.group(1))
        item["limits"] = limits
    elif _PROCEDURE.search(clause):
        item.update(kind="procedure", mode="start_end")
    else:
        return _unclear(clause)
    item["every_h"] = _every_h(clause)
    return _tidy(item)


def _rule_words(clause: str, item: dict) -> dict:
    """The rule item as only the words the rules read from its clause (ruling P16): the drug as said, the amount, the
    interval, the obs or procedure words. Its proof and limits fields account for their own words in `accounted`."""
    parts = []
    if item["kind"] == "dose":
        parts += [_DRUG.search(clause).group(0), item.get("amount") or ""]
    else:
        parts += [m.group(0) for m in (_OBS if item["kind"] == "obs" else _PROCEDURE).finditer(clause)]
    every = _EVERY.search(clause)
    if every and item.get("every_h"):
        parts.append(every.group(0))
    return {**item, "text": " ".join(p for p in parts if p)}


def parse_order_text(text: str) -> dict:
    from app.journey.dictation_cover import accounted  # it imports this module

    reason, items = "", []
    for clause in _clauses(text):
        admit = _ADMIT.match(clause)
        if admit:
            reason = admit.group(1).strip()[:1].upper() + admit.group(1).strip()[1:]
            continue
        item = _clause_item(clause) if not NEGATION.search(clause) else _unclear(clause)  # "stop …" is no give order
        items.append(item)
        if item["kind"] != UNCLEAR and not accounted(clause, [_rule_words(clause, item)]):  # a word no rule read: show it
            items.append(_unclear(clause))
    unclear = [i for i in items if i["kind"] == UNCLEAR]
    return {"reason": reason[:300], "items": [i for i in items if i["kind"] != UNCLEAR][:20], "unclear": unclear[:20]}


_PROOF_WORD = re.compile(r"\b(photo|picture|video)\b", re.I)


def _limit_span(rule: re.Pattern, window: str, value: int) -> tuple[int, int] | None:
    found = rule.search(window)
    if not found:
        return None
    if found.group(1) == str(value):
        return found.span(1)
    after = re.search(rf"\b{value}\b", window[found.start():])
    return (found.start() + after.start(), found.start() + after.end()) if after else None


def order_spans(transcript: str, items: list[dict]) -> dict:
    """Where each order field was said (R9). Offsets index digits(transcript), returned as `text`.

    Per item, a window is the item's own clause (or the whole text for a paraphrase); a field not found gets no mark,
    and a mark that overlaps an earlier one is dropped.
    """
    text = digits(transcript)
    marks: list[dict] = []
    for index, item in enumerate(items):
        own = (item.get("text") or "").strip()
        at = text.lower().find(own.lower()) if own else -1
        lo, hi = (at, at + len(own)) if at >= 0 else (0, len(text))
        window = text[lo:hi]
        found: list[tuple[str, tuple[int, int] | None]] = []
        name = (item.get("name") or "").strip()
        if name:
            hit = re.search(rf"\b{re.escape(name)}\b", window, re.I)
            found.append(("name", hit.span() if hit else None))
        if item.get("amount"):
            hit = _AMOUNT.search(window)
            found.append(("amount", hit.span() if hit else None))
        if item.get("every_h"):
            hit = _EVERY.search(window)
            found.append(("every_h", hit.span() if hit else None))
        for key, rule in (("sbp_min", _SBP_MIN), ("sbp_max", _SBP_MAX)):
            value = (item.get("limits") or {}).get(key)
            if value is not None:
                found.append((f"limits.{key}", _limit_span(rule, window, value)))
        if item.get("proof") and item["proof"] != "none":
            hit = _PROOF_WORD.search(window)
            found.append(("proof", hit.span() if hit else None))
        marks += [{"start": lo + span[0], "end": lo + span[1], "item": index, "field": field} for field, span in found if span]
    marks.sort(key=lambda m: m["start"])
    kept: list[dict] = []
    for mark in marks:
        if not kept or mark["start"] >= kept[-1]["end"]:
            kept.append(mark)
    return {"text": text, "marks": kept}


def discharge_sections(text: str) -> list[dict]:
    return discharge_draft(text)["sections"]


def discharge_draft(text: str) -> dict:
    """Sections by rule, and `unplaced`: sentences no rule places, for the doctor to place (clarity §4.5)."""
    found: dict[str, list[str]] = {}
    unplaced: list[str] = []
    for sentence in _clauses(text):
        heading = None
        for name, rule in _SECTION_RULES:
            hit = (_DRUG.search(sentence) or _DOSE_UNIT.search(sentence)) if rule is None else rule.search(sentence)
            if hit:
                heading = name
                break
        if heading is None:
            unplaced.append(sentence + ".")
            continue
        cue = re.match(rf"{re.escape(heading)}\s*:\s*(?=\S)", sentence, re.I)
        if cue:  # a spoken heading cue would double the heading
            sentence = sentence[cue.end():]
            sentence = sentence[:1].upper() + sentence[1:]
        found.setdefault(heading, []).append(sentence + ".")
    return {"sections": [{"heading": h, "text": " ".join(found[h])[:600]} for h in HEADINGS if h in found],
            "unplaced": [u[:600] for u in unplaced[:20]]}


_STOP = set(
    "the and for with that this from was were has have had are not but his her they them then than into onto "
    "per all any out off its our can may will been being over under".split()
)
_WORD = re.compile(r"[a-z]{3,}")
# Words that flip a meaning. Each must be said as often as the text uses it.
DIRECTION = re.compile(r"\b(no|not|never|without|over|under|above|below|before|after)\b", re.I)


def _words_heard(text: str, heard: str) -> bool:
    """Every content word (3+ letters, not a stopword) of `text` is in `heard`, allowing a plural 's'."""
    said = set(_WORD.findall(heard))
    return all(w in said or w.rstrip("s") in said or w + "s" in said for w in _WORD.findall(text.lower()) if w not in _STOP)


def grounded(text: str, transcript: str) -> bool:
    """Every number, drug name, advice word and content word in `text` is also in the transcript."""
    heard = digits(transcript).lower()
    if not _words_heard(text, heard):
        return False
    heard_numbers = set(_NUMBER.findall(heard))
    if not set(_NUMBER.findall(text)) <= heard_numbers:
        return False
    if any(d.lower() not in heard for d in _DRUG.findall(text)):
        return False
    if not all(w.lower() in heard for w in ADVICE.findall(text)):
        return False
    said = [w.lower() for w in DIRECTION.findall(heard)]
    return all(said.count(w) >= n for w, n in _counts(DIRECTION.findall(text.lower())).items())


def _counts(words: list[str]) -> dict[str, int]:
    return {w: words.count(w) for w in set(words)}


def _json_of(reply: str | None) -> dict | None:
    match = re.search(r"\{.*\}", reply or "", re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _item_grounded(item: dict, transcript: str) -> bool:
    limits = " ".join(str(v) for v in (item.get("limits") or {}).values() if v is not None)
    name = item.get("name") or ""
    if name and name.lower() not in digits(transcript).lower():
        return False
    if not all(grounded(str(item.get(k) or ""), transcript) for k in ("text", "name", "amount")) or not grounded(limits, transcript):
        return False
    heard = transcript.lower()
    if item.get("proof") == "photo" and not re.search(r"photo|picture", heard):
        return False
    if item.get("proof") == "video" and "video" not in heard:
        return False
    if item.get("mode") == "start_end" and not _PROCEDURE.search(item["text"]):
        return False
    return item.get("every_h") is None or item["every_h"] == _every_h(item["text"])


def items_from_reply(reply: str | None, transcript: str) -> dict | None:
    from pydantic import ValidationError

    from app.journey.dictation_cover import place  # it imports this module
    from app.journey.flow_api import OrderItem  # flow_api -> states -> dictation would cycle at import

    data = _json_of(reply)
    raw = data.get("items") if data else None
    reason = data.get("reason", "") if data else ""
    if not isinstance(raw, list) or not 1 <= len(raw) <= 20 or not isinstance(reason, str):
        return None
    if len(reason) > 300 or not grounded(reason, transcript):
        return None
    items = []
    for entry in raw:  # grounding is per item (clarity §4.5): an item not heard is left out, the others keep their fields
        try:
            item = OrderItem.model_validate(entry).model_dump()
        except ValidationError:
            continue
        if _item_grounded(item, transcript):
            items.append(_tidy(item))
    items, unclear = place(transcript, items)  # each item grounded in ONE clause (ruling P14)
    if not items:
        return None
    unclear = [_unclear(c) for c in unclear]
    return {"reason": reason.strip(), "items": items, "unclear": unclear}


def sections_from_reply(reply: str | None, transcript: str) -> list | None:
    data = _json_of(reply)
    raw = data.get("sections") if data else None
    if not isinstance(raw, list) or not 1 <= len(raw) <= len(HEADINGS):
        return None
    out = []
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {"heading", "text"}:
            return None
        text = entry["text"]
        if entry["heading"] not in HEADINGS or not isinstance(text, str) or not 1 <= len(text) <= 600:
            return None
        if not grounded(text, transcript):
            return None
        out.append({"heading": entry["heading"], "text": text})
    return out


def open_drafts(events: list[dict]) -> dict:
    out = {}
    for kind in ("order", "discharge"):
        drafted = [e for e in events if e["event_type"] == f"{kind}.drafted"]
        signed = {e["payload"].get("draft_id") for e in events if e["event_type"] == f"{kind}.signed"}
        last = drafted[-1] if drafted else None
        out[kind] = {"id": last["id"], "at_ms": last["ts_ms"], **last["payload"]} if last and last["id"] not in signed else None
    return out


def draft_refusal(events: list[dict], kind: str, draft_id: str | None) -> tuple[int, str] | None:
    """(status, detail) when `draft_id` cannot be signed as a `kind` draft of this episode, else None."""
    if draft_id is None:
        return None
    if not any(e["id"] == draft_id and e["event_type"] == f"{kind}.drafted" for e in events):
        return 404, "Draft not found"
    if any(e["event_type"] == f"{kind}.signed" and e["payload"].get("draft_id") == draft_id for e in events):
        return 409, "This draft is already signed."
    return None
