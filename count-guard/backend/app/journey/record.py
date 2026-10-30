"""The patient's record lines and a bot that answers only from them.

Every line is built from one event of this episode, so a bot answer can always point at its source.
Nothing here advises: the wrappers name who said what, and the content is the record's own words.
"""

from __future__ import annotations

import re

from app.journey.dictation import ADVICE, _DRUG, _STOP, _WORD, _json_of, digits, grounded
from app.journey.rx import key_of
from app.journey.schedule import build, schedule_text
from app.journey.states import DID
from app.journey.stories import clock
from app.morning.discharge import visible_events

NOT_FOUND = "I can't find that in your record."
FOUND = "Here is what your record says."
BOT = "Record bot"
MAX_LINE = 300

BOT_PROMPT = (
    "A patient asks about their own hospital record. Answer only from the numbered lines below. "
    'Reply with JSON only: {"answer": "...", "sources": ["L1"]}. The answer restates the cited lines '
    "in plain words and adds nothing. If no line answers the question, reply "
    '{"answer": "", "sources": []}. Do not give medical advice.\nLines:\n'
)

WRAPPERS = {
    "prescription": "Prescription from {by}: {medicine} — {schedule}.",
    "advice": "Note on the prescription from {by}: {item}",
    "review": "Follow-up on the prescription: {review}",
    "order": "Order signed by {by} at {clock}: {text}",
    "task": "{title}: done by {by} at {clock}.",
    "discharge": "Discharge summary from {by}: {sentence}",
    "wound": "Wound care on your discharge card: {wound_care}",
    "sign": "Warning sign on your discharge card: {sign}",
    "card_review": "Review on your discharge card: {review}",
    "help": "Help line on your discharge card: {help_line}",
    "moved": "{by} {did} at {clock}.",
    "admitted": "You were admitted to the ward the day before.",
    "answer": "{by} answered your question: {answer}",
    "photo_review": "{by} reviewed your healing photo at {clock}: {label}.",
}

ASK_STOP = _STOP | {
    "when", "what", "which", "where", "should", "could", "would", "does", "take", "have", "about",
    "much", "many", "need", "your", "tell", "know", "please", "there", "their",
}


def bot_prompt(lines: list[dict]) -> str:
    rows = "\n".join(f"{line['id']}: {line['text']}" for line in lines)
    return f"{BOT_PROMPT}{rows}\nQuestion: "


def _w(key: str, **fields) -> str | None:
    """A wrapper filled in, or None when any field is missing or empty (no 'None' line can be cited)."""
    if not all(isinstance(v, str) and v.strip() for v in fields.values()):
        return None
    return WRAPPERS[key].format(**fields)


def _latest_ids(events: list[dict], kind: str) -> set[str]:
    rows = [e["id"] for e in events if e["event_type"] == kind]
    return set(rows[-1:])


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def _event_lines(event: dict, ctx: dict) -> list[tuple]:
    """(kind, text) pairs for one event; a prescription row adds its key. The wrapper is fixed; the content is the record's own."""
    kind, p = event["event_type"], event.get("payload") or {}
    when = clock(event["ts_ms"])
    if kind == "rx.ordered" and event["id"] in ctx["rx"]:
        by = p.get("by")
        rows = [
            ("prescription", _w("prescription", by=by, medicine=row["medicine"], schedule=schedule_text(row)), row["key"])
            for row in build(p)
        ]
        notes = [("prescription", _w("advice", by=by, item=item)) for item in p.get("advice") or []]
        review = p.get("review")
        return rows + notes + ([("prescription", _w("review", review=review))] if review else [])
    if kind == "order.signed":
        return [("order", _w("order", by=p.get("by"), clock=when, text=i.get("text", ""))) for i in p.get("items") or []]
    if kind == "task.done" and event["id"] in ctx["done"]:
        title = ctx["titles"].get(p.get("task_id"))
        return [("task", _w("task", title=title, by=p.get("by"), clock=when))] if title else []
    if kind == "discharge.signed":
        return [("discharge", _w("discharge", by=p.get("by"), sentence=s)) for s in _sentences(p.get("summary"))]
    if kind == "discharge.card" and event["id"] in ctx["card"]:
        out = [("card", _w("wound", wound_care=p.get("wound_care", "")))]
        out += [("card", _w("sign", sign=sign)) for sign in p.get("warning_signs") or []]
        out.append(("card", _w("card_review", review=p.get("review", ""))))
        out.append(("card", _w("help", help_line=p.get("help_line", ""))))
        return out
    if kind == "patient.state":
        if p.get("from") is None:
            return [("stay", WRAPPERS["admitted"])]
        did = DID.get(p.get("to"))
        return [("stay", _w("moved", by=p.get("by"), did=did, clock=when))] if did else []
    if kind == "question.answered" and p.get("source") == "doctor":
        return [("answer", _w("answer", by=p.get("by"), answer=p.get("answer", "")))]
    if kind == "review.answered":
        return [("review", _w("photo_review", by=p.get("by"), clock=when, label=p.get("label", "")))]
    return []


def record_lines(events: list[dict]) -> list[dict]:
    """The patient's record as numbered lines, in ledger order, each tied to the event it came from."""
    shown = visible_events(events)
    done: dict[str, str] = {}
    for event in shown:
        if event["event_type"] == "task.done":
            done[event["payload"].get("task_id")] = event["id"]
    ctx = {
        "rx": _latest_ids(shown, "rx.ordered"),
        "card": _latest_ids(shown, "discharge.card"),
        "done": set(done.values()),
        "titles": {e["id"]: e["payload"].get("title") for e in shown if e["event_type"] == "task.created"},
    }
    lines = []
    for event in shown:
        for kind, text, *key in _event_lines(event, ctx):
            if text is None:
                continue
            line = {"id": f"L{len(lines) + 1}", "kind": kind, "text": text[:MAX_LINE], "event_id": event["id"]}
            lines.append({**line, "key": key[0]} if key else line)
    return lines


def _has(word: str, said: set[str]) -> bool:
    return word in said or word.rstrip("s") in said or word + "s" in said


def _keys(text: str) -> set[str]:
    return {key_of(name) for name in _DRUG.findall(text)}


def rules_answer(question: str, lines: list[dict]) -> dict:
    """Quote the best-matching record lines. No match means 'not found'; nothing is added."""
    heard = digits(question).lower()
    words = {w for w in _WORD.findall(heard) if len(w) >= 4 and w not in ASK_STOP}
    asked = _keys(heard)
    scored = []
    for line in lines:
        said = set(_WORD.findall(line["text"].lower()))
        scored.append(sum(_has(w, said) for w in words) + 2 * len(asked & _keys(line["text"])))
    best = max(scored, default=0)
    if best < 1:
        return {"answer": NOT_FOUND, "sources": [], "found": False}
    top = [line for line, score in zip(lines, scored) if score == best]
    return {"answer": FOUND, "sources": top[:3], "found": True}


def _windows(question: str) -> set[str]:
    """`key_of` of every word and every pair of neighbouring words in the question."""
    words = re.findall(r"[a-z]+", question.lower())
    return {key_of(" ".join(words[i:i + n])) for n in (1, 2) for i in range(len(words) - n + 1)}


def medicine_answer(question: str, lines: list[dict], read_rows: list[dict]) -> dict | None:
    """R27: a medicine named in the question, by key equality. The prescription row is quoted; nothing is added.

    A medicine read from the patient's photo but not prescribed gets one fixed sentence. Else None."""
    asked = _windows(question)
    rows = [line for line in lines if line.get("key") in asked]
    if rows:
        return {"answer": FOUND, "sources": rows[:3], "found": True}
    for row in read_rows:
        if row.get("flag") == "not_prescribed" and row.get("key") in asked:
            return {"answer": f"{row['name'].capitalize()} is not on your prescription. Ask Dr. Rao.", "sources": [], "found": False}
    return None


def answer_from_reply(reply: str | None, lines: list[dict]) -> dict | None:
    """A model reply is used only if it cites real lines and says nothing those lines do not say."""
    data = _json_of(reply)
    if not data:
        return None
    ids, answer = data.get("sources"), data.get("answer")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 3 or not isinstance(answer, str):
        return None
    by_id = {line["id"]: line for line in lines}
    if not all(isinstance(i, str) and i in by_id for i in ids):
        return None
    cited = [by_id[i] for i in dict.fromkeys(ids)]
    answer = answer.strip()
    if not 1 <= len(answer) <= 400 or ADVICE.search(answer):
        return None
    if not grounded(answer, " ".join(line["text"] for line in cited)):
        return None
    return {"answer": answer, "sources": cited, "found": True}
