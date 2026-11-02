"""Ask routes: the record bot, a question to the doctor, and a healing photo the doctor decides on.

The patient's `by` is always the episode label, never a body field. The doctor's spoken answer is
heard here but written only when the doctor confirms the text (D10).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import Field

from app.journey import states
from app.journey.api import At, _at, _require, _store, settle, view
from app.journey import live, switches
from app.journey.ask import ANSWERED, DECISIONS, PHOTO_STATES
from app.journey.media_api import _heard, _structure, keep_photo_evidence, read_upload_photo, strips_from, write_photo
from app.journey.medicines import dose_rows, match_medicines, record_holds
from app.journey.tasks import orders_list
from app.journey.record import BOT, answer_from_reply, bot_prompt, medicine_answer, record_lines, rules_answer

ask_router = APIRouter(prefix="/journey/episodes/{episode_id}")

BOT_ANSWERS = "The record bot answers this question."
REVIEWED = "This photo is reviewed already."
PHOTO_REFUSED = "A healing photo is sent once the visit is closed or you are home."
MEDICINES_REFUSED = "A medicines photo is checked once the visit is closed or you are home."
NO_MEDICINES = "There is no prescription or signed medicine order on your record yet, so the medicines cannot be matched."
WARD_VIEW = ("discharging", "home")  # states in which a dose order is a ward order, not a home one
DOCTOR_ONLY = "Only the doctor marks medicines from home."


class QuestionIn(At):
    text: str = Field(min_length=1, max_length=300)


class AnswerIn(At):
    text: str = Field(min_length=1, max_length=1000)
    by: str = Field(min_length=1, max_length=80)
    via: Literal["text", "voice"] = "text"
    heard_by: str = Field(default="", max_length=40)


class DecisionIn(At):
    decision: Literal["no_visit", "come_in", "call"]
    note: str = Field(default="", max_length=300)
    by: str = Field(min_length=1, max_length=80)


class MarkIn(At):
    row: int = Field(ge=0)
    mark: Literal["noted", "discuss"]
    by: str = Field(min_length=1, max_length=80)


class SeenCheckinIn(At):
    by: str = Field(min_length=1, max_length=80)


def _write(request: Request, episode_id: str, rows: list[tuple[str, dict]], ts: int) -> dict:
    store = _store(request)
    for kind, payload in rows:
        store.append(episode_id, kind, payload, ts_ms=ts)
    settle(request, episode_id, ts)
    return view(request, episode_id)


def _asked(request: Request, episode_id: str, body: QuestionIn, to: str) -> tuple[dict, list[dict], int]:
    episode = _require(request, episode_id)
    events = _store(request).events(episode_id)
    asked = {"to": to, "text": body.text, "by": episode["label"]}
    return asked, events, _at(_store(request), episode_id, body.at_ms)


@ask_router.post("/ask/bot")
def ask_bot(episode_id: str, body: QuestionIn, request: Request) -> dict:
    asked, events, ts = _asked(request, episode_id, body, "bot")
    lines = record_lines(events)  # this episode's events only
    read = [e["payload"] for e in events if e["event_type"] == "medicines.read"]
    result, source, calls = medicine_answer(body.text, lines, read[-1]["rows"] if read else []), "rules", []
    if result is None:  # a medicine named in the question is answered by the rule, with no model call (R27)
        result, source, calls = _structure(
            request.app.state.settings, bot_prompt(lines), body.text,
            lambda reply, question: answer_from_reply(reply, lines), lambda question: rules_answer(question, lines),
        )
    store = _store(request)
    question = store.append(episode_id, "question.asked", asked, ts_ms=ts)
    answer = {
        "question_id": question["id"], "answer": result["answer"], "sources": result["sources"],
        "found": result["found"], "source": source, "by": BOT, "calls": calls,
    }
    store.append(episode_id, "question.answered", answer, ts_ms=ts)
    settle(request, episode_id, ts)
    return view(request, episode_id)


@ask_router.post("/ask/doctor")
def ask_doctor(episode_id: str, body: QuestionIn, request: Request) -> dict:
    asked, _, ts = _asked(request, episode_id, body, "doctor")
    return _write(request, episode_id, [("question.asked", asked)], ts)


@ask_router.post("/ask/hear")
def hear_answer(
    episode_id: str,
    request: Request,
    by: str = Form(..., min_length=1, max_length=80),
    file: UploadFile = File(...),
    at_ms: int | None = Form(None, ge=0),
) -> dict:
    """What was said, as text to check. Any role. Writes nothing."""
    _require(request, episode_id)
    heard = _heard(request.app.state.settings, file, None)
    return {"text": heard["text"], "heard_by": heard["source"]}


def _find(request: Request, episode_id: str, kind: str, found: str, missing: str) -> tuple[dict, list[dict]]:
    """The request event of this episode and whether it has an answer already. 404 if it is not here."""
    _require(request, episode_id)
    events = _store(request).events(episode_id)
    event = next((e for e in events if e["id"] == found and e["event_type"] == kind), None)
    if event is None:
        raise HTTPException(status_code=404, detail=missing)
    return event, events


@ask_router.post("/questions/{question_id}/answer")
def answer_question(episode_id: str, question_id: str, body: AnswerIn, request: Request) -> dict:
    question, events = _find(request, episode_id, "question.asked", question_id, "Question not found")
    if question["payload"]["to"] == "bot":
        raise HTTPException(status_code=409, detail=BOT_ANSWERS)
    if any(e["event_type"] == "question.answered" and e["payload"]["question_id"] == question_id for e in events):
        raise HTTPException(status_code=409, detail=ANSWERED)
    answer = {
        "question_id": question_id, "answer": body.text, "by": body.by, "via": body.via,
        "heard_by": body.heard_by, "sources": [], "found": True, "source": "doctor",
        "calls": live.spoken_calls(request.app.state.settings, body.via, body.heard_by),
    }
    return _write(request, episode_id, [("question.answered", answer)], _at(_store(request), episode_id, body.at_ms))


@ask_router.post("/ask/review")
def ask_review(
    episode_id: str,
    request: Request,
    file: UploadFile = File(...),
    note: str = Form("", max_length=300),
    at_ms: int | None = Form(None, ge=0),
) -> dict:
    episode = _require(request, episode_id)
    store, settings = _store(request), request.app.state.settings
    if states.current_state(store.events(episode_id)) not in PHOTO_STATES:
        raise HTTPException(status_code=409, detail=PHOTO_REFUSED)
    raw, kind = read_upload_photo(file)
    ts, by = _at(store, episode_id, at_ms), episode["label"]
    photo = write_photo(settings, store, episode_id, raw, kind, {"purpose": "healing", "by": by}, ts)
    return _write(request, episode_id, [("review.requested", {"photo_id": photo["id"], "note": note, "by": by})], ts)


@ask_router.post("/reviews/{review_id}/answer")
def answer_review(episode_id: str, review_id: str, body: DecisionIn, request: Request) -> dict:
    _, events = _find(request, episode_id, "review.requested", review_id, "Review not found")
    if any(e["event_type"] == "review.answered" and e["payload"]["review_id"] == review_id for e in events):
        raise HTTPException(status_code=409, detail=REVIEWED)
    decision = {"review_id": review_id, "decision": body.decision, "label": DECISIONS[body.decision], "note": body.note, "by": body.by}
    return _write(request, episode_id, [("review.answered", decision)], _at(_store(request), episode_id, body.at_ms))


@ask_router.post("/ask/medicines")
def ask_medicines(
    episode_id: str,
    request: Request,
    file: UploadFile = File(...),
    at_ms: int | None = Form(None, ge=0),
) -> dict:
    """The strips in a medicine photo, each matched to the prescription or signed dose orders. The photo is kept."""
    episode = _require(request, episode_id)
    store, settings = _store(request), request.app.state.settings
    events = store.events(episode_id)
    if states.current_state(events) not in PHOTO_STATES:
        raise HTTPException(status_code=409, detail=MEDICINES_REFUSED)
    ordered = [e for e in events if e["event_type"] == "rx.ordered"]
    orders = orders_list(events)
    doses = dose_rows(orders)
    if not ordered and not doses:
        raise HTTPException(status_code=409, detail=f"{NO_MEDICINES} {record_holds(orders)}")
    raw, kind = read_upload_photo(file)
    ts, by = _at(store, episode_id, at_ms), episode["label"]
    photo = write_photo(settings, store, episode_id, raw, kind, {"purpose": "medicines", "by": by}, ts)
    read = live.read_photo(settings, "strip", raw, file.filename or "", kind, live_ok=switches.is_live(settings, "medicines"))
    matched = match_medicines(strips_from(read["text"] or ""), ordered[-1]["payload"] if ordered else None, doses,
                             ward=states.current_state(events) in WARD_VIEW)
    kept = keep_photo_evidence(settings, episode_id, "medicines", photo["id"], read, read["regions"])
    return _write(request, episode_id, [("medicines.read", {"photo_id": photo["id"], **matched, "source": read["source"], "calls": read["calls"], **kept, "by": by})], ts)


@ask_router.post("/medicines/{read_id}/mark")
def mark_medicine(episode_id: str, read_id: str, body: MarkIn, request: Request) -> dict:
    """The doctor notes a medicine from home, or marks it to discuss. A record mark, not an order (R28, R33)."""
    if not body.by.startswith("Dr. "):
        raise HTTPException(status_code=403, detail=DOCTOR_ONLY)
    read, _ = _find(request, episode_id, "medicines.read", read_id, "Medicines photo not found")
    rows = read["payload"]["rows"]
    if body.row >= len(rows):
        raise HTTPException(status_code=422, detail="No such row in that photo.")
    marked = {
        "read_id": read_id, "row": body.row, "mark": body.mark, "name": rows[body.row].get("name") or rows[body.row]["read"],
        "read": rows[body.row]["read"], "by": body.by,
    }
    return _write(request, episode_id, [("brownbag.marked", marked)], _at(_store(request), episode_id, body.at_ms))


@ask_router.post("/checkins/{checkin_id}/seen")
def checkin_seen(episode_id: str, checkin_id: str, body: SeenCheckinIn, request: Request) -> dict:
    """A nurse saw a check-in. Once per nurse: a second call writes nothing."""
    _, events = _find(request, episode_id, "checkin.recorded", checkin_id, "Check-in not found")
    if any(e["event_type"] == "checkin.seen" and e["payload"]["checkin_id"] == checkin_id and e["payload"]["by"] == body.by for e in events):
        return view(request, episode_id)
    return _write(request, episode_id, [("checkin.seen", {"checkin_id": checkin_id, "by": body.by})], _at(_store(request), episode_id, body.at_ms))
