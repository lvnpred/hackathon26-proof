"""Shared fixtures. Only the multi-clinic tests use `multi`; every other test is unaffected."""
import pytest


@pytest.fixture(autouse=True)
def _clean_clinic_env(monkeypatch):
    """A developer's .env must not leak multi-clinic mode or secrets into the suite."""
    for name in ("MULTI_CLINIC", "DATA_DIR", "SESSION_SECRET", "DEV_INSECURE_SESSION_SECRET"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def multi(tmp_path, monkeypatch):
    """Multi-clinic mode on, data under a temp folder, a valid session secret, DB_PATH removed so it cannot leak in."""
    monkeypatch.setenv("MULTI_CLINIC", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-" + "x" * 24)
    monkeypatch.delenv("DB_PATH", raising=False)
    return tmp_path
