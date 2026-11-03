"""Photo proof verdicts (spec §6.6, §6.7, U9): a not-accepted or not-checked photo keeps its item open."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from app.adapters.spark import SparkAdapter
from app.journey import check_gate, expected, live, switches, verdict
from tests.test_flow_states import ADMIT_CHECKS, DISCHARGE_CHECKS, _move, _new, _saved_count, _surgery, _to_ward, _view
from tests.test_flow_tasks import DOSE, NURSE, _ack, _done, _sign, _url
from tests.test_p2_live import _keyed, _no_key

PNG = b"\x89PNG\r\n\x1a\nfake"
MEDIA = Path(__file__).resolve().parents[2] / "eval" / "media"
WRONG = MEDIA / "wrong-photo" / "wrong-photo-bed-rail-synthetic.png"
SAYS_NO = {"verdict": "not_accepted", "why": "No wristband visible"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _live(client, monkeypatch, reply=None, error=None):
    """Turn PROOF_LIVE on with a fake Spark: it answers `reply` or raises `error`."""
    client.app.state.settings = replace(client.app.state.settings, meta_api_key="test-key")

    def answer(self, raw, content_type, expect):
        if error:
            raise error
        return dict(reply)

    monkeypatch.setattr(SparkAdapter, "check_photo", answer)


def _photo(client, eid, item, data=PNG, name="any.png"):
    form = {"by": NURSE, "at_ms": 0}
    return client.post(_url(eid, f"checks/{item}/photo"), data=form, files={"file": (name, data, "image/png")})


def _override(client, eid, item, reason="Band checked by hand", by=NURSE):
    return client.post(_url(eid, f"checks/{item}/override"), json={"reason": reason, "by": by, "at_ms": 0})


def _admitting(tmp_path):
    client, eid = _new(tmp_path)
    assert _move(client, eid, "admitting", reason="Hernia repair").status_code == 200
    return client, eid


def _row(view, item):
    return next(r for r in view["photo_checks"] if r["item"] == item)


def test_expected_lines_cover_every_check():
    keys = {f"admission:{k}" for k in ADMIT_CHECKS} | {f"discharge:{k}" for k in DISCHARGE_CHECKS}
    assert keys <= set(expected.EXPECT)
    assert any(k.startswith("theatre:") for k in expected.EXPECT)
    assert {f"task:{k}" for k in ("dose", "obs", "procedure", "check", "other")} <= set(expected.EXPECT)
    assert all(line.strip() for line in expected.EXPECT.values())


def test_not_accepted_keeps_admission_open(tmp_path, monkeypatch):
    client, eid = _admitting(tmp_path)
    _live(client, monkeypatch, SAYS_NO)
    assert _photo(client, eid, "admission:band").status_code == 200
    r = _move(client, eid, "ward", checklist=ADMIT_CHECKS)
    assert r.status_code == 409
    assert r.json()["error"] == "photo checks open"
    assert r.json()["items"] == ["wristband"]
    assert _view(client, eid)["state"] == "admitting"


def test_move_without_photos_still_allowed(tmp_path):
    client, eid = _admitting(tmp_path)
    assert _move(client, eid, "ward", checklist=ADMIT_CHECKS).status_code == 200


def test_item_without_photo_shows_no_photo(tmp_path):
    client, eid = _admitting(tmp_path)
    view = _view(client, eid)
    row = _row(view, "admission:band")
    assert (row["state"], row["text"], row["label"]) == ("none", "No photo", "wristband")
    assert {r["item"] for r in view["photo_checks"]} >= {f"admission:{k}" for k in ADMIT_CHECKS}


def test_unavailable_copy(tmp_path, monkeypatch):
    client, eid = _admitting(tmp_path)
    _live(client, monkeypatch, error=httpx.ConnectError("down"))
    row = _row(_photo(client, eid, "admission:consent").json(), "admission:consent")
    assert row["text"] == "Not checked — model unavailable"
    assert row["state"] == "not_checked" and row["source"] == "unavailable"


def test_override_with_reason_opens_the_move(tmp_path, monkeypatch):
    client, eid = _admitting(tmp_path)
    _live(client, monkeypatch, SAYS_NO)
    _photo(client, eid, "admission:band")
    r = _override(client, eid, "admission:band")
    assert r.status_code == 200
    row = _row(r.json(), "admission:band")
    assert row["state"] == "overridden" and row["reason"] == "Band checked by hand"
    assert _move(client, eid, "ward", checklist=ADMIT_CHECKS).status_code == 200
    plain = [line["plain"] for line in _view(client, eid)["timeline"]]
    assert any("Photo does not match — No wristband visible" in p for p in plain)
    assert any("Band checked by hand" in p and "wristband" in p for p in plain)


def test_override_without_reason_is_422(tmp_path, monkeypatch):
    client, eid = _admitting(tmp_path)
    _live(client, monkeypatch, SAYS_NO)
    _photo(client, eid, "admission:band")
    assert _override(client, eid, "admission:band", reason="").status_code == 422
    assert _override(client, eid, "admission:band", reason="   ").status_code == 422
    assert _move(client, eid, "ward", checklist=ADMIT_CHECKS).status_code == 409


def test_override_with_a_blank_name_is_422(tmp_path, monkeypatch):
    client, eid = _admitting(tmp_path)
    _live(client, monkeypatch, SAYS_NO)
    _photo(client, eid, "admission:band")
    assert _override(client, eid, "admission:band", by="   ").status_code == 422
    r = _override(client, eid, "admission:band", by="  Nurse Meena (synthetic) ")
    assert _row(r.json(), "admission:band")["overridden_by"] == "Nurse Meena (synthetic)"


def test_prepared_verdict_on_the_timeline_says_prepared(tmp_path):
    client, eid = _admitting(tmp_path)
    view = _photo(client, eid, "admission:band").json()
    lines = [t for t in view["timeline"] if t["type"] == "check.photo"]
    assert [t["plain"] for t in lines] == [
        "Photo of the wristband: Photo matches — The photo shows " + expected.EXPECT["admission:band"] + ". · Prepared"]
    assert lines[0]["patient"] == ""  # staff only


def test_live_verdict_on_the_timeline_has_no_prepared_label(tmp_path, monkeypatch):
    client, eid = _admitting(tmp_path)
    _live(client, monkeypatch, SAYS_NO)
    view = _photo(client, eid, "admission:band").json()
    assert [t["plain"] for t in view["timeline"] if t["type"] == "check.photo"] == [
        "Photo of the wristband: Photo does not match — No wristband visible"]


def test_override_of_a_closed_item_is_409(tmp_path):
    client, eid = _admitting(tmp_path)
    assert _override(client, eid, "admission:band").status_code == 409


def test_retake_that_is_accepted_closes_the_item(tmp_path, monkeypatch):
    client, eid = _admitting(tmp_path)
    _live(client, monkeypatch, SAYS_NO)
    _photo(client, eid, "admission:band")
    _live(client, monkeypatch, {"verdict": "accepted", "why": "Wristband with a name"})
    assert _row(_photo(client, eid, "admission:band").json(), "admission:band")["state"] == "accepted"
    assert _move(client, eid, "ward", checklist=ADMIT_CHECKS).status_code == 200


def test_unavailable_model_is_not_checked_and_open(tmp_path, monkeypatch):
    client, eid = _admitting(tmp_path)
    _live(client, monkeypatch, error=httpx.ConnectError("down"))
    _photo(client, eid, "admission:band")
    r = _move(client, eid, "ward", checklist=ADMIT_CHECKS)
    assert r.status_code == 409 and r.json()["items"] == ["wristband"]


def test_a_reply_that_does_not_parse_is_not_checked(tmp_path, monkeypatch):
    settings = _keyed(tmp_path)
    monkeypatch.setattr(SparkAdapter, "_ask", lambda self, prompt, image=None, **k: "I think so")
    got = verdict.check(settings, item="admission:band", raw=PNG, content_type="image/png")
    assert got["verdict"] == "not_checked" and got["source"] == "unavailable"
    assert got["why"] == switches.NOT_CHECKED


def test_live_reply_is_parsed(tmp_path, monkeypatch):
    settings = _keyed(tmp_path)
    reply = '```json\n{"verdict": "not_accepted", "why": "A bed rail, no wristband."}\n```'
    monkeypatch.setattr(SparkAdapter, "_ask", lambda self, prompt, image=None, **k: reply)
    got = verdict.check(settings, item="admission:band", raw=PNG, content_type="image/png")
    assert (got["verdict"], got["why"], got["source"]) == ("not_accepted", "A bed rail, no wristband.", "live")


def test_prepared_verdict_when_switch_off_is_labelled(tmp_path, monkeypatch):
    def called(*a, **k):
        raise AssertionError("the live model was called")

    monkeypatch.setattr(SparkAdapter, "check_photo", called)
    for settings in (_no_key(tmp_path), replace(_keyed(tmp_path), proof_live=False)):
        got = verdict.check(settings, item="admission:band", raw=PNG, content_type="image/png")
        assert got["source"] == "prepared" and got["verdict"] == "accepted" and got["why"]


def test_prepared_wrong_photo_is_chosen_by_content_not_name(tmp_path):
    raw = WRONG.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == verdict.WRONG_PHOTO_SHA256
    got = verdict.check(_no_key(tmp_path), item="admission:band", raw=raw, content_type="image/png")
    assert (got["verdict"], got["source"]) == ("not_accepted", "prepared")
    client, eid = _admitting(tmp_path)
    # The file name says nothing: the same bytes under a good name are still not accepted.
    row = _row(_photo(client, eid, "admission:band", data=raw, name="wristband-synthetic.png").json(), "admission:band")
    assert row["state"] == "not_accepted"


def test_photo_for_a_check_outside_its_state_is_409(tmp_path):
    client, eid = _new(tmp_path)
    assert _photo(client, eid, "admission:band").status_code == 409
    assert _photo(client, eid, "nothing:here").status_code == 404


def test_theatre_proof_never_blocks_surgery_end(tmp_path, monkeypatch):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    assert _move(client, eid, "theatre", procedure="hernia-repair").status_code == 200
    _live(client, monkeypatch, {"verdict": "not_accepted", "why": "Swabs overlap"})
    assert _photo(client, eid, "theatre:swab_tray").status_code == 200
    assert verdict.item_open(client.app.state.morning.events(eid), "theatre:swab_tray")
    assert _surgery(client, eid, "began").status_code == 200
    _saved_count(client, eid)
    assert _surgery(client, eid, "ended").status_code == 200
    assert _move(client, eid, "ward").status_code == 200


def _dose_task(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    order = _sign(client, eid, [DOSE]).json()["order_list"][0]
    task = _ack(client, eid, order["id"]).json()["tasks"][0]
    return client, eid, task


def _task_photo(client, eid, task_id, monkeypatch):
    """A proof photo through the task route. The strip read is stubbed: only the verdict is under test here."""
    monkeypatch.setattr(live, "read_photo", lambda *a, **k: {"text": None, "source": "none", "regions": [], "calls": [],
                                                             "raw": None, "handmade": False})
    form = {"purpose": "proof", "by": NURSE, "at_ms": 0, "task_id": task_id}
    return client.post(_url(eid, "photos"), data=form, files={"file": ("x.png", PNG, "image/png")})


def test_task_done_refused_while_proof_not_accepted(tmp_path, monkeypatch):
    client, eid, task = _dose_task(tmp_path)
    _live(client, monkeypatch, {"verdict": "not_accepted", "why": "No strip in view"})
    photo = _task_photo(client, eid, task["id"], monkeypatch).json()["photos"][-1]
    r = _done(client, eid, task["id"], proof_id=photo["id"])
    assert r.status_code == 409
    assert _row(_view(client, eid), f"task:{task['id']}")["state"] == "not_accepted"


def test_task_done_refused_while_not_checked(tmp_path, monkeypatch):
    client, eid, task = _dose_task(tmp_path)
    _live(client, monkeypatch, error=httpx.ConnectError("down"))
    _task_photo(client, eid, task["id"], monkeypatch)
    assert _done(client, eid, task["id"]).status_code == 409


def test_task_done_refused_while_not_checked_allowed_after_override(tmp_path, monkeypatch):
    client, eid, task = _dose_task(tmp_path)
    _live(client, monkeypatch, error=httpx.ConnectError("down"))
    _task_photo(client, eid, task["id"], monkeypatch)
    assert _override(client, eid, f"task:{task['id']}", reason="Strip read at the bedside").status_code == 200
    assert _done(client, eid, task["id"]).status_code == 200


def test_task_without_photo_can_be_done(tmp_path):
    client, eid, task = _dose_task(tmp_path)
    assert _done(client, eid, task["id"]).status_code == 200


def test_missing_checks_is_only_for_the_two_gated_moves(tmp_path, monkeypatch):
    client, eid = _admitting(tmp_path)
    _live(client, monkeypatch, SAYS_NO)
    _photo(client, eid, "admission:band")
    events = client.app.state.morning.events(eid)
    assert check_gate.missing_checks(events, "ward") == ["admission:band"]
    assert check_gate.missing_checks(events, "theatre") == []
    assert check_gate.missing_checks(events, "home") == []


def test_discharge_photo_gate(tmp_path, monkeypatch):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    signed = client.post(_url(eid, "discharge/sign"), json={"summary": "Recovered.", "by": "Dr. A. Rao (synthetic)", "at_ms": 0})
    assert signed.status_code == 200 and signed.json()["state"] == "discharging"
    _live(client, monkeypatch, {"verdict": "not_accepted", "why": "No labels on the bag"})
    _photo(client, eid, "discharge:medicines_handed")
    r = _move(client, eid, "home", checklist=DISCHARGE_CHECKS)
    assert r.status_code == 409 and r.json()["items"] == ["medicines handed over"]
    assert "medicines handed over" in r.json()["detail"]


def test_staff_copy_has_no_snake_case_or_model_names():
    for line in list(expected.EXPECT.values()) + [verdict.TASK_OPEN, switches.NOT_CHECKED]:
        assert "_" not in line and "Spark" not in line and "Muse" not in line
