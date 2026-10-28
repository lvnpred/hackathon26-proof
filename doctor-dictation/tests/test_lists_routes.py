"""The clinic list routes (plan PQ-f, Task 6): GET /api/v1/lists/{kind} and POST /api/v1/lists/{kind}/changes. Offline.
The world of test_users_routes: dr.rao and dr.iyer are admins of different clinics, dr.mehta is a doctor of Rao's clinic."""
import json
import sqlite3
import threading
from contextlib import closing

from doctor_dictation import db as dbmod
from doctor_dictation.core import overlay
from doctor_dictation.db import overlay as odb
from test_users_routes import H, _conn, _signed_in, world  # noqa: F401

COMBO = "Aceclofenac + Paracetamol"
ADD = {"op": "add", "entry_key": "zerodol-p", "data": {"name": "Zerodol-P", "generic": COMBO}}
ROW = {"form": "Tab.", "name": "Zerodol-P", "strength": "10 mg", "dose": "1-0-0", "timing": "", "duration": "5 days",
       "instructions": "", "status": "verified", "lexicon_match": "", "heard": "", "lookalike": ""}
TRANSCRIPT = "tablet Zerodol-P 10 mg once daily for 5 days"


def post(client, op, key, data=None, kind="medicine"):
    body = {"op": op, "entry_key": key, **({"data": data} if data is not None else {})}
    return client.post(f"/api/v1/lists/{kind}/changes", json=body, headers=H)


def items(client, kind="medicine"):
    r = client.get(f"/api/v1/lists/{kind}", headers=H)
    assert r.status_code == 200, r.text
    return {i["entry_key"]: i for i in r.json()["items"]}


def sql(slug, query, *args):
    with closing(_conn(slug)) as c:
        rows = c.execute(query, args).fetchall()
        c.commit()
    return rows


def audits(slug):
    return [tuple(r) for r in sql(slug, "SELECT action, entity, entity_id FROM audit_log WHERE action LIKE 'list.%' ORDER BY id")]


def count(slug):
    return sql(slug, "SELECT COUNT(*) FROM clinic_overlay")[0][0], len(audits(slug))


def confirm_once(slug, key="zerodol-p"):
    with closing(_conn(slug)) as c:
        eid = dbmod.create_encounter(c, dbmod.create_patient(c, "P", "40 / M", None))
        d = dbmod.save_document(c, eid, "sha1", {"rx": []})
        return odb.record_confirmation(c, "medicine", key, "add", {"name": "Zerodol-P", "generic": COMBO}, "", d, None)


def test_add_then_list_shows_clinic_added(world):
    with _signed_in("dr.rao") as (rao,):
        r = post(rao, "add", "zerodol-p", ADD["data"])
        assert r.status_code == 200 and r.json()["item"]["badge"] == "clinic-added"
        got = rao.get("/api/v1/lists/medicine", headers=H).json()
        assert got["kind"] == "medicine" and got["flags"] == 0 and got["pending"] == 0
        assert items(rao)["zerodol-p"]["entry"]["brands"] == ["Zerodol-P"]
        assert "aceclofenac" in items(rao) and items(rao)["aceclofenac"]["badge"] == "shipped"


def test_the_next_request_sees_the_change(world):
    with _signed_in("dr.rao") as (rao,):
        check = lambda: rao.post("/api/v1/rx/check-row", json={"row": dict(ROW), "transcript": TRANSCRIPT}, headers=H).json()["row"]  # noqa: E731
        before = check()
        assert before["status"] != "verified", before
        assert post(rao, "add", "zerodol-p", ADD["data"]).status_code == 200
        after = check()
        assert after["status"] == "verified" and after != before, (before, after)


def test_edit_of_a_shipped_entry_stores_its_sha(world):
    from doctor_dictation.core import determinism
    shipped = next(e for e in determinism.shipped_lexicon() if e["canonical"] == "Aceclofenac")
    with _signed_in("dr.rao") as (rao,):
        r = post(rao, "edit", "aceclofenac", {"brands": ["Zerodol", "Acemiz"]})
        assert r.status_code == 200
        it = r.json()["item"]
        assert it["badge"] == "clinic-edited" and it["flag"] == "" and "Acemiz" in it["entry"]["brands"]
    (row,) = sql("rao", "SELECT action, base_sha, source FROM clinic_overlay")
    assert tuple(row) == ("edit", overlay.entry_sha(shipped), "admin")


def test_hide_then_reset_restores_shipped(world):
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "hide", "aceclofenac").json()["item"]["badge"] == "hidden"
        assert items(rao)["aceclofenac"]["badge"] == "hidden"
        r = post(rao, "reset", "aceclofenac")
        assert r.status_code == 200 and r.json()["item"]["badge"] == "shipped"
        assert post(rao, "reset", "aceclofenac").status_code == 404
    assert [a[0] for a in audits("rao")] == ["list.hide", "list.reset"]


def test_readding_a_hidden_name_points_to_reset_and_hiding_an_own_addition_too(world):
    with _signed_in("dr.rao") as (rao,):
        post(rao, "hide", "ibuprofen")                      # not Zerodol-P's generic: that hide or the add after it is refused
        r = post(rao, "add", "ibuprofen", {"name": "Ibuprofen", "generic": "Ibuprofen"})
        assert r.status_code == 409 and "Reset" in r.json()["error"]
        post(rao, "add", "zerodol-p", ADD["data"])
        r = post(rao, "hide", "zerodol-p")
        assert r.status_code == 409 and "Reset" in r.json()["error"]


def test_an_add_or_edit_naming_a_hidden_generic_is_refused(world):          # final review I2
    with _signed_in("dr.rao") as (rao,):
        post(rao, "hide", "paracetamol")
        r = post(rao, "add", "barprol", {"name": "Barprol", "generic": "Paracetamol"})
        assert r.status_code == 409 and r.json()["error"] == "Paracetamol is hidden on your list: Reset it first"
        r = post(rao, "add", "foocomb", {"name": "Foocomb", "generic": "Ibuprofen + Paracetamol"})
        assert r.status_code == 409 and r.json()["error"] == "Paracetamol is hidden on your list: Reset it first"
        r = post(rao, "edit", "ibuprofen", {"generic": "paracetamol"})
        assert r.status_code == 409 and "hidden on your list" in r.json()["error"]
        assert post(rao, "reset", "paracetamol").status_code == 200
        assert post(rao, "add", "barprol", {"name": "Barprol", "generic": "Paracetamol"}).status_code == 200


def test_hiding_a_medicine_a_clinic_row_uses_as_its_generic_is_refused_until_that_row_goes(world):   # mirror of I2
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "add", "fooprol", {"name": "Fooprol", "generic": "Paracetamol"}).status_code == 200
        r = post(rao, "hide", "paracetamol")
        assert r.status_code == 409
        assert r.json()["error"] == "Paracetamol is the generic of Fooprol on your list: edit or reset Fooprol first"
        assert post(rao, "reset", "fooprol").status_code == 200
        assert post(rao, "hide", "paracetamol").status_code == 200


def stale(slug):
    with closing(_conn(slug)) as c:
        odb.upsert(c, "medicine", "aceclofenac", "edit", {"brands": ["Zerodol", "Acemiz"]}, "stale", "admin", None)


def test_keep_mine_clears_the_flag(world):
    stale("rao")
    with _signed_in("dr.rao") as (rao,):
        assert items(rao)["aceclofenac"]["flag"] == "shipped-changed"
        assert rao.get("/api/v1/lists/medicine", headers=H).json()["flags"] == 1
        r = post(rao, "keep-mine", "aceclofenac")
        assert r.status_code == 200 and r.json()["item"]["flag"] == "" and "Acemiz" in r.json()["item"]["entry"]["brands"]
        assert post(rao, "keep-mine", "aceclofenac").status_code == 409        # no longer flagged
    assert audits("rao") == [("list.keep-mine", "list.medicine", "aceclofenac")]


def test_take_new_removes_the_row(world):
    stale("rao")
    with _signed_in("dr.rao") as (rao,):
        r = post(rao, "take-new", "aceclofenac")
        assert r.status_code == 200 and r.json()["item"]["badge"] == "shipped"
        assert post(rao, "take-new", "aceclofenac").status_code == 404        # the row is gone
    assert sql("rao", "SELECT COUNT(*) FROM clinic_overlay WHERE removed_at IS NULL")[0][0] == 0


def test_pending_row_is_listed_with_its_count(world):
    assert confirm_once("rao") == 1
    with _signed_in("dr.rao") as (rao,):
        got = rao.get("/api/v1/lists/medicine", headers=H).json()
        it = items(rao)["zerodol-p"]
        assert it["badge"] == "learned" and it["pending"]["count"] == 1 and it["pending"]["threshold"] == 2
        assert got["pending"] == 1 and got["flags"] == 0
        check = rao.post("/api/v1/rx/check-row", json={"row": dict(ROW), "transcript": TRANSCRIPT}, headers=H).json()["row"]
        assert check["status"] != "verified" or check.get("source") != "lexicon"


def test_approve_makes_it_live_and_audits(world):
    confirm_once("rao")
    with _signed_in("dr.rao") as (rao,):
        r = post(rao, "approve", "zerodol-p")
        assert r.status_code == 200 and r.json()["item"]["pending"] is None and r.json()["item"]["badge"] == "clinic-added"
        assert items(rao)["zerodol-p"]["pending"] is None
        assert post(rao, "approve", "zerodol-p").status_code == 404
    assert audits("rao") == [("list.approve", "list.medicine", "zerodol-p")]


def test_every_write_is_audited(world):
    with _signed_in("dr.rao") as (rao,):
        post(rao, "add", "zerodol-p", ADD["data"])
        post(rao, "edit", "zerodol-p", {"name": "Zerodol-P", "generic": COMBO, "aliases": ["zerodol p"]})
        post(rao, "hide", "ibuprofen")                 # not Paracetamol: Zerodol-P's generic uses it (a hide is refused)
        post(rao, "reset", "ibuprofen")
    stale("rao")
    with _signed_in("dr.rao") as (rao,):
        post(rao, "keep-mine", "aceclofenac")
    stale("rao")
    with _signed_in("dr.rao") as (rao,):
        post(rao, "take-new", "aceclofenac")
    assert [a[0] for a in audits("rao")] == ["list.add", "list.edit", "list.hide", "list.reset", "list.keep-mine",
                                             "list.take-new"]
    assert all(a[1] == "list.medicine" for a in audits("rao"))
    detail = json.loads(sql("rao", "SELECT detail FROM audit_log WHERE action = 'list.add'")[0][0])
    assert detail == {"before": None, "after": ADD["data"]}


def test_investigation_works_with_an_empty_shipped_list(world):
    with _signed_in("dr.rao") as (rao,):
        r = post(rao, "add", "rft", {"name": "RFT"}, kind="investigation")
        assert r.status_code == 200 and r.json()["item"]["entry"]["canonical"] == "RFT"
        assert list(items(rao, "investigation")) == ["rft"]
        assert post(rao, "edit", "nothing", {"aliases": ["x"]}, kind="investigation").status_code == 404


def test_a_doctor_gets_403_and_nothing_changes(world):
    before = count("rao")
    with _signed_in("dr.mehta") as (mehta,):
        answers = [post(mehta, op, "aceclofenac", {"brands": ["Zerodol"]}) for op in
                   ("add", "edit", "hide", "reset", "keep-mine", "take-new", "approve")]
    assert all(r.status_code == 403 and r.json() == {"error": "You are not allowed to do that"} for r in answers)
    assert count("rao") == before


def test_bad_input_is_400_and_nothing_written(world):
    before = count("rao")
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "frobnicate", "x").status_code == 422
        assert post(rao, "add", "", {"name": "Zerodol-P", "generic": COMBO}).status_code == 422
        aliases = [f"alias {chr(97 + i)}x" for i in range(21)]
        r = post(rao, "edit", "aceclofenac", {"aliases": aliases})
        assert r.status_code == 400 and "20" in r.json()["error"]
        r = post(rao, "add", "wrong-key", {"name": "Zerodol-P", "generic": COMBO})
        assert r.status_code == 400 and "does not match" in r.json()["error"]
        r = post(rao, "add", "aceclofenac", {"name": "Aceclofenac", "generic": "Aceclofenac"})
        assert r.status_code == 409
        assert post(rao, "edit", "no-such-drug", {"aliases": ["abc"]}).status_code == 404
        assert post(rao, "hide", "no-such-drug").status_code == 404
        assert post(rao, "add", "x", {"name": "Zerodol-P"}).status_code == 400            # a medicine needs its generic
        assert rao.get("/api/v1/lists/drugs", headers=H).status_code == 404
        assert post(rao, "add", "zerodol-p", ADD["data"], kind="drugs").status_code == 404
    assert count("rao") == before


def test_a_write_the_read_path_would_ignore_is_refused(world):
    with _signed_in("dr.rao") as (rao,):
        r = post(rao, "edit", "aceclofenac", {"generic": "Zerodol"})                   # a brand cannot be the generic
        assert r.status_code == 409 and "Zerodol" in r.json()["error"] and r.json()["reasons"]
    assert count("rao")[0] == 0


def test_other_clinic_cannot_see_or_reset(world):
    with _signed_in("dr.rao", "dr.iyer") as (rao, iyer):
        post(rao, "add", "zerodol-p", ADD["data"])
        assert "zerodol-p" not in items(iyer)
        assert post(iyer, "reset", "zerodol-p").status_code == 404
        assert post(iyer, "edit", "zerodol-p", ADD["data"]).status_code == 404
        assert items(rao)["zerodol-p"]["badge"] == "clinic-added"
    assert count("iyer") == (0, 0) and count("rao") == (1, 1)


def test_a_failed_audit_row_leaves_no_change_behind(world, monkeypatch):
    def broken(*_a, **_k):
        raise sqlite3.OperationalError("disk full")
    with _signed_in("dr.rao") as (rao,):
        with monkeypatch.context() as patch:
            patch.setattr(dbmod, "log_audit", broken)
            r = post(rao, "add", "zerodol-p", ADD["data"])
        assert r.status_code == 503 and r.json() == {"error": "try again"}
        assert "zerodol-p" not in items(rao)
    assert count("rao") == (0, 0)


def test_two_admins_cannot_both_pass_a_check_against_the_same_rows(world):
    first = {"name": "Fooqx", "generic": "Barqgen"}
    second = {"name": "Barqgen", "generic": "Paracetamol"}      # Barqgen is the other row's generic
    with _signed_in("dr.rao", "dr.rao") as (a, b):
        barrier, out = threading.Barrier(2), {}

        def run(tag, client, key, data):
            barrier.wait()
            out[tag] = post(client, "add", key, data).status_code
        threads = [threading.Thread(target=run, args=("a", a, "fooqx", first)),
                   threading.Thread(target=run, args=("b", b, "barqgen", second))]
        [t.start() for t in threads]
        [t.join() for t in threads]
    assert sorted(out.values()) == [200, 409], out
    assert count("rao") == (1, 1)


def test_hide_with_data_is_400_and_nothing_written(world):
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "hide", "aceclofenac", {"brands": ["x"]}).status_code == 400
    assert count("rao") == (0, 0)


def pending_add(slug):
    assert confirm_once(slug) == 1


def test_edit_of_a_pending_addition_replaces_it_and_goes_live(world):
    pending_add("rao")
    with _signed_in("dr.rao") as (rao,):
        r = post(rao, "edit", "zerodol-p", {"name": "Zerodol-P", "generic": COMBO, "aliases": ["zerodol p"]})
        assert r.status_code == 200 and r.json()["item"]["badge"] == "clinic-added" and r.json()["item"]["pending"] is None
    assert sql("rao", "SELECT source FROM clinic_overlay")[0][0] == "admin"


def test_hide_of_a_pending_addition_is_refused_like_an_own_addition_and_reset_removes_it(world):
    pending_add("rao")
    with _signed_in("dr.rao") as (rao,):
        r = post(rao, "hide", "zerodol-p")
        assert r.status_code == 409 and "Reset" in r.json()["error"]
        assert post(rao, "reset", "zerodol-p").status_code == 200
        assert "zerodol-p" not in items(rao)


def test_keep_mine_and_take_new_without_a_row_are_404(world):
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "keep-mine", "aceclofenac").status_code == 404
        assert post(rao, "take-new", "aceclofenac").status_code == 404
        assert post(rao, "approve", "aceclofenac").status_code == 404
    assert count("rao") == (0, 0)


# ---- investigations: hidden names and shadowed adds (plan PQ-h Task 7 follow-up) --------------------------------------

IX_CAT = [{"canonical": "Renal Function Test", "aliases": ["rft", "kft"], "category": "Blood", "print": "RFT"},
          {"canonical": "Vit D Level", "aliases": ["vitamin d"], "category": "Blood", "print": ""},
          {"canonical": "Urine C&S", "aliases": ["urine culture"], "category": "Urine", "print": ""}]


def _ix_catalogue(monkeypatch, tmp_path):
    from test_investigations_api import activate_catalogue
    activate_catalogue(monkeypatch, IX_CAT, tmp_path)


def _ix_lookup(client, text):
    return client.post("/api/v1/investigations/lookup", json={"text": text}, headers=H).json()


def test_a_hidden_test_name_cannot_become_another_tests_alias(world, monkeypatch, tmp_path):
    _ix_catalogue(monkeypatch, tmp_path)
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "hide", "vit d level", kind="investigation").status_code == 200
        for alias in ("Vit. D Level", "Vitamin-D"):
            r = post(rao, "edit", "renal function test", {"aliases": ["rft", "kft", alias]}, kind="investigation")
            assert r.status_code == 409 and r.json()["error"] == f"{alias} is hidden on your list: Reset it first", r.text
        r = post(rao, "edit", "renal function test", {"aliases": ["rft", "vit-d level"]}, kind="investigation")
        assert r.status_code == 409, r.text                                  # the hidden canonical (refused before too)
        r = post(rao, "add", "vit. d level", {"name": "Vit. D Level"}, kind="investigation")
        assert r.status_code == 409 and r.json()["error"] == "Vit. D Level is hidden on your list: Reset it first"
        assert _ix_lookup(rao, "Vit D Level") == {"canonical": "", "status": "new"}
        assert post(rao, "edit", "renal function test", {"aliases": ["rft", "kft", "Kidney panel"]},
                    kind="investigation").status_code == 200                 # a name nobody hid is still fine
        assert _ix_lookup(rao, "Kidney panel")["canonical"] == "Renal Function Test"


def test_an_add_the_shipped_test_would_shadow_is_refused(world, monkeypatch, tmp_path):
    _ix_catalogue(monkeypatch, tmp_path)
    with _signed_in("dr.rao") as (rao,):
        r = post(rao, "add", "urine c and s", {"name": "Urine C and S"}, kind="investigation")
        assert r.status_code == 409 and r.json()["error"] == "'Urine C and S' is already on the list — edit it instead"
        assert _ix_lookup(rao, "Urine C and S")["canonical"] == "Urine C&S"
        assert post(rao, "add", "urine c&s culture", {"name": "Urine C&S Culture"},
                    kind="investigation").status_code == 200


def test_a_hidden_test_spelled_by_letters_is_refused(world, monkeypatch, tmp_path):         # final review I2
    _ix_catalogue(monkeypatch, tmp_path)
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "hide", "renal function test", kind="investigation").status_code == 200
        for name in ("K.F.T", "R F T", "r.f.t.", "Repeat KFT", "Repeat R F T", "RFT test", "Rft Profile", "k.f.t. test"):
            r = post(rao, "add", overlay.entry_key_of({"canonical": name}), {"name": name}, kind="investigation")
            assert r.status_code == 409 and r.json()["error"] == f"{name} is hidden on your list: Reset it first", r.text
            r = post(rao, "edit", "vit d level", {"aliases": ["vitamin d", name]}, kind="investigation")
            assert r.status_code == 409 and "hidden on your list" in r.json()["error"], r.text
        assert [_ix_lookup(rao, t)["status"] for t in ("k f t", "R.F.T", "kft")] == ["new"] * 3


def test_an_add_spelling_any_shipped_name_is_refused(world, monkeypatch, tmp_path):            # final review M1
    _ix_catalogue(monkeypatch, tmp_path)
    with _signed_in("dr.rao") as (rao,):
        for name in ("R.F.T", "K F T", "Urine-Culture", "VitaminD", "Vit. D Level"):
            r = post(rao, "add", overlay.entry_key_of({"canonical": name}), {"name": name}, kind="investigation")
            assert r.status_code == 409 and r.json()["error"] == f"'{name}' is already on the list — edit it instead", r.text
        assert _ix_lookup(rao, "r f t")["canonical"] == "Renal Function Test"
        assert post(rao, "add", "kidney panel", {"name": "Kidney Panel"}, kind="investigation").status_code == 200


def test_a_set_aside_test_row_is_flagged_on_the_list_and_freezes_nothing(world, monkeypatch, tmp_path):
    """Final re-review: an admin add stored before a rule now refuses it is listed with a flag, not blocked."""
    _ix_catalogue(monkeypatch, tmp_path)
    with _signed_in("dr.rao") as (rao,):
        with closing(_conn("rao")) as c:
            odb.upsert(c, "investigation", "r.f.t", "add", {"name": "R.F.T", "aliases": [], "category": "", "print": ""},
                       "", "admin", None)
        got = rao.get("/api/v1/lists/investigation", headers=H).json()
        item = next(i for i in got["items"] if i["entry_key"] == "r.f.t")
        assert item["flag"] == "shipped-changed" and "already on the list" in item["flag_reason"] and got["flags"] >= 1
        assert _ix_lookup(rao, "r f t")["canonical"] == "Renal Function Test"
        assert post(rao, "edit", "renal function test", {"aliases": ["rft", "kft", "R.F.T"]},
                    kind="investigation").status_code == 200                  # not "hidden on your list"
        assert post(rao, "reset", "r.f.t", kind="investigation").status_code == 200


def test_medicine_hidden_generic_rule_is_unchanged(world):
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "hide", "aceclofenac").status_code == 200
        r = post(rao, "add", "zerodol-p", ADD["data"])
        assert r.status_code == 409 and r.json()["error"] == "Aceclofenac is hidden on your list: Reset it first"
