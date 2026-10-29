"""Dictated orders and discharge as drafts: prompts, rules, and the checks a model reply must pass.

Pure functions. Nothing here writes. A draft becomes a record only when a person signs it (D10).
"""

from __future__ import annotations

import json
import re

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

HEADINGS = ("Diagnosis", "Procedure", "Course on the ward", "Medicines", "Follow-up")
ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)

_UNITS = (
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen"
).split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
_NUMBER_WORDS = re.compile(
    rf"\b(?:({'|'.join(_TENS)})(?:[\s-]+({'|'.join(_UNITS[:9])}))?|({'|'.join(_UNITS)}))\b", re.I
)
_CLAUSE_SPLIT = re.compile(r"[.;\n](?!\d)")
_ADMIT = re.compile(r"^admit(?:ted)?\s+(?:for\s+)?(.+)", re.I)
_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|g|gram|grams|mcg|ml)\b", re.I)
_EVERY = re.compile(r"every\s+(?:(\d+(?:\.\d+)?)\s+)?(hours?|h|hrs?|minutes?|min)\b", re.I)
_OBS = re.compile(r"\b(bp|blood pressure|pulse|obs|observations)\b", re.I)
_PROCEDURE = re.compile(r"\b(saline|drip|infusion)\b|over\s+\d+\s*(hours?|h)\b", re.I)
_SBP_MIN = re.compile(r"(?:lower|minimum|min|below|under)\D{0,25}(\d{2,3})", re.I)
_SBP_MAX = re.compile(r"(?:upper|maximum|max|above)\D{0,25}(\d{2,3})", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_DRUG = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(known_names(), key=len, reverse=True)) + r")\b", re.I)
_DOSE_UNIT = re.compile(r"\d+\s*(mg|g|ml)\b", re.I)
_SECTION_RULES = (
    ("Diagnosis", re.compile(r"diagnos", re.I)),
    ("Medicines", None),
    ("Follow-up", re.compile(r"review|follow|clinic|appointment|stitches", re.I)),
    ("Procedure", re.compile(r"repair|surgery|operation|procedure|count", re.I)),
)


def digits(text: str) -> str:
    """Number words become digits: 'eighty two over fifty four' -> '82 over 54'."""

    def swap(match: re.Match) -> str:
        tens, unit, single = (g.lower() if g else None for g in match.groups())
        if single:
            return str(_UNITS.index(single) + 1)
        return str((_TENS.index(tens) + 2) * 10 + (_UNITS.index(unit) + 1 if unit else 0))

    return _NUMBER_WORDS.sub(swap, text)


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
    unit = "g" if found.group(2).lower().startswith("gram") else found.group(2).lower()
    return f"{found.group(1)} {unit}"


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


def _clause_item(clause: str) -> dict:
    item = {"kind": "other", "text": clause[:200], "mode": "tick", "proof": "photo" if "photo" in clause.lower() else "none"}
    drug = _drug_in(clause)
    if drug:
        item.update(kind="dose", name=drug, amount=_amount(clause))
    elif _OBS.search(clause):
        item["kind"] = "obs"
        limits = {}
        for key, rule in (("sbp_min", _SBP_MIN), ("sbp_max", _SBP_MAX)):
            found = rule.search(clause)
            if found:
                limits[key] = int(found.group(1))
        item["limits"] = limits
    elif _PROCEDURE.search(clause):
        item.update(kind="procedure", mode="start_end")
    item["every_h"] = _every_h(clause)
    return _tidy(item)


def parse_order_text(text: str) -> dict:
    reason, items = "", []
    for clause in _clauses(text):
        admit = _ADMIT.match(clause)
        if admit:
            reason = admit.group(1).strip()[:1].upper() + admit.group(1).strip()[1:]
        else:
            items.append(_clause_item(clause))
    return {"reason": reason[:300], "items": items[:20]}


def discharge_sections(text: str) -> list[dict]:
    found: dict[str, list[str]] = {}
    for sentence in _clauses(text):
        heading = "Course on the ward"
        for name, rule in _SECTION_RULES:
            hit = (_DRUG.search(sentence) or _DOSE_UNIT.search(sentence)) if rule is None else rule.search(sentence)
            if hit:
                heading = name
                break
        found.setdefault(heading, []).append(sentence + ".")
    return [{"heading": h, "text": " ".join(found[h])[:600]} for h in HEADINGS if h in found]


_STOP = set(
    "the and for with that this from was were has have had are not but his her they them then than into onto "
    "per all any out off its our can may will been being over under".split()
)
_WORD = re.compile(r"[a-z]{3,}")


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
    return all(w.lower() in heard for w in ADVICE.findall(text))


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

    from app.journey.flow_api import OrderItem  # flow_api -> states -> dictation would cycle at import

    data = _json_of(reply)
    raw = data.get("items") if data else None
    reason = data.get("reason", "") if data else ""
    if not isinstance(raw, list) or not 1 <= len(raw) <= 20 or not isinstance(reason, str):
        return None
    if len(reason) > 300 or not grounded(reason, transcript):
        return None
    items = []
    for entry in raw:
        try:
            item = OrderItem.model_validate(entry).model_dump()
        except ValidationError:
            return None
        if not _item_grounded(item, transcript):
            return None
        items.append(_tidy(item))
    return {"reason": reason.strip(), "items": items}


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
