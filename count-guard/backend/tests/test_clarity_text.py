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
