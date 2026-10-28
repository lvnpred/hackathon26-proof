"""Plan FB-D Task 5: private download links across two clinics (slug in the path, cookies ignored, revoke rules)."""
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from doctor_dictation.api import share_public
from doctor_dictation.directory import open_directory
from doctor_dictation.scope import current_scope
from isolation_fixtures import (A, B, H, a_only_id, fingerprint, opened_files, owner_refusal, save, save_body, sql,
                                world)  # noqa: F401

CAPTION = "Scan to download · valid until"


def _in(slug, path):
    return str(Path("clinics") / slug) in path


def _set_status(slug, status):
    with closing(open_directory()) as d:
        d.execute("UPDATE clinics SET status = ? WHERE slug = ?", (status, slug))
        d.commit()


def _token(encounter_id):
    return sql(A, "SELECT token FROM share_links WHERE encounter_id = ?", encounter_id)[0][0]


def test_a_link_opens_only_in_its_own_clinic_and_ignores_any_cookie(world, monkeypatch):
    j = save(world.rao, "Asha Verma")
    tok = _token(j["encounter_id"])
    with TestClient(world.app) as anon:
        r = anon.get(f"/s/{A}/{tok}")
    assert r.status_code == 200
    assert "Asha Verma" in r.text and CAPTION in r.text
    before = fingerprint(B)
    r_iyer = world.iyer.get(f"/s/{A}/{tok}")                   # signed in to clinic B: the cookie is neither needed nor used
    assert r_iyer.status_code == 200 and r_iyer.content == r.content
    expired = set()
    for slug in (B, "nope", "a", "RAO"):
        miss = world.iyer.get(f"/s/{slug}/{tok}")
        assert miss.status_code == 404 and "This link has expired" in miss.text, slug
        expired.add(miss.text)
    assert len(expired) == 1
    assert not (world.root / "clinics" / "nope").exists()
    with opened_files(monkeypatch) as seen:
        assert world.iyer.get(f"/s/{A}/{tok}").status_code == 200
        assert world.iyer.get(f"/s/nope/{tok}").status_code == 404
    assert [p for _, p in seen if _in(A, p)], seen                       # positive control: the spy sees clinic files
    assert not [p for _, p in seen if _in(B, p)], seen
    with opened_files(monkeypatch) as seen:                              # the direction that matters
        assert world.rao.get(f"/s/{B}/{tok}").status_code == 404
    assert not [p for _, p in seen if _in(A, p)], seen
    assert fingerprint(B) == before
    _set_status(A, "disabled")
    try:
        with opened_files(monkeypatch) as seen:
            off = world.iyer.get(f"/s/{A}/{tok}")
        assert off.status_code == 404 and "This link has expired" in off.text
        assert not [p for _, p in seen if _in(A, p)], seen
    finally:
        _set_status(A, "active")
    assert world.iyer.get(f"/s/{A}/{tok}").status_code == 200
    world.app.state.failed_clinics = frozenset({A})
    try:
        assert world.iyer.get(f"/s/{A}/{tok}").status_code == 404
    finally:
        world.app.state.failed_clinics = frozenset()
    assert world.iyer.get(f"/s/{A}/{tok}").status_code == 200


def test_only_the_author_or_the_clinic_admin_may_revoke_and_a_re_save_issues_a_new_link(world):
    j = save(world.rao, "Asha Verma")
    doc, old = j["document_id"], _token(j["encounter_id"])
    denied = world.mehta.post(f"/api/v1/documents/{doc}/share/revoke", headers=H)
    assert denied.status_code == 403 and denied.json() == owner_refusal("Dr. A. Rao")
    foreign = a_only_id("documents")
    assert world.rao.get(f"/api/v1/documents/{foreign}/share").status_code == 200       # control: the same id answers in its own clinic
    assert world.iyer.get(f"/api/v1/documents/{foreign}/share").status_code == 404
    assert world.iyer.post(f"/api/v1/documents/{foreign}/share/revoke", headers=H).status_code == 404
    assert world.iyer.post(f"/api/v1/documents/{doc}/share/revoke", headers=H).status_code == 404
    assert world.iyer.get(f"/s/{A}/{old}").status_code == 200       # still live after the refused attempts
    assert world.rao_admin.post(f"/api/v1/documents/{doc}/share/revoke", headers=H).json() == {"revoked": True}
    assert world.iyer.get(f"/s/{A}/{old}").status_code == 404
    again = world.rao.post("/api/v1/documents", json=save_body("Asha Verma", document_id=doc), headers=H)
    assert again.status_code == 200, again.text
    new = _token(j["encounter_id"])
    assert new != old
    assert world.iyer.get(f"/s/{A}/{new}").status_code == 200
    assert world.iyer.get(f"/s/{A}/{old}").status_code == 404


def test_a_share_path_passes_the_session_middleware_without_a_scope(world, monkeypatch):
    tok = _token(save(world.rao, "Asha Verma")["encounter_id"])
    seen = {}
    real_find, real_open = share_public.sdb.find_by_token, share_public._clinic_open

    def spy_open(request, slug):
        seen["identity"] = getattr(request.state, "identity", None)
        seen["before"] = current_scope()
        return real_open(request, slug)

    def spy_find(conn, token):
        seen["scope"] = current_scope()
        return real_find(conn, token)
    monkeypatch.setattr(share_public, "_clinic_open", spy_open)
    monkeypatch.setattr(share_public.sdb, "find_by_token", spy_find)
    assert world.iyer.get(f"/s/{A}/{tok}").status_code == 200
    assert seen["identity"] is None and seen["before"] is None
    assert seen["scope"].clinic_slug == A and seen["scope"].user_id is None
