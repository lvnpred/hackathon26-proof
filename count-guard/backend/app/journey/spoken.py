"""Spoken task completion: which open tasks a sentence is about, and what values it states.

Pure functions. Nothing here writes. The nurse confirms one candidate with a tap (D10).
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import TypeAdapter, ValidationError

from app.journey.dictation import _json_of, digits, grounded
from app.journey.flow_api import Values
from app.journey.rx import key_of

TASK_PROMPT = (
    "A nurse said which ward task she finished. Reply with JSON only, with no other text: "
    '{"task_ids": [], "values": {}}. '
    "Choose task_ids only from the open tasks below. "
    "Put in values only numbers she said, using the keys sbp, dbp, hr, spo2 and temp. "
    "Omit a value that was not said; never write 0 or null for it. "
    "Do not give medical advice.\nOpen tasks (id: title):\n"
)

OPEN = ("open", "running")
_BP = re.compile(r"(\d{2,3})\s*(?:over|/)\s*(\d{2,3})", re.I)
_HR = re.compile(r"(?:pulse|heart rate|hr)\D{0,10}(\d{2,3})", re.I)
_SPO2 = re.compile(r"(?:sats?|saturation|spo2|oxygen)\D{0,10}(\d{2,3})", re.I)
_TEMP = re.compile(r"temp(?:erature)?\D{0,10}(\d{2}(?:\.\d)?)", re.I)
_OBS_WORD = re.compile(r"\b(bp|pressure|pulse|obs)\b", re.I)
_WORD = re.compile(r"[a-z]{3,}")
_STOP = set("every hour hours minute minutes with this that from over each after before times done given".split())
_CHECKS = {
    name: TypeAdapter(Annotated[field.annotation, *field.metadata]) for name, field in Values.model_fields.items()
}


def task_prompt(tasks: list[dict]) -> str:
    """The prompt with this ward's open tasks listed, ready for the transcript to follow."""
    rows = "\n".join(f"{t['id']}: {t['title']}" for t in tasks if t["status"] in OPEN)
    return f"{TASK_PROMPT}{rows}\nTranscript: "


def parse_values(text: str) -> dict:
    heard = digits(text)
    out: dict = {}
    if found := _BP.search(heard):
        out["sbp"], out["dbp"] = int(found.group(1)), int(found.group(2))
    for key, rule in (("hr", _HR), ("spo2", _SPO2)):
        if found := rule.search(heard):
            out[key] = int(found.group(1))
    if found := _TEMP.search(heard):
        out["temp"] = float(found.group(1))
    return out


def _matches(text: str, heard: str, words: set[str], task: dict) -> bool:
    if task["kind"] == "dose":
        wanted = key_of(task.get("name") or task["title"])
        return wanted in heard or any(key_of(w) == wanted for w in words)
    if task["kind"] == "obs":
        return "sbp" in parse_values(text) or bool(_OBS_WORD.search(heard))
    return any(w in words for w in _WORD.findall(task["title"].lower()) if len(w) >= 4 and w not in _STOP)


def match_tasks(text: str, tasks: list[dict]) -> list[str]:
    """Ids of the open or running tasks the text is about, in task order."""
    heard = digits(text).lower()
    words = set(_WORD.findall(heard))
    return [t["id"] for t in tasks if t["status"] in OPEN and _matches(text, heard, words, t)]


def _value_ok(key: str, value) -> bool:
    check = _CHECKS.get(key)
    if check is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        check.validate_python(value)
    except ValidationError:
        return False
    return True


def _without_placeholders(values: dict, transcript: str) -> dict:
    """Drop null entries, and a 0 for a key the rules did not read from the transcript: both mean "not said"."""
    stated = parse_values(transcript)
    return {k: v for k, v in values.items() if v is not None and not (v == 0 and not isinstance(v, bool) and k not in stated)}


def completion_from_reply(reply: str | None, tasks: list[dict], transcript: str) -> dict | None:
    """The model's {"task_ids", "values"} when the transcript supports all of it, else None."""
    data = _json_of(reply)
    ids, values = (data or {}).get("task_ids"), (data or {}).get("values", {})
    if not isinstance(ids, list) or not ids or not isinstance(values, dict):
        return None
    values = _without_placeholders(values, transcript)
    open_ids = {t["id"] for t in tasks if t["status"] in OPEN}
    if not all(isinstance(i, str) and i in open_ids for i in ids):
        return None
    # A model may only name a task the sentence is about, and only repeat numbers that were said.
    if not set(ids) <= set(match_tasks(transcript, tasks)):
        return None
    if not all(_value_ok(k, v) and grounded(str(v), transcript) for k, v in values.items()):
        return None
    return {"task_ids": [t["id"] for t in tasks if t["id"] in ids], "values": values}
