"""Spec 10: OP numbers carry the clinic's prefix; per-clinic sequences; concurrency; edits. Offline."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation.db.opno import check_op_prefix, create_patient_with_new_op, get_op_prefix, next_op_no, set_op_prefix
from doctor_dictation.directory import DirectoryError, get_clinic, open_directory, set_clinic_op_prefix
from doctor_dictation.scope import Scope, clinic_dir, use_scope
from letterhead_fixtures import rao, record_renders  # noqa: F401
from template_fixtures import tclient, tconn  # noqa: F401

NOW = datetime(2026, 10, 14, 9, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
PROFILE = "/api/v1/profile"
SAVE = {"structured": {"patientName": "Anita", "opNo": "", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}


def _with_prefix(c, value):
    """Today's profile (seven flat keys) sent back unchanged except the prefix."""
    return {**c.get(PROFILE).json(), "op_prefix": value}


def test_prefix_defaults_to_op_and_follows_the_clinic_copy(tconn):
    assert get_op_prefix(tconn) == "OP" and next_op_no(tconn, now=NOW) == "OP-20261014-001"
    assert set_op_prefix(tconn, "rao") == "RAO"
    assert get_op_prefix(tconn) == "RAO" and next_op_no(tconn, now=NOW) == "RAO-20261014-001"
    tconn.execute("UPDATE clinic_profile SET op_prefix = 'bad prefix'")
    tconn.commit()
    assert get_op_prefix(tconn) == "OP"                    # an invalid stored value never reaches a number


def test_check_op_prefix_rules():
    assert check_op_prefix("rao") == "RAO" and check_op_prefix(" iy2 ") == "IY2" and check_op_prefix("OP") == "OP"
    for bad in ("", "R", "RAOCLIN", "R-1", "R O", None, 12, "ΩΩ"):
        with pytest.raises(ValueError):
            check_op_prefix(bad)


def test_changing_the_prefix_never_rewrites_issued_numbers(tconn):
    pid = dbmod.create_patient(tconn, "Old", op_no="OP-20261014-003")
    set_op_prefix(tconn, "RAO")
    assert next_op_no(tconn, now=NOW) == "RAO-20261014-001"
    assert dbmod.get_patient(tconn, pid)["op_no"] == "OP-20261014-003"
    set_op_prefix(tconn, "OP")
    assert next_op_no(tconn, now=NOW) == "OP-20261014-004"


def test_two_clinics_first_patient_same_day_get_different_strings(multi):
    clinics.provision_clinic("rao", "Rao Clinic", "RAO")
    clinics.provision_clinic("iyer", "Iyer Clinic", "IYR")
    got = {}
    for slug in ("rao", "iyer"):
        with use_scope(Scope(slug)), closing(dbmod.get_conn()) as conn:
            got[slug] = create_patient_with_new_op(conn, "First", now=NOW)[1]
    assert got == {"rao": "RAO-20261014-001", "iyer": "IYR-20261014-001"}


def test_concurrent_first_saves_inside_one_clinic_stay_distinct(multi):
    clinics.provision_clinic("rao", "Rao Clinic", "RAO")
    path = clinic_dir("rao") / "app.db"

    def one(i):
        with closing(dbmod.get_conn(path)) as conn:
            return create_patient_with_new_op(conn, f"P{i}", now=NOW)[1]
    with ThreadPoolExecutor(8) as ex:
        ops = list(ex.map(one, range(8)))
    assert sorted(ops) == [f"RAO-20261014-{n:03d}" for n in range(1, 9)]


def test_provision_and_migrate_all_mirror_the_directory_prefix(multi):
    clinics.provision_clinic("rao", "Rao Clinic", "RAO")
    path = clinic_dir("rao") / "app.db"
    with closing(dbmod.get_conn(path)) as conn:
        assert get_op_prefix(conn) == "RAO"
        conn.execute("UPDATE clinic_profile SET op_prefix = NULL")          # a clinic created before this plan
        conn.commit()
        assert get_op_prefix(conn) == "OP"
    with closing(open_directory()) as d:
        set_clinic_op_prefix(d, "rao", "RK")
    done, failed = clinics.migrate_all()
    assert failed == {} and "rao" in done
    with closing(dbmod.get_conn(path)) as conn:
        assert get_op_prefix(conn) == "RK"


def test_set_clinic_op_prefix_validates_and_reports_unknown_clinics(multi):
    clinics.provision_clinic("rao", "Rao Clinic", "RAO")
    with closing(open_directory()) as d:
        assert set_clinic_op_prefix(d, "rao", "RAO2") is True and get_clinic(d, "rao")["op_prefix"] == "RAO2"
        assert set_clinic_op_prefix(d, "nobody", "ZZ") is False
        for bad in ("r", "rao", "TOOLONG", "R-1", None):
            with pytest.raises(DirectoryError):
                set_clinic_op_prefix(d, "rao", bad)
        assert get_clinic(d, "rao")["op_prefix"] == "RAO2"


def test_profile_route_shows_and_changes_the_prefix_in_both_places(rao, monkeypatch):
    record_renders(monkeypatch)
    got = rao.rao.get(PROFILE).json()
    assert got["op_prefix"] == "RAO" and list(got)[-1] == "op_prefix"
    r = rao.mehta.put(PROFILE, json=_with_prefix(rao.mehta, "rk2"))
    assert r.status_code == 200, r.text
    assert r.json()["op_prefix"] == "RK2" and rao.rao.get(PROFILE).json()["op_prefix"] == "RK2"
    with closing(open_directory()) as d:
        assert get_clinic(d, "rao")["op_prefix"] == "RK2"
    saved = rao.rao.post("/api/v1/documents", json=SAVE)
    assert saved.status_code == 200 and saved.json()["op_no"].startswith("RK2-")


def test_profile_route_rejects_a_bad_prefix_and_changes_nothing(rao):
    before = rao.rao.get(PROFILE).json()
    r = rao.rao.put(PROFILE, json={**_with_prefix(rao.rao, "R-1"), "clinic_name": "Changed"})
    assert r.status_code == 400 and "OP prefix" in r.json()["error"]
    assert rao.rao.get(PROFILE).json() == before


def test_single_mode_prefix_round_trip_and_an_old_client_keeps_it(tclient, monkeypatch):
    record_renders(monkeypatch)
    assert tclient.put(PROFILE, json=_with_prefix(tclient, "cln")).status_code == 200
    assert tclient.get(PROFILE).json()["op_prefix"] == "CLN"
    old = {k: v for k, v in tclient.get(PROFILE).json().items() if k != "op_prefix"}
    assert tclient.put(PROFILE, json=old).status_code == 200            # a client that does not know the field
    assert tclient.get(PROFILE).json()["op_prefix"] == "CLN"
    assert tclient.post("/api/v1/documents", json=SAVE).json()["op_no"].startswith("CLN-")


def test_check_op_prefix_rejects_unicode_that_folds_to_ascii():
    for bad in ("ßß", "ſſ", "ﬁx"):                        # 'ßß'.upper() == 'SSSS', 'ſſ'.upper() == 'SS'
        with pytest.raises(ValueError, match="OP prefix must be 2 to 6 letters or digits"):
            check_op_prefix(bad)


def test_profile_route_answers_an_error_when_the_directory_does_not_know_the_clinic(rao, monkeypatch):
    import doctor_dictation.api.profile as profile_api
    monkeypatch.setattr(profile_api, "set_clinic_op_prefix", lambda *a, **k: False)
    r = rao.rao.put(PROFILE, json=_with_prefix(rao.rao, "ZZ9"))
    assert r.status_code == 404 and "error" in r.json()
    assert rao.rao.get(PROFILE).json()["op_prefix"] == "RAO"        # the clinic copy was not written
