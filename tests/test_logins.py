"""Username index and login throttling in the directory database. Offline."""
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from doctor_dictation import directory as D
from doctor_dictation.directory import logins as L

T0 = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def d(multi):
    with closing(D.open_directory()) as conn:
        D.create_clinic(conn, "rao", "Rao Clinic")
        D.create_clinic(conn, "iyer", "Iyer Clinic")
        yield conn


def _attempt(d):
    return d.execute("SELECT failed_count, locked_until FROM login_attempts").fetchone()


def test_index_and_lookup_ignore_case(d):
    L.index_username(d, "Dr.Rao", "rao", 1)
    row = L.lookup_username(d, "dr.RAO")
    assert (row["clinic_slug"], row["user_id"]) == ("rao", 1)
    assert L.lookup_username(d, "nobody") is None


def test_a_taken_username_is_refused_whatever_its_case(d):
    L.index_username(d, "Dr.Rao", "rao", 1)
    with pytest.raises(D.DirectoryError, match="already taken"):
        L.index_username(d, "dr.rao", "iyer", 9)


def test_an_unknown_clinic_is_refused(d):
    with pytest.raises(D.DirectoryError, match="unknown clinic"):
        L.index_username(d, "dr.x", "ghost", 1)
    assert L.lookup_username(d, "dr.x") is None


def test_drop_username_frees_it(d):
    L.index_username(d, "dr.rao", "rao", 1)
    L.drop_username(d, "DR.RAO")
    assert L.lookup_username(d, "dr.rao") is None
    L.index_username(d, "dr.rao", "iyer", 2)


def test_five_failures_lock_and_four_do_not(d):
    for _ in range(4):
        L.record_failure(d, "dr.rao", "1.2.3.4", T0)
        assert L.is_locked(d, "dr.rao", "1.2.3.4", T0) is False
    L.record_failure(d, "dr.rao", "1.2.3.4", T0)
    assert L.is_locked(d, "dr.rao", "1.2.3.4", T0) is True


def test_lock_expires_after_five_minutes_and_the_count_restarts(d):
    for _ in range(5):
        L.record_failure(d, "dr.rao", "ip", T0)
    assert L.is_locked(d, "dr.rao", "ip", T0 + timedelta(seconds=299)) is True
    later = T0 + timedelta(seconds=300)
    assert L.is_locked(d, "dr.rao", "ip", later) is False
    L.record_failure(d, "dr.rao", "ip", later)
    row = _attempt(d)
    assert (row["failed_count"], row["locked_until"]) == (1, None)


def test_clear_failures_and_separate_keys_per_username_and_ip(d):
    for _ in range(5):
        L.record_failure(d, "dr.rao", "ip1", T0)
    assert L.is_locked(d, "dr.rao", "ip2", T0) is False
    assert L.is_locked(d, "dr.iyer", "ip1", T0) is False
    L.clear_failures(d, "DR.RAO", "ip1")
    assert L.is_locked(d, "dr.rao", "ip1", T0) is False


def test_failures_while_locked_do_not_extend_the_lock(d):
    for _ in range(5):
        L.record_failure(d, "dr.rao", "ip", T0)
    before = tuple(_attempt(d))
    L.record_failure(d, "dr.rao", "ip", T0 + timedelta(seconds=100))
    assert tuple(_attempt(d)) == before
