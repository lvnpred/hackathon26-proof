"""Password hashing: round trip, salts, hostile hashes, temporary passwords. Offline."""
import hashlib

import pytest

from doctor_dictation import passwords as P


def test_hash_and_verify_round_trip():
    h = P.hash_password("correct horse battery")
    assert h.startswith("scrypt$16384$8$1$")
    assert P.verify_password("correct horse battery", h) is True
    assert P.verify_password("correct horse batterY", h) is False


def test_each_hash_has_its_own_salt():
    a, b = P.hash_password("same password!"), P.hash_password("same password!")
    assert a != b
    assert P.verify_password("same password!", a) and P.verify_password("same password!", b)


def test_verify_rejects_malformed_and_hostile_hashes_without_raising():
    parts = P.hash_password("secret-pass-1").split("$")
    hostile = [
        "", "x", None, 7, "scrypt$1$1$1$a$b",
        "$".join(["scrypt", str(2**30), "8", "1", parts[4], parts[5]]),   # memory bomb
        "$".join(["scrypt", "16384", "8", "1", "***", parts[5]]),         # bad base64
        "$".join(["bcrypt"] + parts[1:]),                                 # wrong scheme
        "$".join(parts[:5]),                                              # digest missing
    ]
    for stored in hostile:
        assert P.verify_password("secret-pass-1", stored) is False, stored


def test_temp_password_shape():
    a, b = P.temp_password(), P.temp_password()
    assert len(a) == P.TEMP_LENGTH == 16 and a != b
    assert set(a) <= set(P._ALPHABET)
    assert not set(a) & set("0O1lI")          # no look-alike characters


def test_check_new_password_rules():
    P.check_new_password("x" * 10)
    P.check_new_password("x" * 200)
    for bad in ("", "x" * 9, "x" * 201, None, 123):
        with pytest.raises(P.PasswordError):
            P.check_new_password(bad)


def test_dummy_verify_runs_a_real_scrypt_and_returns_false(monkeypatch):
    calls, real = [], hashlib.scrypt
    monkeypatch.setattr(P.hashlib, "scrypt", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    P._dummy = None
    assert P.dummy_verify("whatever") is False
    assert len(calls) >= 2                    # one to build the cached dummy hash, one for the comparison
    calls.clear()
    assert P.dummy_verify("whatever") is False and len(calls) == 1
