"""The owner gate, the pending store and the export (plan PQ-f, Task 9). Offline, temp DATA_DIR / DB_PATH.
Clinics and users come from test_users_routes: dr.rao is made the owner here, dr.iyer is not."""
import json
import multiprocessing
import os
from datetime import date
from contextlib import closing
from types import SimpleNamespace

from fastapi.testclient import TestClient

from doctor_dictation import policy
from doctor_dictation.api.app import create_app
from test_users_routes import H, _conn, _signed_in, world  # noqa: F401

URL = "/api/v1/owner/lists/medicine"


def post(c, op, key, data=None, kind="medicine"):
    return c.post(f"/api/v1/owner/lists/{kind}/changes", json={"op": op, "entry_key": key, "data": data or {}}, headers=H)


def test_is_owner_reads_the_env(monkeypatch):
    monkeypatch.delenv("OWNER_USERNAMES", raising=False)
    me = SimpleNamespace(username="Naren")
    assert policy.is_owner(me) is False
    monkeypatch.setenv("OWNER_USERNAMES", " Naren , x")
    assert policy.is_owner(me) is True and policy.is_owner(SimpleNamespace(username="x")) is True
    assert policy.is_owner(SimpleNamespace(username="y")) is False and policy.is_owner(None) is False
    monkeypatch.setenv("OWNER_USERNAMES", "")
    assert policy.is_owner(me) is False


def test_non_owner_and_single_mode_get_404(world, monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_USERNAMES", "dr.rao")
    with _signed_in("dr.iyer") as (iyer,):
        assert iyer.get(URL, headers=H).status_code == 404
        assert iyer.get(URL, headers=H).json() == {"error": "not found"}
        assert post(iyer, "edit", "paracetamol", {"safety": True}).status_code == 404
        assert iyer.get(URL + "/export", headers=H).status_code == 404
    monkeypatch.delenv("MULTI_CLINIC")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "single.db"))
    c = TestClient(create_app())
    assert c.get(URL).status_code == 404 and post(c, "drop", "x").status_code == 404


def test_owner_edit_with_safety_is_pending_and_exported(world, monkeypatch):
    monkeypatch.setenv("OWNER_USERNAMES", "dr.rao")
    with _signed_in("dr.rao") as (rao,):
        r = post(rao, "edit", "paracetamol", {"safety": True})
        assert r.status_code == 200, r.text
        got = rao.get(URL, headers=H).json()
        assert {i["entry_key"]: i["pending"] for i in got["items"]}["paracetamol"]["data"] == {"safety": True}
        e = rao.get(URL + "/export", headers=H)
        assert e.json() == {"kind": "medicine", "changes": [{"action": "edit", "entry_key": "paracetamol", "data": {"safety": True}}]}
        assert e.headers["content-disposition"] == f'attachment; filename="list-changes-medicine-{date.today().isoformat()}.json"'
        assert rao.get(URL + "/export", headers=H).json()["changes"]          # exporting does not clear
        with closing(_conn("rao")) as c:
            rows = c.execute("SELECT action, entity_id FROM audit_log WHERE action LIKE 'owner-list.%'").fetchall()
        assert [tuple(x) for x in rows] == [("owner-list.edit", "paracetamol")]


def test_add_of_a_shipped_key_is_409(world, monkeypatch):
    monkeypatch.setenv("OWNER_USERNAMES", "dr.rao")
    with _signed_in("dr.rao") as (rao,):
        r = post(rao, "add", "paracetamol", {"name": "Paracetamol", "generic": "Paracetamol"})
        assert r.status_code == 409
        assert post(rao, "edit", "no-such-key-zz", {"aliases": ["Zz"]}).status_code == 404


def test_add_of_a_new_key_lists_under_pending(world, monkeypatch):
    monkeypatch.setenv("OWNER_USERNAMES", "dr.rao")
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "add", "zerodol-p", {"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}).status_code == 200
        assert [r["entry_key"] for r in rao.get(URL, headers=H).json()["pending"]] == ["zerodol-p"]


def test_edit_may_not_change_the_generic(world, monkeypatch):
    monkeypatch.setenv("OWNER_USERNAMES", "dr.rao")
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "edit", "paracetamol", {"generic": "Other"}).status_code == 400
        assert post(rao, "edit", "paracetamol", {"name": "Other"}).status_code == 400
        assert post(rao, "edit", "paracetamol", {"safety": "yes"}).status_code == 400
        assert rao.post(f"{URL}/changes", json={"op": "nope", "entry_key": "x"}, headers=H).status_code == 422
        assert rao.post(f"{URL}/changes", json={"op": "drop", "entry_key": "x" * 61}, headers=H).status_code == 422


def test_drop_removes_the_change(world, monkeypatch):
    monkeypatch.setenv("OWNER_USERNAMES", "dr.rao")
    with _signed_in("dr.rao") as (rao,):
        post(rao, "edit", "paracetamol", {"safety": True})
        assert post(rao, "drop", "paracetamol").status_code == 200
        with closing(_conn("rao")) as c:
            detail = c.execute("SELECT detail FROM audit_log WHERE action = 'owner-list.drop'").fetchone()[0]
        assert json.loads(detail) == {"before": {"action": "edit", "entry_key": "paracetamol", "data": {"safety": True}},
                                      "after": None}
        assert rao.get(URL + "/export", headers=H).json()["changes"] == []
        assert post(rao, "drop", "paracetamol").status_code == 404


def test_pending_survives_a_new_app(world, monkeypatch):
    monkeypatch.setenv("OWNER_USERNAMES", "dr.rao")
    with _signed_in("dr.rao") as (rao,):
        post(rao, "edit", "paracetamol", {"safety": True})
    with _signed_in("dr.rao") as (rao2,):
        assert len(rao2.get(URL + "/export", headers=H).json()["changes"]) == 1


def test_pending_write_is_atomic(world, monkeypatch):
    monkeypatch.setenv("OWNER_USERNAMES", "dr.rao")
    with _signed_in("dr.rao") as (rao,):
        post(rao, "edit", "paracetamol", {"safety": True})
        from doctor_dictation.api import owner_lists
        path = owner_lists.pending_path()
        before = path.read_text(encoding="utf-8")
        with monkeypatch.context() as m:
            m.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
            assert post(rao, "edit", "paracetamol", {"aliases": ["Pcm"]}).status_code == 503
        assert path.read_text(encoding="utf-8") == before and not list(path.parent.glob("*.tmp"))


def test_a_malformed_file_is_empty_not_a_500(world, monkeypatch):
    monkeypatch.setenv("OWNER_USERNAMES", "dr.rao")
    from doctor_dictation.api import owner_lists
    with _signed_in("dr.rao") as (rao,):
        owner_lists.pending_path().parent.mkdir(parents=True, exist_ok=True)
        for text in ("{not json", "[]", '{"medicine": 5}'):
            owner_lists.pending_path().write_text(text, encoding="utf-8")
            assert rao.get(URL + "/export", headers=H).json()["changes"] == []
        assert post(rao, "edit", "paracetamol", {"safety": True}).status_code == 200


def test_me_says_is_owner(world, monkeypatch):
    monkeypatch.setenv("OWNER_USERNAMES", "dr.rao")
    with _signed_in("dr.rao", "dr.iyer") as (rao, iyer):
        assert rao.get("/api/v1/auth/me", headers=H).json()["is_owner"] is True
        assert iyer.get("/api/v1/auth/me", headers=H).json()["is_owner"] is False


def test_an_unreadable_file_is_503_on_post_and_left_untouched(world, monkeypatch):
    monkeypatch.setenv("OWNER_USERNAMES", "dr.rao")
    from doctor_dictation.api import owner_lists
    with _signed_in("dr.rao") as (rao,):
        owner_lists.pending_path().parent.mkdir(parents=True, exist_ok=True)
        for text in ("{not json", "[]"):
            owner_lists.pending_path().write_text(text, encoding="utf-8")
            assert post(rao, "edit", "paracetamol", {"safety": True}).status_code == 503
            assert post(rao, "drop", "paracetamol").status_code == 503
            assert owner_lists.pending_path().read_text(encoding="utf-8") == text
            assert rao.get(URL, headers=H).status_code == 200


def _add_many(tag, barrier, n=8):
    from doctor_dictation.api import owner_lists
    from doctor_dictation.core import formulary
    barrier.wait()
    for i in range(n):
        name = f"Zeta{tag}{i}"
        owner_lists._apply("medicine", owner_lists.OwnerChange(
            op="add", entry_key=formulary.key(name), data={"name": name, "generic": "Paracetamol"}))


def test_two_processes_adding_different_keys_both_survive(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from doctor_dictation.api import owner_lists
    ctx = multiprocessing.get_context("fork")
    barrier = ctx.Barrier(2)
    procs = [ctx.Process(target=_add_many, args=(t, barrier)) for t in ("a", "b")]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    assert [p.exitcode for p in procs] == [0, 0]
    with owner_lists._LOCK:
        keys = {r["entry_key"] for r in owner_lists._read()["medicine"]}
    assert len(keys) == 16
