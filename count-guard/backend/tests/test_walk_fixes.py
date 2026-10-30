"""Bugs from the owner's live walk on 30 Oct: NOW on a shared clock time, orders acknowledged in clinic, surgeon theatre steps."""

from __future__ import annotations

from tests.test_care_demo import _client

DOCTOR = "Dr. A. Rao (synthetic)"
ITEMS = [{"kind": "obs", "text": "BP and pulse every 1 h", "every_h": 1, "mode": "tick", "proof": "none", "limits": {"sbp_min": 90}}]


def _seeded(tmp_path):
    client = _client(tmp_path)
    patients = client.post("/journey/demo/seed").json()["patients"]
    return client, {p["name"].split(",")[0]: p["id"] for p in patients}


def _view(client, eid):
    return client.get(f"/journey/episodes/{eid}").json()


def test_a_real_move_wins_now_over_the_seeded_admission_at_the_same_time(tmp_path):
    client, ids = _seeded(tmp_path)
    iyer = ids["S. Iyer (synthetic)"] if "S. Iyer (synthetic)" in ids else ids["S. Iyer"]
    body = {"to": "theatre", "by": DOCTOR, "at_ms": 0, "procedure": "hernia-repair"}
    assert client.post(f"/journey/episodes/{iyer}/state", json=body).status_code == 200
    now = _view(client, iyer)["now_next"]["now"]
    assert "theatre" in now
    assert "the day before" not in now


def test_orders_signed_in_clinic_cannot_be_acknowledged_until_admission(tmp_path):
    client, ids = _seeded(tmp_path)
    kumar = next(v for k, v in ids.items() if k.startswith("R. Kumar"))
    signed = client.post(f"/journey/episodes/{kumar}/orders/sign", json={"items": ITEMS, "by": DOCTOR, "at_ms": 0})
    assert signed.status_code == 200
    order_id = _view(client, kumar)["order_list"][0]["id"]
    early = client.post(f"/journey/episodes/{kumar}/orders/{order_id}/ack", json={"by": "Nurse Meena (synthetic)", "at_ms": 0})
    assert early.status_code == 409
    assert _view(client, kumar)["tasks"] == []
    client.post(f"/journey/episodes/{kumar}/state", json={"to": "admitting", "by": DOCTOR, "at_ms": 0, "reason": "Hernia repair"})
    later = client.post(f"/journey/episodes/{kumar}/orders/{order_id}/ack", json={"by": "Nurse Meena (synthetic)", "at_ms": 0})
    assert later.status_code == 200
    assert len(_view(client, kumar)["tasks"]) == 1
