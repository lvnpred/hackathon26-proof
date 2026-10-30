import re

from app.journey.stories import count_of, patient_line, plain, timeline_items

def ev(kind, eid="e1", ts=0, /, **p):
    return {"id": eid, "event_type": kind, "ts_ms": ts, "payload": p}

def test_obs_line_leaves_out_missing_values():
    assert plain(ev("obs.recorded", by="N", sbp=82, dbp=54, hr=112, spo2=None, temp=None)) == "N logged BP 82/54, HR 112."
    assert plain(ev("obs.recorded", by="N", sbp=112, dbp=70, hr=84, spo2=None, temp=36.9)) == "N logged BP 112/70, HR 84, T 36.9."

def test_order_counts_are_singular_and_plural():
    assert count_of(1, "order") == "1 order" and count_of(2, "order") == "2 orders"
    assert plain(ev("order.signed", by="D", items=[{}])) == "D signed 1 order."
    assert plain(ev("order.drafted", by="D", items=[{}])) == "D dictated 1 order (draft, not signed)."

TASKS = {"t1": {"title": "Paracetamol 1 g every 6 h", "name": "Paracetamol", "kind": "dose"},
         "t2": {"title": "BP and pulse every 1 h", "name": "", "kind": "obs"},
         "t3": {"title": "Saline 1 litre over 2 hours", "name": "", "kind": "procedure"}}

def test_patient_nudge_and_discharge_wording():
    to_patient = ev("nudge.raised", to="patient", says="This strip reads amlodipine 10 mg.")
    assert patient_line(to_patient, {}) == "A note for you: This strip reads amlodipine 10 mg."
    to_nurse = ev("nudge.raised", to="nurse", says="BP 82/54 is past the limit.")
    line = patient_line(to_nurse, {})
    assert line == "" and "Nudge" not in line and "nurse" not in line.lower()
    moved = ev("patient.state", by="D", to="discharging", **{"from": "ward"})
    assert patient_line(moved, {}) == "You are getting ready to go home."
    assert patient_line(moved, {}) != patient_line(ev("discharge.signed", by="D"), {})


def test_patient_lines_pass_the_no_advice_scan():
    advice = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
    state = lambda frm, to: ev("patient.state", by="D", to=to, **{"from": frm})
    events = [state(None, "ward"), state("clinic", "admitting"), state("admitting", "ward"), state("ward", "theatre"),
              state("theatre", "ward"), state("ward", "discharging"), state("discharging", "home"), state("ward", "clinic_done"),
              ev("surgery.began", by="N"), ev("surgery.ended", by="N"), ev("discharge.signed", by="D"),
              ev("order.signed", by="D", items=[{}]), ev("nudge.raised", to="patient", says="Photo flagged."),
              ev("nudge.raised", to="nurse", says="BP low.")]
    for event in events:
        assert not advice.search(patient_line(event, {})), patient_line(event, {})
    for tid in ("t1", "t2", "t3"):
        task_done = ev("task.done", by="Nurse Meena (synthetic)", task_id=tid)
        assert not advice.search(patient_line(task_done, TASKS))


def test_patient_wording():
    s = lambda frm, to: ev("patient.state", by="D", to=to, **{"from": frm})
    assert patient_line(s("clinic", "admitting"), {}) == "You were admitted."
    assert patient_line(s(None, "ward"), {}) == "You were admitted."
    assert patient_line(s("ward", "theatre"), {}) == "You went to theatre."
    assert patient_line(s("theatre", "ward"), {}) == "You are back on the ward."
    assert patient_line(s("discharging", "home"), {}) == "You went home."
    assert patient_line(ev("surgery.ended", by="N"), {}) == "Your operation finished."
    assert patient_line(ev("order.signed", by="D", items=[{}, {}]), {}) == "The doctor signed 2 orders."
    done = lambda tid: ev("task.done", by="Nurse Meena (synthetic)", task_id=tid)
    assert patient_line(done("t1"), TASKS) == "Nurse Meena gave paracetamol."
    assert patient_line(done("t2"), TASKS) == "Nurse Meena checked your observations."
    assert patient_line(done("t3"), TASKS) == "Nurse Meena finished: Saline 1 litre over 2 hours."
    other = ev("help.requested", says="Pain")
    assert patient_line(other, {}) == plain(other)

def test_timeline_items_carry_both_texts():
    events = [ev("task.created", "t1", **{**TASKS["t1"], "order_id": "o1"}),
              ev("task.done", "d1", 120_000, by="Nurse Meena (synthetic)", task_id="t1", via="tap")]
    item = timeline_items(events)[1]
    assert item == {"id": "d1", "when": "Day 0 09:02", "type": "task.done",
                    "plain": "Nurse Meena (synthetic) finished a task.", "patient": "Nurse Meena gave paracetamol."}

def test_ward_orders_and_rx_counts_are_singular():
    assert plain(ev("ward.orders_set", by="D", doses=[{}], obs_every_h=4)) == "Ward orders from D: 1 dose, observations every 4 h."
    assert plain(ev("rx.ordered", by="D", rows=[{}], source="demo")) == "Prescription from D: 1 medicine (demo)."


def test_patient_timeline_hides_staff_drafts_and_the_duplicate_card_line():
    draft = ev("order.drafted", by="D", items=[{}])
    summary = ev("discharge.drafted", by="D")
    card = ev("discharge.card", by="D")
    for e in (draft, summary):
        assert patient_line(e, {}) == "" and "dictated" in plain(e)
    assert patient_line(card, {}) == plain(card)  # no signed line yet: the card line stays
    events = [summary, ev("discharge.signed", "s1", 1, by="D"), ev("discharge.card", "c1", 2, by="D")]
    items = {i["id"]: i["patient"] for i in timeline_items(events)}
    assert items["e1"] == "" and items["c1"] == "" and items["s1"] == "The doctor signed your discharge."
