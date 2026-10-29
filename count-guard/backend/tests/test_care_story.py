"""The demo video's whole story: three patients, three paths, every step by tap on the shared clock."""

from __future__ import annotations

from tests.test_care_demo import _client
from tests.test_flow_states import ADMIT_CHECKS, ADVICE, DISCHARGE_CHECKS

H = 3_600_000
M = 60_000
DOCTOR = "Dr. A. Rao (synthetic)"
NURSE = "Nurse Asha (synthetic)"
SCRUB = "Nurse Priya (synthetic)"
PARACETAMOL = {"kind": "dose", "text": "Paracetamol 1 g every 6 h", "name": "Paracetamol", "amount": "1 g", "every_h": 6}
OBS_HOURLY = {"kind": "obs", "text": "BP and pulse every 1 h", "every_h": 1, "limits": {"sbp_min": 90}}
SALINE = {"kind": "procedure", "text": "Saline 1 L over 2 h", "mode": "start_end"}
OBS_QUARTER = {"kind": "obs", "text": "BP and pulse every 15 min", "every_h": 0.25}
SUMMARY = "Recovered well. Home with the discharge card."


class Ward:
    """One patient's HTTP calls, recording every now/next line the screens would show."""

    def __init__(self, client, eid):
        self.client, self.eid, self.seen = client, eid, []

    def post(self, path, body):
        res = self.client.post(f"/journey/episodes/{self.eid}/{path}", json=body)
        assert res.status_code == 200, f"{path}: {res.text}"
        view = res.json()
        if "now_next" in view:
            self.seen.append(view["now_next"])
        return view

    def get(self):
        view = self.client.get(f"/journey/episodes/{self.eid}").json()
        self.seen.append(view["now_next"])
        return view

    def move(self, to, at, by=DOCTOR, **extra):
        return self.post("state", {"to": to, "by": by, "at_ms": at, **extra})

    def sign(self, items, at):
        return self.post("orders/sign", {"items": items, "by": DOCTOR, "at_ms": at})["order_list"][-1]["id"]

    def ack(self, order_id, at):
        return self.post(f"orders/{order_id}/ack", {"by": NURSE, "at_ms": at})

    def done(self, task_id, at, **extra):
        return self.post(f"tasks/{task_id}/done", {"by": NURSE, "via": "tap", "at_ms": at, **extra})

    def count(self, at, **body):
        return self.post("count", {"by": SCRUB, "at_ms": at, **body})

    def audit(self, kind):
        rows = self.client.get(f"/journey/episodes/{self.eid}/audit").json()["rows"]
        return [r for r in rows if r["type"] == kind]


def _wards(client):
    seeded = client.post("/journey/demo/seed").json()["patients"]
    return {p["bed"]: Ward(client, p["id"]) for p in seeded}


def _tasks(view, kind):
    return [t for t in view["tasks"] if t["kind"] == kind]


def _discharge(ward, sign_at, home_at):
    ward.post("discharge/sign", {"summary": SUMMARY, "by": DOCTOR, "at_ms": sign_at})
    return ward.move("home", home_at, by=NURSE, checklist=DISCHARGE_CHECKS)


def test_three_paths_by_tap(tmp_path):
    client = _client(tmp_path)
    wards = _wards(client)

    # Das: seen in clinic, visit closed.
    das = wards["9"]
    das.post("rx/demo", {"at_ms": 0})
    assert das.move("clinic_done", 10 * M)["state"] == "clinic_done"

    # Kumar: clinic, admission, orders, theatre with a corrected count, ward, discharge, home.
    kumar = wards["4"]
    kumar.post("rx/demo", {"at_ms": 0})
    assert kumar.move("admitting", 40 * M, reason="Hernia repair")["state"] == "admitting"
    assert kumar.move("ward", H, by=NURSE, checklist=ADMIT_CHECKS)["state"] == "ward"
    order = kumar.sign([PARACETAMOL, OBS_HOURLY], H + 10 * M)
    view = kumar.ack(order, H + 15 * M)
    assert len(view["tasks"]) == 2
    assert kumar.move("theatre", 2 * H, procedure="hernia-repair")["state"] == "theatre"
    kumar.post("surgery", {"step": "began", "by": SCRUB, "at_ms": 2 * H + 5 * M})
    kumar.count(2 * H + 20 * M, step="opened", quantity=20)
    view = kumar.count(3 * H + 30 * M, step="closing", returned=19)
    assert [n["kind"] for n in view["nudges"]] == ["count_open"]
    first = kumar.audit("count.closing")[0]["id"]
    kumar.count(3 * H + 35 * M, step="closing", returned=20, supersedes_id=first)
    kumar.post("surgery", {"step": "ended", "by": SCRUB, "at_ms": 3 * H + 40 * M})
    assert kumar.move("ward", 3 * H + 45 * M, by=NURSE, reason="")["state"] == "ward"
    paracetamol = _tasks(kumar.get(), "dose")[0]
    view = kumar.done(paracetamol["id"], 4 * H)
    assert any(e["type"] == "dose.given" for e in view["timeline"])
    assert _discharge(kumar, 30 * H, 31 * H)["state"] == "home"
    closings = kumar.audit("count.closing")
    struck = next(r for r in closings if r["id"] == first)
    assert len(closings) == 2 and struck["replaced_by"]

    # Iyer: already on the ward; a low reading, a saline drip, discharge.
    iyer = wards["7"]
    view = iyer.get()
    assert view["state"] == "ward"
    obs = _tasks(view, "obs")[0]
    view = iyer.done(obs["id"], H, values={"sbp": 82, "dbp": 50, "hr": 96})
    assert [n["kind"] for n in view["nudges"]] == ["obs_past_limit"]
    order = iyer.sign([SALINE, OBS_QUARTER], H + 5 * M)
    view = iyer.ack(order, H + 5 * M)
    drip = _tasks(view, "procedure")[0]
    assert iyer.post(f"tasks/{drip['id']}/begin", {"by": NURSE, "at_ms": H + 10 * M})["tasks"]
    view = iyer.done(drip["id"], 3 * H + 10 * M)
    assert next(t for t in view["tasks"] if t["id"] == drip["id"])["status"] == "done"
    assert _discharge(iyer, 26 * H, 27 * H)["state"] == "home"

    assert [w.get()["state"] for w in (das, kumar, iyer)] == ["clinic_done", "home", "home"]
    for ward in wards.values():
        for line in ward.seen:
            assert not ADVICE.search(f"{line['now']} {line['next']}"), line
