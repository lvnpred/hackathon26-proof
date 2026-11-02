"""Intake (spec §7.1, §7.2, §7.5): one path for a Doctor Dictation push, Sync and a new patient."""

from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

from app.journey import intake, seed
from app.ops import run as ops_run
from tests.test_care_demo import _client
from tests.test_flow_states import ADMIT_CHECKS

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "dd_admission.json").read_text())
LABEL = "M. Fernandes, 52 F (synthetic)"


def _payload(**changes) -> dict:
    payload = copy.deepcopy(FIXTURE)
    payload.update(changes)
    return payload


def _post(client, payload=None, headers=None):
    return client.post("/journey/intake", json=payload or _payload(), headers=headers or {})


def _events(client, eid):
    return client.app.state.morning.events(eid)


def _kinds(client, eid):
    return [e["event_type"] for e in _events(client, eid)]


def _ward(client):
    return client.get("/journey/ward").json()["patients"]


def _move(client, eid, to, **extra):
    body = {"to": to, "by": seed.DOCTOR, **extra}
    return client.post(f"/journey/episodes/{eid}/state", json=body)


def _resaved() -> dict:
    later = _payload(finalized_at="2026-11-03T11:02:40")
    later["document"]["structured"]["rx"][0]["dose"] = "1-1-1"
    return later


def test_admit_creates_patient_in_admitting_with_rx(tmp_path):
    client = _client(tmp_path)
    res = _post(client)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["created"] is True and body["updated"] is False and body["notice"] is None
    eid = body["episode_id"]
    row = next(p for p in _ward(client) if p["id"] == eid)
    assert row["state"] == "admitting"
    assert row["name"] == LABEL
    assert row["source"] == "doctor-dictation" and row["document_id"] == 42
    events = _events(client, eid)
    assert [e["event_type"] for e in events] == ["patient.registered", "rx.ordered", "patient.state"]
    registered = events[0]["payload"]
    assert registered == {
        "bed": body["bed"], "source": "doctor-dictation", "document_id": 42, "age_sex": "52 F",
        "op_no": "OP-24-0042", "diagnosis": ["Left inguinal hernia, for elective repair"],
        "dd_doctor": "Dr. A. Rao (synthetic)",
    }
    assert [r["name"] for r in events[1]["payload"]["rows"]] == ["Paracetamol", "Pantoprazole"]
    assert events[2]["payload"]["to"] == "admitting"
    assert events[2]["payload"]["reason"] == FIXTURE["admit_reason"]


def test_second_post_is_idempotent(tmp_path):
    client = _client(tmp_path)
    first = _post(client).json()
    res = _post(client)
    assert res.status_code == 200
    assert res.json()["created"] is False and res.json()["episode_id"] == first["episode_id"]
    assert _kinds(client, first["episode_id"]).count("patient.registered") == 1


def test_concurrent_different_documents_get_distinct_beds(tmp_path):
    client = _client(tmp_path)
    store = client.app.state.morning
    results = []

    def take(n):
        results.append(intake.take(store, _payload(document_id=100 + n), now_ms=0))

    threads = [threading.Thread(target=take, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({r["bed"] for r in results}) == 8
    assert sorted(int(r["bed"]) for r in results) == list(range(1, 9))


def test_push_and_sync_race_make_one_patient(tmp_path):
    client = _client(tmp_path)
    store = client.app.state.morning
    results = []

    def take():
        results.append(intake.take(store, _payload(), now_ms=0))

    threads = [threading.Thread(target=take) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(r["created"] for r in results) == 1
    assert len({r["episode_id"] for r in results}) == 1
    assert len([p for p in _ward(client) if p["document_id"] == 42]) == 1
    assert _kinds(client, results[0]["episode_id"]).count("rx.ordered") == 1


def test_resave_with_new_finalized_at_supersedes_rx(tmp_path):
    client = _client(tmp_path)
    eid = _post(client).json()["episode_id"]
    old = next(e for e in _events(client, eid) if e["event_type"] == "rx.ordered")
    res = _post(client, _resaved())
    assert res.status_code == 200
    body = res.json()
    assert body["updated"] is True and body["created"] is False
    assert body["notice"] == "Prescription updated in Doctor Dictation"
    rx = [e for e in _events(client, eid) if e["event_type"] == "rx.ordered"]
    assert len(rx) == 2 and rx[1]["supersedes_id"] == old["id"]
    assert rx[1]["payload"]["rows"][0]["dose"] == "1-1-1"
    chart = client.get(f"/journey/episodes/{eid}").json()
    assert chart["rx"]["rows"][0]["dose"] == "1-1-1"
    assert any(i["plain"] == "Prescription updated in Doctor Dictation" for i in chart["timeline"])


def test_resave_after_theatre_never_changes_state(tmp_path):
    client = _client(tmp_path)
    eid = _post(client).json()["episode_id"]
    assert _move(client, eid, "ward", checklist=ADMIT_CHECKS).status_code == 200
    assert _move(client, eid, "theatre", procedure="hernia-repair").status_code == 200
    assert _post(client, _resaved()).json()["updated"] is True
    assert client.get(f"/journey/episodes/{eid}").json()["state"] == "theatre"


def test_send_home_resave_adds_notice_only(tmp_path):
    client = _client(tmp_path)
    eid = _post(client).json()["episode_id"]
    before = _kinds(client, eid)
    res = _post(client, _payload(status="send_home", finalized_at="2026-11-03T12:00:00"))
    assert res.status_code == 200
    assert res.json()["notice"] == "Doctor Dictation now says: send home"
    events = _events(client, eid)
    assert [e["event_type"] for e in events] == before + ["notice.dd"]
    assert events[-1]["payload"]["text"] == "Doctor Dictation now says: send home"
    assert client.get(f"/journey/episodes/{eid}").json()["state"] == "admitting"


def test_send_home_for_a_document_never_admitted_makes_nobody(tmp_path):
    client = _client(tmp_path)
    res = _post(client, _payload(status="send_home"))
    assert res.status_code == 422
    assert _ward(client) == []


def test_unchanged_resave_appends_nothing(tmp_path):
    client = _client(tmp_path)
    eid = _post(client).json()["episode_id"]
    count = len(_events(client, eid))
    body = _post(client).json()
    assert body["updated"] is False and body["notice"] is None
    assert len(_events(client, eid)) == count


def test_token_required_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv("CG_SYNC_TOKEN", "t")
    client = _client(tmp_path)
    assert _post(client).status_code == 401
    assert _post(client, headers={"X-CG-Sync-Token": "wrong"}).status_code == 401
    assert _post(client, headers={"X-CG-Sync-Token": "t"}).status_code == 201


def test_no_token_needed_when_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("CG_SYNC_TOKEN", raising=False)
    assert _post(_client(tmp_path)).status_code == 201


def test_new_patient_starts_in_clinic(tmp_path):
    client = _client(tmp_path)
    res = client.post("/journey/patients", json={"name": "K. Nair (synthetic)", "age_sex": "35 M", "reason": "Lump"})
    assert res.status_code == 201, res.text
    eid = res.json()["episode_id"]
    row = next(p for p in _ward(client) if p["id"] == eid)
    assert row["state"] == "clinic" and row["source"] == "count-guard" and row["name"] == "K. Nair, 35 M (synthetic)"
    assert "rx.ordered" not in _kinds(client, eid)
    assert _move(client, eid, "admitting", reason="x").status_code == 200


def test_new_patient_needs_synthetic_name_in_demo(tmp_path):
    client = _client(tmp_path)
    assert client.post("/journey/demo/seed").status_code == 200
    res = client.post("/journey/patients", json={"name": "K. Nair", "age_sex": "35 M", "reason": "Lump"})
    assert res.status_code == 422
    two = client.post("/journey/patients", json={"name": "K. Nair (synthetic)", "age_sex": "35 M", "reason": "Lump"})
    assert two.status_code == 201
    three = client.post("/journey/patients", json={"name": "L. Rao (synthetic)", "age_sex": "", "reason": ""})
    assert three.status_code == 201 and two.json()["bed"] != three.json()["bed"]


def test_settle_runs_after_intake(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ops_run, "run", lambda store, eid, ts, **kw: calls.append(eid))
    client = _client(tmp_path)
    eid = _post(client).json()["episode_id"]
    assert calls == [eid]
    _post(client)
    assert calls == [eid]  # nothing changed, nothing to settle


def test_intake_links_dd_pdf_via_dd_base_url(tmp_path):
    client = _client(tmp_path, dd_base="http://127.0.0.1:8300")
    eid = _post(client).json()["episode_id"]
    header = client.get(f"/journey/episodes/{eid}").json()["header"]
    assert header["dd_pdf"] == "http://127.0.0.1:8300/api/v1/documents/42/pdf"
    assert header["age_sex"] == "52 F" and header["op_no"] == "OP-24-0042"
    assert header["diagnosis"] == ["Left inguinal hernia, for elective repair"]
    assert header["dd_doctor"] == "Dr. A. Rao (synthetic)"
    assert header["bed"] == "1"


def test_seeded_patient_has_no_dd_link(tmp_path):
    client = _client(tmp_path)
    kumar = client.post("/journey/demo/seed").json()["patients"][0]["id"]
    header = client.get(f"/journey/episodes/{kumar}").json()["header"]
    assert header["dd_pdf"] is None and header["bed"] == "4"


def test_doctor_moves_bed(tmp_path):
    client = _client(tmp_path)
    eid = _post(client).json()["episode_id"]
    other = _post(client, _payload(document_id=43)).json()
    assert other["bed"] == "2"
    res = client.post(f"/journey/episodes/{eid}/bed", json={"bed": "5", "by": seed.DOCTOR})
    assert res.status_code == 200, res.text
    assert next(p for p in _ward(client) if p["id"] == eid)["bed"] == "5"
    assert _kinds(client, eid)[-1] == "bed.changed"
    taken = client.post(f"/journey/episodes/{eid}/bed", json={"bed": "2", "by": seed.DOCTOR})
    assert taken.status_code == 409
    assert next(p for p in _ward(client) if p["id"] == eid)["bed"] == "5"
    assert client.post("/journey/episodes/nope/bed", json={"bed": "6", "by": seed.DOCTOR}).status_code == 404


def test_reset_clears_intake_keys(tmp_path):
    client = _client(tmp_path)
    first = _post(client).json()["episode_id"]
    assert client.post("/journey/demo/seed").status_code == 200
    assert all(p["document_id"] != 42 for p in _ward(client))
    res = _post(client)
    assert res.status_code == 201 and res.json()["episode_id"] != first
    assert len([p for p in _ward(client) if p["document_id"] == 42]) == 1


def test_resave_racing_the_first_push_never_leaves_the_older_rx_current(tmp_path):
    client = _client(tmp_path)
    store = client.app.state.morning
    payloads = [_payload() if n % 2 == 0 else _resaved() for n in range(8)]
    results = []

    def take(payload):
        results.append(intake.take(store, payload, now_ms=0))

    threads = [threading.Thread(target=take, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    eid = results[0]["episode_id"]
    assert sum(r["created"] for r in results) == 1
    _post(client, _resaved())  # the next Sync
    chart = client.get(f"/journey/episodes/{eid}").json()
    assert chart["rx"]["rows"][0]["dose"] == "1-1-1"
    rx = [e for e in _events(client, eid) if e["event_type"] == "rx.ordered"]
    assert all(e["supersedes_id"] == rx[i]["id"] for i, e in enumerate(rx[1:]))  # one chain, no stray list


def test_resave_while_the_first_write_is_in_flight_changes_nothing(tmp_path):
    client = _client(tmp_path)
    store = client.app.state.morning
    # Thread A has claimed the document but written no events yet.
    eid, created = store.claim_intake("doctor-dictation", 42, FIXTURE["finalized_at"], LABEL)
    assert created
    result = intake.take(store, _resaved(), now_ms=0)
    assert result["episode_id"] == eid and result["updated"] is False
    assert store.events(eid) == []
    # The stored time is still A's, so the next Sync with the newer document is an update.
    assert store.update_intake("doctor-dictation", 42, FIXTURE["finalized_at"]) is False


def test_an_older_save_arriving_late_changes_nothing(tmp_path):
    client = _client(tmp_path)
    eid = _post(client).json()["episode_id"]
    assert _post(client, _resaved()).json()["updated"] is True
    count = len(_events(client, eid))
    late = _post(client)  # the first save, delivered after the re-save
    assert late.status_code == 200 and late.json()["updated"] is False
    assert len(_events(client, eid)) == count
    assert client.get(f"/journey/episodes/{eid}").json()["rx"]["rows"][0]["dose"] == "1-1-1"
