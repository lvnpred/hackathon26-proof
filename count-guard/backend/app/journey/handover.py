"""Shift handover drafted from the timeline. Muse Spark 1.3 may reword it; it may not add to it.

The template is built from recorded events only. A model rewording is kept only
when it passes the wording check: no advice words, no number and no drug name
that the template does not already contain. Otherwise the template is used.
"""

from __future__ import annotations

import time

import httpx

from app.adapters.spark import SparkAdapter
from app.agent.verifier import ADVICE
from app.journey import switches
from app.journey.evidence_payload import evidence_of
from app.journey.live import call_of
from app.journey.nudges import HOUR_MS, hours, open_nudges
from app.journey.clocktext import when_text
from app.morning.discharge import visible_events
from app.morning.vitals import wording_ok

NO_KEY = "no Meta Model API key"

PROMPT = (
    "You help a ward nurse hand over a shift. Regroup the numbered facts below for the incoming nurse "
    "under these headings, in this order, leaving out a heading with no facts: Patient, Doses given, "
    "Due by the orders, Observations, Nudges answered, Still open. Put each heading on its own line "
    "followed by a colon, then one or two short plain sentences. Keep every number, time and name exactly "
    "as written. Do not add any fact, number, medicine, opinion or instruction. Do not say what to give "
    "or do. Reply with the grouped text only.\n\n"
)


def _line(text: str, *ids: str | None) -> dict:
    return {"text": text, "evidence": [i for i in ids if i]}


def template_lines(events: list[dict], *, since_ms: int, at_ms: int, patient: str) -> list[dict]:
    """One line per recorded fact the incoming nurse needs, each with the events it came from."""
    shown = [e for e in visible_events(events) if e["ts_ms"] <= at_ms]
    lines: list[dict] = []

    def latest(kind):
        rows = [e for e in shown if e["event_type"] == kind]
        return rows[-1] if rows else None

    rx = latest("rx.ordered")
    if rx and rx["payload"].get("diagnosis"):
        lines.append(_line(f"{patient}: {'; '.join(rx['payload']['diagnosis'])}.", rx["id"]))
    closing = latest("count.closing")
    if closing:
        p = closing["payload"]
        lines.append(_line(f"Theatre count: {p.get('returned')} of {p.get('opened')} back, {p.get('unaccounted')} unaccounted.", closing["id"]))

    orders = latest("ward.orders_set")
    given = [e for e in shown if e["event_type"] == "dose.given" and since_ms <= e["ts_ms"]]
    for dose in given:
        p = dose["payload"]
        lines.append(_line(f"{when_text(dose['ts_ms'], at_ms)}: {p['name']} {p.get('amount') or ''} logged by {p['by']}.".replace("  ", " "), dose["id"]))
    if orders and latest("discharge.card") is None:  # ward order times end at discharge
        all_given = [e for e in shown if e["event_type"] == "dose.given"]
        for order in orders["payload"]["doses"]:
            mine = [d for d in all_given if d["payload"]["key"] == order["key"]]
            if mine:
                due = mine[-1]["ts_ms"] + int(order["every_h"] * HOUR_MS)
                lines.append(_line(
                    f"{order['name']} is ordered every {hours(order['every_h'])}; by that order the next is due {when_text(due, at_ms)}.",
                    orders["id"], mine[-1]["id"],
                ))

    readings = [e for e in shown if e["event_type"] == "obs.recorded"]
    if readings:
        last = readings[-1]
        p = last["payload"]
        lines.append(_line(
            f"Last observations {when_text(last['ts_ms'], at_ms)}: BP {p['sbp']}/{p['dbp']}, HR {p['hr']}, SpO2 {p.get('spo2')}, T {p.get('temp')}.",
            last["id"],
        ))

    answered = {e["payload"]["nudge_id"]: e for e in shown if e["event_type"] == "nudge.seen"}
    for nudge in (e for e in shown if e["event_type"] == "nudge.raised" and since_ms <= e["ts_ms"]):
        reply = answered.get(nudge["id"])
        if reply:
            note = (reply["payload"].get("note") or "seen").rstrip(".")
            lines.append(_line(f"Nudge {when_text(nudge['ts_ms'], at_ms)}: {nudge['payload']['says']} Answer: {note}.", nudge["id"], reply["id"]))
    for nudge in open_nudges(shown):
        if nudge["payload"]["to"] == "nurse":
            lines.append(_line(f"Still open: {nudge['payload']['says']}", nudge["id"]))
    if not lines:
        lines.append(_line("Nothing was recorded for this patient in this shift."))
    return lines


def reword(lines: list[dict], settings, write=None, prompt: str = PROMPT) -> tuple[str | None, str]:
    """Ask Muse Spark 1.3 (Meta Model API key) for one paragraph. Returns (text or None, why not used).

    No tools are needed here, so the handover runs on the same key as strips and the second look.
    """
    if write is None:
        if not switches.is_live(settings, "spark"):
            return None, NO_KEY
        write = SparkAdapter(settings).write
    facts = "\n".join(f"{n}. {line['text']}" for n, line in enumerate(lines, 1))
    try:
        text = (write(prompt + facts) or "").strip()
    except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as exc:
        return None, f"model call failed ({type(exc).__name__})"
    return text or None, "" if text else "empty reply"


def checked(text: str | None, lines: list[dict]) -> tuple[bool, str]:
    if not text:
        return False, "no text"
    source = " ".join(line["text"] for line in lines)
    if ADVICE.search(text):
        return False, "advice wording"
    if not wording_ok(text, source):
        return False, "added a number, a medicine or an instruction"
    return True, ""


def wording_evidence(kind: str, lines: list[dict], prompt: str, reply: str | None, ok: bool, problem: str, calls: list[dict],
                     used: dict) -> dict:
    """The evidence of a reworded draft (§4.2): the facts sent, Spark's raw reply, and whether the template stood in."""
    facts = [line["text"] for line in lines]
    inputs = {"facts": facts, "text": prompt + "\n".join(f"{n}. {f}" for n, f in enumerate(facts, 1))}
    used = {**used, "fallback": None if ok else "template", "why": "" if ok else problem}
    return evidence_of(kind, inputs=inputs, reply=reply, used=used, calls=calls)


def draft(events, *, patient, since_ms, at_ms, from_nurse, to_nurse, settings, use_model=True, write=None) -> dict:
    lines = template_lines(events, since_ms=since_ms, at_ms=at_ms, patient=patient)
    text, why = (None, "model not asked")
    calls: list[dict] = []
    if use_model:
        start = time.monotonic()
        text, why = reword(lines, settings, write)
        ms = round((time.monotonic() - start) * 1000)
    ok, problem = checked(text, lines) if text else (False, why)
    if use_model and why != NO_KEY:  # no key: the adapter was never reached, so no call (R5)
        calls = [call_of("spark", settings, "muse-spark-1.3" if ok else "failed", ms)]
    return {
        "from": from_nurse,
        "to": to_nurse,
        "since": when_text(since_ms, at_ms),
        "until": when_text(at_ms, at_ms),
        "lines": lines,
        "text": text if ok else None,
        "wording": "muse-spark-1.3" if ok else "template",
        "model_note": "" if ok else problem,
        "by": from_nurse,
        "calls": calls,
        "evidence": wording_evidence("handover", lines, PROMPT, text, ok, problem, calls,
                                     {"text": text if ok else None, "lines": len(lines)}),
    }
