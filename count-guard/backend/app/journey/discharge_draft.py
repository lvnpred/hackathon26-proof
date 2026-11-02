"""The discharge drafted from the timeline (spec §6.8): the DD prescription, drugs given, the count, key moves.

`build` reads recorded events only. The summary is template lines from that build; with SPARK_LIVE on, Muse
Spark 1.3 may regroup them and the rewording is kept only when it passes the wording check (handover.checked).
Otherwise the template stands, labelled prepared (§6.7). Nothing here writes; the route does.
"""

from __future__ import annotations

import time
from datetime import date, datetime, time as clock_time, timedelta, timezone

from app.journey import handover, switches
from app.journey.clocktext import DAY0, when_text
from app.journey.live import call_of
from app.journey.placed import in_place
from app.journey.states import PROCEDURES, stay_events
from app.journey.stories import by_ai
from app.morning.discharge import fold, visible_events

SPARK = "muse-spark-1.3"
PREPARED = "prepared"
FOLLOW_UP_DAYS = 7  # morning.ics.follow_up_ics adds the same seven days
_DAY_MS = 24 * 3_600_000
KEY_MOVES = {"admitting": "Admitted", "ward": "On the ward", "theatre": "To theatre", "discharging": "Discharge signed",
             "home": "Home"}

PROMPT = (
    "You help a doctor write a discharge summary. Regroup the numbered facts below into short plain sentences "
    "under these headings, in this order, leaving out a heading with no facts: Diagnosis, Procedure, In theatre, "
    "Medicines, Follow-up. Keep every number, date and name exactly as written. Do not add any fact, number, "
    "medicine, opinion or instruction. Do not say what to give or do. Reply with the text only.\n\n"
)


def _drug(e: dict) -> dict:
    p = e["payload"]
    return {"name": p.get("generic") or p.get("name_as_heard") or "", "strength": p.get("strength") or "",
            "amount": p.get("amount"), "unit": p.get("unit") or "", "route": p.get("route") or "",
            "by": p.get("by"), "at_ms": e["ts_ms"], "when": when_text(e["ts_ms"], None), "id": e["id"]}


def _drug_text(d: dict) -> str:
    return " ".join(str(part) for part in (d["name"], d["strength"], d["amount"], d["unit"], d["route"]) if part not in ("", None))


def _theatre_stay(events: list[dict]) -> list[dict]:
    """The visible events of the latest theatre stay (states.stay_events on the record up to leaving theatre)."""
    moves = [i for i, e in enumerate(events) if e["event_type"] == "patient.state"]
    into = [i for i in moves if events[i]["payload"].get("to") == "theatre"]
    if not into:
        return []
    end = next((i for i in moves if i > into[-1]), len(events))
    return stay_events(events[:end])


def _count(events: list[dict]) -> dict | None:
    """The latest closing a person saved in the theatre stay after surgery began: count_gate's rule (§6.5).
    A closing the AI or the camera wrote, or one taken before incision, is never the count."""
    stay = _theatre_stay(events)
    began = [i for i, e in enumerate(stay) if e["event_type"] == "surgery.began"]
    people = [e for i, e in enumerate(stay) if e["event_type"] == "count.closing" and began and i > began[-1]
              and str(e["payload"].get("by") or "").strip() and not by_ai(e["payload"])]
    if not people:
        return None
    e = people[-1]
    p = e["payload"]
    text = f"opened {p.get('opened')} / returned {p.get('returned')}, {p.get('unaccounted')} unaccounted"
    if (p.get("detail") or "").strip():
        text += f" ({p['detail'].strip()})"
    return {"opened": p.get("opened"), "returned": p.get("returned"), "unaccounted": p.get("unaccounted"),
            "detail": p.get("detail") or "", "by": p.get("by"), "at_ms": e["ts_ms"], "text": text, "id": e["id"]}


def _move(e: dict) -> dict:
    p = e["payload"]
    text = KEY_MOVES.get(p.get("to"), str(p.get("to")))
    if p.get("to") == "theatre" and p.get("procedure") in PROCEDURES:
        text += f": {PROCEDURES[p['procedure']]}"
    return {"to": p.get("to"), "by": p.get("by"), "at_ms": e["ts_ms"], "when": when_text(e["ts_ms"], None), "text": text}


def follow_up_date(at_ms: int):
    return DAY0 + timedelta(days=max(0, int(at_ms)) // _DAY_MS + FOLLOW_UP_DAYS)


def ics_start(follow_up: dict) -> datetime:
    """The `start` for morning.ics.follow_up_ics, which moves it seven days on to the follow-up date at 10:00."""
    due = date.fromisoformat(follow_up["date"]) - timedelta(days=FOLLOW_UP_DAYS)
    return datetime.combine(due, clock_time(10, 0), tzinfo=timezone.utc)


def follow_up_of(source: dict) -> dict:
    """The follow-up of a drafted or signed event: the draft's own, else seven days from that event's day.
    One base for the draft card, the PDF and the .ics, so a later event never moves the date."""
    kept = (source["payload"].get("timeline") or {}).get("follow_up")
    if kept:
        return kept
    due = follow_up_date(source["ts_ms"])
    return {"date": due.isoformat(), "when": f"{due:%a} {due.day} {due:%b}", "text": "Follow-up visit", "days": FOLLOW_UP_DAYS}


def build(events: list[dict]) -> dict:
    """The draft from the record: prescription, drugs_given, count, events (key moves) and follow_up."""
    shown = visible_events(events)
    rxs = [e for e in shown if e["event_type"] == "rx.ordered"]
    rx = rxs[-1]["payload"] if rxs else None
    prescription = None if rx is None else {
        "patient": rx.get("patient") or "", "diagnosis": list(rx.get("diagnosis") or []), "by": rx.get("by"),
        "source": rx.get("source"), "review": rx.get("review") or "",
        "rows": [{k: row.get(k, "") for k in ("name", "strength", "dose", "instructions")} for row in rx.get("rows") or []],
    }
    at_ms = max((e["ts_ms"] for e in shown), default=0)
    due = follow_up_date(at_ms)
    return {
        "prescription": prescription,
        "drugs_given": [_drug(e) for e in in_place(events) if e["event_type"] == "drug.given"],  # corrections in place
        "count": _count(events),
        "events": [_move(e) for e in shown if e["event_type"] == "patient.state"],
        "follow_up": {"date": due.isoformat(), "when": f"{due:%a} {due.day} {due:%b}",
                      "text": (rx or {}).get("review") or "Follow-up visit", "days": FOLLOW_UP_DAYS},
    }


def lines(draft: dict, patient: str) -> list[dict]:
    """The template summary: one line per fact in the draft, in the order a discharge summary reads."""
    out: list[str] = []
    rx = draft["prescription"]
    if rx and rx["diagnosis"]:
        out.append(f"{rx['patient'] or patient}: {'; '.join(rx['diagnosis'])}.")
    for move in draft["events"]:
        if move["to"] == "theatre":
            out.append(f"Procedure: {move['text'].removeprefix('To theatre: ')}, {move['when']}.")
    if draft["drugs_given"]:
        out.append("Given in theatre: " + "; ".join(f"{_drug_text(d)} by {d['by']}" for d in draft["drugs_given"]) + ".")
    if draft["count"]:
        out.append(f"Swab count: {draft['count']['text']}, saved by {draft['count']['by']}.")
    if rx and rx["rows"]:
        rows = [" ".join(p for p in (r["name"], r["strength"], r["dose"], r["instructions"].lower()) if p) for r in rx["rows"]]
        out.append("Medicines on the prescription: " + "; ".join(rows) + ".")
    follow = draft["follow_up"]
    out.append(f"Follow-up: {follow['text'].rstrip('.')}, {follow['when']}.")
    return [{"text": text} for text in out]


def wording(draft: dict, patient: str, settings, write=None) -> dict:
    """The summary text: Spark's regrouping when live and it passes the wording check, else the template."""
    template = lines(draft, patient)
    plain = "\n".join(line["text"] for line in template)
    if not switches.is_live(settings, "spark"):
        return {"summary": plain, "lines": template, "wording": "template", "source": PREPARED, "model_note": "", "calls": []}
    start = time.monotonic()
    text, why = handover.reword(template, settings, write, prompt=PROMPT)
    ms = round((time.monotonic() - start) * 1000)
    ok, problem = handover.checked(text, template) if text else (False, why)
    call = [call_of("spark", settings, SPARK if ok else "failed", ms)]
    if ok:
        return {"summary": text, "lines": template, "wording": SPARK, "source": SPARK, "model_note": "", "calls": call}
    return {"summary": plain, "lines": template, "wording": "template", "source": PREPARED, "model_note": problem, "calls": call}


def sheet(events: list[dict], summary: str, source: dict) -> dict:
    """The morning.pdf.write_discharge sheet for a care stay: drugs given and the person's count from the record,
    the follow-up of the drafted or signed `source` event."""
    draft = build(events)
    return {**fold(events), **draft, "drugs": [{**d, "generic": d["name"]} for d in draft["drugs_given"]],
            "count": draft["count"], "summary": summary, "follow_up": follow_up_of(source)}


def summary_of(events: list[dict]) -> tuple[str, dict | None]:
    """The summary the PDF prints: the latest signed one, else the latest draft's summary with its dictated sections
    under it (as the summary box shows it). (text, that event)."""
    for kind in ("discharge.signed", "discharge.drafted"):
        rows = [e for e in events if e["event_type"] == kind]
        if rows:
            p = rows[-1]["payload"]
            dictated = "\n".join(f"{s.get('heading')}: {s.get('text', '')}" for s in p.get("sections") or [])
            return "\n\n".join(part for part in (p.get("summary") or "", dictated) if part), rows[-1]
    return "", None


def stale(events: list[dict], draft_id: str | None) -> bool:
    """True when a newer discharge draft than `draft_id` exists: sign uses the latest."""
    drafts = [e["id"] for e in events if e["event_type"] == "discharge.drafted"]
    return bool(draft_id and drafts and draft_id in drafts and drafts[-1] != draft_id)
