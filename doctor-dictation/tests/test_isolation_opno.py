"""OP numbers (spec 10, 13.1): each clinic has its own prefix and its own sequence, and concurrent saves inside a
clinic still get distinct numbers while the other clinic saves too. Offline."""
import re
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.clinics import clinic_dir
from doctor_dictation.db import opno
from doctor_dictation.db.opno import create_patient_with_new_op
from isolation_fixtures import A, B, H, save, save_body, sql, world  # noqa: F401


DAY = "20300304"


@pytest.fixture()
def frozen_day(monkeypatch):
    """Today is 4 March 2030 for every OP number, the seeded ones included. Request it BEFORE ``world``."""
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2030, 3, 4, 12, 0).astimezone()

    monkeypatch.setattr(opno, "datetime", Frozen)


def _ops(slug):
    return [r["op_no"] for r in sql(slug, "SELECT op_no FROM patients ORDER BY id")]


def _issue(slug, name, gate):
    """A bare thread: its own connection to the clinic file, no scope. Waits on the gate so all threads start together."""
    gate.wait(10)
    with closing(dbmod.get_conn(clinic_dir(slug) / "app.db")) as conn:
        return create_patient_with_new_op(conn, name)[1]


def _prefix_route(client, prefix):
    return client.put("/api/v1/profile", json={"op_prefix": prefix}, headers=H)


def test_both_clinics_start_the_day_at_001_with_their_own_prefix(frozen_day, world):
    a, b = _ops(A)[0], _ops(B)[0]
    assert (a, b) == (f"RAO-{DAY}-001", f"IYER-{DAY}-001")
    assert a != b and a[-12:] == b[-12:]                 # same day and sequence number, different prefix


def test_the_next_number_continues_inside_each_clinic_only(frozen_day, world):
    before = (_ops(A), _ops(B))
    a, b = save(world.mehta, "Next A Patient"), save(world.iyer, "Next B Patient")
    assert (_ops(A)[:-1], _ops(B)[:-1]) == before        # issued numbers are never rewritten
    seq = lambda ops, prefix: len([o for o in ops if o.startswith(f"{prefix}-{DAY}-")])    # noqa: E731
    assert (a["op_no"], b["op_no"]) == (f"RAO-{DAY}-{seq(before[0], 'RAO') + 1:03d}",
                                        f"IYER-{DAY}-{seq(before[1], 'IYER') + 1:03d}")


def test_changing_the_prefix_keeps_old_numbers_and_counts_from_001_under_the_new_one(frozen_day, world):
    before = _ops(A)
    assert _prefix_route(world.rao, "NEWRAO").status_code == 200
    assert _ops(A) == before                                     # issued numbers are never rewritten
    first = save(world.rao, "After Change One")["op_no"]
    second = save(world.mehta, "After Change Two")["op_no"]
    # The day counter is per prefix (opno._day_prefix includes it): a new prefix starts at 001 and then continues.
    assert (first, second) == (f"NEWRAO-{DAY}-001", f"NEWRAO-{DAY}-002")
    assert all(o.startswith("IYER-") for o in _ops(B))           # the other clinic's prefix did not move


def test_concurrent_saves_get_distinct_numbers_inside_each_clinic(frozen_day, world):
    start = (len(_ops(A)), len(_ops(B)))
    jobs = ([(world.rao, f"Rao Rush {i}") for i in range(4)] + [(world.mehta, f"Mehta Rush {i}") for i in range(4)]
            + [(world.iyer, f"Iyer Rush {i}") for i in range(4)])
    with ThreadPoolExecutor(12) as pool:
        results = list(pool.map(lambda job: job[0].post("/api/v1/documents", json=save_body(job[1]), headers=H), jobs))
    assert all(r.status_code == 200 for r in results), [r.text for r in results if r.status_code != 200]
    a_ops, b_ops = {r.json()["op_no"] for r in results[:8]}, {r.json()["op_no"] for r in results[8:]}
    assert len(a_ops) == 8 and all(o.startswith("RAO-") for o in a_ops)
    assert len(b_ops) == 4 and all(o.startswith("IYER-") for o in b_ops)
    assert (len(_ops(A)), len(_ops(B))) == (start[0] + 8, start[1] + 4)

    # Second phase: bare threads, each with its own connection, hitting both clinic files at once.
    mid = (len(_ops(A)), len(_ops(B)))
    gate, out, errors = threading.Barrier(12), {}, []
    plan = [(A, i) for i in range(6)] + [(B, i) for i in range(6)]

    def run(slug, i):
        try:
            out[(slug, i)] = _issue(slug, f"Direct {slug} {i}", gate)
        except Exception as exc:  # noqa: BLE001 - collected and asserted empty after the joins
            errors.append((slug, i, repr(exc)))

    threads = [threading.Thread(target=run, args=job) for job in plan]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not any(t.is_alive() for t in threads)
    assert errors == []
    assert len(out) == 12
    for slug, prefix in ((A, "RAO-"), (B, "IYER-")):
        issued = [out[(slug, i)] for i in range(6)]
        assert len(set(issued)) == 6 and all(o.startswith(prefix) for o in issued)
        stored = _ops(slug)
        assert len(stored) == len(set(stored))           # no number twice in the clinic's file
    assert (len(_ops(A)), len(_ops(B))) == (mid[0] + 6, mid[1] + 6)
