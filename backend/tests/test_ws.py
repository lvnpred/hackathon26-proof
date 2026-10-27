"""Live socket: ready banner, state after each message, refusals and errors."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from test_api import client

# Three side-by-side strips, normalized 0-1. The socket renders them on its default 640x360 frame.
_ZONES = {
    "zones": [
        {"name": "tray", "polygon": [[0, 0], [0.333, 0], [0.333, 1], [0, 1]]},
        {"name": "field", "polygon": [[0.333, 0], [0.666, 0], [0.666, 1], [0.333, 1]]},
        {"name": "bucket", "polygon": [[0.666, 0], [1, 0], [1, 1], [0.666, 1]]},
    ]
}


def _case(api: TestClient) -> str:
    created = api.post("/cases", json={"label": "Socket case", "item_types": ["lap sponge"]})
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_ws_ready_then_state(tmp_path):
    api = client(tmp_path)
    case_id = _case(api)
    assert api.post(f"/cases/{case_id}/zones", json=_ZONES).status_code == 200
    with api.websocket_connect(f"/cases/{case_id}/stream") as socket:
        ready = socket.receive_json()
        assert ready["type"] == "ready"
        assert ready["banner"] == "Research demo. Not for clinical use."
        assert ready["perception"] == "scripted"

        socket.send_json({"type": "utterance", "text": "Adding 2 lap sponges", "media_ts_ms": 1000})
        state = socket.receive_json()
        assert state["type"] == "state"
        assert any("lap sponges" in row["text"] for row in state["transcript"])

        detections = [
            {"track_id": "a", "label": "lap sponge", "bbox": [0.03, 0.05, 0.125, 0.22], "score": 0.9},
            {"track_id": "b", "label": "lap sponge", "bbox": [0.155, 0.05, 0.125, 0.22], "score": 0.9},
        ]
        socket.send_json({"type": "detections", "detections": detections, "media_ts_ms": 2000})
        state = socket.receive_json()
        assert state["type"] == "state"
        rows = {row["item_type"]: row for row in state["ledger"]}
        assert rows["lap sponge"]["opened"] == 2
        assert rows["lap sponge"]["tray"] == 2


def test_ws_unknown_case_is_refused(tmp_path):
    api = client(tmp_path)
    with pytest.raises(WebSocketDisconnect) as refused:
        with api.websocket_connect("/cases/no-such-case/stream") as socket:
            socket.receive_json()
    assert refused.value.code == 4404


def test_ws_bad_json_sends_error(tmp_path):
    api = client(tmp_path)
    case_id = _case(api)
    with api.websocket_connect(f"/cases/{case_id}/stream") as socket:
        assert socket.receive_json()["type"] == "ready"
        socket.send_text("{not json")
        error = socket.receive_json()
        assert error["type"] == "error"
        assert error["message"]
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 1011
    # The server is still serving after the bad message.
    assert api.get("/health").status_code == 200
