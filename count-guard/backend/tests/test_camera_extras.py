"""Count extras on the theatre swab camera (spec §6.4, §6.5, U10, §9): replay of recorded detections (Prepared), the
bucket-dwell counter, resolve of camera advice with a reason, and closing the camera case with the drafted
explanation and the count-sheet PDF. None of them writes a swab count."""

from __future__ import annotations

import dataclasses
import json

from app.adapters import spark as spark_adapter
from app.adapters import spark_open
from app.core.ledger import open_discrepancies
from app.journey import states
from app.journey.stories import CAMERA_BY
from app.ops.policy import AI_BY
from tests.test_count_gate_paths import NURSE, _begin_with_pack, _camera, _events, _new_patient, _post_json


def _kinds(client, eid, kind):
    return [e for e in _events(client, eid) if e["event_type"] == kind]


def _counts(client, eid):
    return [e["id"] for e in _events(client, eid) if e["event_type"] in ("count.closing", "count.pack_opened")]


def _live(client, **changes):
    client.app.state.settings = dataclasses.replace(client.app.state.settings, **changes)


def test_replay_is_labelled_prepared(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    before = _counts(client, eid)
    r = _post_json(client, eid, "/camera/replay", {"by": NURSE})
    assert r.status_code == 200, r.text
    replay = r.json()["camera"]["replay"]
    assert replay["source"] == "prepared"
    assert (replay["opened"], replay["returned"], replay["missing"]) == (20, 19, ["swab-20"])
    rows = [a for a in r.json()["camera"]["advice"] if a["source"] == "prepared" and a["item"] == "swab-20"]
    assert len(rows) == 1 and "_" not in rows[0]["text"] and not rows[0]["frame_url"]
    written = _kinds(client, eid, "camera.replayed")
    assert len(written) == 1 and written[0]["payload"]["by"] == CAMERA_BY and written[0]["payload"]["started_by"] == NURSE
    assert _counts(client, eid) == before and not _kinds(client, eid, "count.item_out")
    _post_json(client, eid, "/camera/replay", {"by": NURSE})  # the same finding is not advised twice
    assert len([a for a in _kinds(client, eid, "camera.advice") if a["payload"]["item"] == "swab-20"]) == 1


def test_replay_only_in_theatre(tmp_path):
    client = _new_patient(tmp_path)[0]
    eid = client.post("/journey/patients", json={"name": "L. Rao (synthetic)", "age_sex": "40 F", "reason": "Lump"}).json()["episode_id"]
    assert _post_json(client, eid, "/camera/replay", {"by": NURSE}).status_code == 409
    assert _post_json(client, eid, "/camera/dwell", {"track_id": "s1", "zone": "bucket", "t_ms": 0}).status_code == 409


def test_bucket_dwell_counts_returned(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    before = _counts(client, eid)

    def frame(track, zone, t):
        r = _post_json(client, eid, "/camera/dwell", {"track_id": track, "zone": zone, "frame_id": f"{track}-{t}", "t_ms": t})
        assert r.status_code == 200, r.text
        return r.json()

    for t in (0, 100):
        assert frame("swab-1", "bucket", t)["emitted"] == []
    third = frame("swab-1", "bucket", 200)  # three frames in the bucket: counted back
    assert third["returned"] == 1 and third["out"] == ["swab-1"] and len(third["emitted"]) == 1
    assert frame("swab-1", "bucket", 300)["returned"] == 1  # never counted twice
    frame("swab-2", "bucket", 400)
    frame("swab-2", "bucket", 500)
    waved = frame("swab-2", "field", 600)  # a hand wave out of the bucket before the dwell is not a swab back
    assert waved["returned"] == 1 and waved["out"] == ["swab-1"]
    out = _kinds(client, eid, "camera.item_out")
    assert [e["payload"]["track_id"] for e in out] == ["swab-1"]
    assert out[0]["payload"]["by"] == CAMERA_BY and out[0]["payload"]["frame_id"] == "swab-1-200"
    assert client.get(f"/journey/episodes/{eid}/camera").json()["dwell"] == {"returned": 1}
    assert _counts(client, eid) == before and not _kinds(client, eid, "count.item_out")
    bad = _post_json(client, eid, "/camera/dwell", {"track_id": "s", "zone": "floor", "t_ms": 0})
    assert bad.status_code == 422


def test_resolve_needs_reason(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    advice = next(a for a in _camera(client, eid, "clip2")["camera"]["advice"] if a["rule"] == "R3")
    path = f"/camera/advice/{advice['id']}/resolve"
    before = _counts(client, eid)
    assert _post_json(client, eid, path, {"by": NURSE, "reason": "   "}).status_code == 422
    assert _post_json(client, eid, path, {"by": NURSE}).status_code == 422
    for by in (CAMERA_BY, AI_BY, " count guard ai"):
        assert _post_json(client, eid, path, {"by": by, "reason": "Found it"}).status_code == 422, by
    assert _post_json(client, eid, "/camera/advice/nope/resolve", {"by": NURSE, "reason": "x"}).status_code == 404
    r = _post_json(client, eid, path, {"by": NURSE, "reason": " Found under the drape "})
    assert r.status_code == 200, r.text
    row = next(a for a in r.json()["camera"]["advice"] if a["id"] == advice["id"])
    assert row["resolved"] == {"by": NURSE, "reason": "Found under the drape"}
    case_id = r.json()["camera"]["case_id"]
    key = next(e for e in _kinds(client, eid, "camera.advice") if e["id"] == advice["id"])["payload"]["key"]
    found = [d for d in open_discrepancies(client.app.state.store.events(case_id)) if key == f"{case_id}:{d['id']}"]
    assert found and found[0]["status"] == "resolved" and found[0]["resolution"]["by"] == NURSE
    assert _post_json(client, eid, path, {"by": NURSE, "reason": "again"}).status_code == 200
    assert len(_kinds(client, eid, "camera.resolved")) == 1
    assert _counts(client, eid) == before  # resolving advice never changes the count


def test_close_writes_count_sheet_pdf(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    pdf = f"/journey/episodes/{eid}/camera/count-sheet.pdf"
    assert _post_json(client, eid, "/camera/close", {"by": NURSE}).status_code == 409  # no camera case yet
    _camera(client, eid, "clip2")
    assert client.get(pdf).status_code == 409
    r = _post_json(client, eid, "/camera/close", {"by": NURSE})
    assert r.status_code == 200, r.text
    closed = r.json()["camera"]["closed"]
    assert closed["source"] == "prepared" and closed["text"] and "_" not in closed["text"]
    assert closed["count_sheet_url"] == pdf and closed["by"] == NURSE
    got = client.get(pdf)
    assert got.status_code == 200 and got.headers["content-type"] == "application/pdf" and got.content[:4] == b"%PDF"
    sheets = list(tmp_path.rglob("count-sheet*.pdf"))
    assert len(sheets) == 1 and tmp_path in sheets[0].parents  # the data dir, never the repo
    event = _kinds(client, eid, "camera.closed")[0]
    assert event["payload"]["by"] == CAMERA_BY and event["payload"]["closed_by"] == NURSE
    assert _post_json(client, eid, "/camera/close", {"by": CAMERA_BY}).status_code == 422


def _sentences(prompt: str) -> str:
    rows = json.loads(prompt.split("Discrepancies:\n", 1)[1].split("\n", 1)[0])
    return json.dumps({"sentences": [
        {"discrepancy_id": row["id"], "text": f"One {row['item_type']} is not seen back. Evidence {row['evidence'][0]}.",
         "evidence_ids": row["evidence"][:1], "claims": {}} for row in rows]})


def test_explanation_never_writes_closing(tmp_path, monkeypatch):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    _camera(client, eid, "clip2")
    before = _counts(client, eid)
    asked: list[str] = []

    def write(self, prompt):
        asked.append(prompt)
        return _sentences(prompt)

    monkeypatch.setattr(spark_adapter.SparkAdapter, "write", write)
    _live(client, meta_api_key="test-key")
    r = _post_json(client, eid, "/camera/close", {"by": NURSE})
    assert r.status_code == 200, r.text
    closed = r.json()["camera"]["closed"]
    assert asked and closed["source"] == "spark" and "is not seen back" in closed["text"] and "Evidence" not in closed["text"]
    assert _kinds(client, eid, "camera.closed")[-1]["payload"]["model"] == "muse-spark-1.3"
    events = _events(client, eid)
    assert _counts(client, eid) == before
    assert states.count_gate(events) == "none" and _end_refused(client, eid)


def test_explanation_uses_spark_open_when_its_key_is_set(tmp_path, monkeypatch):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    _camera(client, eid, "clip2")

    def complete(self, messages, tools):
        return {"role": "assistant", "content": _sentences(messages[1]["content"])}

    monkeypatch.setattr(spark_open.SparkOpenAdapter, "_http_complete", complete)
    _live(client, meta_api_key="test-key", baseten_api_key="test-key")
    closed = _post_json(client, eid, "/camera/close", {"by": NURSE}).json()["camera"]["closed"]
    assert closed["source"] == "spark"
    assert _kinds(client, eid, "camera.closed")[-1]["payload"]["model"] == "meta-models/muse-spark-open-1026"


def test_explanation_falls_back_to_prepared_when_the_call_fails(tmp_path, monkeypatch):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    _camera(client, eid, "clip2")

    def fail(self, prompt):
        raise RuntimeError("down")

    monkeypatch.setattr(spark_adapter.SparkAdapter, "write", fail)
    _live(client, meta_api_key="test-key")
    closed = _post_json(client, eid, "/camera/close", {"by": NURSE}).json()["camera"]["closed"]
    assert closed["source"] == "prepared" and closed["text"]


def _end_refused(client, eid):
    return _post_json(client, eid, "/surgery", {"step": "ended", "by": NURSE}).status_code == 409
