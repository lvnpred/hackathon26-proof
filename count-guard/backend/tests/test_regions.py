"""Photo regions: SAM boxes paired with Spark values. Never a live call."""

from __future__ import annotations

import re

import httpx
from fastapi.testclient import TestClient

from app.adapters.sam import SamAdapter
from app.adapters.spark import SparkAdapter
from app.journey import evidence, live
from app.journey.regions import READER_CONCEPTS, monitor_values, pair_regions, strip_values
from app.main import create_app
from tests.test_flow_states import _to_ward
from tests.test_flow_tasks import DOSE, NURSE, OBS, _ack, _sign
from tests.test_p3_video import ADVICE, _keyed, _no_key, no_network  # noqa: F401  (fixture)

PNG = b"\x89PNG" + b"x" * 20
B = lambda x, y: {"bbox": [x, y, 0.2, 0.1], "score": 0.9}
V = lambda s: {"label": s, "value": s}
MONITOR = '{"sbp": 118, "dbp": 76, "hr": 80}'


def _recs(ys, label="digital display", score=0.9):
    return [{"frame_index": 0, "object_id": str(i), "label": label, "bbox": [0.4, y, 0.2, 0.1], "score": score} for i, y in enumerate(ys)]


def test_pair_equal_counts_reads_top_to_bottom_then_left_to_right():
    out = pair_regions([B(0.5, 0.5), B(0.6, 0.1), B(0.1, 0.12)], [V("a"), V("b"), V("c")])
    assert [(r["bbox"][:2], r["label"], r["row"]) for r in out] == [([0.1, 0.12], "a", 0), ([0.6, 0.1], "b", 1), ([0.5, 0.5], "c", 2)]


def test_pair_more_regions():
    out = pair_regions([B(0.1, 0.1), B(0.1, 0.5)], [V("a")])
    assert [(r["label"], r["row"]) for r in out] == [("a", 0), (None, None)]


def test_pair_more_values():
    out = pair_regions([B(0.1, 0.1)], [V("a"), V("b")])
    assert [(r["bbox"] is None, r["label"]) for r in out] == [(False, "a"), (True, "b")]


def test_pair_zero_regions():
    assert [r["bbox"] for r in pair_regions([], [V("a")])] == [None]


def test_monitor_values_always_three():
    assert monitor_values({"sbp": 88, "dbp": 54}) == [{"label": "SBP", "value": "88"}, {"label": "DBP", "value": "54"}, {"label": "HR", "value": None}]


def test_strip_values_name_and_strength():
    strips = [{"name_as_read": "Paracetamol", "strength": "500 mg"}, {"name_as_read": "Aspirin", "strength": ""}]
    assert [v["label"] for v in strip_values(strips)] == ["Paracetamol 500 mg", "Aspirin"]
    assert READER_CONCEPTS == {"strip": ["blister strip"], "monitor": ["digital display"]}


def test_read_photo_prepared_monitor_has_boxes(tmp_path):
    out = live.read_photo(_no_key(tmp_path), "monitor", b"x", "monitor-88-54.png", "image/png")
    assert [(r["label"], r["value"]) for r in out["regions"]] == [("SBP", "88"), ("DBP", "54"), ("HR", "112")]
    assert all(r["bbox"] for r in out["regions"]) and out["handmade"] is True
    assert [c["model"] for c in out["calls"]] == ["sam", "spark"]


def test_read_photo_prepared_without_regions_has_values_only(tmp_path):
    out = live.read_photo(_no_key(tmp_path), "monitor", b"x", "iyer-bp.png", "image/png")
    assert out["text"] is None and out["regions"] == [] and out["calls"] == []


def test_read_photo_prepared_meds_have_a_box_per_card(tmp_path):
    out = live.read_photo(_no_key(tmp_path), "strip", b"x", "meds-kumar.png", "image/png")
    assert [r["row"] for r in out["regions"]] == [0, 1, 2, 3] and all(r["bbox"] for r in out["regions"])
    assert out["regions"][0]["label"] == "Metoprolol 25 mg"


def test_read_photo_live_pairs_sam_with_spark(tmp_path, monkeypatch):
    monkeypatch.setattr(SamAdapter, "segment_images", lambda self, urls, concepts: _recs((0.7, 0.1, 0.4)))
    monkeypatch.setattr(SparkAdapter, "read_monitor", lambda self, url: MONITOR)
    out = live.read_photo(_keyed(tmp_path), "monitor", b"x", "a.png", "image/png")
    assert [(r["bbox"][1], r["label"]) for r in out["regions"]] == [(0.1, "SBP"), (0.4, "DBP"), (0.7, "HR")]
    assert [(c["model"], c["source"]) for c in out["calls"]] == [("sam", "sam-3.1"), ("spark", "muse-spark-1.3")]
    assert out["raw"]["spark"] == MONITOR and len(out["raw"]["sam"]) == 3 and out["handmade"] is False


def test_read_photo_live_asks_sam_for_the_reader_concepts_and_drops_low_boxes(tmp_path, monkeypatch):
    asked = []
    recs = _recs((0.1, 0.4)) + [{**_recs((0.8,))[0], "score": 0.2}]
    monkeypatch.setattr(SamAdapter, "segment_images", lambda self, urls, concepts: asked.append(concepts) or recs)
    monkeypatch.setattr(SparkAdapter, "read_monitor", lambda self, url: MONITOR)
    out = live.read_photo(_keyed(tmp_path), "monitor", b"x", "a.png", "image/png")
    assert asked == [["digital display"]]
    assert [r["bbox"] is None for r in out["regions"]] == [False, False, True]


def test_read_photo_sam_fails_values_kept(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("no")

    monkeypatch.setattr(SamAdapter, "segment_images", boom)
    monkeypatch.setattr(SparkAdapter, "read_monitor", lambda self, url: MONITOR)
    out = live.read_photo(_keyed(tmp_path), "monitor", b"x", "a.png", "image/png")
    assert [r["bbox"] for r in out["regions"]] == [None, None, None] and out["calls"][0]["source"] == "failed"
    assert [r["value"] for r in out["regions"]] == ["118", "76", "80"]


def _obs_client(tmp_path):
    client = TestClient(create_app(_no_key(tmp_path)))
    eid = client.post("/journey/episodes", json={"label": "Synthetic demo, B"}).json()["id"]
    _to_ward(client, eid)
    order = _sign(client, eid, [DOSE, OBS]).json()["order_list"][0]
    view = _ack(client, eid, order["id"]).json()
    return client, eid, {t["kind"]: t["id"] for t in view["tasks"]}


def _proof(client, eid, task_id, name):
    return client.post(f"/journey/episodes/{eid}/photos", files={"file": (name, PNG, "image/png")},
                       data={"purpose": "proof", "by": NURSE, "task_id": task_id, "at_ms": "0"})


def _checked(client, eid):
    return [e for e in client.app.state.morning.events(eid) if e["event_type"] == "proof.checked"][-1]["payload"]


def test_proof_photo_saves_a_sidecar(tmp_path):
    client, eid, ids = _obs_client(tmp_path)
    assert _proof(client, eid, ids["obs"], "monitor-88-54.png").status_code == 200
    payload = _checked(client, eid)
    assert evidence.EVIDENCE_ID.fullmatch(payload["evidence_id"])
    assert [r["label"] for r in payload["regions"]] == ["SBP", "DBP", "HR"]
    got = client.get(f"/journey/episodes/{eid}/evidence/{payload['evidence_id']}").json()
    assert got["kind"] == "monitor" and got["media"] == "photos" and got["frames"] is None and got["handmade"] is True
    assert len(got["regions"]) == 3 and got["images"][0]["t"] is None and [c["model"] for c in got["calls"]] == ["sam", "spark"]
    shown = client.get(f"/journey/episodes/{eid}").json()["photos"][-1]["check"]
    assert shown["evidence_id"] == payload["evidence_id"] and len(shown["regions"]) == 3


def test_strip_proof_regions_carry_a_match(tmp_path):
    client, eid, ids = _obs_client(tmp_path)
    assert _proof(client, eid, ids["dose"], "strip-paracetamol.png").status_code == 200
    payload = _checked(client, eid)
    assert [(r["label"], r["match"]) for r in payload["regions"]] == [("Paracetamol 500 mg", "ok")]
    got = client.get(f"/journey/episodes/{eid}/evidence/{payload['evidence_id']}").json()
    assert got["kind"] == "strip"


def test_unread_photo_saves_no_sidecar(tmp_path):
    client, eid, ids = _obs_client(tmp_path)
    assert _proof(client, eid, ids["obs"], "IMG_0001.png").status_code == 200
    assert "evidence_id" not in _checked(client, eid)


def test_new_strings_have_no_advice():
    for r in pair_regions([B(0.1, 0.1)], monitor_values({"sbp": 1})):
        assert not ADVICE.search(r["label"])


def test_medicines_photo_saves_a_sidecar_and_ask_view_carries_the_regions(tmp_path):
    from tests.test_care_demo import _client
    from tests.test_p4_ask import _home, _patients
    from tests.test_p4_medicines import _post

    client = _client(tmp_path)
    kumar = _patients(client)["4"]
    _home(client, kumar)
    assert _post(client, kumar).status_code == 200
    read = client.get(f"/journey/episodes/{kumar}").json()["ask"]["medicines"][-1]
    assert [r["row"] for r in read["regions"]] == [0, 1, 2, 3] and len(read["rows"]) == 4
    got = client.get(f"/journey/episodes/{kumar}/evidence/{read['evidence_id']}").json()
    assert got["kind"] == "medicines" and got["images"][0]["photo_id"] == read["photo"]["id"] and len(got["regions"]) == 4


def _spark_down(monkeypatch):
    def boom(self, url):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(SparkAdapter, "read_monitor", boom)
    monkeypatch.setattr(SparkAdapter, "read_strips", boom)


def test_spark_failure_keeps_live_boxes_and_never_the_fixture(tmp_path, monkeypatch):
    # A file named like a fixture gets no prepared regions or values when Spark fails live (spec §4).
    monkeypatch.setattr(SamAdapter, "segment_images", lambda self, urls, concepts: _recs((0.1,)))
    _spark_down(monkeypatch)
    out = live.read_photo(_keyed(tmp_path), "monitor", b"x", "monitor-88-54.png", "image/png")
    assert out["source"] == "unavailable" and out["text"] is None and out["handmade"] is False
    assert [(r["bbox"] is not None, r["value"]) for r in out["regions"]] == [(True, None)]
    assert [(c["model"], c["source"]) for c in out["calls"]] == [("sam", "sam-3.1"), ("spark", "unavailable")]


def test_spark_failure_when_sam_also_failed(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("no")

    monkeypatch.setattr(SamAdapter, "segment_images", boom)
    _spark_down(monkeypatch)
    out = live.read_photo(_keyed(tmp_path), "strip", b"x", "meds-kumar.png", "image/png")
    assert out["regions"] == [] and out["handmade"] is False
    assert [(c["model"], c["source"]) for c in out["calls"]] == [("sam", "failed"), ("spark", "unavailable")]


def test_garbage_monitor_text_gives_no_regions(tmp_path, monkeypatch):
    monkeypatch.setattr(SamAdapter, "segment_images", lambda self, urls, concepts: [])
    monkeypatch.setattr(SparkAdapter, "read_monitor", lambda self, url: "not json")
    assert live.read_photo(_keyed(tmp_path), "monitor", b"x", "a.png", "image/png")["regions"] == []


def test_stale_strip_row_does_not_crash_the_proof_check(tmp_path, monkeypatch):
    from app.journey import media_api

    read = {"text": "", "source": "prepared", "calls": [], "raw": None, "handmade": True,
            "regions": [{"bbox": [0, 0, 1, 1], "label": "x", "value": "x", "row": 3}]}
    monkeypatch.setattr(live, "read_photo", lambda *a, **k: read)
    out = media_api._check_photo(_no_key(tmp_path), "e", "p", {"kind": "dose", "title": "Paracetamol"}, b"x", "a.png", "image/png", {})
    assert out["regions"][0]["match"] is None
