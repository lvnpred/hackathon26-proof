"""Ops routes: undo, approve, reject, the kill switch and the feed."""

from __future__ import annotations

from app.ops import site
from app.ops.items import ops_view
from app.ops.policy import AI_BY
from tests.test_ops_gate import (ADMIT, ASHA, DR, _admit, _events, _kumar_in_clinic, _move, _of, _ops, _ops_client,
                                 _seed, _store, _url, _ward_with_card)

MEENA = "Nurse Meena (synthetic)"
M = 60_000


def _item(client, eid, prefix):
    return next(r for r in _ops(client, eid)["handling"] if r["summary"].startswith(prefix))["work_id"]


def _undo(client, eid, wi, at_ms, by=MEENA):
    return client.post(_url(eid, f"ops/work/{wi}/undo"), json={"by": by, "at_ms": at_ms})


def _admitted(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    _admit(client, eid, 1000)
    return client, eid, _item(client, eid, "Acknowledged")


def test_undo_inside_window_restores_acknowledge(tmp_path):
    client, eid, wi = _admitted(tmp_path)
    view = _undo(client, eid, wi, 1000 + M)
    assert view.status_code == 200
    body = view.json()
    assert body["order_list"][0]["acknowledged_by"] is None
    assert body["tasks"] == []
    assignment = next(r for r in body["ops"]["handling"] if r["summary"].startswith("Assigned"))
    assert assignment["status"] == "undone"
    reverted = _of(client, eid, "work.reverted")
    assert len(reverted) == 5 and all(e["supersedes_id"] for e in reverted)
    assert len(_of(client, eid, "work.undone")) == 2


def test_undo_after_window_409(tmp_path):
    client, eid, wi = _admitted(tmp_path)
    before = len(_events(client, eid))
    r = _undo(client, eid, wi, 1000 + 600_001)
    assert r.status_code == 409 and r.json()["detail"] == "The undo window has closed."
    assert len(_events(client, eid)) == before
    assert _undo(client, eid, wi, 1000 + 600_000).status_code == 200  # the last ms is still inside


def test_undo_refused_after_person_acted(tmp_path):
    client, eid, wi = _admitted(tmp_path)
    task = next(t for t in client.get(_url(eid, "")[:-1]).json()["tasks"] if t["kind"] == "dose")
    r = client.post(_url(eid, f"tasks/{task['id']}/done"), json={"by": ASHA, "via": "tap", "at_ms": 2000})
    assert r.status_code == 200, r.json()
    before = len(_events(client, eid))
    r = _undo(client, eid, wi, 3000)
    assert r.status_code == 409
    assert r.json()["detail"] == "A person has already acted on this, so it cannot be undone here."
    assert len(_events(client, eid)) == before


def test_undo_twice_and_no_refire(tmp_path):
    client, eid, wi = _admitted(tmp_path)
    assert _undo(client, eid, wi, 1000 + M).status_code == 200
    again = _undo(client, eid, wi, 1000 + 2 * M)
    assert again.status_code == 409 and again.json()["detail"] == "This action cannot be undone."
    view = client.post(_url(eid, "tick"), json={"at_ms": 1000 + 3 * M}).json()
    assert view["order_list"][0]["acknowledged_by"] is None
    assert len(_of(client, eid, "work.opened")) == 2  # the ack and its assignment; nothing reopened
    assert not [e for e in _of(client, eid, "order.acknowledged") if e["payload"]["by"] == AI_BY and not e["supersedes_id"]
                and e["id"] not in {r["supersedes_id"] for r in _of(client, eid, "work.reverted")}]


def _propose_move(client):
    eid = _seed(client)[0]["id"]
    assert _move(client, eid, "admitting", 0, reason="Hernia repair").status_code == 200
    assert _move(client, eid, "ward", 10, checklist=ADMIT).status_code == 200
    assert _move(client, eid, "theatre", 20, procedure="hernia-repair").status_code == 200
    assert client.post(_url(eid, "surgery"), json={"step": "began", "by": DR, "at_ms": 30}).status_code == 200
    assert client.post(_url(eid, "surgery"), json={"step": "ended", "by": DR, "at_ms": 40}).status_code == 200
    return eid


def _proposal(client, eid, kind):
    return next(p["work_id"] for p in _ops(client, eid)["proposals"] if p["kind"] == kind)


def test_approve_move_writes_state_by_the_person(tmp_path):
    client = _ops_client(tmp_path)
    eid = _propose_move(client)
    wi = _proposal(client, eid, "propose_move")
    r = client.post(_url(eid, f"ops/work/{wi}/approve"), json={"by": MEENA, "at_ms": 50})
    assert r.status_code == 200
    state = _of(client, eid, "patient.state")[-1]["payload"]
    assert state["to"] == "ward" and state["by"] == MEENA
    done = next(e for e in _of(client, eid, "work.done") if e["payload"]["work_id"] == wi)["payload"]
    assert done["approved_by"] == MEENA and done["level"] == "L1" and done["wrote"]


def test_approve_move_no_longer_allowed(tmp_path):
    client = _ops_client(tmp_path)
    eid = _propose_move(client)
    wi = _proposal(client, eid, "propose_move")
    store = _store(client)
    store.append(eid, "count.pack_opened", {"quantity": 15, "by": ASHA}, ts_ms=45)
    store.append(eid, "count.closing", {"returned": 14, "unaccounted": 1, "by": ASHA}, ts_ms=46)
    before = len(_events(client, eid))
    r = client.post(_url(eid, f"ops/work/{wi}/approve"), json={"by": MEENA, "at_ms": 50})
    assert r.status_code == 409 and r.json()["detail"].startswith("The closing count is open. A reason is needed")
    assert len(_events(client, eid)) == before


def _ask(client, eid):
    r = client.post(_url(eid, "ask/doctor"), json={"text": "Question?", "at_ms": 100})
    assert r.status_code == 200
    return _proposal(client, eid, "draft_answer")


def test_approve_draft_is_doctor_only_and_writes_doctor_answer(tmp_path):
    client = _ops_client(tmp_path)
    eid = _ward_with_card(client)
    wi = _ask(client, eid)
    before = len(_events(client, eid))
    nurse = client.post(_url(eid, f"ops/work/{wi}/approve"), json={"by": MEENA, "at_ms": 200})
    assert nurse.status_code == 403 and nurse.json()["detail"] == "Only the doctor approves an answer to the patient."
    assert len(_events(client, eid)) == before
    r = client.post(_url(eid, f"ops/work/{wi}/approve"), json={"by": DR, "text": "Edited.", "at_ms": 200})
    assert r.status_code == 200
    answer = r.json()["ask"]["questions"][-1]["answer"]
    assert answer["text"] == "Edited." and answer["source"] == "doctor"
    written = _of(client, eid, "question.answered")[-1]["payload"]
    assert written["by"] == DR and written["sources"] and written["via"] == "text"
    assert next(h for h in _ops(client, eid)["handling"] if h["work_id"] == wi)["status"] == "done"


def test_approve_answered_question_409(tmp_path):
    client = _ops_client(tmp_path)
    eid = _ward_with_card(client)
    wi = _ask(client, eid)
    qid = next(e for e in _of(client, eid, "question.asked"))["id"]
    assert client.post(_url(eid, f"questions/{qid}/answer"), json={"text": "Hi.", "by": DR, "at_ms": 150}).status_code == 200
    before = len(_events(client, eid))
    r = client.post(_url(eid, f"ops/work/{wi}/approve"), json={"by": DR, "at_ms": 200})
    assert r.status_code == 409
    assert len(_events(client, eid)) == before


def test_never_refused_in_api(tmp_path):
    client = _ops_client(tmp_path)
    eid = _seed(client)[0]["id"]
    store = _store(client)
    opened = store.append(eid, "work.opened", {"kind": "clear_count", "reason": "r", "inputs": [], "owner_role": "doctor",
                                               "level": "Never", "key": "k:clear_count:x", "by": AI_BY}, ts_ms=1)
    store.append(eid, "work.proposed", {"work_id": opened["id"], "level": "L1", "sentence": "s", "owner_role": "doctor"}, ts_ms=2)
    before = len(_events(client, eid))
    r = client.post(_url(eid, f"ops/work/{opened['id']}/approve"), json={"by": DR, "at_ms": 3})
    assert r.status_code == 403
    assert r.json()["detail"] == "The AI never does this: clear a count. A person does it from the chart."
    assert len(_events(client, eid)) == before


def test_reject_drops_the_proposal(tmp_path):
    client = _ops_client(tmp_path)
    eid = _ward_with_card(client)
    wi = _ask(client, eid)
    r = client.post(_url(eid, f"ops/work/{wi}/reject"), json={"by": DR, "note": "", "at_ms": 200})
    assert r.status_code == 200
    drop = _of(client, eid, "work.dropped")[-1]["payload"]
    assert drop["code"] == "rejected" and drop["reason"] == "Rejected" and drop["by"] == DR
    assert not _ops(client, eid)["proposals"]
    again = client.post(_url(eid, f"ops/work/{wi}/reject"), json={"by": DR, "at_ms": 300})
    assert again.status_code == 409


def test_ops_boundary_validation(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    other = _seed(client)[1]["id"]
    _admit(client, eid, 1000)
    wi = _item(client, eid, "Acknowledged")
    before = len(_events(client, eid)), len(_events(client, other))
    for tail in ("undo", "approve", "reject"):
        assert client.post(_url(other, f"ops/work/{wi}/{tail}"), json={"by": DR}).status_code == 404
        assert client.post(_url(eid, f"ops/work/nope/{tail}"), json={"by": DR}).status_code == 404
        assert client.post(_url(eid, f"ops/work/{wi}/{tail}"), json={"by": "AI (on behalf of Ward 4)"}).status_code == 422
        assert client.post(_url(eid, f"ops/work/{wi}/{tail}"), json={"by": ""}).status_code == 422
    ai = client.post(_url(eid, f"ops/work/{wi}/undo"), json={"by": "AI (on behalf of Ward 4)"})
    assert ai.json()["detail"] == "A person must do this, not the AI."
    waiting = client.post(_url(eid, f"ops/work/{wi}/approve"), json={"by": DR})
    assert waiting.status_code == 409 and waiting.json()["detail"] == "This proposal is no longer waiting."
    assert client.post(_url(eid, f"ops/work/{wi}/reject"), json={"by": DR}).status_code == 409
    assert (len(_events(client, eid)), len(_events(client, other))) == before


def test_pause_resume_routes(tmp_path):
    client = _ops_client(tmp_path)
    assert client.get("/journey/ops").json() == {"paused": False, "by": None}
    assert client.post("/journey/ops/pause", json={"by": "Charge nurse"}).json() == {"paused": True, "by": "Charge nurse"}
    assert client.get("/journey/ops").json()["paused"] is True
    assert client.post("/journey/ops/resume", json={"by": "Charge nurse"}).json()["paused"] is False
    assert client.post("/journey/ops/pause", json={"by": "AI x"}).status_code == 422
    assert client.get("/journey/ops").json()["paused"] is False


def test_feed_lists_actions_across_roster(tmp_path):
    client = _ops_client(tmp_path)
    kumar = _kumar_in_clinic(client)
    iyer = _seed(client)[1]["id"]
    _admit(client, kumar, 1000)
    r = client.get(f"/journey/ops/feed?ids={kumar},{iyer}")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and all(i["episode_id"] == kumar and i["patient"] == "R. Kumar" for i in items)
    assert [i["at_ms"] for i in items] == sorted((i["at_ms"] for i in items), reverse=True)
    assert client.get("/journey/ops/feed?ids=" + ",".join(f"e{n}" for n in range(11))).status_code == 422
    assert client.get("/journey/ops/feed?ids=nope").status_code == 404


def test_view_carries_ops(tmp_path):
    client, eid, wi = _admitted(tmp_path)
    view = client.get(_url(eid, "")[:-1]).json()
    assert view["ops"] == ops_view(_events(client, eid))


def test_feed_has_no_per_patient_cap_and_pause_default_clock(tmp_path):
    client = _ops_client(tmp_path)
    eid = _seed(client)[0]["id"]
    store = _store(client)
    for n in range(7):
        w = store.append(eid, "work.opened", {"kind": "ack_order", "reason": "r", "inputs": [], "owner_role": "nurse",
                                              "level": "L2", "key": f"k{n}", "by": AI_BY}, ts_ms=n)
        store.append(eid, "work.done", {"work_id": w["id"], "level": "L2", "summary": f"s{n}", "wrote": []}, ts_ms=n)
    assert len(client.get(f"/journey/ops/feed?ids={eid}").json()["items"]) == 7
    assert len(ops_view(_events(client, eid))["handling"]) == 5
    client.post("/journey/ops/pause", json={"by": "Charge nurse", "at_ms": 5000})
    client.post("/journey/ops/resume", json={"by": "Charge nurse"})
    site_events = store.events(site.site_episode(store))
    assert site_events[-1]["ts_ms"] == 6000
