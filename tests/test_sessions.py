"""Signed session cookie: round trip, tampering, expiry, hostile input, secret rules. Offline."""
import json

import pytest

from doctor_dictation import sessions as S


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    monkeypatch.delenv(S.DEV_FLAG_ENV, raising=False)


def test_round_trip():
    token = S.sign("rao", 7, 3, now=1000)
    assert S.verify(token, now=1001) == {"clinic": "rao", "uid": 7, "ver": 3, "iat": 1000, "exp": 1000 + S.LIFETIME_SECONDS}


def test_tampered_payload_is_rejected():
    _body, sig = S.sign("rao", 7, 0, now=1000).split(".")
    forged = S._b64(json.dumps({"clinic": "iyer", "uid": 7, "ver": 0, "iat": 1000, "exp": 10**12}).encode())
    assert S.verify(f"{forged}.{sig}", now=1001) is None


def test_tampered_signature_is_rejected():
    body, sig = S.sign("rao", 7, 0, now=1000).split(".")
    bad = sig[:-2] + ("AA" if not sig.endswith("AA") else "BB")
    assert S.verify(f"{body}.{bad}", now=1001) is None


def test_expired_token_is_rejected():
    token = S.sign("rao", 7, 0, now=1000)
    assert S.verify(token, now=1000 + S.LIFETIME_SECONDS - 1) is not None
    assert S.verify(token, now=1000 + S.LIFETIME_SECONDS) is None


def test_token_signed_with_another_secret_is_rejected(monkeypatch):
    token = S.sign("rao", 7, 0, now=1000)
    monkeypatch.setenv("SESSION_SECRET", "z" * 40)
    assert S.verify(token, now=1001) is None


def test_garbage_tokens_return_none_without_raising():
    for token in (None, "", "a", "a.b", "..", "a.b.c", "é.é", "x" * 10000, 12):
        assert S.verify(token, now=1) is None, token


def test_verified_payload_with_bad_field_types_is_rejected():
    good = {"clinic": "rao", "uid": 1, "ver": 0, "iat": 1, "exp": 10**12}
    assert S.verify(S._encode(good), now=2) is not None
    for field, bad in (("clinic", "../x"), ("clinic", 5), ("uid", "1"), ("uid", True), ("ver", None), ("exp", "9"), ("exp", True)):
        assert S.verify(S._encode({**good, field: bad}), now=2) is None, (field, bad)
    assert S.verify(S._encode({"clinic": "rao"}), now=2) is None     # missing fields


def test_session_secret_needs_32_characters(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET")
    with pytest.raises(S.SecretError):
        S.session_secret()
    monkeypatch.setenv("SESSION_SECRET", "x" * 31)
    with pytest.raises(S.SecretError):
        S.session_secret()
    monkeypatch.setenv("SESSION_SECRET", "x" * 32)
    assert S.session_secret() == b"x" * 32


def test_dev_flag_allows_a_fixed_secret_only_when_exactly_1(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET")
    monkeypatch.setenv(S.DEV_FLAG_ENV, "true")
    with pytest.raises(S.SecretError):
        S.session_secret()
    monkeypatch.setenv(S.DEV_FLAG_ENV, "1")
    assert len(S.session_secret()) >= S.MIN_SECRET_LENGTH
