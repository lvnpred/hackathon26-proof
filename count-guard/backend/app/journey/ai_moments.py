"""AI moments: every AI or rules result in the care flow, built from the events already held (contract C1).

One pure function. Each builder reads one anchor event and its follow-ups. A finding is made of numbers and
record fields (`moment_text`), never of model text.
"""

from __future__ import annotations

from app.journey import moment_text as text
from app.journey import nudges
from app.journey.medicines import day_plan
from app.journey.stories import clock, count_of, plain
from app.morning.discharge import visible_events

MONITOR_KEYS = (("sbp", "SBP"), ("dbp", "DBP"), ("hr", "HR"))
FAILED_SOURCES = ("failed", "unreadable", "prepared (live call failed)", "rules (model reply not usable)")
VISUAL = {"tray.checked": "tray", "setup.checked": "setup", "swabs.counted": "swabs"}


def line_of(event: dict) -> dict:
    """C2: one recorded event as a citable line."""
    return {
        "id": event["id"], "type": event["event_type"], "when": clock(event["ts_ms"]),
        "by": (event.get("payload") or {}).get("by"), "plain": plain(event),
    }


def visual_finding(rows: list[dict]) -> str:
    """R5: the first sentence of `evidence.js` `explain()`, from the rows alone."""
    rows = rows or []
    seen_any = any((r.get("seen") or 0) > 0 for r in rows)
    if not seen_any:
        return text.NOTHING_SEEN
    short = next((r for r in rows if r.get("seen") is not None and r["seen"] < r["planned"]), None)
    if short:
        return f"Saw {short['seen']} of {short['planned']} {text.plural_of(short['concept'], short['planned'])}."
    seen = sum(r.get("seen") or 0 for r in rows)
    return f"Saw every planned item: {seen} of {sum(r['planned'] for r in rows)}."


class _Index:
    """The follow-up lookups, built once per call."""

    def __init__(self, events: list[dict]):
        self.events = events
        self.shown = visible_events(events)
        self.order = {e["id"]: i for i, e in enumerate(events)}
        self.by_id = {e["id"]: e for e in events}
        self.open_nudges = {e["id"] for e in nudges.open_nudges(events)}
        self.follow: dict[tuple[str, str], list[dict]] = {}
        for e in self.shown:
            p = e["payload"]
            for kind, key in (
                ("order.signed", "draft_id"), ("discharge.signed", "draft_id"), ("brownbag.marked", "read_id"),
                ("nudge.seen", "nudge_id"), ("handover.accepted", "handover_id"),
                ("question.answered", "question_id"), ("review.answered", "review_id"),
            ):
                if e["event_type"] == kind and p.get(key):
                    self.follow.setdefault((kind, p[key]), []).append(e)
        self.held: dict[str, list[dict]] = {}
        for e in self.shown:
            if e["payload"].get("evidence_id"):
                self.held.setdefault(e["payload"]["evidence_id"], []).append(e)
        groups: dict[str, list[dict]] = {}
        for e in self.shown:
            if e["event_type"] == "brownbag.med_found" and e["payload"].get("evidence_id"):
                groups.setdefault(e["payload"].get("photo_id") or e["payload"]["evidence_id"], []).append(e)
        self.strip_groups = groups

    def after(self, kind: str, anchor_id: str) -> list[dict]:
        return self.follow.get((kind, anchor_id), [])

    def line(self, event_id: str | None) -> dict | None:
        found = self.by_id.get(event_id) if event_id else None
        return line_of(found) if found else None


def _written(ix: _Index, anchor: dict, extra: list[dict]) -> list[dict]:
    rows = {anchor["id"]: anchor}
    for e in extra + ix.held.get(anchor["payload"].get("evidence_id"), []):
        rows.setdefault(e["id"], e)
    out = []
    for e in sorted(rows.values(), key=lambda e: ix.order[e["id"]]):
        p = e["payload"]
        out.append({
            "event_id": e["id"], "type": e["event_type"], "when": clock(e["ts_ms"]), "by": p.get("by"), "plain": plain(e),
            **{k: p[k] for k in ("read", "saved") if k in p},
        })
    return out


def _moment(ix: _Index, anchor: dict, cap: str, finding: str, status: str, refs: dict, *, patient_finding: str | None = None,
            extra: list[dict] | None = None, calls: list | None = None, source: str = "", owner: str | None = None,
            photo_id: str | None = None, moment_id: str | None = None, title: str | None = None) -> dict:
    p = anchor["payload"]
    return {
        "id": moment_id or anchor["id"], "kind": text.KIND[cap], "capability": cap, "title": title or text.TITLE[cap],
        "at_ms": anchor["ts_ms"], "calls": calls if calls is not None else (p.get("calls") or []), "source": source,
        "handmade": bool(p.get("handmade", False)), "finding": finding, "patient_finding": patient_finding,
        "status": status, "owner": owner if owner is not None else text.OWNER.get(cap), "filter": text.FILTER[cap],
        "evidence_id": p.get("evidence_id"), "photo_id": photo_id, "refs": refs, "written": _written(ix, anchor, extra or []),
    }


def _check_status(p: dict) -> str:
    if p.get("match") == "ok":
        return "matches"
    if p.get("match") == "mismatch":
        return "flagged"
    return "failed" if p.get("source") in FAILED_SOURCES else "recorded"


def _resolved(ix: _Index, e: dict) -> bool:
    """A flagged camera check stops needing anyone once the record answers it (I-1)."""
    later = [x for x in ix.shown if ix.order[x["id"]] > ix.order[e["id"]]]
    if e["event_type"] == "swabs.counted":  # a closing count saved equal to the pack opened
        return any(x["event_type"] == "count.closing" and (x["payload"].get("unaccounted") or 0) == 0 for x in later)
    if any(x["event_type"] == e["event_type"] and x["payload"].get("match") == "ok" for x in later):
        return True  # a later check of the same kind matched
    before = [x for x in ix.shown if ix.order[x["id"]] < ix.order[e["id"]] and x["event_type"] == "patient.state"]
    in_theatre = bool(before) and before[-1]["payload"].get("to") == "theatre"
    for x in later:  # the patient has left theatre
        if x["event_type"] == "patient.state":
            if x["payload"].get("to") == "theatre":
                in_theatre = True
            elif in_theatre:
                return True
    return False


def _visual(ix: _Index, e: dict) -> dict:
    p, cap = e["payload"], VISUAL[e["event_type"]]
    status = _check_status(p)
    resolved = status == "flagged" and _resolved(ix, e)
    if resolved:
        status = "recorded"
    check = {"check": cap, "rows": p.get("rows") or [], "missing": p.get("missing"), "match": p.get("match"),
             "why": p.get("why"), "media": p.get("media", "video"), "unchecked": p.get("unchecked") or []}
    frames = p.get("frame_ids") or []
    moment = _moment(ix, e, cap, visual_finding(check["rows"]), status,
                     {"check": check}, patient_finding=text.PATIENT_TEXT[cap], source=p.get("source", ""),
                     photo_id=frames[0] if frames else None)
    if resolved:
        moment["owner"] = None  # nobody is waiting on it any more
    return moment


def _monitor_finding(values: dict) -> str:
    parts = [f"{label} {values[key]}" for key, label in MONITOR_KEYS if key in values]
    return f"Read {', '.join(parts)}." if parts else "Photo kept, not checked."


def _proof(ix: _Index, e: dict) -> dict | None:
    p = e["payload"]
    if "values_read" in p:
        values = p.get("values_read") or {}
        status = _check_status(p) if values else "failed"
        refs = {"reader": "monitor", "regions": p.get("regions") or [], "values_read": values, "rows": None,
                "match": p.get("match"), "why": p.get("why")}
        return _moment(ix, e, "monitor", _monitor_finding(values), status, refs, patient_finding=text.PATIENT_TEXT["monitor"],
                       source=p.get("source", ""), photo_id=p.get("photo_id"))
    if p.get("source") == "none":  # a proof photo for a task with nothing to read: kept as a record row
        return _moment(ix, e, "photo", "Proof photo kept, not checked.", "recorded", {}, patient_finding="Proof photo kept, not checked.",
                       calls=[], photo_id=p.get("photo_id"), title="Proof photo")
    finding = {"ok": "Strip photo matches the task.", "mismatch": "Strip photo does not match the task."}.get(
        p.get("match"), "Photo kept, not checked.")
    refs = {"reader": "strip", "regions": p.get("regions") or [], "values_read": None, "rows": None,
            "match": p.get("match"), "why": p.get("why")}
    return _moment(ix, e, "dose_strip", finding, _check_status(p), refs, patient_finding=text.PATIENT_TEXT["dose_strip"],
                   source=p.get("source", ""), photo_id=p.get("photo_id"))


def _medicines(ix: _Index, e: dict) -> dict:
    p = e["payload"]
    rows = p.get("rows") or []
    flagged = [i for i, r in enumerate(rows) if r.get("flag")]
    on = sum(bool(r.get("prescribed")) for r in rows)
    marks = ix.after("brownbag.marked", e["id"])
    status = _check_status(p)
    if status == "flagged" and flagged and {m["payload"]["row"] for m in marks} >= set(flagged):
        status = "recorded"  # the doctor marked every flagged row
    refs = {"reader": "medicines", "regions": p.get("regions") or [], "values_read": None, "rows": rows,
            "match": p.get("match"), "why": p.get("why")}
    return _moment(ix, e, "medicines", text.medicines_text(len(rows), on, len(flagged)), status, refs,
                   patient_finding=f"{count_of(len(rows), 'medicine')} read from your photo.", extra=marks,
                   source=p.get("source", ""), photo_id=p.get("photo_id"))


def _strips(ix: _Index, e: dict) -> dict | None:
    p = e["payload"]
    group = ix.strip_groups.get(p.get("photo_id") or p.get("evidence_id")) or []
    if not group or group[0]["id"] != e["id"]:
        return None
    ids = {row["id"] for row in group}
    made = [n for n in nudges.strips_vs_rx(ix.shown) if n["fact_id"] in ids]
    differ = sum(n["kind"] == "strip_strength_differs" for n in made)
    unlisted = sum(n["kind"] == "strip_not_prescribed" for n in made)
    refs = {"reader": "strip", "regions": p.get("regions") or [], "values_read": None,
            "rows": [row["payload"] for row in group], "match": "mismatch" if made else "ok", "why": ""}
    return _moment(ix, e, "strips", text.strips_text(len(group), differ, unlisted), "flagged" if made else "matches", refs,
                   patient_finding=f"{count_of(len(group), 'strip')} read from your photo.", extra=group[1:],
                   source=p.get("source", ""), photo_id=p.get("photo_id"))


def _voice(ix: _Index, e: dict, cap: str, transcript: str, finding: str, status: str, *, items=None, sections=None,
           signed_items=None, extra=None, source: str = "", patient_finding: str | None = None) -> dict:
    p = e["payload"]
    refs = {"transcript": transcript, "heard_by": p.get("heard_by", ""), "spans": p.get("spans"), "items": items,
            "signed_items": signed_items, "sections": sections}
    return _moment(ix, e, cap, finding, status, refs, patient_finding=patient_finding, extra=extra or [],
                   source=source or p.get("heard_by", ""))


def _order_draft(ix: _Index, e: dict) -> dict:
    p = e["payload"]
    signed = ix.after("order.signed", e["id"])
    items = p.get("items") or []
    return _voice(ix, e, "orders", p.get("transcript", ""), text.order_text(len(items), text.words(p.get("transcript"))),
                  "recorded" if signed else "open", items=items, extra=signed, source=p.get("source", ""),
                  signed_items=signed[0]["payload"].get("items") if signed else None)


def _discharge_draft(ix: _Index, e: dict) -> dict:
    p = e["payload"]
    signed = ix.after("discharge.signed", e["id"])
    sections = p.get("sections") or []
    return _voice(ix, e, "discharge", p.get("transcript", ""),
                  text.discharge_text(len(sections), text.words(p.get("transcript"))),
                  "recorded" if signed else "open", sections=sections, extra=signed, source=p.get("source", ""))


def _task_done(ix: _Index, e: dict) -> dict | None:
    p = e["payload"]
    if p.get("via") != "voice":
        return None
    return _voice(ix, e, "task_voice", p.get("transcript", ""), text.task_voice_text(text.words(p.get("transcript"))), "recorded")


def _answered(ix: _Index, e: dict) -> dict | None:
    p = e["payload"]
    if p.get("source") == "doctor":
        if p.get("via") != "voice":
            return None
        return _voice(ix, e, "answer_voice", p.get("answer", ""), text.answer_voice_text(text.words(p.get("answer"))),
                      "recorded", patient_finding=text.PATIENT_TEXT["answer_voice"])
    sources = [{"id": s.get("id"), "text": s.get("text")} if isinstance(s, dict) else {"id": s, "text": ""}
               for s in p.get("sources") or []]
    asked = ix.by_id.get(p.get("question_id"))
    refs = {"question_id": p.get("question_id"), "question": (asked["payload"].get("text") if asked else None), "answer": p.get("answer"),
            "found": bool(p.get("found")), "sources": sources}
    return _moment(ix, e, "record_bot", text.bot_text(len(sources), bool(p.get("found"))), "recorded", refs,
                   patient_finding=text.bot_text(len(sources), bool(p.get("found")), patient=True),
                   source=p.get("source", ""))


def _nudge(ix: _Index, e: dict) -> dict:
    p = e["payload"]
    seen = ix.after("nudge.seen", e["id"])
    staff = p.get("says_staff") or p.get("says", "")
    refs = {"says": p.get("says", ""), "says_staff": staff, "to": p.get("to"), "kind": p.get("kind"),
            "intent": ix.line(p.get("intent_id")), "fact": ix.line(p.get("fact_id")),
            "rule": text.RULE_TEXT.get(p.get("kind"), "")}
    return _moment(ix, e, "nudge", staff, "open" if e["id"] in ix.open_nudges else "recorded", refs, calls=[], source="rules",
                   patient_finding=p.get("says") if p.get("to") == "patient" else None, extra=seen, owner=p.get("to"))


def _handover(ix: _Index, e: dict) -> dict:
    p = e["payload"]
    accepted = ix.after("handover.accepted", e["id"])
    lines = [{"text": row["text"], "evidence": [x for x in (ix.line(i) for i in row.get("evidence") or []) if x]}
             for row in p.get("lines") or []]
    cited = {i for row in p.get("lines") or [] for i in row.get("evidence") or []}
    refs = {"lines": lines, "text": p.get("text"), "wording": p.get("wording"), "from": p.get("from"), "to": p.get("to")}
    return _moment(ix, e, "handover", text.handover_text(len(lines), len(cited)), "recorded" if accepted else "open", refs,
                   extra=accepted, source=p.get("wording", ""))


def _card(ix: _Index, e: dict) -> dict:
    p = e["payload"]
    lines = [{"text": p[k], "evidence": []} for k in ("wound_care", "review", "help_line") if p.get(k)]
    return _moment(ix, e, "discharge_card",
                   text.card_text(len(p.get("warning_signs") or []), len(p.get("schedule") or [])), "recorded",
                   {"lines": lines}, patient_finding=text.PATIENT_TEXT["discharge_card"], calls=[], source="rules")


def _healing(ix: _Index, e: dict) -> dict:
    p = e["payload"]
    answered = ix.after("review.answered", e["id"])
    finding = f"Reviewed: {answered[0]['payload'].get('label')}." if answered else "Healing photo waiting for review."
    return _moment(ix, e, "healing_photo", finding, "recorded" if answered else "open", {}, patient_finding=finding,
                   calls=[], extra=answered, photo_id=p.get("photo_id"))


def _photo(ix: _Index, e: dict) -> dict | None:
    purpose = e["payload"].get("purpose")
    if purpose not in text.PHOTO_TITLE:
        return None
    finding = f"{text.PHOTO_TITLE[purpose]}."
    return _moment(ix, e, "photo", finding, "recorded", {}, patient_finding=finding, calls=[], photo_id=e["id"],
                   title=text.PHOTO_TITLE[purpose])


def _typed_orders(ix: _Index, e: dict) -> dict | None:
    if e["payload"].get("draft_id"):
        return None
    return _moment(ix, e, "typed_orders", f"{count_of(len(e['payload'].get('items') or []), 'order')} signed.", "recorded",
                   {}, calls=[])


BUILDERS = {
    "tray.checked": _visual, "setup.checked": _visual, "swabs.counted": _visual, "proof.checked": _proof,
    "medicines.read": _medicines, "brownbag.med_found": _strips, "order.drafted": _order_draft,
    "discharge.drafted": _discharge_draft, "task.done": _task_done, "question.answered": _answered,
    "nudge.raised": _nudge, "handover.drafted": _handover, "discharge.card": _card, "review.requested": _healing,
    "photo.added": _photo, "order.signed": _typed_orders,
}


def _day_plan(ix: _Index) -> dict | None:
    rx = next((e for e in reversed(ix.shown) if e["event_type"] == "rx.ordered"), None)
    read = next((e for e in reversed(ix.shown) if e["event_type"] == "medicines.read"), None)
    if rx is None or read is None:  # the plan is an AI moment once a medicines photo is matched to it
        return None
    plan = day_plan(rx["payload"], read["payload"])
    items = [i for group in (*plan["slots"].values(), plan["as_needed"], plan["as_written"]) for i in group]
    keys = {i["key"] for i in items}
    matched = {i["key"] for i in items if i["region"] is not None}
    k = len(rx["payload"].get("rows") or []) or len(keys)
    rows = [{k2: i[k2] for k2 in ("key", "medicine", "text", "region")} for i in items]
    shown = {**rx, "ts_ms": read["ts_ms"]}
    refs = {"lines": [{"text": f"{r['medicine']}: {r['text']}", "evidence": [line_of(rx)]} for r in rows], "rows": rows,
            "photo_id": plan["photo_id"], "evidence_id": plan["evidence_id"]}
    moment = _moment(ix, shown, "day_plan", text.day_plan_text(k, len(matched)), "recorded", refs,
                     patient_finding=f"Your day plan lists {count_of(k, 'medicine')}.", calls=[], source="rules",
                     extra=[read], photo_id=plan["photo_id"], moment_id=f"dayplan:{rx['id']}")
    moment["evidence_id"] = plan["evidence_id"]
    return moment


def moments(events: list[dict]) -> list[dict]:
    """C1: every AI moment of one episode, newest first (`at_ms` desc, ties by record order desc)."""
    ix = _Index(events)
    built = [(e, BUILDERS[e["event_type"]](ix, e)) for e in ix.shown if e["event_type"] in BUILDERS]
    rows = [(ix.order[e["id"]], m) for e, m in built if m]
    plan = _day_plan(ix)
    if plan:
        rows.append((max(ix.order[w["event_id"]] for w in plan["written"]), plan))
    rows.sort(key=lambda r: (r[1]["at_ms"], r[0]), reverse=True)
    return [m for _, m in rows]
