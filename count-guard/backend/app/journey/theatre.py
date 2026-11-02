"""Theatre panels, the record side (spec §6.4): drugs and packs heard, the simulated vitals strip, the context card.

The morning helpers do the work: `druglog.parse_drug_phrase`, `intents.parse_pack`, and `vitals.demo_readings`,
`evaluate`, `collect_facts`, `template_card`, `choose_wording`. This module only reads this theatre stay's events.

Hard stop (§6.5): a heard pack is `count.pack_heard`, a draft. Only a person's confirm writes `count.pack_opened`.
"""

from __future__ import annotations

from app.journey import states
from app.journey.placed import in_place
from app.morning.druglog import parse_drug_phrase
from app.morning.intents import parse_pack
from app.morning.vitals import Reading, collect_facts, demo_readings, evaluate, template_card

RESEARCH_BANNER = "Research demo — not for clinical use"
DRUG_HEARD, DRUG_GIVEN = "druglog.parsed", "drug.given"
PACK_HEARD, PACK_OPENED = "count.pack_heard", "count.pack_opened"
READING, CARD = "vitals.reading", "vitals.card"
SIMULATED = "simulated"
DOSE = ("strength", "amount", "unit", "route")
CARD_PROMPT = (
    "Reword this theatre context line in one or two plain sentences. Keep every number and name. "
    "Add no advice, no new numbers and no new drug names:\n"
)


def placed_stay(events: list[dict]) -> list[dict]:
    """This stay's visible events, a corrected drug line standing where its original stood (journey/placed.py)."""
    return states.stay_events(in_place(events))


def heard(text: str) -> tuple[str, dict]:
    """The morning "hear" intent: a pack line ("opening twenty swabs") or a drug line. Returns (event type, payload)."""
    pack = parse_pack(text)
    if pack:
        return PACK_HEARD, {"n": pack["quantity"], "item_type": pack["item_type"], "text": pack["text"]}
    return DRUG_HEARD, parse_drug_phrase(text)


def draft(stay: list[dict], kind: str, draft_id: str) -> dict | None:
    return next((e for e in stay if e["id"] == draft_id and e["event_type"] == kind), None)


def confirmed(stay: list[dict], kind: str, draft_id: str) -> dict | None:
    """The confirm event that names this draft, if any."""
    return next((e for e in stay if e["event_type"] == kind and e["payload"].get("draft_id") == draft_id), None)


def readings(stay: list[dict]) -> list[dict]:
    return [e for e in stay if e["event_type"] == READING]


def next_reading(stay: list[dict]) -> dict | None:
    """The next simulated reading of the demo strip (120 → 86 over 4 min), or None when the strip has ended."""
    rows = demo_readings()
    done = len(readings(stay))
    if done >= len(rows):
        return None
    row = rows[done]
    return {"systolic": row.systolic, "diastolic": row.diastolic, "hr": row.hr, "t_ms": row.ts_ms,
            "step": done + 1, "of": len(rows), "source": SIMULATED}


def drop(stay: list[dict]) -> dict | None:
    """The BP-drop rule on this stay's strip, evaluated on the scenario's own minutes, or None."""
    rows = [Reading(e["payload"]["t_ms"], e["payload"]["systolic"], e["payload"]["diastolic"], e["payload"]["hr"])
            for e in readings(stay)]
    return next((fire for fire in evaluate(rows) if fire["rule_id"] == "bp_drop_pct"), None)


def facts(events: list[dict], stay: list[dict], now_ms: int) -> list[str]:
    """The card's sources: drugs given (voice log), medicines from home, and the swab count.

    `collect_facts` words them. A drug given counts within its 10 minutes; a medicine from home stands for the whole
    stay, so it is read as of now. The swab count is this stay's opened packs (people's confirmed packs only)."""
    drugs = [{**e, "event_type": "druglog.given"} for e in stay if e["event_type"] == DRUG_GIVEN]
    home = [{**e, "ts_ms": now_ms} for e in states.visible_events(events) if e["event_type"] == "brownbag.med_found"]
    out = collect_facts(drugs + home, now_ms)
    opened = states.stay_opened(events)
    if opened:
        out.append(f"{opened} swabs opened (swab count)")
    return out


def card_payload(events: list[dict], now_ms: int, reword) -> dict | None:
    """The context card for this stay's BP drop, or None. `reword(template) -> (text, wording, source, calls)`."""
    stay = placed_stay(events)
    fire = drop(stay)
    if fire is None or any(e["event_type"] == CARD for e in stay):
        return None
    found = facts(events, stay, now_ms)
    template = template_card(fire, found)
    text, wording, source, calls = reword(template)
    return {"text": text, "template": template, "wording": wording, "source": source, "calls": calls,
            "facts": found, "rule_id": fire["rule_id"]}


def panel(events: list[dict], tier: bool) -> dict:
    """What the three theatre panels show for this stay."""
    stay = placed_stay(events)
    drugs = []
    for e in stay:
        if e["event_type"] != DRUG_HEARD:
            continue
        given = confirmed(stay, DRUG_GIVEN, e["id"])
        dose = {k: given["payload"].get(k) for k in DOSE} if given else {}  # a corrected drug given shows its dose
        drugs.append({**e["payload"], **dose, "id": e["id"], "at_ms": e["ts_ms"],
                      "given": {"by": given["payload"]["by"], "at_ms": given["ts_ms"], "id": given["id"]} if given else None})
    packs = []
    for e in stay:
        if e["event_type"] != PACK_HEARD:
            continue
        opened = confirmed(stay, PACK_OPENED, e["id"])
        packs.append({**e["payload"], "id": e["id"], "at_ms": e["ts_ms"],
                      "confirmed_by": opened["payload"]["by"] if opened else None})
    shown = [{**e["payload"], "id": e["id"], "at_ms": e["ts_ms"]} for e in readings(stay)]
    return {"banner": RESEARCH_BANNER, "tier": tier, "drugs": drugs, "packs": packs, "readings": shown,
            "strip_done": next_reading(stay) is None, "strip_total": len(demo_readings())}
