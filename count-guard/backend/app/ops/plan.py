"""The planner: rules that decide who and what, with template text. Pure; the gate writes the events."""

from __future__ import annotations

import re

from app.agent import verifier
from app.journey import doctor_status, handover, states, tasks
from app.journey.ask import short_name
from app.morning.discharge import visible_events
from app.ops import watch
from app.ops.items import Action, WorkItem, assignees, routes
from app.ops.policy import DOCTORS, NURSES

TEMPLATES = {
    "ack_order": "Acknowledged {doctor}'s orders",
    "assign_task": "Assigned {n} {noun} to {names}",
    "nudge_obs_overdue": "Nudged {nurse}: {says}",
    "route_question": "Sent the patient's question to {doctor}",
    "file_monitor": "Filed the monitor read {sbp}/{dbp}, pulse {hr}",
    "file_swabs": "Filed the camera count: {n} of {opened} swabs back",
    "draft_answer": "Draft answer to {patient}'s question",
    "propose_move": "Back to ward: {patient}",
    "draft": "Your discharge card lists these warning signs: {signs}. {care}",
}
OPS_PROMPT = ("Reword these record lines as one short plain sentence for a doctor to approve. "
              "Add no number, medicine or instruction that is not in the lines.\n\n")
_OPEN = ("open", "running")
_OBS_FIELDS = tasks.OBS_FIELDS


def _find(events: list[dict], event_id: str, kind: str) -> dict | None:
    return next((e for e in visible_events(events) if e["id"] == event_id and e["event_type"] == kind), None)


def _latest(events: list[dict], kind: str) -> dict | None:
    rows = [e for e in visible_events(events) if e["event_type"] == kind]
    return rows[-1] if rows else None


def _answered(events: list[dict], question_id: str) -> bool:
    return any(e["payload"].get("question_id") == question_id
               for e in visible_events(events) if e["event_type"] == "question.answered")


def pick_nurses(events: list[dict], task_ids: list[str]) -> dict[str, str]:
    """Greedy by load (R3): the nurse with the fewest open assigned tasks in this episode; a tie goes to roster order."""
    given = assignees(events)
    live = {t["id"] for t in tasks.task_list(events) if t["status"] in _OPEN}
    load = {nurse: 0 for nurse in NURSES}
    for task_id in live:
        if given.get(task_id) in load:
            load[given[task_id]] += 1
    out: dict[str, str] = {}
    for task_id in task_ids:
        nurse = min(NURSES, key=lambda n: (load[n], NURSES.index(n)))
        out[task_id] = nurse
        load[nurse] += 1
    return out


def pick_doctor(events: list[dict], board: list[dict], at_ms: int) -> str:
    """The first doctor who is available (R17), else the named one."""
    for doctor in DOCTORS:
        if doctor_status.current(doctor, [events], list(board), at_ms)["status"] == "available":
            return doctor
    return DOCTORS[0]


def cited_card(events: list[dict]) -> list[dict]:
    """One row per warning sign and one for wound care, each with an id the card event can be checked by."""
    card = _latest(events, "discharge.card")
    if not card:
        return []
    p = card["payload"]
    rows = [{"id": f"{card['id']}:w{i}", "text": sign} for i, sign in enumerate(p.get("warning_signs") or [])]
    if p.get("wound_care"):
        rows.append({"id": f"{card['id']}:care", "text": p["wound_care"]})
    return rows


def _patient(events: list[dict]) -> str:
    """The patient's short name from the record. Only the patient's own question carries it."""
    asked = _latest(events, "question.asked")
    return short_name(asked["payload"].get("by")) if asked else "the patient"


def _worded(template: str, cited: list[dict], settings, write) -> tuple[str, str]:
    """(text, model): the model's reword when every check passes, else the template. Never raises."""
    if not cited or (write is None and (settings is None or not settings.spark_configured)):
        return template, "rules"
    text, _why = handover.reword(cited, settings, write, prompt=OPS_PROMPT)
    ok, _problem = handover.checked(text, cited)
    if not ok:
        return template, "rules"
    figures = {f"n{i}": int(n) for i, n in enumerate(re.findall(r"\b\d+\b", " ".join(r["text"] for r in cited)))}
    if verifier.check_sentence(text, evidence_ids=[], known_ids=set(), figures=figures, claims={}):
        return template, "rules"
    return text, "spark"


def _ack_order(item, events, board, at_ms, patient=""):
    order = next((o for o in tasks.orders_list(events) if o["id"] == item.inputs[0]), None)
    if order is None or order["acknowledged_by"]:
        return None
    return Action("ack_order", {"order_id": order["id"]},
                  TEMPLATES["ack_order"].format(doctor=short_name(order["by"])))


def _assign_task(item, events, board, at_ms, patient=""):
    given = assignees(events)
    live = {t["id"] for t in tasks.task_list(events) if t["status"] in _OPEN}
    ids = [i for i in item.inputs if i in live and i not in given]
    if not ids:
        return None
    picks = pick_nurses(events, ids)
    names = list(dict.fromkeys(short_name(n) for n in picks.values()))
    summary = TEMPLATES["assign_task"].format(n=len(ids), noun="task" if len(ids) == 1 else "tasks",
                                              names=", ".join(names))
    return Action("assign_task", {"pairs": [[t, n] for t, n in picks.items()]}, summary)


def _nudge(item, events, board, at_ms, patient=""):
    nudge = _find(events, item.inputs[0], "nudge.raised")
    if nudge is None:
        return None
    kind = "dose" if nudge["payload"].get("kind") == "dose_overdue" else "obs"
    given = assignees(events)
    nurse = next((given[t["id"]] for t in tasks.task_list(events)
                  if t["kind"] == kind and t["status"] in _OPEN and t["id"] in given), NURSES[0])
    says = nudge["payload"].get("says_staff") or nudge["payload"].get("says", "")
    return Action("nudge_obs_overdue", {"nudge_id": nudge["id"], "nurse": nurse},
                  TEMPLATES["nudge_obs_overdue"].format(nurse=short_name(nurse), says=says))


def _route(item, events, board, at_ms, patient=""):
    question_id = item.inputs[0]
    if _find(events, question_id, "question.asked") is None or _answered(events, question_id) \
            or question_id in routes(events):
        return None
    doctor = pick_doctor(events, board, at_ms)
    return Action("route_question", {"question_id": question_id, "to": doctor},
                  TEMPLATES["route_question"].format(doctor=short_name(doctor)))


def _file_read(item, events, board, at_ms, patient=""):
    read = next((e for e in watch.monitor_reads(events) if e["id"] == item.inputs[0]), None)
    if read is not None:
        p = read["payload"]
        values = {k: p["values_read"][k] for k in _OBS_FIELDS if p["values_read"].get(k) is not None}
        return Action("file_read", {"source": "monitor", "task_id": p["task_id"], "photo_id": p["photo_id"],
                                    "values": values},
                      TEMPLATES["file_monitor"].format(sbp=values["sbp"], dbp=values["dbp"], hr=values["hr"]))
    camera = _find(events, item.inputs[0], "swabs.counted")
    if camera is None or states.current_state(events) != "theatre":
        return None
    stay = states.stay_events(events)
    closing = states.stay_latest(events, "count.closing")
    pack = states.stay_latest(events, "count.pack_opened")
    p = camera["payload"]
    if (pack is None or camera["id"] != (states.stay_latest(events, "swabs.counted") or {}).get("id")
            or (closing and stay.index(closing) > stay.index(camera))
            or p.get("count") is None or not p.get("evidence_id")):
        return None
    opened = p.get("opened")
    if opened is None:
        opened = pack["payload"]["quantity"]
    return Action("file_read", {"source": "swabs", "count": p["count"], "evidence_id": p["evidence_id"]},
                  TEMPLATES["file_swabs"].format(n=p["count"], opened=opened))


def _draft_answer(item, events, board, at_ms, patient="", settings=None, write=None):
    question = _find(events, item.inputs[0], "question.asked")
    rows = cited_card(events)
    card_signs = (_latest(events, "discharge.card") or {"payload": {}})["payload"].get("warning_signs")
    if question is None or _answered(events, question["id"]) or not rows or not card_signs:
        return None
    card = _latest(events, "discharge.card")["payload"]
    draft = TEMPLATES["draft"].format(signs="; ".join(card.get("warning_signs") or []),
                                      care=card.get("wound_care", "")).strip()
    sentence = TEMPLATES["draft_answer"].format(patient=short_name(question["payload"].get("by")))
    draft, model = _worded(draft, rows, settings, write)
    return Action("draft_answer", {"question_id": question["id"]}, sentence, sentence=sentence,
                  draft=draft, cited=tuple(rows), model=model)


def _propose_move(item, events, board, at_ms, patient=""):
    if not watch.move_ready(events, at_ms, set()):
        return None
    sentence = TEMPLATES["propose_move"].format(patient=patient or _patient(events))
    return Action("propose_move", {"to": "ward"}, sentence, sentence=sentence)


_PLANNERS = {
    "ack_order": _ack_order, "assign_task": _assign_task, "nudge_obs_overdue": _nudge,
    "route_question": _route, "file_read": _file_read, "draft_answer": _draft_answer,
    "propose_move": _propose_move,
}


def plan(item: WorkItem, events: list[dict], *, board=(), at_ms: int = 0, settings=None, write=None,
         patient: str = "") -> Action | None:
    """The action for a work item, or None when the work is no longer needed.

    `settings` and `write` are for the reword. `patient` is the episode's short name for the move sentence."""
    planner = _PLANNERS[item.kind]
    if planner is _draft_answer:  # only the L1 draft is reworded; propose_move has no cited rows, so it stays a template
        return planner(item, events, board, at_ms, patient, settings, write)
    return planner(item, events, board, at_ms, patient)
