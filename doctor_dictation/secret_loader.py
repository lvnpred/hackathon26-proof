"""Secret loader + presence report (P0-2).

Precedence for every secret name (implemented exactly):

1. **Environment variable, if PRESENT** -- including when set to the empty
   string. ``os.environ`` *membership* decides "present", NOT truthiness. This
   is what lets the offline determinism tests force "no secret" deterministically
   even when a secrets file exists on the machine.
2. Else the secrets file (``doctor_dictation/secrets.json``, path overridable via the
   ``SECRETS_FILE`` env var).
3. Else absent -> ``""``.

A secret **value** is never logged, printed, or returned in an error/response.
Callers report presence as booleans only (see :func:`secret_presence`).

Stdlib only (``os``, ``json``, ``pathlib``, ``stat``). No network.
"""
import json
import os
import stat
from pathlib import Path

# ``doctor_dictation/secret_loader.py`` lives next to ``main.py``; the default file is
# ``doctor_dictation/secrets.json`` (already gitignored). Renamed from ``secrets.py`` so
# it can never shadow the stdlib ``secrets`` module (ruling R15).
_DEFAULT_SECRETS_FILE = Path(__file__).resolve().parent / "secrets.json"
SECRETS_FILE_ENV = "SECRETS_FILE"


def secrets_file_path() -> Path:
    """Resolve the secrets file path (``SECRETS_FILE`` env, else the default)."""
    env = os.getenv(SECRETS_FILE_ENV)
    return Path(env) if env else _DEFAULT_SECRETS_FILE


def _read_secrets_file(path=None) -> dict:
    """Best-effort read of the secrets file as a JSON object.

    Missing/unreadable/corrupt files yield ``{}`` -- never raise, never echo the
    file contents.
    """
    p = Path(path) if path is not None else secrets_file_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_secret(name, path=None) -> str:
    """Resolve one secret by the precedence chain documented above.

    ``path`` overrides the secrets-file location (mainly for tests). The env var
    membership check happens first and beats the file even when it is empty.
    """
    if name in os.environ:
        return os.environ[name]
    value = _read_secrets_file(path).get(name)
    return value if isinstance(value, str) else ""


def secret_presence(names, path=None, overrides=None) -> dict:
    """Return ``{name: bool}`` presence for ``names`` -- booleans, never values.

    ``overrides`` (optional) map already-resolved values to their presence, so a
    caller holding a settings snapshot (e.g. the health endpoint, which must
    stay monkeypatch-friendly) does not have to re-read the environment.
    """
    overrides = overrides or {}
    out = {}
    for name in names:
        if name in overrides:
            out[name] = bool(overrides[name])
        else:
            out[name] = bool(load_secret(name, path))
    return out


def secure_permissions(path) -> bool:
    """Best-effort: restrict a secrets file to owner-only (POSIX ``0600``).

    Returns ``True`` when permissions were tightened, ``False`` otherwise.

    Windows cannot express POSIX ``0600`` -- ``os.chmod`` there only toggles the
    read-only attribute, and NTFS access is governed by ACLs, not mode bits. So
    on Windows this is a deliberate no-op returning ``False`` rather than
    pretending the file is protected. Lock the file down via ACLs on Windows.
    """
    p = Path(path)
    if not p.exists():
        return False
    if os.name == "nt":
        # Honest no-op: mode bits cannot express 0600 on Windows.
        return False
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        return True
    except OSError:
        return False
