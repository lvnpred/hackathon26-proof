"""Shared fixtures. Only the multi-clinic tests use `multi`; every other test is unaffected."""
import pytest


@pytest.fixture(autouse=True)
def _clean_clinic_env(monkeypatch):
    """A developer's .env must not leak multi-clinic mode or secrets into the suite."""
    for name in ("MULTI_CLINIC", "DATA_DIR", "SESSION_SECRET", "DEV_INSECURE_SESSION_SECRET"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _private_single_mode_db(tmp_path_factory, monkeypatch):
    """Single-database mode writes the REAL dev database when DB_PATH is unset (doctor_dictation/data/app.db).

    Point it at a per-test temp folder (not tmp_path: tests list that). A test that sets its own DB_PATH wins,
    because its monkeypatch.setenv runs later; the `multi` fixture removes it again (multi-clinic mode ignores it).
    """
    monkeypatch.setenv("DB_PATH", str(tmp_path_factory.mktemp("single-db") / "app.db"))


@pytest.fixture(autouse=True)
def _offline_provider_keys(monkeypatch):
    """No test may reach a real provider through a developer's .env.

    Set blank, never delete: load_dotenv() does not override a variable that exists, so a blank
    survives it, and load_secret() treats a present-but-empty env var as winning over secrets.json.
    The settings snapshot is cached, so drop it too: the next get_settings() rebuilds with blank keys.
    monkeypatch restores the old snapshot at teardown.
    """
    from doctor_dictation import config
    for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.setenv(name, "")
    monkeypatch.setattr(config, "_settings", None)


@pytest.fixture()
def multi(tmp_path, monkeypatch):
    """Multi-clinic mode on, data under a temp folder, a valid session secret, DB_PATH removed so it cannot leak in."""
    monkeypatch.setenv("MULTI_CLINIC", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-" + "x" * 24)
    monkeypatch.delenv("DB_PATH", raising=False)
    return tmp_path
