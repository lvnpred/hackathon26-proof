"""The demo video's whole story, played through the routes the care screens call."""

from __future__ import annotations

from tests.test_care_demo import _client

H = 3_600_000
M = 60_000
DOCTOR, SCRUB, WARD, NIGHT = "Dr. A. Rao", "Nurse Priya", "Nurse Meena", "Nurse Kavya"
ORDERS = {
    "doses": [{"name": "Paracetamol", "amount": "1 g IV", "every_h": 6}],
    "obs_every_h": 1,
    "limits": {"sbp_min": 90},
    "by": DOCTOR,
}


def _open(view, kind):
    return [n for n in view["nudges"] if n["kind"] == kind]


def test_care_story(tmp_path):
    client = _client(tmp_path)
    seeded = client.post("/journey/demo/seed").json()["patients"]
    eid = next(p["id"] for p in seeded if p["bed"] == "4")
    base = f"/journey/episodes/{eid}"

    def post(path, body):
        res = client.post(f"{base}{path}", json=body)
        assert res.status_code == 200, res.text
        return res.json()

    def seen_ok(view, kind, to, by, at):
        """The nudge is open with the right recipient, then leaves the queue once seen."""
        found = _open(view, kind)
        assert found, f"{kind} not raised; open: {[n['kind'] for n in view['nudges']]}"
        nudge = found[0]
        assert nudge["to"] == to
        after = post(f"/nudges/{nudge['id']}/seen", {"by": by, "note": "Answered.", "at_ms": at})
        assert nudge["id"] not in {n["id"] for n in after["nudges"]}
        return after

    def nurse_open(view):
        return [n for n in view["nudges"] if n["to"] == "nurse"]

    # Clinic
    post("/rx/demo", {"at_ms": 0})

    # Admission (Day 1 07:00): the doctor sets the ward orders
    view = post("/orders", {**ORDERS, "at_ms": 22 * H})
    assert view["orders"]["limits"]["sbp_min"] == 90

    # Strips: the patient types amlodipine 10 mg
    view = post("/strips", {"strips": [{"name": "amlodipine", "strength": "10 mg"}], "at_ms": 10 * H})
    view = seen_ok(view, "strip_strength_differs", "patient", "patient", 10 * H + M)

    # Theatre: pack opened 20, closing 19, then corrected to 20
    post("/count", {"step": "opened", "quantity": 20, "by": SCRUB, "at_ms": 24 * H})
    view = post("/count", {"step": "closing", "returned": 19, "by": SCRUB, "at_ms": 24 * H + 50 * M})
    closing_id = next(
        r["id"] for r in client.get(f"{base}/audit").json()["rows"] if r["type"] == "count.closing"
    )
    view = seen_ok(view, "count_open", "nurse", SCRUB, 24 * H + 52 * M)
    post("/count", {"step": "closing", "returned": 20, "by": SCRUB, "at_ms": 24 * H + 54 * M,
                    "supersedes_id": closing_id})
    rows = [r for r in client.get(f"{base}/audit").json()["rows"] if r["type"] == "count.closing"]
    assert len(rows) == 2
    old = next(r for r in rows if r["id"] == closing_id)
    assert old["replaced_by"], "the 19-of-20 closing is shown as replaced"
    assert next(r for r in rows if r is not old)["replaced_by"] in (None, "")

    # Ward
    post("/obs", {"sbp": 128, "dbp": 80, "hr": 84, "by": WARD, "at_ms": 26 * H})
    view = post("/dose", {"name": "Paracetamol", "amount": "1 g IV", "by": WARD, "at_ms": 26 * H})
    view = post("/obs", {"sbp": 86, "dbp": 54, "hr": 96, "by": WARD, "at_ms": 31 * H + 10 * M})
    view = seen_ok(view, "obs_past_limit", "nurse", WARD, 31 * H + 15 * M)
    assert not _open(view, "dose_overdue"), "no dose is overdue before the 18:30 check"
    view = post("/tick", {"at_ms": 33 * H + 30 * M})
    assert _open(view, "dose_overdue")[0]["when"] == "Day 1 18:30"
    view = seen_ok(view, "dose_overdue", "nurse", WARD, 33 * H + 31 * M)
    post("/dose", {"name": "Paracetamol", "amount": "1 g IV", "by": WARD, "at_ms": 33 * H + 35 * M})
    drafted = post("/handover", {"from_nurse": WARD, "to_nurse": NIGHT, "use_model": False,
                                 "at_ms": 34 * H})
    assert drafted["handover"]["accepted_by"] is None
    view = post(f"/handover/{drafted['handover']['id']}/accept", {"by": NIGHT, "at_ms": 34 * H + 5 * M})
    assert view["handover"]["accepted_by"] == NIGHT

    # Home
    view = post("/discharge-card", {"by": DOCTOR, "at_ms": 35 * H})
    assert view["card"] is not None
    post("/tick", {"at_ms": 48 * H})
    view = post("/checkin", {"day": 2, "feels": "Sore and warm", "signs": ["Fever above 38 °C"],
                             "at_ms": 48 * H})
    view = seen_ok(view, "warning_sign_ticked", "nurse", WARD, 48 * H + M)
    view = post("/help", {"says": "The dressing is wet.", "at_ms": 48 * H + 2 * M})
    view = seen_ok(view, "help_requested", "nurse", WARD, 48 * H + 3 * M)

    left = [n["kind"] for n in nurse_open(view)]
    # obs_overdue is the real rule firing after the time jumps; the story leaves it open on purpose.
    assert not {"count_open", "obs_past_limit", "dose_overdue", "warning_sign_ticked", "help_requested"} & set(left)
