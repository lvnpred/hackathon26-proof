"""Password hashing and temporary passwords. Standard library only (scrypt).

The stored form carries its own parameters, so they can be raised later without breaking old hashes:
``scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P, DKLEN, SALT_BYTES = 2**14, 8, 1, 32, 16
MAXMEM = 64 * 1024 * 1024
MIN_LENGTH, MAX_LENGTH, TEMP_LENGTH = 10, 200, 16
_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/l/I
_dummy: str | None = None


class PasswordError(ValueError):
    """A new password does not meet the rules."""


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=MAXMEM)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, N, R, P, DKLEN)
    return "$".join(("scrypt", str(N), str(R), str(P), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()))


def verify_password(password: str, stored) -> bool:
    """True only for a matching password. Any malformed or hostile ``stored`` value is simply False."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        n, r, p = int(n), int(r), int(p)
        if scheme != "scrypt" or not (2**10 <= n <= 2**15 and 1 <= r <= 8 and 1 <= p <= 4):
            return False
        want = base64.b64decode(digest, validate=True)
        got = _scrypt(password, base64.b64decode(salt, validate=True), n, r, p, len(want))
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(got, want)


def dummy_verify(password) -> bool:
    """Spend one scrypt computation and return False: used for unknown, locked and disabled logins."""
    global _dummy
    _dummy = _dummy or hash_password(secrets.token_urlsafe(8))
    verify_password(password, _dummy)
    return False


def temp_password() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(TEMP_LENGTH))


def check_new_password(password) -> None:
    if not isinstance(password, str) or not MIN_LENGTH <= len(password) <= MAX_LENGTH:
        raise PasswordError(f"password must be {MIN_LENGTH} to {MAX_LENGTH} characters")
