import asyncio
import json

import pytest

from doctor_dictation.config import get_settings, override_settings
from doctor_dictation.db import templates as tdb
from doctor_dictation.templates import service
from template_fixtures import GOOD_LAYOUT, make_jpeg, tclient, tconn  # noqa: F401

URL = "/api/v1/templates"


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(GOOD_LAYOUT))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)


def _draft(conn):
    return asyncio.run(service.upload(conn, make_jpeg(), get_settings(), actor=None))["id"]


def _accepted(conn):
    tid = _draft(conn)
    service.accept(conn, tid)
    return tid


def _audit(conn):
    return [(r["action"], r["actor"], r["entity_id"])
            for r in conn.execute("SELECT action, actor, entity_id FROM audit_log ORDER BY id")]


def test_deactivate_archives_the_active_template_and_audits(tconn):
    tid = _accepted(tconn)
    assert service.deactivate(tconn, actor="demo") is True
    assert service.get_active(tconn) is None
    assert tdb.get_template(tconn, tid)["status"] == "archived"
    assert ("template_deactivate", "demo", str(tid)) in _audit(tconn)


def test_deactivate_without_an_active_template_is_false_and_writes_no_audit(tconn):  # Review Focus #1
    before = _audit(tconn)
    assert service.deactivate(tconn) is False
    assert _audit(tconn) == before


def test_deactivate_leaves_a_pending_draft_alone(tconn):  # Review Focus #2
    _accepted(tconn)
    draft = _draft(tconn)
    service.deactivate(tconn)
    assert tdb.get_template(tconn, draft)["status"] == "draft"


def test_saves_use_the_builtin_layout_after_deactivate(tconn):  # Review Focus #3
    _accepted(tconn)
    assert service.active_layout_for_save(tconn)[0] is not None
    service.deactivate(tconn)
    assert service.active_layout_for_save(tconn) == (None, None)


def test_route_deactivate_then_no_active_template(tclient):
    tid = tclient.post(URL, files={"image": ("p.jpg", make_jpeg(), "image/jpeg")}).json()["id"]
    assert tclient.post(f"{URL}/{tid}/accept").status_code == 200
    assert tclient.get(URL + "/active").status_code == 200
    r = tclient.post(URL + "/deactivate")
    assert r.status_code == 200 and r.json() == {"deactivated": True}
    assert tclient.get(URL + "/active").status_code == 404


def test_route_deactivate_twice_is_idempotent(tclient):
    assert tclient.post(URL + "/deactivate").json() == {"deactivated": False}
    assert tclient.post(URL + "/deactivate").status_code == 200
