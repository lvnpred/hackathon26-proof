"""Ops gate and run loop: AI actions are ordinary events written inside the same request."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.journey import seed, states
from app.journey.seed import card_payload
from app.ops import plan as planner
from app.ops import run as ops_run
from app.ops import site
from app.ops.items import Action, ops_view
from app.ops.policy import AI_BY
from tests.test_flow_tasks import DOSE, OBS

DR = "Dr. A. Rao (synthetic)"
ASHA = "Nurse Asha (synthetic)"
ADMIT = {"band": True, "allergies": True, "baseline_obs": True, "consent": True}
EVIDENCE = "a" * 32
M = 60_000


def _ops_client(tmp_path, ops_agent=True):
    settings = Settings(
        data_dir=tmp_path, meta_api_key="", meta_base="https://api.meta.ai/v1", sam_model="sam-3.1",
        voice_model="muse-voice-transcribe-1.0", spark_model="muse-spark-1.3", baseten_api_key="",
        spark_open_base="https://inference.baseten.co/v1", spark_open_model="meta-models/muse-spark-open-1026",
        low_confidence=0.45, unannounced_window_ms=30_000, lost_after_frames=4, sam_fps=2,
        dd_base="http://127.0.0.1:9", ops_agent=ops_agent,
    )
    return TestClient(create_app(settings))


def _seed(client):
    return client.post("/journey/demo/seed").json()["patients"]


def _url(eid, tail):
    return f"/journey/episodes/{eid}/{tail}"


def _store(client):
    return client.app.state.morning


def _events(client, eid):
    return _store(client).events(eid)


def _ops(client, eid):
    return ops_view(_events(client, eid))


def _sign(client, eid, at_ms=0):
    return client.post(_url(eid, "orders/sign"), json={"items": [DOSE, OBS], "by": DR, "at_ms": at_ms})


def _move(client, eid, to, at_ms=0, **extra):
    return client.post(_url(eid, "state"), json={"to": to, "by": DR, "at_ms": at_ms, **extra})


def _kumar_in_clinic(client):
    eid = _seed(client)[0]["id"]
    assert client.post(_url(eid, "rx/demo"), json={"at_ms": 0}).status_code == 200
    assert _sign(client, eid).status_code == 200
    return eid


def _admit(client, eid, at_ms=1000):
    return _move(client, eid, "admitting", at_ms, reason="Hernia repair")


def _of(client, eid, kind):
    return [e for e in _events(client, eid) if e["event_type"] == kind]


def test_admit_acks_and_assigns_in_one_write(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    view = _admit(client, eid).json()
    assert view["order_list"][0]["acknowledged_by"] == AI_BY
    assert len(view["tasks"]) == 2
    handling = _ops(client, eid)["handling"]
    assert handling[0]["summary"].startswith("Assigned 2 tasks to")
    assert handling[1]["summary"] == "Acknowledged Dr. A. Rao's orders"
    assert view["now_next"]["next"] == "Nurse completes the admission."


def test_l2_done_lists_wrote_and_window(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    _admit(client, eid, 1000)
    done = next(e for e in _of(client, eid, "work.done") if e["payload"]["summary"].startswith("Acknowledged"))
    ack = _of(client, eid, "order.acknowledged")[0]["id"]
    created = [e["id"] for e in _of(client, eid, "task.created")]
    assert done["payload"]["wrote"] == [ack, *created]
    assert done["payload"]["undo_until_ms"] == 1000 + 600_000
    assert done["payload"]["level"] == "L2" and done["payload"]["by"] == AI_BY


def test_never_is_dropped(tmp_path, monkeypatch):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    monkeypatch.setattr(ops_run, "plan", lambda *a, **k: Action("prescribe", {}, "x"))
    view = _admit(client, eid).json()
    assert view["order_list"][0]["acknowledged_by"] is None
    kinds = {e["event_type"] for e in _events(client, eid) if e["event_type"].startswith("work.")}
    assert kinds == {"work.opened", "work.dropped"}
    assert {e["payload"]["code"] for e in _of(client, eid, "work.dropped")} == {"never"}
    assert not _of(client, eid, "order.acknowledged")


def _ward_with_card(client):
    eid = _seed(client)[0]["id"]
    assert _move(client, eid, "admitting", 0, reason="Hernia repair").status_code == 200
    assert _move(client, eid, "ward", 10, checklist=ADMIT).status_code == 200
    _store(client).append(eid, "discharge.card", card_payload("hernia-repair", None, DR), ts_ms=20)
    return eid


def test_l1_proposes_and_caps_at_three(tmp_path):
    client = _ops_client(tmp_path)
    eid = _ward_with_card(client)
    for n in range(4):
        r = client.post(_url(eid, "ask/doctor"), json={"text": f"Question {n}?", "at_ms": 100 + n})
        assert r.status_code == 200
    proposed = _of(client, eid, "work.proposed")
    assert len(proposed) == 3 and {e["payload"]["owner_role"] for e in proposed} == {"doctor"}
    assert all(e["payload"]["cited"] and e["payload"]["sentence"] for e in proposed)
    rows = ops_view(_events(client, eid))
    assert len(rows["proposals"]) == 3
    assert [o["kind"] for o in rows["open"]] == ["draft_answer"]
    assert len(_of(client, eid, "question.routed")) == 4


def test_seed_stays_quiet(tmp_path):  # the scripted play this also ran is archived (Task 16, U13)
    client = _ops_client(tmp_path)
    patients = _seed(client)
    for p in patients:
        assert not [e for e in _events(client, p["id"]) if e["event_type"].startswith("work.")]


def test_paused_opens_but_does_nothing(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    site.set_paused(_store(client), True, "Charge nurse", 0)
    view = _admit(client, eid).json()
    assert view["order_list"][0]["acknowledged_by"] is None
    assert [o["kind"] for o in _ops(client, eid)["open"]] == ["ack_order"]
    assert _of(client, eid, "work.opened") and not _of(client, eid, "work.done")


def test_resume_acts_or_drops(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    site.set_paused(_store(client), True, "Charge nurse", 0)
    _admit(client, eid)
    site.set_paused(_store(client), False, "Charge nurse", 2000)
    view = client.post(_url(eid, "tick"), json={"at_ms": 3000}).json()
    assert view["order_list"][0]["acknowledged_by"] == AI_BY
    # A person acts while paused: on resume the item is closed, not redone.
    other = _ops_client(tmp_path / "b")
    eid = _kumar_in_clinic(other)
    site.set_paused(_store(other), True, "Charge nurse", 0)
    _admit(other, eid)
    order = other.get(_url(eid, "")[:-1]).json()["order_list"][0]
    assert other.post(_url(eid, f"orders/{order['id']}/ack"), json={"by": ASHA, "at_ms": 1500}).status_code == 200
    site.set_paused(_store(other), False, "Charge nurse", 2000)
    other.post(_url(eid, "tick"), json={"at_ms": 3000})
    drops = _of(other, eid, "work.dropped")
    assert [d["payload"]["code"] for d in drops][0] == "done_by_person"
    assert _of(other, eid, "order.acknowledged")[0]["payload"]["by"] == ASHA


def _theatre_with_pack(client, opened_at=0):
    eid = _seed(client)[0]["id"]
    assert _move(client, eid, "admitting", 0, reason="Hernia repair").status_code == 200
    assert _move(client, eid, "ward", 10, checklist=ADMIT).status_code == 200
    assert _move(client, eid, "theatre", 20, procedure="hernia-repair").status_code == 200
    assert client.post(_url(eid, "count"), json={"step": "opened", "quantity": 15, "by": ASHA, "at_ms": 30}).status_code == 200
    _store(client).append(eid, "swabs.counted", {"count": 14, "opened": 15, "evidence_id": EVIDENCE, "rows": [], "missing": [],
                                                  "match": "mismatch", "why": "w", "source": "prepared",
                                                  "frame_ids": [], "by": ASHA}, ts_ms=1000)
    return eid


def test_camera_count_is_never_filed_by_the_ai(tmp_path):
    """Ruling F-I3: no file_read opens for a camera count, even long after 5 minutes; the AI writes no closing."""
    client = _ops_client(tmp_path)
    eid = _theatre_with_pack(client)
    for at in (1000 + 4 * M, 1000 + 5 * M, 1000 + 30 * M):
        client.post(_url(eid, "tick"), json={"at_ms": at})
    assert not _of(client, eid, "count.closing")
    assert not [e for e in _of(client, eid, "work.opened") if e["payload"]["kind"] == "file_read"]


def test_person_closing_keeps_camera_read_and_saved(tmp_path):
    client = _ops_client(tmp_path)
    eid = _theatre_with_pack(client)
    client.post(_url(eid, "tick"), json={"at_ms": 1000 + 6 * M})
    view = client.post(_url(eid, "count"), json={"step": "closing", "returned": 15, "by": ASHA, "detail": "Found under the drape.",
                                                 "evidence_id": EVIDENCE, "at_ms": 1000 + 6 * M}).json()
    closing = _of(client, eid, "count.closing")[0]["payload"]
    assert closing["by"] == ASHA and closing["via"] == "camera" and closing["evidence_id"] == EVIDENCE
    assert view["count"]["read"] == {"returned": 14}
    assert view["count"]["saved"] == {"returned": 15}
    assert view["count"]["closed_by"] == ASHA


def test_patient_never_sees_work(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    _admit(client, eid)
    view = client.post(_url(eid, "ask/doctor"), json={"text": "When can I eat?", "at_ms": 5000}).json()
    work = [t for t in view["timeline"] if t["type"].startswith("work.") or t["type"] == "task.assigned"]
    assert work and all(t["patient"] == "" for t in work)
    assert not [t for t in view["timeline"] if t["type"] in ("work.opened", "work.reverted")]
    routed = [t for t in view["timeline"] if t["type"] == "question.routed"]
    assert [t["patient"] for t in routed] == ["Your question went to Dr. A. Rao."]


def test_agent_off_by_default_changes_nothing(tmp_path):
    client = _ops_client(tmp_path, ops_agent=False)
    eid = _kumar_in_clinic(client)
    view = _admit(client, eid).json()
    assert view["order_list"][0]["acknowledged_by"] is None
    assert not [e for e in _events(client, eid) if e["event_type"].startswith("work.")]


def test_closing_payload_needs_a_pack():
    with pytest.raises(ValueError, match="Record the pack opened first."):
        states.closing_payload([], 3, "x")


def test_plan_move_names_the_patient():
    from app.ops.items import WorkItem
    item = WorkItem("propose_move", "r", ("s1",), "nurse", "move_ready", "move_ready:propose_move:ward:s1")
    ev = [{"id": "s0", "episode_id": "e", "ts_ms": 0, "wall_clock": "", "event_type": "patient.state",
           "payload": {"from": "ward", "to": "theatre", "by": DR}, "supersedes_id": None, "tier": "documentation"}]
    action = planner.plan(item, ev, patient="R. Kumar")
    assert action is None or action.sentence == "Back to ward: R. Kumar"


def test_new_copy_has_no_advice_words():
    advice = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
    from app.journey.stories import plain
    for kind, p in (("work.proposed", {"owner_role": "doctor", "sentence": "Back to ward: R. Kumar"}),
                    ("work.dropped", {"reason": "A person already did this."}),
                    ("work.undone", {"by": DR}), ("task.assigned", {"by": AI_BY, "to": ASHA}),
                    ("question.routed", {"by": AI_BY, "to": DR})):
        assert not advice.search(plain({"event_type": kind, "payload": p, "ts_ms": 0}))


def test_agent_error_never_fails_the_write(tmp_path, monkeypatch):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)

    def boom(*a, **k):
        raise RuntimeError("planner down")

    monkeypatch.setattr(ops_run, "plan", boom)
    r = _admit(client, eid)
    assert r.status_code == 200
    assert _of(client, eid, "patient.state")[-1]["payload"]["to"] == "admitting"


def test_refused_helper_is_dropped_with_detail(tmp_path, monkeypatch):
    from app.ops import gate
    from app.journey import tasks

    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)

    def refuse(*a, **k):
        raise tasks.TaskError(409, "Not allowed now.")

    monkeypatch.setattr(gate, "execute", refuse)
    _admit(client, eid)
    drops = _of(client, eid, "work.dropped")
    assert drops and drops[0]["payload"]["code"] == "refused" and drops[0]["payload"]["reason"] == "Not allowed now."
    assert not _of(client, eid, "order.acknowledged")


def test_no_longer_needed_reason_is_truthful(tmp_path, monkeypatch):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    monkeypatch.setattr(ops_run, "plan", lambda *a, **k: None)
    _admit(client, eid)
    drop = _of(client, eid, "work.dropped")[0]["payload"]
    assert drop["code"] == "done_by_person" and drop["reason"] == "No longer needed."


def test_patient_lens_hides_ai_authored_helper_events(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    view = _admit(client, eid).json()
    acked = [t for t in view["timeline"] if t["type"] == "order.acknowledged"]
    assert acked and all(t["patient"] == "" for t in acked)
    assert "acknowledged" not in view["now_next"]["you_now"]
    from app.journey.stories import AI_PREFIX
    assert AI_BY.startswith(AI_PREFIX)


def test_monitor_read_is_filed_after_five_minutes(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    _admit(client, eid, 1000)
    task = next(t for t in client.get(_url(eid, "")[:-1]).json()["tasks"] if t["kind"] == "obs")
    store = _store(client)
    photo = store.append(eid, "photo.added", {"purpose": "proof", "by": ASHA, "task_id": task["id"]}, ts_ms=2000)
    values = {"sbp": 118, "dbp": 76, "hr": 80}
    store.append(eid, "proof.checked", {"photo_id": photo["id"], "task_id": task["id"], "values_read": values,
                                        "match": "ok", "why": "w", "source": "prepared"}, ts_ms=2000)
    client.post(_url(eid, "tick"), json={"at_ms": 2000 + 4 * M})
    assert not _of(client, eid, "task.done")
    client.post(_url(eid, "tick"), json={"at_ms": 2000 + 5 * M})
    done = _of(client, eid, "task.done")[0]["payload"]
    assert done["by"] == AI_BY and done["values"] == values and done["proof_id"] == photo["id"]
    work = [e for e in _of(client, eid, "work.done") if e["payload"]["summary"].startswith("Filed the monitor read")][0]
    assert work["payload"]["undo_until_ms"] == 2000 + 5 * M + 600_000
